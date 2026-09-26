"""G08：发布时补齐文本块向量（ADR-047；specs/teacher-review-publish.md V5 P8/P9、V8「向量检索」）。

文本块不可变、各版本共享（ADR-012 修订 1），向量属于 ``(course_id, chunk_id)`` 的 ``Chunk`` 节点。
抽取阶段（F04）只为被知识点引用的块建节点，不写向量；J01 检索却要覆盖版本内的全部文本块。

- ``index_chunks``：P8 中、写副本之前调用。按快照的修订列表从 SQLite 读出全部文本块，查出 Neo4j 中
  还没有当前空间向量（或维度不对）的块，只为这些块调用向量模型，再分批 ``MERGE`` 节点并写向量。
  缺 ``revision_id`` 的旧节点一并补上（J01 按它过滤）。可重复执行；块内容不可变，已有向量不重算。发布失败时写入的节点与向量保留，不属于版本副本，C1 不删除。
- ``verify_chunks``：P9 中核对这些块都有当前空间、维度正确的向量，缺失即 ``VerificationError``。

回滚不调用本模块：源版本发布时已补齐，且回滚不得调用向量模型（PUB-26）。
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Final

from app.repositories.chunks import StoredChunk, list_chunks
from app.repositories.graph_migrations import VectorSpaceError, _dimensions, _validate_vector, vector_property
from app.repositories.neo4j import GraphScope, Neo4jRepository, ScopedTransaction
from app.services.versions.materialize import Embedder, VerificationError

__all__ = ["DEFAULT_BATCH_SIZE", "ChunkIndexResult", "index_chunks", "verify_chunks"]

DEFAULT_BATCH_SIZE: Final = 200  # 每个 Neo4j 写事务的块数


@dataclass(frozen=True)
class ChunkIndexResult:
    total: int  # 版本修订内的文本块数
    embedded: int  # 本次新算向量的块数


def _missing_query(prop: str) -> str:
    # $version_id 只满足作用域参数约定：文本块跨版本共享。
    return f"""
UNWIND $chunk_ids AS id
OPTIONAL MATCH (c:Chunk {{course_id: $course_id, chunk_id: id}})
WITH id, c, $version_id AS version_id
WHERE c IS NULL OR c.revision_id IS NULL OR c.{prop} IS NULL OR size(c.{prop}) <> $dims
RETURN id AS chunk_id
"""


def _write_query(prop: str) -> str:
    return f"""
UNWIND $rows AS row
MERGE (c:Chunk {{course_id: $course_id, chunk_id: row.chunk_id}})
SET c.document_id = coalesce(c.document_id, row.document_id),
    c.revision_id = coalesce(c.revision_id, row.revision_id), c.{prop} = row.vector
RETURN count(c) AS written, $version_id AS version_id
"""


def _chunks(sqlite_url: str, course_id: str, revision_ids: Iterable[str]) -> list[StoredChunk]:
    chunks: list[StoredChunk] = []
    for revision_id in sorted(set(revision_ids)):
        chunks.extend(list_chunks(sqlite_url, course_id=course_id, revision_id=revision_id))
    return chunks


def _missing(repo: Neo4jRepository, scope: GraphScope, chunk_ids: Sequence[str], space: str) -> set[str]:
    if not chunk_ids:
        return set()
    rows = repo.read(_missing_query(vector_property(space)), scope, reader="worker",
                     parameters={"chunk_ids": list(chunk_ids), "dims": _dimensions(space)})
    return {row["chunk_id"] for row in rows}


def index_chunks(
    sqlite_url: str,
    repo: Neo4jRepository,
    embedder: Embedder,
    scope: GraphScope,
    revision_ids: Iterable[str],
    space: str,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> ChunkIndexResult:
    """为 ``revision_ids`` 的全部文本块补齐 ``space`` 向量，只对缺失的块调用 ``embedder``。"""
    if type(batch_size) is not int or batch_size < 1:
        raise ValueError("batch_size must be a positive integer")
    if embedder.space != space:
        raise VectorSpaceError(f"embedder space {embedder.space!r} differs from current space {space!r}")
    chunks = _chunks(sqlite_url, scope.course_id, revision_ids)
    missing = _missing(repo, scope, [c.chunk_id for c in chunks], space)
    todo = [c for c in chunks if c.chunk_id in missing]
    if not todo:
        return ChunkIndexResult(len(chunks), 0)
    vectors = embedder.embed([c.text for c in todo])
    if len(vectors) != len(todo):
        raise VectorSpaceError("embedding count differs from chunk count")
    rows: list[dict[str, Any]] = [
        {"chunk_id": c.chunk_id, "document_id": c.material_id, "revision_id": c.revision_id,
         "vector": _validate_vector(v, space)}
        for c, v in zip(todo, vectors, strict=True)
    ]
    query = _write_query(vector_property(space))
    for start in range(0, len(rows), batch_size):
        batch = rows[start:start + batch_size]

        def work(tx: ScopedTransaction, batch: list[dict[str, Any]] = batch) -> None:
            [row] = tx.run(query, {"rows": batch})
            if row["written"] != len(batch):
                raise VectorSpaceError("chunk vector write count differs from the batch")

        repo.write_transaction(scope, work)
    return ChunkIndexResult(len(chunks), len(todo))


def verify_chunks(
    sqlite_url: str, repo: Neo4jRepository, scope: GraphScope, revision_ids: Iterable[str], space: str
) -> None:
    """P9：``revision_ids`` 的每个文本块都有节点、``revision_id`` 与 ``space`` 的向量，且维度正确。"""
    chunks = _chunks(sqlite_url, scope.course_id, revision_ids)
    missing = _missing(repo, scope, [c.chunk_id for c in chunks], space)
    if missing:
        raise VerificationError(f"{len(missing)} text chunks lack a {space} vector")
