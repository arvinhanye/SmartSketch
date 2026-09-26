"""J02：在绑定的已发布版本副本上做图结构检索（specs/grounded-qa.md 处理链路「图谱结构检索」；ADR-050）。

输入是 G07 绑定版本的作用域与修订列表、术语（改写后的问题或关键词）和可选的种子知识点（Q8 H4
``kp_id``）；输出是一张**有界子图**：

1. **种子**：版本副本中名称或别名（去首尾空白、小写）与某个术语相等、包含在某个术语中，或包含
   某个长度 ≥ 2 的术语的知识点；显式给出且属于本版本的 ``seed_kp_ids`` 优先，不在本版本的忽略并记
   日志（H4）。排序：显式种子 > 相等 > 名称在术语中 > 术语在名称中；同级按匹配名称长者优先，再按
   ``kp_id``。至多 ``max_seeds`` 个。
2. **扩展**：从种子逐跳沿 ``relation_types``（缺省为规格列出的前置 / 包含 / 相关，不含
   ``EXAMPLE_OF``）无向扩展，至多 ``max_hops`` 跳，总点数至多 ``max_nodes``；同一跳内按 ``kp_id``
   取前者。
3. **结果**：节点（种子在前，其余按跳数、``kp_id``）、两端都在结果中的四类关系、节点的
   ``EVIDENCED_BY`` 文本块（只保留 ``revision_id`` 属于修订列表的，至多 ``max_evidence`` 条）。
   任一上限截掉了内容时 ``truncated`` 为真。无匹配返回空子图。

只接受已发布版本作用域：版本副本按 ``(course_id, version_id)`` 隔离，草稿、其他版本与他课的内容
不可达。子图只作无编号结构上下文，证据块能否进入允许引用集合由 J04 / J06 按 Q3.1 判定。
"""

from __future__ import annotations

import logging
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from typing import Any, Final

from app.repositories.neo4j import GraphScope, GraphScopeError, Neo4jRepository

__all__ = [
    "DEFAULT_MAX_EVIDENCE",
    "DEFAULT_MAX_HOPS",
    "DEFAULT_MAX_NODES",
    "DEFAULT_MAX_SEEDS",
    "DEFAULT_RELATION_TYPES",
    "MAX_HOPS_LIMIT",
    "MAX_NODES_LIMIT",
    "GraphEvidence",
    "GraphSubgraph",
    "SubgraphEdge",
    "SubgraphNode",
    "search_subgraph",
]

logger = logging.getLogger(__name__)

DRAFT: Final = "draft"
RELATION_TYPES: Final = ("CONTAINS", "PREREQUISITE", "RELATED_TO", "EXAMPLE_OF")
DEFAULT_RELATION_TYPES: Final = ("CONTAINS", "PREREQUISITE", "RELATED_TO")
# 以下为占位值（ADR-050），由 J04 按上下文预算与评测调整；硬上限防止调用方放开。
DEFAULT_MAX_HOPS: Final = 2
DEFAULT_MAX_NODES: Final = 30
DEFAULT_MAX_SEEDS: Final = 10
DEFAULT_MAX_EVIDENCE: Final = 60
MAX_HOPS_LIMIT: Final = 3
MAX_NODES_LIMIT: Final = 200
MAX_EVIDENCE_LIMIT: Final = 500


@dataclass(frozen=True)
class SubgraphNode:
    """子图中的一个知识点。``hops`` 为到最近种子的跳数；``matched`` 为命中的名称或别名（显式种子与扩展点为 None）。"""

    kp_id: str
    name: str
    aliases: tuple[str, ...]
    type: str
    definition: str
    chapter_id: str | None
    hops: int
    matched: str | None


@dataclass(frozen=True)
class SubgraphEdge:
    rel_id: str
    type: str
    from_id: str
    to_id: str


@dataclass(frozen=True)
class GraphEvidence:
    """子图节点的来源文本块（候选集合 H 的来源之一，Q1）。"""

    kp_id: str
    chunk_id: str
    revision_id: str
    document_id: str | None


@dataclass(frozen=True)
class GraphSubgraph:
    nodes: tuple[SubgraphNode, ...]
    edges: tuple[SubgraphEdge, ...]
    evidence: tuple[GraphEvidence, ...]
    seed_kp_ids: tuple[str, ...]
    truncated: bool

    @property
    def empty(self) -> bool:
        return not self.nodes

    @property
    def kp_ids(self) -> tuple[str, ...]:
        return tuple(n.kp_id for n in self.nodes)


