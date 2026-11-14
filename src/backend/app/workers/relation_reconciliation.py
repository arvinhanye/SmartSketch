"""Monotonic invalidation of local relation dependencies during merging (ADR-102)."""
from itertools import combinations

from app.workers.extraction.local import dependent

MAX_REEXTRACTED_SECTIONS = 32


def settle_relations(sections, mapped, kp_ids, reextract, rebuild, *, max_sections=MAX_REEXTRACTED_SECTIONS):
    """Rebuild receives exact selections and split prohibitions, never provisional union edges."""
    if type(max_sections) is not int or max_sections < 0:
        raise ValueError('max_sections must be nonnegative')
    selected = {sid:dict(kind='initial',digest=result['relation_input_digest'])
                for sid,result in sections.items()}
    forbidden = set()
    count = 0
    reason = None
    while True:
        affected = []
        for sid,result in sorted(sections.items()):
            # A later replacement can split more members of an already rerun
            # section. Record every observed split before any further rebuild.
            split = False
            for group in result['normalization']['groups']:
                for a,b in combinations(group,2):
                    x,y = kp_ids[a],kp_ids[b]
                    if mapped.mapping[x] != mapped.mapping[y]:
                        forbidden.add(tuple(sorted((x,y))))
                        split = True
            if split and selected[sid]['kind'] == 'initial':
                affected.append(sid)
        if not affected:
            break
        sid = affected[0]
        if count >= max_sections:
            reason = 'relation_reextraction_limit'
        else:
            selected[sid] = reextract(sid)
            count += 1
            if selected[sid].get('status') != 'done':
                reason = 'relation_reextraction_failed'
        if reason:
            # Disabling merging also invalidates any previously accepted local group.
            for key,result in sections.items():
                if selected[key]['kind']=='initial' and dependent(result):
                    selected[key] = dict(kind='omitted',reason=reason)
        mapped = rebuild(selected,forbidden,reason is not None)
        if reason:
            break
    coverage = dict(status='partial' if reason else 'complete',
                    reextracted_sections=count, max_sections=max_sections,
                    omitted_sections=sorted(k for k,v in selected.items() if v['kind']=='omitted'),
                    failed_sections=sorted(k for k,v in selected.items() if v.get('status')=='failed'),
                    reasons=[] if reason is None else [reason])
    return selected,mapped,coverage


def has_pinned_normalization(sqlite_url, lease):
    from app.repositories.sqlite import connect
    from app.repositories.extraction_checkpoints import read_checkpoints
    with connect(sqlite_url) as db:
        return any((c.metadata or {}).get('normalization_version') == 1 for c in
                   read_checkpoints(db,course_id=lease.course_id,task_id=lease.task_id))


def reextraction_config(toolkit, limits):
    """Cache identity changes when the replacement model/template/output or L2 limit changes."""
    from dataclasses import asdict
    from app.services.ai.policy import CallAttribution
    from app.workers.extraction.units import _AttemptClient
    extractor = toolkit.relations(_AttemptClient(toolkit.policy,CallAttribution(course_id='probe'))).normalized()
    return dict(version=1,model=extractor.model,prompt=extractor.prompt().sha256,
                output_tokens=extractor.max_output_tokens, limits=asdict(limits),
                max_sections=MAX_REEXTRACTED_SECTIONS)


def reextract_section(sqlite_url, lease, checkpoint, *, toolkit, limits):
    """One immutable identity-partition replacement. No graph lock or task-stage rewind."""
    from dataclasses import replace
    from app.repositories.chunks import get_chunks
    from app.repositories.extraction_checkpoints import read_checkpoints
    from app.repositories.relation_revisions import read_revision,put_revision
    from app.repositories.sqlite import connect
    from app.repositories.task_leases import leased_transaction,LeaseLost
    from app.repositories.tasks import read_leased_task
    from app.services.ai.extraction_windows import WindowPolicy
    from app.services.ai.policy import CallAttribution
    from app.services.ai.relations import SectionEntity,SourceChunk
    from app.services.fusion.local import local_normalization
    from app.services.fusion.mapping import fingerprint
    from app.workers.extraction.candidates import _group_entities,_identity
    from app.workers.extraction.local import relation_input_digest
    from app.workers.extraction.types import _Section,_Halt,_UnitResult,OUTPUT_INVALID_CODE
    from app.workers.extraction.units import _AttemptClient,_extract_section
    from app.workers.fusion_task import _guard,FusionCancelled

    check = lambda: _guard(sqlite_url,lease,toolkit.guard)
    check()
    with connect(sqlite_url) as db:
        checks = read_checkpoints(db,course_id=lease.course_id,task_id=lease.task_id,unit_kind='chunk')
    wanted = checkpoint.result['chunk_ids']
    chunks = get_chunks(sqlite_url,course_id=lease.course_id,chunk_ids=wanted)
    by_id = {c.chunk_id:c for c in chunks}
    chunks = tuple(by_id[k] for k in wanted if k in by_id)
    members = _group_entities(lease.task_id,lease.course_id,[c for c in checks if c.unit_id in wanted])
    entities = tuple(SectionEntity(e.entity_id,lease.course_id,e.name,e.type,e.candidates[0].definition,
                                   e.candidates[0].evidence) for e in members)
    policy_raw = (checkpoint.metadata or {}).get('window_policy')
    policy = None if policy_raw is None else WindowPolicy(**policy_raw)
    extractor = toolkit.relations(_AttemptClient(toolkit.policy,
        CallAttribution(course_id=lease.course_id,task_id=lease.task_id),guard=check)).normalized()
    normalization = local_normalization(entities,None)
    digest = fingerprint(dict(original=checkpoint.result['relation_input_digest'],
        input=relation_input_digest(checkpoint.unit_id,entities,
            tuple(SourceChunk(_identity(c),c.text) for c in chunks),extractor,policy,normalization),
        chunk_attempts=limits.chunk_max_attempts))
    args = dict(course_id=lease.course_id,task_id=lease.task_id,section_id=checkpoint.unit_id,input_digest=digest)
    with connect(sqlite_url) as db:
        saved = read_revision(db,**args)
    if saved is None:
        if set(by_id) != set(wanted):
            result = _UnitResult('failed',1,OUTPUT_INVALID_CODE,metadata={'reason':'missing_relation_source'})
        else:
            original_factory = toolkit.relations
            kit = replace(toolkit,local_normalization=False,preserve_mentions=True,resolver=None,
                          guard=check,window_policy=policy,relations=lambda client: original_factory(client).normalized())
            section = _Section(checkpoint.unit_id,(chunks[0].revision_id,chunks[0].ordinal),
                               None,tuple(chunks))
            try:
                result = _extract_section(kit,lease,limits,section,entities,task_entities=members)
            except _Halt as exc:
                # Preserve existing task-level auth/circuit/audit semantics in fusion.
                if exc.__cause__ is not None:
                    raise exc.__cause__
                raise
        check()
        with leased_transaction(sqlite_url,lease.task_id,lease.token) as db:
            task = read_leased_task(db,lease.task_id,lease.token)
            if task is None or task.course_id != lease.course_id or task.stage != 'merging':
                raise LeaseLost('relation reextraction stage changed')
            if task.cancel_requested:
                raise FusionCancelled()
            put_revision(db,**args,status=result.status,attempts=result.attempts,error_code=result.error_code,
                         result=result.result,metadata={**(result.metadata or {}),
                             'normalization':normalization,'original_input_digest':checkpoint.result['relation_input_digest']})
            saved = read_revision(db,**args)
    check()
    return dict(kind='revision',digest=digest,status=saved.status)
