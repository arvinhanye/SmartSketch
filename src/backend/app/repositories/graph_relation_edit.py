"""F06 API：教师对草稿关系的读与写（契约 ``createRelation`` / ``updateRelation`` / ``deleteRelation``；
specs/course-knowledge-graph.md「前置关系成环处理」）。

本模块只放 Cypher，调用方 ``app.services.graph.edit_relation`` 已持 SQLite 课程写锁并读好 V：

- ``read_relation_detail``：按 ``rel_id`` 读一条可见的草稿关系（V 或人工贡献可见，且两端可见），
  返回与 ``GraphReader.edges`` 相同的行形状（``type`` / ``from_id`` / ``to_id`` / ``p``）；不可见视为不存在。
  响应体由它读出的真实图组装，不是请求体回显。
- ``delete_relation``：删除该关系与它的 ``RelationIdentity``。关系身份由「课程 + 类型 + 起点 + 终点」派生
  （§8.4），所以改端点或改类型时必须先删旧关系：既腾出 ``rel_id``，也让随后的环检测看见真实的边集
  （反转 ``A → B`` 为 ``B → A`` 时两条边同时存在会误报成环）。
- ``retake_relation``：同一身份的改状态不删除重建，只改 ``status`` 并把 ``source`` 置 ``manual``、
  ``contrib_manual`` 置真、修订号加 1；``source_pairs``（AI 的来源证据）因此在改状态后仍然保留。
- ``DraftRelationStore``：``transaction``（一个写事务 = 先锁草稿守卫节点）、``relation``（审计对账用的读），
  以及 ``audit.reconcile`` 处理**节点**审计行时仍需要的 ``node``（复用 ``DraftNodeStore``，不复制读法）。

失败时由调用方或 ``Neo4jRepository`` 抛出已脱敏的 ``RepositoryError``；本模块不吞异常。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, TypeVar

from app.repositories.graph_edit import DraftNodeStore
from app.repositories.graph_relations import RELATION_TYPES, lock_draft
from app.repositories.neo4j import GraphScope, GraphScopeError, Neo4jRepository, ScopedTransaction

__all__ = [
    "DRAFT_VERSION",
    "DraftRelationStore",
    "delete_relation",
    "read_relation_detail",
    "retake_relation",
]

DRAFT_VERSION = "draft"
T = TypeVar("T")


def _visible(var: str) -> str:
    return (f"(coalesce({var}.contrib_manual, false) OR any(t IN coalesce({var}.contrib_tasks, []) "
            f"WHERE t IN $effective_task_ids))")


# 关系类型不能参数化，端点方向由箭头固定：`(a)-[r {rel_id}]->(b)` 同时匹配类型与方向。
_RELATION_DETAIL = f"""
MATCH (a:KnowledgePoint {{course_id: $course_id, version_id: $version_id}})
      -[r {{course_id: $course_id, version_id: $version_id, rel_id: $rel_id}}]->
      (b:KnowledgePoint {{course_id: $course_id, version_id: $version_id}})
WHERE type(r) IN $types AND {_visible("r")} AND {_visible("a")} AND {_visible("b")}
RETURN type(r) AS type, a.kp_id AS from_id, b.kp_id AS to_id, properties(r) AS p
"""

# 删除关系与它的身份：不可见的关系对教师不存在（调用方按 404 处理），这里也不匹配。
_DELETE_RELATION = f"""
MATCH (a:KnowledgePoint {{course_id: $course_id, version_id: $version_id}})
      -[r {{course_id: $course_id, version_id: $version_id, rel_id: $rel_id}}]->
      (b:KnowledgePoint {{course_id: $course_id, version_id: $version_id}})
