"""G03：按快照物化版本图与知识点向量（specs/teacher-review-publish.md V5 P8/P9、V2、V12）。

- ``embed_snapshot_nodes``：用 E07 适配器为快照里的每个知识点算向量（文本 = 名称 + 换行 + 定义，
  ADR-033）；适配器按「空间 + 文本哈希」缓存，重试不重复计费。
- ``materialize``（P8）：在**一个 Neo4j 写事务**里先删除本 ``(course_id, version_id)`` 已有的副本，
  再建章节、知识点（含当前空间的向量属性）、关系与 ``EVIDENCED_BY`` 来源边。重试同一 ``version_id``
  得到同一张图，不会重复。向量的空间标识必须等于 SQLite 当前空间、维度等于空间维度，否则在
  连库前失败；来源块在 Neo4j 缺失、端点缺失时整体回滚。发布指针不在这里改，学生仍读旧版。
- ``verify``（P9）：读回副本复算摘要（``revisions`` 取自快照本身，它们不物化到 Neo4j），必须等于
  快照摘要；向量数等于知识点数且维度正确。
- ``drop_version``（C1 第 2 步）：删除一个非草稿版本的全部副本，不碰共享文本块。

版本副本只含快照字段、向量与作用域字段，不写状态、置信度、锁、贡献记录（V2）。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, Protocol

from app.repositories.graph_migrations import VectorSpaceError, _dimensions, _validate_vector, vector_property
from app.repositories.neo4j import GraphScope, Neo4jRepository, ScopedTransaction
from app.services.versions.snapshot import Snapshot, canonical_bytes, digest_of

__all__ = [
    "MaterializeError",
    "MaterializeResult",
    "VerificationError",
    "drop_version",
    "embed_snapshot_nodes",
    "materialize",
    "node_embedding_text",
    "verify",
]

DRAFT: Final = "draft"
RELATION_TYPES: Final = ("CONTAINS", "EXAMPLE_OF", "PREREQUISITE", "RELATED_TO")


class Vector(Protocol):
    values: Sequence[float]
    space: str


class Embedder(Protocol):
    space: str

    def embed(self, texts: Sequence[str]) -> Sequence[Vector]: ...


class MaterializeError(RuntimeError):
    """副本没有完整写入（来源块或端点缺失），事务已回滚。"""


class VerificationError(RuntimeError):
    """P9 核对失败：读回的副本与快照不符，或向量不全、维度不对。"""


@dataclass(frozen=True)
class MaterializeResult:
    version_id: str
    space: str
    chapters: int
    nodes: int
    edges: int
    evidence: int


# ---------------------------------------------------------------- vectors


def node_embedding_text(node: Mapping[str, Any]) -> str:
    """知识点向量的输入文本：名称与定义（ADR-033）。"""
    return f"{node['name']}\n{node['definition']}"


def embed_snapshot_nodes(embedder: Embedder, snapshot: Snapshot) -> dict[str, Vector]:
    nodes = list(snapshot.data["nodes"])
    vectors = embedder.embed([node_embedding_text(n) for n in nodes])
    if len(vectors) != len(nodes):
        raise VectorSpaceError("embedding count differs from knowledge point count")
    return {n["kp_id"]: v for n, v in zip(nodes, vectors, strict=True)}


# ---------------------------------------------------------------- P8


def _scope(snapshot: Snapshot, version_id: str) -> GraphScope:
    if not isinstance(version_id, str) or not version_id.strip() or version_id == DRAFT:
        raise ValueError("a published version_id is required")
    return GraphScope(str(snapshot.data["course_id"]), version_id)


# 按标签匹配走 (course_id, version_id) 索引，不做无标签全库扫描。
_DELETE = """
CALL { MATCH (k:KnowledgePoint {course_id: $course_id, version_id: $version_id}) DETACH DELETE k }
CALL { MATCH (c:Chapter {course_id: $course_id, version_id: $version_id}) DETACH DELETE c }
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


def _written(tx: ScopedTransaction, query: str, rows: list[dict[str, Any]], what: str) -> int:
    if not rows:
        return 0
    [record] = tx.run(query, {"rows": rows})
    if record["written"] != len(rows):
        raise MaterializeError(f"{what}: wrote {record['written']} of {len(rows)}")
    return len(rows)


def _no_nulls(row: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in row.items() if v is not None}


