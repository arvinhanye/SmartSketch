"""G02：版本元数据与发布/回滚尝试（specs/teacher-review-publish.md V1、V2、V5、V6；ADR-012）。

``graph_versions`` 每行是一次发布或回滚尝试，``version_id``（ULID）在尝试开始时生成、永不复用，
是这次尝试的幂等键：同一尝试无论提交多少次，至多成为一个版本。状态只前进：

``preparing`` →（写快照）→ ``materialized`` → ``committed``；``preparing``/``materialized`` → ``failed``。

- **同一课程同时至多一个尝试**：部分唯一索引，冲突为 ``PublishInProgress``（409 ``PUBLISH_IN_PROGRESS``）。
- **版本号只在提交时分配**（本课程已提交最大 + 1），失败不占号；``commit_seq`` 同事务从全局
  ``commit_sequence`` 取号。提交与发布指针 CAS 在同一 SQLite 事务（P11 第 1、2 条），调用方在同一
  事务里再做 T7，任一条件不成立抛 ``CommitRejected`` 使整个事务回滚。
- **失败可查**：``failed`` 行带 ``failure_reason`` 永久保留（``list_attempts``）；``committed`` 行由
  触发器保护，不可删、内容不可改。

租约时间由 SQLite ``unixepoch()`` 计算，与 ``course_locks`` 一致。
"""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Final

from app.repositories.sqlite import connect

__all__ = [
    "CommitRejected",
    "DraftState",
    "PublishInProgress",
    "VersionNotFound",
    "VersionRecord",
    "begin_attempt",
    "commit_attempt",
    "complete_published_tasks",
    "current_version",
    "discard_attempt",
    "fail_attempt",
    "get_committed",
    "get_version",
    "heartbeat",
    "immediate",
    "list_attempts",
    "list_versions",
    "mark_materialized",
    "new_version_id",
    "next_commit_seq",
    "read_draft_state",
    "read_snapshot",
    "record_snapshot",
    "set_cleanup_pending",
]

ACTIVE: Final = ("preparing", "materialized")
_CROCKFORD: Final = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_COLUMNS: Final = (
    "version_id, course_id, version, kind, source_version, state, expires_at, digest, node_count, edge_count, "
    "excluded, draft_revision, task_watermark, embedding_space, failure_reason, cleanup_pending, created_by, "
    "created_at, committed_at, commit_seq"
)


class PublishInProgress(Exception):
    """本课程已有进行中的发布或回滚（V2 部分唯一索引）。"""

    code = "PUBLISH_IN_PROGRESS"


class VersionNotFound(LookupError):
    """回滚源版本不存在、不属于本课程或尚未提交。"""

    code = "NOT_FOUND"


class CommitRejected(Exception):
    """提交或幂等路径的条件不成立；调用方的事务必须整体回滚（按 C1 处理）。"""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class VersionRecord:
    version_id: str
    course_id: str
    version: int | None
    kind: str
    source_version: int | None
    state: str
    expires_at: int
    digest: str | None
    node_count: int | None
    edge_count: int | None
    excluded: Mapping[str, int] | None
    draft_revision: int | None
    task_watermark: int | None
    embedding_space: str | None
    failure_reason: str | None
    cleanup_pending: bool
    created_by: str | None
    created_at: str
    committed_at: str | None
    commit_seq: int | None


def _record(row: tuple[Any, ...]) -> VersionRecord:
    values = list(row)
    values[10] = None if values[10] is None else json.loads(values[10])
    values[15] = bool(values[15])
    return VersionRecord(*values)


# ---------------------------------------------------------------- helpers


