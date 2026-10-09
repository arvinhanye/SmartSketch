"""Teacher-owned vector configuration and additive, course-scoped reindexing.

The active row is switched only after all new properties are written and verified.
Old properties/indexes remain usable by in-flight student requests and for recovery.
"""
from __future__ import annotations
import hashlib
import time
import uuid
from contextlib import ExitStack
from pydantic import SecretStr
from app.repositories import embedding_configs as rows, course_locks
from app.repositories.sqlite import connect
from app.repositories.graph_migrations import GraphVectorWriter, vector_property
from app.services.model_configs import _cipher, _check_key, normalize_model, KeyRequired
from app.services.ai.outbound import check_endpoint_url, build_transport
from app.services.ai.compatible import CompatibleEmbeddingClient
from app.services.ai.embeddings import EmbeddingAdapter, embedding_calls
from app.repositories.model_calls import SqliteCallStore
from app.services.ai.client import ModelCallError

class EmbeddingConfigBusy(Exception):
    pass
class EmbeddingConfigFailure(Exception):
    pass

def domain(user_id: str) -> str:
    return 'embedding:' + user_id

def space_id(user_id: str, base_url: str, model: str, dimensions: int) -> str:
    identity = hashlib.sha256((base_url + '\n' + model).encode()).hexdigest()[:24]
    return f'real/teacher-{user_id}/{identity}/{dimensions}'

def public(settings, user_id: str) -> dict:
    row = rows.get_config(settings.SQLITE_URL,user_id)
    if row is None:
        return {'configured':False, 'base_url':settings.EMBEDDING_BASE_URL,
                'model':settings.EMBEDDING_MODEL,'dimensions':settings.EMBEDDING_DIMENSIONS}
    return {'configured':True,'base_url':row.base_url,'model':row.model,'dimensions':row.dimensions,
            'key_hint':row.key_hint,'version':row.version,'updated_at':row.updated_at}

def candidate(settings, user_id: str, *, base_url: str, model: str, dimensions: int, api_key: str | None):
    cipher = _cipher(settings)
    base_url = base_url.strip().rstrip("/")
    check_endpoint_url(base_url,allow_private=settings.MODEL_ENDPOINT_ALLOW_PRIVATE)
    model = normalize_model(model)
    if type(dimensions) is not int or not 1 <= dimensions <= 4096:
        raise ValueError('invalid_dimensions')
    old = rows.get_config(settings.SQLITE_URL,user_id)
    if api_key is None:
        if old is None or old.base_url != base_url:
            raise KeyRequired()
        api_key = cipher.open(domain(user_id),old.sealed)
    _check_key(api_key)
    target = space_id(user_id,base_url,model,dimensions)
    configured = settings.model_copy(update={'EMBEDDING_MODE':'online','EMBEDDING_BASE_URL':base_url,
        'EMBEDDING_MODEL':model,'EMBEDDING_DIMENSIONS':dimensions,'EMBEDDING_API_KEY':SecretStr(api_key)})
    return configured, api_key, target, old

def adapter(settings, *, space: str, transport=None, record: bool=True):
    client = CompatibleEmbeddingClient(
        settings.EMBEDDING_BASE_URL,settings.EMBEDDING_API_KEY.get_secret_value(),transport=transport or build_transport(settings),
        batch_size=settings.EMBEDDING_BATCH_SIZE,default_timeout_seconds=settings.LLM_REQUEST_TIMEOUT_SECONDS)
    return EmbeddingAdapter(settings,client,space=space,
                            store=SqliteCallStore(settings.SQLITE_URL) if record else None)

def for_course(settings, course_id: str):
    row = rows.for_course(settings.SQLITE_URL,course_id)
    if row is None:
        return None
    key = _cipher(settings).open(domain(row.user_id),row.sealed)
    configured = settings.model_copy(update={'EMBEDDING_MODE':'online','EMBEDDING_BASE_URL':row.base_url,
        'EMBEDDING_MODEL':row.model,'EMBEDDING_DIMENSIONS':row.dimensions,'EMBEDDING_API_KEY':SecretStr(key)})
    return adapter(configured,space=row.space)

