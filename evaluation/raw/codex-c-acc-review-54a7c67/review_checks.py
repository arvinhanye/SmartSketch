import re, contextlib, hashlib, importlib.util, io, json, logging, sqlite3, subprocess, sys, tempfile, types
from dataclasses import asdict, replace
from pathlib import Path
from unittest.mock import patch
ROOT = Path.cwd()
M = Path('/Users/arvinhan/SmartSketch/.claude/worktrees/smartsketch-c03b-measure')
C = Path('/Users/arvinhan/SmartSketch/.claude/worktrees/smartsketch-plan-a-fixes-e70a34')

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def state(path):
    return {'head': subprocess.check_output(['git','rev-parse','HEAD'],cwd=path,text=True).strip(),
            'status': subprocess.check_output(['git','status','--porcelain','-uall'],cwd=path,text=True).splitlines()}

signoff = load('review_signoff', ROOT/'evaluation/c04_signoff.py')
test = load('review_signoff_tests', ROOT/'tests/tooling/test_c04_signoff_sheet.py')
review = {'scope': {'base':'4a6308b','head':'54a7c67','files':subprocess.check_output(['git','diff','--name-only','4a6308b..54a7c67'],text=True).splitlines()}, 'source_state_before': {'claude':state(C), 'measurement':state(M)}}
data = []
for course, stem in signoff.COURSES.items():
    d = ROOT/'evaluation/raw/c04-signoff'
    hashes = {}
    for suffix in ('predictions.json','worksheet.md'):
        p = d/f'{stem}-{suffix}'
        s = M/'evaluation/raw/c04'/p.name
        hashes[suffix] = {'source_sha256':sha(s),'review_sha256':sha(p),'equal':sha(s)==sha(p)}
        assert hashes[suffix]['equal']
    predictions=json.loads((d/f'{stem}-predictions.json').read_text())
    original=(d/f'{stem}-worksheet.md').read_text()
    user_sheet=(d/f'{stem}-worksheet-user.md').read_text()
    judged=signoff.to_judgments(user_sheet,original,predictions)
    stored=json.loads((d/f'{stem}-judgments-user.json').read_text())
    report=signoff.evaluate.judge_report(predictions,stored)
    stored_report=json.loads((d/f'{stem}-report-user.json').read_text())
    assert judged.judgments == stored and report == stored_report
    assist=json.loads((d/f'{stem}-judgments-claude-assist.json').read_text())
    matched=wrong=same_notes=remove_marker=0
    edited=[]
    for kind in ('entities','relations'):
        for item_id,value in stored[kind].items():
            assert value == assist[kind][item_id]
            matched+=1
            if value == 'incorrect':
                wrong+=1
                u,a=stored['notes'].get(item_id,''),assist['notes'].get(item_id,'')
                a = re.sub(r'^#\d+\s+', '', a)  # assist notes include worksheet row-number prefixes
                if u == a: same_notes+=1
                elif u == re.sub(r'【[^】]*请复核[^】]*】', '', a).strip(): remove_marker+=1; edited.append({'kind':kind,'id':item_id})
                else: raise AssertionError('unexpected edited note')
    # All committed data row occurrences, not dict-based counting.
    physical=sum(1 for line in user_sheet.splitlines() if signoff.ROW.match(line))
    assert physical == matched
    data.append({'course':course,'original_hashes':hashes,'judgments_equal':True,'report_equal':True,
                 'judge':stored['judge'],'is_human_judgment':report['is_human_judgment'],
                 'hard_indicators':report['hard_indicators'],'matched_assist':matched,'incorrect':wrong,
                 'same_wrong_notes_after_row_prefix_removal':same_notes,'removed_review_marker':remove_marker,'edited_ids':edited})
review['signoff_evidence']=data

p=test._predictions(); orig=test.convert.worksheet(p); sheet=signoff.user_sheet(orig)
filled=test._fill(sheet,test.ALL_OK)
probes=[]
def convert_probe(name,value):
    try:
        result=signoff.to_judgments(value,orig,p)
        probes.append({'name':name,'accepted':True,'judgments':result.judgments})
    except Exception as e:
        probes.append({'name':name,'accepted':False,'exception':type(e).__name__,'message':str(e)})
