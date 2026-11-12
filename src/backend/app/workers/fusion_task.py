"""Bounded global analysis; immutable plans, no visible graph mutation or locked inference."""
from __future__ import annotations

from dataclasses import asdict
import sqlite3
import json

from app.repositories import course_locks, fusion
from app.repositories.chunks import get_chunks
from app.repositories.extraction_checkpoints import read_checkpoints
from app.repositories.graph_nodes import _check as check_node
from app.repositories.graph_projection import read_snapshot
from app.repositories.graph_relations import source_pair
from app.repositories.lease_guard import LeaseGuard
from app.repositories.sqlite import connect
from app.repositories.task_leases import LeaseLost, leased_transaction
from app.repositories.tasks import read_leased_task
from app.services.ai.embeddings import embedding_calls, EmbeddingBatchError, EmbeddingRecordError
from app.services.ai.policy import CallAttribution
from app.services.fusion.judge import FusionEntity, FusionEvidence
from app.services.fusion.mapping import fingerprint, plan_mapping
from app.services.fusion.recall import RECALL_VERSION, RecallCard, recall_candidates
from app.services.fusion.resolution import SemanticDecision
from app.workers.extraction.units import _AttemptClient
from app.workers.extraction.types import ExtractionToolkit


class FusionCancelled(Exception):
    pass


class FusionBusy(RuntimeError):
    pass


def _guard(url, lease, credential_guard=None):
    with connect(url) as db:
        if db.execute("SELECT 1 FROM processing_tasks WHERE id=? AND lease_token=? AND lease_expires_at>unixepoch()",
                      (lease.task_id, lease.token)).fetchone() is None:
            raise LeaseLost('fusion lease expired')
        task = read_leased_task(db, lease.task_id, lease.token)
        if task is None or task.stage != 'merging' or task.course_id != lease.course_id:
            raise LeaseLost('fusion task changed')
        if task.cancel_requested: raise FusionCancelled()
    if credential_guard is not None: credential_guard()


def _raw(snapshot, plan, candidates, task_id):
    """Match F04/F06 fact encoding; retain proof of source occurrence resolution."""
    course = snapshot['course_id']
    result = {**snapshot, 'nodes': list(snapshot['nodes']), 'edges': list(snapshot['edges']),
              'evidence': list(snapshot['evidence'])}
    for node, entity in zip(plan.nodes, candidates.entities, strict=True):
        result['nodes'].append(dict(kp_id=node.kp_id, course_id=course, name=node.name,
            type=node.type, definition=node.definition, confidence=node.confidence, status=node.status,
            aliases=list(node.aliases), source='ai', locked=False, contrib_manual=False,
            contrib_tasks=[task_id], revision=1, level=0))
        for source in node.sources:
            ambiguous = any(c.source.evidence_ambiguous for c in entity.candidates
                if (c.source.chunk_id, c.source.evidence_start, c.source.evidence_end) ==
                   (source.chunk_id, source.evidence_start, source.evidence_end))
            result['evidence'].append(dict(kp_id=node.kp_id, chunk_id=source.chunk_id,
                document_id=source.document_id, revision_id=source.revision_id,
                props=dict(task_id=task_id, chunk_id=source.chunk_id, evidence_start=source.evidence_start,
                           evidence_end=source.evidence_end, occurrence_verified=not ambiguous)))
    for rel in plan.relations:
        result['edges'].append(dict(type=rel.type, from_id=rel.from_id, to_id=rel.to_id,
            p=dict(rel_id=rel.rel_id, course_id=course, confidence=rel.confidence, status=rel.status,
                source=rel.source, contrib_tasks=[task_id], contrib_manual=False, revision=1,
                source_pairs=[source_pair(task_id, cid) for cid in rel.chunk_ids])))
    return result


def _entity(node, evidence, chunks):
    sources = []
    for e in evidence:
        if e['kp_id'] != node['kp_id']: continue
        chunk = chunks.get(e['chunk_id']); p = e['props']
        a, b = p.get('evidence_start'), p.get('evidence_end')
        if (chunk is None or chunk.course_id != node['course_id'] or
            chunk.material_id != e['document_id'] or chunk.revision_id != e['revision_id'] or
            type(a) is not int or type(b) is not int or not 0 <= a < b <= len(chunk.text)):
            raise ValueError('invalid_evidence')
        # Legacy evidence with repeated quotes has no occurrence certificate.
        if p.get('occurrence_verified') is False or (p.get('occurrence_verified') is not True and
                                                    chunk.text.count(chunk.text[a:b]) != 1):
            raise ValueError('ambiguous_evidence')
        sources.append(FusionEvidence(fingerprint(e), node['course_id'], e['document_id'],
                                      e['revision_id'], e['chunk_id'], chunk.text))
    if not sources: raise ValueError('missing_evidence')
    return FusionEntity(node['kp_id'], node['course_id'], node['name'], node['type'],
                        node['definition'], tuple(sources))


