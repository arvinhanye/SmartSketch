"""I02：掌握标记——读时投影与批量写入（specs/learning-path.md §5；ADR-014 修订 1 决定 8、9；ADR-017 决定 5）。

原始进度由 I01 仓储（``app.repositories.progress``）按 ``(user_id, course_id, kp_id)`` 保存；本模块只读写它，
从不改写原始行来表达继承。

**读时投影**（``project_progress``）：调用方按 G07 在请求开始时绑定一个已提交版本 V。取该学生该课程的原始行与
本课程全部已提交版本的节点集、谱系 ``merged_from``、提交序号，得到 V 中**每个节点**的进度项：

- 来源 ``m`` 在绑定版本（版本号 ``n``）中出现在 ``p.merged_from`` 即归属 ``p``（ADR-012 修订 3 决定 15：链已展平，
  “最近的仍在 V 中的节点”由构造保证）。从 ``n`` 起逐个往前，``m`` 连续出现在 ``p.merged_from`` 的最早版本为
  ``k``，其提交序号为 ``T``；``p`` 自身行的 ``write_seq > T`` 时 ``m`` 被覆盖（决定 9）。
- ``status`` 取自身行（无行按 ``unknown``）与未被覆盖、有原始行的来源中的最高者（``unknown < learning < mastered``）；
  ``inherited_from`` 只列这些来源，按 ``kp_id`` 的 UTF-8 字节序。
- 原始行 ``kp_id`` 不在本课程任何已提交版本中 → 脏行：告警并附诊断 ID 后忽略；历史版出现过的是 dormant，不告警。
- 绑定版本谱系违反修订 3 决定 16、``V = ∅``、快照损坏或不属于本课程 → ``VersionIntegrityError``（5xx），
  不输出部分进度。

**写入**（``update_progress``）：整批先查同批重复 ``kp_id``（422 通用），再在一个 ``BEGIN IMMEDIATE`` 事务里重新
解析发布指针——持有写锁后指针不会再动，这就是提交时的最终绑定版本；请求开始后指针变化时自然按新版本复核整批。
任一目标不在该版本（草稿独有、已删除、他课）→ ``ProgressNotInPublishedVersion``（422，零写入）。同值写入按 A08S-R01：
仍有未被覆盖的来源时以 ``force`` 写入以覆盖它们，否则由仓储判为无操作（不取号、不改 ``updated_at``）。提交后按
最终绑定版本重新投影并返回。身份 ``user_id`` 只由路由从已认证会话传入。
"""

from __future__ import annotations

import logging
import threading
import uuid
from collections import OrderedDict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, Literal

from app.repositories import progress as progress_repository
from app.repositories import versions as versions_repository
from app.repositories.progress import ProgressRecord, ProgressUpdate
from app.services.versions.resolver import PublishedVersion, VersionIntegrityError, resolve_published
from app.services.versions.snapshot import SnapshotFormatError, digest_of, load_snapshot

__all__ = [
    "DuplicateProgressTarget",
    "InheritedSource",
    "MasteryStatus",
    "ProgressEntry",
    "ProgressNotInPublishedVersion",
    "ProgressView",
    "clear_cache",
    "get_progress",
    "project_progress",
    "update_progress",
]

logger = logging.getLogger(__name__)

MasteryStatus = Literal["unknown", "learning", "mastered"]
_RANK: Final = {"unknown": 0, "learning": 1, "mastered": 2}
_CACHE_SIZE: Final = 256


# ---------------------------------------------------------------- 结果与错误


@dataclass(frozen=True)
class InheritedSource:
    """契约 ``ProgressInheritedSource``：归属到本节点、有原始行且未被覆盖的来源。"""

    kp_id: str
    status: MasteryStatus


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
                "inherited_from": [{"kp_id": s.kp_id, "status": s.status} for s in self.inherited_from],
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
        """推荐（I03/I04/I05）使用的投影掌握集合 ``M ⊆ V``。"""
        return frozenset(entry.kp_id for entry in self.entries if entry.status == "mastered")

    def to_dict(self) -> dict[str, Any]:
        """契约 ``ProgressResponse``。"""
        return {"graph_version": self.graph_version, "entries": [entry.to_dict() for entry in self.entries]}


