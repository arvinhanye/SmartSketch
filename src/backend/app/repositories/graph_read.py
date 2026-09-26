"""F07：草稿与已发布图谱的只读查询（specs/task-processing.md §8.4「草稿可见性」；ADR-024、ADR-025）。

- **草稿**（``version_id = "draft"``）：节点、章节、关系按 V 判定可见（``contrib_manual`` 为真，或
  ``contrib_tasks`` 与 V 相交）；关系另要求两端可见；来源关联只取人工添加（无 ``task_id``）或
  ``task_id ∈ V`` 的。关系来源对 ``source_pairs`` 在服务层按同样规则过滤。
- **已发布版本**：版本副本不带贡献记录，按 ``(course_id, version_id)`` 读取全部内容。

返回普通字典，由 ``app.services.graph.read`` 组装成契约模型。
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Final, Literal

from app.repositories.neo4j import GraphScope, Neo4jRepository

__all__ = ["GraphReader", "NodeEvidence", "stored_version_ids"]

DRAFT: Final = "draft"
Reader = Literal["teacher", "student"]


def _visible(var: str) -> str:
    return (f"(coalesce({var}.contrib_manual, false) OR any(t IN coalesce({var}.contrib_tasks, []) "
            f"WHERE t IN $effective_task_ids))")


# 显式投影：不把向量属性（embedding_<suffix>，G03）带回应用层。
_NODE_FIELDS = ("n {.kp_id, .chapter_id, .name, .aliases, .type, .definition, .importance, .difficulty, "
                ".confidence, .status, .source, .locked, .revision, .merged_from} AS p")

_DRAFT_NODES = f"""
MATCH (n:KnowledgePoint {{course_id: $course_id, version_id: $version_id}})
WHERE {_visible("n")} AND ($kp_ids IS NULL OR n.kp_id IN $kp_ids)
RETURN {_NODE_FIELDS} ORDER BY n.kp_id
"""
_PUBLISHED_NODES = f"""
MATCH (n:KnowledgePoint {{course_id: $course_id, version_id: $version_id}})
WHERE $kp_ids IS NULL OR n.kp_id IN $kp_ids
RETURN {_NODE_FIELDS} ORDER BY n.kp_id
"""

_EDGE_MATCH = """
MATCH (a:KnowledgePoint {course_id: $course_id, version_id: $version_id})
      -[r {course_id: $course_id, version_id: $version_id}]->
      (b:KnowledgePoint {course_id: $course_id, version_id: $version_id})
WHERE type(r) IN ['CONTAINS', 'PREREQUISITE', 'RELATED_TO', 'EXAMPLE_OF']
  AND ($kp_ids IS NULL OR a.kp_id IN $kp_ids OR b.kp_id IN $kp_ids)
"""
_DRAFT_EDGES = _EDGE_MATCH + f"""  AND {_visible("r")} AND {_visible("a")} AND {_visible("b")}
RETURN type(r) AS type, a.kp_id AS from_id, b.kp_id AS to_id, properties(r) AS p ORDER BY r.rel_id
"""
_PUBLISHED_EDGES = _EDGE_MATCH + """
RETURN type(r) AS type, a.kp_id AS from_id, b.kp_id AS to_id, properties(r) AS p ORDER BY r.rel_id
"""

_DRAFT_EVIDENCE = f"""
MATCH (n:KnowledgePoint {{course_id: $course_id, version_id: $version_id}})-[e:EVIDENCED_BY]->
      (c:Chunk {{course_id: $course_id}})
WHERE n.kp_id IN $kp_ids AND {_visible("n")} AND (e.task_id IS NULL OR e.task_id IN $effective_task_ids)
RETURN n.kp_id AS kp_id, c.chunk_id AS chunk_id, coalesce(c.document_id, e.document_id) AS document_id,
       e.evidence_start AS evidence_start, e.evidence_end AS evidence_end
ORDER BY kp_id, chunk_id, evidence_start
"""
_PUBLISHED_EVIDENCE = """
MATCH (n:KnowledgePoint {course_id: $course_id, version_id: $version_id})-[e:EVIDENCED_BY]->
      (c:Chunk {course_id: $course_id})