row=next(line for line in filled.splitlines() if '`kp_a`' in line and line.startswith('| 1'))
other=row.replace('| ✓ |  |','| ✗ | E2: conflicting duplicate |')
convert_probe('duplicate_row_conflicting_first',filled.replace(row,other+'\n'+row,1))
convert_probe('duplicate_row_conflicting_last',filled.replace(row,row+'\n'+other,1))
convert_probe('additional_column',filled.replace(row,row[:-1]+' unexpected extra column |',1))
convert_probe('deleted_row',filled.replace(row+'\n','',1))
convert_probe('invalid_marker',filled.replace(row,row.replace('| ✓ |','| invalid |'),1))
convert_probe('blank_judge',filled.replace('- 判定人：张三','- 判定人：',1))
convert_probe('uppercase_assist_judge',filled.replace('- 判定人：张三','- 判定人：CLAUDE-ASSIST reviewer',1))
convert_probe('unfilled',sheet)
wrongrow=next(line for line in filled.splitlines() if '`kp_c`' in line and line.startswith('| 3'))
convert_probe('incorrect_without_note',filled.replace(wrongrow,wrongrow.replace('E2：把命令当名称',''),1))
cleared=signoff.apply_marks(signoff.apply_marks(sheet,'arvin',dict(test.ALL_OK)), 'arvin', {k:('','') for k in test.ALL_OK})
origrows=[x for x in orig.splitlines() if signoff.ROW.match(x)]
assert all(row in cleared.splitlines() for row in origrows)
review['apply_marks_clear_original_rows_identical']=True
review['escaped_pipe_roundtrip_valid']=signoff.to_judgments(filled,orig,p).judgments['entities']['kp_c']=='incorrect'
with tempfile.TemporaryDirectory(prefix='codex-c-acc-signoff-') as tmp:
    tmp=Path(tmp)
    for course,stem in signoff.COURSES.items():
        (tmp/f'{stem}-predictions.json').write_text(json.dumps(p,ensure_ascii=False))
        (tmp/f'{stem}-worksheet.md').write_text(orig)
        (tmp/f'{stem}-worksheet-user.md').write_text(filled if course=='course1' else sheet)
        for suffix in ('judgments-user.json','report-user.json'):
            (tmp/f'{stem}-{suffix}').write_text('{"previous_result":true}\n')
    before={x.name:sha(x) for x in tmp.iterdir()}
    with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
        status=signoff.main(['convert','--dir',str(tmp)])
    changed=[x.name for x in tmp.iterdir() if sha(x)!=before[x.name]]
    review['batch_invalid_second_course']={'exit':status,'changed_files':sorted(changed)}
review['signoff_boundary_probes']=probes

# Side-effect/order/return comparison against the exact base implementation.
from app.workers import persist_graph as head
base=types.ModuleType('review_base_persist')
sys.modules[base.__name__]=base
source=subprocess.check_output(['git','show','4a6308b:src/backend/app/workers/persist_graph.py'],text=True)
exec(compile(source,'git:4a6308b/persist_graph.py','exec'),base.__dict__)
lease=head.Lease(task_id='t-review',course_id='c-review',document_id='d-review',stage='persisting',progress=0.0,attempt=1,owner='owner',token='test-token',expires_at=0)
logging.disable(logging.CRITICAL)

def simulate(module, case):
    events=[]
    def fail_at(name):
        if case == name+'_sqlite': raise sqlite3.OperationalError('synthetic failure')
        if case == name+'_lost': raise module.LeaseLost('synthetic lost')
        if case == name+'_runtime': raise RuntimeError('synthetic failure')
    def step(name,result=None):
        def fn(*args,**kwargs):
            events.append(name);fail_at(name)
            if case=='plan_runtime' and name=='plan': raise RuntimeError('synthetic plan')
            return result
        return fn
    class Repo:
        def write_transaction(self,scope,work):
            events.append('transaction'); events.append(['scope',scope.course_id,scope.version_id,list(scope.effective_task_ids)])
            result=work(object())
            if case=='retry': result=work(object())
            if case=='neo4j_repository': raise module.RepositoryError()
            if case=='neo4j_cycle': raise module.UnresolvableCycleError(('a','b','a'))
            if case in ('neo4j_runtime','failure_sqlite','failure_runtime'): raise RuntimeError('synthetic runtime')
            if case=='neo4j_relation': raise module.RelationWriteError('synthetic relation')
            if case=='neo4j_value': raise ValueError('synthetic value')
            if case=='neo4j_key': raise KeyError('synthetic key')
            return result
    @contextlib.contextmanager
    def held(*args,**kwargs):
        events.append('lock_enter');fail_at('lock_enter')
        try: yield None
        finally:
            events.append('lock_exit');fail_at('lock_exit')
    def release(*args,**kwargs):
        events.append(['release',kwargs]);fail_at('release')
        return module.PersistOutcome(module.PersistStatus.RELEASED,lease.task_id,'persisting',not_before=10)
    def failure(*args,**kwargs):
        events.append(['failure',kwargs]);fail_at('failure')
        return module.PersistOutcome(module.PersistStatus.FAILED,lease.task_id,'failed',error_code=kwargs['code'],cleanup_pending=True)
    vals={'load_candidates':step('candidates',object()),'build_plan':step('plan',object()),'_source_chunk_ids':step('source_ids',()),
          'get_chunks':step('chunks',()),'_check_lease':step('lease'), '_effective':step('effective',('t-current',)),
          '_write_draft':step('write',types.SimpleNamespace(nodes=4,relations=3,downgraded=())), '_t6':step('t6'),
          '_release':release,'_after_failure':failure}
    log=[]
    with contextlib.ExitStack() as stack:
        for key,val in vals.items(): stack.enter_context(patch.object(module,key,val))
        stack.enter_context(patch.object(module.course_locks,'acquire',step('lock_acquire',None if case=='lock_missing' or case.startswith('release_') else object())))
        stack.enter_context(patch.object(module.course_locks,'held',held))
        stack.enter_context(patch.object(module.logger,'info',lambda *args,**kwargs: log.append(args)))
        try:
            result=module.run_persist_stage('sqlite:///synthetic-unused',replace(lease,stage='parsing') if case=='invalid_stage' else lease,repo=Repo(),max_attempts=3,lock_seconds=60,lock_wait_seconds=1,holder='override')
            outcome={'return':asdict(result)}
        except BaseException as error: outcome={'exception':type(error).__name__,'message':str(error)}
    return {'events':events,'outcome':outcome},log

