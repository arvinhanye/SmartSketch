"""Complete-link semantic groups and lossless, graph-checked draft projections."""
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
import hashlib
import json

from app.repositories.graph_relations import derive_rel_id
from app.services.fusion.resolution import SemanticDecision
from app.services.graph.dag import find_cycle

RELATIONS = frozenset({"CONTAINS", "PREREQUISITE", "RELATED_TO", "EXAMPLE_OF"})


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def fingerprint(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def validate_snapshot(snapshot: Mapping) -> None:
    course = snapshot["course_id"]
    nodes = snapshot["nodes"]
    ids = {n["kp_id"] for n in nodes}
    if not course or len(ids) != len(nodes) or any(n.get("course_id") != course for n in nodes):
        raise ValueError("invalid node scope or duplicate ID")
    for edge in snapshot["edges"]:
        if (edge["type"] not in RELATIONS or edge["from_id"] not in ids or edge["to_id"] not in ids
                or edge["p"].get("course_id") != course):
            raise ValueError("invalid edge scope or endpoint")
    if any(e["kp_id"] not in ids for e in snapshot["evidence"]):
        raise ValueError("invalid evidence endpoint")


def _cycle(snapshot: Mapping):
    return find_cycle((n["kp_id"] for n in snapshot["nodes"]),
                      [(e["from_id"], e["to_id"]) for e in snapshot["edges"]
                       if e["type"] == "PREREQUISITE" and e["p"].get("status") != "rejected"])


def _protected_relation(p):
    return p.get('contrib_manual') or p.get('source') == 'manual' or p.get('status') in ('approved', 'rejected')


def project_snapshot(snapshot: Mapping, mapping: Mapping[str, str]) -> dict:
    """Preserve every source/contribution; reject collapsing any explicit relationship."""
    validate_snapshot(snapshot)
    result = deepcopy(dict(snapshot))
    by_id = {n["kp_id"]: n for n in result["nodes"]}
    if set(mapping) != set(by_id) or any(v not in by_id or mapping[v] != v for v in mapping.values()):
        raise ValueError("invalid canonical map")
    buckets: dict[str, list[dict]] = {}
    for old, new in mapping.items(): buckets.setdefault(new, []).append(by_id[old])
    merged_nodes = []
    for new, members in sorted(buckets.items()):
        node = by_id[new]
        if len(members) > 1:
            aliases = {s for n in members for s in [n["name"], *n.get("aliases", [])] if s != node["name"]}
            node["aliases"] = sorted(aliases)
            node["contrib_tasks"] = sorted({t for n in members for t in n.get("contrib_tasks", [])})
            node["merged_from"] = sorted({i for n in members for i in [n["kp_id"], *n.get("merged_from", [])]} - {new})
            node["revision"] = int(node.get("revision", 1)) + 1
        merged_nodes.append(node)
    result["nodes"] = merged_nodes
    evidence = {}
    for e in result["evidence"]:
        e["kp_id"] = mapping[e["kp_id"]]
        evidence[canonical_json(e)] = e
    result["evidence"] = [evidence[k] for k in sorted(evidence)]
    edges: dict[tuple, dict] = {}
    for e in result["edges"]:
        old_a, old_b = e["from_id"], e["to_id"]
        a, b = mapping[old_a], mapping[old_b]
        if a == b:
            raise ValueError("merge_self_loop")
        if (a, b) != (old_a, old_b) and _protected_relation(e['p']):
            raise ValueError('protected_relation')
        e["from_id"], e["to_id"] = a, b
        if (a, b) != (old_a, old_b):
            e["p"]["rel_id"] = derive_rel_id(snapshot["course_id"], e["type"], a, b)
        key = (e["type"], a, b)
        if key not in edges:
            edges[key] = e
        else:
            p, incoming = edges[key]["p"], e["p"]
            if _protected_relation(p) or _protected_relation(incoming):
                raise ValueError('protected_relation')
            if any(p.get(k) != incoming.get(k) for k in ("status", "source", "contrib_manual")):
                raise ValueError("relation_semantics_conflict")
            for k in ("contrib_tasks", "chunk_ids", "source_pairs"):
                p[k] = sorted(set(p.get(k, [])) | set(incoming.get(k, [])))
            p["confidence"] = max(p.get("confidence", 0), incoming.get("confidence", 0))
    result["edges"] = [edges[k] for k in sorted(edges)]
    if _cycle(result): raise ValueError("merge_prerequisite_cycle")
    return result


@dataclass(frozen=True)
class MappingPlan:
    mapping: dict[str, str]
    groups: tuple[tuple[str, ...], ...]
    blocked: tuple[dict, ...]
    snapshot: dict = field(repr=False)


def plan_mapping(snapshot: Mapping, decisions: Sequence[SemanticDecision], *, existing_ids: Iterable[str],
                 member_ids: Mapping[str, Sequence[str]] | None = None,
                 candidate_pairs: Sequence[tuple[str, str]] | None = None,
                 forbidden_pairs: Iterable[tuple[str, str]] = (), protected_ids: Iterable[str] = ()) -> MappingPlan:
    validate_snapshot(snapshot)
    nodes = {n["kp_id"]: n for n in snapshot["nodes"]}
    existing = set(existing_ids)
    if not existing <= set(nodes): raise ValueError("unknown existing node")
    mapping = {k: k for k in nodes}
    group = {k: {k} for k in nodes}
    # A collapsed node is a group, never a new singleton. Missing provenance blocks expansion.
    lineage = {k: tuple(sorted({k, *n.get('merged_from', [])})) for k, n in nodes.items()}
    supplied = {k: tuple(sorted(v)) for k, v in (member_ids or {}).items()}
    unknown = {k for k, ids in lineage.items() if len(ids)>1 and supplied.get(k) != ids}
    allowed = set(nodes) | {i for ids in lineage.values() for i in ids}
    forbidden = {tuple(sorted(pair)) for pair in forbidden_pairs}
    protected = set(protected_ids)
    atom_verified: set[tuple[str, str]] = set()
    seen: dict[tuple[str, str], SemanticDecision] = {}
    for d in decisions:
        pair = tuple(sorted((d.left_id, d.right_id)))
        if len(set(pair)) != 2 or any(k not in allowed for k in pair): raise ValueError("invalid decision endpoints")
        if pair in seen and seen[pair] != d: raise ValueError("conflicting decisions")
        seen[pair] = d
        if (d.status == "complete" and d.verdict == "SAME" and d.code is None and d.model_calls >= 2
                and d.left_source_ids and d.right_source_ids and d.prompt_sha256):
            atom_verified.add(pair)
    proposals = candidate_pairs if candidate_pairs is not None else [p for p in seen if set(p) <= set(nodes)]
    verified = set()
    blocked = []
    for a, b in proposals:
        if a not in nodes or b not in nodes or a == b: raise ValueError('invalid candidate pair')
        atoms = set(lineage[a]) | set(lineage[b])
        if a in unknown or b in unknown:
            blocked.append(dict(members=sorted((a,b)), reason='unverified_lineage')); continue
        if atoms & protected or any(set(pair) <= atoms for pair in forbidden):
            blocked.append(dict(members=sorted((a,b)), reason='teacher_decision')); continue
        if all(tuple(sorted((x,y))) in atom_verified for x in lineage[a] for y in lineage[b]):
            verified.add(tuple(sorted((a,b))))
        elif len(atoms)>2:
            blocked.append(dict(members=sorted((a,b)), reason='unverified_group'))
    projected = deepcopy(dict(snapshot))
    for a, b in sorted(verified):
        ga, gb = group[mapping[a]], group[mapping[b]]
        if ga == gb: continue
        members = ga | gb
        reason = None
        atoms = {i for k in members for i in lineage[k]}
        if atoms & protected or any(set(pair) <= atoms for pair in forbidden):
            reason = 'teacher_decision'
        elif any(nodes[k].get("locked") or nodes[k].get("contrib_manual") or
               nodes[k].get("source") == "manual" or nodes[k].get("status") in ("approved", "rejected") for k in members):
            reason = "protected_node"
        elif any(tuple(sorted((x, y))) not in verified for x in ga for y in gb):
            reason = "unverified_group"
        if reason:
            blocked.append(dict(members=sorted(members), reason=reason)); continue
        canonical = min(members, key=lambda k: (k not in existing, k))
        tentative = {k: canonical if v in (mapping[a], mapping[b]) else v for k, v in mapping.items()}
        try:
            candidate = project_snapshot(snapshot, tentative)
        except ValueError as exc:
            blocked.append(dict(members=sorted(members), reason=str(exc))); continue
        old_a, old_b = mapping[a], mapping[b]
        group.pop(old_a); group.pop(old_b)
        group[canonical] = members
        mapping, projected = tentative, candidate
    return MappingPlan(mapping, tuple(sorted(tuple(sorted(g)) for g in group.values() if len(g) > 1)),
                       tuple(blocked), projected)
