"""Append-only relation versions are scoped, atomic and rollback protected."""
import sqlite3
from pathlib import Path

import pytest

from app.repositories.sqlite import connect
from tests.backend.test_fusion_storage import state


def write(db,cid,**extra):
    from app.repositories.relation_revisions import put_revision
    return put_revision(db,course_id=cid,task_id='task',section_id='s',input_digest='digest',
                        status='done',attempts=1,result={'chunk_ids':['r-0'],'relations':[]},
                        metadata={'window_coverage':{'status':'complete'}},**extra)


def test_revision_requires_transaction_and_is_scoped_immutable_idempotent(state):
    from app.repositories.relation_revisions import read_revision
    url,cid=state
    with connect(url) as db:
        with pytest.raises(RuntimeError): write(db,cid)
        db.execute('BEGIN IMMEDIATE')
        assert write(db,cid)
        assert not write(db,cid)
        db.execute('COMMIT')
        row=read_revision(db,course_id=cid,task_id='task',section_id='s',input_digest='digest')
        assert row.status=='done' and row.result['relations']==[]
        assert read_revision(db,course_id='other',task_id='task',section_id='s',input_digest='digest') is None
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE task_relation_revisions SET result='{}'")
        db.execute('BEGIN IMMEDIATE')
        with pytest.raises(sqlite3.IntegrityError): write(db,'other')
        db.execute('ROLLBACK')
        db.execute('BEGIN IMMEDIATE'); db.execute('DELETE FROM task_relation_revisions'); db.execute('ROLLBACK')
        assert read_revision(db,course_id=cid,task_id='task',section_id='s',input_digest='digest')==row


def test_failed_revision_never_has_candidate_payload(state):
    from app.repositories.relation_revisions import put_revision,read_revision
    url,cid=state
    with connect(url) as db:
        db.execute('BEGIN IMMEDIATE')
        with pytest.raises(sqlite3.IntegrityError):
            put_revision(db,course_id=cid,task_id='task',section_id='s',input_digest='bad',
                         status='failed',attempts=1,error_code='OUTPUT_INVALID',result={})
        assert put_revision(db,course_id=cid,task_id='task',section_id='s',input_digest='bad',
                            status='failed',attempts=1,error_code='OUTPUT_INVALID')
        db.execute('COMMIT')
        assert read_revision(db,course_id=cid,task_id='task',section_id='s',input_digest='bad').result is None


def test_rollback_refuses_active_pinned_task_then_preserves_original_checkpoints(state):
    from app.repositories.extraction_checkpoints import write_checkpoint
    url,cid=state
    path=Path(__file__).parents[2]/'src/backend/migrations/023_relation_revisions.sql'
    statements=[line.split('-- ROLLBACK: ',1)[1] for line in path.read_text().splitlines()
                if line.startswith('-- ROLLBACK: ')]
    with connect(url) as db:
        db.execute('BEGIN IMMEDIATE')
        write_checkpoint(db,course_id=cid,task_id='task',unit_kind='chunk',unit_id='r-0',status='done',
                         attempts=1,result={'entities':[]},metadata={'normalization_version':1})
        db.execute('COMMIT')
        db.execute('BEGIN IMMEDIATE')
        with pytest.raises(sqlite3.IntegrityError):
            for s in statements: db.execute(s)
        db.execute('ROLLBACK')
        db.execute("UPDATE processing_tasks SET stage='cancelled',cancel_requested=1 WHERE id='task'")
        db.execute('BEGIN IMMEDIATE')
        for s in statements: db.execute(s)
        db.execute('COMMIT')
        assert db.execute('SELECT count(*) FROM task_chunk_checkpoints').fetchone()[0]==1
        assert db.execute("SELECT count(*) FROM sqlite_master WHERE name='task_relation_revisions'").fetchone()[0]==0

    from app.repositories.sqlite import migrate
    migrate(url)
    with connect(url) as db:
        assert db.execute('SELECT count(*) FROM task_relation_revisions').fetchone()[0]==0
        assert db.execute('SELECT count(*) FROM task_chunk_checkpoints').fetchone()[0]==1
