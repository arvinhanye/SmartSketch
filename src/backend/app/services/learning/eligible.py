"""Pure eligible-set computation for next-step recommendation (I03); no I/O, no database.

Implements ``specs/learning-path.md`` §2::

    Eligible(V, E, M) = { k ∈ V \\ M | Pred(k) ⊆ M }

``V`` is every ``kp_id`` of one committed graph version, ``E`` its ``PREREQUISITE``
edges only (``(a, b)``: ``a`` is a direct prerequisite of ``b``), and ``M`` the
*projected* mastered set of that version. Projection (merge lineage, overrides,
dormant and dirty rows, ``learning`` not counting as mastered) is done by the caller
before this module (§5, ADR-014 "后果": I03 receives the projected mastered set).
Only direct prerequisites are checked; an out-of-order mastered node satisfies its
successors like any other mastered node, and no prerequisite is ever exempted (§2).

Two steps, so one validated graph can serve many mastered sets (and I04):

- ``build_prerequisite_graph(nodes, edges)`` validates the whole committed graph in
  linear time (plus the sort inside F05's ``find_cycle``) and returns an immutable
  ``PrerequisiteGraph``. Duplicate edges are de-duplicated (§1). Every other defect is
  a committed-version integrity fault (§1, §4) and raises ``GraphIntegrityError``;
  nothing is repaired silently and no partial result is produced. Checks run in a
  fixed order and the first failing one is reported: ``malformed`` → ``empty_graph``
  → ``duplicate_node`` → ``dangling_edge`` → ``self_loop`` → ``cycle``. The cycle
  check reuses F05 ``find_cycle`` (closed path, rotated to its smallest ID).
- ``eligible_set(graph, mastered)`` returns the candidates as a tuple sorted by
  ``kp_id`` UTF-8 byte order ascending. This order exists only to make the result
  deterministic and independent of input order; ranking by
  ``(-score, chapter_rank, kp_id)`` belongs to I04. ``mastered`` must be a subset of
  ``V`` (§1: the pure function only accepts projected keys ⊆ V); any other ID raises
  ``ProgressOutsideGraphError`` instead of being ignored. ``mastered`` is read once
  into a private ``frozenset`` and is never modified.

Error payloads (``kind``, ``ids``) carry internal IDs and cycle paths for server-side
logs only. The student read path (I05) must map both errors to the 5xx integrity
response with a diagnostic ID and must not expose these IDs (§1).
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

from app.services.graph.dag import find_cycle

Edge = tuple[str, str]

IntegrityKind = Literal[
    "malformed", "empty_graph", "duplicate_node", "dangling_edge", "self_loop", "cycle"
]


class GraphIntegrityError(ValueError):
    """The committed graph violates §1 invariants; ``ids`` is for server logs only.

    ``ids`` by ``kind``: ``duplicate_node`` / ``dangling_edge`` / ``self_loop`` list the
    offending IDs sorted by UTF-8 bytes; ``cycle`` is a closed path from F05
    ``find_cycle``; ``empty_graph`` and ``malformed`` carry ``()``.
    """

    def __init__(self, kind: IntegrityKind, ids: tuple[str, ...] = (), detail: str = "") -> None:
        self.kind = kind
        self.ids = ids
        message = f"committed prerequisite graph integrity error: {kind}"
        if detail:
            message += f" ({detail})"
        if ids:
            message += f": {list(ids)!r}"
        super().__init__(message)


class ProgressOutsideGraphError(ValueError):
    """``mastered`` holds IDs outside ``V``; the caller skipped the §5 projection."""

    def __init__(self, ids: tuple[str, ...]) -> None:
        self.ids = ids
        super().__init__(f"mastered IDs are not in the bound graph version: {list(ids)!r}")


@dataclass(frozen=True)
class PrerequisiteGraph:
    """Validated, immutable ``PREREQUISITE`` DAG of one committed version.

    Build it with ``build_prerequisite_graph``; ``predecessors`` maps every node to its
    direct prerequisites (empty ``frozenset`` for roots) and is read-only.
    """

    nodes: frozenset[str]
    edges: frozenset[Edge]
    predecessors: Mapping[str, frozenset[str]]


def build_prerequisite_graph(nodes: Iterable[str], edges: Iterable[Edge]) -> PrerequisiteGraph:
    """Validate one committed version's nodes and prerequisite edges (see module doc)."""
    node_list = [_checked_id(node, "node ID") for node in nodes]
    edge_list = [_checked_edge(edge) for edge in edges]
    if not node_list:
        raise GraphIntegrityError("empty_graph")

    known: set[str] = set()
    duplicates: set[str] = set()
    for node in node_list:
        (duplicates if node in known else known).add(node)
    if duplicates:
        raise GraphIntegrityError("duplicate_node", _utf8_sorted(duplicates))

    edge_set = frozenset(edge_list)
    dangling = {endpoint for edge in edge_set for endpoint in edge if endpoint not in known}
    if dangling:
        raise GraphIntegrityError("dangling_edge", _utf8_sorted(dangling))

    loops = {source for source, target in edge_set if source == target}
    if loops:
        raise GraphIntegrityError("self_loop", _utf8_sorted(loops))

    cycle = find_cycle(known, edge_set)
    if cycle is not None:
        raise GraphIntegrityError("cycle", cycle)

    predecessors: dict[str, set[str]] = {node: set() for node in known}
    for source, target in edge_set:
        predecessors[target].add(source)
    return PrerequisiteGraph(
        nodes=frozenset(known),
        edges=edge_set,
        predecessors=MappingProxyType({k: frozenset(v) for k, v in predecessors.items()}),
    )


def eligible_set(graph: PrerequisiteGraph, mastered: Iterable[str]) -> tuple[str, ...]:
    """Return ``{k ∈ V \\ M | Pred(k) ⊆ M}`` sorted by ``kp_id`` UTF-8 bytes ascending.

    Empty exactly when ``M = V`` (I05 turns that into ``state=all_mastered``); for any
    other ``M`` a DAG always yields at least one candidate.
    """
    if not isinstance(graph, PrerequisiteGraph):
        raise TypeError("graph must be a PrerequisiteGraph from build_prerequisite_graph")
    owned = frozenset(mastered)
    for kp_id in owned:
        if not isinstance(kp_id, str):
            raise TypeError(f"mastered IDs must be strings, got {type(kp_id).__name__}")
    outside = owned - graph.nodes
    if outside:
        raise ProgressOutsideGraphError(_utf8_sorted(outside))
    return _utf8_sorted(
        node
        for node in graph.nodes
        if node not in owned and graph.predecessors[node] <= owned
    )


def _checked_id(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise GraphIntegrityError("malformed", detail=f"{label} must be a non-empty string")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise GraphIntegrityError("malformed", detail=f"{label} is not valid UTF-8") from None
    return value


def _checked_edge(item: object) -> Edge:
    if not isinstance(item, (tuple, list)) or len(item) != 2:
        raise GraphIntegrityError("malformed", detail="each edge must be a (from_id, to_id) pair")
    source, target = item
    return _checked_id(source, "edge endpoint"), _checked_id(target, "edge endpoint")


def _utf8_sorted(ids: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted(ids, key=lambda kp_id: kp_id.encode("utf-8")))
