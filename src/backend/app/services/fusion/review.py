"""Read-only semantic review projection. No model calls and no graph mutations."""
from __future__ import annotations

from dataclasses import dataclass
import base64
import binascii
import json
from itertools import product
from typing import Any, Mapping, Sequence

from app.repositories.fusion import DraftHead, FusionPlan
from app.repositories import fusion


@dataclass(frozen=True)
class ReviewProposal:
    left_id: str
    right_id: str
    reason: str
    analysis: dict[str, Any]


@dataclass(frozen=True)
class ReviewView:
    summary: dict[str, Any]
    proposals: tuple[ReviewProposal, ...] = ()


def _current(head: DraftHead, plan: FusionPlan, undone: Sequence[str]) -> bool:
    # T6 adds exactly this task to V and increments draft_revision once. Dismissals
    # may be added without bumping the revision; apply them below rather than
    # accidentally resurrecting a teacher's rejection from the immutable plan.
    return (plan.course_id == head.course_id and plan.state == 'committed' and not plan.reason and not undone
            and plan.payload.get('version') == 2
            and head.draft_revision == plan.head.draft_revision + 1
            and set(head.effective_task_ids) == {*plan.head.effective_task_ids, plan.task_id}
            and head.storage_version_id == (plan.storage_version_id if plan.applied else plan.head.storage_version_id)
            and set(plan.head.review_decisions) <= set(head.review_decisions))


def build_review_view(head: DraftHead, plan: FusionPlan | None, nodes: Sequence[Mapping[str, Any]], *,
                      undone: Sequence[str] = ()) -> ReviewView:
    summary: dict[str, Any] = dict(status='not_analyzed' if plan is None else 'stale', queue_mode='legacy',
        draft_revision=head.draft_revision, plan_id=None, task_id=None,
        pair_unit='original_member_pairs', total_pairs=None, examined_pairs=None, completed_pairs=None,
        same_pairs=None, different_pairs=None, uncertain_pairs=None, technical_unchecked_pairs=None,
        auto_merged_groups=None, review_pairs=0, legacy_candidates=0, recall=None,
        reasons=['no_analysis' if plan is None else 'stale_analysis'])
    if plan is None or not _current(head, plan, undone):
        return ReviewView(summary)
    data = plan.payload
    complete = {tuple(sorted((d['left_id'], d['right_id']))): d for d in data['decisions']
                if d['status'] == 'complete' and d.get('verdict') in ('SAME','DIFFERENT','UNCERTAIN')}
    recall = data.get('recall')
    reasons = list(dict.fromkeys(filter(None, [data.get('reason'), data.get('vector_error'),
        *data.get('extraction_coverage', {}).get('reasons', []),
        *[d.get('code') for d in data['decisions'] if d['status'] != 'complete'],
        *[d.get('code') for d in data.get('deferred_pairs', [])]])))
    total = data['total_pairs']
    summary.update(status='complete' if len(complete) == total and data.get('completion') == 'complete' else 'partial',
        queue_mode='semantic', plan_id=plan.plan_id, task_id=plan.task_id,
        total_pairs=total, examined_pairs=len(data['decisions']), completed_pairs=len(complete),
        same_pairs=sum(d['verdict']=='SAME' for d in complete.values()),
        different_pairs=sum(d['verdict']=='DIFFERENT' for d in complete.values()),
        uncertain_pairs=sum(d['verdict']=='UNCERTAIN' for d in complete.values()),
        technical_unchecked_pairs=max(0,total-len(complete)),
        auto_merged_groups=len(data['groups']) if plan.applied else 0, reasons=reasons)
    if recall is not None:
        summary['recall'] = dict(pair_unit='visible_node_pairs', total_pairs=recall['total_possible_pairs'],
            retrieved_pairs=len(recall['pairs']), truncated_pairs=recall['truncated_pairs'],
            limited_queries=recall['limited_queries'], missing_channels=list(recall['missing_channels']))
    by_id = {n['kp_id']: n for n in nodes if n.get('status') != 'rejected'}
    before = {n['kp_id']: n for n in data['before']['nodes']}
    mapping = data['mapping'] if plan.applied else {k:k for k in before}
    projected_members: dict[str,set[str]] = {}
    for key,node in before.items():
        projected_members.setdefault(mapping.get(key,key),set()).update({key,*node.get('merged_from',[])})
    dismissed = {tuple(sorted(json.loads(key))) for kind,key in head.review_decisions
                 if kind == 'suspected_duplicate'}
    proposals = {}
    for pair in (() if recall is None else recall['pairs']):
        a, b = pair['left_id'], pair['right_id']
        x, y = sorted((mapping.get(a,a), mapping.get(b,b)))
        if x == y or x not in by_id or y not in by_id or (x,y) in dismissed or a not in before or b not in before:
            continue
        left, right = projected_members[x], projected_members[y]
        proofs = [complete.get(tuple(sorted((l,r)))) for l,r in product(left,right)]
        # Never elevate a partial comparison of canonical groups to a verdict.
        if any(d is None for d in proofs) or any(d['verdict']=='DIFFERENT' for d in proofs):
            continue
        verdict = 'UNCERTAIN' if any(d['verdict']=='UNCERTAIN' for d in proofs) else 'SAME'
        reason = 'semantic_uncertain' if verdict=='UNCERTAIN' else 'merge_blocked'
        evidence = dict(plan_id=plan.plan_id, verdict=verdict,
            basis=proofs[0]['basis'] if len({d['basis'] for d in proofs})==1 else 'mixed',
            reasons=list(dict.fromkeys(d['reason'] for d in proofs if d.get('reason'))),
            differences=list(dict.fromkeys(v for d in proofs for v in d.get('differences', []))),
            constraints=list(dict.fromkeys(g['reason'] for g in data.get('blocked', [])
                if {a,b} <= set(g['members']))))
        proposals[(x,y)] = ReviewProposal(x,y,reason,evidence)
    summary['review_pairs'] = len(proposals)
    return ReviewView(summary, tuple(proposals[k] for k in sorted(proposals)))


class InvalidHistoryCursor(ValueError):
    pass


def read_merge_history(sqlite_url: str, course_id: str, *, cursor: str | None = None, limit: int = 50) -> dict:
    after = None
    if cursor is not None:
        try:
            data = json.loads(base64.urlsafe_b64decode(cursor+'='*(-len(cursor)%4)))
            if (not isinstance(data,list) or len(data)!=4 or data[0]!=1 or data[1]!=course_id
                or type(data[2]) is not int or type(data[3]) is not int or data[2]<1 or data[3]<0):
                raise ValueError('invalid history cursor')
            after = (data[2],data[3])
        except (ValueError,UnicodeError,binascii.Error):
            raise InvalidHistoryCursor('invalid_cursor') from None
    head,rows = fusion.merge_history_page(sqlite_url,course_id,after=after,limit=limit+1)
    chosen = rows[:limit]
    next_cursor = None
    if len(rows)>limit:
        last = chosen[-1]
        raw = json.dumps([1,course_id,last['sequence'],last['index']],separators=(',',':')).encode()
        next_cursor = base64.urlsafe_b64encode(raw).decode().rstrip('=')
    return dict(draft_revision=head.draft_revision, next_cursor=next_cursor,
                items=[{k:v for k,v in r.items() if k not in ('sequence','index')} for r in chosen])