WHERE type(r) IN $types AND {_visible("r")} AND {_visible("a")} AND {_visible("b")}
WITH r, r.rel_id AS rel_id
OPTIONAL MATCH (ri:RelationIdentity {{course_id: $course_id, version_id: $version_id, rel_id: rel_id}})
DELETE r, ri
RETURN count(*) AS deleted
"""

# 教师改状态（同身份，不走删除重建）：接管为人工、修订号加 1；`source_pairs` 与贡献记录不动。
_RETAKE_RELATION = f"""
MATCH (a:KnowledgePoint {{course_id: $course_id, version_id: $version_id}})
      -[r {{course_id: $course_id, version_id: $version_id, rel_id: $rel_id}}]->
      (b:KnowledgePoint {{course_id: $course_id, version_id: $version_id}})
WHERE type(r) IN $types AND {_visible("r")} AND {_visible("a")} AND {_visible("b")}
SET r.status = $status, r.source = 'manual', r.contrib_manual = true, r.revision = r.revision + 1
RETURN r.rel_id AS rel_id
"""


def _row(row: Mapping[str, Any]) -> dict[str, Any]:
    """与 ``GraphReader.edges`` 一致的一行，另带 ``rel_id``：类型、端点与关系属性。"""
    props = dict(row["p"] or {})
    return {"rel_id": str(props.get("rel_id") or ""), "type": str(row["type"]), "from_id": str(row["from_id"]),
            "to_id": str(row["to_id"]), "status": props.get("status"), "source": props.get("source"),
            "revision": props.get("revision"), "p": props}


def read_relation_detail(tx: ScopedTransaction, rel_id: str) -> dict[str, Any] | None:
    """事务内读一条可见的草稿关系；不可见或不存在返回 ``None``。"""
    rows = tx.run(_RELATION_DETAIL, {"rel_id": rel_id, "types": list(RELATION_TYPES)})
    return _row(rows[0]) if rows else None


def delete_relation(tx: ScopedTransaction, rel_id: str) -> bool:
    """删除可见的草稿关系及其关系身份；关系不可见（或已不存在）返回 ``False``。"""
    rows = tx.run(_DELETE_RELATION, {"rel_id": rel_id, "types": list(RELATION_TYPES)})
    return bool(rows) and int(rows[0]["deleted"]) > 0


def retake_relation(tx: ScopedTransaction, rel_id: str, status: str) -> bool:
    """同身份改状态：接管为人工并递增修订号；关系不可见（或已不存在）返回 ``False``。"""
    rows = tx.run(_RETAKE_RELATION, {"rel_id": rel_id, "status": status, "types": list(RELATION_TYPES)})
    return bool(rows)


class DraftRelationStore:
    """草稿关系的读与写；只接受 ``version_id = "draft"`` 且带 V 的作用域。"""

    def __init__(self, repo: Neo4jRepository) -> None:
        self._repo = repo
        self._nodes = DraftNodeStore(repo)

    @staticmethod
    def _check(scope: GraphScope) -> None:
        if scope.version_id != DRAFT_VERSION or scope.effective_task_ids is None:
            raise GraphScopeError("teacher relation edits require the draft scope with effective_task_ids")

    def transaction(self, scope: GraphScope, work: Callable[[ScopedTransaction], T]) -> T:
        """一个草稿写事务：先锁课程守卫节点，再执行 ``work``；``work`` 抛错则整体回滚。

        驱动遇到瞬时错误可能重跑 ``work``，所以 ``work`` 只能依据事务内读到的数据行事。
        """
        self._check(scope)

        def guarded(tx: ScopedTransaction) -> T:
            lock_draft(tx)
            return work(tx)

        return self._repo.write_transaction(scope, guarded)

    def relation(self, scope: GraphScope, rel_id: str) -> dict[str, Any] | None:
        """按 V 可见的草稿关系；不可见视为不存在（``audit.reconcile`` 用它判定关系审计行）。"""
        self._check(scope)
        rows = self._repo.read(_RELATION_DETAIL, scope, reader="teacher",
                               parameters={"rel_id": rel_id, "types": list(RELATION_TYPES)})
        return _row(rows[0]) if rows else None

    def node(self, scope: GraphScope, kp_id: str) -> dict[str, Any] | None:
        """节点读（F12 审计对账会对同课程的遗留节点行调用）；读法与 ``DraftNodeStore`` 完全相同。"""
        return self._nodes.node(scope, kp_id)
