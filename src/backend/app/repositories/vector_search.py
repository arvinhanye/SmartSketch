"""J01：按绑定的已发布版本检索文本块向量（specs/teacher-review-publish.md V8「向量检索」；ADR-046）。

文本块向量各版本共享，Neo4j 向量索引又做不到先过滤再检索，所以采用「多取再过滤」：
向 ``chunk_embedding_<suffix>`` 索引取 ``k`` 个最近邻，只保留 ``course_id`` 等于请求课程、
``revision_id`` 属于绑定版本修订列表的文本块（不按 ``material_id``，Codex A04-R01）。
过滤后不足 ``limit`` 条且索引还有更多结果时按 ``fetch_factor`` 倍扩大 ``k`` 重查，
直到凑满、索引取尽或到达 ``max_fetch``；封顶时记告警，返回已有结果。

``score`` 是 Neo4j 余弦相似度归一到 ``[0, 1]`` 后的值（``(1 + cos) / 2``），阈值判断归 J04。
可定位（Q3.1 第 3 条）要看 SQLite 中的块定位信息，也归 J04 / J06。
"""

from __future__ import annotations

import logging
from collections.abc import Collection
from dataclasses import dataclass
from typing import Final

from app.repositories.graph_migrations import Vector, _validate_vector, vector_property
from app.repositories.neo4j import GraphScope, GraphScopeError, Neo4jRepository

__all__ = ["DEFAULT_FETCH_FACTOR", "DEFAULT_MAX_FETCH", "ChunkHit", "search_chunks"]

logger = logging.getLogger(__name__)

DRAFT: Final = "draft"
DEFAULT_FETCH_FACTOR: Final = 4  # 占位值，ADR-046；召回实测后由 J04 调整
DEFAULT_MAX_FETCH: Final = 1000  # 占位值，ADR-046

# $version_id 只满足作用域参数约定：文本块跨版本共享，版本由修订列表过滤。
_QUERY = """
CALL db.index.vector.queryNodes($index, $k, $vector) YIELD node, score
WITH collect({node: node, score: score}) AS found
RETURN size(found) AS fetched, $version_id AS version_id,
       [x IN found WHERE x.node.course_id = $course_id AND x.node.revision_id IN $revision_ids
        | {chunk_id: x.node.chunk_id, revision_id: x.node.revision_id,
           document_id: x.node.document_id, score: x.score}] AS hits
"""


@dataclass(frozen=True)
class ChunkHit:
    """一个通过课程与版本过滤的文本块候选。"""

    chunk_id: str
    revision_id: str
    document_id: str | None
    score: float


def _positive_int(name: str, value: object) -> int:
    if type(value) is not int or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


def search_chunks(
    repo: Neo4jRepository,
    scope: GraphScope,
    revision_ids: Collection[str],
    vector: Vector,
    *,
    space: str,
    limit: int,
    fetch_factor: int = DEFAULT_FETCH_FACTOR,
    max_fetch: int = DEFAULT_MAX_FETCH,
) -> tuple[ChunkHit, ...]:
    """返回至多 ``limit`` 个属于 ``scope.course_id`` 且修订在 ``revision_ids`` 内的文本块，按相似度降序。

    ``scope`` 是 G07 绑定的已发布版本（``PublishedVersion.graph_scope()``），``revision_ids`` 是它的修订列表；
    ``space`` 是当前向量空间，查询向量必须属于它（V12）。
    """
    limit = _positive_int("limit", limit)
    fetch_factor = _positive_int("fetch_factor", fetch_factor)
    max_fetch = _positive_int("max_fetch", max_fetch)
    if fetch_factor < 2:
        raise ValueError("fetch_factor must be at least 2")
    if max_fetch < limit:
        raise ValueError("max_fetch must be at least limit")
    if not isinstance(scope, GraphScope) or scope.version_id == DRAFT:
        raise GraphScopeError("vector search requires a published version scope")
    values = _validate_vector(vector, space)
    revisions = sorted({r for r in revision_ids if isinstance(r, str) and r})
    if not revisions:
        return ()
    index = "chunk_" + vector_property(space)
    k = min(limit * fetch_factor, max_fetch)
    while True:
        [row] = repo.read(_QUERY, scope, reader="student",
                          parameters={"index": index, "k": k, "vector": values, "revision_ids": revisions})
        hits = row["hits"]
        if len(hits) >= limit or row["fetched"] < k:
            break
        if k >= max_fetch:
            logger.warning("vector search for course %s hit max_fetch=%d with %d of %d hits",
                           scope.course_id, max_fetch, len(hits), limit)
            break
        k = min(k * fetch_factor, max_fetch)
    ranked = sorted(hits, key=lambda h: (-h["score"], h["chunk_id"]))[:limit]
    return tuple(ChunkHit(h["chunk_id"], h["revision_id"], h["document_id"], float(h["score"])) for h in ranked)
