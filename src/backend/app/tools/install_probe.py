"""Read-only installed schema/space/index checks, with no model calls."""
import hashlib
import json
import sqlite3
import sys
from contextlib import closing
from app.config import embedding_space_identity
from app.repositories.sqlite import database_path, MIGRATIONS_DIR
from app.repositories.graph_migrations import vector_property

def probe_install(settings,driver_factory=None):
    result={'schema_current':False,'embedding_space_matches':False,'vector_indexes_online':False}
    try:
        with closing(sqlite3.connect(database_path(settings.SQLITE_URL).as_uri()+'?mode=ro',uri=True,timeout=5)) as db:
            db.execute('PRAGMA query_only=ON')
            history={r[0]:(r[1],r[2]) for r in db.execute('SELECT version,filename,checksum FROM schema_migrations')}
            expected={p.name.split('_')[0]:(p.name,hashlib.sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest()) for p in MIGRATIONS_DIR.glob('[0-9][0-9][0-9]_*.sql')}
            result['schema_current']=history==expected
            row=db.execute('SELECT model,dimensions,is_fake FROM embedding_space_state WHERE singleton=1').fetchone()
            configured=embedding_space_identity(settings)
            result['embedding_space_matches']=row is not None and tuple(row)==configured
        if not all(result[k] for k in ('schema_current','embedding_space_matches')): return result
        model,dimensions,is_fake=configured
        space=f'fake/{dimensions}' if is_fake else f'real/{model}/{dimensions}'
        suffix=vector_property(space).removeprefix('embedding_')
        if driver_factory is None:
            from neo4j import GraphDatabase
            driver_factory=GraphDatabase.driver
        driver=driver_factory(settings.NEO4J_URI,auth=(settings.NEO4J_USER,settings.NEO4J_PASSWORD.get_secret_value()))
        try:
            rows=driver.execute_query('SHOW INDEXES YIELD name,type,state,options RETURN name,type,state,options',routing_='r').records
            indexes={r['name']:r for r in rows}
            result['vector_indexes_online']=all(name in indexes and indexes[name]['type']=='VECTOR' and indexes[name]['state']=='ONLINE' and indexes[name]['options']['indexConfig']['vector.dimensions']==dimensions for name in (f'chunk_embedding_{suffix}',f'kp_embedding_{suffix}'))
        finally: driver.close()
    except Exception:
        pass  # Diagnostic contract exposes only readiness booleans, never connection details.
    return result

def main():
    try:
        from app.config import load_settings
        result=probe_install(load_settings())
    except Exception:
        result={'schema_current':False,'embedding_space_matches':False,'vector_indexes_online':False}
    print(json.dumps(result))
    return 0 if all(result.values()) else 1

if __name__=='__main__':sys.exit(main())
