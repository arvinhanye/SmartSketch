"""Pure DAG cycle checks for ``PREREQUISITE`` edges (F05); no I/O, no database.

Callers own the edge selection rules of ``specs/course-knowledge-graph.md``
「前置关系成环处理」: pass only one course's knowledge-point IDs as ``nodes`` and only
that course's ``type = PREREQUISITE`` edges with ``status != rejected`` as ``edges``.
An edge is ``(from_id, to_id)``: ``from_id`` must be learned before ``to_id``.
To re-check an edited edge (retype, re-point, reverse, restore from ``rejected``,
re-wire after a merge), remove its old form from ``edges`` and pass the new form as a
candidate. This module does not implement the ADR-009 auto-downgrade loop (F13); it
only answers "legal, or which cycle".

Cycle paths are *closed*: the first and last items are the same ID and there are at
least two items (a self-loop ``A→A`` is ``("A", "A")``). This matches the B11 contract
fields marked ``x-closed-cycle: true`` (``CYCLE_DETECTED.details.cycle``,
``PublishBlockedCycleReason.cycle``, ``Relation.downgrade_cycle``). Apart from the
closing repeat, no ID appears twice.

Determinism: results depend only on the *sets* of nodes, edges and candidates, never
on their iteration order or duplicates.

- ``find_cycle`` runs DFS from roots in ascending ID order, visiting successors in
  ascending ID order, and returns the first cycle found, rotated to start at the
  smallest ID on it.
- ``check_candidates`` first runs ``find_cycle`` on the existing edges. If they are
  already cyclic (the draft violates the invariant, DAG-10), that cycle is returned
  with ``edge=None``. Otherwise candidates are added one at a time in ascending
  ``(from_id, to_id)`` order; the first one that closes a cycle is reported with the
  shortest cycle through it, starting at its ``from_id``: ``(u, v, ..., u)``. Among
  equally short paths ``v ... u``, BFS expanding successors in ascending ID order
  decides.

Complexity (V nodes, E distinct existing edges, k distinct candidates): building the
sorted adjacency is O(V + E log E); ``find_cycle`` is O(V + E) after that; each
candidate costs one BFS, O(V + E + k). Overall ``check_candidates`` is
O(V + E log E + k log k + k * (V + E + k)) time and O(V + E + k) memory; a single
candidate is O(V + E log E). Both traversals are iterative, so path length is bounded
by memory, not by Python's recursion limit.
"""

from bisect import insort
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass

Edge = tuple[str, str]

_GRAY = 1  # on the current DFS path
_BLACK = 2  # fully explored, no cycle reachable through it


class UnknownNodeError(ValueError):
    """An edge endpoint is not in ``nodes`` (for example another course's ID)."""


@dataclass(frozen=True)
class CycleCheck:
    """``ok`` is True iff no cycle; otherwise ``cycle`` is a closed ID path.

    ``edge`` is the candidate that closed the cycle, or ``None`` when the existing
    edges were already cyclic (or when ``ok`` is True).
    """

    ok: bool
    cycle: tuple[str, ...] | None = None
    edge: Edge | None = None


def find_cycle(nodes: Iterable[str], edges: Iterable[Edge]) -> tuple[str, ...] | None:
    """Return one closed cycle in the whole graph, or ``None`` if it is a DAG.

    Intended for full re-checks such as the pre-publish check (G04 ``PUBLISH_BLOCKED``).
    Raises ``UnknownNodeError`` for endpoints outside ``nodes``; ``TypeError`` /
    ``ValueError`` for malformed IDs or edges.
    """
    known = _node_set(nodes)
    return _first_cycle(_adjacency(known, _edge_set(edges, known, "edge")))


def check_candidates(
    nodes: Iterable[str], edges: Iterable[Edge], candidates: Iterable[Edge]
) -> CycleCheck:
    """Check whether adding ``candidates`` to ``edges`` keeps the graph acyclic.

    Intended for teacher edits (F06, ``CYCLE_DETECTED``), including multi-edge
    re-wiring after a knowledge-point merge. See the module docstring for which cycle
    is reported and in what rotation.
    """
    known = _node_set(nodes)
    existing = _edge_set(edges, known, "edge")
    pending = sorted(_edge_set(candidates, known, "candidate"))
    adjacency = _adjacency(known, existing)

    cycle = _first_cycle(adjacency)
    if cycle is not None:
        return CycleCheck(ok=False, cycle=cycle, edge=None)

    for edge in pending:
        if edge in existing:
            continue  # already part of an acyclic graph
        source, target = edge
        if source == target:
            return CycleCheck(ok=False, cycle=(source, source), edge=edge)
        back = _shortest_path(adjacency, target, source)
        if back is not None:
            return CycleCheck(ok=False, cycle=(source, *back), edge=edge)
        insort(adjacency[source], target)
        existing.add(edge)
    return CycleCheck(ok=True)


def _node_set(nodes: Iterable[str]) -> set[str]:
    known: set[str] = set()
    for node in nodes:
        if not isinstance(node, str):
            raise TypeError(f"node IDs must be strings, got {type(node).__name__}")
        if not node:
            raise ValueError("node IDs must be non-empty")
        known.add(node)
    return known


def _edge_set(edges: Iterable[Edge], known: set[str], label: str) -> set[Edge]:
    result: set[Edge] = set()
    for item in edges:
        if not isinstance(item, (tuple, list)):
            raise TypeError(f"each {label} must be a (from_id, to_id) pair")
        if len(item) != 2:
            raise ValueError(f"each {label} must be a (from_id, to_id) pair")
        source, target = item
        for endpoint in (source, target):
            if not isinstance(endpoint, str):
                raise TypeError(f"{label} endpoints must be strings")
            if endpoint not in known:
                raise UnknownNodeError(f"{label} endpoint {endpoint!r} is not a known node")
        result.add((source, target))
    return result


def _adjacency(known: set[str], edges: set[Edge]) -> dict[str, list[str]]:
    successors: dict[str, list[str]] = {node: [] for node in known}
    for source, target in edges:
        successors[source].append(target)
    for targets in successors.values():
        targets.sort()
    return successors


def _first_cycle(adjacency: dict[str, list[str]]) -> tuple[str, ...] | None:
    state: dict[str, int] = {}
    for root in sorted(adjacency):
        if root in state:
            continue
        state[root] = _GRAY
        path = [root]
        position = {root: 0}
        frames = [iter(adjacency[root])]
        while frames:
            for successor in frames[-1]:
                seen = state.get(successor)
                if seen is None:
                    state[successor] = _GRAY
                    position[successor] = len(path)
                    path.append(successor)
                    frames.append(iter(adjacency[successor]))
                    break
                if seen == _GRAY:
                    return _closed(path[position[successor]:])
            else:
                done = path.pop()
                del position[done]
                state[done] = _BLACK
                frames.pop()
    return None


def _closed(cycle: list[str]) -> tuple[str, ...]:
    start = cycle.index(min(cycle))
    rotated = cycle[start:] + cycle[:start]
    return (*rotated, rotated[0])


def _shortest_path(adjacency: dict[str, list[str]], source: str, target: str) -> list[str] | None:
    parent: dict[str, str] = {}
    visited = {source}
    queue = deque([source])
    while queue:
        node = queue.popleft()
        for successor in adjacency[node]:
            if successor in visited:
                continue
            visited.add(successor)
            parent[successor] = node
            if successor == target:
                path = [target]
                while path[-1] != source:
                    path.append(parent[path[-1]])
                path.reverse()
                return path
            queue.append(successor)
    return None
