"""F08：教师对草稿知识点的写入（specs/teacher-review-publish.md「节点加锁」V4；ADR-035）。

Neo4j 部分（``DraftNodeStore``）只放 Cypher，调用方已持课程写锁并读好 V：

- ``node``：按 V 可见的草稿节点，不可见视为不存在。
- ``update`` / ``unlock``：一个写事务 = 锁草稿守卫节点 + 以 ``revision = expected`` 为条件的更新；
  条件不成立返回 ``None``。两者都置 ``contrib_manual = true``（§8.4：教师任何写入置真，不回落），
  修订号加 1；``update`` 置 ``locked = true``，``unlock`` 置 ``false``。
- ``create``：新建 ``source = manual``、``locked = true`` 的节点及其人工来源关联（``EVIDENCED_BY`` 不带
  ``task_id``，F07 按人工来源读取）。

SQLite 部分：草稿修订号加 1（V4，在写 Neo4j 之前）、可作为人工来源的块
（块属于本课程，且其修订关联到 V 中的任务）。

F10 合并（ADR-047）的语句只在 ``DraftNodeStore.transaction`` 打开的**一个**写事务里执行（先锁草稿守卫
节点），由 ``app.services.graph.merge_nodes`` 组合为「读 → 校验与验环 → 写」：``read_nodes``、
``read_incident_relations``、``read_evidence``、``update_merged_primary``、``add_evidence``、
``replace_relations``、``delete_merged_nodes``。任何一步抛错，整个事务回滚。
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, TypeVar

from app.repositories.chunks import StoredChunk, get_chunks
from app.repositories.graph_relations import RELATION_TYPES, lock_draft
from app.repositories.neo4j import GraphScope, GraphScopeError, Neo4jRepository, ScopedTransaction
from app.repositories.sqlite import connect

__all__ = [
    "DRAFT_VERSION",
    "DraftNodeStore",
    "IncidentRelation",
    "add_evidence",
    "bump_draft_revision",
    "delete_merged_nodes",
    "read_evidence",
    "read_incident_relations",
    "read_nodes",
    "replace_relations",
    "source_chunks",
    "update_merged_primary",
]

DRAFT_VERSION: Final = "draft"
T = TypeVar("T")


def _visible(var: str) -> str:
    return (f"(coalesce({var}.contrib_manual, false) OR any(t IN coalesce({var}.contrib_tasks, []) "
            f"WHERE t IN $effective_task_ids))")


_FIELDS = ("n {.kp_id, .chapter_id, .name, .aliases, .type, .definition, .importance, .difficulty, "
           ".confidence, .status, .source, .locked, .revision} AS p")

_NODE = f"""
MATCH (n:KnowledgePoint {{course_id: $course_id, version_id: $version_id, kp_id: $kp_id}})
WHERE {_visible("n")}
RETURN {_FIELDS}
"""

_CHAPTER = f"""
MATCH (n:Chapter {{course_id: $course_id, version_id: $version_id, chapter_id: $chapter_id}})
WHERE {_visible("n")}
RETURN n.chapter_id AS chapter_id
"""

_UPDATE = f"""
MATCH (n:KnowledgePoint {{course_id: $course_id, version_id: $version_id, kp_id: $kp_id}})
WHERE {_visible("n")} AND n.revision = $expected_revision
SET n += $changes, n.locked = $locked, n.contrib_manual = true, n.revision = n.revision + 1
RETURN {_FIELDS}
"""

_CREATE = f"""
CREATE (n:KnowledgePoint {{course_id: $course_id, version_id: $version_id, kp_id: $kp_id}})
SET n += $props, n.source = 'manual', n.locked = true, n.contrib_manual = true, n.contrib_tasks = [],
    n.revision = 1, n.level = 0
WITH n
UNWIND $sources AS s
MERGE (c:Chunk {{course_id: $course_id, chunk_id: s.chunk_id}})
ON CREATE SET c.document_id = s.document_id, c.revision_id = s.revision_id
MERGE (n)-[:EVIDENCED_BY {{chunk_id: s.chunk_id, evidence_start: s.evidence_start,
                           evidence_end: s.evidence_end}}]->(c)
