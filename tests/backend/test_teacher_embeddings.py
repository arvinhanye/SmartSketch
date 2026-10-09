"""Teacher embedding configuration: authorization and real response dimensions."""
from test_l06 import env, _auth

BASE = '/api/v1/me/embedding-config'

def test_student_cannot_read_or_write_embedding_config(env):
    for method, suffix in [('get', ''), ('put', ''), ('post', '/test'), ('post', '/models')]:
        response = getattr(env.client, method)(BASE + suffix, headers=_auth(env.bob), **({} if method == 'get' else {'json': {}}))
        assert response.status_code == 403

def test_teacher_can_read_default_without_key(env):
    result = env.client.get(BASE, headers=_auth(env.alice))
    assert result.status_code == 200
    assert result.json()['configured'] is False
    assert 'api_key' not in result.json()
import json
import pytest
from test_l06 import FakeResponse
from app.repositories import embedding_configs as repo
from app.repositories.courses import create_course
from app.repositories.accounts import insert_account
from app.services import embedding_configs as service
from app.services.credentials import CredentialCipher, CredentialError

class VectorTransport:
    def __init__(self, wrong=False): self.requests=[]; self.wrong=wrong
    def open(self,url,body,headers,timeout):
        data=json.loads(body);self.requests.append((url,data,headers))
        n=data['dimensions'] + int(self.wrong)
        return FakeResponse(200,json.dumps({'model':data['model'],'data':[{'index':i,'embedding':[0.1]*n} for i,_ in enumerate(data['input'])],'usage':{'prompt_tokens':1,'total_tokens':1}}).encode())

def _vector(env,**updates):
    env.app.state.embedding_transport=VectorTransport()
    env.app.state.embedding_rebuilder=lambda *args,**kwargs:None
    return {'base_url':'https://api.example.com/v1','model':'vector-model','dimensions':256,'api_key':'vector-test-key-1234',**updates}

def test_teacher_save_encrypts_separately_and_student_cannot_obtain(env):
    values=_vector(env)
    result=env.client.put(BASE,json=values,headers=_auth(env.alice))
    assert result.status_code==200,result.text
    assert result.json()['dimensions']==256
    assert values['api_key'] not in result.text
    row=repo.get_config(env.url,env.alice.id)
    assert values['api_key'].encode() not in row.sealed.ciphertext
    cipher=CredentialCipher.from_settings(env.app.state.settings)
    assert cipher.open(service.domain(env.alice.id),row.sealed)==values['api_key']
    with pytest.raises(CredentialError): cipher.open(env.alice.id,row.sealed)
    assert env.client.get(BASE,headers=_auth(env.bob)).status_code==403

def test_wrong_actual_dimensions_do_not_save(env):
    values=_vector(env)
    env.app.state.embedding_transport=VectorTransport(wrong=True)
    test=env.client.post(BASE+'/test',json=values,headers=_auth(env.alice))
    assert test.status_code==200 and test.json()['ok'] is False
    assert env.client.put(BASE,json=values,headers=_auth(env.alice)).status_code==422
    assert repo.get_config(env.url,env.alice.id) is None

@pytest.mark.parametrize('dimensions',[0,-1,4097])
def test_invalid_dimension_rejected_without_network(env,dimensions):
    values=_vector(env,dimensions=dimensions)
    assert env.client.post(BASE+'/test',json=values,headers=_auth(env.alice)).status_code==422
    assert env.app.state.embedding_transport.requests==[]

def test_test_only_does_not_save(env):
    values=_vector(env)
    assert env.client.post(BASE+'/test',json=values,headers=_auth(env.alice)).json()['ok'] is True
    assert repo.get_config(env.url,env.alice.id) is None

def test_different_teacher_course_and_endpoint_spaces_are_isolated(env):
    values=_vector(env)
    settings=env.app.state.settings
    course=create_course(env.url,name='teacher one',description=None,creator_id=env.alice.id)
    other=insert_account(env.url,account_id='a'*32,username='otherteacher',password_hash='$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA',role='teacher')
    other_course=create_course(env.url,name='teacher two',description=None,creator_id=other.id)
    service.save(settings,env.alice.id,**values,transport=env.app.state.embedding_transport,rebuilder=lambda *a,**k:None)
    assert repo.for_course(env.url,other_course.id) is None
    first=repo.for_course(env.url,course.id)
    assert service.for_course(settings,course.id).space==first.space
    assert service.space_id(other.id,values['base_url'],values['model'],256)!=first.space
    assert service.space_id(env.alice.id,'https://other.example/v1',values['model'],256)!=first.space

