import hashlib
from types import SimpleNamespace
from app.config import Settings
from app.repositories.sqlite import migrate
from app.repositories.embedding_space import read_or_initialize_space
from app.repositories.graph_migrations import vector_property
from app.tools.install_probe import probe_install

def test_probe_is_read_only_and_rejects_index_or_space_mismatch(tmp_path):
    path=tmp_path/'fixture.sqlite3'; url='sqlite:///'+str(path)
    migrate(url);read_or_initialize_space(url,'',1024,1)
    suffix=vector_property('fake/1024').removeprefix('embedding_')
    rows=[{'name':kind+'_embedding_'+suffix,'type':'VECTOR','state':'ONLINE','options':{'indexConfig':{'vector.dimensions':1024}}} for kind in ['chunk','kp']]
    class Driver:
        def execute_query(self,query,**kwargs):
            assert query.startswith('SHOW INDEXES') and kwargs['routing_']=='r'
            return SimpleNamespace(records=rows)
        def close(self): pass
    settings=Settings(SQLITE_URL=url,LLM_MODE='fake',EMBEDDING_MODE='fake')
    before=hashlib.sha256(path.read_bytes()).digest()
    assert probe_install(settings,driver_factory=lambda *a,**k:Driver())=={'schema_current':True,'embedding_space_matches':True,'vector_indexes_online':True}
    assert hashlib.sha256(path.read_bytes()).digest()==before
    rows.pop()
    assert not probe_install(settings,driver_factory=lambda *a,**k:Driver())['vector_indexes_online']
    settings=Settings(SQLITE_URL=url,LLM_MODE='fake',EMBEDDING_MODE='fake',EMBEDDING_DIMENSIONS=256)
    assert not probe_install(settings,driver_factory=lambda *a,**k:Driver())['embedding_space_matches']