class DuplicateProgressTarget(ValueError):
    """同批 ``kp_id`` 重复：通用 422 ``VALIDATION_ERROR``，整批零写入；``indices`` 为重复出现项的下标。"""

    def __init__(self, indices: tuple[int, ...]) -> None:
        super().__init__(f"{len(indices)} progress item(s) repeat a kp_id of this batch")
        self.indices = indices


class ProgressNotInPublishedVersion(Exception):
    """目标不在写入事务所见的当前发布版（ADR-017 决定 5）；整批零写入。

    ``details()`` 即契约 ``ProgressNotInPublishedVersionDetails``：只以请求下标定位，不回显 ``kp_id``，
    草稿独有、已删除、他课同一 ``reason``。
    """

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


def _lineage(sqlite_url: str, course_id: str, record: versions_repository.VersionRecord) -> _Lineage:
    """已提交快照不可变（G02 触发器），因此按 ``version_id`` 缓存；损坏的快照不缓存。"""
    key = (sqlite_url, record.version_id)
    with _lock:
        cached = _lineages.get(key)
        if cached is not None:
            _lineages.move_to_end(key)
            return cached
    raw = versions_repository.read_snapshot(sqlite_url, record.version_id)
    if raw is None:
        raise VersionIntegrityError(f"committed version {record.version_id} has no snapshot")
    if digest_of(raw) != record.digest:
        raise VersionIntegrityError(f"snapshot digest mismatch for version {record.version_id}")
    try:
        snapshot = load_snapshot(raw)
    except SnapshotFormatError as error:
        raise VersionIntegrityError(f"snapshot of version {record.version_id} is malformed") from error
    if snapshot.data["course_id"] != course_id:
        raise VersionIntegrityError(f"snapshot of version {record.version_id} belongs to another course")
    nodes = frozenset(node["kp_id"] for node in snapshot.data["nodes"])
    merged = {node["kp_id"]: frozenset(node["merged_from"]) for node in snapshot.data["nodes"]}
    lineage = _Lineage(nodes, merged, _defect(nodes, merged))
    with _lock:
        _lineages[key] = lineage
        while len(_lineages) > _CACHE_SIZE:
            _lineages.popitem(last=False)
    return lineage


def _history(sqlite_url: str, course_id: str) -> list[_Version]:
    """本课程全部已提交版本，版本号升序。已提交行只增不改，读取无需与进度行共用快照。"""
    history = []
    for record in sorted(versions_repository.list_versions(sqlite_url, course_id), key=lambda r: r.version or 0):
        if record.version is None or record.commit_seq is None:
            raise VersionIntegrityError(f"committed version {record.version_id} lacks a number or commit_seq")
        history.append(_Version(record.version_id, record.version, record.commit_seq,
                                _lineage(sqlite_url, course_id, record)))
    return history


# ---------------------------------------------------------------- 投影


def _utf8(value: str) -> bytes:
    return value.encode("utf-8")


