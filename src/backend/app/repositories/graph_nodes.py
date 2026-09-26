"""F04：草稿知识点与来源关联的批量写入（specs/task-processing.md §8.4「贡献记录」「草稿可见性」；
specs/teacher-review-publish.md「节点加锁」；ADR-011 修订 1、ADR-024）。

``write_draft_nodes`` 把一个任务的知识点候选写进课程草稿（``version_id = "draft"``）：

1. **先校验，后写库**：每个节点逐条校验，不合格的记入 ``rejected`` 并跳过，不影响其他节点——
   字段非法（类型不在五类闭集、名称/定义空白、置信度不在 [0, 1]、状态不是 ``draft``/``low_confidence``）、
   没有来源、kp_id 重复（保留首个）、来源块不在调用方给出的本课程块中（跨课程来源）、来源与块不符
   （资料/修订不一致、证据区间越界或为空）。
2. **分批写入**：每批一个 Neo4j 托管事务（F02 ``Neo4jRepository.write``）。节点按
   ``(course_id, "draft", kp_id)`` ``MERGE``；新建时 ``source = ai``、``locked = false``、
   ``contrib_manual = false``、``revision = 1``、``level = 0``。本任务 ID 并入 ``contrib_tasks``（不重复）；
   内容有变化才把节点 ``revision`` 加 1，因此重试不改变任何数据。
3. **来源**：来源块以 ``(course_id, chunk_id)`` ``MERGE`` 为共享 ``Chunk`` 节点（只在新建时写资料与修订），
   知识点到块的 ``EVIDENCED_BY`` 关系带 ``task_id`` 与证据半开区间，按这四个值 ``MERGE``，重试不重复。
4. **加锁节点完全不动**（ArvinHan 2026-09-26）：已加锁的草稿节点不改内容、不并入贡献、不加来源，
   只记入 ``skipped_locked``。
5. 某批写库失败（F02 已脱敏的 ``RepositoryError``）时，该批节点记为 ``write_failed``，其余批次照常写入；
   是否据此整体失败由调用方（F13 ``persisting``）决定。

``created`` 列出写入前对教师不可见（不存在，或只有不在有效任务集合 V 中的任务贡献）的节点；
其余写入的节点是对已可见节点的更新。本模块不决定节点状态与置信度阈值（D-08），也不做融合映射。
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final

from app.repositories.chunks import StoredChunk
from app.repositories.neo4j import GraphScope, GraphScopeError, Neo4jRepository, RepositoryError, ScopedTransaction

__all__ = [
    "DEFAULT_BATCH_SIZE",
    "DRAFT_VERSION",
    "DraftNode",
    "NodeSource",
    "NodeWriteResult",
    "RejectReason",
    "derive_kp_id",
    "write_draft_nodes",
    "write_draft_nodes_in",
]

logger = logging.getLogger(__name__)

DRAFT_VERSION: Final = "draft"
DEFAULT_BATCH_SIZE: Final = 200
NODE_TYPES: Final = frozenset({"concept", "theorem", "formula", "method", "example"})
#: 自动流程可写的状态；``approved``/``rejected`` 只由教师审核产生。
AUTO_STATUSES: Final = frozenset({"draft", "low_confidence"})


class RejectReason(StrEnum):
    INVALID_NODE = "invalid_node"
    NO_SOURCE = "no_source"
    DUPLICATE_KP_ID = "duplicate_kp_id"
    SOURCE_OUTSIDE_COURSE = "source_outside_course"
    INVALID_SOURCE = "invalid_source"
    WRITE_FAILED = "write_failed"


@dataclass(frozen=True)
class NodeSource:
    """知识点的一条来源：块与证据在块文本中的半开区间。"""

    chunk_id: str
    document_id: str
    revision_id: str
    evidence_start: int
    evidence_end: int


@dataclass(frozen=True)
class DraftNode:
    kp_id: str
    name: str = field(repr=False)
    type: str
    definition: str = field(repr=False)
    confidence: float
    status: str
    aliases: tuple[str, ...] = field(default=(), repr=False)
    sources: tuple[NodeSource, ...] = ()


@dataclass(frozen=True)
class NodeWriteResult:
    written: tuple[str, ...]
    created: tuple[str, ...]
    skipped_locked: tuple[str, ...]
    rejected: tuple[tuple[str, RejectReason], ...]


def derive_kp_id(course_id: str, task_id: str, candidate_key: str) -> str:
    """§8.4：新节点 ID 由「课程 + 任务 + 候选键」确定。"""
    for name, value in (("course_id", course_id), ("task_id", task_id), ("candidate_key", candidate_key)):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")
    digest = hashlib.sha256(json.dumps([course_id, task_id, candidate_key], ensure_ascii=False).encode("utf-8"))
    return "kp_" + digest.hexdigest()[:32]


# ---------------------------------------------------------------- 校验


def _text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _node_valid(node: DraftNode) -> bool:
    return (
        _text(node.kp_id)
        and _text(node.name)
        and node.type in NODE_TYPES
        and _text(node.definition)
        and _number(node.confidence)
        and 0 <= node.confidence <= 1
        and node.status in AUTO_STATUSES
        and isinstance(node.aliases, tuple)
        and all(_text(alias) for alias in node.aliases)
    )


def _source_problem(source: NodeSource, course_id: str, chunks: Mapping[str, StoredChunk]) -> RejectReason | None:
    chunk = chunks.get(source.chunk_id) if isinstance(source, NodeSource) else None
    if chunk is None or chunk.course_id != course_id:
        return RejectReason.SOURCE_OUTSIDE_COURSE
    start, end = source.evidence_start, source.evidence_end
    if (
        source.document_id != chunk.material_id
        or source.revision_id != chunk.revision_id
        or type(start) is not int
        or type(end) is not int
        or not 0 <= start < end <= len(chunk.text)
    ):
        return RejectReason.INVALID_SOURCE
    return None


def _check(node: DraftNode, course_id: str, chunks: Mapping[str, StoredChunk]) -> RejectReason | None:
    if not isinstance(node, DraftNode) or not _node_valid(node):
        return RejectReason.INVALID_NODE
    if not node.sources:
        return RejectReason.NO_SOURCE
    for source in node.sources:
        problem = _source_problem(source, course_id, chunks)
        if problem is not None:
            return problem
    return None


def _row(node: DraftNode) -> dict[str, object]:
    return {
        "kp_id": node.kp_id,
        "name": node.name.strip(),
        "type": node.type,
        "definition": node.definition.strip(),
        "confidence": float(node.confidence),
        "status": node.status,
        "aliases": [alias.strip() for alias in node.aliases],
        "sources": [
            {
                "chunk_id": s.chunk_id,
                "document_id": s.document_id,
                "revision_id": s.revision_id,
                "evidence_start": s.evidence_start,
                "evidence_end": s.evidence_end,
            }
            for s in node.sources
        ],
    }


# ---------------------------------------------------------------- 写入

# 一批一个托管事务。加锁节点在子查询里被过滤，外层照常返回它的行（locked = true）供记录。
_WRITE_BATCH = """
UNWIND $nodes AS row
OPTIONAL MATCH (existing:KnowledgePoint {course_id: $course_id, version_id: $version_id, kp_id: row.kp_id})
WITH row, existing, coalesce(existing.locked, false) AS locked,
     existing IS NOT NULL AND (coalesce(existing.contrib_manual, false)
         OR any(t IN coalesce(existing.contrib_tasks, []) WHERE t IN $effective_task_ids)) AS was_visible
