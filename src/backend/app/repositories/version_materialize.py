"""G03/G06：版本副本的 Neo4j 持久化；校验与事务内编排由版本服务提供。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from app.repositories.neo4j import GraphScope, Neo4jRepository, ScopedTransaction

T = TypeVar("T")

# 按标签匹配走 (course_id, version_id) 索引，不做无标签全库扫描。
_DELETE = """
CALL () { MATCH (k:KnowledgePoint {course_id: $course_id, version_id: $version_id}) DETACH DELETE k }
CALL () { MATCH (c:Chapter {course_id: $course_id, version_id: $version_id}) DETACH DELETE c }
"""


_CHAPTERS = """
UNWIND $rows AS row
CREATE (c:Chapter)
SET c = row, c.course_id = $course_id, c.version_id = $version_id
RETURN count(c) AS written
"""


_NODES = """
UNWIND $rows AS row
CREATE (k:KnowledgePoint)
SET k = row, k.course_id = $course_id, k.version_id = $version_id
RETURN count(k) AS written
"""


_EVIDENCE = """
UNWIND $rows AS row
MATCH (k:KnowledgePoint {course_id: $course_id, version_id: $version_id, kp_id: row.kp_id})
MATCH (c:Chunk {course_id: $course_id, chunk_id: row.chunk_id})
CREATE (k)-[:EVIDENCED_BY {chunk_id: row.chunk_id}]->(c)
RETURN count(*) AS written
"""


def _relations_query(kind: str) -> str:
    return f"""
UNWIND $rows AS row
MATCH (a:KnowledgePoint {{course_id: $course_id, version_id: $version_id, kp_id: row.from_id}})
MATCH (b:KnowledgePoint {{course_id: $course_id, version_id: $version_id, kp_id: row.to_id}})
CREATE (a)-[r:{kind}]->(b)
SET r.course_id = $course_id, r.version_id = $version_id, r.rel_id = row.rel_id, r.source_refs = row.source_refs
RETURN count(r) AS written
"""


_READ_CHAPTERS = """
MATCH (c:Chapter {course_id: $course_id, version_id: $version_id})
RETURN properties(c) AS p
"""


_READ_NODES = """
MATCH (k:KnowledgePoint {course_id: $course_id, version_id: $version_id})
OPTIONAL MATCH (k)-[e:EVIDENCED_BY]->(c:Chunk {course_id: $course_id})
RETURN properties(k) AS p, collect(c.chunk_id) AS source_refs
"""


_READ_EDGES = """
MATCH (a:KnowledgePoint {course_id: $course_id, version_id: $version_id})
      -[r {course_id: $course_id, version_id: $version_id}]->
      (b:KnowledgePoint {course_id: $course_id, version_id: $version_id})
RETURN type(r) AS type, a.kp_id AS from_id, b.kp_id AS to_id, properties(r) AS p
"""


_COPY_CHAPTERS = """
MATCH (c:Chapter {course_id: $course_id, version_id: $source})
CREATE (n:Chapter) SET n = c {.*, version_id: $version_id}
RETURN count(n) AS written
"""


_COPY_NODES = """
MATCH (k:KnowledgePoint {course_id: $course_id, version_id: $source})
CREATE (n:KnowledgePoint) SET n = k {.*, version_id: $version_id}
RETURN count(n) AS written
"""


_COPY_EVIDENCE = """
MATCH (k:KnowledgePoint {course_id: $course_id, version_id: $source})-[e:EVIDENCED_BY]->
      (c:Chunk {course_id: $course_id})
MATCH (n:KnowledgePoint {course_id: $course_id, version_id: $version_id, kp_id: k.kp_id})
CREATE (n)-[:EVIDENCED_BY {chunk_id: e.chunk_id}]->(c)
RETURN count(*) AS written
"""


def _copy_relations_query(kind: str) -> str:
    return f"""
MATCH (a:KnowledgePoint {{course_id: $course_id, version_id: $source}})
      -[r:{kind} {{course_id: $course_id, version_id: $source}}]->
      (b:KnowledgePoint {{course_id: $course_id, version_id: $source}})
MATCH (x:KnowledgePoint {{course_id: $course_id, version_id: $version_id, kp_id: a.kp_id}})
MATCH (y:KnowledgePoint {{course_id: $course_id, version_id: $version_id, kp_id: b.kp_id}})
CREATE (x)-[s:{kind}]->(y) SET s = r {{.*, version_id: $version_id}}
RETURN count(s) AS written
"""


def transaction(repo: Neo4jRepository, scope: GraphScope, work: Callable[[ScopedTransaction], T]) -> T:
    """保留服务回调中的校验，使失败仍回滚同一个写事务。"""
    return repo.write_transaction(scope, work)


def delete_in(tx: ScopedTransaction) -> None:
    tx.run(_DELETE)


def delete(repo: Neo4jRepository, scope: GraphScope) -> None:
    repo.write(_DELETE, scope)


def _write_rows(tx: ScopedTransaction, query: str, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    [record] = tx.run(query, {"rows": rows})
    return record["written"]


def write_chapters(tx: ScopedTransaction, rows: list[dict[str, Any]]) -> int:
    return _write_rows(tx, _CHAPTERS, rows)


def write_nodes(tx: ScopedTransaction, rows: list[dict[str, Any]]) -> int:
    return _write_rows(tx, _NODES, rows)


def write_evidence(tx: ScopedTransaction, rows: list[dict[str, Any]]) -> int:
    return _write_rows(tx, _EVIDENCE, rows)


def write_relations(tx: ScopedTransaction, kind: str, rows: list[dict[str, Any]]) -> int:
    return _write_rows(tx, _relations_query(kind), rows)


def read_chapters(repo: Neo4jRepository, scope: GraphScope) -> list[dict[str, Any]]:
    return repo.read(_READ_CHAPTERS, scope, reader="worker")


def read_nodes(repo: Neo4jRepository, scope: GraphScope) -> list[dict[str, Any]]:
    return repo.read(_READ_NODES, scope, reader="worker")


def read_edges(repo: Neo4jRepository, scope: GraphScope) -> list[dict[str, Any]]:
    return repo.read(_READ_EDGES, scope, reader="worker")


def copy_chapters(tx: ScopedTransaction, source_version_id: str) -> None:
    tx.run(_COPY_CHAPTERS, {"source": source_version_id})


def copy_nodes(tx: ScopedTransaction, source_version_id: str) -> int:
    [nodes] = tx.run(_COPY_NODES, {"source": source_version_id})
    return nodes["written"]


def copy_evidence(tx: ScopedTransaction, source_version_id: str) -> None:
    tx.run(_COPY_EVIDENCE, {"source": source_version_id})


def copy_relations(tx: ScopedTransaction, kind: str, source_version_id: str) -> None:
    tx.run(_copy_relations_query(kind), {"source": source_version_id})
