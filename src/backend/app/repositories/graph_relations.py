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
    "PrerequisiteEdge",
    "downgrade_relation",
    "lock_draft",
    "read_prerequisite_edges",
    "revoke_task",
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
    #: ADR-009 自动降级的闭合环路；非空时 ``type`` 为 ``RELATED_TO``、原类型为 ``PREREQUISITE``。
    downgrade_cycle: tuple[str, ...] = ()


@dataclass(frozen=True)
class PrerequisiteEdge:
    """参与环检测的一条现有边及其是否可被自动降级（``source = ai`` 且未经教师确认）。"""

    rel_id: str
    from_id: str
    to_id: str
    confidence: float
    downgradable: bool


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
              r.contrib_tasks = [], r.contrib_manual = false, r.source_pairs = [], r.revision = 1,
              r.downgraded_from_type = CASE WHEN size(row.cycle) > 0 THEN 'PREREQUISITE' END,
              r.downgrade_cycle = CASE WHEN size(row.cycle) > 0 THEN row.cycle END
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


_PREREQUISITE_DETAILS = f"""
MATCH (a:KnowledgePoint {{course_id: $course_id, version_id: $version_id}})
      -[r:PREREQUISITE {{course_id: $course_id, version_id: $version_id}}]->
      (b:KnowledgePoint {{course_id: $course_id, version_id: $version_id}})
WHERE coalesce(r.status, '') <> 'rejected' AND {_visible("r")} AND {_visible("a")} AND {_visible("b")}
RETURN r.rel_id AS rel_id, a.kp_id AS from_id, b.kp_id AS to_id, coalesce(r.confidence, 0.0) AS confidence,
       r.source = 'ai' AND NOT coalesce(r.contrib_manual, false)
       AND r.status IN ['draft', 'low_confidence'] AS downgradable
"""

# ADR-009 第 4 步：类型改为 RELATED_TO、状态 low_confidence，保留端点、置信度、贡献与来源。
# 只降级对写入方可见（或写入方本次也要写入同一 ID，``$force``）、仍可自动降级的边。
_DOWNGRADE = f"""
MATCH (a:KnowledgePoint {{course_id: $course_id, version_id: $version_id, kp_id: $from_id}})
      -[r:PREREQUISITE {{course_id: $course_id, version_id: $version_id, rel_id: $rel_id}}]->
      (b:KnowledgePoint {{course_id: $course_id, version_id: $version_id, kp_id: $to_id}})
WHERE r.source = 'ai' AND NOT coalesce(r.contrib_manual, false) AND r.status IN ['draft', 'low_confidence']
      AND ($force OR {_visible("r")})
MATCH (ri:RelationIdentity {{course_id: $course_id, version_id: $version_id, rel_id: $rel_id}})
CREATE (a)-[d:RELATED_TO]->(b)
SET d = properties(r), d.status = 'low_confidence', d.downgraded_from_type = 'PREREQUISITE',
    d.downgrade_cycle = $cycle, d.revision = coalesce(r.revision, 0) + 1, ri.type = 'RELATED_TO'
DELETE r
RETURN d.rel_id AS rel_id
"""

# §8.4：撤销一个任务的全部贡献，并删除因此不再有任何贡献的元素（及其关系身份）。
# 与 V 无关；``$effective_task_ids IS NOT NULL`` 只为满足草稿作用域的参数约定。
_REVOKE_RELATIONS = """
MATCH (:KnowledgePoint {course_id: $course_id, version_id: $version_id})
      -[r {course_id: $course_id, version_id: $version_id}]->
      (:KnowledgePoint {course_id: $course_id, version_id: $version_id})
WHERE $task_id IN coalesce(r.contrib_tasks, []) AND $effective_task_ids IS NOT NULL
SET r.contrib_tasks = [t IN r.contrib_tasks WHERE t <> $task_id],
    r.source_pairs = [p IN coalesce(r.source_pairs, []) WHERE NOT p STARTS WITH $pair_prefix]
WITH r, r.rel_id AS rel_id, size(r.contrib_tasks) = 0 AND NOT coalesce(r.contrib_manual, false) AS orphan
CALL (r, rel_id, orphan) {
    WITH r, rel_id WHERE orphan
    OPTIONAL MATCH (ri:RelationIdentity {course_id: $course_id, version_id: $version_id, rel_id: rel_id})
    DELETE r, ri
}
RETURN count(*) AS revoked, sum(CASE WHEN orphan THEN 1 ELSE 0 END) AS deleted
"""