WITH DISTINCT n
// 草稿写入必须带 V（F02 作用域检查）；新建节点由人工贡献可见，不按 V 过滤，这里只是引用该参数。
WHERE $effective_task_ids IS NOT NULL
RETURN {_FIELDS}
"""


class DraftNodeStore:
    """草稿知识点的读与教师写入；只接受 ``version_id = "draft"`` 且带 V 的作用域。"""

    def __init__(self, repo: Neo4jRepository) -> None:
        self._repo = repo

    @staticmethod
    def _check(scope: GraphScope) -> None:
        if scope.version_id != DRAFT_VERSION or scope.effective_task_ids is None:
            raise GraphScopeError("teacher node edits require the draft scope with effective_task_ids")

    def node(self, scope: GraphScope, kp_id: str) -> dict[str, Any] | None:
        self._check(scope)
        rows = self._repo.read(_NODE, scope, reader="teacher", parameters={"kp_id": kp_id})
        return rows[0]["p"] if rows else None

    def chapter_visible(self, scope: GraphScope, chapter_id: str) -> bool:
        self._check(scope)
        return bool(self._repo.read(_CHAPTER, scope, reader="teacher", parameters={"chapter_id": chapter_id}))

    def _conditional(self, scope: GraphScope, kp_id: str, expected_revision: int,
                     changes: Mapping[str, Any], locked: bool) -> dict[str, Any] | None:
        self._check(scope)

        def work(tx: ScopedTransaction) -> dict[str, Any] | None:
            lock_draft(tx)
            rows = tx.run(_UPDATE, {"kp_id": kp_id, "expected_revision": expected_revision,
                                    "changes": dict(changes), "locked": locked})
            return rows[0]["p"] if rows else None

        return self._repo.write_transaction(scope, work)

    def update(self, scope: GraphScope, kp_id: str, expected_revision: int,
               changes: Mapping[str, Any]) -> dict[str, Any] | None:
        """教师修改：写入 ``changes`` 并加锁；修订号不等于 ``expected_revision`` 时返回 ``None``。"""
        return self._conditional(scope, kp_id, expected_revision, changes, True)

    def unlock(self, scope: GraphScope, kp_id: str, expected_revision: int) -> dict[str, Any] | None:
        return self._conditional(scope, kp_id, expected_revision, {}, False)

    def transaction(self, scope: GraphScope, work: Callable[[ScopedTransaction], T]) -> T:
        """一个草稿写事务：先锁课程守卫节点，再执行 ``work``；``work`` 抛错则整体回滚（F10、F09）。

        驱动遇到瞬时错误可能重跑 ``work``，所以 ``work`` 只能依据事务内读到的数据行事。
        """
        self._check(scope)

        def guarded(tx: ScopedTransaction) -> T:
            lock_draft(tx)
            return work(tx)

        return self._repo.write_transaction(scope, guarded)

    def create(self, scope: GraphScope, kp_id: str, props: Mapping[str, Any],
               sources: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        """新建人工知识点；``sources`` 至少一条，每条含块、资料、修订与证据区间。"""
        self._check(scope)
        if not sources:
            raise ValueError("a manual knowledge point needs at least one source")

        def work(tx: ScopedTransaction) -> dict[str, Any]:
            lock_draft(tx)
            [row] = tx.run(_CREATE, {"kp_id": kp_id, "props": dict(props),
                                     "sources": [dict(s) for s in sources]})
            return row["p"]

        return self._repo.write_transaction(scope, work)


# ---------------------------------------------------------------- F10 合并：事务内语句

_TX_NODE_FIELDS = ("n {.kp_id, .chapter_id, .name, .aliases, .type, .definition, .importance, .difficulty, "
                   ".confidence, .status, .source, .locked, .revision, .merged_from, .contrib_tasks, "
                   ".contrib_manual} AS p")

_TX_NODES = f"""
UNWIND $kp_ids AS id
MATCH (n:KnowledgePoint {{course_id: $course_id, version_id: $version_id, kp_id: id}})
WHERE {_visible("n")}
RETURN {_TX_NODE_FIELDS}
"""

# 与给定节点相连的全部草稿关系（不论可见与否）：合并时它们都要迁移，否则会随节点一起消失。
_TX_INCIDENT = f"""
UNWIND $kp_ids AS id
MATCH (:KnowledgePoint {{course_id: $course_id, version_id: $version_id, kp_id: id}})
      -[r]-(:KnowledgePoint {{course_id: $course_id, version_id: $version_id}})
WHERE r.course_id = $course_id AND r.version_id = $version_id AND type(r) IN $types
WITH DISTINCT r
WITH r, startNode(r) AS a, endNode(r) AS b
RETURN type(r) AS type, a.kp_id AS from_id, b.kp_id AS to_id, properties(r) AS p,
       {_visible("r")} AND {_visible("a")} AND {_visible("b")} AS visible
ORDER BY r.rel_id
"""

_TX_EVIDENCE = """
UNWIND $kp_ids AS id
MATCH (n:KnowledgePoint {course_id: $course_id, version_id: $version_id, kp_id: id})
      -[e:EVIDENCED_BY]->(c:Chunk {course_id: $course_id})
