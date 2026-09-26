"""F06：草稿关系的 Cypher（specs/task-processing.md §8.4；ADR-009、ADR-025）。

本模块只放在一个 ``ScopedTransaction`` 里执行的语句，由 ``app.services.graph.relations`` 组合成
「锁草稿 → 读图 → 校验 → 写入」的单一写事务；F13 的 ``persisting`` 可以把它们与节点写入、降级组合在
同一个事务里。

- **课程守卫**：``lock_draft`` 按 ``(course_id, version_id)`` ``MERGE`` 一个 ``DraftWriteGuard`` 节点并
  递增其序号（F03 唯一约束），拿到该节点的写锁直到提交。同一课程草稿的关系写入因此串行，
  后到者在锁释放后读到先到者已提交的边，读、检测与提交处于同一写入序列。
- **关系身份**：每条关系在同一事务里先 ``MERGE (:RelationIdentity {course_id, version_id, rel_id})``，
  记录当前类型与端点；四种关系类型各自的唯一约束无法保证 ``rel_id`` 跨类型唯一。
- **可见性**（§8.4「草稿可见性」）：节点或关系在 ``contrib_manual`` 为真，或 ``contrib_tasks`` 与
  V 相交时可见；关系另要求两端可见。写入方是任务时，它自己的贡献对它也可见（``own_tasks``）。
- **关系属性**：``confidence``、``status``、``source``、``contrib_tasks``、``contrib_manual``、``revision``，
  以及来源 ``source_pairs``：每项是 JSON 字符串 ``[贡献方, chunk_id]``，贡献方为任务 ID，人工为 ``null``。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Final

from app.repositories.neo4j import ScopedTransaction

__all__ = [
    "RELATION_TYPES",
    "DraftRelation",
    "StoredRelation",
    "derive_rel_id",
    "lock_draft",
    "merge_relations",
    "read_prerequisite_graph",
    "read_relations",
    "read_visible_nodes",
    "source_pair",
]

RELATION_TYPES: Final = ("CONTAINS", "PREREQUISITE", "RELATED_TO", "EXAMPLE_OF")


def derive_rel_id(course_id: str, type: str, from_id: str, to_id: str) -> str:
    """§8.4：关系 ID 由「课程 + 类型 + 起点 + 终点」确定；有方向。"""
    if type not in RELATION_TYPES:
        raise ValueError("unknown relation type")
    for name, value in (("course_id", course_id), ("from_id", from_id), ("to_id", to_id)):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")
    digest = hashlib.sha256(json.dumps([course_id, type, from_id, to_id], ensure_ascii=False).encode("utf-8"))
    return "rel_" + digest.hexdigest()[:32]


def source_pair(contributor: str | None, chunk_id: str) -> str:
    """关系来源的存储编码：``[贡献方, chunk_id]``，人工贡献方为 ``null``。"""
    return json.dumps([contributor, chunk_id], ensure_ascii=False)


@dataclass(frozen=True)
class DraftRelation:
    rel_id: str
    type: str
    from_id: str
    to_id: str
    confidence: float
    status: str
    source: str
    chunk_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class StoredRelation:
    """已有的关系身份及其关系（若关系已被清理，``status`` 等为 ``None``）。"""

    rel_id: str
    type: str
    from_id: str
    to_id: str
    status: str | None
    visible: bool


# 可见性谓词。``own`` 是写入任务自己（教师写入时为空列表）。
def _visible(var: str) -> str:
    return (f"(coalesce({var}.contrib_manual, false) OR any(t IN coalesce({var}.contrib_tasks, []) "
            f"WHERE t IN $effective_task_ids OR t IN $own_tasks))")


_LOCK = """
MERGE (g:DraftWriteGuard {course_id: $course_id, version_id: $version_id})
SET g.seq = coalesce(g.seq, 0) + 1
RETURN g.seq AS seq, size($effective_task_ids) AS visible_tasks
"""

_VISIBLE_NODES = f"""
MATCH (n:KnowledgePoint {{course_id: $course_id, version_id: $version_id}})
WHERE {_visible("n")}
RETURN n.kp_id AS kp_id
"""

_PREREQUISITE_EDGES = f"""
MATCH (a:KnowledgePoint {{course_id: $course_id, version_id: $version_id}})
      -[r:PREREQUISITE {{course_id: $course_id, version_id: $version_id}}]->
      (b:KnowledgePoint {{course_id: $course_id, version_id: $version_id}})
WHERE coalesce(r.status, '') <> 'rejected' AND {_visible("r")} AND {_visible("a")} AND {_visible("b")}
RETURN r.rel_id AS rel_id, a.kp_id AS from_id, b.kp_id AS to_id
"""

_RELATIONS = f"""
UNWIND $rel_ids AS id
MATCH (ri:RelationIdentity {{course_id: $course_id, version_id: $version_id, rel_id: id}})
OPTIONAL MATCH (a:KnowledgePoint {{course_id: $course_id, version_id: $version_id, kp_id: ri.from_id}})
               -[r {{course_id: $course_id, version_id: $version_id, rel_id: id}}]->
               (b:KnowledgePoint {{course_id: $course_id, version_id: $version_id, kp_id: ri.to_id}})