def _project(bound: PublishedVersion, history: Sequence[_Version],
             rows: Mapping[str, ProgressRecord]) -> ProgressView:
    index = next((i for i, item in enumerate(history) if item.version_id == bound.version_id), None)
    if index is None:
        raise VersionIntegrityError(f"bound version {bound.version_id} is not committed in course {bound.course_id}")
    current = history[index]
    if current.version != bound.version:
        raise VersionIntegrityError(f"bound version {bound.version_id} number disagrees with its row")
    if current.lineage.defect is not None:
        raise VersionIntegrityError(f"committed version {bound.version_id}: {current.lineage.defect}")

    known = frozenset().union(*(item.lineage.nodes for item in history))
    dirty = sorted((kp for kp in rows if kp not in known), key=_utf8)
    if dirty:
        logger.warning("ignored progress rows outside every committed version of course %s: %s diagnostic_id=%s",
                       bound.course_id, ",".join(dirty), uuid.uuid4().hex)

    def bound_seq(source: str, primary: str) -> int:
        """``source`` 连续归属 ``primary`` 的起算版本 ``k`` 的提交序号 ``T``。"""
        start = index
        while start > 0 and source in history[start - 1].lineage.merged_from.get(primary, ()):
            start -= 1
        return history[start].commit_seq

    entries = []
    for kp_id in sorted(current.lineage.nodes, key=_utf8):
        own = rows.get(kp_id)
        inherited = []
        for source in sorted(current.lineage.merged_from[kp_id], key=_utf8):
            row = rows.get(source)
            if row is None:
                continue
            if own is not None and own.write_seq > bound_seq(source, kp_id):
                continue
            inherited.append(InheritedSource(source, row.status))  # type: ignore[arg-type]
        candidates = [own.status if own is not None else "unknown", *(s.status for s in inherited)]
        status = max(candidates, key=_RANK.__getitem__)
        entries.append(ProgressEntry(kp_id, status, None if own is None else own.status,  # type: ignore[arg-type]
                                     tuple(inherited), None if own is None else own.updated_at))
    return ProgressView(bound.course_id, bound.version_id, bound.version, tuple(entries))


def _rows(sqlite_url: str, user_id: str, course_id: str) -> dict[str, ProgressRecord]:
    return {row.kp_id: row for row in progress_repository.read_progress(sqlite_url, user_id=user_id,
                                                                         course_id=course_id)}


def project_progress(sqlite_url: str, user_id: str, bound: PublishedVersion) -> ProgressView:
    """按请求已绑定的版本投影；推荐（I05）与 ``GET /progress`` 共用，保证同版本同投影。"""
    rows = _rows(sqlite_url, user_id, bound.course_id)
    return _project(bound, _history(sqlite_url, bound.course_id), rows)


def get_progress(sqlite_url: str, user_id: str, course_id: str) -> ProgressView:
    """``GET /progress``：请求开始时绑定一次当前发布版（G07），再投影。"""
    return project_progress(sqlite_url, user_id, resolve_published(sqlite_url, course_id))


# ---------------------------------------------------------------- 写入


def _duplicates(updates: Sequence[tuple[str, str]]) -> tuple[int, ...]:
    seen: set[str] = set()
    repeated = []
    for index, (kp_id, _) in enumerate(updates):
        if kp_id in seen:
            repeated.append(index)
        seen.add(kp_id)
    return tuple(repeated)


def update_progress(sqlite_url: str, user_id: str, course_id: str,
                    updates: Sequence[tuple[str, str]]) -> ProgressView:
    """``PUT /progress``：整批校验后在一个写事务内写入，返回提交时最终绑定版本的投影。

    ``updates`` 为已通过 schema 校验的 ``(kp_id, status)``。从未发布 → 404 ``GRAPH_NOT_PUBLISHED``；
    指针或已提交版本损坏 → ``VersionIntegrityError``。
    """
    if not updates:
        raise ValueError("progress updates must not be empty")
    repeated = _duplicates(updates)
    if repeated:
        raise DuplicateProgressTarget(repeated)
    with versions_repository.immediate(sqlite_url) as database:
        # 持有写锁后发布指针不会再变（发布/回滚提交同样需要写锁），因此此处绑定的就是提交时的最终版本。
        bound = resolve_published(sqlite_url, course_id)
        view = _project(bound, _history(sqlite_url, course_id), _rows(sqlite_url, user_id, course_id))
        nodes = {entry.kp_id: entry for entry in view.entries}
        missing = tuple(index for index, (kp_id, _) in enumerate(updates) if kp_id not in nodes)
        if missing:
            raise ProgressNotInPublishedVersion(missing, bound.version)
        batch = [ProgressUpdate(kp_id, status,
                                force=nodes[kp_id].own_status == status and bool(nodes[kp_id].inherited_from))
                 for kp_id, status in updates]
        progress_repository.write_progress_in_transaction(
            database, user_id=user_id, course_id=course_id, version_id=bound.version_id,
            published_kp_ids=nodes.keys(), updates=batch,
        )
    return project_progress(sqlite_url, user_id, bound)
