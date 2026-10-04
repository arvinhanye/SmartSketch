"""Read-only numeric audit; never copies credentials, course text, or databases.
Run: python3 audit.py MEASUREMENT_WORKTREE OUTPUT_JSON
"""
import collections
import hashlib
import json
import math
import sqlite3
import subprocess
import sys
import unicodedata
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

root, output = map(Path, sys.argv[1:])
manifest = {}
def load(rel):
    path = root / rel
    data = path.read_bytes()
    manifest[rel] = {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
    return json.loads(data)
def ts(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))
def stats(values):
    values = sorted(v for v in values if v is not None)
    return {"n": len(values), "min": values[0], "p50": values[math.ceil(len(values)*.5)-1],
            "p95": values[math.ceil(len(values)*.95)-1], "max": values[-1]}
def key(name):
    return ''.join(unicodedata.normalize('NFKC', name).casefold().split())
def acyclic(nodes, edges):
    adjacency = {n['id']: [] for n in nodes}
    for e in edges:
        if e['type'] == 'PREREQUISITE': adjacency[e['from_id']].append(e['to_id'])
    visited, active = set(), set()
    def visit(n):
        if n in active: return False
        if n in visited: return True
        active.add(n)
        if not all(visit(v) for v in adjacency[n]): return False
        active.remove(n); visited.add(n); return True
    return all(visit(n) for n in adjacency)

dbpath = root / 'src/backend/storage/smartsketch.sqlite3'
db = sqlite3.connect('file:' + quote(str(dbpath), safe='/') + '?mode=ro', uri=True)
db.row_factory = sqlite3.Row
db.execute('PRAGMA query_only=ON')
assert db.execute('PRAGMA query_only').fetchone()[0] == 1
head = subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()
assert head.startswith('88f9f6f')
result = {"measurement_commit": head, "read_only": True, "paid_calls": 0,
          "migrations": [r[0] for r in db.execute("SELECT filename FROM schema_migrations WHERE filename IN ('017_model_call_reasoning.sql','018_model_config_disable_thinking.sql')")],
          "pdf": {}, "qa": {}}
assert set(result['migrations']) == {'017_model_call_reasoning.sql','018_model_config_disable_thinking.sql'}
newcalls = []
for course, expected in [('course2', (30,32842,68,58)), ('course1', (31,40292,76,61))]:
    prefix = f'evaluation/raw/c03b/{course}-pdf'
    audit = load(prefix+'-task-audit.json'); draft = load(prefix+'-draft-thinking-disabled.json')
    load(prefix+'-extract.json')
    taskid = audit['task']['id']; courseid = draft['course_id']
    task = dict(db.execute('SELECT id,stage,created_at,updated_at,error_code FROM processing_tasks WHERE id=?',(taskid,)).fetchone())
    assert task == audit['task']
    calls = [dict(r) for r in db.execute('SELECT call_id,status,purpose,created_at,finished_at,is_repair,usage_input,usage_output,usage_reasoning FROM model_calls WHERE task_id=?',(taskid,))]
    newcalls.extend(calls)
    tokens = sum(r['usage_input']+r['usage_output'] for r in calls)
    span = (max(ts(r['finished_at']) for r in calls)-min(ts(r['created_at']) for r in calls)).total_seconds()
    assert (len(calls),tokens,len(draft['nodes']),len(draft['edges'])) == expected
    assert round(span,3) == audit['model_span_seconds']
    assert not any(r['is_repair'] or r['status']!='ok' for r in calls)
    assert acyclic(draft['nodes'],draft['edges'])
    types = collections.Counter(e['type'] for e in draft['edges'])
    assert set(types)=={'CONTAINS','PREREQUISITE','RELATED_TO','EXAMPLE_OF'}
    connected = {e[k] for e in draft['edges'] for k in ('from_id','to_id')}
    binding = dict(db.execute('SELECT config_version,disable_thinking FROM task_model_bindings WHERE task_id=?',(taskid,)).fetchone())
    assert binding['disable_thinking']==1
    candidates = collections.defaultdict(list)
    for row in db.execute("SELECT result FROM task_chunk_checkpoints WHERE task_id=? AND unit_kind='chunk' AND status='done'",(taskid,)):
        for e in json.loads(row[0])['entities']: candidates[key(e['name'])].append(e['source'])
    backed = 0
    for node in draft['nodes']:
        refs = candidates[key(node['name'])]
        entityid='tent_'+hashlib.sha256(json.dumps([taskid,key(node['name'])],ensure_ascii=False).encode()).hexdigest()[:32]
        nodeid='kp_'+hashlib.sha256(json.dumps([courseid,taskid,entityid],ensure_ascii=False).encode()).hexdigest()[:32]
        assert nodeid == node['id']
        assert refs
        for ref in refs:
            chunk = db.execute('SELECT course_id,material_id,revision_id,sources FROM chunks WHERE chunk_id=?',(ref['chunk_id'],)).fetchone()
            assert chunk is not None and (chunk['course_id'],chunk['material_id'],chunk['revision_id']) == (courseid,ref['document_id'],ref['revision_id'])
            assert any(s.get('locator',{}).get('page') is not None or s.get('locator',{}).get('section_titles') for s in json.loads(chunk['sources']))
        backed += 1
    prediction=load(f'evaluation/raw/c04/{course}-pdf-h2-thinking-off-predictions.json')
    assert prediction['source_draft_course_id']==courseid
    assert (len(prediction['entities']),len(prediction['relations'])) == expected[2:]
    phase = {'parsing_ms':629,'extracting_ms':17720,'merging_ms':9,'persisting_ms':1037} if course=='course2' else {'parsing_ms':807,'extracting_ms':18959,'merging_ms':6,'persisting_ms':6471}
    server=(ts(task['updated_at'])-ts(task['created_at'])).total_seconds()
    result['pdf'][course] = {'task_id':taskid,'course_id':courseid,'server_seconds':round(server,3),
        'client_seconds':audit['client_elapsed_seconds'],'model_span_seconds':span,'non_model_client_seconds':audit['non_model_seconds'],
        'last_model_finished_at':max(r['finished_at'] for r in calls),
        'awaiting_review_at':task['updated_at'],
        'tail_without_model_seconds':round((ts(task['updated_at'])-max(ts(r['finished_at']) for r in calls)).total_seconds(),3),
        'calls':len(calls),'tokens':tokens,'repair':0,'nodes':len(draft['nodes']),'edges':len(draft['edges']),
        'edge_types':dict(types),'isolated':sum(n['id'] not in connected for n in draft['nodes']),
        'acyclic':True,'nonempty_origin_tag':sum(bool(n.get('source')) for n in draft['nodes']),
        'checkpoint_entity_sources_with_same_course_chunk_locator':backed,
        'persisted_node_source_refs_independently_verified':False,'binding':binding,
        'reported_phases_ms_not_retained_in_logs':phase,
        'server_minus_reported_phases_seconds':round(server-sum(phase.values())/1000,3)}