def test_rebuild_failure_preserves_old_config_and_only_passes_owned_courses(env):
    values=_vector(env);settings=env.app.state.settings
    own=create_course(env.url,name='one',description=None,creator_id=env.alice.id)
    service.save(settings,env.alice.id,**values,transport=env.app.state.embedding_transport,rebuilder=lambda *a,**k:None)
    old=repo.get_config(env.url,env.alice.id)
    def fail(settings,user,courses,target,**kwargs):
        assert courses==[own.id]
        raise service.EmbeddingConfigFailure('mock')
    with pytest.raises(service.EmbeddingConfigFailure):
        service.save(settings,env.alice.id,**{**values,'dimensions':512},transport=env.app.state.embedding_transport,rebuilder=fail)
    assert repo.get_config(env.url,env.alice.id)==old

def test_address_change_requires_new_key_before_network(env):
    values=_vector(env);settings=env.app.state.settings
    service.save(settings,env.alice.id,**values,transport=env.app.state.embedding_transport,rebuilder=lambda *a,**k:None)
    with pytest.raises(service.KeyRequired):
        service.save(settings,env.alice.id,**{**values,'base_url':'https://other.example/v1','api_key':None},transport=env.app.state.embedding_transport)
from types import SimpleNamespace
from app.repositories.sqlite import connect
from app.repositories import course_locks
from test_g06 import commit
from neo4j import EagerResult

def test_real_rebuild_code_scopes_vectors_and_switches_only_owned_history(env,monkeypatch):
    values=_vector(env);settings=env.app.state.settings
    own=create_course(env.url,name='own',description=None,creator_id=env.alice.id)
    other=insert_account(env.url,account_id='b'*32,username='teacherother',password_hash='$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA',role='teacher')
    theirs=create_course(env.url,name='theirs',description=None,creator_id=other.id)
    published=commit(env.url,own.id,nodes=1);other_version=commit(env.url,theirs.id,nodes=1)
    stock=[{'kind':'KnowledgePoint','id':'point1','version':'draft','name':'栈','definition':'后进先出'},
           {'kind':'KnowledgePoint','id':'point1','version':published.version_id,'name':'栈','definition':'后进先出'}]
    class Driver:
        def __init__(self): self.writes=[];self.closed=False
        def execute_query(self,query,parameters_=None,**kwargs):
            params=parameters_ or {k:v for k,v in kwargs.items() if k not in ['database_','routing_']}
            if 'ORDER BY kind,id,version' in query:
                assert params['course']==own.id and 'n.course_id=$course' in query
                return EagerResult(stock,None,[])
            if 'AS ready' in query:
                assert params['course']==own.id
                return EagerResult([{'total':2,'ready':2}],None,[])
            if 'RETURN count(n) AS matched' in query:
                assert params['course_id']==own.id
                assert len(params['values'])==256
                assert 'DELETE' not in query and 'REMOVE' not in query
                self.writes.append(params);return EagerResult([{'matched':1}],None,[])
            return EagerResult([],None,[])
        def close(self):self.closed=True
    driver=Driver();monkeypatch.setattr('neo4j.GraphDatabase.driver',lambda *a,**k:driver)
    service.save(settings,env.alice.id,**values,transport=env.app.state.embedding_transport)
    row=repo.get_config(env.url,env.alice.id)
    assert driver.closed and len(driver.writes)==2
    with connect(env.url) as db:
        spaces=dict(db.execute("SELECT course_id,embedding_space FROM graph_versions WHERE state='committed'"))
    assert spaces[own.id]==row.space
    assert spaces[theirs.id]=='fake/4'
    # Request builders bind the teacher embedding, retaining the student's chat models.
    from app.api.versions import publish_context
    from app.api.chat import user_chat_service
    from app.services.versions.publish import PublishContext
    class Base:
        embedding='global'
        def with_models(self,a,b):self.rewriter=a;self.generator=b;return self
    state=SimpleNamespace(settings=settings,publish_context=PublishContext(env.url,object(),object(),lambda:'fake/4'),
        chat_service=Base(),user_chat_models=SimpleNamespace(for_user=lambda user:('student-rewriter','student-generator')))
    request=SimpleNamespace(app=SimpleNamespace(state=state))
    ctx=publish_context(request,own.id)
    assert ctx.embedder.space==row.space and ctx.current_space()==row.space
    chat=user_chat_service(request,env.bob.id,own.id)
    assert chat.embedding.space==row.space and chat.generator=='student-generator'
    assert state.chat_service.embedding=='global'

