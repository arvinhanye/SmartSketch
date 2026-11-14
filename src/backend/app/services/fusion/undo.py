"""Single-group undo with conservative conflict detection and an atomic draft pointer."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field, replace

from app.repositories import course_locks, fusion
from app.repositories.graph_projection import read_snapshot, write_snapshot
from app.repositories.lease_guard import LeaseGuard
from app.repositories.neo4j import Neo4jRepository
from app.repositories.sqlite import connect
from app.services.fusion.mapping import canonical_json, fingerprint, project_snapshot, validate_snapshot
from app.services.graph.dag import find_cycle


class UndoBusy(RuntimeError):
    """The course write lock could not be acquired within its configured wait."""


@dataclass(frozen=True)
class UndoContext:
    """Service composition owns storage construction, not the HTTP route."""

    sqlite_url: str
    repo: Neo4jRepository
    lock_seconds: int
    wait_seconds: float

    @classmethod
    def from_settings(cls, settings, *, repository=None):
        return cls(settings.SQLITE_URL,
                   Neo4jRepository.from_settings(settings) if repository is None else repository,
                   settings.TASK_LEASE_SECONDS,settings.COURSE_LOCK_WAIT_SECONDS)


def _without(payload, excluded):
    mapping = {n['kp_id']: n['kp_id'] for n in payload['before']['nodes']}
    for group in payload['groups']:
        if group['group_id'] not in excluded:
            mapping.update({k: group['canonical_id'] for k in group['members']})
    return project_snapshot(payload['before'], mapping)


def _index(snapshot, kind):
    if kind == 'nodes': return {n['kp_id']: n for n in snapshot[kind]}
    if kind == 'edges': return {e['p']['rel_id']: e for e in snapshot[kind]}
    return {canonical_json(e): e for e in snapshot[kind]}


def inverse_patch(payload, group_id, current, *, undone):
    group = next((g for g in payload['groups'] if g['group_id'] == group_id), None)
    if group is None: raise LookupError('unknown fusion group')
    expected = _without(payload, set(undone))
    desired = _without(payload, set(undone) | {group_id})
    affected = set(group['members'])
    conflicts = []
    for kind in ('nodes', 'edges', 'evidence'):
        def touches(item):
            if kind == 'edges': return bool({item['from_id'], item['to_id']} & affected)
            return item['kp_id'] in affected
        want = {k: v for k, v in _index(expected, kind).items() if touches(v)}
        actual = {k: v for k, v in _index(current, kind).items() if touches(v)}
        if actual != want:
            conflicts.append(dict(reason='affected_content_changed', kind=kind,
                                  ids=sorted(k for k in set(want) | set(actual) if want.get(k) != actual.get(k))
                                      if kind != 'evidence' else sorted(affected)))
    if conflicts: return None, conflicts
    result = deepcopy(current)
    for kind in ('nodes', 'edges', 'evidence'):
        before, after, now = _index(expected, kind), _index(desired, kind), _index(result, kind)
        changed = {k for k in set(before) | set(after) if before.get(k) != after.get(k)}
        # A shared relationship may touch another group's canonical node; compare its whole fact.
        if any(now.get(k) != before.get(k) for k in changed):
            return None, [dict(reason='dependent_content_changed', kind=kind, ids=sorted(affected))]
        for k in changed:
            replacement = deepcopy(after[k]) if k in after else None
            if kind == 'nodes' and replacement is not None:
                # Undo is a new write, including resurrected absorbed nodes. Reusing
                # the pre-merge token would admit stale edits after a later merge.
                replacement['revision'] = max(int(replacement.get('revision', 1)),
                    int(now.get(k, {}).get('revision', 0))) + 1
            now.pop(k, None)
            if replacement is not None: now[k] = replacement
        result[kind] = [now[k] for k in sorted(now)]
    validate_snapshot(result)
    cycle = find_cycle((n['kp_id'] for n in result['nodes']), [(e['from_id'], e['to_id'])
        for e in result['edges'] if e['type']=='PREREQUISITE' and e['p'].get('status')!='rejected'])
    if cycle: return None, [dict(reason='prerequisite_cycle', ids=list(cycle))]
    return result, []


@dataclass(frozen=True)
class UndoResult:
    status: str
    current_revision: int
    group_id: str
    conflicts: tuple[dict, ...] = ()
    affected_ids: tuple[str, ...] = ()
    storage_version_id: str | None = None


def _operate(*, sqlite_url, repo, course_id, plan_id, group_id, expected_revision, actor_id,
             lock_seconds, wait_seconds, apply):
    if type(expected_revision) is not int or expected_revision < 0:
        raise ValueError('expected_revision must be a nonnegative integer')
    with connect(sqlite_url) as db: fusion.require_teacher(db, course_id, actor_id)
    lock = course_locks.acquire(sqlite_url, course_id, holder='fusion-undo:'+actor_id,
                               lease_seconds=lock_seconds, wait_seconds=wait_seconds)
    if lock is None: raise UndoBusy('COURSE_BUSY')
    guard = LeaseGuard.from_expiry(lock_seconds, lock.expires_at)
    with course_locks.held(sqlite_url, lock, lease_seconds=lock_seconds, guard=guard):
        with connect(sqlite_url) as db:
            fusion.require_teacher(db, course_id, actor_id)
            head = fusion.read_draft_head(db, course_id)
            plan = fusion.get_plan(db, course_id, plan_id)
            undone = fusion.undone_groups(db, course_id, plan_id)
            scope = fusion.read_draft_scope(db, course_id)
        if plan is None or not plan.applied: raise LookupError('applied fusion plan not found')
        group = next((g for g in plan.payload['groups'] if g['group_id'] == group_id), None)
        if group is None: raise LookupError('fusion group not found')
        common = dict(current_revision=head.draft_revision, group_id=group_id,
                      affected_ids=tuple(group['members']))
        if group_id in undone: return UndoResult('already_undone', **common)
        if expected_revision != head.draft_revision:
            return UndoResult('conflict', conflicts=(dict(reason='stale_revision'),), **common)
        guard.check()
        current = read_snapshot(repo, scope)
        guard.check()
        after, conflicts = inverse_patch(plan.payload, group_id, current, undone=undone)
        if conflicts: return UndoResult('conflict', conflicts=tuple(conflicts), **common)
        if not apply: return UndoResult('ready', **common)
        storage = 'draftgen_undo_'+fingerprint([plan_id, group_id, asdict(head), after])[:40]
        target = replace(scope, storage_version_id=storage)
        with repo.persist_write_transaction(target, check=guard.check, remaining=guard.remaining) as tx:
            write_snapshot(tx, after)
            acquired = []
            with fusion.undo_transaction(sqlite_url, head, lock.token, deadline=tx.deadline,
                                         on_acquired=acquired.append) as db:
                guard.check()
                fusion.require_teacher(db, course_id, actor_id)
                try:
                    tx.commit(started_at=acquired[0])
                    fusion.record_undo(db, course_id=course_id, plan_id=plan_id, group_id=group_id,
                        actor_id=actor_id, head=head, storage_version_id=storage,
                        payload=dict(head=asdict(head), before=current, after=after, storage_version_id=storage))
                except BaseException:
                    if tx.commit_started: guard.lose()
                    raise
        return UndoResult('undone', **{**common, 'current_revision': head.draft_revision+1}, storage_version_id=storage)


def preview_undo(**kwargs) -> UndoResult:
    return _operate(**kwargs, apply=False)


def undo_merge(**kwargs) -> UndoResult:
    return _operate(**kwargs, apply=True)
