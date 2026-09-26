#!/usr/bin/env python3
"""F14 offline re-vectorisation: move every stored vector to the configured embedding space.

Implements specs/teacher-review-publish.md V12 (steps 1-7) through the F03 migration context
(PUB-39). The target space is the one in the environment (``EMBEDDING_MODE`` /
``EMBEDDING_MODEL`` / ``EMBEDDING_DIMENSIONS``); the source space is the one SQLite records.

1. Stop API and worker first. The command refuses while any task lease or course write lock is
   live, or while any publish/rollback attempt is still ``preparing``/``materialized`` (expired
   or not: run the G05 compensation first). It backs SQLite up (``VACUUM INTO`` +
   ``integrity_check``) and requires ``--neo4j-backup-confirmed`` for the K10 Neo4j backup.
2. Creates the target space's vector indexes next to the old ones.
3. Enumerates the Neo4j stock (not task states): every ``Chunk``, every draft
   ``KnowledgePoint`` and every copy of a ``committed`` version, and writes target-space vectors
   through the migration context. Identical texts are embedded once. On a re-run, chunks and
   committed copies that already hold a valid target vector are reused (their text is
   immutable); draft knowledge points are always recomputed. Calls are logged in
   ``model_calls`` with purpose ``embedding`` (never budget-checked).
4. Re-reads the stock: no node of the three classes may lack a target vector of the target
   dimension, the stock must not have changed, and each committed version must hold exactly
   ``node_count`` copies.
5. One SQLite transaction switches the recorded space and every committed version's
   ``embedding_space``. This is the only commit point.
6. Drops every other space's vector indexes and properties. A failure here is reported (exit 3)
   and finished by re-running the command with the same configuration.
7. Any failure before step 5 leaves the old space recorded; the old configuration still starts.

Run from the repository root with the new EMBEDDING_* and the usual SQLITE_URL / NEO4J_* set::

    python3 scripts/reembed.py --neo4j-backup-confirmed

Exit codes: 0 done, 1 failed before the switch (old space kept), 2 refused (not stopped / no
backup confirmation), 3 switched but old-space cleanup unfinished (re-run to finish).
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
import time
import uuid
from collections import defaultdict
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "backend"))

from app.repositories.graph_migrations import (  # noqa: E402
    GraphMigrationError, GraphVectorWriter, VectorSpaceError, _dimensions, sqlite_current_space, vector_property,
)
from app.repositories.model_calls import EMBEDDING_PURPOSE, CallOutcome, CallRecord, SqliteCallStore  # noqa: E402
from app.repositories.sqlite import connect, database_path  # noqa: E402
from app.services.ai.client import EmbeddingClient, EmbeddingRequest, EmbeddingResult, ModelCallError  # noqa: E402
from app.services.ai.embeddings import EmbeddingAdapter, EmbeddingBatchError, EmbeddingCache  # noqa: E402
from app.services.versions.materialize import node_embedding_text  # noqa: E402

DRAFT = "draft"
REMOVE_BATCH = 1000
_STALE_INDEX = re.compile(r"^(?:chunk|kp)_embedding_([0-9a-f]{16})$")
_STALE_PROPERTY = re.compile(r"^embedding_[0-9a-f]{16}$")

ROLLBACK_STEPS = """回滚步骤（specs/teacher-review-publish.md V12）：
- 第 5 步（SQLite 切换）之前失败：记录的空间仍是旧空间。改回旧配置（EMBEDDING_*）即可照常启动；
  如需清掉写了一半的新空间属性与索引，用旧配置再运行本命令（记录空间与配置相同时只做清理）。