WHERE $effective_task_ids IS NOT NULL
RETURN n.kp_id AS kp_id, c.chunk_id AS chunk_id, properties(e) AS p
ORDER BY kp_id, chunk_id, e.evidence_start, e.evidence_end
"""

_TX_UPDATE_PRIMARY = f"""
MATCH (n:KnowledgePoint {{course_id: $course_id, version_id: $version_id, kp_id: $kp_id}})
WHERE {_visible("n")} AND n.revision = $expected_revision
SET n.aliases = $aliases, n.merged_from = $merged_from, n.contrib_tasks = $contrib_tasks,
    n.locked = true, n.contrib_manual = true, n.revision = n.revision + 1
RETURN {_FIELDS}
"""

_TX_ADD_EVIDENCE = """
MATCH (n:KnowledgePoint {course_id: $course_id, version_id: $version_id, kp_id: $kp_id})
WHERE $effective_task_ids IS NOT NULL
UNWIND $rows AS row
MATCH (c:Chunk {course_id: $course_id, chunk_id: row.chunk_id})
CREATE (n)-[e:EVIDENCED_BY]->(c)
SET e = row.props
RETURN count(e) AS created
"""

# 关系类型不能参数化，按白名单逐类型生成语句。
_TX_DELETE_RELATIONS = {
    t: f"""
UNWIND $rel_ids AS id
MATCH (:KnowledgePoint {{course_id: $course_id, version_id: $version_id}})
      -[r:{t} {{course_id: $course_id, version_id: $version_id, rel_id: id}}]->
      (:KnowledgePoint {{course_id: $course_id, version_id: $version_id}})
WHERE $effective_task_ids IS NOT NULL
DELETE r
RETURN count(*) AS deleted
""" for t in RELATION_TYPES
}

_TX_DELETE_IDENTITIES = """
UNWIND $rel_ids AS id
MATCH (ri:RelationIdentity {course_id: $course_id, version_id: $version_id, rel_id: id})
WHERE $effective_task_ids IS NOT NULL
DELETE ri
RETURN count(*) AS deleted
"""

_TX_CREATE_RELATIONS = {
    t: f"""
