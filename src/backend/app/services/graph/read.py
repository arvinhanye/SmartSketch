"""F07：图谱与知识点详情的读取服务（契约 ``getGraph`` / ``getKnowledgePoint``）。

读入口（契约 ``getGraph`` 的 ``version`` 参数说明）：

- 教师、不带 ``version``：读草稿。V 在请求开始时从 SQLite 读一次（§8.4），只返回可见内容。
- 学生（或教师带 ``version``）：读已发布版本。课程未发布 → 404 ``GRAPH_NOT_PUBLISHED``（学生由 C03 依赖
  提前拒绝）；``version`` 不是当前发布版本号 → 404 ``NOT_FOUND``（历史版本表归 G02）。
- **空图与未发布不同**：教师的空草稿、已发布的空版本都返回 200 与空的 ``nodes``/``edges``；
  只有「没有可读的发布版本」才是 ``GRAPH_NOT_PUBLISHED``。

来源定位（ADR-003）：每条 ``SourceRef`` 都从 SQLite 按本课程读出的块（D10）取定位，``page`` 与
``section_path`` 至少一个；知识点来源另带证据区间对应的原文片段。无法定位的来源（块已不在本课程）
被丢弃并记日志，不返回无法回到原文的引用。

``level`` 在读取时按返回图中有效（非 ``rejected``）``PREREQUISITE`` 边的最长前置路径计算。
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict, deque
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError

from app.repositories.chunks import StoredChunk, get_chunks
from app.repositories.graph_read import GraphReader, NodeEvidence
from app.repositories.neo4j import GraphScope
from app.repositories.sqlite import connect
from app.repositories.tasks import read_effective_task_ids
from app.schemas.contracts import (
    Chapter,
    GraphExchange,
    GraphStats,
    KnowledgePoint,
    KnowledgePointDetail,
    KnowledgePointRef,
    Relation,
    SourceRef,
)
from app.services.access import CourseAccess, graph_not_published, not_found
from app.services.ai.entities import _layout, _sources_for  # 块文本拼接规则与抽取时相同

__all__ = ["GraphFilter", "ReadTarget", "SourceUnavailable", "read_graph", "read_knowledge_point", "resolve_target"]

logger = logging.getLogger(__name__)

DRAFT = "draft"
FORMAT_VERSION = "1.0"


class SourceUnavailable(Exception):
    """知识点没有任何可定位的来源；契约 ``KnowledgePointDetail.source_refs`` 要求至少一条。"""

    code = "INTERNAL_ERROR"


@dataclass(frozen=True)
class ReadTarget:
    scope: GraphScope
    reader: str  # teacher | student
    graph_version: int | None


@dataclass(frozen=True)
class GraphFilter:
    chapter_id: str | None = None
    type: str | None = None
    relation_types: tuple[str, ...] | None = None


def resolve_target(sqlite_url: str, access: CourseAccess, version: int | None) -> ReadTarget:
    """按角色与 ``version`` 决定读草稿还是已发布版本。"""
    course = access.course
    role = access.member.role
    if role == "teacher" and version is None:
        with connect(sqlite_url) as database:
            v = read_effective_task_ids(database, course.id)
        return ReadTarget(GraphScope(course.id, DRAFT, effective_task_ids=v), "teacher", None)
    if course.published_version is None or course.published_version_id is None:
        raise graph_not_published()
    if version is not None and version != course.published_version:
        raise not_found()
    return ReadTarget(GraphScope(course.id, course.published_version_id), role, course.published_version)


# ---------------------------------------------------------------- 来源定位


def _locate(chunk: StoredChunk, start: int | None, end: int | None) -> dict[str, int | str]:
    """证据区间（块文本内的偏移）落在哪个解析块，就取哪个块的定位；无区间时取块的第一个出处。

    块文本的拼接方式与 E05 抽取时相同，复用其区间重建；重建失败时退回第一个出处。
    """
    sources = chunk.sources
    if isinstance(start, int) and isinstance(end, int) and start < end:
        sources = _sources_for(_layout(chunk.sources, chunk.text), chunk.sources, start, end)
    for source in sources:
        fields = source.locator.to_source_fields()
        if fields:
            return fields
    return {}


def _source_ref(chunk: StoredChunk | None, document_id: str | None, start: int | None,
                end: int | None) -> SourceRef | None:
    if chunk is None:
        return None
    fields: dict[str, Any] = {"chunk_id": chunk.chunk_id, "document_id": document_id or chunk.material_id,
                              **_locate(chunk, start, end)}
    if "page" not in fields and "section_path" not in fields:
        return None
    if isinstance(start, int) and isinstance(end, int) and 0 <= start < end <= len(chunk.text):
        text = chunk.text[start:end]
        if text.strip():
            fields["text"] = text
    return SourceRef.model_validate(fields)


def _chunks(sqlite_url: str, course_id: str, chunk_ids: Iterable[str]) -> dict[str, StoredChunk]:
    return {c.chunk_id: c for c in get_chunks(sqlite_url, course_id=course_id, chunk_ids=list(chunk_ids))}


def _pair(raw: object) -> tuple[str | None, str] | None:
    try:
        contributor, chunk_id = json.loads(raw) if isinstance(raw, str) else (None, None)
    except (ValueError, TypeError):
        return None
    if not isinstance(chunk_id, str) or not (contributor is None or isinstance(contributor, str)):
        return None
    return contributor, chunk_id


def _relation_chunk_ids(edge: Mapping[str, Any], scope: GraphScope) -> list[str]:
    visible = set(scope.effective_task_ids or ())
    ids = []
    for raw in edge["p"].get("source_pairs") or []:
        pair = _pair(raw)
        if pair is None:
            continue
        contributor, chunk_id = pair
        if scope.version_id != DRAFT or contributor is None or contributor in visible:
            ids.append(chunk_id)
    return list(dict.fromkeys(ids))


# ---------------------------------------------------------------- 组装


def _levels(node_ids: Iterable[str], edges: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    """最长前置路径长度；只用有效 ``PREREQUISITE`` 边。草稿违反 DAG 时环上节点保持 0。"""
    nodes = set(node_ids)
    succ: dict[str, list[str]] = defaultdict(list)
    indeg = {n: 0 for n in nodes}
    for e in edges:
        if e["type"] == "PREREQUISITE" and e["p"].get("status") != "rejected" \
                and e["from_id"] in nodes and e["to_id"] in nodes:
            succ[e["from_id"]].append(e["to_id"])
            indeg[e["to_id"]] += 1
    level = {n: 0 for n in nodes}
    queue = deque(sorted(n for n, d in indeg.items() if d == 0))
    while queue:
        n = queue.popleft()
        for m in succ[n]:
            level[m] = max(level[m], level[n] + 1)
            indeg[m] -= 1
            if indeg[m] == 0:
                queue.append(m)
    return level


def _node(course_id: str, p: Mapping[str, Any], level: int) -> KnowledgePoint | None:
    fields = {
        "id": p.get("kp_id"),
        "course_id": course_id,
        "chapter_id": p.get("chapter_id"),
        "name": p.get("name"),
        "aliases": list(p.get("aliases") or []),
        "type": p.get("type"),
        "definition": p.get("definition") or "",
        "importance": p.get("importance"),
        "difficulty": p.get("difficulty"),
        "level": level,
        "confidence": p.get("confidence", 1.0),
        "status": p.get("status"),
        "source": p.get("source") or "manual",
        "locked": bool(p.get("locked", False)),
        "revision": max(1, int(p.get("revision") or 1)),
    }
    try:
        return KnowledgePoint.model_validate({k: v for k, v in fields.items() if v is not None})
    except ValidationError:
        logger.warning("skipping malformed knowledge point in course graph")
        return None


def _relation(course_id: str, edge: Mapping[str, Any], refs: list[SourceRef]) -> Relation | None:
    p = edge["p"]
    fields: dict[str, Any] = {
        "id": p.get("rel_id"),
        "course_id": course_id,
        "type": edge["type"],
        "from_id": edge["from_id"],
        "to_id": edge["to_id"],
        "confidence": p.get("confidence", 1.0),
        "status": p.get("status"),
        "source": p.get("source") or "manual",
        "source_refs": refs,
    }
    if p.get("downgraded_from_type") == "PREREQUISITE" and p.get("downgrade_cycle") \
            and fields["status"] == "low_confidence" and fields["source"] == "ai":
        fields["downgraded_from_type"] = "PREREQUISITE"
        fields["downgrade_cycle"] = list(p["downgrade_cycle"])
    try:
        return Relation.model_validate(fields)
    except ValidationError:
        logger.warning("skipping malformed relation in course graph")
        return None


def _stats(nodes: Sequence[KnowledgePoint], edges: Sequence[Relation]) -> GraphStats:
    by_type: dict[str, int] = defaultdict(int)
    touched: set[str] = set()
    for edge in edges:
        by_type[edge.root.type if isinstance(edge.root.type, str) else edge.root.type.value] += 1
        touched.update((edge.root.from_id, edge.root.to_id))
    return GraphStats(node_count=len(nodes), edge_count=len(edges), edges_by_type=dict(by_type),
                      isolated_count=sum(1 for n in nodes if n.id not in touched))


def _type_value(value: object) -> object:
    return getattr(value, "value", value)


def read_graph(reader: GraphReader, sqlite_url: str, target: ReadTarget, graph_filter: GraphFilter,
               *, now: datetime | None = None) -> GraphExchange:
    scope = target.scope
    raw_nodes = reader.nodes(scope, target.reader)  # type: ignore[arg-type]
    raw_edges = reader.edges(scope, target.reader)  # type: ignore[arg-type]
    levels = _levels((p.get("kp_id") for p in raw_nodes), raw_edges)

    nodes = []
    for p in raw_nodes:
        if graph_filter.chapter_id is not None and p.get("chapter_id") != graph_filter.chapter_id:
            continue
        if graph_filter.type is not None and p.get("type") != graph_filter.type:
            continue
        node = _node(scope.course_id, p, levels.get(p.get("kp_id"), 0))
        if node is not None:
            nodes.append(node)
    kept = {n.id for n in nodes}

    wanted = set(graph_filter.relation_types) if graph_filter.relation_types else None
    raw_edges = [e for e in raw_edges if e["from_id"] in kept and e["to_id"] in kept
                 and (wanted is None or e["type"] in wanted)]
    chunk_ids = {cid for e in raw_edges for cid in _relation_chunk_ids(e, scope)}
    chunks = _chunks(sqlite_url, scope.course_id, chunk_ids)
    edges = []
    for e in raw_edges:
        refs = [ref for cid in _relation_chunk_ids(e, scope)
                if (ref := _source_ref(chunks.get(cid), None, None, None)) is not None]
        relation = _relation(scope.course_id, e, refs)
        if relation is not None:
            edges.append(relation)

    chapters = []
    for p in reader.chapters(scope, target.reader):  # type: ignore[arg-type]
        try:
            chapters.append(Chapter.model_validate({"id": p.get("chapter_id"), "title": p.get("title"),
                                                    "order": p.get("order", 0)}))
        except ValidationError:
            logger.warning("skipping malformed chapter in course graph")

    return GraphExchange(
        format_version=FORMAT_VERSION,
        course_id=scope.course_id,
        graph_version=target.graph_version,
        generated_at=now or datetime.now(timezone.utc),
        chapters=chapters,
        nodes=nodes,
        edges=edges,
        stats=_stats(nodes, edges),
    )


def _evidence_refs(sqlite_url: str, course_id: str, evidence: Sequence[NodeEvidence]) -> list[SourceRef]:
    chunks = _chunks(sqlite_url, course_id, (e.chunk_id for e in evidence))
    refs: list[SourceRef] = []
    seen: set[tuple[object, ...]] = set()
    for e in evidence:
        ref = _source_ref(chunks.get(e.chunk_id), e.document_id, e.evidence_start, e.evidence_end)
        if ref is None:
            logger.warning("dropping a knowledge point source that cannot be located")
            continue
        key = tuple(sorted(ref.root.model_dump(exclude_none=True).items()))
        if key not in seen:
            seen.add(key)
            refs.append(ref)
    return refs


def read_knowledge_point(reader: GraphReader, sqlite_url: str, target: ReadTarget, kp_id: str) -> KnowledgePointDetail:
    """知识点详情：至少一条可定位来源，另给直接前置、直接后继与相关知识点。"""
    scope = target.scope
    role = target.reader
    found = reader.nodes(scope, role, [kp_id])  # type: ignore[arg-type]
    if not found:
        raise not_found()
    edges = [e for e in reader.edges(scope, role, [kp_id])  # type: ignore[arg-type]
             if e["p"].get("status") != "rejected"]
    others = {e["to_id"] if e["from_id"] == kp_id else e["from_id"] for e in edges}
    names = {p.get("kp_id"): p for p in reader.nodes(scope, role, sorted(others))} if others else {}  # type: ignore[arg-type]

    def ref(other: str) -> KnowledgePointRef | None:
        p = names.get(other)
        if p is None or not p.get("name"):
            return None
        return KnowledgePointRef.model_validate({k: v for k, v in
                                                 {"id": other, "name": p["name"], "type": p.get("type")}.items()
                                                 if v is not None})

    def pick(kind: str, direction: str) -> list[KnowledgePointRef]:
        out = []
        for e in edges:
            if e["type"] != kind:
                continue
            if direction == "in" and e["to_id"] == kp_id:
                other = e["from_id"]
            elif direction == "out" and e["from_id"] == kp_id:
                other = e["to_id"]
            elif direction == "any":
                other = e["to_id"] if e["from_id"] == kp_id else e["from_id"]
            else:
                continue
            r = ref(other)
            if r is not None and r.id not in {x.id for x in out}:
                out.append(r)
        return out

    refs = _evidence_refs(sqlite_url, scope.course_id, reader.evidence(scope, role, [kp_id]))  # type: ignore[arg-type]
    if not refs:
        raise SourceUnavailable()
    level = _levels((p.get("kp_id") for p in reader.nodes(scope, role)),  # type: ignore[arg-type]
                    reader.edges(scope, role)).get(kp_id, 0)  # type: ignore[arg-type]
    node = _node(scope.course_id, found[0], level)
    if node is None:
        raise not_found()
    return KnowledgePointDetail.model_validate({
        **node.model_dump(exclude_none=True),
        "source_refs": [r.model_dump(exclude_none=True) for r in refs],
        "prerequisites": [r.model_dump(exclude_none=True) for r in pick("PREREQUISITE", "in")],
        "successors": [r.model_dump(exclude_none=True) for r in pick("PREREQUISITE", "out")],
        "related": [r.model_dump(exclude_none=True) for r in pick("RELATED_TO", "any")],
    })