- 第 5 步之后要退回旧空间：优先停 API 与 worker，用本次命令打印的 SQLite 备份
  （backups/*-before-reembed.sqlite）替换数据库，并按 K10 流程恢复运行前的 Neo4j 备份；
  或者把配置改回旧空间，再完整运行一次本命令（重新计算旧空间的向量）。
- 第 6 步（删除旧空间）失败不影响新空间：用同一配置重新运行本命令即可完成清理。"""


class ReembedError(RuntimeError):
    """The command stopped; unless stated otherwise the old space is still recorded."""


class OfflineCheckError(ReembedError):
    """Step 1 refused: the system is not stopped, or a backup is missing."""


class VerificationFailed(ReembedError):
    """The Neo4j stock does not match what the switch requires."""


@dataclass(frozen=True)
class Report:
    action: str  # "switched" or "cleanup"
    source_space: str
    target_space: str
    chunks: int = 0
    draft_kps: int = 0
    committed_kps: int = 0
    versions: int = 0
    orphans: int = 0
    embedded_texts: int = 0
    reused: int = 0
    backup: Path | None = None
    cleanup_error: str | None = None


@dataclass(frozen=True)
class _Item:
    kind: str  # "Chunk" or "KnowledgePoint"
    course_id: str
    version_id: str | None
    entity_id: str
    text: str
    has_target: bool  # already holds a vector of the target dimension

    @property
    def reusable(self) -> bool:
        # Chunk text and committed copies are immutable; a draft's text may have changed.
        return self.has_target and self.version_id != DRAFT


def target_space(settings: Any) -> str:
    """Same derivation as E07 ``EmbeddingAdapter.space`` and B06's startup check."""
    if settings.EMBEDDING_MODE == "fake":
        space = f"fake/{settings.EMBEDDING_DIMENSIONS}"
    else:
        space = f"real/{settings.EMBEDDING_MODEL}/{settings.EMBEDDING_DIMENSIONS}"
    try:
        _dimensions(space)
    except VectorSpaceError:
        raise ReembedError(f"invalid target embedding space {space!r}") from None
    return space


# ---------------------------------------------------------------- step 1


def check_offline(sqlite_url: str) -> None:
    """Refuse while anything could still write (A06 §8.7)."""
    with connect(sqlite_url) as database:
        if database.execute(
            "SELECT 1 FROM processing_tasks WHERE lease_expires_at >= unixepoch() LIMIT 1"
        ).fetchone():
            raise OfflineCheckError("active task lease: stop API and worker first")
        if database.execute("SELECT 1 FROM course_locks WHERE expires_at >= unixepoch() LIMIT 1").fetchone():
            raise OfflineCheckError("active course write lock: stop API and worker first")
        if database.execute(
            "SELECT 1 FROM graph_versions WHERE state IN ('preparing', 'materialized') LIMIT 1"
        ).fetchone():
            raise OfflineCheckError(
                "unfinished publish/rollback attempt: stop API and worker and run the G05 compensation first"
            )


def _committed_versions(sqlite_url: str, source: str) -> dict[tuple[str, str], int]:
    with connect(sqlite_url) as database:
        rows = database.execute(
            "SELECT course_id, version_id, node_count, embedding_space FROM graph_versions WHERE state = 'committed'"
        ).fetchall()
    broken = [row[1] for row in rows if row[3] != source]
    if broken:
        raise ReembedError(
            f"{len(broken)} committed version(s) have an embedding_space other than the recorded {source!r}; "
            "the V12 invariant is broken, repair before re-vectorising"
        )
    return {(course, version): count for course, version, count, _ in rows}


def backup_sqlite(sqlite_url: str) -> Path:
    path = database_path(sqlite_url)
    directory = path.parent / "backups"
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup = directory / f"{stamp}-before-reembed.sqlite"
    with connect(sqlite_url) as database:
        database.execute("VACUUM INTO ?", (str(backup),))
    with closing(sqlite3.connect(backup)) as copy:
        ok = copy.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    if not ok:
        backup.unlink(missing_ok=True)
        raise OfflineCheckError("SQLite backup failed integrity_check; nothing was changed")
    return backup


# ---------------------------------------------------------------- Neo4j access


def _query(driver: Any, query: str, params: dict | None = None) -> list:
    try:
        return list(driver.execute_query(query, parameters_=params or {}, routing_="w", database_="neo4j").records)
    except Exception:
        raise GraphMigrationError("Neo4j query failed during re-vectorisation") from None


def _inventory(driver: Any, space: str) -> tuple[list[dict], list[dict]]:
    params = {"prop": vector_property(space), "dims": _dimensions(space)}
    prop = params["prop"]
    ok = f"n.{prop} IS NOT NULL AND size(n.{prop}) = $dims AS ok"
    chunks = _query(driver, f"MATCH (n:Chunk) RETURN n.course_id AS course_id, n.chunk_id AS id, {ok}", params)
    kps = _query(driver, "MATCH (n:KnowledgePoint) RETURN n.course_id AS course_id, n.version_id AS version_id, "
                         f"n.kp_id AS id, n.name AS name, n.definition AS definition, {ok}", params)
    return [dict(r) for r in chunks], [dict(r) for r in kps]


def _chunk_texts(sqlite_url: str, keys: set[tuple[str, str]]) -> dict[tuple[str, str], str]:
    by_course: dict[str, list[str]] = defaultdict(list)
    for course, chunk in keys:
        by_course[course].append(chunk)
    found: dict[tuple[str, str], str] = {}
    with connect(sqlite_url) as database:
        for course, chunk_ids in by_course.items():
            for start in range(0, len(chunk_ids), 500):
                part = chunk_ids[start:start + 500]
                marks = ",".join("?" * len(part))
                for chunk_id, text in database.execute(
                    f"SELECT chunk_id, text FROM chunks WHERE course_id = ? AND chunk_id IN ({marks})", (course, *part)
                ):
                    found[(course, chunk_id)] = text
    return found


@dataclass
class _Stock:
    items: list[_Item]
    chunks: int
    drafts: int
    committed: int
    orphans: int
    signature: tuple


def _classify(driver: Any, sqlite_url: str, space: str, versions: dict[tuple[str, str], int]) -> _Stock:
    chunks, kps = _inventory(driver, space)
    items: list[_Item] = []
    texts = _chunk_texts(sqlite_url, {(r["course_id"], r["id"]) for r in chunks})
    missing = [r for r in chunks if (r["course_id"], r["id"]) not in texts]
    if missing:
        raise VerificationFailed(f"{len(missing)} chunk node(s) have no stored text in SQLite; repair before re-running")
    for r in chunks:
        items.append(_Item("Chunk", r["course_id"], None, r["id"], texts[(r["course_id"], r["id"])], r["ok"]))
    drafts = committed = orphans = 0
    per_version: dict[tuple[str, str], int] = defaultdict(int)
    for r in kps:
        key = (r["course_id"], r["version_id"])
        if r["version_id"] == DRAFT:
            drafts += 1
        elif key in versions:
            committed += 1
            per_version[key] += 1
        else:
            orphans += 1  # copy of an uncommitted attempt: not a version, left to G05
            continue
        if not isinstance(r["name"], str) or not isinstance(r["definition"], str):
            raise VerificationFailed(f"knowledge point {r['id']!r} in {key} has no name/definition")
        items.append(_Item("KnowledgePoint", r["course_id"], r["version_id"], r["id"],
                           node_embedding_text(r), r["ok"]))
    wrong = sorted(f"{k[1]}={per_version.get(k, 0)}/{n}" for k, n in versions.items() if per_version.get(k, 0) != n)
    if wrong:
        raise VerificationFailed(f"committed version copy counts differ from node_count: {', '.join(wrong[:5])}")
    signature = (len(chunks), drafts, committed,
                 tuple(sorted((i.kind, i.course_id, i.version_id or "", i.entity_id) for i in items)))
    return _Stock(items, len(chunks), drafts, committed, orphans, signature)


# ---------------------------------------------------------------- model call log


class _RecordingClient:
    """Logs each physical embedding call in ``model_calls`` against the course being migrated."""

    def __init__(self, inner: EmbeddingClient, store: SqliteCallStore) -> None:
        self._inner = inner
        self._store = store
        self.course_id = ""

    def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        call_id = uuid.uuid4().hex
        self._store.prewrite(CallRecord(
            call_id=call_id, course_id=self.course_id, task_id=None, chunk_id=None, request_id=None,
            purpose=EMBEDDING_PURPOSE, task_attempt=None, chunk_attempt=None, call_seq=None,
            provider_role="primary", is_repair=False, model_requested=request.model,
            input_tokens_est=sum(len(text) for text in request.texts), max_output_tokens=0,
        ), task_budget=0, daily_budget=0)
        started = time.monotonic()
        try:
            result = self._inner.embed(request)
        except ModelCallError as exc:
            usage = exc.usage
            self._store.finish(CallOutcome(
                call_id, "error", None, usage and usage.input_tokens, usage and usage.output_tokens,
                int((time.monotonic() - started) * 1000), exc.error_class.value, exc.rejected_before_generation))
            raise
        except Exception:
            self._store.finish(CallOutcome(call_id, "error", None, None, None,
                                           int((time.monotonic() - started) * 1000), "unknown", False))
            raise
        usage = result.usage
        self._store.finish(CallOutcome(
            call_id, "ok", result.model_responded, usage and usage.input_tokens, usage and usage.output_tokens,
            int((time.monotonic() - started) * 1000), None, False))
        return result


# ---------------------------------------------------------------- step 6


def cleanup_other_spaces(driver: Any, keep: str) -> None:
    """Drop every vector index and property that does not belong to ``keep``."""
    keep_prop = vector_property(keep)
    keep_suffix = keep_prop.removeprefix("embedding_")
    for record in _query(driver, "SHOW INDEXES YIELD name RETURN name"):
        match = _STALE_INDEX.fullmatch(str(record["name"]))
        if match and match.group(1) != keep_suffix:
            _query(driver, f"DROP INDEX {record['name']} IF EXISTS")
    stale = [
        str(r["key"]) for r in _query(
            driver,
            "MATCH (n) WHERE n:Chunk OR n:KnowledgePoint UNWIND keys(n) AS key "
            "WITH DISTINCT key WHERE key STARTS WITH 'embedding_' RETURN key",
        )
    ]
    for prop in stale:
        if prop == keep_prop or not _STALE_PROPERTY.fullmatch(prop):
            continue
        for label in ("Chunk", "KnowledgePoint"):
            while True:
                [row] = _query(driver, f"MATCH (n:{label}) WHERE n.{prop} IS NOT NULL WITH n LIMIT $limit "
                                       f"REMOVE n.{prop} RETURN count(n) AS removed", {"limit": REMOVE_BATCH})
                if row["removed"] == 0:
                    break


# ---------------------------------------------------------------- the command


def run(*, sqlite_url: str, driver: Any, settings: Any, client: EmbeddingClient,
        neo4j_backup_confirmed: bool, cache: EmbeddingCache | None = None) -> Report:
    target = target_space(settings)
    try:
        source = sqlite_current_space(sqlite_url)()
    except VectorSpaceError as exc:
        raise ReembedError(f"recorded embedding space unavailable: {exc}") from None
    check_offline(sqlite_url)

    if source == target:
        # Nothing to switch; finish an interrupted step 6, or remove a half-written other space.
        cleanup_other_spaces(driver, source)
        return Report("cleanup", source, target)

    if not neo4j_backup_confirmed:
        raise OfflineCheckError("back Neo4j up (K10) first, then pass --neo4j-backup-confirmed")
    versions = _committed_versions(sqlite_url, source)
    backup = backup_sqlite(sqlite_url)

    cache = cache if cache is not None else EmbeddingCache(max_entries=1 << 20)
    recorder = _RecordingClient(client, SqliteCallStore(sqlite_url))
    adapter = EmbeddingAdapter(settings, recorder, cache=cache)
    writer = GraphVectorWriter(driver, sqlite_current_space(sqlite_url))
    with writer.migration(target, prerequisite_check=lambda: check_offline(sqlite_url)) as context:
        writer.ensure_vector_indexes(target)                                      # step 2
        stock = _classify(driver, sqlite_url, target, versions)                  # step 3
        todo = [item for item in stock.items if not item.reusable]
        reused = len(stock.items) - len(todo)
        by_course: dict[str, list[_Item]] = defaultdict(list)
        for item in todo:
            by_course[item.course_id].append(item)
        seen: set[str] = set()
        step = max(1, int(settings.EMBEDDING_BATCH_SIZE))
        for course_id, items in sorted(by_course.items()):
            recorder.course_id = course_id
            # Write after every batch so an interrupted run keeps its progress for the re-run.
            for start in range(0, len(items), step):
                group = items[start:start + step]
                try:
                    vectors = adapter.embed([item.text for item in group])
                except EmbeddingBatchError as exc:
                    raise ReembedError(f"embedding failed for course {course_id}: {exc}; old space kept") from None
                for item, vector in zip(group, vectors, strict=True):
                    seen.add(vector.text_hash)
                    context.write(item.kind, item.course_id, item.version_id, item.entity_id, vector)
        embedded = len(seen)

        after = _classify(driver, sqlite_url, target, versions)                  # step 4
        if after.signature != stock.signature:
            raise VerificationFailed("stock count changed during the run; was something still writing?")
        lacking = sum(not item.has_target for item in after.items)
        if lacking:
            raise VerificationFailed(f"{lacking} target vector(s) missing or of the wrong dimension after step 3")

        _switch(sqlite_url, source, target)                                       # step 5
    cache.clear_space(source)

    cleanup_error = None
    try:
        cleanup_other_spaces(driver, target)                                      # step 6
    except GraphMigrationError as exc:
        cleanup_error = f"{exc}; re-run the command with the same configuration to finish"
    return Report("switched", source, target, stock.chunks, stock.drafts, stock.committed, len(versions),
                  stock.orphans, embedded, reused, backup, cleanup_error)


def _switch(sqlite_url: str, source: str, target: str) -> None:
    model, dims = ("", _dimensions(target)) if target.startswith("fake/") else (target[5:].rsplit("/", 1)[0],
                                                                                 _dimensions(target))
    with connect(sqlite_url) as database:
        database.execute("BEGIN IMMEDIATE")
        try:
            row = database.execute(
                "SELECT model, dimensions, is_fake FROM embedding_space_state WHERE singleton = 1").fetchone()
            recorded = None if row is None else (f"fake/{row[1]}" if row[2] else f"real/{row[0]}/{row[1]}")
            if recorded != source:
                raise ReembedError(f"recorded space changed to {recorded!r} during the run; nothing switched")
            for query, message in (
                ("SELECT 1 FROM processing_tasks WHERE lease_expires_at >= unixepoch() LIMIT 1", "task lease"),
                ("SELECT 1 FROM course_locks WHERE expires_at >= unixepoch() LIMIT 1", "course write lock"),
                ("SELECT 1 FROM graph_versions WHERE state IN ('preparing', 'materialized') LIMIT 1",
                 "publish attempt"),
            ):
                if database.execute(query).fetchone():
                    raise OfflineCheckError(f"{message} appeared during the run; nothing switched")
            database.execute("UPDATE embedding_space_state SET model = ?, dimensions = ?, is_fake = ? "
                             "WHERE singleton = 1", (model, dims, int(target.startswith("fake/"))))
            database.execute("UPDATE graph_versions SET embedding_space = ? WHERE state = 'committed'", (target,))
            database.execute("COMMIT")
        except BaseException:
            if database.in_transaction:
                database.execute("ROLLBACK")
            raise


# ---------------------------------------------------------------- CLI


def _client_from_settings(settings: Any) -> EmbeddingClient:
    if settings.EMBEDDING_MODE == "fake":
        from app.services.ai.fake import FakeEmbeddingClient
        return FakeEmbeddingClient()
    from app.services.ai.compatible import CompatibleEmbeddingClient
    return CompatibleEmbeddingClient(settings.EMBEDDING_BASE_URL, settings.EMBEDDING_API_KEY.get_secret_value(),
                                     batch_size=settings.EMBEDDING_BATCH_SIZE)


def main(argv: Sequence[str] | None = None, *, settings: Any = None, driver: Any = None,
         client: EmbeddingClient | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline re-vectorisation (V12). Stop API and worker first.")
    parser.add_argument("--neo4j-backup-confirmed", action="store_true",
                        help="confirm the Neo4j backup (K10) was taken after stopping API and worker")
    args = parser.parse_args(argv)
    if settings is None:
        from app.config import load_settings
        settings = load_settings()
    own_driver = driver is None
    if own_driver:
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(settings.NEO4J_URI,
                                      auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD.get_secret_value()))
    try:
        report = run(sqlite_url=settings.SQLITE_URL, driver=driver, settings=settings,
                     client=client or _client_from_settings(settings),
                     neo4j_backup_confirmed=args.neo4j_backup_confirmed)
    except OfflineCheckError as exc:
        print(f"拒绝执行：{exc}（需加 --neo4j-backup-confirmed 并确认已停机）", file=sys.stderr)
        return 2
    except (ReembedError, GraphMigrationError, VectorSpaceError) as exc:
        print(f"失败，记录空间保持不变：{exc}\n{ROLLBACK_STEPS}", file=sys.stderr)
        return 1
    finally:
        if own_driver:
            driver.close()
    if report.action == "cleanup":
        print(f"记录空间已是 {report.target_space}，只清理其他空间的残留属性与索引。")
        return 0
    print(f"已切换向量空间 {report.source_space} -> {report.target_space}")
    print(f"文本块 {report.chunks}，草稿知识点 {report.draft_kps}，已提交版本 {report.versions} 个"
          f"（副本 {report.committed_kps}），未提交尝试残留 {report.orphans}（未迁移，留给 G05 清理）")
    print(f"实际计算 {report.embedded_texts} 段文本，复用 {report.reused} 个已写入向量；SQLite 备份 {report.backup}")
    print(ROLLBACK_STEPS)
    if report.cleanup_error:
        print(f"旧空间清理未完成：{report.cleanup_error}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