EMPTY: Final = GraphSubgraph((), (), (), (), False)

# rank：0 显式种子，1 相等，2 名称在术语中，3 术语（≥ 2 字）在名称中。
_SEEDS = """
MATCH (k:KnowledgePoint {course_id: $course_id, version_id: $version_id})
UNWIND [k.name] + coalesce(k.aliases, []) AS label
WITH k, label, toLower(trim(label)) AS key
WHERE key <> ''
WITH k, label, CASE
    WHEN k.kp_id IN $seed_ids THEN 0
    WHEN key IN $terms THEN 1
    WHEN any(t IN $terms WHERE t CONTAINS key) THEN 2
    WHEN any(t IN $terms WHERE size(t) >= 2 AND key CONTAINS t) THEN 3
  END AS rank
WITH k, label, rank
WHERE rank IS NOT NULL
WITH k, label, rank
ORDER BY rank, size(label) DESC, label
WITH k, collect({rank: rank, label: label})[0] AS best
WITH k.kp_id AS kp_id, best.rank AS rank, best.label AS label,
     CASE WHEN best.rank = 0 THEN 0 ELSE size(best.label) END AS len
RETURN kp_id, rank, CASE WHEN rank = 0 THEN null ELSE label END AS matched
ORDER BY rank, len DESC, kp_id
LIMIT $limit
"""

_HOP = """
MATCH (a:KnowledgePoint {course_id: $course_id, version_id: $version_id})-[r]-
      (b:KnowledgePoint {course_id: $course_id, version_id: $version_id})
WHERE a.kp_id IN $frontier AND type(r) IN $types
  AND r.course_id = $course_id AND r.version_id = $version_id
  AND NOT b.kp_id IN $visited
RETURN DISTINCT b.kp_id AS kp_id
ORDER BY kp_id
LIMIT $limit
"""

_NODES = """
MATCH (k:KnowledgePoint {course_id: $course_id, version_id: $version_id})
WHERE k.kp_id IN $kp_ids
RETURN k.kp_id AS kp_id, k.name AS name, coalesce(k.aliases, []) AS aliases, k.type AS type,
       k.definition AS definition, k.chapter_id AS chapter_id
"""

_EDGES = """
MATCH (a:KnowledgePoint {course_id: $course_id, version_id: $version_id})-[r]->
      (b:KnowledgePoint {course_id: $course_id, version_id: $version_id})
WHERE a.kp_id IN $kp_ids AND b.kp_id IN $kp_ids AND type(r) IN $all_types
  AND r.course_id = $course_id AND r.version_id = $version_id
RETURN r.rel_id AS rel_id, type(r) AS type, a.kp_id AS from_id, b.kp_id AS to_id
ORDER BY rel_id, type
"""

_EVIDENCE = """
MATCH (k:KnowledgePoint {course_id: $course_id, version_id: $version_id})-[:EVIDENCED_BY]->
      (c:Chunk {course_id: $course_id})
WHERE k.kp_id IN $kp_ids AND c.revision_id IN $revision_ids
RETURN DISTINCT k.kp_id AS kp_id, c.chunk_id AS chunk_id, c.revision_id AS revision_id,
       c.document_id AS document_id
"""


def _bounded_int(name: str, value: object, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{name} must be an integer in [{low}, {high}]")
    return value


def _strings(name: str, values: object) -> list[str]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Iterable):
        raise TypeError(f"{name} must be a collection of strings")
    items = list(values)
    if any(not isinstance(v, str) for v in items):
        raise TypeError(f"{name} must contain strings only")
    return items


def _relation_types(values: object) -> list[str]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Iterable):
        raise ValueError("relation_types must be a collection of relation types")
    types = sorted(set(values))
    if not types or any(t not in RELATION_TYPES for t in types):
        raise ValueError(f"relation_types must be a nonempty subset of {RELATION_TYPES}")
    return types


def _normalize(term: str) -> str:
    return " ".join(term.split()).lower()


