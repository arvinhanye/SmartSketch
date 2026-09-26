"""F06：草稿关系的事务写入与并发防环（specs/course-knowledge-graph.md「前置关系成环处理」；
specs/task-processing.md §8.4；ADR-009、ADR-025）。

``write_relations`` 在**一个** Neo4j 写事务里完成：

1. 锁住课程草稿守卫节点（``lock_draft``），同一课程的关系写入从此串行；
2. 读取对写入方可见的知识点与参与环检测的 ``PREREQUISITE`` 边（V，任务写入另含它自己的贡献）；
3. 校验端点、关系身份，再用 F05 ``check_candidates`` 检查「现有边 + 本次候选」；
4. 全部通过才 ``MERGE`` 关系身份与关系并登记贡献；任何一步失败整个事务回滚，草稿不变。

写入方：``task_id is None`` 为教师（``source = manual``），否则为该任务（``source = ai``）。
关系已存在时：

- 教师：可见的同 ID 关系 → ``DUPLICATE_RELATION``；不可见的（未提交或失败任务留下）由教师接管，
  字段改为教师给出的值并置 ``contrib_manual``。身份的类型或端点与请求不同也按重复处理。
- 任务：端点与身份不同（教师改过端点）→ 跳过并记入 ``conflicts``；类型不同（ADR-009 降级，或教师改过
  类型）→ 沿用现有类型，只登记贡献与来源，记入 ``kept_type``。任务写入从不改动已有关系的字段。

本模块不实现 ADR-009 自动降级（F13 在同一事务里先降级再调用下层语句），也不取 SQLite 课程写锁与
``draft_revision``（V4，由 API/发布层持有）；守卫节点保证即便绕过课程写锁，防环依然成立。
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from typing import Final

from app.repositories.chunks import StoredChunk
from app.repositories.graph_relations import (
    RELATION_TYPES,
    DraftRelation,
    derive_rel_id,
    lock_draft,
    merge_relations,
    read_prerequisite_graph,
    read_relations,
    read_visible_nodes,
)
from app.repositories.neo4j import GraphScope, GraphScopeError, Neo4jRepository, ScopedTransaction
from app.services.graph.dag import check_candidates

__all__ = [
    "CycleDetectedError",
    "DanglingEndpointError",
    "DuplicateRelationError",
    "InvalidRelationError",
    "RelationWriteError",
    "RelationWriteResult",
    "write_relations",
]

DRAFT_VERSION: Final = "draft"
STATUSES: Final = frozenset({"draft", "low_confidence", "approved", "rejected"})
#: 自动流程可写的状态；``approved``/``rejected`` 只由教师产生。
AUTO_STATUSES: Final = frozenset({"draft", "low_confidence"})


class RelationWriteError(Exception):
    code = "INTERNAL_ERROR"


class InvalidRelationError(RelationWriteError, ValueError):
    code = "VALIDATION_ERROR"


class CycleDetectedError(RelationWriteError):
    """``cycle`` 为首尾相同的节点 ID 链；``edge`` 为闭合它的候选（草稿本已成环时为 ``None``）。"""

    code = "CYCLE_DETECTED"

    def __init__(self, cycle: tuple[str, ...], edge: tuple[str, str] | None) -> None:
        super().__init__(self.code)
        self.cycle, self.edge = cycle, edge


class DanglingEndpointError(RelationWriteError):
    code = "DANGLING_ENDPOINT"

    def __init__(self, missing: Sequence[str]) -> None:
        super().__init__(self.code)
        self.missing = tuple(missing)


class DuplicateRelationError(RelationWriteError):
    code = "DUPLICATE_RELATION"

    def __init__(self, existing_id: str) -> None:
        super().__init__(self.code)
        self.existing_id = existing_id


@dataclass(frozen=True)
class RelationWriteResult:
    written: tuple[str, ...] = ()
    #: 写入前对教师不可见（不存在，或贡献任务都不在 V 且非人工）的关系。
    created: tuple[str, ...] = ()
    #: 任务候选沿用了已有关系的类型（降级或教师改类型）。
    kept_type: tuple[str, ...] = ()
    #: 任务候选的 ID 已指向其他端点，未写入。
    conflicts: tuple[str, ...] = ()


# ---------------------------------------------------------------- 校验


def _text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _valid_id(rel: DraftRelation, course_id: str) -> bool:
    allowed = {derive_rel_id(course_id, rel.type, rel.from_id, rel.to_id)}
    if rel.type == "RELATED_TO":  # ADR-009 降级保留原 PREREQUISITE 关系的 ID
        allowed.add(derive_rel_id(course_id, "PREREQUISITE", rel.from_id, rel.to_id))
    return rel.rel_id in allowed


def _validate(rel: object, course_id: str, task_id: str | None, chunks: dict[str, StoredChunk]) -> DraftRelation:
    if not isinstance(rel, DraftRelation):
        raise InvalidRelationError("relation must be a DraftRelation")
    confidence = rel.confidence
    if not (
        rel.type in RELATION_TYPES
        and _text(rel.from_id)
        and _text(rel.to_id)
        and isinstance(confidence, (int, float))
        and not isinstance(confidence, bool)
        and math.isfinite(confidence)
        and 0 <= confidence <= 1
        and rel.status in (STATUSES if task_id is None else AUTO_STATUSES)
        and rel.source == ("manual" if task_id is None else "ai")
        and isinstance(rel.chunk_ids, tuple)
        and _valid_id(rel, course_id)
    ):
        raise InvalidRelationError("invalid relation")
    if task_id is not None and not rel.chunk_ids:
        raise InvalidRelationError("AI relations need at least one source chunk")
    for chunk_id in rel.chunk_ids:
        chunk = chunks.get(chunk_id) if isinstance(chunk_id, str) else None
        if chunk is None or chunk.course_id != course_id:
            raise InvalidRelationError("relation source is outside the course")
    if rel.from_id == rel.to_id:
        if rel.type == "PREREQUISITE":
            raise CycleDetectedError((rel.from_id, rel.to_id), (rel.from_id, rel.to_id))
        raise InvalidRelationError("self-loop relation")
    return rel


# ---------------------------------------------------------------- 写入


def _apply(tx: ScopedTransaction, relations: Sequence[DraftRelation], task_id: str | None) -> RelationWriteResult:
    lock_draft(tx)  # 之后的读取都在守卫锁之内

    nodes = read_visible_nodes(tx, task_id=task_id)
    missing = sorted({end for rel in relations for end in (rel.from_id, rel.to_id)} - nodes)
    if missing:
        raise DanglingEndpointError(missing)

    existing = read_relations(tx, (rel.rel_id for rel in relations))
    plan: list[DraftRelation] = []
    created: list[str] = []
    kept: list[str] = []
    conflicts: list[str] = []
    effective_status: dict[str, str] = {}
    for rel in relations:
        old = existing.get(rel.rel_id)
        status = rel.status
        if old is not None:
            same = (old.from_id, old.to_id) == (rel.from_id, rel.to_id)
            if task_id is None:
                if old.visible or not same or old.type != rel.type:
                    raise DuplicateRelationError(rel.rel_id)
            else:
                if not same:
                    conflicts.append(rel.rel_id)
                    continue
                if old.type != rel.type:
                    rel = replace(rel, type=old.type)
                    kept.append(rel.rel_id)
                status = old.status or rel.status
        if old is None or not old.visible:
            created.append(rel.rel_id)
        effective_status[rel.rel_id] = status
        plan.append(rel)

    edges = read_prerequisite_graph(tx, task_id=task_id)
    candidates = []
    for rel in plan:
        edges.pop(rel.rel_id, None)
        if rel.type == "PREREQUISITE" and effective_status[rel.rel_id] != "rejected":
            candidates.append((rel.from_id, rel.to_id))
    check = check_candidates(nodes, edges.values(), candidates)
    if not check.ok:
        raise CycleDetectedError(check.cycle or (), check.edge)

    written = merge_relations(tx, plan, task_id=task_id)
    unwritten = {rel.rel_id for rel in plan} - set(written)
    if unwritten:  # 端点在读取后变为不可见：回滚整个事务
        raise DanglingEndpointError(sorted({end for rel in plan if rel.rel_id in unwritten
                                            for end in (rel.from_id, rel.to_id)}))
    order = [rel.rel_id for rel in plan]
    return RelationWriteResult(tuple(order), tuple(created), tuple(kept), tuple(conflicts))


def write_relations(
    repo: Neo4jRepository,
    scope: GraphScope,
    *,
    relations: Iterable[DraftRelation],
    task_id: str | None = None,
    chunks: Iterable[StoredChunk] = (),
) -> RelationWriteResult:
    """见模块说明。``chunks`` 是调用方按本课程从 SQLite 读出的来源块（D10），用于拒绝跨课程来源。

    失败时抛出 ``RelationWriteError`` 的子类（``code`` 为契约错误码），草稿不变；
    Neo4j 故障抛出 F02 已脱敏的 ``RepositoryError``。
    """
    if scope.version_id != DRAFT_VERSION:
        raise GraphScopeError("draft relation writes require version_id 'draft'")
    if scope.effective_task_ids is None:
        raise GraphScopeError("draft relation writes require effective_task_ids from SQLite")
    if task_id is not None and not _text(task_id):
        raise ValueError("task_id must be a non-empty string or None")

    known = {chunk.chunk_id: chunk for chunk in chunks}
    items = [_validate(rel, scope.course_id, task_id, known) for rel in relations]
    ids = [rel.rel_id for rel in items]
    if len(set(ids)) != len(ids):
        raise InvalidRelationError("duplicate rel_id in one write")
    if not items:
        return RelationWriteResult()
    return repo.write_transaction(scope, lambda tx: _apply(tx, items, task_id))
