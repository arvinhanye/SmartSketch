"""J02: bounded, request-version-pinned structural graph search."""
from __future__ import annotations

from dataclasses import dataclass

from app.repositories.neo4j import GraphScope, Neo4jRepository

__all__ = ["GraphSearchResult", "search_graph"]

_NODE = "n {.kp_id, .name, .aliases, .type, .definition, .chapter_id} AS node"
_SEEDS = f"""
MATCH (n:KnowledgePoint {{course_id: $course_id, version_id: $version_id}})
WHERE ($kp_id <> '' AND n.kp_id = $kp_id)
   OR ($term <> '' AND (toLower(coalesce(n.name, '')) CONTAINS $term
       OR any(alias IN coalesce(n.aliases, []) WHERE toLower(alias) CONTAINS $term)))
RETURN {_NODE}
ORDER BY CASE WHEN n.kp_id = $kp_id THEN 0 ELSE 1 END, n.kp_id
LIMIT $limit
"""
_NEIGHBORS = f"""
MATCH (a:KnowledgePoint {{course_id: $course_id, version_id: $version_id}})
      -[r {{course_id: $course_id, version_id: $version_id}}]-
      (n:KnowledgePoint {{course_id: $course_id, version_id: $version_id}})
WHERE a.kp_id IN $frontier AND NOT n.kp_id IN $known
  AND type(r) IN ['CONTAINS', 'PREREQUISITE', 'RELATED_TO', 'EXAMPLE_OF']
RETURN DISTINCT n.kp_id AS kp_id, {_NODE}
ORDER BY kp_id
LIMIT $limit
"""
_EDGES = """
MATCH (a:KnowledgePoint {course_id: $course_id, version_id: $version_id})
      -[r {course_id: $course_id, version_id: $version_id}]->
      (b:KnowledgePoint {course_id: $course_id, version_id: $version_id})
WHERE a.kp_id IN $ids AND b.kp_id IN $ids
  AND type(r) IN ['CONTAINS', 'PREREQUISITE', 'RELATED_TO', 'EXAMPLE_OF']
RETURN a.kp_id AS from_id, b.kp_id AS to_id, type(r) AS type, r.rel_id AS rel_id
ORDER BY from_id, to_id, type, rel_id
LIMIT $limit
"""


@dataclass(frozen=True)
class GraphSearchResult:
    nodes: list[dict]
    edges: list[dict]


def search_graph(
    repo: Neo4jRepository,
    scope: GraphScope,
    *,
    term: str = "",
    kp_id: str | None = None,
    max_hops: int = 2,
    max_nodes: int = 32,
    max_edges: int = 128,
) -> GraphSearchResult:
    """Find a small published subgraph. The caller authenticates and binds once via G07.

    An unknown ``kp_id`` is ignored; it never becomes evidence or changes scope.
    Traversal treats structural relationships as adjacency but returns their stored direction.
    """
    if not isinstance(term, str) or (kp_id is not None and not isinstance(kp_id, str)):
        raise ValueError("term and kp_id must be strings")
    term = term.strip().lower()
    kp_id = (kp_id or "").strip()
    if not term and not kp_id:
        raise ValueError("term or kp_id is required")
    if (type(max_hops) is not int or not 0 <= max_hops <= 2
            or type(max_nodes) is not int or not 1 <= max_nodes <= 32
            or type(max_edges) is not int or not 0 <= max_edges <= 128):
        raise ValueError("graph search limits exceed J02 bounds")
    if not isinstance(scope, GraphScope) or scope.version_id == "draft":
        raise ValueError("a published graph scope is required")

    rows = repo.read(_SEEDS, scope, reader="student",
                     parameters={"kp_id": kp_id, "term": term, "limit": max_nodes})
    nodes = {row["node"]["kp_id"]: row["node"] for row in rows}
    frontier = list(nodes)
    for _ in range(max_hops):
        remaining = max_nodes - len(nodes)
        if not frontier or remaining == 0:
            break
        rows = repo.read(_NEIGHBORS, scope, reader="student",
                         parameters={"frontier": frontier, "known": list(nodes), "limit": remaining})
        frontier = []
        for row in rows:
            node = row["node"]
            if node["kp_id"] not in nodes:
                nodes[node["kp_id"]] = node
                frontier.append(node["kp_id"])
    if not nodes or not max_edges:
        return GraphSearchResult([nodes[k] for k in sorted(nodes)], [])
    edges = repo.read(_EDGES, scope, reader="student",
                      parameters={"ids": list(nodes), "limit": max_edges})
    return GraphSearchResult([nodes[k] for k in sorted(nodes)], edges)