def course_space(settings, course_id: str):
    from app.repositories.graph_migrations import sqlite_current_space
    def read():
        row = rows.for_course(settings.SQLITE_URL,course_id)
        return row.space if row else sqlite_current_space(settings.SQLITE_URL)()
    return read

def test(settings, user_id: str, *, transport=None, **values) -> dict:
    configured, _, target, _ = candidate(settings,user_id,**values)
    started=time.monotonic()
    try:
        client=adapter(configured,space=target,transport=transport,record=False)
        client.embed(('连接测试',),deadline=started+15)
        return {'ok':True,'latency_ms':round((time.monotonic()-started)*1000)}
    except ModelCallError as error:
        return {'ok':False,'error_class':error.error_class.value,'latency_ms':round((time.monotonic()-started)*1000)}
    except Exception as error:
        cause = error.__cause__
        error_class = cause.error_class.value if isinstance(cause, ModelCallError) else 'malformed_response'
        return {'ok':False,'error_class':error_class,'latency_ms':round((time.monotonic()-started)*1000)}

def save(settings,user_id: str, *, transport=None, rebuilder=None, **values) -> dict:
    # Cipher and validation before any model/network operation or write.
    configured,key,target,old=candidate(settings,user_id,**values)
    lease=max(60,settings.PUBLISH_LEASE_SECONDS)
    with ExitStack() as stack:
        locks=[]
        def take(course):
            lock=course_locks.acquire(settings.SQLITE_URL,course,holder='embedding-config',
                                     lease_seconds=lease,wait_seconds=0)
            if lock is None: raise EmbeddingConfigBusy()
            stack.enter_context(course_locks.held(settings.SQLITE_URL,lock,lease_seconds=lease))
            locks.append(lock)
        take('embedding-teacher:'+user_id)
        # Serialize updates and refresh after obtaining the teacher lock.
        configured,key,target,old=candidate(settings,user_id,**values)
        courses=rows.owned_courses(settings.SQLITE_URL,user_id)
        for course in courses: take(course)
        # Publication leases outlive their draft locks. Refuse all active attempts;
        # begin_attempt also checks our owner lock in its insertion transaction.
        with connect(settings.SQLITE_URL) as db:
            if db.execute("SELECT 1 FROM graph_versions v JOIN courses c ON c.id=v.course_id WHERE c.teacher_id=? AND v.state IN ('preparing','materialized')",(user_id,)).fetchone():
                raise EmbeddingConfigBusy()
        result=test(settings,user_id,transport=transport,**values)
        if not result['ok']: raise EmbeddingConfigFailure(result['error_class'])
        if old is None or old.space != target:
            (rebuilder or rebuild_courses)(configured,user_id,courses,target,transport=transport)
        sealed=_cipher(settings).seal(domain(user_id),key)
        with connect(settings.SQLITE_URL) as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute("SELECT 1 FROM graph_versions v JOIN courses c ON c.id=v.course_id WHERE c.teacher_id=? AND v.state IN ('preparing','materialized')",(user_id,)).fetchone():
                raise EmbeddingConfigBusy()
            current=db.execute('SELECT revision FROM teacher_embedding_configs WHERE user_id=?',(user_id,)).fetchone()
            owned=[r[0] for r in db.execute('SELECT id FROM courses WHERE teacher_id=? ORDER BY id',(user_id,))]
            if owned!=courses or (current[0] if current else None)!=(old.revision if old else None):
                raise EmbeddingConfigBusy()
            for lock in locks:
                if db.execute('SELECT 1 FROM course_locks WHERE course_id=? AND token=? AND expires_at>=unixepoch()',
                              (lock.course_id,lock.token)).fetchone() is None: raise EmbeddingConfigBusy()
            db.execute('''INSERT INTO teacher_embedding_configs
              (user_id,base_url,model,dimensions,key_ciphertext,key_nonce,key_hint,space,revision,version)
              VALUES (?,?,?,?,?,?,?,?,?,1) ON CONFLICT(user_id) DO UPDATE SET
              base_url=excluded.base_url,model=excluded.model,dimensions=excluded.dimensions,
              key_ciphertext=excluded.key_ciphertext,key_nonce=excluded.key_nonce,key_hint=excluded.key_hint,
              space=excluded.space,revision=excluded.revision,version=teacher_embedding_configs.version+1,
              updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')''',
              (user_id,configured.EMBEDDING_BASE_URL,configured.EMBEDDING_MODEL,configured.EMBEDDING_DIMENSIONS,
               sealed.ciphertext,sealed.nonce,key[-4:],target,uuid.uuid4().hex))
            db.execute("UPDATE graph_versions SET embedding_space=? WHERE state='committed' AND course_id IN (SELECT id FROM courses WHERE teacher_id=?)",(target,user_id))
            db.execute('COMMIT')
    return public(settings,user_id)