UNWIND $rows AS row
MATCH (a:KnowledgePoint {{course_id: $course_id, version_id: $version_id, kp_id: row.from_id}})
MATCH (b:KnowledgePoint {{course_id: $course_id, version_id: $version_id, kp_id: row.to_id}})
WHERE $effective_task_ids IS NOT NULL
CREATE (a)-[r:{t}]->(b)
SET r = row.props, r.course_id = $course_id, r.version_id = $version_id, r.rel_id = row.rel_id
MERGE (ri:RelationIdentity {{course_id: $course_id, version_id: $version_id, rel_id: row.rel_id}})
SET ri.type = '{t}', ri.from_id = row.from_id, ri.to_id = row.to_id
RETURN row.rel_id AS rel_id
""" for t in RELATION_TYPES
}

_TX_DELETE_NODES = """
UNWIND $kp_ids AS id
MATCH (n:KnowledgePoint {course_id: $course_id, version_id: $version_id, kp_id: id})
WHERE $effective_task_ids IS NOT NULL
DETACH DELETE n
RETURN count(*) AS deleted
"""


@dataclass(frozen=True)
class IncidentRelation:
    """草稿中一条关系的完整属性；``visible`` 按 V 与人工贡献判断（含两端）。"""

    type: str
    from_id: str
    to_id: str
    props: Mapping[str, Any]
    visible: bool

    @property
    def rel_id(self) -> str:
        return str(self.props["rel_id"])


def read_nodes(tx: ScopedTransaction, kp_ids: Sequence[str]) -> dict[str, dict[str, Any]]:
    """可见的草稿节点（含 ``merged_from`` 与贡献记录），按 ``kp_id`` 索引；不可见视为不存在。"""
    return {str(r["p"]["kp_id"]): r["p"] for r in tx.run(_TX_NODES, {"kp_ids": list(kp_ids)})}


def read_incident_relations(tx: ScopedTransaction, kp_ids: Sequence[str]) -> list[IncidentRelation]:
    rows = tx.run(_TX_INCIDENT, {"kp_ids": list(kp_ids), "types": list(RELATION_TYPES)})
    return [IncidentRelation(str(r["type"]), str(r["from_id"]), str(r["to_id"]), dict(r["p"]), bool(r["visible"]))
            for r in rows]


def read_evidence(tx: ScopedTransaction, kp_ids: Sequence[str]) -> list[dict[str, Any]]:
    """节点的全部来源关联（不按 V 过滤）：``{kp_id, chunk_id, props}``。"""
    return [{"kp_id": str(r["kp_id"]), "chunk_id": str(r["chunk_id"]), "props": dict(r["p"])}
            for r in tx.run(_TX_EVIDENCE, {"kp_ids": list(kp_ids)})]


def update_merged_primary(tx: ScopedTransaction, kp_id: str, expected_revision: int, *, aliases: Sequence[str],
                          merged_from: Sequence[str], contrib_tasks: Sequence[str]) -> dict[str, Any] | None:
    """写合并后的主节点：别名、谱系、贡献并集，加锁并登记人工贡献，修订号加 1；条件不成立返回 ``None``。"""
    rows = tx.run(_TX_UPDATE_PRIMARY, {"kp_id": kp_id, "expected_revision": expected_revision,
                                       "aliases": list(aliases), "merged_from": list(merged_from),
                                       "contrib_tasks": list(contrib_tasks)})
    return rows[0]["p"] if rows else None


def add_evidence(tx: ScopedTransaction, kp_id: str, rows: Sequence[Mapping[str, Any]]) -> int:
    """给节点新建来源关联，每行 ``{chunk_id, props}``，``props`` 原样作为关联属性（保留 ``task_id``）。"""
    if not rows:
        return 0
    [row] = tx.run(_TX_ADD_EVIDENCE, {"kp_id": kp_id, "rows": [dict(r) for r in rows]})
    return int(row["created"])


def replace_relations(tx: ScopedTransaction, *, removed: Sequence[tuple[str, str]],
                      created: Sequence[Mapping[str, Any]]) -> list[str]:
    """删除 ``removed``（``(类型, rel_id)``）中的草稿关系与不再使用的关系身份，再按 ``created`` 新建关系。

    ``created`` 每项含 ``type``、``rel_id``、``from_id``、``to_id`` 与 ``props``；返回实际新建的 ``rel_id``。
    """
    for t in RELATION_TYPES:
        ids = sorted({rel_id for rtype, rel_id in removed if rtype == t})
        if ids:
            tx.run(_TX_DELETE_RELATIONS[t], {"rel_ids": ids})
    kept = {str(c["rel_id"]) for c in created}
    stale = sorted({rel_id for _, rel_id in removed} - kept)
    if stale:
        tx.run(_TX_DELETE_IDENTITIES, {"rel_ids": stale})
    written: list[str] = []
    for t in RELATION_TYPES:
        rows = [{"rel_id": c["rel_id"], "from_id": c["from_id"], "to_id": c["to_id"], "props": dict(c["props"])}
                for c in created if c["type"] == t]
        if rows:
            written.extend(str(r["rel_id"]) for r in tx.run(_TX_CREATE_RELATIONS[t], {"rows": rows}))
    return written


def delete_merged_nodes(tx: ScopedTransaction, kp_ids: Sequence[str]) -> int:
    """删除草稿节点及其余下的来源关联；共享的文本块与其他版本的副本不动。"""
    [row] = tx.run(_TX_DELETE_NODES, {"kp_ids": list(kp_ids)})
    return int(row["deleted"])


# ---------------------------------------------------------------- SQLite


def bump_draft_revision(sqlite_url: str, course_id: str) -> int:
    """V4：持锁后、写 Neo4j 前把课程草稿修订号加 1，返回新值。"""
    with connect(sqlite_url) as database:
        row = database.execute(
            "UPDATE courses SET draft_revision = draft_revision + 1 WHERE id = ? RETURNING draft_revision",
            (course_id,),
        ).fetchone()
    if row is None:
        raise LookupError(f"course {course_id} does not exist")
    return int(row[0])


def source_chunks(sqlite_url: str, course_id: str, chunk_ids: Iterable[str],
                  effective_task_ids: Sequence[str]) -> dict[str, StoredChunk]:
    """可作为人工来源的块：属于本课程，且所属修订关联到 V 中至少一个任务（其内容已提交）。"""
    ids = list(dict.fromkeys(chunk_ids))
    chunks = {c.chunk_id: c for c in get_chunks(sqlite_url, course_id=course_id, chunk_ids=ids)}
    revisions = sorted({c.revision_id for c in chunks.values()})
    tasks = list(effective_task_ids)
    if not revisions or not tasks:
        return {}
    with connect(sqlite_url) as database:
        rows = database.execute(
            f"""SELECT DISTINCT revision_id FROM task_revisions
                WHERE course_id = ? AND revision_id IN ({",".join("?" * len(revisions))})
                  AND task_id IN ({",".join("?" * len(tasks))})""",
            (course_id, *revisions, *tasks),
        ).fetchall()
    committed = {str(r[0]) for r in rows}
    return {cid: c for cid, c in chunks.items() if c.revision_id in committed}