WHERE n.kp_id IN $kp_ids
RETURN n.kp_id AS kp_id, c.chunk_id AS chunk_id, coalesce(c.document_id, e.document_id) AS document_id,
       e.evidence_start AS evidence_start, e.evidence_end AS evidence_end
ORDER BY kp_id, chunk_id, evidence_start
"""

_DRAFT_CHAPTERS = f"""
MATCH (n:Chapter {{course_id: $course_id, version_id: $version_id}})
WHERE {_visible("n")}
RETURN properties(n) AS p ORDER BY n.order, n.chapter_id
"""
_PUBLISHED_CHAPTERS = """
MATCH (n:Chapter {course_id: $course_id, version_id: $version_id})
RETURN properties(n) AS p ORDER BY n.order, n.chapter_id
"""


@dataclass(frozen=True)
class NodeEvidence:
    kp_id: str
    chunk_id: str
    document_id: str | None
    evidence_start: int | None
    evidence_end: int | None


class GraphReader:
    """按作用域读取图谱。``reader`` 为调用方已鉴权的角色；学生只能读已发布版本（F02 拒绝草稿）。"""

    def __init__(self, repo: Neo4jRepository) -> None:
        self._repo = repo

    def _read(self, draft_query: str, published_query: str, scope: GraphScope, reader: Reader,
              parameters: dict[str, Any]) -> list[dict[str, Any]]:
        query = draft_query if scope.version_id == DRAFT else published_query
        return self._repo.read(query, scope, reader=reader, parameters=parameters)

    def nodes(self, scope: GraphScope, reader: Reader, kp_ids: Sequence[str] | None = None) -> list[dict[str, Any]]:
        rows = self._read(_DRAFT_NODES, _PUBLISHED_NODES, scope, reader,
                          {"kp_ids": None if kp_ids is None else list(kp_ids)})
        return [row["p"] for row in rows]

    def edges(self, scope: GraphScope, reader: Reader, kp_ids: Sequence[str] | None = None) -> list[dict[str, Any]]:
        """关系；给出 ``kp_ids`` 时只取至少一端在其中的关系。"""
        rows = self._read(_DRAFT_EDGES, _PUBLISHED_EDGES, scope, reader,
                          {"kp_ids": None if kp_ids is None else list(kp_ids)})
        return [{"type": row["type"], "from_id": row["from_id"], "to_id": row["to_id"], **{"p": row["p"]}}
                for row in rows]

    def evidence(self, scope: GraphScope, reader: Reader, kp_ids: Iterable[str]) -> list[NodeEvidence]:
        ids = sorted(set(kp_ids))
        if not ids:
            return []
        rows = self._read(_DRAFT_EVIDENCE, _PUBLISHED_EVIDENCE, scope, reader, {"kp_ids": ids})
        return [NodeEvidence(str(r["kp_id"]), str(r["chunk_id"]), r["document_id"], r["evidence_start"],
                             r["evidence_end"]) for r in rows]

    def chapters(self, scope: GraphScope, reader: Reader) -> list[dict[str, Any]]:
        return [row["p"] for row in self._read(_DRAFT_CHAPTERS, _PUBLISHED_CHAPTERS, scope, reader, {})]


# 草稿作用域只为满足 F02 的参数约定；本查询列出草稿之外的全部版本副本，不读草稿内容。
_VERSION_IDS = """
MATCH (k:KnowledgePoint {course_id: $course_id})
WHERE k.version_id <> $version_id AND $effective_task_ids IS NOT NULL
RETURN DISTINCT k.version_id AS version_id
UNION
MATCH (c:Chapter {course_id: $course_id})
WHERE c.version_id <> $version_id AND $effective_task_ids IS NOT NULL
RETURN DISTINCT c.version_id AS version_id
"""


def stored_version_ids(repo: Neo4jRepository, course_id: str) -> set[str]:
    """G05 清扫：本课程在 Neo4j 中存有副本的全部非草稿 ``version_id``。"""
    rows = repo.read(_VERSION_IDS, GraphScope(course_id, DRAFT, effective_task_ids=()), reader="worker")
    return {str(r["version_id"]) for r in rows}