def rebuild_courses(settings, user_id: str, courses: list[str], target: str, *, transport=None):
    from neo4j import GraphDatabase
    driver=GraphDatabase.driver(settings.NEO4J_URI,auth=(settings.NEO4J_USER,settings.NEO4J_PASSWORD.get_secret_value()))
    try:
        writer=GraphVectorWriter(driver,lambda:target)
        writer.ensure_vector_indexes(target)
        driver.execute_query('CALL db.awaitIndexes(60)',database_='neo4j')
        embedder=adapter(settings,space=target,transport=transport)
        prop=vector_property(target)
        def inventory(course):
            records,_,_=driver.execute_query('''MATCH (n) WHERE n.course_id=$course AND (n:Chunk OR n:KnowledgePoint)
              RETURN CASE WHEN n:Chunk THEN 'Chunk' ELSE 'KnowledgePoint' END AS kind,
              coalesce(n.chunk_id,n.kp_id) AS id,n.version_id AS version,n.name AS name,n.definition AS definition
              ORDER BY kind,id,version''',course=course,database_='neo4j')
            return [dict(r) for r in records]
        for course in courses:
            stock=inventory(course)
            with connect(settings.SQLITE_URL) as db:
                texts={r[0]:r[1] for r in db.execute('SELECT chunk_id,text FROM chunks WHERE course_id=?',(course,))}
                versions=list(db.execute("SELECT version_id,node_count FROM graph_versions WHERE course_id=? AND state='committed'",(course,)))
            for version,count in versions:
                if sum(item['kind']=='KnowledgePoint' and item['version']==version for item in stock)!=count:
                    raise EmbeddingConfigFailure('version_stock_mismatch')
            for start in range(0,len(stock),settings.EMBEDDING_BATCH_SIZE):
                batch=stock[start:start+settings.EMBEDDING_BATCH_SIZE]
                content=[]
                for item in batch:
                    if item['kind']=='Chunk':
                        if item['id'] not in texts: raise EmbeddingConfigFailure('missing_chunk')
                        content.append(texts[item['id']])
                    else:
                        if not isinstance(item['name'],str) or not isinstance(item['definition'],str):
                            raise EmbeddingConfigFailure('missing_definition')
                        content.append(item['name']+'\n'+item['definition'])
                with embedding_calls(course_id=course,request_id='embedding-config-'+uuid.uuid4().hex,user_id=user_id):
                    vectors=embedder.embed(content)
                for item,vector in zip(batch,vectors,strict=True):
                    writer.write_runtime(item['kind'],course,item['version'] if item['kind']=='KnowledgePoint' else None,item['id'],vector)
            if inventory(course)!=stock: raise EmbeddingConfigBusy()
            records,_,_=driver.execute_query(f'''MATCH (n) WHERE n.course_id=$course AND (n:Chunk OR n:KnowledgePoint)
              RETURN count(n) AS total,sum(CASE WHEN n.{prop} IS NOT NULL AND size(n.{prop})=$dimensions THEN 1 ELSE 0 END) AS ready''',
              course=course,dimensions=settings.EMBEDDING_DIMENSIONS,database_='neo4j')
            if not records or records[0]['total']!=len(stock) or records[0]['ready']!=len(stock):
                raise EmbeddingConfigFailure('verification_failed')
    finally:
        driver.close()