def materialize(
    repo: Neo4jRepository,
    snapshot: Snapshot,
    version_id: str,
    vectors: Mapping[str, Vector],
    current_space: Callable[[], str],
) -> MaterializeResult:
    """P8：一个写事务内（重）建 ``(course_id, version_id)`` 的副本。"""
    scope = _scope(snapshot, version_id)
    space = current_space()
    prop = vector_property(space)
    data = snapshot.data

    node_rows = []
    for node in data["nodes"]:
        vector = vectors.get(node["kp_id"])
        if vector is None:
            raise VectorSpaceError(f"knowledge point {node['kp_id']} has no vector")
        row = _no_nulls({k: v for k, v in node.items() if k != "source_refs"})
        row[prop] = _validate_vector(vector, space)
        node_rows.append(row)
    chapter_rows = [_no_nulls(c) for c in data["chapters"]]
    evidence_rows = [{"kp_id": n["kp_id"], "chunk_id": c} for n in data["nodes"] for c in n["source_refs"]]
    edges_by_type: dict[str, list[dict[str, Any]]] = {t: [] for t in RELATION_TYPES}
    for edge in data["edges"]:
        edges_by_type[edge["type"]].append({k: edge[k] for k in ("rel_id", "from_id", "to_id", "source_refs")})

    def work(tx: ScopedTransaction) -> MaterializeResult:
        tx.run(_DELETE)
        chapters = _written(tx, _CHAPTERS, chapter_rows, "chapters")
        nodes = _written(tx, _NODES, node_rows, "knowledge points")
        evidence = _written(tx, _EVIDENCE, evidence_rows, "source links (missing Chunk?)")
        edges = sum(_written(tx, _relations_query(kind), rows, f"{kind} relations")
                    for kind, rows in edges_by_type.items())
        return MaterializeResult(version_id, space, chapters, nodes, edges, evidence)

    return repo.write_transaction(scope, work)


# ---------------------------------------------------------------- P9

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
_NODE_FIELDS: Final = ("aliases", "chapter_id", "definition", "difficulty", "importance", "kp_id", "merged_from",
                       "name", "type")


def verify(repo: Neo4jRepository, snapshot: Snapshot, version_id: str, space: str) -> None:
    """P9：读回副本，复算摘要必须等于快照摘要；每个知识点都有 ``space`` 的向量且维度正确。"""
    scope = _scope(snapshot, version_id)
    prop = vector_property(space)
    dims = _dimensions(space)

    def read(query: str) -> list[dict[str, Any]]:
        return repo.read(query, scope, reader="worker")

    chapters = sorted(
        ({"chapter_id": p.get("chapter_id"), "title": p.get("title"), "order": p.get("order"),
          "parent_id": p.get("parent_id")} for p in (r["p"] for r in read(_READ_CHAPTERS))),
        key=lambda c: str(c["chapter_id"]),
    )
    nodes = []
    missing_vectors = 0
    for record in read(_READ_NODES):
        p = record["p"]
        vector = p.get(prop)
        if not isinstance(vector, list) or len(vector) != dims:
            missing_vectors += 1
        node = {field: p.get(field) for field in _NODE_FIELDS}
        for field in ("aliases", "merged_from"):
            node[field] = sorted(set(node[field] or []))
        node["source_refs"] = sorted(set(record["source_refs"]))
        nodes.append(node)
    nodes.sort(key=lambda n: str(n["kp_id"]))
    edges = sorted(
        ({"rel_id": r["p"].get("rel_id"), "type": r["type"], "from_id": r["from_id"], "to_id": r["to_id"],
          "source_refs": sorted(set(r["p"].get("source_refs") or []))} for r in read(_READ_EDGES)),
        key=lambda e: str(e["rel_id"]),
    )
    if missing_vectors:
        raise VerificationError(f"{missing_vectors} knowledge points lack a {space} vector of {dims} dimensions")
    rebuilt = {**snapshot.data, "chapters": chapters, "nodes": nodes, "edges": edges}
    if digest_of(canonical_bytes(rebuilt)) != snapshot.digest:
        raise VerificationError("materialized version does not match the snapshot digest")


def drop_version(repo: Neo4jRepository, course_id: str, version_id: str) -> None:
    """C1 第 2 步：删除一个非草稿版本的全部副本（可重复执行，不碰共享文本块）。"""
    if not isinstance(version_id, str) or not version_id.strip() or version_id == DRAFT:
        raise ValueError("a published version_id is required")
    repo.write(_DELETE, GraphScope(course_id, version_id))
