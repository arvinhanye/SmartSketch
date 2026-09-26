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
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Final

from app.repositories.chunks import StoredChunk, get_chunks
from app.repositories.graph_relations import lock_draft
from app.repositories.neo4j import GraphScope, GraphScopeError, Neo4jRepository, ScopedTransaction
from app.repositories.sqlite import connect

__all__ = [
    "DRAFT_VERSION",
    "DraftNodeStore",
    "bump_draft_revision",
    "source_chunks",
]

DRAFT_VERSION: Final = "draft"


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