def new_version_id() -> str:
    """ULID：48 位毫秒时间戳 + 80 位随机数，Crockford base32，26 字符。"""
    value = (time.time_ns() // 1_000_000) << 80 | int.from_bytes(secrets.token_bytes(10), "big")
    return "".join(_CROCKFORD[(value >> shift) & 31] for shift in range(125, -1, -5))


def _text(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _count(name: str, value: object, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an int >= {minimum}")
    return value


@contextmanager
def immediate(sqlite_url: str) -> Iterator[sqlite3.Connection]:
    """一个 ``BEGIN IMMEDIATE`` 写事务；G04 在其中组合 ``commit_attempt`` 与 T7。"""
    with connect(sqlite_url) as database:
        database.execute("BEGIN IMMEDIATE")
        try:
            yield database
            database.execute("COMMIT")
        except BaseException:
            if database.in_transaction:
                database.execute("ROLLBACK")
            raise


def _require_transaction(database: sqlite3.Connection, operation: str) -> None:
    if not database.in_transaction:
        raise RuntimeError(f"{operation} must run inside the caller's write transaction")


def _get(database: sqlite3.Connection, version_id: str) -> VersionRecord | None:
    row = database.execute(f"SELECT {_COLUMNS} FROM graph_versions WHERE version_id = ?", (version_id,)).fetchone()
    return None if row is None else _record(row)


# ---------------------------------------------------------------- attempts


def begin_attempt(
    sqlite_url: str,
    course_id: str,
    *,
    kind: str,
    created_by: str | None,
    lease_seconds: int,
    source_version: int | None = None,
    version_id: str | None = None,
) -> VersionRecord:
    """P2 / R4：插入 ``preparing`` 尝试行。回滚在同一事务里从源版本复制快照、摘要、统计与向量空间。"""
    _text("course_id", course_id)
    _count("lease_seconds", lease_seconds, 1)
    if kind not in ("publish", "rollback"):
        raise ValueError("kind must be publish or rollback")
    if (kind == "rollback") != (source_version is not None):
        raise ValueError("source_version is required for rollback and only for rollback")
    if source_version is not None:
        _count("source_version", source_version, 1)
    version_id = new_version_id() if version_id is None else _text("version_id", version_id)
    with immediate(sqlite_url) as database:
        copied: tuple[Any, ...] = (None,) * 6
        if kind == "rollback":
            source = database.execute(
                """SELECT snapshot_json, digest, node_count, edge_count, excluded, embedding_space
                   FROM graph_versions WHERE course_id = ? AND version = ? AND state = 'committed'""",
                (course_id, source_version),
            ).fetchone()
            if source is None:
                raise VersionNotFound(f"version {source_version} is not a committed version of this course")
            copied = tuple(source)
        try:
            database.execute(
                """INSERT INTO graph_versions (version_id, course_id, kind, source_version, state, expires_at,
                       snapshot_json, digest, node_count, edge_count, excluded, embedding_space, created_by)
                   VALUES (?, ?, ?, ?, 'preparing', unixepoch() + ?, ?, ?, ?, ?, ?, ?, ?)""",
                (version_id, course_id, kind, source_version, lease_seconds, *copied, created_by),
            )
        except sqlite3.IntegrityError as error:
            if "graph_versions.course_id" in str(error) or _active(database, course_id):
                raise PublishInProgress() from None
            raise
        record = _get(database, version_id)
    assert record is not None
    return record


def _active(database: sqlite3.Connection, course_id: str) -> bool:
    return database.execute(
        "SELECT 1 FROM graph_versions WHERE course_id = ? AND state IN ('preparing', 'materialized')",
        (course_id,),
    ).fetchone() is not None


def heartbeat(sqlite_url: str, version_id: str, *, lease_seconds: int) -> bool:
    """续约进行中的尝试；租约已过期（清扫可随时判它失败）或已终态则返回 ``False``。"""
    _count("lease_seconds", lease_seconds, 1)
    with connect(sqlite_url) as database:
        changed = database.execute(
            """UPDATE graph_versions SET expires_at = unixepoch() + ?
               WHERE version_id = ? AND state IN ('preparing', 'materialized') AND expires_at >= unixepoch()""",
            (lease_seconds, version_id),
        ).rowcount
    return changed == 1


def record_snapshot(
    sqlite_url: str,
    version_id: str,
    *,
    snapshot: bytes,
    digest: str,
    node_count: int,
    edge_count: int,
    excluded: Mapping[str, int],
    draft_revision: int,
    task_watermark: int,
    embedding_space: str,
) -> bool:
    """P7：把快照写入仍在 ``preparing`` 的发布尝试；摘要必须是快照字节的 sha256。"""
    if not isinstance(snapshot, (bytes, bytearray)):
        raise TypeError("snapshot must be the canonical bytes")
    if digest != "sha256:" + hashlib.sha256(snapshot).hexdigest():
        raise ValueError("digest does not match the snapshot bytes")
    for name, value in (("node_count", node_count), ("edge_count", edge_count),
                        ("draft_revision", draft_revision), ("task_watermark", task_watermark)):
        _count(name, value)
    _text("embedding_space", embedding_space)
    excluded_json = json.dumps({k: _count(k, excluded[k]) for k in
                                ("low_confidence_nodes", "low_confidence_edges", "cascaded_edges")},
                               sort_keys=True, separators=(",", ":"))
    with connect(sqlite_url) as database:
        changed = database.execute(
            """UPDATE graph_versions
               SET snapshot_json = ?, digest = ?, node_count = ?, edge_count = ?, excluded = ?,
                   draft_revision = ?, task_watermark = ?, embedding_space = ?
               WHERE version_id = ? AND kind = 'publish' AND state = 'preparing'""",
            (bytes(snapshot).decode("utf-8"), digest, node_count, edge_count, excluded_json, draft_revision,
             task_watermark, embedding_space, version_id),
        ).rowcount
    return changed == 1


def mark_materialized(sqlite_url: str, version_id: str) -> bool:
    """P10 / R5 之后：``preparing`` → ``materialized``（必须已有快照）。"""
    with connect(sqlite_url) as database:
        changed = database.execute(
            """UPDATE graph_versions SET state = 'materialized'
               WHERE version_id = ? AND state = 'preparing' AND digest IS NOT NULL""",
            (version_id,),
        ).rowcount
    return changed == 1


def next_commit_seq(database: sqlite3.Connection) -> int:
    """在调用方的写事务里从全局 ``commit_sequence`` 取号；事务回滚则号不被占用。"""
    _require_transaction(database, "next_commit_seq")
    [value] = database.execute(
        "UPDATE commit_sequence SET value = value + 1 WHERE singleton = 1 RETURNING value").fetchone()
    return int(value)


def _pointer_cas(database: sqlite3.Connection, course_id: str, expected_pointer: str | None,
                 assignments: str, parameters: tuple[Any, ...]) -> None:
    changed = database.execute(
        f"UPDATE courses SET {assignments} WHERE id = ? AND published_version_id IS ?",
        (*parameters, course_id, expected_pointer),
    ).rowcount
    if changed != 1:
        raise CommitRejected("publish pointer moved")


def commit_attempt(
    database: sqlite3.Connection,
    version_id: str,
    *,
    expected_pointer: str | None,
    published_from_revision: int,
) -> VersionRecord:
    """P11 / R7 第 1、2 条，在调用方的写事务里：分配版本号与提交序号并切换发布指针。

    条件：尝试行 ``materialized`` 且租约未过期；发布指针仍是 ``expected_pointer``。不成立抛
    ``CommitRejected``，调用方回滚整个事务（T7 一并撤销）。
    """
    _require_transaction(database, "commit_attempt")
    if type(published_from_revision) is not int or published_from_revision < -1:
        raise ValueError("published_from_revision must be an int >= -1")
    attempt = _get(database, version_id)
    if attempt is None:
        raise CommitRejected("attempt not found")
    [live] = database.execute(
        "SELECT state = 'materialized' AND expires_at > unixepoch() FROM graph_versions WHERE version_id = ?",
        (version_id,),
    ).fetchone()
    if not live:
        raise CommitRejected("attempt is not materialized or its lease expired")
    [number] = database.execute(
        "SELECT coalesce(max(version), 0) + 1 FROM graph_versions WHERE course_id = ? AND state = 'committed'",
        (attempt.course_id,),
    ).fetchone()
    seq = next_commit_seq(database)
    database.execute(
        """UPDATE graph_versions
           SET state = 'committed', version = ?, commit_seq = ?,
               committed_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
           WHERE version_id = ?""",
        (number, seq, version_id),
    )
    _pointer_cas(database, attempt.course_id, expected_pointer,
                 "published_version_id = ?, published_version = ?, published_from_revision = ?",
                 (version_id, number, published_from_revision))
    record = _get(database, version_id)
    assert record is not None
    return record


def discard_attempt(
    database: sqlite3.Connection,
    version_id: str,
    *,
    expected_pointer: str | None,
    published_from_revision: int,
) -> None:
    """P7 幂等路径 / R3：删除从未成为版本的 ``preparing`` 尝试行并更新 ``published_from_revision``。

    条件：尝试行仍为 ``preparing``（未被清扫判失败）；发布指针仍是 ``expected_pointer``。T7 由调用方在
    同一事务里执行。
    """
    _require_transaction(database, "discard_attempt")
    attempt = _get(database, version_id)
    changed = database.execute(
        "DELETE FROM graph_versions WHERE version_id = ? AND state = 'preparing'", (version_id,)
    ).rowcount
    if attempt is None or changed != 1:
        raise CommitRejected("attempt is no longer preparing")
    if expected_pointer is None:
        raise CommitRejected("no published version to keep")
    _pointer_cas(database, attempt.course_id, expected_pointer, "published_from_revision = ?",
                 (published_from_revision,))


def fail_attempt(sqlite_url: str, version_id: str, reason: str) -> bool:
    """C1 第 1 步：``preparing``/``materialized`` → ``failed``。0 行说明已提交或已被处理，不得清理 Neo4j。"""
    _text("reason", reason)
    with connect(sqlite_url) as database:
        changed = database.execute(
            """UPDATE graph_versions SET state = 'failed', failure_reason = ?
               WHERE version_id = ? AND state IN ('preparing', 'materialized')""",
            (reason[:255], version_id),
        ).rowcount
    return changed == 1


def set_cleanup_pending(sqlite_url: str, version_id: str, pending: bool) -> bool:
    """C1 第 3 步与清扫：只对 ``failed`` 行设置或清除 Neo4j 待清理标记。"""
    with connect(sqlite_url) as database:
        changed = database.execute(
            "UPDATE graph_versions SET cleanup_pending = ? WHERE version_id = ? AND state = 'failed'",
            (1 if pending else 0, version_id),
        ).rowcount
    return changed == 1


# ---------------------------------------------------------------- reads


def get_version(sqlite_url: str, version_id: str) -> VersionRecord | None:
    with connect(sqlite_url) as database:
        return _get(database, version_id)


def get_committed(sqlite_url: str, course_id: str, version: int) -> VersionRecord | None:
    with connect(sqlite_url) as database:
        row = database.execute(
            f"SELECT {_COLUMNS} FROM graph_versions WHERE course_id = ? AND version = ? AND state = 'committed'",
            (course_id, version),
        ).fetchone()
    return None if row is None else _record(row)


def current_version(sqlite_url: str, course_id: str) -> VersionRecord | None:
    """发布指针指向的版本；从未发布为 ``None``。"""
    with connect(sqlite_url) as database:
        row = database.execute(
            f"""SELECT {", ".join("v." + c.strip() for c in _COLUMNS.split(","))}
                FROM courses c JOIN graph_versions v ON v.version_id = c.published_version_id
                WHERE c.id = ?""",
            (course_id,),
        ).fetchone()
    return None if row is None else _record(row)


def list_versions(sqlite_url: str, course_id: str) -> list[VersionRecord]:
    """版本列表：本课程已提交版本，版本号降序；``failed`` 行不参与。"""
    with connect(sqlite_url) as database:
        rows = database.execute(
            f"""SELECT {_COLUMNS} FROM graph_versions WHERE course_id = ? AND state = 'committed'
                ORDER BY version DESC""",
            (course_id,),
        ).fetchall()
    return [_record(r) for r in rows]


def list_attempts(sqlite_url: str, course_id: str) -> list[VersionRecord]:
    """审计：本课程全部尝试（含 ``failed`` 与进行中），按创建先后。"""
    with connect(sqlite_url) as database:
        rows = database.execute(
            f"SELECT {_COLUMNS} FROM graph_versions WHERE course_id = ? ORDER BY created_at, version_id",
            (course_id,),
        ).fetchall()
    return [_record(r) for r in rows]


def read_snapshot(sqlite_url: str, version_id: str) -> bytes | None:
    with connect(sqlite_url) as database:
        row = database.execute("SELECT snapshot_json FROM graph_versions WHERE version_id = ?",
                               (version_id,)).fetchone()
    return None if row is None or row[0] is None else row[0].encode("utf-8")


# ---------------------------------------------------------------- G04 发布输入与 T7


@dataclass(frozen=True)
class DraftState:
    """P4 在课程写锁内一次读出的 SQLite 部分（V3 可见性前提、V4）。

    ``effective_task_ids`` 即有效任务集合 V；``task_watermark`` 为本课程当前最大 T6 提交序号（无则 0），
    持锁时 V 恰为 T6 序号 ≤ 水位的 ``awaiting_review``/``completed`` 任务；``revisions`` 为 V 内任务产生的
    全部资料修订 ``(revision_id, material_id, content_hash, parser_version)``，按 ``revision_id`` 升序。
    """

    course_id: str
    draft_revision: int
    published_version_id: str | None
    task_watermark: int
    effective_task_ids: tuple[str, ...]
    revisions: tuple[tuple[str, str, str, str], ...]


def read_draft_state(sqlite_url: str, course_id: str) -> DraftState:
    """P4：在一个读事务里读草稿修订号、发布指针、任务水位、V 与 V 的资料修订。课程不存在抛 ``LookupError``。"""
    _text("course_id", course_id)
    with connect(sqlite_url) as database:
        database.execute("BEGIN")
        try:
            row = database.execute(
                "SELECT draft_revision, published_version_id FROM courses WHERE id = ?", (course_id,)
            ).fetchone()
            if row is None:
                raise LookupError("course not found")
            [watermark] = database.execute(
                "SELECT coalesce(max(t6_seq), 0) FROM processing_tasks WHERE course_id = ?", (course_id,)
            ).fetchone()
            tasks = tuple(r[0] for r in database.execute(
                """SELECT id FROM processing_tasks
                   WHERE course_id = ? AND stage IN ('awaiting_review', 'completed') ORDER BY id""",
                (course_id,),
            ))
            revisions = tuple(tuple(r) for r in database.execute(
                """SELECT DISTINCT r.revision_id, r.material_id, r.content_hash, r.parser_version
                   FROM processing_tasks t
                   JOIN task_revisions tr ON tr.task_id = t.id AND tr.course_id = t.course_id
                   JOIN material_revisions r ON r.revision_id = tr.revision_id AND r.course_id = t.course_id
                   WHERE t.course_id = ? AND t.stage IN ('awaiting_review', 'completed')
                   ORDER BY r.revision_id""",
                (course_id,),
            ))
        finally:
            database.execute("COMMIT")
    return DraftState(course_id, int(row[0]), row[1], int(watermark), tasks, revisions)  # type: ignore[arg-type]


def complete_published_tasks(database: sqlite3.Connection, course_id: str, task_watermark: int) -> int:
    """T7（A03 §3），在调用方的提交事务里：水位以内的 ``awaiting_review`` 任务转 ``completed``。

    T6 在同一事务里分配序号并进入 ``awaiting_review``，故这些任务的 ``t6_seq`` 非空；为兼容 009 之前的
    历史行，空序号按 0 处理（它们一定早于任何水位可见）。
    """
    _require_transaction(database, "complete_published_tasks")
    _count("task_watermark", task_watermark)
    return database.execute(
        """UPDATE processing_tasks
           SET stage = 'completed', progress = 1, updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
           WHERE course_id = ? AND stage = 'awaiting_review' AND coalesce(t6_seq, 0) <= ?""",
        (course_id, task_watermark),
    ).rowcount
