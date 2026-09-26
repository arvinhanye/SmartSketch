"""I01: original student progress. Version lineage is projected by learning services.

All writes use the same SQLite sequence as committed graph versions. A published
node set must come from the bound version; the pointer is checked again under a
SQLite write lock so an outdated binding cannot silently commit.
"""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Collection, Sequence
import logging
import sqlite3
import uuid

from app.repositories.sqlite import connect
from app.repositories.versions import immediate, next_commit_seq
from app.services.versions.snapshot import SnapshotFormatError, digest_of, load_snapshot

_STATUSES = frozenset({'unknown', 'learning', 'mastered'})
_LOG = logging.getLogger(__name__)


class InvalidProgressTarget(ValueError):
    """One or more targets are not in the bound published graph."""


class StalePublishedVersion(RuntimeError):
    """The course publish pointer moved before the write transaction."""


@dataclass(frozen=True)
class ProgressUpdate:
    kp_id: str
    status: str
    force: bool = False


@dataclass(frozen=True)
class ProgressRecord:
    user_id: str
    course_id: str
    kp_id: str
    status: str
    updated_at: str
    write_seq: int


_COLUMNS = 'user_id, course_id, kp_id, status, updated_at, write_seq'


def read_progress(sqlite_url: str, *, user_id: str, course_id: str) -> tuple[ProgressRecord, ...]:
    """Read every original row for one student/course, including dormant nodes."""
    with connect(sqlite_url) as database:
        rows = database.execute(
            f'SELECT {_COLUMNS} FROM learning_progress WHERE user_id = ? AND course_id = ? ORDER BY kp_id',
            (user_id, course_id),
        ).fetchall()
    return tuple(ProgressRecord(*row) for row in rows)


def read_committed_progress(sqlite_url: str, *, user_id: str, course_id: str) -> tuple[ProgressRecord, ...]:
    """Ignore corrupt IDs while retaining nodes absent from the current version.

    Membership is the union of all committed versions of this course, never
    just the currently published graph. The rows and version history share a
    SQLite read snapshot, so a concurrent publish cannot mix the two.
    """
    with connect(sqlite_url) as database:
        database.execute('BEGIN')
        rows = database.execute(
            f'SELECT {_COLUMNS} FROM learning_progress WHERE user_id=? AND course_id=? ORDER BY kp_id',
            (user_id, course_id),
        ).fetchall()
        versions = database.execute(
            "SELECT snapshot_json, digest FROM graph_versions WHERE course_id=? AND state='committed'",
            (course_id,),
        ).fetchall()
        known: set[str] = set()
        for raw, digest in versions:
            if raw is None or digest_of(raw.encode('utf-8')) != digest:
                raise RuntimeError('committed progress history has an invalid snapshot')
            try:
                snapshot = load_snapshot(raw)
            except SnapshotFormatError as exc:
                raise RuntimeError('committed progress history has a malformed snapshot') from exc
            if snapshot.data['course_id'] != course_id:
                raise RuntimeError('committed progress history has a cross-course snapshot')
            known.update(node['kp_id'] for node in snapshot.data['nodes'])
    valid: list[ProgressRecord] = []
    for row in rows:
        if row[2] not in known:
            _LOG.warning('Ignored progress ID absent from committed course history: kp_id=%s diagnostic_id=%s',
                         row[2], uuid.uuid4().hex)
            continue
        valid.append(ProgressRecord(*row))
    return tuple(valid)


def write_progress(
    sqlite_url: str, *, user_id: str, course_id: str, version_id: str,
    published_kp_ids: Collection[str], updates: Sequence[ProgressUpdate],
) -> tuple[ProgressRecord, ...]:
    """Write a batch in its own transaction when no caller transaction is needed."""
    with immediate(sqlite_url) as database:
        return write_progress_in_transaction(
            database, user_id=user_id, course_id=course_id, version_id=version_id,
            published_kp_ids=published_kp_ids, updates=updates,
        )


def write_progress_in_transaction(
    database: sqlite3.Connection, *, user_id: str, course_id: str, version_id: str,
    published_kp_ids: Collection[str], updates: Sequence[ProgressUpdate],
) -> tuple[ProgressRecord, ...]:
    """Join the caller's write transaction for version binding and progress writes.

    ``force`` lets I02 record a same-status explicit write that covers inherited
    sources. Without it, same-status writes are idempotent. The caller owns
    authenticated identity, graph membership, and the lineage decision.
    """
    if not database.in_transaction:
        raise RuntimeError('progress writes require a caller transaction')
    if not updates:
        raise ValueError('progress updates must not be empty')
    seen: set[str] = set()
    allowed = set(published_kp_ids)
    for update in updates:
        if not isinstance(update.kp_id, str) or not update.kp_id:
            raise ValueError('kp_id must be a nonempty string')
        if update.status not in _STATUSES:
            raise ValueError('invalid mastery status')
        if update.kp_id in seen:
            raise ValueError('duplicate kp_id')
        seen.add(update.kp_id)
    if not seen <= allowed:
        raise InvalidProgressTarget('target is not in the published version')

    pointer = database.execute('SELECT published_version_id FROM courses WHERE id = ?', (course_id,)).fetchone()
    if pointer is None or pointer[0] != version_id:
        raise StalePublishedVersion('published version changed')
    result: list[ProgressRecord] = []
    for update in updates:
        row = database.execute(
            f'SELECT {_COLUMNS} FROM learning_progress WHERE user_id=? AND course_id=? AND kp_id=?',
            (user_id, course_id, update.kp_id),
        ).fetchone()
        if row is not None and row[3] == update.status and not update.force:
            result.append(ProgressRecord(*row))
            continue
        sequence = next_commit_seq(database)
        database.execute(
            """INSERT INTO learning_progress(user_id, course_id, kp_id, status, updated_at, write_seq)
               VALUES (?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'), ?)
               ON CONFLICT(user_id, course_id, kp_id) DO UPDATE SET
                 status=excluded.status, updated_at=excluded.updated_at, write_seq=excluded.write_seq""",
            (user_id, course_id, update.kp_id, update.status, sequence),
        )
        saved = database.execute(
            f'SELECT {_COLUMNS} FROM learning_progress WHERE user_id=? AND course_id=? AND kp_id=?',
            (user_id, course_id, update.kp_id),
        ).fetchone()
        result.append(ProgressRecord(*saved))
    return tuple(result)