cases=['success','retry','lock_missing','candidates_sqlite','plan_sqlite','chunks_sqlite','plan_runtime','lock_acquire_sqlite',
       'lock_enter_lost','lease_lost','effective_sqlite','neo4j_repository','neo4j_cycle','neo4j_runtime','neo4j_value','neo4j_key',
       't6_sqlite','t6_lost','lock_exit_sqlite','lock_exit_runtime','t6_runtime','neo4j_relation','release_sqlite','release_runtime','failure_sqlite','failure_runtime','invalid_stage']
comparisons=[]
for case in cases:
    left,_=simulate(base,case);right,log=simulate(head,case)
    assert left==right,case
    comparison={'case':case,'equivalent':True,'events':right['events'],'outcome':right['outcome']}
    if case=='lock_exit_sqlite':
        comparison['persist_steps_fields']=log[-1][3]
        comparison['lock_release_ms_present']='lock_release_ms=' in log[-1][3]
    comparisons.append(comparison)
review['persist_semantics_comparison']=comparisons
logging.disable(logging.NOTSET)

# Patch all four SQLite connector bindings, and verify finally restores after an exception.
audit=load('review_sources',ROOT/'evaluation/audit_persisted_sources.py')
original_bindings=[m.connect for m in audit._PATCHED]
try:
    with audit.readonly_repositories():
        assert all(m.connect is audit._ro for m in audit._PATCHED)
        raise RuntimeError('synthetic context abort')
except RuntimeError: pass
assert all(m.connect is conn for m,conn in zip(audit._PATCHED,original_bindings))
review['readonly_four_module_patch_and_exception_restore']=True
review['source_state_after']={'claude':state(C),'measurement':state(M)}
assert review['source_state_before']==review['source_state_after']
db_path=M/'src/backend/storage/smartsketch.sqlite3'
stored_sources=json.loads((ROOT/'evaluation/raw/c-acc-a/sources.json').read_text())
review['measurement_db_main_sha256_matches_stored_sources']=sha(db_path)==stored_sources['sqlite']['sha256_before']==stored_sources['sqlite']['sha256_after']
review['measurement_db_sidecar_sizes']={s:(Path(str(db_path)+s).stat().st_size if Path(str(db_path)+s).exists() else None) for s in ('-wal','-shm')}
assert review['measurement_db_main_sha256_matches_stored_sources']
review['paid_generation_calls']=0;review['paid_embedding_calls']=0
out=ROOT/'evaluation/raw/codex-c-acc-review-54a7c67'
out.mkdir(parents=True,exist_ok=True)
(out/'checks.json').write_text(json.dumps(review,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'original_hashes_equal':True,'judgments_and_reports_equal':True,'assist_matched':sum(x['matched_assist'] for x in data),
                 'wrong_notes_same':sum(x['same_wrong_notes_after_row_prefix_removal'] for x in data),'wrong_notes_removed_marker':sum(x['removed_review_marker'] for x in data),
                 'semantics_equivalent_cases':len(comparisons),'boundary_acceptance':[{k:v for k,v in x.items() if k in ('name','accepted')} for x in probes],
                 'batch_invalid_second_course':review['batch_invalid_second_course'],'four_module_restore':True,'source_state_unchanged':True},ensure_ascii=False,indent=2))