CALL (row, locked) {
    WITH row WHERE NOT locked
    MERGE (n:KnowledgePoint {course_id: $course_id, version_id: $version_id, kp_id: row.kp_id})
    ON CREATE SET n.source = 'ai', n.locked = false, n.contrib_manual = false, n.contrib_tasks = [],
                  n.revision = 0, n.level = 0
    WITH row, n,
         n.name IS NULL OR n.name <> row.name OR n.type <> row.type OR n.definition <> row.definition
         OR n.confidence <> row.confidence OR n.status <> row.status
         OR coalesce(n.aliases, []) <> row.aliases AS changed
    SET n.name = row.name, n.type = row.type, n.definition = row.definition,
        n.confidence = row.confidence, n.status = row.status, n.aliases = row.aliases,
        n.revision = CASE WHEN changed THEN n.revision + 1 ELSE n.revision END,
        n.contrib_tasks = CASE WHEN $task_id IN n.contrib_tasks THEN n.contrib_tasks
                               ELSE n.contrib_tasks + $task_id END
    WITH row, n
    UNWIND row.sources AS s
    MERGE (c:Chunk {course_id: $course_id, chunk_id: s.chunk_id})
    ON CREATE SET c.document_id = s.document_id, c.revision_id = s.revision_id
    MERGE (n)-[:EVIDENCED_BY {task_id: $task_id, chunk_id: s.chunk_id,
                              evidence_start: s.evidence_start, evidence_end: s.evidence_end}]->(c)
}
RETURN row.kp_id AS kp_id, locked, was_visible
"""


def _batches(rows: Sequence[dict[str, object]], size: int) -> Iterable[Sequence[dict[str, object]]]:
    for start in range(0, len(rows), size):
        yield rows[start:start + size]


def _accept(
    scope: GraphScope, task_id: str, nodes: Sequence[DraftNode], chunks: Iterable[StoredChunk], batch_size: int
) -> tuple[list[dict[str, object]], list[tuple[str, RejectReason]]]:
    if scope.version_id != DRAFT_VERSION:
        raise GraphScopeError("draft node writes require version_id 'draft'")
    if scope.effective_task_ids is None:
        raise GraphScopeError("draft node writes require effective_task_ids from SQLite")
    if not _text(task_id):
        raise ValueError("task_id must be a non-empty string")
    if type(batch_size) is not int or batch_size < 1:
        raise ValueError("batch_size must be an int >= 1")

    known = {chunk.chunk_id: chunk for chunk in chunks}
    rejected: list[tuple[str, RejectReason]] = []
    accepted: list[DraftNode] = []
    seen: set[str] = set()
    for node in nodes:
        kp_id = getattr(node, "kp_id", "")
        problem = _check(node, scope.course_id, known)
        if problem is None and kp_id in seen:
            problem = RejectReason.DUPLICATE_KP_ID
        if problem is not None:
            rejected.append((kp_id if isinstance(kp_id, str) else "", problem))
            continue
        seen.add(kp_id)
        accepted.append(node)
    return [_row(node) for node in accepted], rejected


class _Collector:
    def __init__(self) -> None:
        self.written: list[str] = []
        self.created: list[str] = []
        self.locked: list[str] = []

    def add(self, records: Iterable[Mapping[str, object]]) -> None:
        for record in records:
            kp_id = str(record["kp_id"])
            if record["locked"]:
                self.locked.append(kp_id)
                continue
            self.written.append(kp_id)
            if not record["was_visible"]:
                self.created.append(kp_id)

    def result(self, rejected: Sequence[tuple[str, RejectReason]]) -> NodeWriteResult:
        return NodeWriteResult(tuple(self.written), tuple(self.created), tuple(self.locked), tuple(rejected))


def write_draft_nodes(
    repo: Neo4jRepository,
    scope: GraphScope,
    *,
    task_id: str,
    nodes: Sequence[DraftNode],
    chunks: Iterable[StoredChunk],
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> NodeWriteResult:
    """见模块说明。``chunks`` 是调用方按本课程从 SQLite 读出的来源块（D10），用于拒绝跨课程来源。"""
    rows, rejected = _accept(scope, task_id, nodes, chunks, batch_size)
    collector = _Collector()
    for batch in _batches(rows, batch_size):
        try:
            records = repo.write(_WRITE_BATCH, scope, parameters={"nodes": list(batch), "task_id": task_id})
        except RepositoryError as exc:
            logger.warning("draft node batch of %d failed (%s)", len(batch), exc.code)
            rejected.extend((str(row["kp_id"]), RejectReason.WRITE_FAILED) for row in batch)
            continue
        collector.add(records)
    return collector.result(rejected)


def write_draft_nodes_in(
    tx: ScopedTransaction,
    *,
    task_id: str,
    nodes: Sequence[DraftNode],
    chunks: Iterable[StoredChunk],
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> NodeWriteResult:
    """同上，但在调用方的写事务里执行（F13 §8.4 单事务）。写库错误不按批吞掉，而是让整个事务失败。"""
    rows, rejected = _accept(tx.scope, task_id, nodes, chunks, batch_size)
    collector = _Collector()
    for batch in _batches(rows, batch_size):
        collector.add(tx.run(_WRITE_BATCH, {"nodes": list(batch), "task_id": task_id}))
    return collector.result(rejected)
