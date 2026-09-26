"""I01：学习进度仓储（specs/learning-path.md §5；ADR-014 修订 1 决定 8、9；ADR-012 修订 3 决定 21～24；ADR-049）。

**原始进度**存 SQLite ``learning_progress``，按 ``(user_id, course_id, kp_id)`` 一行，是学生声明的事实：
不按版本复制，节点离开版本时不删除（dormant），合并继承不写回。每次写入事务从全局
``commit_sequence``（迁移 010，与版本提交共用）取**一个**写入序号 ``write_seq``。

**读时投影**（§5）：调用方按 G07 ``resolve_published`` 在请求开始时绑定一个已提交版本，
``project_progress`` 在一个读事务里取该学生该课程的原始行与本课程全部已提交版本的节点集、谱系
``merged_from``、提交序号，得到绑定版本 V 中**每个节点**的 ``ProgressEntry``：

- 来源 ``m`` 在绑定版本（版本号 ``n``）中出现在 ``p.merged_from`` 即归属 ``p``（修订 3 决定 15：链已展平，
  「最近的仍在 V 中的节点」由构造保证）。从 ``n`` 起逐个往前，``m`` 连续出现在 ``p.merged_from`` 的最早版本
  为 ``k``，其提交序号为 ``T``；``p`` 自身行的 ``write_seq > T`` 时 ``m`` 被覆盖（决定 9）。
- ``status`` = 自身行（无行按 ``unknown``）与未被覆盖、有原始行的来源中的最高者，序为
  ``unknown < learning < mastered``；``inherited_from`` 只列这些来源，按 ``kp_id`` 的 UTF-8 字节序。
- 原始行的 ``kp_id`` 不在本课程任何已提交版本的节点集中 → 脏行：记告警与诊断 ID 后忽略，不中断读取；
  历史版本出现过、当前不在 V 中的行是 dormant，不告警。
- 绑定版本谱系违反修订 3 决定 16、``V = ∅``、快照损坏或不属于本课程 → ``VersionIntegrityError``（5xx），
  不输出部分进度。

**写入**（``write_progress``，§5「写入进度」「同值写入」）：先整批校验（非空、字段闭合、状态合法、
同批 ``kp_id`` 不重复），再在一个 ``BEGIN IMMEDIATE`` 事务里读发布指针（这就是提交时的最终绑定版本，
请求开始后指针变化时自然按新版本复核），任一目标不在该版本 → ``ProgressNotInPublishedVersion``（422，
零写入）。同值写入仅当该节点已有自身行、状态相同且投影中没有未被覆盖的来源时为无操作：不取号、不改
``updated_at``。其余项在同一事务里写入同一个 ``write_seq``，提交前按最终绑定版本重新投影并返回。

身份（``user_id``）只由调用方从已认证会话传入；本仓储不做鉴权与成员判断（I02）。
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import uuid
from collections import OrderedDict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, Literal

from app.repositories.sqlite import connect
from app.repositories.versions import next_commit_seq
from app.services.access import graph_not_published, not_found
from app.services.versions.resolver import PublishedVersion, VersionIntegrityError
from app.services.versions.snapshot import SnapshotFormatError, digest_of, load_snapshot

__all__ = [
    "STATUSES",
    "InheritedSource",
    "MasteryStatus",
    "ProgressEntry",
    "ProgressNotInPublishedVersion",
    "ProgressRow",
    "ProgressValidationError",
    "ProgressView",
    "ProgressWrite",
    "clear_cache",
    "project_progress",
    "read_rows",
    "write_progress",
]

logger = logging.getLogger(__name__)

MasteryStatus = Literal["unknown", "learning", "mastered"]
STATUSES: Final[tuple[MasteryStatus, ...]] = ("unknown", "learning", "mastered")
_RANK: Final = {status: rank for rank, status in enumerate(STATUSES)}
_UPDATE_KEYS: Final = frozenset({"kp_id", "status"})
_CACHE_SIZE: Final = 256


# ---------------------------------------------------------------- 结果与错误


@dataclass(frozen=True)
class ProgressRow:
    """该学生在一个 ``kp_id`` 上的原始行。"""

    kp_id: str
    status: MasteryStatus
    write_seq: int
    updated_at: str


@dataclass(frozen=True)
class InheritedSource:
    """契约 ``ProgressInheritedSource``：归属到本节点、有原始行且未被覆盖的来源。"""

    kp_id: str
    status: MasteryStatus

    def to_dict(self) -> dict[str, Any]:
        return {"kp_id": self.kp_id, "status": self.status}


@dataclass(frozen=True)
class ProgressEntry:
    """契约 ``ProgressEntry``：绑定版本 V 中一个节点的投影。"""

    kp_id: str
    status: MasteryStatus
    own_status: MasteryStatus | None
    inherited_from: tuple[InheritedSource, ...]
    updated_at: str | None

    def to_dict(self) -> dict[str, Any]:
        return {"kp_id": self.kp_id, "status": self.status, "own_status": self.own_status,
                "inherited_from": [source.to_dict() for source in self.inherited_from],
                "updated_at": self.updated_at}


@dataclass(frozen=True)
class ProgressView:
    """一次投影：绑定版本与 V 中每个节点的进度项（按 ``kp_id`` 的 UTF-8 字节序）。"""

    course_id: str
    version_id: str
    graph_version: int
    entries: tuple[ProgressEntry, ...]

    @property
    def mastered(self) -> frozenset[str]:
        """推荐（I03/I04）使用的投影掌握集合 ``M ⊆ V``。"""
        return frozenset(entry.kp_id for entry in self.entries if entry.status == "mastered")

    def to_dict(self) -> dict[str, Any]:
        """契约 ``ProgressResponse``。"""
        return {"graph_version": self.graph_version, "entries": [entry.to_dict() for entry in self.entries]}


@dataclass(frozen=True)
class ProgressWrite:
    """``write_progress`` 的结果：``written`` 为实际写入的 ``kp_id``（升序），全为无操作时 ``write_seq`` 为 ``None``。"""

    view: ProgressView
    written: tuple[str, ...]
    write_seq: int | None


class ProgressValidationError(ValueError):
    """批次不合结构、状态非法或同批 ``kp_id`` 重复；整批拒绝、零写入（通用 422）。"""

    code = "VALIDATION_ERROR"


class ProgressNotInPublishedVersion(Exception):
    """目标不在写入事务所见的当前发布版（草稿独有、已删除、他课、途中被新版本删除）；整批零写入。

    ``details()`` 即契约 ``ProgressNotInPublishedVersionDetails``（ADR-017 决定 5），只以请求下标定位，
    不回显 ``kp_id``。
    """

    code = "VALIDATION_ERROR"

    def __init__(self, indices: tuple[int, ...], graph_version: int) -> None:
        super().__init__(f"{len(indices)} progress item(s) not in published version {graph_version}")
        self.indices = indices
        self.graph_version = graph_version

    def details(self) -> dict[str, Any]:
        return {"fields": [{"in": "body", "field": f"{index}.kp_id", "reason": "not_in_published_version"}
                           for index in self.indices],
                "graph_version": self.graph_version}


# ---------------------------------------------------------------- 已提交版本的谱系（按 version_id 缓存）


@dataclass(frozen=True)
class _Lineage:
    """一个已提交版本的节点集与谱系；``defect`` 非空表示违反修订 3 决定 16 或 ``V = ∅``。"""

    course_id: str
    nodes: frozenset[str]
    merged_from: Mapping[str, frozenset[str]]
    defect: str | None


@dataclass(frozen=True)
class _Version:
    version_id: str
    version: int
    commit_seq: int
    lineage: _Lineage


_lock = threading.Lock()
_lineages: OrderedDict[tuple[str, str], _Lineage] = OrderedDict()


def clear_cache() -> None:
    with _lock:
        _lineages.clear()


def _lineage(database: sqlite3.Connection, sqlite_url: str, version_id: str) -> _Lineage:
    key = (sqlite_url, version_id)
    with _lock:
        cached = _lineages.get(key)
        if cached is not None:
            _lineages.move_to_end(key)
            return cached
    row = database.execute(
        "SELECT course_id, snapshot_json, digest FROM graph_versions WHERE version_id = ? AND state = 'committed'",
        (version_id,),
    ).fetchone()
    if row is None or row[1] is None:
        raise VersionIntegrityError(f"committed version {version_id} has no snapshot")
    raw = row[1].encode("utf-8")
    if digest_of(raw) != row[2]:
        raise VersionIntegrityError(f"snapshot digest mismatch for version {version_id}")
    try:
        snapshot = load_snapshot(raw)
    except SnapshotFormatError as error:
        raise VersionIntegrityError(f"snapshot of version {version_id} is malformed") from error
    if snapshot.data["course_id"] != row[0]:
        raise VersionIntegrityError(f"snapshot of version {version_id} belongs to another course")
    nodes = frozenset(node["kp_id"] for node in snapshot.data["nodes"])
    merged = {node["kp_id"]: frozenset(node["merged_from"]) for node in snapshot.data["nodes"]}
    lineage = _Lineage(row[0], nodes, merged, _defect(nodes, merged))
    with _lock:
        _lineages[key] = lineage
        while len(_lineages) > _CACHE_SIZE:
            _lineages.popitem(last=False)
    return lineage


def _defect(nodes: frozenset[str], merged: Mapping[str, frozenset[str]]) -> str | None:
    if not nodes:
        return "empty version"
    seen: set[str] = set()
    for primary in sorted(merged):
        sources = merged[primary]
        if sources & nodes:  # 含自身：来源不能是本快照的节点
            return f"lineage source of {primary} is a node of the version"
        if sources & seen:
            return f"lineage source of {primary} belongs to another node too"
        seen |= sources
    return None


def _history(database: sqlite3.Connection, sqlite_url: str, course_id: str) -> list[_Version]:
    """本课程全部已提交版本，版本号升序。"""
    rows = database.execute(
        """SELECT version_id, version, commit_seq FROM graph_versions
           WHERE course_id = ? AND state = 'committed' ORDER BY version""",
        (course_id,),
    ).fetchall()
    # 版本行按 course_id 查出；快照的课程归属已在 _lineage 中与版本行核对。
    return [_Version(vid, number, seq, _lineage(database, sqlite_url, vid)) for vid, number, seq in rows]


# ---------------------------------------------------------------- 投影


def _utf8(value: str) -> bytes:
    return value.encode("utf-8")


def _rows(database: sqlite3.Connection, user_id: str, course_id: str) -> dict[str, ProgressRow]:
    return {row[0]: ProgressRow(*row) for row in database.execute(
        """SELECT kp_id, status, write_seq, updated_at FROM learning_progress
           WHERE user_id = ? AND course_id = ?""",
        (user_id, course_id),
    )}


def _project(course_id: str, version_id: str, history: Sequence[_Version],
             rows: Mapping[str, ProgressRow], *, warn: bool = True) -> ProgressView:
    index = next((i for i, item in enumerate(history) if item.version_id == version_id), None)
    if index is None:
        raise VersionIntegrityError(f"bound version {version_id} is not a committed version of course {course_id}")
    bound = history[index]
    if bound.lineage.defect is not None:
        raise VersionIntegrityError(f"committed version {version_id}: {bound.lineage.defect}")

    known = frozenset().union(*(item.lineage.nodes for item in history))
    dirty = sorted((kp for kp in rows if kp not in known), key=_utf8)
    if dirty and warn:
        logger.warning("ignored progress rows outside every committed version of course %s: %s diagnostic_id=%s",
                       course_id, ",".join(dirty), uuid.uuid4().hex)

    def bound_seq(source: str, primary: str) -> int:
        """``source`` 连续归属 ``primary`` 的起算版本 ``k`` 的提交序号 ``T``。"""
        start = index
        while start > 0 and source in history[start - 1].lineage.merged_from.get(primary, ()):
            start -= 1
        return history[start].commit_seq

    entries = []
    for kp_id in sorted(bound.lineage.nodes, key=_utf8):
        own = rows.get(kp_id)
        inherited = []
        for source in sorted(bound.lineage.merged_from[kp_id], key=_utf8):
            row = rows.get(source)
            if row is None or source not in known:
                continue
            if own is not None and own.write_seq > bound_seq(source, kp_id):
                continue
            inherited.append(InheritedSource(source, row.status))
        candidates = [own.status if own is not None else "unknown", *(s.status for s in inherited)]
        status = max(candidates, key=_RANK.__getitem__)
        entries.append(ProgressEntry(kp_id, status, None if own is None else own.status, tuple(inherited),
                                     None if own is None else own.updated_at))
    return ProgressView(course_id, version_id, bound.version, tuple(entries))


def read_rows(sqlite_url: str, user_id: str, course_id: str) -> dict[str, ProgressRow]:
    """该学生在该课程的全部原始行（含 dormant 与脏行），不投影；只按 ``(user_id, course_id)`` 隔离。"""
    _text("user_id", user_id)
    _text("course_id", course_id)
    with connect(sqlite_url) as database:
        return _rows(database, user_id, course_id)


def project_progress(sqlite_url: str, user_id: str, bound: PublishedVersion) -> ProgressView:
    """``GET /progress`` 与推荐：按请求已绑定的版本投影，原始行与版本历史在同一读事务里读出。"""
    _text("user_id", user_id)
    with connect(sqlite_url) as database:
        database.execute("BEGIN")
        try:
            rows = _rows(database, user_id, bound.course_id)
            history = _history(database, sqlite_url, bound.course_id)
        finally:
            database.execute("COMMIT")
    view = _project(bound.course_id, bound.version_id, history, rows)
    if view.graph_version != bound.version:
        raise VersionIntegrityError(f"bound version {bound.version_id} number disagrees with its row")
    return view


# ---------------------------------------------------------------- 写入


def _text(name: str, value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _validate(updates: object) -> list[tuple[str, MasteryStatus]]:
    if isinstance(updates, (str, bytes)) or not isinstance(updates, Sequence):
        raise ProgressValidationError("progress updates must be a list")
    if not updates:
        raise ProgressValidationError("progress updates must not be empty")
    items: list[tuple[str, MasteryStatus]] = []
    seen: set[str] = set()
    for index, update in enumerate(updates):
        if not isinstance(update, Mapping) or set(update) != _UPDATE_KEYS:
            raise ProgressValidationError(f"item {index} must have exactly kp_id and status")
        kp_id, status = update["kp_id"], update["status"]
        if not isinstance(kp_id, str) or not kp_id:
            raise ProgressValidationError(f"item {index} kp_id must be a non-empty string")
        if status not in _RANK:
            raise ProgressValidationError(f"item {index} status is not a mastery status")
        if kp_id in seen:
            raise ProgressValidationError(f"item {index} repeats a kp_id of this batch")
        seen.add(kp_id)
        items.append((kp_id, status))
    return items


_POINTER: Final = """
    SELECT c.published_version_id, c.published_version, v.course_id, v.version, v.state
    FROM courses c LEFT JOIN graph_versions v ON v.version_id = c.published_version_id
    WHERE c.id = ?"""

_UPSERT: Final = """
    INSERT INTO learning_progress (user_id, course_id, kp_id, status, write_seq, updated_at)
    VALUES (?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
    ON CONFLICT (user_id, course_id, kp_id) DO UPDATE
    SET status = excluded.status, write_seq = excluded.write_seq, updated_at = excluded.updated_at"""


def write_progress(sqlite_url: str, user_id: str, course_id: str,
                   updates: Iterable[Mapping[str, Any]]) -> ProgressWrite:
    """``PUT /progress``：整批校验后在一个写事务内写入，并按提交时的最终绑定版本返回投影。

    课程不存在 → 404 ``NOT_FOUND``；从未发布 → 404 ``GRAPH_NOT_PUBLISHED``（均为 ``AccessDenied``）；
    指针或已提交版本损坏 → ``VersionIntegrityError``。
    """
    _text("user_id", user_id)
    _text("course_id", course_id)
    items = _validate(updates)
    with connect(sqlite_url) as database:
        database.execute("BEGIN IMMEDIATE")
        try:
            result = _write(database, sqlite_url, user_id, course_id, items)
            database.execute("COMMIT")
        except BaseException:
            if database.in_transaction:
                database.execute("ROLLBACK")
            raise
    return result


def _write(database: sqlite3.Connection, sqlite_url: str, user_id: str, course_id: str,
           items: list[tuple[str, MasteryStatus]]) -> ProgressWrite:
    pointer = database.execute(_POINTER, (course_id,)).fetchone()
    if pointer is None:
        raise not_found()
    version_id, pointer_number, row_course, number, state = pointer
    if version_id is None:
        raise graph_not_published()
    if state != "committed" or row_course != course_id or number != pointer_number:
        raise VersionIntegrityError(f"publish pointer of course {course_id} is not a consistent committed version")
    history = _history(database, sqlite_url, course_id)
    rows = _rows(database, user_id, course_id)
    view = _project(course_id, version_id, history, rows)
    nodes = {entry.kp_id: entry for entry in view.entries}

    missing = tuple(index for index, (kp_id, _) in enumerate(items) if kp_id not in nodes)
    if missing:
        raise ProgressNotInPublishedVersion(missing, view.graph_version)

    changed = sorted((kp_id for kp_id, status in items
                      if not (nodes[kp_id].own_status == status and not nodes[kp_id].inherited_from)), key=_utf8)
    if not changed:
        return ProgressWrite(view, (), None)
    seq = next_commit_seq(database)
    wanted = dict(items)
    database.executemany(_UPSERT, [(user_id, course_id, kp_id, wanted[kp_id], seq) for kp_id in changed])
    view = _project(course_id, version_id, history, _rows(database, user_id, course_id), warn=False)
    return ProgressWrite(view, tuple(changed), seq)
