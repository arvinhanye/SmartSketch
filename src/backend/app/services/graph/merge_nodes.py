"""F10：教师合并重复知识点与重接边（契约 ``mergeKnowledgePoints``；specs/teacher-review-publish.md
「审核队列」「V3 merged_from」「V4」；ADR-047）。

顺序与 F08 相同（V4）：输入校验 → 有界等待取课程写锁（持有方 ``edit``）→ 读 V → **一个** Neo4j 写事务：

1. 锁课程草稿守卫节点（与 F06 关系写入串行）；
2. 读主节点与被合并节点（须全部可见，否则 422 ``not_found``），核对可选的 ``expected_revisions``
   （不符 → ``RevisionConflict``）；
3. 读与被合并节点相连的全部草稿关系，计算重接方案（见下），对迁移后的 ``PREREQUISITE`` 做 F05 环检测
   （成环 → ``CycleDetectedError``）；
4. 校验全部通过后才 ``draft_revision + 1``（SQLite，只加一次），再依次写主节点、补来源、换关系、删被合并节点。

任何一步失败都整体回滚，草稿与 ``draft_revision`` 保持原样（第 4 步 SQLite 已加 1 而 Neo4j 提交失败时，
按 V4「最坏结果是课程被判为 revising」处理）。

**重接规则**：被合并节点一端换成主节点。两端都落在「主节点 + 被合并节点」内的关系删除（否则成自环）。
新关系 ID 按「课程 + 类型 + 起点 + 终点」重新派生；ADR-009 降级而来的关系按原类型 ``PREREQUISITE``
派生，与降级保留原 ID 的约定一致。ID 相同或「类型 + 端点」相同的关系合成一条：主节点原有的关系胜出，
否则按「可见 → 状态 approved > draft > low_confidence > rejected → 人工 → 置信度高 → rel_id」挑选；胜出者
提供类型与字段，贡献任务、人工贡献与来源对取并集，修订号取最大值加 1。不可见的关系照样迁移，
贡献原样保留，因此迁移后仍不可见，由失败任务的清理撤销。

**节点字段**：主名与其他字段取主节点；被合并节点的名称与别名依次并入别名（去重，不含主名）；
``merged_from`` 取主节点、被合并节点及其 ``merged_from`` 的并集（展平，V3）；贡献任务取并集；
主节点加锁、登记人工贡献、修订号加 1。来源关联全部迁到主节点（按 ``task_id``、块、区间去重，保留
``task_id``），共享的文本块不删。

审计（F12，ADR-061）：第 4 步的 ``draft_revision + 1`` 由 ``audit.begin`` 连同 ``pending`` 审计行一起写入，
摘要记主节点、**直接**被合并的节点与展平谱系（ADR-012 修订 3）；提交后补上重接与来源迁移的计数并置
``committed``，事务抛错则置 ``aborted``。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from app.repositories import graph_edit
from app.repositories.graph_edit import IncidentRelation
from app.repositories.graph_relations import derive_rel_id, read_prerequisite_graph, read_visible_nodes
from app.repositories.neo4j import GraphScope, ScopedTransaction
from app.schemas.contracts import KnowledgePoint
from app.services.graph import audit
from app.services.graph.dag import check_candidates
from app.services.graph.edit_node import EditContext, InvalidEdit, RevisionConflict, _course_write, _respond
from app.services.graph.relations import CycleDetectedError

__all__ = ["merge_nodes"]

PREREQUISITE: Final = "PREREQUISITE"
_STATUS_RANK: Final = {"approved": 0, "draft": 1, "low_confidence": 2, "rejected": 3}


def _field(field: str, reason: str) -> dict[str, str]:
    return {"in": "body", "field": field, "reason": reason}


# ---------------------------------------------------------------- 输入校验（不取锁、不读库）


def _validate(primary_id: object, merged_ids: Sequence[object],
              expected: Mapping[str, object] | None) -> tuple[str, list[str], dict[str, int]]:
    errors: list[dict[str, str]] = []
    if not isinstance(primary_id, str) or not primary_id.strip():
        errors.append(_field("primary_id", "blank"))
    if not merged_ids:
        errors.append(_field("merged_ids", "too_short"))
    seen: set[str] = set()
    for i, kp_id in enumerate(merged_ids):
        if not isinstance(kp_id, str) or not kp_id.strip():
            errors.append(_field(f"merged_ids.{i}", "blank"))
        elif kp_id == primary_id:
            errors.append(_field(f"merged_ids.{i}", "contains_primary"))
        elif kp_id in seen:
            errors.append(_field(f"merged_ids.{i}", "duplicate"))
        if isinstance(kp_id, str):
            seen.add(kp_id)
    involved = {primary_id, *seen}
    revisions: dict[str, int] = {}
    for kp_id, revision in (expected or {}).items():
        where = f"expected_revisions.{kp_id}"
        if kp_id not in involved:
            errors.append(_field(where, "not_in_merge"))
        elif type(revision) is not int:
            errors.append(_field(where, "int_type"))
        elif revision < 1:
            errors.append(_field(where, "greater_than_equal"))
        else:
            revisions[kp_id] = revision
    if errors:
        raise InvalidEdit(errors)
    return str(primary_id), [str(k) for k in merged_ids], revisions


# ---------------------------------------------------------------- 重接方案


@dataclass(frozen=True)
class _Moved:
    """一条关系在合并后的形态；``existing`` 为主节点原有、端点不变的关系。"""

    rel: IncidentRelation
    rel_id: str
    from_id: str
    to_id: str
    existing: bool


@dataclass(frozen=True)
class _Plan:
    removed: list[tuple[str, str]]
    created: list[dict[str, Any]]


def _union(values: Sequence[Sequence[Any]]) -> list[Any]:
    out: list[Any] = []
    for items in values:
        for item in items or ():
            if item not in out:
                out.append(item)
    return out


def _rank(m: _Moved) -> tuple[Any, ...]:
    p = m.rel.props
    confidence = p.get("confidence")
    return (not m.existing, not m.rel.visible, _STATUS_RANK.get(str(p.get("status")), 4),
            not p.get("contrib_manual"), -(confidence if isinstance(confidence, (int, float)) else 0.0), m.rel.rel_id)


def _groups(members: list[_Moved]) -> list[list[_Moved]]:
    """ID 相同或「类型 + 端点」相同的关系归为一组（并查集）。"""
    parent = list(range(len(members)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    owner: dict[tuple[str, ...], int] = {}
    for i, m in enumerate(members):
        for key in (("id", m.rel_id), ("shape", m.rel.type, m.from_id, m.to_id)):
            if key in owner:
                parent[find(i)] = find(owner[key])
            else:
                owner[key] = i
    groups: dict[int, list[_Moved]] = {}
    for i, m in enumerate(members):
        groups.setdefault(find(i), []).append(m)
    return list(groups.values())


def _rewire(course_id: str, primary: str, merged: set[str], relations: Sequence[IncidentRelation]) -> _Plan:
    removed: list[tuple[str, str]] = []
    members: list[_Moved] = []
    for rel in relations:
        if rel.from_id not in merged and rel.to_id not in merged:
            # 主节点原有的关系：只有与迁移来的关系重合时才参与改写
            members.append(_Moved(rel, rel.rel_id, rel.from_id, rel.to_id, existing=True))
            continue
        removed.append((rel.type, rel.rel_id))
        from_id = primary if rel.from_id in merged else rel.from_id
        to_id = primary if rel.to_id in merged else rel.to_id
        if from_id == to_id:
            continue  # 两端都在本次合并内：删除
        id_type = str(rel.props.get("downgraded_from_type") or rel.type)
        members.append(_Moved(rel, derive_rel_id(course_id, id_type, from_id, to_id), from_id, to_id, existing=False))

    created: list[dict[str, Any]] = []
    for group in _groups(members):
        if all(m.existing for m in group):
            continue
        group.sort(key=_rank)
        winner = group[0]
        for m in group:
            if m.existing:
                removed.append((m.rel.type, m.rel.rel_id))
        props = dict(winner.rel.props)
        props.update(
            rel_id=winner.rel_id,
            contrib_tasks=_union([m.rel.props.get("contrib_tasks") or [] for m in group]),
            contrib_manual=any(bool(m.rel.props.get("contrib_manual")) for m in group),
            source_pairs=_union([m.rel.props.get("source_pairs") or [] for m in group]),
            revision=max(int(m.rel.props.get("revision") or 0) for m in group) + 1,
        )
        created.append({"type": winner.rel.type, "rel_id": winner.rel_id, "from_id": winner.from_id,
                        "to_id": winner.to_id, "props": props})
    return _Plan(removed, created)


def _check_cycles(tx: ScopedTransaction, scope: GraphScope, merged: set[str], plan: _Plan) -> None:
    """迁移后的草稿必须仍是 DAG：现有边去掉被改写的，加上新形态中可见、未拒绝的 ``PREREQUISITE``。"""
    nodes = set(read_visible_nodes(tx)) - merged
    touched = {rel_id for _, rel_id in plan.removed}
    existing = [edge for rel_id, edge in read_prerequisite_graph(tx).items() if rel_id not in touched]
    effective = set(scope.effective_task_ids or ())
    candidates = []
    for c in plan.created:
        p = c["props"]
        visible = bool(p.get("contrib_manual")) or any(t in effective for t in p.get("contrib_tasks") or [])
        if (c["type"] == PREREQUISITE and p.get("status") != "rejected" and visible
                and c["from_id"] in nodes and c["to_id"] in nodes):
            candidates.append((c["from_id"], c["to_id"]))
    check = check_candidates(nodes, existing, candidates)
    if not check.ok:
        raise CycleDetectedError(check.cycle or (), check.edge)


# ---------------------------------------------------------------- 来源


def _evidence_key(props: Mapping[str, Any], chunk_id: str) -> tuple[Any, ...]:
    return (props.get("task_id"), chunk_id, props.get("evidence_start"), props.get("evidence_end"))


def _new_evidence(rows: Sequence[Mapping[str, Any]], primary: str) -> list[dict[str, Any]]:
    seen = {_evidence_key(r["props"], r["chunk_id"]) for r in rows if r["kp_id"] == primary}
    out: list[dict[str, Any]] = []
    for r in rows:
        key = _evidence_key(r["props"], r["chunk_id"])
        if r["kp_id"] == primary or key in seen:
            continue
        seen.add(key)
        out.append({"chunk_id": r["chunk_id"], "props": dict(r["props"])})
    return out


# ---------------------------------------------------------------- 操作


def _merge(tx: ScopedTransaction, ctx: EditContext, scope: GraphScope, primary: str, merged: list[str],
           expected: Mapping[str, int], bump: Any) -> dict[str, Any]:
    ids = [primary, *merged]
    nodes = graph_edit.read_nodes(tx, ids)
    missing = [_field("primary_id" if kp_id == primary else f"merged_ids.{i - 1}", "not_found")
               for i, kp_id in enumerate(ids) if kp_id not in nodes]
    if missing:
        raise InvalidEdit(missing)
    for kp_id in ids:
        current = int(nodes[kp_id].get("revision") or 0)
        if kp_id in expected and expected[kp_id] != current:
            raise RevisionConflict(kp_id, expected[kp_id], nodes[kp_id])

    merged_set = set(merged)
    plan = _rewire(scope.course_id, primary, merged_set, graph_edit.read_incident_relations(tx, ids))
    _check_cycles(tx, scope, merged_set, plan)
    evidence = _new_evidence(graph_edit.read_evidence(tx, ids), primary)

    head = nodes[primary]
    name = head.get("name")
    aliases = [a for a in _union([head.get("aliases") or []]
                                 + [[nodes[m].get("name"), *(nodes[m].get("aliases") or [])] for m in merged])
               if a and a != name]
    lineage = sorted(set(_union([head.get("merged_from") or [], merged]
                                + [nodes[m].get("merged_from") or [] for m in merged])) - {primary})
    tasks = _union([head.get("contrib_tasks") or []] + [nodes[m].get("contrib_tasks") or [] for m in merged])

    bump(int(head.get("revision") or 0), {
        "primary": head, "merged": [nodes[m] for m in merged], "lineage": lineage,
        "relations_removed": len(plan.removed), "relations_created": len(plan.created), "evidence_moved": len(evidence),
    })
    written = graph_edit.update_merged_primary(tx, primary, int(head.get("revision") or 0), aliases=aliases,
                                               merged_from=lineage, contrib_tasks=tasks)
    if written is None:  # 同一事务内刚读过且持有守卫锁：不应出现
        raise RevisionConflict(primary, int(head.get("revision") or 0), head)
    graph_edit.add_evidence(tx, primary, evidence)
    graph_edit.replace_relations(tx, removed=plan.removed, created=plan.created)
    graph_edit.delete_merged_nodes(tx, merged)
    return written


def merge_nodes(ctx: EditContext, course_id: str, primary_id: str, merged_ids: Sequence[str],
                expected_revisions: Mapping[str, int] | None = None) -> KnowledgePoint:
    """把 ``merged_ids`` 并入 ``primary_id``，返回合并后的主节点（见模块说明）。

    失败时抛出 ``InvalidEdit``（422）、``RevisionConflict`` / ``CycleDetectedError`` / ``CourseBusy``（409），
    草稿不变；Neo4j 故障抛出 F02 已脱敏的 ``RepositoryError``。
    """
    primary, merged, expected = _validate(primary_id, merged_ids, expected_revisions)
    with _course_write(ctx, course_id) as scope:
        started: list[tuple[audit.Pending, dict[str, Any]]] = []

        def bump(revision: int, facts: dict[str, Any]) -> None:
            # 驱动重跑事务时不重复加；事实取最后一次（即提交的那次）执行
            if not started:
                started.append((audit.begin(ctx, course_id, "merge", primary, revision_before=revision,
                                            summary=audit.merge_summary(facts["primary"], facts["merged"],
                                                                        lineage=facts["lineage"])), facts))
            else:
                started[0] = (started[0][0], facts)

        try:
            written = ctx.store.transaction(  # type: ignore[attr-defined]
                scope, lambda tx: _merge(tx, ctx, scope, primary, merged, expected, bump))
        except BaseException as exc:
            if started:
                audit.abort(ctx, started[0][0], exc)
            raise
        pending, facts = started[0]
        audit.commit(ctx, pending, revision_after=int(written.get("revision") or 0) or None,
                     summary=audit.merge_summary(facts["primary"], facts["merged"], lineage=facts["lineage"],
                                                 relations_removed=facts["relations_removed"],
                                                 relations_created=facts["relations_created"],
                                                 evidence_moved=facts["evidence_moved"]))
        return _respond(ctx, scope, written)