def search_subgraph(
    repo: Neo4jRepository,
    scope: GraphScope,
    revision_ids: Collection[str],
    terms: Iterable[str],
    *,
    seed_kp_ids: Iterable[str] = (),
    max_hops: int = DEFAULT_MAX_HOPS,
    max_nodes: int = DEFAULT_MAX_NODES,
    max_seeds: int | None = None,
    max_evidence: int = DEFAULT_MAX_EVIDENCE,
    relation_types: Collection[str] = DEFAULT_RELATION_TYPES,
) -> GraphSubgraph:
    """返回 ``scope`` 所指已发布版本中与 ``terms`` / ``seed_kp_ids`` 相关的有界子图。

    ``scope`` 是 G07 绑定的已发布版本（``PublishedVersion.graph_scope()``），``revision_ids`` 是它的
    修订列表，只用于过滤证据块。``max_seeds`` 缺省为 ``min(DEFAULT_MAX_SEEDS, max_nodes)``。
    """
    max_hops = _bounded_int("max_hops", max_hops, 0, MAX_HOPS_LIMIT)
    max_nodes = _bounded_int("max_nodes", max_nodes, 1, MAX_NODES_LIMIT)
    max_seeds = min(DEFAULT_MAX_SEEDS, max_nodes) if max_seeds is None else \
        _bounded_int("max_seeds", max_seeds, 1, max_nodes)
    max_evidence = _bounded_int("max_evidence", max_evidence, 0, MAX_EVIDENCE_LIMIT)
    types = _relation_types(relation_types)
    if not isinstance(scope, GraphScope) or scope.version_id == DRAFT:
        raise GraphScopeError("graph search requires a published version scope")
    keys = sorted({k for k in (_normalize(t) for t in _strings("terms", terms)) if k})
    seeds = sorted({s for s in _strings("seed_kp_ids", seed_kp_ids) if s})
    revisions = sorted({r for r in revision_ids if isinstance(r, str) and r})
    if not keys and not seeds:
        return EMPTY

    def read(query: str, **parameters: Any) -> list[dict[str, Any]]:
        return repo.read(query, scope, reader="student", parameters=parameters)

    rows = read(_SEEDS, terms=keys, seed_ids=seeds, limit=max_seeds + 1)
    truncated = len(rows) > max_seeds
    rows = rows[:max_seeds]
    explicit = sum(1 for r in rows if r["rank"] == 0)
    if explicit < len(seeds) and explicit < max_seeds:
        logger.info("graph search for course %s ignored %d seed kp_ids outside version %s",
                    scope.course_id, len(seeds) - explicit, scope.version_id)
    if not rows:
        return GraphSubgraph((), (), (), (), truncated)

    order = [str(r["kp_id"]) for r in rows]
    matched = {str(r["kp_id"]): r["matched"] for r in rows}
    distance = dict.fromkeys(order, 0)
    frontier = list(order)
    for hop in range(1, max_hops + 1):
        if not frontier:
            break
        remaining = max_nodes - len(order)
        found = [str(r["kp_id"]) for r in read(_HOP, frontier=frontier, visited=order, types=types,
                                                 limit=remaining + 1)]
        if len(found) > remaining:
            truncated = True
            found = found[:remaining]
        for kp_id in found:
            distance[kp_id] = hop
        order.extend(found)
        frontier = found

    details = {str(r["kp_id"]): r for r in read(_NODES, kp_ids=order)}
    nodes = tuple(
        SubgraphNode(kp_id, str(d["name"]), tuple(d["aliases"]), str(d["type"]), str(d["definition"]),
                     d["chapter_id"], distance[kp_id], matched.get(kp_id))
        for kp_id in order if (d := details.get(kp_id)) is not None
    )
    edges = tuple(SubgraphEdge(str(r["rel_id"]), str(r["type"]), str(r["from_id"]), str(r["to_id"]))
                  for r in read(_EDGES, kp_ids=order, all_types=list(RELATION_TYPES)))
    evidence: list[GraphEvidence] = []
    if revisions and max_evidence:
        position = {kp_id: i for i, kp_id in enumerate(order)}
        found_evidence = sorted(read(_EVIDENCE, kp_ids=order, revision_ids=revisions),
                                key=lambda r: (position[r["kp_id"]], r["chunk_id"]))
        if len(found_evidence) > max_evidence:
            truncated = True
        evidence = [GraphEvidence(str(r["kp_id"]), str(r["chunk_id"]), str(r["revision_id"]), r["document_id"])
                    for r in found_evidence[:max_evidence]]
    seeds_found = tuple(r for r in order if distance[r] == 0)
    return GraphSubgraph(nodes, edges, tuple(evidence), seeds_found, truncated)