rawpath='evaluation/raw/c02b-qa/all.jsonl'
b = (root/rawpath).read_bytes();manifest[rawpath]={'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b)}
raw=[json.loads(line) for line in b.decode().splitlines()]
audit=load('evaluation/raw/c02b-qa/audit-records.json');load('evaluation/raw/c02b-qa/audit-window.json')
rows=[];generations=[];embeddings=[];citations=0
for sample in raw:
    row=dict(db.execute('SELECT request_id,course_id,outcome,reason,error_code,truncated,invalidation_subtype,unknown_citation_count,latency_ms,first_delta_latency_ms,citations_json,version_id FROM chat_logs WHERE request_id=?',(sample['request_id'],)).fetchone())
    for field in ('course_id','outcome','reason','error_code'): assert row[field]==sample[field]
    assert row['latency_ms']==sample['server_latency_ms']
    assert row['truncated']==0 and row['invalidation_subtype'] is None and row['unknown_citation_count']==0
    refs=json.loads(row['citations_json']);assert len(refs)==sample['citations']
    for _,chunkid in refs:
        chunk=db.execute('SELECT course_id,sources FROM chunks WHERE chunk_id=?',(chunkid,)).fetchone()
        assert chunk and chunk['course_id']==row['course_id']
        assert any(s.get('locator',{}).get('page') is not None or s.get('locator',{}).get('section_titles') for s in json.loads(chunk['sources']))
        citations += 1
    calls=[dict(r) for r in db.execute('SELECT call_id,purpose,status,usage_input,usage_output,usage_reasoning,input_tokens_est,max_output_tokens FROM model_calls WHERE request_id=?',(sample['request_id'],))]
    generations.extend(r for r in calls if r['purpose']!='embedding');embeddings.extend(r for r in calls if r['purpose']=='embedding');rows.append(row)
newcalls+=generations+embeddings
repeat_data=(root/'evaluation/raw/c02b-qa/repeat.jsonl').read_bytes()
manifest['evaluation/raw/c02b-qa/repeat.jsonl']={'sha256':hashlib.sha256(repeat_data).hexdigest(),'bytes':len(repeat_data)}
repeat=[json.loads(line) for line in repeat_data.decode().splitlines()]
assert len(repeat)==3 and all(r['outcome']=='answered' for r in repeat)
assert {r['request_id'] for r in repeat}.issubset({r['request_id'] for r in raw})
assert len(raw)==13 and len({r['request_id'] for r in raw})==13
assert collections.Counter(r['outcome'] for r in rows)=={'answered':11,'not_covered':2}
assert len(generations)==11 and len(embeddings)==10
assert all(r['status']=='ok' and r['max_output_tokens']==2048 for r in generations)
assert sum(r['usage_input']+r['usage_output'] for r in generations)==24960
assert sum(r['usage_input']+r['usage_output'] for r in embeddings)==59
summary={'client_elapsed_seconds':stats([r['client_elapsed_seconds'] for r in raw]),
         'server_latency_ms':stats([r['latency_ms'] for r in rows]),
         'server_first_delta_ms':stats([r['first_delta_latency_ms'] for r in rows]),
         'client_sse_first_delta_ms':stats([r['client_sse_first_delta_ms'] for r in raw])}
for k,v in summary.items():
    assert v == {field: audit['summary'][k][field] for field in v}, (k,v,audit['summary'][k])
result['qa']={'counts':dict(collections.Counter(r['outcome'] for r in rows)),'statistics':summary,
    'answered_client_seconds':stats([r['client_elapsed_seconds'] for r in raw if r['outcome']=='answered']),
    'citations_same_course_with_locator':citations,'browser_first_token':'not_measured',
    'generation_tokens':24960,'embedding_tokens':59,'generation_calls':11,'embedding_calls':10,
    'repeat_comparison_answered':len(repeat),'comparison_answered_including_original':sum(r['outcome']=='answered' for r in raw if r['question']=='栈和队列有什么区别'),
    'v3_thinking_on_projection':{'observed_input_tokens':sum(r['usage_input'] for r in generations),
      'output_ceiling':sum(r['max_output_tokens'] for r in generations),
      'actual_input_plus_output_ceiling':sum(r['usage_input']+r['max_output_tokens'] for r in generations),
      'unknown_usage_upper_estimate':sum(r['input_tokens_est']+r['max_output_tokens'] for r in generations),
      'largest_call_estimate':max(r['input_tokens_est']+r['max_output_tokens'] for r in generations),
      'thirteen_calls_at_largest_estimate':13*max(r['input_tokens_est']+r['max_output_tokens'] for r in generations)}}
assert len({r['call_id'] for r in newcalls})==82
assert not any(r['usage_input'] is None or r['usage_output'] is None for r in newcalls)
assert all(r['usage_reasoning'] is None for r in newcalls if r['purpose']!='embedding')
known=db.execute("SELECT SUM(usage_input+usage_output) FROM model_calls WHERE purpose!='embedding'").fetchone()[0]
unknown=db.execute("SELECT SUM(input_tokens_est+max_output_tokens) FROM model_calls WHERE purpose!='embedding' AND (usage_input IS NULL OR usage_output IS NULL) AND NOT (status='error' AND error_class LIKE '%:rejected_before_generation')").fetchone()[0]
vector=db.execute("SELECT SUM(usage_input+usage_output) FROM model_calls WHERE purpose='embedding'").fetchone()[0]
assert (known,unknown,vector)==(829784,12116,12005)
assert 746357+32842+40292+24960==known+unknown+2551==844451
result['budget']={'generation_known':known,'old_unknown_estimate':unknown,'manual_probe':2551,
    'generation_system_before':746357,'increment':98094,'generation_system_after':844451,
    'approved_total':900000,'remaining':55549,'embedding_before':11946,'embedding_after':vector,
    'new_unknown_usage_calls':0,'measurement_groups':'two PDF tasks plus one QA round (three question groups)'}
old = load('evaluation/raw/c03/course2-pdf-task-audit.json')
oldtask = db.execute('SELECT created_at,updated_at FROM processing_tasks WHERE id=?',(old['task']['id'],)).fetchone()
oldcalls = db.execute('SELECT min(created_at),max(finished_at),count(*),sum(is_repair),sum(usage_reasoning) FROM model_calls WHERE task_id=?',(old['task']['id'],)).fetchone()
assert round((ts(oldcalls[1])-ts(oldcalls[0])).total_seconds(),3)==old['model_span_seconds']
assert round(old['client_elapsed_seconds']-old['model_span_seconds'],3)==18.742
result['old_c03_1']={'task_id':old['task']['id'],'client_seconds':old['client_elapsed_seconds'],
    'server_seconds':round((ts(oldtask[1])-ts(oldtask[0])).total_seconds(),3),
    'non_model_client_seconds':18.742,'last_model_finished_at':oldcalls[1],
    'awaiting_review_at':oldtask[1],'tail_without_model_seconds':round((ts(oldtask[1])-ts(oldcalls[1])).total_seconds(),3),
    'calls':oldcalls[2],'repair':oldcalls[3],'usage_reasoning':oldcalls[4]}
result['retained_logs']={}
for rel in ['.demo/c03b/logs/worker.log' ,'.demo/c03b/logs/api.log','.demo/c03b/logs/migrate.log',
            'docs/handoffs/deepseek-plan-c-to-codex.md','docs/handoffs/deepseek-plan-c-thinking-disabled.md',
            'evaluation/reports/c03b-pdf-thinking-disabled.md','evaluation/reports/c02b-qa-thinking-disabled.md',
            'evaluation/raw/c04/course1-pdf-h2-thinking-off-worksheet.md','evaluation/raw/c04/course2-pdf-h2-thinking-off-worksheet.md']:
    path=root/rel;data=path.read_bytes();manifest[rel]={'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}
    if rel.endswith('.log'):
        result['retained_logs'][rel]={'bytes':len(data),'lines':len(data.splitlines()),'stage_timer_lines':data.count(b'task stage done')}
result['manifest']=manifest
result['stage_c_status']='OPEN'
db.close()
output.parent.mkdir(parents=True,exist_ok=True)
output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k!='manifest'},ensure_ascii=False,indent=2))
