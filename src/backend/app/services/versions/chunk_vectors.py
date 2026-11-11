"""G08：发布时补齐文本块向量（ADR-066；specs/teacher-review-publish.md V5 P8/P9、V8「向量检索」）。

文本块不可变、各版本共享（ADR-012 修订 1），向量属于 ``(course_id, chunk_id)`` 的 ``Chunk`` 节点。
抽取阶段（F04）只为被知识点引用的块建节点，不写向量；J01 检索却要覆盖版本内的全部文本块。

- ``index_chunks``：P8 中、写副本之前调用。按快照的修订列表从 SQLite 读出全部文本块，查出 Neo4j 中
  还没有当前空间向量（或维度不对）的块，只为这些块调用向量模型，再分批 ``MERGE`` 节点并写向量。
  节点的 ``revision_id``、``document_id`` 缺失或与 SQLite 不符时一并改正（J01 按修订过滤；块 ID 由修订派生，改正是安全的）。可重复执行；块内容不可变，已有向量不重算。发布失败时写入的节点与向量保留，不属于版本副本，C1 不删除。
- ``verify_chunks``：P9 中核对这些块的身份与向量，并核对该空间的文本块向量索引在线；否则 ``VerificationError``。
  索引由部署时的 ``python -m app.repositories.graph_migrations`` 创建（ADR-055）。

回滚不调用本模块：源版本发布时已补齐，且回滚不得调用向量模型（PUB-26）。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Final

from app.repositories import version_chunk_vectors as chunk_repo
from app.repositories.version_chunk_vectors import _chunks, _index_online, _missing
from app.repositories.graph_migrations import VectorSpaceError, _validate_vector, vector_property
from app.repositories.neo4j import GraphScope, Neo4jRepository, ScopedTransaction
from app.services.versions.materialize import Embedder, VerificationError

__all__ = ["DEFAULT_BATCH_SIZE", "ChunkIndexResult", "index_chunks", "verify_chunks"]

DEFAULT_BATCH_SIZE: Final = 200  # 每个 Neo4j 写事务的块数


@dataclass(frozen=True)
class ChunkIndexResult:
    total: int  # 版本修订内的文本块数
    embedded: int  # 本次新算向量的块数


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
    missing = _missing(repo, scope, chunks, space)
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
    prop = vector_property(space)
    for start in range(0, len(rows), batch_size):
        batch = rows[start:start + batch_size]

        def work(tx: ScopedTransaction, batch: list[dict[str, Any]] = batch) -> None:
            written = chunk_repo.write_batch(tx, prop, batch)
            if written != len(batch):
                raise VectorSpaceError("chunk vector write count differs from the batch")

        chunk_repo.transaction(repo, scope, work)
    return ChunkIndexResult(len(chunks), len(todo))


def verify_chunks(
    sqlite_url: str, repo: Neo4jRepository, scope: GraphScope, revision_ids: Iterable[str], space: str
) -> None:
    """P9：每个文本块都有节点、与 SQLite 一致的身份和 ``space`` 的向量；该空间的文本块向量索引在线（ADR-055）。"""
    chunks = _chunks(sqlite_url, scope.course_id, revision_ids)
    missing = _missing(repo, scope, chunks, space)
    if missing:
        raise VerificationError(f"{len(missing)} text chunks lack a {space} vector or have a wrong identity")
    if chunks and not _index_online(repo, scope, space):
        raise VerificationError(f"chunk vector index of {space} is missing or not online; "
                                "run python -m app.repositories.graph_migrations")
