"""Encrypted teacher embedding rows; course ownership chooses the credential."""
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from app.repositories.sqlite import connect
from app.repositories.model_configs import SealedKey

@dataclass(frozen=True)
class EmbeddingConfigRow:
    user_id: str
    base_url: str
    model: str
    dimensions: int
    sealed: SealedKey = field(repr=False)
    key_hint: str
    space: str
    revision: str
    version: int
    updated_at: str

def get_config(sqlite_url: str, user_id: str) -> EmbeddingConfigRow | None:
    with connect(sqlite_url) as db:
        row = db.execute('SELECT user_id,base_url,model,dimensions,key_ciphertext,key_nonce,key_hint,space,revision,version,updated_at FROM teacher_embedding_configs WHERE user_id=?', (user_id,)).fetchone()
    if row is None:
        return None
    return EmbeddingConfigRow(*row[:4], SealedKey(bytes(row[4]),bytes(row[5])), *row[6:])

def for_course(sqlite_url: str, course_id: str) -> EmbeddingConfigRow | None:
    with connect(sqlite_url) as db:
        row = db.execute('SELECT teacher_id FROM courses WHERE id=?',(course_id,)).fetchone()
    return get_config(sqlite_url,row[0]) if row else None

def owned_courses(sqlite_url: str, user_id: str) -> list[str]:
    with connect(sqlite_url) as db:
        return [r[0] for r in db.execute('SELECT id FROM courses WHERE teacher_id=? ORDER BY id',(user_id,))]


def active_publication(db: sqlite3.Connection, user_id: str) -> tuple | None:
    return db.execute("SELECT 1 FROM graph_versions v JOIN courses c ON c.id=v.course_id WHERE c.teacher_id=? AND v.state IN ('preparing','materialized')",(user_id,)).fetchone()


@contextmanager
def config_update(sqlite_url: str, user_id: str) -> Iterator[tuple[sqlite3.Connection, tuple | None]]:
    """Open the original save transaction and expose its publication check to the caller.

    An exception closes the connection without COMMIT, preserving SQLite's implicit rollback.
    """
    with connect(sqlite_url) as db:
        db.execute('BEGIN IMMEDIATE')
        publishing = db.execute("SELECT 1 FROM graph_versions v JOIN courses c ON c.id=v.course_id WHERE c.teacher_id=? AND v.state IN ('preparing','materialized')",(user_id,)).fetchone()
        yield db, publishing
        db.execute('COMMIT')


def config_revision(db: sqlite3.Connection, user_id: str) -> tuple | None:
    return db.execute('SELECT revision FROM teacher_embedding_configs WHERE user_id=?',(user_id,)).fetchone()


def owned_courses_in_connection(db: sqlite3.Connection, user_id: str) -> list[str]:
    return [r[0] for r in db.execute('SELECT id FROM courses WHERE teacher_id=? ORDER BY id',(user_id,))]


def current_lock(db: sqlite3.Connection, course_id: str, token: str) -> tuple | None:
    return db.execute('SELECT 1 FROM course_locks WHERE course_id=? AND token=? AND expires_at>=unixepoch()',
                      (course_id,token)).fetchone()


def upsert_config(
    db: sqlite3.Connection, user_id: str, *, base_url: str, model: str, dimensions: int,
    sealed: SealedKey, key_hint: str, target: str, revision: str,
) -> None:
    db.execute('''INSERT INTO teacher_embedding_configs
              (user_id,base_url,model,dimensions,key_ciphertext,key_nonce,key_hint,space,revision,version)
              VALUES (?,?,?,?,?,?,?,?,?,1) ON CONFLICT(user_id) DO UPDATE SET
              base_url=excluded.base_url,model=excluded.model,dimensions=excluded.dimensions,
              key_ciphertext=excluded.key_ciphertext,key_nonce=excluded.key_nonce,key_hint=excluded.key_hint,
              space=excluded.space,revision=excluded.revision,version=teacher_embedding_configs.version+1,
              updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')''',
              (user_id,base_url,model,dimensions,sealed.ciphertext,sealed.nonce,key_hint,target,revision))


def update_committed_spaces(db: sqlite3.Connection, user_id: str, target: str) -> None:
    db.execute("UPDATE graph_versions SET embedding_space=? WHERE state='committed' AND course_id IN (SELECT id FROM courses WHERE teacher_id=?)",(target,user_id))


def course_chunk_texts(db: sqlite3.Connection, course_id: str) -> dict[str, str]:
    return {r[0]:r[1] for r in db.execute('SELECT chunk_id,text FROM chunks WHERE course_id=?',(course_id,))}


def committed_versions(db: sqlite3.Connection, course_id: str) -> list[tuple[str, int]]:
    return list(db.execute("SELECT version_id,node_count FROM graph_versions WHERE course_id=? AND state='committed'",(course_id,)))


def await_vector_indexes(driver) -> None:
    driver.execute_query('CALL db.awaitIndexes(60)',database_='neo4j')


def graph_inventory(driver, course: str) -> list[dict]:
    records,_,_=driver.execute_query('''MATCH (n) WHERE n.course_id=$course AND (n:Chunk OR n:KnowledgePoint)
              RETURN CASE WHEN n:Chunk THEN 'Chunk' ELSE 'KnowledgePoint' END AS kind,
              coalesce(n.chunk_id,n.kp_id) AS id,n.version_id AS version,n.name AS name,n.definition AS definition
              ORDER BY kind,id,version''',course=course,database_='neo4j')
    return [dict(r) for r in records]


def vector_readiness(driver, course: str, prop: str, dimensions: int):
    records,_,_=driver.execute_query(f'''MATCH (n) WHERE n.course_id=$course AND (n:Chunk OR n:KnowledgePoint)
              RETURN count(n) AS total,sum(CASE WHEN n.{prop} IS NOT NULL AND size(n.{prop})=$dimensions THEN 1 ELSE 0 END) AS ready''',
              course=course,dimensions=dimensions,database_='neo4j')
    return records
