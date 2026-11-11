"""ADR-097: explicit, preview-bound deletion of orphaned CONTAINS descendants.

Preview and delete recompute the same finite plan under the course and draft locks.
The digest is a concurrency check, not authorization; API checks the teacher each time.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections import deque
from dataclasses import dataclass
from typing import Any

from app.repositories import graph_edit
from app.repositories.neo4j import GraphScope, ScopedTransaction
from app.schemas.contracts import KnowledgePointDeletion, KnowledgePointDeletionNode
from app.services.access import not_found
from app.services.graph import audit
from app.services.graph.delete_node import _validate
from app.services.graph.edit_node import EditContext, InvalidEdit, RevisionConflict, _course_write


class DeletionPreviewStale(RevisionConflict):
    def __init__(self, kp_id: str) -> None:
        super().__init__(kp_id, 0, {})

    def details(self) -> dict[str, Any]:
        return {"kp_id": self.kp_id, "reason": "deletion_preview_stale"}


@dataclass(frozen=True)
class DeletionPlan:
    impact: KnowledgePointDeletion
    root: dict[str, Any]
    relations: tuple[graph_edit.IncidentRelation, ...]


def _visible(node: dict[str, Any], effective: set[str]) -> bool:
    return bool(node.get("contrib_manual") or effective.intersection(node.get("contrib_tasks") or ()))


def _canonical(value: Any) -> Any:
    """Neo4j contribution/alias/source collections are sets for preview identity."""
    if isinstance(value, dict):
        return {key: _canonical(item) for key, item in sorted(value.items())}
    if isinstance(value, (list, tuple, set, frozenset)):
        items = [_canonical(item) for item in value]
        return sorted(items, key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True))
    return value


def _plan(tx: ScopedTransaction, scope: GraphScope, root_id: str, revision: int) -> DeletionPlan:
    root = graph_edit.read_nodes(tx, [root_id]).get(root_id)
    if root is None:
        raise not_found()
    nodes = graph_edit.read_cascade_nodes(tx)
    relations = graph_edit.read_incident_relations(tx, sorted(nodes))
    effective = set(scope.effective_task_ids or ())
    visible_ids = {key for key, node in nodes.items() if _visible(node, effective)}
    children: dict[str, set[str]] = {}
    parents: dict[str, set[str]] = {}
    for relation in relations:
        if (relation.type == "CONTAINS" and relation.visible
                and relation.from_id in visible_ids and relation.to_id in visible_ids):
            children.setdefault(relation.from_id, set()).add(relation.to_id)
            parents.setdefault(relation.to_id, set()).add(relation.from_id)

    depths = {root_id: 0}
    queue = deque([root_id])
    while queue:
        parent = queue.popleft()
        for child in sorted(children.get(parent, ())):
            if child not in depths:
                depths[child] = depths[parent] + 1
                queue.append(child)

    doomed = {root_id}
    queue = deque([root_id])
    while queue:
        parent = queue.popleft()
        for child in sorted(children.get(parent, ())):
            if child not in doomed and parents[child] <= doomed:
                doomed.add(child)
                queue.append(child)

    def report_node(kid: str) -> KnowledgePointDeletionNode:
        retained = sorted({str(nodes[parent].get("name") or "")
                           for parent in parents.get(kid, ()) - doomed}) if kid not in doomed else []
        return KnowledgePointDeletionNode(id=kid, name=str(nodes[kid].get("name") or ""),
                                          depth=depths[kid], retained_parents=retained or None)

    order = lambda kid: (depths[kid], str(nodes[kid].get("name") or ""), kid)
    removed = tuple(sorted((r for r in relations if r.from_id in doomed or r.to_id in doomed),
                           key=lambda r: (r.type, r.rel_id)))
    # Include all draft topology, even invisible incidents that deletion will clean.
    # Thus same-count rewiring, hidden relation changes and node content edits invalidate
    # a preview even if an external writer failed to increment the root revision.
    fingerprint = _canonical({
        "format": 1, "course_id": scope.course_id, "root_id": root_id,
        "draft_revision": revision, "effective_task_ids": list(effective),
        "nodes": nodes,
        "relations": [{"type": r.type, "from_id": r.from_id, "to_id": r.to_id,
                       "props": dict(r.props), "visible": r.visible} for r in relations],
        "deleted": sorted(doomed), "retained": sorted(set(depths) - doomed),
    })
    token = hashlib.sha256(json.dumps(fingerprint, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    impact = KnowledgePointDeletion(
        root_id=root_id, root_name=str(root.get("name") or ""), root_revision=int(root["revision"]),
        cascade=True, preview_token=token,
        deleted_count=len(doomed), relation_count=len(removed),
        nodes=[report_node(kid) for kid in sorted(doomed, key=order)],
        retained=[report_node(kid) for kid in sorted(set(depths) - doomed, key=order)],
    )
    return DeletionPlan(impact, root, removed)


def preview_deletion(ctx: EditContext, course_id: str, kp_id: str) -> KnowledgePointDeletion:
    _validate(kp_id, None)
    with _course_write(ctx, course_id, reconcile_audit=False) as scope:
        revision = graph_edit.draft_revision(ctx.sqlite_url, course_id)
        return ctx.store.transaction(scope, lambda tx: _plan(tx, scope, kp_id, revision).impact)  # type: ignore[attr-defined]


def delete_node_cascade(ctx: EditContext, course_id: str, kp_id: str, preview_token: str | None,
                        expected_revision: int | None = None) -> KnowledgePointDeletion:
    _validate(kp_id, expected_revision)
    if not isinstance(preview_token, str) or re.fullmatch(r"[0-9a-f]{64}", preview_token) is None:
        raise InvalidEdit([{"in": "query", "field": "preview_token", "reason": "invalid_preview_token"}])
    with _course_write(ctx, course_id, reconcile_audit=False) as scope:
        revision = graph_edit.draft_revision(ctx.sqlite_url, course_id)
        started: list[audit.Pending] = []
        root: dict[str, Any] = {}

        def write(tx: ScopedTransaction) -> KnowledgePointDeletion:
            plan = _plan(tx, scope, kp_id, revision)
            if not hmac.compare_digest(preview_token, plan.impact.preview_token):
                raise DeletionPreviewStale(kp_id)
            if expected_revision is not None and expected_revision != int(plan.root.get("revision") or 0):
                raise RevisionConflict(kp_id, expected_revision, plan.root)
            root.update(plan.root)
            if not started:  # Neo4j can retry the transaction callback.
                # Preview/conflict must not resolve older pending audits. Reconcile only
                # after all validation, and never reconcile this callback's own pending row.
                audit.reconcile(ctx, scope)
                started.append(audit.begin(ctx, course_id, "delete", kp_id,
                                           revision_before=int(root.get("revision") or 0),
                                           summary=audit.delete_summary(root)))
            count = graph_edit.delete_cascade_nodes(tx, [node.id for node in plan.impact.nodes], plan.relations)
            if count != plan.impact.deleted_count:
                raise DeletionPreviewStale(kp_id)
            return plan.impact

        try:
            impact = ctx.store.transaction(scope, write)  # type: ignore[attr-defined]
        except BaseException as exc:
            if started:
                audit.abort(ctx, started[0], exc)
            raise
        audit.commit(ctx, started[0], revision_after=None,
                     summary=audit.delete_summary(root, impact.relation_count))
        return impact