_REVOKE_NODES = """
MATCH (n:KnowledgePoint {course_id: $course_id, version_id: $version_id})
WHERE $effective_task_ids IS NOT NULL AND ($task_id IN coalesce(n.contrib_tasks, [])
   OR EXISTS { (n)-[:EVIDENCED_BY {task_id: $task_id}]->(:Chunk {course_id: $course_id}) })
OPTIONAL MATCH (n)-[e:EVIDENCED_BY {task_id: $task_id}]->(:Chunk {course_id: $course_id})
DELETE e
WITH DISTINCT n
SET n.contrib_tasks = [t IN coalesce(n.contrib_tasks, []) WHERE t <> $task_id]
WITH n, size(n.contrib_tasks) = 0 AND NOT coalesce(n.contrib_manual, false) AS orphan
CALL (n, orphan) {
    WITH n WHERE orphan
    OPTIONAL MATCH (n)-[r {course_id: $course_id, version_id: $version_id}]-(:KnowledgePoint)
    OPTIONAL MATCH (ri:RelationIdentity {course_id: $course_id, version_id: $version_id, rel_id: r.rel_id})
    DETACH DELETE ri, n
}
RETURN count(*) AS revoked, sum(CASE WHEN orphan THEN 1 ELSE 0 END) AS deleted
"""


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
                "cycle": list(rel.downgrade_cycle),
            }
            for rel in relations
            if rel.type == type
        ]
        if rows:
            params = {"rows": rows, "task_id": task_id, "own_tasks": _own(task_id)}
            written.extend(str(row["rel_id"]) for row in tx.run(_MERGE[type], params))
    return written


def read_prerequisite_edges(tx: ScopedTransaction, *, task_id: str | None = None) -> list[PrerequisiteEdge]:
    """同 ``read_prerequisite_graph``，另带置信度与是否可自动降级（ADR-009 降级算法的输入）。"""
    return [
        PrerequisiteEdge(str(row["rel_id"]), str(row["from_id"]), str(row["to_id"]), float(row["confidence"]),
                         bool(row["downgradable"]))
        for row in tx.run(_PREREQUISITE_DETAILS, {"own_tasks": _own(task_id)})
    ]


def downgrade_relation(tx: ScopedTransaction, *, rel_id: str, from_id: str, to_id: str,
                       cycle: Sequence[str], task_id: str | None = None, force: bool = False) -> bool:
    """把一条可降级的 AI ``PREREQUISITE`` 边改为 ``RELATED_TO`` + ``low_confidence``（ADR-009）。

    ``force`` 用于写入方本次候选与一条对它不可见的边同 ID 的情形：写入后该边会以同一身份变为可见。
    """
    rows = tx.run(_DOWNGRADE, {"rel_id": rel_id, "from_id": from_id, "to_id": to_id, "cycle": list(cycle),
                               "own_tasks": _own(task_id), "force": force})
    return bool(rows)


def revoke_task(tx: ScopedTransaction, task_id: str) -> tuple[int, int]:
    """撤销 ``task_id`` 的全部贡献（§8.4），返回 ``(涉及元素数, 删除元素数)``。

    关系：移出 ``contrib_tasks``，去掉该任务的来源对；已无任务贡献且非人工的关系连同其身份删除。
    节点：删除该任务的 ``EVIDENCED_BY``，移出 ``contrib_tasks``；已无任何贡献的节点连同与它相连的关系
    及其身份删除。其他任务或人工的贡献不动；本任务此前对他人边的降级不撤销（§8.4 已知限制）。
    """
    if not isinstance(task_id, str) or not task_id.strip():
        raise ValueError("task_id must be a non-empty string")
    params = {"task_id": task_id, "pair_prefix": source_pair(task_id, "")[:-4]}
    [rels] = tx.run(_REVOKE_RELATIONS, params)
    [nodes] = tx.run(_REVOKE_NODES, params)
    return int(rels["revoked"]) + int(nodes["revoked"]), int(rels["deleted"]) + int(nodes["deleted"])