def test_course_lock_busy_refuses_change_and_cleans_teacher_lock(env):
    values=_vector(env);own=create_course(env.url,name='busy',description=None,creator_id=env.alice.id)
    lock=course_locks.try_acquire(env.url,own.id,holder='worker',lease_seconds=60)
    try:
        with pytest.raises(service.EmbeddingConfigBusy):
            service.save(env.app.state.settings,env.alice.id,**values,transport=env.app.state.embedding_transport)
        assert course_locks.current_holder(env.url,'embedding-teacher:'+env.alice.id) is None
        assert repo.get_config(env.url,env.alice.id) is None
        assert env.app.state.embedding_transport.requests==[]
    finally:course_locks.release(env.url,lock)

def test_new_course_during_rebuild_aborts_switch(env):
    values=_vector(env)
    def new_course(*a,**k):create_course(env.url,name='created during migration',description=None,creator_id=env.alice.id)
    with pytest.raises(service.EmbeddingConfigBusy):
        service.save(env.app.state.settings,env.alice.id,**values,transport=env.app.state.embedding_transport,rebuilder=new_course)
    assert repo.get_config(env.url,env.alice.id) is None

def test_global_reembed_is_blocked_after_teacher_override(env):
    values=_vector(env)
    service.save(env.app.state.settings,env.alice.id,**values,transport=env.app.state.embedding_transport,rebuilder=lambda *a,**k:None)
    import importlib.util
    from pathlib import Path
    import sys
    spec=importlib.util.spec_from_file_location('teacher_reembed_guard',Path(__file__).resolve().parents[2]/'scripts/reembed.py')
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    with pytest.raises(module.OfflineCheckError):module.check_offline(env.url)

from app.repositories import versions

def test_pending_publication_blocks_vector_switch_after_draft_lock_release(env):
    values=_vector(env)
    course=create_course(env.url,name='busy publish',description=None,creator_id=env.alice.id)
    versions.begin_attempt(env.url,course.id,kind='publish',created_by=env.alice.id,lease_seconds=60)
    with pytest.raises(service.EmbeddingConfigBusy):
        service.save(env.app.state.settings,env.alice.id,**values,transport=env.app.state.embedding_transport,rebuilder=lambda *a,**k:None)
    assert repo.get_config(env.url,env.alice.id) is None
    assert env.app.state.embedding_transport.requests==[]

@pytest.mark.parametrize('kind',['publish','rollback'])
def test_vector_switch_blocks_new_attempt_transactionally(env,kind):
    course=create_course(env.url,name='switching',description=None,creator_id=env.alice.id)
    if kind=='rollback': commit(env.url,course.id,nodes=0)
    lock=course_locks.acquire(env.url,'embedding-teacher:'+env.alice.id,holder='embedding-config',lease_seconds=60,wait_seconds=0)
    try:
        with pytest.raises(versions.PublishInProgress):
            versions.begin_attempt(env.url,course.id,kind=kind,created_by=env.alice.id,lease_seconds=60,source_version=1 if kind=='rollback' else None)
    finally: course_locks.release(env.url,lock)

def test_commit_rejects_old_course_space(env):
    values=_vector(env)
    course=create_course(env.url,name='space CAS',description=None,creator_id=env.alice.id)
    service.save(env.app.state.settings,env.alice.id,**values,transport=env.app.state.embedding_transport,rebuilder=lambda *a,**k:None)
    attempt=versions.begin_attempt(env.url,course.id,kind='publish',created_by=env.alice.id,lease_seconds=60)
    import hashlib
    snapshot=b'{"snapshot_format":1}'
    versions.record_snapshot(env.url,attempt.version_id,snapshot=snapshot,digest='sha256:'+hashlib.sha256(snapshot).hexdigest(),node_count=0,edge_count=0,excluded={'low_confidence_nodes':0,'low_confidence_edges':0,'cascaded_edges':0},draft_revision=0,task_watermark=0,embedding_space='fake/4')
    versions.mark_materialized(env.url,attempt.version_id)
    with pytest.raises(versions.CommitRejected,match='embedding configuration changed'):
        with versions.immediate(env.url) as db:
            versions.commit_attempt(db,attempt.version_id,expected_pointer=None,published_from_revision=0)
    assert versions.current_version(env.url,course.id) is None
