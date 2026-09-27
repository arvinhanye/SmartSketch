"""F11：审核队列的持久化（ADR-060）。

SQLite：教师「不是重复」「确认保留」的记录（``review_dismissals``，迁移 013）。这类处理不改草稿图，
所以不加草稿修订号，也不持课程写锁。

Neo4j：单项处理的事务内语句，只在 ``DraftNodeStore.transaction`` 打开的写事务里执行（先锁草稿守卫节点），
由 ``app.services.graph.review`` 组合为「读 → 判断仍在队列 → 写」：

- ``read_relation``：按 ``rel_id`` 读一条可见的草稿关系及两端状态；
- ``set_relation_status``：以「当前仍是 ``low_confidence``」为条件改状态，登记人工贡献、修订号加 1；
- ``read_isolation``：节点（可见）的状态、修订号，以及仍计入发布的相连关系条数；
- ``reject_node``：以修订号为条件把节点置 ``rejected``，同 F08 的教师修改一样加锁、登记人工贡献、修订号加 1。
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Final

from app.repositories.graph_relations import RELATION_TYPES
from app.repositories.neo4j import ScopedTransaction
from app.repositories.sqlite import connect

__all__ = [
    "DUPLICATE",
    "ISOLATED",
    "DraftRelationState",
    "IsolationState",
    "dismiss",
    "is_dismissed",
    "pair_key",
    "read_dismissals",
    "read_isolation",
    "read_relation",
    "reject_node",
    "set_relation_status",
]

DUPLICATE: Final = "suspected_duplicate"
ISOLATED: Final = "isolated_node"


def pair_key(a: str, b: str) -> str:
    """一对知识点的记录键：两个 ID 按码点升序的 JSON 数组，与顺序无关。"""
    return json.dumps(sorted((a, b)), ensure_ascii=False, separators=(",", ":"))


# ---------------------------------------------------------------- SQLite


def read_dismissals(sqlite_url: str, course_id: str) -> tuple[set[tuple[str, str]], set[str]]:
    """本课程已处理的「不是重复」对（升序二元组）与「确认保留」的孤立节点。"""
    with connect(sqlite_url) as database:
        rows = database.execute("SELECT kind, item_key FROM review_dismissals WHERE course_id = ?",
                                (course_id,)).fetchall()
    pairs: set[tuple[str, str]] = set()
    isolated: set[str] = set()
    for kind, key in rows:
        if kind == DUPLICATE:
            a, b = json.loads(key)
            pairs.add((str(a), str(b)))
        else:
            isolated.add(str(key))
    return pairs, isolated


def is_dismissed(sqlite_url: str, course_id: str, kind: str, item_key: str) -> bool:
    with connect(sqlite_url) as database:
        row = database.execute("SELECT 1 FROM review_dismissals WHERE course_id = ? AND kind = ? AND item_key = ?",
                               (course_id, kind, item_key)).fetchone()
    return row is not None


def dismiss(sqlite_url: str, course_id: str, kind: str, item_key: str, user_id: str) -> bool:
    """记下一条处理；已记过返回 ``False``（幂等，保留第一次的处理人与时间）。"""
    with connect(sqlite_url) as database:
        cursor = database.execute(
            "INSERT OR IGNORE INTO review_dismissals (course_id, kind, item_key, dismissed_by, dismissed_at) "
            "VALUES (?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))",
            (course_id, kind, item_key, user_id),
        )
        return cursor.rowcount == 1


# ---------------------------------------------------------------- Neo4j：事务内语句


def _visible(var: str) -> str:
    return (f"(coalesce({var}.contrib_manual, false) OR any(t IN coalesce({var}.contrib_tasks, []) "
            f"WHERE t IN $effective_task_ids))")


_RELATION_MATCH = """
MATCH (a:KnowledgePoint {course_id: $course_id, version_id: $version_id})
      -[r {course_id: $course_id, version_id: $version_id, rel_id: $rel_id}]->
      (b:KnowledgePoint {course_id: $course_id, version_id: $version_id})
WHERE type(r) IN $types AND %s AND %s AND %s
""" % (_visible("r"), _visible("a"), _visible("b"))

_READ_RELATION = _RELATION_MATCH + """
RETURN r.status AS status, a.status AS from_status, b.status AS to_status
"""

_SET_RELATION_STATUS = _RELATION_MATCH + """  AND r.status = 'low_confidence'
SET r.status = $status, r.contrib_manual = true, r.revision = coalesce(r.revision, 0) + 1
RETURN r.rel_id AS rel_id
"""

_READ_ISOLATION = f"""
MATCH (n:KnowledgePoint {{course_id: $course_id, version_id: $version_id, kp_id: $kp_id}})
WHERE {_visible("n")}
OPTIONAL MATCH (n)-[r]-(m:KnowledgePoint {{course_id: $course_id, version_id: $version_id}})
WHERE r.course_id = $course_id AND r.version_id = $version_id AND type(r) IN $types
  AND coalesce(r.status, '') <> 'rejected' AND coalesce(m.status, '') <> 'rejected'
  AND {_visible("r")} AND {_visible("m")}
RETURN n.status AS status, n.revision AS revision, count(r) AS relations
"""

_REJECT_NODE = f"""
MATCH (n:KnowledgePoint {{course_id: $course_id, version_id: $version_id, kp_id: $kp_id}})
WHERE {_visible("n")} AND n.revision = $expected_revision
SET n.status = 'rejected', n.locked = true, n.contrib_manual = true, n.revision = n.revision + 1
RETURN n.kp_id AS kp_id
"""


@dataclass(frozen=True)
class DraftRelationState:
    status: str | None
    from_status: str | None
    to_status: str | None


@dataclass(frozen=True)
class IsolationState:
    status: str | None
    revision: int
    relations: int


def read_relation(tx: ScopedTransaction, rel_id: str) -> DraftRelationState | None:
    """可见（含两端）的草稿关系；不存在或不可见为 ``None``。"""
    rows = tx.run(_READ_RELATION, {"rel_id": rel_id, "types": list(RELATION_TYPES)})
    if not rows:
        return None
    r = rows[0]
    return DraftRelationState(r["status"], r["from_status"], r["to_status"])


def set_relation_status(tx: ScopedTransaction, rel_id: str, status: str) -> bool:
    """把仍是 ``low_confidence`` 的可见草稿关系改为 ``status``；条件不成立返回 ``False``。"""
    return bool(tx.run(_SET_RELATION_STATUS, {"rel_id": rel_id, "status": status, "types": list(RELATION_TYPES)}))


def read_isolation(tx: ScopedTransaction, kp_id: str) -> IsolationState | None:
    """可见节点的状态、修订号与仍计入发布的相连关系数（关系与另一端都可见且未拒绝）。"""
    rows: Sequence[Any] = tx.run(_READ_ISOLATION, {"kp_id": kp_id, "types": list(RELATION_TYPES)})
    if not rows:
        return None
    r = rows[0]
    return IsolationState(r["status"], int(r["revision"] or 0), int(r["relations"]))


def reject_node(tx: ScopedTransaction, kp_id: str, expected_revision: int) -> bool:
    return bool(tx.run(_REJECT_NODE, {"kp_id": kp_id, "expected_revision": expected_revision}))
