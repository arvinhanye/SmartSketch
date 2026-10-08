"""F09 扩展：级联删除与删除影响预览（ADR-092）。

既有 ``delete_node`` 只删被点名的节点与它相连的关系、保留相邻节点，于是一个章节节点被删后
它的知识点会变成没有父节点的孤儿。本模块把「连带删除会变成孤儿的后代」做成可选项，并在真正
删除前提供**只读预览**，让教师按下确认前就知道会少掉哪些知识点（ADR-092）。

级联边界：

- **只沿 ``CONTAINS`` 递归**。``PREREQUISITE`` 表示学习顺序而不是归属，删掉一个前置知识不应连带
  删除依赖它的后续知识点，否则删一个基础概念会带走整条学习路径。
- **只删会变成孤儿的节点**：一个节点被删，当且仅当它原有的 ``CONTAINS`` 父节点全都在待删集合里。
  仍挂在别处的共享节点（例如同时被「顺序栈」与「链队列」包含的节点）保留，并在报告里以
  ``retained`` 说明原因。
- 预览与实际删除**共用同一个计划函数** :func:`_plan`，不会出现「预览 3 个、实际删 30 个」。

删除范围与 ``delete_node`` 一致：只作用于草稿（``version_id = draft``）；已发布版本的副本、
SQLite 快照与发布指针都不动，学生在重新发布前仍读旧版本。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.repositories import graph_edit
from app.repositories.neo4j import ScopedTransaction
from app.services.access import not_found
from app.services.graph import audit
from app.services.graph.edit_node import EditContext, InvalidEdit, RevisionConflict, _course_write

__all__ = ["DeletionImpact", "delete_node_cascade", "preview_deletion"]


@dataclass(frozen=True)
class DeletionImpact:
    """一次级联删除的影响报告（契约 ``KnowledgePointDeletion``）。"""

    root_id: str
    root_name: str
    cascade: bool
    nodes: tuple[graph_edit.CascadeNode, ...]
    retained: tuple[graph_edit.CascadeNode, ...]
    relation_count: int

    @property
    def deleted_count(self) -> int:
        return len(self.nodes)


@dataclass(frozen=True)
class _Plan:
    """计划：删除集、保留集与会一并删除的关系条数。"""

    deleted: tuple[graph_edit.CascadeNode, ...]
    retained: tuple[graph_edit.CascadeNode, ...]
    relation_count: int


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


def _depths(root_id: str, reachable: list[str],
            parents: dict[str, list[tuple[str, str]]]) -> dict[str, int]:
    """按父链逐层松弛，求每个可达节点到根的**最短** ``CONTAINS`` 距离。

    逐层而不是递归：``CONTAINS`` 理论上可能被手工连成环，逐层加已访问集合保证终止。
    """
    depth: dict[str, int] = {root_id: 0}
    frontier = {root_id}
    for _ in range(graph_edit.CASCADE_MAX_DEPTH + 1):
        children = {
            kp_id for kp_id in reachable
            if kp_id not in depth and any(parent_id in frontier for parent_id, _ in parents.get(kp_id, []))
        }
        if not children:
            break
        for kp_id in children:
            reached = [depth[parent_id] for parent_id, _ in parents.get(kp_id, []) if parent_id in depth]
            depth[kp_id] = min(reached) + 1
        frontier = children
    return depth


def _plan(tx: ScopedTransaction, root_id: str) -> _Plan:
    """在一个事务里算出删除集、保留集与会删除的关系条数；根节点不存在时 404。

    调用方须已经在同一个事务里持有课程守卫锁，这样「读到的图」与「随后删除的图」一致。
    """
    root_row = graph_edit.read_draft_nodes_by_id(tx, [root_id]).get(root_id)
    if root_row is None:
        raise not_found()
    root_name = str(root_row.get("name") or "")

    reachable = graph_edit.read_contains_reachable(tx, root_id)
    parents = graph_edit.read_contains_parents(tx, [root_id, *reachable]) if reachable else {}
    depths = _depths(root_id, reachable, parents)

    # 孤儿安全收敛：只有当一个节点的 CONTAINS 父节点全部在待删集合里，它才跟着删除。
    # 每轮只可能把节点从保留变成删除，因此至多 len(reachable) 轮。
    doomed = {root_id}
    for _ in range(len(reachable) + 1):
        grown = {
            kp_id for kp_id in reachable
            if kp_id not in doomed
            and (own := parents.get(kp_id, []))
            and all(parent_id in doomed for parent_id, _ in own)
        }
        if not grown:
            break
        doomed |= grown

    names = graph_edit.read_draft_nodes_by_id(tx, reachable) if reachable else {}
    deleted = tuple(
        graph_edit.CascadeNode(kp_id, root_name if kp_id == root_id else str(names.get(kp_id, {}).get("name") or ""),
                               depths.get(kp_id, 0))
        for kp_id, _ in sorted(((k, depths.get(k, 0)) for k in doomed), key=lambda item: (item[1], item[0]))
    )
    retained = tuple(
        graph_edit.CascadeNode(
            kp_id,
            str(names.get(kp_id, {}).get("name") or ""),
            depths.get(kp_id, 0),
            # 保留原因：这些父节点不在删除集合里，所以该节点不会被孤立
            tuple(sorted({name for parent_id, name in parents.get(kp_id, []) if parent_id not in doomed})),
        )
        for kp_id in sorted(reachable)
        if kp_id not in doomed
    )
    relation_count = graph_edit.count_draft_relations_among(
        tx, [node.kp_id for node in deleted]
    ) + graph_edit.count_draft_relations_to_outside(tx, [node.kp_id for node in deleted])
    return _Plan(deleted=deleted, retained=retained, relation_count=relation_count)


def _impact(root_id: str, root_name: str, plan: _Plan, *, cascade: bool) -> DeletionImpact:
    return DeletionImpact(root_id=root_id, root_name=root_name, cascade=cascade,
                          nodes=plan.deleted, retained=plan.retained, relation_count=plan.relation_count)


def preview_deletion(ctx: EditContext, course_id: str, kp_id: str) -> DeletionImpact:
    """只读预览：``cascade=true`` 时会删掉哪些知识点与多少条关系。

    走与其他草稿读一致的课程写锁（不写任何数据，也不加草稿修订号），
    这样预览看到的图与随后的删除属于同一个锁序。
    """
    _validate(kp_id, None)
    with _course_write(ctx, course_id) as scope:
        holder: list[DeletionImpact] = []

        def read_only(tx: ScopedTransaction) -> int:
            plan = _plan(tx, kp_id)
            root_row = graph_edit.read_draft_nodes_by_id(tx, [kp_id])[kp_id]
            holder.append(_impact(kp_id, str(root_row.get("name") or ""), plan, cascade=True))
            return 0

        ctx.store.transaction(scope, read_only)  # type: ignore[attr-defined]
    return holder[0]


def delete_node_cascade(ctx: EditContext, course_id: str, kp_id: str,
                        expected_revision: int | None = None) -> DeletionImpact:
    """级联删除 ``kp_id`` 及因本次删除而失去全部 ``CONTAINS`` 父节点的节点。

    写入顺序、锁与并发语义同 ``delete_node``；区别只在删除集合更大。
    失败时抛出 ``AccessDenied``（404）、``InvalidEdit``（422）、``RevisionConflict`` / ``CourseBusy``（409），
    草稿不变；Neo4j 故障抛出 F02 已脱敏的 ``RepositoryError``。
    """
    _validate(kp_id, expected_revision)
    with _course_write(ctx, course_id) as scope:
        started: list[tuple[audit.Pending, dict[str, Any]]] = []

        def write(tx: ScopedTransaction) -> DeletionImpact:
            plan = _plan(tx, kp_id)
            root_row = graph_edit.read_draft_nodes_by_id(tx, [kp_id])[kp_id]
            root_name = str(root_row.get("name") or "")
            if expected_revision is not None and expected_revision != int(root_row.get("revision") or 0):
                raise RevisionConflict(kp_id, expected_revision, root_row)
            if not started:
                started.append((
                    audit.begin(ctx, course_id, "delete", kp_id,
                                revision_before=int(root_row.get("revision") or 0),
                                summary=audit.delete_summary(root_row)),
                    root_row,
                ))
            graph_edit.delete_draft_nodes(tx, [node.kp_id for node in plan.deleted])
            return _impact(kp_id, root_name, plan, cascade=True)

        try:
            impact = ctx.store.transaction(scope, write)  # type: ignore[attr-defined]
        except BaseException as exc:
            if started:
                audit.abort(ctx, started[0][0], exc)
            raise
        pending, root_row = started[0]
        audit.commit(ctx, pending, revision_after=None,
                     summary=audit.delete_summary(root_row, impact.relation_count))
        return impact
