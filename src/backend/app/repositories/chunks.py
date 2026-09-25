"""D10: material revisions and immutable source chunks in SQLite.

Implements ADR-012 revision 1 decision 9 and ADR-018 (``specs/teacher-review-publish.md`` V2
「资料修订」「文本块不可变」「文本块删除保护」; ``specs/task-processing.md`` §8.4 ``parsing``, §8.6):

* ``record_revision`` stores ``(material_id, content_hash, parser_version) → revision_id`` (ids
  from D09 ``chunk_identity``) and links it to the task that produced it; both are idempotent.
* ``put_chunks`` writes a revision's D08 chunks under ``revision_id-ordinal`` ids with
  insert-or-ignore. Rewriting an existing id with the same text and locators is a no-op; a
  different text hash or locator raises ``ChunkImmutableError`` and never overwrites (PUB-30).
* reads are always constrained by ``course_id``; lookups by material, revision or chunk ids.
* ``delete_task_chunks`` reclaims the chunks of a ``failed``/``cancelled`` task's revisions only
  when no other task still uses the revision and no committed version lists it (V2, §8.6).

Connection-level writers run inside the caller's open write transaction (for example C09
``leased_transaction``), so a rejected batch rolls back as a whole. Chunk text never appears in
``repr`` or error messages.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Iterable, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator

from app.repositories.sqlite import connect
from app.services.chunk_identity import (
    ChunkIdentityError,
    derive_chunk_id,
    revision_id_for,
    text_sha256,
)
from app.services.chunking import ChunkSource, SemanticChunk
from app.services.parsers.models import RevisionKey, SourceLocator

__all__ = [
    "ChunkCleanupResult",
    "ChunkDeleteRefused",
    "ChunkImmutableError",
    "ChunkScopeError",
    "ChunkStoreError",
    "ChunkWriteResult",
    "CommittedRevisions",
    "RevisionRecord",
    "StoredChunk",
    "delete_task_chunks",
    "get_chunk",
    "get_chunks",
    "get_revision",
    "list_chunks",
    "list_material_revisions",
    "list_task_revisions",
    "persist_revision_chunks",
    "put_chunks",
    "record_revision",
]

#: Stages whose source chunks may be reclaimed (§8.6).
RECLAIMABLE_STAGES = frozenset({"failed", "cancelled"})

#: ``(connection, course_id) → revision ids listed by any committed version of that course``.
#: Called inside the deletion transaction. The version table belongs to G02 (see handoff).
CommittedRevisions = Callable[[sqlite3.Connection, str], Iterable[str]]


class ChunkStoreError(RuntimeError):
    """Base class for refused chunk-store operations."""


class ChunkScopeError(ChunkStoreError):
    """The task, material or revision does not belong to the given course (or does not exist)."""


class ChunkImmutableError(ChunkStoreError):
    """An existing chunk id was written with a different text hash or locator (PUB-30)."""


class ChunkDeleteRefused(ChunkStoreError):
    """Only ``failed`` or ``cancelled`` tasks have reclaimable source chunks (§8.6)."""


@dataclass(frozen=True)
class RevisionRecord:
    revision_id: str
    course_id: str
    material_id: str
    content_hash: str
    parser_version: str
    created_at: str


@dataclass(frozen=True)
class StoredChunk:
    chunk_id: str
    course_id: str
    material_id: str
    revision_id: str
    ordinal: int
    text: str = field(repr=False)
    text_sha256: str
    section_titles: tuple[str, ...]
    sources: tuple[ChunkSource, ...]


@dataclass(frozen=True)
class ChunkWriteResult:
    """Chunk ids newly inserted and ids that already held identical content, in ordinal order."""

    inserted: tuple[str, ...]
    existing: tuple[str, ...]


@dataclass(frozen=True)
class ChunkCleanupResult:
    deleted_revisions: tuple[str, ...]
    kept_revisions: tuple[str, ...]
    deleted_chunks: int


_REVISION_COLUMNS = "revision_id, course_id, material_id, content_hash, parser_version, created_at"
_CHUNK_COLUMNS = (
    "chunk_id, course_id, material_id, revision_id, ordinal, text, text_sha256, section_titles, sources"
)


def _non_empty(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _require_transaction(database: sqlite3.Connection, operation: str) -> None:
    if not database.in_transaction:
        raise RuntimeError(f"{operation} must run inside the caller's write transaction")


@contextmanager
def _immediate(sqlite_url: str) -> Iterator[sqlite3.Connection]:
    with connect(sqlite_url) as database:
        database.execute("BEGIN IMMEDIATE")
        try:
            yield database
            database.execute("COMMIT")
        except BaseException:
            if database.in_transaction:
                database.execute("ROLLBACK")
            raise


# ---------------------------------------------------------------- (de)serialisation


def _canon_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _locator_json(locator: SourceLocator) -> dict[str, object]:
    data: dict[str, object] = {"section_titles": list(locator.section_titles)}
    for name in ("page", "paragraph", "line_start", "line_end"):
        value = getattr(locator, name)
        if value is not None:
            data[name] = value
    return data


def _sources_json(sources: Sequence[ChunkSource]) -> str:
    return _canon_json(
        [
            {
                "block_ordinal": source.block_ordinal,
                "start": source.start,
                "end": source.end,
                "locator": _locator_json(source.locator),
            }
            for source in sources
        ]
    )


def _sources_from_json(raw: str) -> tuple[ChunkSource, ...]:
    result: list[ChunkSource] = []
    for item in json.loads(raw):
        locator = item["locator"]
        result.append(
            ChunkSource(
                block_ordinal=item["block_ordinal"],
                start=item["start"],
                end=item["end"],
                locator=SourceLocator(
                    page=locator.get("page"),
                    section_titles=tuple(locator.get("section_titles", ())),
                    paragraph=locator.get("paragraph"),
                    line_start=locator.get("line_start"),
                    line_end=locator.get("line_end"),
                ),
            )
        )
    return tuple(result)


def _revision_from_row(row: tuple[object, ...]) -> RevisionRecord:
    return RevisionRecord(*row)  # type: ignore[arg-type]


def _chunk_from_row(row: tuple[object, ...]) -> StoredChunk:
    return StoredChunk(
        chunk_id=row[0],  # type: ignore[arg-type]
        course_id=row[1],  # type: ignore[arg-type]
        material_id=row[2],  # type: ignore[arg-type]
        revision_id=row[3],  # type: ignore[arg-type]
        ordinal=row[4],  # type: ignore[arg-type]
        text=row[5],  # type: ignore[arg-type]
        text_sha256=row[6],  # type: ignore[arg-type]
        section_titles=tuple(json.loads(row[7])),  # type: ignore[arg-type]
        sources=_sources_from_json(row[8]),  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------- writes


def _revision_in_course(
    database: sqlite3.Connection, course_id: str, revision_id: str
) -> RevisionRecord | None:
    row = database.execute(
        f"SELECT {_REVISION_COLUMNS} FROM material_revisions WHERE revision_id = ? AND course_id = ?",
        (revision_id, course_id),
    ).fetchone()
    return _revision_from_row(row) if row else None


def record_revision(
    database: sqlite3.Connection, *, course_id: str, task_id: str, key: RevisionKey
) -> RevisionRecord:
    """Record ``key``'s revision and link it to ``task_id``; idempotent.

    The task must belong to ``course_id`` and process ``key.document_id``. ``key.parser_version``
    must be the ADR-018 composite version (D09 raises ``ChunkIdentityError`` otherwise).
    """
    _require_transaction(database, "record_revision")
    _non_empty("course_id", course_id)
    _non_empty("task_id", task_id)
    if not isinstance(key, RevisionKey):
        raise TypeError(f"key must be a RevisionKey, got {type(key).__name__}")
    revision_id = revision_id_for(key)

    task = database.execute(
        "SELECT 1 FROM processing_tasks WHERE id = ? AND course_id = ? AND document_id = ?",
        (task_id, course_id, key.document_id),
    ).fetchone()
    if task is None:
        raise ChunkScopeError(
            f"task {task_id} does not process material {key.document_id} in course {course_id}"
        )

    database.execute(
        """INSERT INTO material_revisions
           (revision_id, course_id, material_id, content_hash, parser_version)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(revision_id) DO NOTHING""",
        (revision_id, course_id, key.document_id, key.content_hash, key.parser_version),
    )
    record = _revision_in_course(database, course_id, revision_id)
    if record is None or (record.material_id, record.content_hash, record.parser_version) != (
        key.document_id,
        key.content_hash,
        key.parser_version,
    ):
        raise ChunkScopeError(f"revision {revision_id} is recorded for a different course or key")
    database.execute(
        """INSERT INTO task_revisions (task_id, revision_id, course_id, material_id)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(task_id, revision_id) DO NOTHING""",
        (task_id, revision_id, course_id, key.document_id),
    )
    return record


def put_chunks(
    database: sqlite3.Connection,
    *,
    course_id: str,
    revision_id: str,
    chunks: Sequence[SemanticChunk],
) -> ChunkWriteResult:
    """Write a recorded revision's D08 chunks under their D09 ids (insert-or-ignore).

    Ordinals must run from 0 without gaps. An id that already exists must hold the same text
    hash and locators, otherwise ``ChunkImmutableError`` is raised and the caller's
    transaction must be rolled back.
    """
    _require_transaction(database, "put_chunks")
    _non_empty("course_id", course_id)
    revision = _revision_in_course(database, course_id, revision_id)
    if revision is None:
        raise ChunkScopeError(f"revision {revision_id} is not recorded in course {course_id}")

    ordered = list(chunks)
    rows: list[tuple[str, int, str, str, str, str]] = []
    for expected, chunk in enumerate(ordered):
        if not isinstance(chunk, SemanticChunk):
            raise TypeError(f"chunks must only contain SemanticChunk, got {type(chunk).__name__}")
        if type(chunk.ordinal) is not int or chunk.ordinal != expected:
            raise ChunkIdentityError(f"chunk ordinal must run from 0 without gaps: position {expected} got {chunk.ordinal!r}")
        if not isinstance(chunk.text, str) or not chunk.text:
            raise ChunkIdentityError(f"chunk {expected} has empty text")
        if not chunk.sources or not all(isinstance(s, ChunkSource) for s in chunk.sources):
            raise ChunkIdentityError(f"chunk {expected} has no valid source")
        rows.append(
            (
                derive_chunk_id(revision_id, expected),
                expected,
                chunk.text,
                text_sha256(chunk.text),
                _canon_json(list(chunk.section_titles)),
                _sources_json(chunk.sources),
            )
        )

    inserted: list[str] = []
    existing: list[str] = []
    for chunk_id, ordinal, text, digest, titles, sources in rows:
        created = database.execute(
            """INSERT INTO chunks
               (chunk_id, revision_id, course_id, material_id, ordinal, text, text_sha256,
                section_titles, sources)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(chunk_id) DO NOTHING
               RETURNING chunk_id""",
            (chunk_id, revision_id, course_id, revision.material_id, ordinal, text, digest, titles, sources),
        ).fetchone()
        if created is not None:
            inserted.append(chunk_id)
            continue
        stored = database.execute(
            "SELECT course_id, text_sha256, section_titles, sources FROM chunks WHERE chunk_id = ?",
            (chunk_id,),
        ).fetchone()
        if stored is None or stored[0] != course_id:
            raise ChunkScopeError(f"chunk {chunk_id} belongs to a different course")
        if stored[1] != digest:
            raise ChunkImmutableError(f"chunk {chunk_id} already exists with a different text hash")
        if (stored[2], stored[3]) != (titles, sources):
            raise ChunkImmutableError(f"chunk {chunk_id} already exists with different locators")
        existing.append(chunk_id)
    return ChunkWriteResult(inserted=tuple(inserted), existing=tuple(existing))


def persist_revision_chunks(
    sqlite_url: str,
    *,
    course_id: str,
    task_id: str,
    key: RevisionKey,
    chunks: Sequence[SemanticChunk],
) -> tuple[RevisionRecord, ChunkWriteResult]:
    """``record_revision`` + ``put_chunks`` in one ``BEGIN IMMEDIATE`` transaction.

    Workers holding a lease use the connection-level functions inside C09
    ``leased_transaction`` instead, so the write is fenced by the lease token.
    """
    with _immediate(sqlite_url) as database:
        revision = record_revision(database, course_id=course_id, task_id=task_id, key=key)
        written = put_chunks(database, course_id=course_id, revision_id=revision.revision_id, chunks=chunks)
    return revision, written


# ---------------------------------------------------------------- reads (course-scoped)


def get_revision(sqlite_url: str, *, course_id: str, revision_id: str) -> RevisionRecord | None:
    with connect(sqlite_url) as database:
        return _revision_in_course(database, course_id, revision_id)


def list_material_revisions(sqlite_url: str, *, course_id: str, material_id: str) -> tuple[RevisionRecord, ...]:
    with connect(sqlite_url) as database:
        rows = database.execute(
            f"""SELECT {_REVISION_COLUMNS} FROM material_revisions
                WHERE course_id = ? AND material_id = ? ORDER BY created_at, revision_id""",
            (course_id, material_id),
        ).fetchall()
    return tuple(_revision_from_row(row) for row in rows)


def list_task_revisions(sqlite_url: str, *, course_id: str, task_id: str) -> tuple[RevisionRecord, ...]:
    with connect(sqlite_url) as database:
        rows = database.execute(
            f"""SELECT {', '.join('r.' + c.strip() for c in _REVISION_COLUMNS.split(','))}
                FROM task_revisions t JOIN material_revisions r ON r.revision_id = t.revision_id
                WHERE t.course_id = ? AND r.course_id = ? AND t.task_id = ?
                ORDER BY r.created_at, r.revision_id""",
            (course_id, course_id, task_id),
        ).fetchall()
    return tuple(_revision_from_row(row) for row in rows)


def get_chunk(sqlite_url: str, *, course_id: str, chunk_id: str) -> StoredChunk | None:
    with connect(sqlite_url) as database:
        row = database.execute(
            f"SELECT {_CHUNK_COLUMNS} FROM chunks WHERE chunk_id = ? AND course_id = ?",
            (chunk_id, course_id),
        ).fetchone()
    return _chunk_from_row(row) if row else None


def get_chunks(sqlite_url: str, *, course_id: str, chunk_ids: Iterable[str]) -> tuple[StoredChunk, ...]:
    """Chunks of ``course_id`` in first-requested order; unknown or foreign ids are omitted."""
    wanted = list(dict.fromkeys(chunk_ids))
    if not wanted:
        return ()
    found: dict[str, StoredChunk] = {}
    with connect(sqlite_url) as database:
        for start in range(0, len(wanted), 500):
            batch = wanted[start:start + 500]
            placeholders = ", ".join("?" for _ in batch)
            for row in database.execute(
                f"SELECT {_CHUNK_COLUMNS} FROM chunks WHERE course_id = ? AND chunk_id IN ({placeholders})",
                (course_id, *batch),
            ):
                found[row[0]] = _chunk_from_row(row)
    return tuple(found[chunk_id] for chunk_id in wanted if chunk_id in found)


def list_chunks(
    sqlite_url: str,
    *,
    course_id: str,
    material_id: str | None = None,
    revision_id: str | None = None,
) -> tuple[StoredChunk, ...]:
    """Chunks of a material and/or revision within ``course_id``, by revision then ordinal."""
    _non_empty("course_id", course_id)
    if material_id is None and revision_id is None:
        raise ValueError("list_chunks needs material_id or revision_id")
    clauses, params = ["course_id = ?"], [course_id]
    if material_id is not None:
        clauses.append("material_id = ?")
        params.append(material_id)
    if revision_id is not None:
        clauses.append("revision_id = ?")
        params.append(revision_id)
    with connect(sqlite_url) as database:
        rows = database.execute(
            f"SELECT {_CHUNK_COLUMNS} FROM chunks WHERE {' AND '.join(clauses)} ORDER BY revision_id, ordinal",
            params,
        ).fetchall()
    return tuple(_chunk_from_row(row) for row in rows)


# ---------------------------------------------------------------- deletion protection


def delete_task_chunks(
    sqlite_url: str,
    *,
    course_id: str,
    task_id: str,
    committed_revision_ids: CommittedRevisions,
) -> ChunkCleanupResult:
    """Reclaim the source chunks of a ``failed``/``cancelled`` task (§8.6 with the V2 protection).

    A revision of the task is kept untouched when any other task that is not ``failed`` or
    ``cancelled`` is linked to it (``awaiting_review``/``completed`` per V2; queued or running
    tasks too, see handoff), or when ``committed_revision_ids`` lists it. Otherwise its chunks
    and this task's link are deleted, and the revision row once no task links it any more.
    Runs in one ``BEGIN IMMEDIATE`` transaction; any error deletes nothing. Idempotent.
    """
    _non_empty("course_id", course_id)
    _non_empty("task_id", task_id)
    with _immediate(sqlite_url) as database:
        row = database.execute(
            "SELECT stage FROM processing_tasks WHERE id = ? AND course_id = ?", (task_id, course_id)
        ).fetchone()
        if row is None:
            raise ChunkScopeError(f"task {task_id} is not in course {course_id}")
        if row[0] not in RECLAIMABLE_STAGES:
            raise ChunkDeleteRefused(f"task {task_id} is {row[0]}; only failed or cancelled tasks are reclaimed")

        revision_ids = [
            r[0]
            for r in database.execute(
                "SELECT revision_id FROM task_revisions WHERE task_id = ? AND course_id = ? ORDER BY revision_id",
                (task_id, course_id),
            )
        ]
        if not revision_ids:
            return ChunkCleanupResult(deleted_revisions=(), kept_revisions=(), deleted_chunks=0)
        committed = set(committed_revision_ids(database, course_id))

        deleted: list[str] = []
        kept: list[str] = []
        chunk_count = 0
        for revision_id in revision_ids:
            in_use = database.execute(
                """SELECT 1 FROM task_revisions t JOIN processing_tasks p ON p.id = t.task_id
                   WHERE t.revision_id = ? AND t.task_id <> ? AND p.stage NOT IN ('failed', 'cancelled')
                   LIMIT 1""",
                (revision_id, task_id),
            ).fetchone()
            if in_use is not None or revision_id in committed:
                kept.append(revision_id)
                continue
            chunk_count += database.execute(
                "DELETE FROM chunks WHERE revision_id = ? AND course_id = ?", (revision_id, course_id)
            ).rowcount
            database.execute(
                "DELETE FROM task_revisions WHERE task_id = ? AND revision_id = ?", (task_id, revision_id)
            )
            database.execute(
                """DELETE FROM material_revisions WHERE revision_id = ? AND course_id = ?
                   AND NOT EXISTS (SELECT 1 FROM task_revisions WHERE revision_id = ?)""",
                (revision_id, course_id, revision_id),
            )
            deleted.append(revision_id)
    return ChunkCleanupResult(
        deleted_revisions=tuple(deleted), kept_revisions=tuple(kept), deleted_chunks=chunk_count
    )