def _lineage(snapshot, plans):
    """Recover original occurrence cards, not the canonical node's accumulated definition."""
    result = {}
    for node in snapshot['nodes']:
        key = node['kp_id']
        wanted = {key, *node.get('merged_from', [])}
        if len(wanted) == 1:
            result[key] = [dict(node=node, evidence=[e for e in snapshot['evidence'] if e['kp_id']==key])]
            continue
        result[key] = []
        for plan in reversed(plans):
            atoms = plan.payload.get('lineage_after', {}).get(key, []) if plan.applied else []
            if {a['node']['kp_id'] for a in atoms} == wanted:
                result[key] = atoms
                break
    return result


def prepare_fusion(sqlite_url, lease, *, repo, toolkit, max_pairs, top_k,
                   lock_seconds, lock_wait_seconds, embedding=None, max_corpus_nodes=2000,
                   max_corpus_bytes=2_000_000):
    from app.workers.persist_graph import build_plan, load_candidates
    _guard(sqlite_url, lease)
    with connect(sqlite_url) as db:
        checks = [c for c in read_checkpoints(db, course_id=lease.course_id, task_id=lease.task_id)
                  if c.unit_kind == 'chunk' and c.status == 'done']
    if not checks or any(c.result.get('entity_identity_version', 1) != 2 for c in checks):
        return None  # v1 has already collapsed names; never reinterpret that identity.
    toolkit = toolkit if isinstance(toolkit, ExtractionToolkit) else toolkit(lease)
    check = lambda: _guard(sqlite_url, lease, toolkit.guard)
    check()
    if toolkit.resolver is None: return None
    resolver = toolkit.resolver(_AttemptClient(toolkit.policy,
        CallAttribution(course_id=lease.course_id, task_id=lease.task_id, task_attempt=lease.attempt,
                        user_id=toolkit.user_id), guard=check))
    lock = course_locks.acquire(sqlite_url, lease.course_id, holder='fusion-read:'+lease.owner,
                               lease_seconds=lock_seconds, wait_seconds=lock_wait_seconds)
    if lock is None: raise FusionBusy('course busy')
    guard = LeaseGuard.from_expiry(lock_seconds, lock.expires_at)
    with course_locks.held(sqlite_url, lock, lease_seconds=lock_seconds, guard=guard):
        check(); guard.check()
        with connect(sqlite_url) as db:
            head = fusion.read_draft_head(db, lease.course_id)
            scope = fusion.read_draft_scope(db, lease.course_id)
            history = fusion.list_plans(db, lease.course_id)
        old = read_snapshot(repo, scope)
        guard.check(); check()
    candidates = load_candidates(sqlite_url, course_id=lease.course_id, task_id=lease.task_id)
    plan = build_plan(lease.course_id, lease.task_id, candidates)
    before = _raw(old, plan, candidates, lease.task_id)
    lineage = _lineage(before, history)
    member_ids = {k: [a['node']['kp_id'] for a in atoms] for k, atoms in lineage.items()}
    forbidden = {tuple(sorted(json.loads(key))) for kind, key in head.review_decisions if kind=='suspected_duplicate'}
    protected = {key for kind, key in head.review_decisions if kind=='isolated_node'}
    chunks = {c.chunk_id: c for c in get_chunks(sqlite_url, course_id=lease.course_id,
                    chunk_ids=sorted({e['chunk_id'] for e in before['evidence']} |
                                     {c for r in plan.relations for c in r.chunk_ids}))}
    digest = fingerprint(dict(version=2, head=asdict(head), before=before, lineage=lineage,
        chunks={k: asdict(c) for k, c in chunks.items()}, model=resolver.model,
        prompt=resolver.template.sha256, input_bytes=resolver.max_input_bytes,
        output_tokens=resolver.max_output_tokens, max_pairs=max_pairs, top_k=top_k,
        max_corpus_nodes=max_corpus_nodes, max_corpus_bytes=max_corpus_bytes,
        embedding_space=None if embedding is None else embedding.space, recall_version=RECALL_VERSION))
    with connect(sqlite_url) as db:
        saved = fusion.task_plan(db, lease.course_id, lease.task_id)
    if saved is not None and saved.input_digest == digest: return saved
    cards = [RecallCard(n['kp_id'], n['course_id'], n['name'], '\n'.join(dict.fromkeys(
        [n['definition'], *[a['node']['definition'] for a in lineage[n['kp_id']]]])), tuple(n.get('aliases', [])))
             for n in before['nodes']]
    texts = [c.name+'\n'+c.definition+'\n'+'\n'.join(c.aliases) for c in cards]
    reason = None
    if len(cards) > max_corpus_nodes or sum(len(t.encode('utf-8')) for t in texts) > max_corpus_bytes:
        reason = 'corpus_budget'
    if any(check_node(n, lease.course_id, chunks) for n in plan.nodes): reason = 'invalid_raw_candidate'
    if any(c not in chunks for r in plan.relations for c in r.chunk_ids): reason = 'invalid_relation_source'
    vectors = None
    vector_error = None
    if embedding is not None and reason is None:
        check()
        try:
            with embedding_calls(course_id=lease.course_id, request_id='fusion:'+lease.task_id, user_id=toolkit.user_id):
                values = embedding.embed(texts, before_attempt=check)
            vectors = dict(zip((c.entity_id for c in cards), values, strict=True))
        except EmbeddingRecordError:
            raise
        except EmbeddingBatchError as exc:
            from app.services.ai.client import ModelAuthError
            if isinstance(exc.__cause__, ModelAuthError): raise exc.__cause__
            vector_error = 'embedding_failed'  # semantic conclusions still need two checked judgments
    recall = None if reason else recall_candidates(cards, top_k=top_k, max_pairs=max_pairs, vectors=vectors)
    decisions_by_pair = {}
    deferred = []
    nodes = {n['kp_id']: n for n in before['nodes']}
    for pair in (() if recall is None else recall.pairs):
        check()
        a, b = nodes[pair.left_id], nodes[pair.right_id]
        left_atoms, right_atoms = lineage[pair.left_id], lineage[pair.right_id]
        atoms = {a['kp_id'], b['kp_id'], *member_ids[a['kp_id']], *member_ids[b['kp_id']]}
        code = None
        if any(n.get('locked') or n.get('contrib_manual') or n.get('source') == 'manual' or
               n.get('status') in ('approved', 'rejected') for n in (a, b)):
            code = 'protected_node'
        elif atoms & protected or any(set(p) <= atoms for p in forbidden): code = 'teacher_decision'
        elif not left_atoms or not right_atoms: code = 'unverified_lineage'
        elif len(decisions_by_pair) + len(left_atoms)*len(right_atoms) > max_pairs: code = 'pair_budget'
        if code:
            deferred.append(dict(left_id=pair.left_id, right_id=pair.right_id, code=code)); continue
        for left_atom in left_atoms:
            for right_atom in right_atoms:
                check()
                x, y = left_atom['node']['kp_id'], right_atom['node']['kp_id']
                key = tuple(sorted((x,y)))
                if key in decisions_by_pair: continue
                try:
                    left = _entity(left_atom['node'], left_atom['evidence'], chunks)
                    right = _entity(right_atom['node'], right_atom['evidence'], chunks)
                except ValueError as exc:
                    d = SemanticDecision(x, y, 'deferred', code=str(exc))
                else:
                    # Original members of a canonical group need not preserve
                    # the recall pair's ID order (a+z compared with m).
                    left, right = sorted((left, right), key=lambda entity: entity.entity_id)
                    d = resolver.resolve(left, right)
                decisions_by_pair[key] = d
    decisions = list(decisions_by_pair.values())
    mapped = plan_mapping(before, decisions, existing_ids=[n['kp_id'] for n in old['nodes']],
        member_ids=member_ids, candidate_pairs=[] if recall is None else [(p.left_id,p.right_id) for p in recall.pairs],
        forbidden_pairs=forbidden, protected_ids=protected)
    lineage_after = {}
    for old_id, canonical in mapped.mapping.items():
        lineage_after.setdefault(canonical, []).extend(lineage[old_id])
    sizes = [len({n['kp_id'], *n.get('merged_from', [])}) for n in before['nodes']]
    total_pairs = (sum(sizes)**2 - sum(size**2 for size in sizes))//2
    completed = sum(d.status == 'complete' for d in decisions)
    groups = [dict(group_id='fgroup_'+fingerprint(g)[:24], members=list(g), canonical_id=mapped.mapping[g[0]])
              for g in mapped.groups]
    payload = dict(version=2, before=before, after=mapped.snapshot, mapping=mapped.mapping, groups=groups,
        lineage_after=lineage_after, deferred_pairs=deferred,
        incoming_ids=[n.kp_id for n in plan.nodes], decisions=[asdict(d) for d in decisions],
        recall=None if recall is None else asdict(recall), blocked=list(mapped.blocked),
        total_pairs=total_pairs, examined_pairs=len(decisions), completed_pairs=completed,
        unprocessed_pairs=total_pairs-completed,
        completion='complete' if reason is None and completed==total_pairs else 'partial',
        reason=reason, vector_error=vector_error)
    check()
    with leased_transaction(sqlite_url, lease.task_id, lease.token) as db:
        task = read_leased_task(db, lease.task_id, lease.token)
        if task.stage != 'merging': raise LeaseLost('fusion stage changed')
        if task.cancel_requested: raise FusionCancelled()
        return fusion.put_plan(db, course_id=lease.course_id, task_id=lease.task_id, head=head,
                               input_digest=digest, payload=payload)


