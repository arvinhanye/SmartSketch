"""I05：下一步推荐查询（specs/learning-path.md §1、§4；ADR-014 修订 1 决定 7；ADR-017 决定 4；ADR-069）。

一次请求只绑定一个已提交版本，全程不再读发布指针：

1. ``resolve_published``（G07）在请求开始时解析一次当前发布版；从未发布 → 404 ``GRAPH_NOT_PUBLISHED``，
   不运行推荐函数。
2. 图取自**该版本的已提交快照**（SQLite ``graph_versions.snapshot_json``，摘要复核），而非 Neo4j 副本或草稿：
   节点及其 ``importance``/``difficulty``/``chapter_id``/``name``、``PREREQUISITE`` 边、章节树。快照不可变
   （G02 触发器），与 I02 投影所用谱系同源，所以图、进度投影、理由与响应版本号必然一致（LP-10）。
3. ``project_progress``（I02）在同一绑定版本上投影出 ``M ⊆ V``。
4. I03 ``build_prerequisite_graph`` 全图校验 → ``eligible_set`` → I04 ``rank_candidates`` 对**全部**候选
   排序，之后才截断到 ``limit``；``total_eligible`` 为截断前总数。排序键 ``(-score, chapter_rank, kp_id)``
   是全序，因此截断稳定：``limit=k`` 的结果恰是 ``limit=50`` 结果的前 ``k`` 条。
5. 候选为空只可能是 ``M = V``（DAG 至少有一个入度 0 的未掌握点）→ ``state = all_mastered``。

已提交版完整性故障——快照缺失/摘要不符/不可解析/他课、``V = ∅``、环、自环、悬空端点、重复 ID、
章节树损坏、非法数值、谱系违反修订 3 决定 16——一律抛出，由路由映射为 500 ``INTERNAL_ERROR``，
``details`` 只含 ``request_id``；环路与节点 ID 只进服务端日志（§1）。I03 的 ``ProgressOutsideGraphError``
在此路径上若仍被抛出视为缺陷，同样按 500 处理（LP-12）。
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Final, Literal

from app.repositories import versions as versions_repository
from app.services.learning.eligible import PrerequisiteGraph, build_prerequisite_graph, eligible_set
from app.services.learning.progress import project_progress
from app.services.learning.ranking import (
    Chapter,
    KnowledgePointAttributes,
    RankedCandidate,
    RecommendWeights,
    rank_candidates,
)
from app.services.versions.resolver import PublishedVersion, VersionIntegrityError, resolve_published
from app.services.versions.snapshot import SnapshotFormatError, digest_of, load_snapshot

__all__ = [
    "DEFAULT_LIMIT",
    "MAX_LIMIT",
    "RecommendResult",
    "VersionGraph",
    "clear_cache",
    "get_recommendations",
    "load_version_graph",
]

DEFAULT_LIMIT: Final = 10
MAX_LIMIT: Final = 50
_CACHE_SIZE: Final = 64


@dataclass(frozen=True)
class VersionGraph:
    """一个已提交版本中参与推荐的全部数据；已通过 I03 全图校验。"""

    graph: PrerequisiteGraph
    attributes: tuple[KnowledgePointAttributes, ...]
    chapters: tuple[Chapter, ...]


@dataclass(frozen=True)
class RecommendResult:
    """契约 ``RecommendResponse`` 的领域形态。"""

    graph_version: int
    total_eligible: int
    recommendations: tuple[RankedCandidate, ...]

    @property
    def state(self) -> Literal["recommendations", "all_mastered"]:
        return "all_mastered" if self.total_eligible == 0 else "recommendations"

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "graph_version": self.graph_version,
            "total_eligible": self.total_eligible,
            "recommendations": [_item(candidate, self.graph_version) for candidate in self.recommendations],
        }


def _item(candidate: RankedCandidate, graph_version: int) -> dict[str, Any]:
    facts = candidate.reason_facts
    return {
        "kp_id": candidate.kp_id,
        "name": candidate.name,
        "graph_version": graph_version,
        "score": candidate.score,
        "factors": candidate.factors.as_dict(),
        "weighted": candidate.weighted.as_dict(),
        "unlock_count": candidate.unlock_count,
        "reason": candidate.reason,
        "reason_facts": {
            "primary_factor": facts.primary_factor,
            "chapter_id": facts.chapter_id,
            "chapter_name": facts.chapter_name,
            "chapter_rank": facts.chapter_rank,
            "importance": facts.importance,
            "centrality": facts.centrality,
            "difficulty": facts.difficulty,
        },
    }


# ---------------------------------------------------------------- 绑定版本的图（按 version_id 缓存）


_lock = threading.Lock()
_graphs: OrderedDict[tuple[str, str], VersionGraph] = OrderedDict()


def clear_cache() -> None:
    with _lock:
        _graphs.clear()


def load_version_graph(sqlite_url: str, bound: PublishedVersion) -> VersionGraph:
    """读绑定版本的已提交快照并做全图校验；只缓存校验通过的结果（损坏的快照每次都重新报错）。"""
    key = (sqlite_url, bound.version_id)
    with _lock:
        cached = _graphs.get(key)
        if cached is not None:
            _graphs.move_to_end(key)
            return cached
    raw = versions_repository.read_snapshot(sqlite_url, bound.version_id)
    if raw is None:
        raise VersionIntegrityError(f"committed version {bound.version_id} has no snapshot")
    record = versions_repository.get_version(sqlite_url, bound.version_id)
    if record is None or record.state != "committed" or digest_of(raw) != record.digest:
        raise VersionIntegrityError(f"snapshot digest mismatch for version {bound.version_id}")
    try:
        data = load_snapshot(raw).data
    except SnapshotFormatError as error:
        raise VersionIntegrityError(f"snapshot of version {bound.version_id} is malformed") from error
    if data["course_id"] != bound.course_id:
        raise VersionIntegrityError(f"snapshot of version {bound.version_id} belongs to another course")

    nodes = data["nodes"]
    graph = build_prerequisite_graph(
        (node["kp_id"] for node in nodes),
        ((edge["from_id"], edge["to_id"]) for edge in data["edges"] if edge["type"] == "PREREQUISITE"),
    )
    loaded = VersionGraph(
        graph=graph,
        attributes=tuple(
            KnowledgePointAttributes(kp_id=node["kp_id"], name=node["name"], chapter_id=node["chapter_id"],
                                     importance=node["importance"], difficulty=node["difficulty"])
            for node in nodes
        ),
        chapters=tuple(
            Chapter(chapter_id=chapter["chapter_id"], parent_id=chapter["parent_id"], order=chapter["order"],
                    name=chapter["title"])
            for chapter in data["chapters"]
        ),
    )
    with _lock:
        _graphs[key] = loaded
        while len(_graphs) > _CACHE_SIZE:
            _graphs.popitem(last=False)
    return loaded


# ---------------------------------------------------------------- 查询


def get_recommendations(
    sqlite_url: str, user_id: str, course_id: str, weights: RecommendWeights, limit: int = DEFAULT_LIMIT
) -> RecommendResult:
    """``GET /recommend``：绑定一次发布版，在该版本上投影、校验、全量排序后截断。"""
    if type(limit) is not int or not 1 <= limit <= MAX_LIMIT:
        raise ValueError(f"limit must be an integer in 1..{MAX_LIMIT}")
    bound = resolve_published(sqlite_url, course_id)
    version_graph = load_version_graph(sqlite_url, bound)
    view = project_progress(sqlite_url, user_id, bound)
    if frozenset(entry.kp_id for entry in view.entries) != version_graph.graph.nodes:
        raise VersionIntegrityError(f"progress projection of version {bound.version_id} disagrees with its graph")
    mastered = view.mastered
    candidates = eligible_set(version_graph.graph, mastered)
    ranked = rank_candidates(version_graph.graph, candidates, mastered, version_graph.attributes,
                             version_graph.chapters, weights)
    return RecommendResult(bound.version, len(ranked), ranked[:limit])
