"""F09：教师删除草稿知识点与关系清理（契约 ``deleteKnowledgePoint``；specs/teacher-review-publish.md
「V3 merged_from」「V4」；ADR-048）。

顺序同 F08/F10（V4）：输入校验 → 有界等待取课程写锁（持有方 ``edit``，超时 ``CourseBusy``）→ 读 V →
**一个** Neo4j 写事务：锁课程草稿守卫节点 → 读目标节点（不存在、对 V 不可见或属于他课 → 404
``NOT_FOUND``）→ 核对可选的 ``expected_revision``（不符 → ``RevisionConflict``）→ ``draft_revision + 1`` →
以修订号为条件删除。校验失败不写任何数据，也不加 ``draft_revision``。

删除范围只限草稿（``version_id = "draft"``）：节点、与它相连的全部草稿关系（含对 V 不可见的，否则会成悬空边）
及其 ``RelationIdentity``、节点的来源关联与 ``merged_from``（V3：F09 删除时丢弃谱系）。已发布版本的副本、
SQLite 中的快照与发布指针、共享文本块都不动；学生在重新发布前仍读旧版本。

并发：同一课程的删除经课程写锁与守卫节点串行，后到者读到节点已不存在 → 404，所以同一节点恰有一次成功。
加锁节点照常可删（锁只约束自动流程）。审计日志归 F12。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.repositories import graph_edit
from app.repositories.graph_edit import bump_draft_revision
from app.repositories.neo4j import ScopedTransaction
from app.services.access import not_found
from app.services.graph.edit_node import EditContext, InvalidEdit, RevisionConflict, _course_write

__all__ = ["DeletedNode", "delete_node"]


@dataclass(frozen=True)
class DeletedNode:
    kp_id: str
    #: 随节点删除的草稿关系数（含对 V 不可见的）
    relations: int


def _validate(kp_id: object, expected_revision: object) -> None:
    if expected_revision is not None:
        reason = None
        if type(expected_revision) is not int:
            reason = "int_type"
        elif expected_revision < 1:
            reason = "greater_than_equal"
        if reason is not None:
            raise InvalidEdit([{"in": "query", "field": "expected_revision", "reason": reason}])
    if not isinstance(kp_id, str) or not kp_id.strip():
        raise not_found()


def _delete(tx: ScopedTransaction, kp_id: str, expected_revision: int | None, bump: Any) -> DeletedNode:
    node = graph_edit.read_nodes(tx, [kp_id]).get(kp_id)
    if node is None:
        raise not_found()
    current = int(node.get("revision") or 0)
    if expected_revision is not None and expected_revision != current:
        raise RevisionConflict(kp_id, expected_revision, node)
    bump()
    relations = graph_edit.delete_draft_node(tx, kp_id, current)
    if relations is None:  # 同一事务内刚读过且持有守卫锁：不应出现
        raise RevisionConflict(kp_id, current, node)
    return DeletedNode(kp_id, relations)


def delete_node(ctx: EditContext, course_id: str, kp_id: str, expected_revision: int | None = None) -> DeletedNode:
    """删除草稿知识点及其草稿关系（见模块说明）。

    失败时抛出 ``AccessDenied``（404）、``InvalidEdit``（422）、``RevisionConflict`` / ``CourseBusy``（409），
    草稿不变；Neo4j 故障抛出 F02 已脱敏的 ``RepositoryError``。
    """
    _validate(kp_id, expected_revision)
    with _course_write(ctx, course_id) as scope:
        bumped: list[int] = []

        def bump() -> None:  # 驱动重跑事务时不重复加
            if not bumped:
                bumped.append(bump_draft_revision(ctx.sqlite_url, course_id))

        return ctx.store.transaction(  # type: ignore[attr-defined, no-any-return]
            scope, lambda tx: _delete(tx, kp_id, expected_revision, bump))
