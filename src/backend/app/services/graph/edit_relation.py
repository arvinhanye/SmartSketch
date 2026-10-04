"""F06 API：教师关系编辑（契约 ``createRelation`` / ``updateRelation`` / ``deleteRelation``；
specs/course-knowledge-graph.md「前置关系成环处理」；ADR-071）。

顺序同 F08～F10（V4）：输入处理 → 有界等待取课程写锁（持有方 ``edit``，超时 ``CourseBusy``）→ 读 V →
**一个** Neo4j 写事务：锁课程草稿守卫节点 → 读当前关系（不存在、对 V 不可见 → 404 ``NOT_FOUND``）→
写入与环检测 → 记审计 → 读回真实图。校验失败（422）与写入前的拒绝（409 成环 / 重复、422 悬空端点）
不写任何数据，也不加 ``draft_revision``。

三处复用与既有约定一致：

- 关系写入走 F06 服务层 ``app.services.graph.relations.apply_relations``（同一事务内的守卫锁、端点校验、
  重复关系、DAG 环检测与 ``MERGE``），本模块只组合「先删旧身份 / 改状态」这一步；
- 课程写锁与 ``draft_revision`` 走 ``edit_node._course_write`` + ``audit.begin/commit``（F12/ADR-061）；
- 响应体由 ``read_relation_detail`` 读出的真实图组装（``app.services.graph.read._relation``），不是请求体回显，
  因此 ``status`` 等字段与 ``RelationStandard`` / ``RelationDowngraded`` 的 ``oneOf`` 约束一致。

修改语义（契约 ``RelationUpdate``）：

- ``type`` / ``from_id`` / ``to_id`` 任一变化 → 关系身份（§8.4 由「课程 + 类型 + 起点 + 终点」派生）变化：
  先删旧关系与旧身份，再按新身份写入一条人工关系（``source = manual``，保留原 ``confidence`` 与 ``status``）。
  同一个事务里的先删后写也让环检测看见真实的边集：反转 ``A → B`` 为 ``B → A`` 时两条边不会同时存在而误报成环。
- 只改 ``status``（身份不变）→ 不删除重建，只 ``retake_relation``：接管为人工、修订号加 1，``source_pairs``
  与贡献记录保留（改状态不该丢掉 AI 的来源证据）；把 ``rejected`` 恢复为有效时同样先做环检测
  （``rejected`` 的边不参与环检测，恢复它等于重新加边）。
- 目标状态与当前状态已经一致、且关系已是人工的 → 空操作：不写入、不加修订号、不记审计（同 F08 解锁语义）。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from app.repositories.graph_relations import (
    DraftRelation,
    derive_rel_id,
    read_prerequisite_graph,
    read_visible_nodes,
)
from app.repositories.graph_relation_edit import delete_relation as delete_relation_row
from app.repositories.graph_relation_edit import read_relation_detail, retake_relation
from app.repositories.neo4j import GraphScope, ScopedTransaction
from app.services.access import not_found
from app.services.graph import audit
from app.services.graph.dag import check_candidates
from app.services.graph.edit_node import EditContext, InvalidEdit, _course_write
from app.services.graph.read import _chunk_names, _chunks, _relation, _relation_chunk_ids, _source_ref
from app.services.graph.relations import CycleDetectedError, apply_relations

__all__ = ["RelationFields", "create_relation", "delete_relation", "update_relation"]

#: 教师新建的关系视为已确认（与 ``create_node`` 的 ``MANUAL_STATUS`` / ``MANUAL_CONFIDENCE`` 同口径）。
MANUAL_STATUS = "approved"
MANUAL_CONFIDENCE = 1.0
#: 可编辑字段（契约 ``RelationUpdate``）；``course_id`` 等由路由层拒绝，不属于编辑面。
EDITABLE = ("type", "from_id", "to_id", "status")


class RelationStore(Protocol):
    def transaction(self, scope: GraphScope, work: Callable[[ScopedTransaction], Any]) -> Any: ...


@dataclass(frozen=True)
class RelationFields:
    """一条关系的身份与状态（写入前由请求与当前关系合成）。"""

    type: str
    from_id: str
    to_id: str
    status: str


def _state(relation: Mapping[str, Any]) -> dict[str, Any]:
    """审计摘要用的白名单状态；``rel_id`` 与 ``revision`` 只在存在时附上。"""
    out: dict[str, Any] = {key: relation.get(key) for key in ("type", "from_id", "to_id", "status", "source")
                           if relation.get(key) is not None}
    for key in ("rel_id", "revision"):
        if relation.get(key) is not None:
            out[key] = relation[key]
    return out


def _planned(rel: DraftRelation) -> dict[str, Any]:
    """将要写入的关系的身份与状态，按 ``_state`` 的同形状给出（新身份从修订号 1 起）。"""
    return {"rel_id": rel.rel_id, "type": rel.type, "from_id": rel.from_id, "to_id": rel.to_id,
            "status": rel.status, "source": rel.source, "revision": 1}


def _draft(course_id: str, fields: RelationFields, *, confidence: float) -> DraftRelation:
    """合成 F06 的人工关系：ID 由身份派生，``source = manual``，来源证据由调用方决定。"""
    return DraftRelation(
        rel_id=derive_rel_id(course_id, fields.type, fields.from_id, fields.to_id),
        type=fields.type, from_id=fields.from_id, to_id=fields.to_id,
        confidence=confidence, status=fields.status, source="manual",
    )


def _required(tx: ScopedTransaction, rel_id: str) -> dict[str, Any]:
    detail = read_relation_detail(tx, rel_id)
    if detail is None:  # 同一事务内刚写入且持有守卫锁：不应出现
        raise RuntimeError(f"relation {rel_id} is not readable after the write")
    return detail


def _recheck_cycle(tx: ScopedTransaction, rel_id: str, fields: RelationFields) -> None:
    """把一条 ``PREREQUISITE`` 边恢复为有效时重新检测成环（``rejected`` 的边不参与环检测）。"""
    if fields.type != "PREREQUISITE" or fields.status == "rejected":
        return
    edges = read_prerequisite_graph(tx, task_id=None)
    edges.pop(rel_id, None)  # 本次改写的边：它现在的身份就是候选
    check = check_candidates(read_visible_nodes(tx, task_id=None), edges.values(),
                             [(fields.from_id, fields.to_id)])
    if not check.ok:
        raise CycleDetectedError(check.cycle or (), check.edge)


def _self_loop(fields: RelationFields) -> None:
    """``PREREQUISITE`` 的自环由 F06 报成 ``CYCLE_DETECTED``（规格把人工作环与自环并作一行）；
    其余类型不存在自环语义，按 422 的字段错误报告（``InvalidEdit``，与 F08 同一形状）。"""
    if fields.from_id == fields.to_id and fields.type != "PREREQUISITE":
        raise InvalidEdit([{"in": "body", "field": "to_id", "reason": "self_loop"}])


def _write(ctx: EditContext, scope: GraphScope, work: Callable[[ScopedTransaction], Any],
           started: list[audit.Pending]) -> tuple[dict[str, Any], bool]:
    """执行一个关系写事务并收尾审计行；``work`` 返回 ``(读回的关系, 是否空操作)``。

    事务内的失败（含环检测拒绝、端点不可见）按 ``abort`` 记；成功按 ``commit`` 记。``commit`` 自身失败
    只记日志、行留在 ``pending``（``audit.commit`` 从不抛错），已提交的编辑不回滚（ADR-061）。
    """
    try:
        detail, no_op = ctx.store.transaction(scope, work)  # type: ignore[attr-defined]
    except BaseException as exc:
        if started:
            audit.abort(ctx, started[0], exc)
        raise
    if not no_op:
        audit.commit(ctx, started[0], revision_after=None)
    return detail, no_op


def _body(ctx: EditContext, scope: GraphScope, detail: Mapping[str, Any]) -> dict[str, Any]:
    """按契约 ``Relation`` 组装响应：属性来自图，来源按 V 过滤后定位回原文。"""
    row = {"type": detail["type"], "from_id": detail["from_id"], "to_id": detail["to_id"], "p": detail["p"]}
    chunk_ids = _relation_chunk_ids(row, scope)
    chunks = _chunks(ctx.sqlite_url, scope.course_id, chunk_ids)
    names = _chunk_names(ctx.sqlite_url, scope.course_id, chunks)
    refs = [ref for cid in chunk_ids
            if (ref := _source_ref(chunks.get(cid), None, None, None, names)) is not None]
    relation = _relation(scope.course_id, row, refs)
    if relation is None:  # 存储里的关系不满足契约：不应出现
        raise RuntimeError(f"relation {detail['p'].get('rel_id')} does not satisfy the contract after the write")
    return relation.model_dump(mode="json", exclude_none=True)


# ---------------------------------------------------------------- 操作


def create_relation(ctx: EditContext, course_id: str, *, type: str, from_id: str, to_id: str) -> dict[str, Any]:
    """新建人工关系（``source = manual``、``confidence = 1``、``status = approved``）。

    失败时抛出 ``InvalidRelationError``（422）、``CycleDetectedError`` / ``DuplicateRelationError``（409）、
    ``DanglingEndpointError``（422）、``CourseBusy``（409）或 ``AccessDenied``；草稿不变。
    """
    fields = RelationFields(type=type, from_id=from_id, to_id=to_id, status=MANUAL_STATUS)
    _self_loop(fields)
    rel = _draft(course_id, fields, confidence=MANUAL_CONFIDENCE)
    with _course_write(ctx, course_id) as scope:
        started: list[audit.Pending] = []

        def work(tx: ScopedTransaction) -> tuple[dict[str, Any], bool]:
            apply_relations(tx, relations=[rel], task_id=None)  # F06：校验、环检测与写入
            if not started:
                started.append(audit.begin(ctx, course_id, "create", rel.rel_id, revision_before=None,
                                           summary=audit.relation_create_summary(_state(_planned(rel)))))
            return _required(tx, rel.rel_id), False

        detail, _ = _write(ctx, scope, work, started)
    return _body(ctx, scope, detail)


def update_relation(ctx: EditContext, course_id: str, rel_id: str, changes: Mapping[str, Any]) -> dict[str, Any]:
    """改关系类型、方向或状态（见模块说明）；关系对 V 不可见 → 404 ``NOT_FOUND``。"""
    with _course_write(ctx, course_id) as scope:
        started: list[audit.Pending] = []

        def work(tx: ScopedTransaction) -> tuple[dict[str, Any], bool]:
            current = read_relation_detail(tx, rel_id)
            if current is None:
                raise not_found()
            fields = RelationFields(type=changes.get("type", current["type"]),
                                    from_id=changes.get("from_id", current["from_id"]),
                                    to_id=changes.get("to_id", current["to_id"]),
                                    status=changes.get("status", current["status"]))
            _self_loop(fields)
            rel = _draft(course_id, fields, confidence=float(current["p"].get("confidence", MANUAL_CONFIDENCE)))
            if rel.rel_id == rel_id:
                if fields.status == current["status"] and current.get("source") == "manual":
                    return current, True  # 空操作：不写入、不加修订号、不记审计
                _recheck_cycle(tx, rel_id, fields)
                if not retake_relation(tx, rel_id, fields.status):
                    raise not_found()  # 同一事务内刚读过且持有守卫锁：不应出现
                after: dict[str, Any] = {**current, "status": fields.status, "source": "manual"}
            else:
                if not delete_relation_row(tx, rel_id):
                    raise not_found()
                apply_relations(tx, relations=[rel], task_id=None)
                after = _state(_planned(rel))
            if not started:
                started.append(audit.begin(ctx, course_id, "update", rel.rel_id, revision_before=None,
                                           summary=audit.relation_update_summary(_state(current), after)))
            return _required(tx, rel.rel_id), False

        detail, _ = _write(ctx, scope, work, started)
    return _body(ctx, scope, detail)


def delete_relation(ctx: EditContext, course_id: str, rel_id: str) -> None:
    """删除草稿关系及其关系身份；不存在或对 V 不可见 → 404 ``NOT_FOUND``。"""
    with _course_write(ctx, course_id) as scope:
        started: list[audit.Pending] = []

        def work(tx: ScopedTransaction) -> tuple[dict[str, Any], bool]:
            current = read_relation_detail(tx, rel_id)
            if current is None:
                raise not_found()
            if not delete_relation_row(tx, rel_id):
                raise not_found()  # 同一事务内刚读过且持有守卫锁：不应出现
            if not started:
                started.append(audit.begin(ctx, course_id, "delete", rel_id, revision_before=None,
                                           summary=audit.relation_delete_summary(_state(current))))
            return current, False

        _write(ctx, scope, work, started)
