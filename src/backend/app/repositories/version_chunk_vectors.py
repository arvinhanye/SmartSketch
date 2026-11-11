"""G08：共享文本块与向量的持久化；向量生成与完整性校验由版本服务负责。"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from typing import Any, TypeVar

from app.repositories.chunks import StoredChunk, list_chunks
from app.repositories.graph_migrations import _dimensions, vector_property
from app.repositories.neo4j import GraphScope, Neo4jRepository, ScopedTransaction

T = TypeVar("T")


def _missing_query(prop: str) -> str:
    # $version_id 只满足作用域参数约定：文本块跨版本共享。
    return f"""
UNWIND $expected AS row
OPTIONAL MATCH (c:Chunk {{course_id: $course_id, chunk_id: row.chunk_id}})
WITH row, c, $version_id AS version_id
WHERE c IS NULL OR c.revision_id IS NULL OR c.revision_id <> row.revision_id
   OR c.document_id IS NULL OR c.document_id <> row.document_id
   OR c.{prop} IS NULL OR size(c.{prop}) <> $dims
RETURN row.chunk_id AS chunk_id
"""


def _write_query(prop: str) -> str:
    return f"""
UNWIND $rows AS row
MERGE (c:Chunk {{course_id: $course_id, chunk_id: row.chunk_id}})
SET c.document_id = row.document_id, c.revision_id = row.revision_id, c.{prop} = row.vector
RETURN count(c) AS written, $version_id AS version_id
"""


def _chunks(sqlite_url: str, course_id: str, revision_ids: Iterable[str]) -> list[StoredChunk]:
    chunks: list[StoredChunk] = []
    for revision_id in sorted(set(revision_ids)):
        chunks.extend(list_chunks(sqlite_url, course_id=course_id, revision_id=revision_id))
    return chunks


def _missing(repo: Neo4jRepository, scope: GraphScope, chunks: Sequence[StoredChunk], space: str) -> set[str]:
    """缺节点、身份（``revision_id``、``document_id``）与 SQLite 不符、缺向量或维度不对的块。"""
    if not chunks:
        return set()
    expected = [{"chunk_id": c.chunk_id, "revision_id": c.revision_id, "document_id": c.material_id}
                for c in chunks]
    rows = repo.read(_missing_query(vector_property(space)), scope, reader="worker",
                     parameters={"expected": expected, "dims": _dimensions(space)})
    return {row["chunk_id"] for row in rows}


_INDEX_STATE = """
SHOW VECTOR INDEXES YIELD name, state
WHERE name = $index
RETURN state, $course_id AS course_id, $version_id AS version_id
"""


def _index_online(repo: Neo4jRepository, scope: GraphScope, space: str) -> bool:
    rows = repo.read(_INDEX_STATE, scope, reader="worker",
                     parameters={"index": "chunk_" + vector_property(space)})
    return any(row["state"] == "ONLINE" for row in rows)


def transaction(repo: Neo4jRepository, scope: GraphScope, work: Callable[[ScopedTransaction], T]) -> T:
    """每批一个写事务，包含服务回调中的写入计数核对。"""
    return repo.write_transaction(scope, work)


def write_batch(tx: ScopedTransaction, prop: str, rows: list[dict[str, Any]]) -> int:
    [row] = tx.run(_write_query(prop), {"rows": rows})
    return row["written"]