WHERE type(r) = ri.type
RETURN id AS rel_id, ri.type AS type, ri.from_id AS from_id, ri.to_id AS to_id, r.status AS status,
       r IS NOT NULL AND {_visible("r")} AND {_visible("a")} AND {_visible("b")} AS visible
"""

# 关系类型不能参数化，按白名单逐类型生成语句。人工写入（$task_id 为 null）覆盖字段并置
# contrib_manual；任务写入只在新建时写字段，之后只并入贡献与来源。
_MERGE_TEMPLATE = """
UNWIND $rows AS row
MATCH (a:KnowledgePoint {course_id: $course_id, version_id: $version_id, kp_id: row.from_id})
MATCH (b:KnowledgePoint {course_id: $course_id, version_id: $version_id, kp_id: row.to_id})
WHERE %(a_visible)s AND %(b_visible)s
MERGE (ri:RelationIdentity {course_id: $course_id, version_id: $version_id, rel_id: row.rel_id})
ON CREATE SET ri.type = '%(type)s', ri.from_id = row.from_id, ri.to_id = row.to_id
MERGE (a)-[r:%(type)s {course_id: $course_id, version_id: $version_id, rel_id: row.rel_id}]->(b)
ON CREATE SET r.confidence = row.confidence, r.status = row.status, r.source = row.source,
              r.contrib_tasks = [], r.contrib_manual = false, r.source_pairs = [], r.revision = 1
WITH row, r,
     $task_id IS NULL AND (r.confidence <> row.confidence OR r.status <> row.status
                           OR r.source <> row.source) AS retake
SET r.confidence = CASE WHEN $task_id IS NULL THEN row.confidence ELSE r.confidence END,
    r.status = CASE WHEN $task_id IS NULL THEN row.status ELSE r.status END,
    r.source = CASE WHEN $task_id IS NULL THEN row.source ELSE r.source END,
    r.revision = CASE WHEN retake THEN r.revision + 1 ELSE r.revision END,
    r.contrib_manual = r.contrib_manual OR $task_id IS NULL,
    r.contrib_tasks = CASE WHEN $task_id IS NULL OR $task_id IN r.contrib_tasks THEN r.contrib_tasks
                           ELSE r.contrib_tasks + $task_id END,
    r.source_pairs = r.source_pairs + [p IN row.pairs WHERE NOT p IN r.source_pairs]
RETURN row.rel_id AS rel_id
"""
_MERGE = {
    type: _MERGE_TEMPLATE % {"type": type, "a_visible": _visible("a"), "b_visible": _visible("b")}
    for type in RELATION_TYPES
}


def _own(task_id: str | None) -> list[str]:
    return [] if task_id is None else [task_id]


def lock_draft(tx: ScopedTransaction) -> int:
    """锁住本课程草稿的守卫节点直到事务结束；返回递增后的守卫序号。"""
    [row] = tx.run(_LOCK)
    return int(row["seq"])


def read_visible_nodes(tx: ScopedTransaction, *, task_id: str | None = None) -> frozenset[str]:
    return frozenset(str(row["kp_id"]) for row in tx.run(_VISIBLE_NODES, {"own_tasks": _own(task_id)}))


def read_prerequisite_graph(tx: ScopedTransaction, *, task_id: str | None = None) -> dict[str, tuple[str, str]]:
    """参与环检测的边：可见、``status ≠ rejected`` 的 ``PREREQUISITE``，按 ``rel_id`` 给出端点。"""
    return {
        str(row["rel_id"]): (str(row["from_id"]), str(row["to_id"]))
        for row in tx.run(_PREREQUISITE_EDGES, {"own_tasks": _own(task_id)})
    }


def read_relations(tx: ScopedTransaction, rel_ids: Iterable[str]) -> dict[str, StoredRelation]:
    """已有关系身份；``visible`` 只按 V 与人工贡献判断（与 F04 的 ``created`` 口径一致）。"""
    ids = sorted(set(rel_ids))
    if not ids:
        return {}
    rows = tx.run(_RELATIONS, {"rel_ids": ids, "own_tasks": []})
    return {
        str(row["rel_id"]): StoredRelation(str(row["rel_id"]), str(row["type"]), str(row["from_id"]),
                                           str(row["to_id"]), row["status"], bool(row["visible"]))
        for row in rows
    }


def merge_relations(tx: ScopedTransaction, relations: Sequence[DraftRelation], *,
                    task_id: str | None) -> list[str]:
    """按身份 ``MERGE`` 关系并登记贡献与来源；调用方已完成校验与环检测。

    端点不可见的行不写入、也不出现在返回值中（调用方据此判定事务失败）。
    """
    written: list[str] = []
    for type in RELATION_TYPES:
        rows = [
            {
                "rel_id": rel.rel_id,
                "from_id": rel.from_id,
                "to_id": rel.to_id,
                "confidence": float(rel.confidence),
                "status": rel.status,
                "source": rel.source,
                "pairs": [source_pair(task_id, chunk_id) for chunk_id in rel.chunk_ids],
            }
            for rel in relations
            if rel.type == type
        ]
        if rows:
            params = {"rows": rows, "task_id": task_id, "own_tasks": _own(task_id)}
            written.extend(str(row["rel_id"]) for row in tx.run(_MERGE[type], params))
    return written