def run_fusion_stage(settings, lease, *, repo, toolkit, **lock):
    """Task-level failure semantics around optional global analysis and T5/T8."""
    from app.services.ai.client import ModelAuthError
    from app.services.ai.policy import CallRecordError, ModelUnavailableError
    from app.services.ai.factory import build_embedding_adapter
    from app.services.credentials import CredentialUnavailable
    from app.repositories.neo4j import RepositoryError
    from app.repositories.task_leases import release_after_transient_failure
    from app.workers.persist_graph import run_merge_stage, PersistOutcome, PersistStatus
    try:
        embedding = build_embedding_adapter(settings) if settings.EMBEDDING_MODE == 'online' else None
        prepare_fusion(settings.SQLITE_URL, lease, repo=repo, toolkit=toolkit,
            max_pairs=settings.DISAMBIGUATION_MAX_GLOBAL_PAIRS, top_k=settings.DISAMBIGUATION_RECALL_TOP_K,
            max_corpus_nodes=settings.DISAMBIGUATION_MAX_CORPUS_NODES,
            max_corpus_bytes=settings.DISAMBIGUATION_MAX_CORPUS_BYTES, embedding=embedding, **lock)
    except FusionCancelled:
        pass  # C08 stage boundary consumes cancellation.
    except LeaseLost:
        return PersistOutcome(PersistStatus.LOST, lease.task_id, None)
    except (CredentialUnavailable, ModelAuthError):
        try:
            with leased_transaction(settings.SQLITE_URL, lease.task_id, lease.token) as db:
                changed = db.execute("""UPDATE processing_tasks SET stage='failed',error_code='LLM_UNAVAILABLE',
                    error_message='模型凭据不可用，消歧任务已终止', lease_owner=NULL,lease_token=NULL,lease_expires_at=NULL,
                    updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
                    WHERE id=? AND stage='merging'""", (lease.task_id,)).rowcount
                if changed != 1: raise LeaseLost('fusion stage changed')
        except LeaseLost:
            return PersistOutcome(PersistStatus.LOST, lease.task_id, None)
        return PersistOutcome(PersistStatus.FAILED, lease.task_id, 'failed', error_code='LLM_UNAVAILABLE')
    except (FusionBusy, RepositoryError, sqlite3.Error, CallRecordError, EmbeddingRecordError, ModelUnavailableError) as exc:
        code = 'LLM_UNAVAILABLE' if isinstance(exc, ModelUnavailableError) else 'STORAGE_UNAVAILABLE'
        released = release_after_transient_failure(settings.SQLITE_URL, lease.task_id, lease.token,
                                                   code=code, max_attempts=settings.TASK_MAX_ATTEMPTS)
        return PersistOutcome(PersistStatus(released.status), lease.task_id,
            'merging' if released.status == 'released' else ('failed' if released.status == 'failed' else None),
            error_code=code, not_before=released.not_before)
    return run_merge_stage(settings.SQLITE_URL, lease)
