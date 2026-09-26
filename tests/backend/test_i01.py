"""I01 raw progress persistence and transaction semantics."""
import sqlite3
import uuid

import pytest

from app.repositories.accounts import insert_account
from app.repositories.courses import create_course
from app.repositories.sqlite import connect, migrate
from app.repositories.progress import (
    InvalidProgressTarget, ProgressUpdate, StalePublishedVersion,
    read_progress, read_committed_progress, write_progress,
)
from app.repositories import progress as progress_repository
from app.repositories.versions import immediate
from app.services.versions.snapshot import DraftGraph, DraftNode, Revision, build_snapshot

HASH = '$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA'


@pytest.fixture
def env(tmp_path):
    url = f"sqlite:///{(tmp_path / 'state.sqlite').as_posix()}"
    migrate(url)
    teacher = insert_account(url, account_id=uuid.uuid4().hex, username='teacher', password_hash=HASH, role='teacher')
    alice = insert_account(url, account_id=uuid.uuid4().hex, username='alice', password_hash=HASH, role='student')
    bob = insert_account(url, account_id=uuid.uuid4().hex, username='bobby', password_hash=HASH, role='student')
    course = create_course(url, name='Course A', description=None, creator_id=teacher.id)
    other = create_course(url, name='Course B', description=None, creator_id=teacher.id)
    version_id = '0' * 26
    with connect(url) as db:
        db.execute("UPDATE courses SET published_version_id=?, published_version=1 WHERE id=?", (version_id, course.id))
    return url, alice.id, bob.id, course.id, other.id, version_id


def test_migration_schema_and_isolation(env):
    url, alice, bob, course, other, version = env
    with connect(url) as db:
        columns = {row[1] for row in db.execute('PRAGMA table_info(learning_progress)')}
    assert {'user_id', 'course_id', 'kp_id', 'status', 'write_seq', 'updated_at'} <= columns
    write_progress(url, user_id=alice, course_id=course, version_id=version,
                   published_kp_ids={'a'}, updates=[ProgressUpdate('a', 'mastered')])
    assert [row.status for row in read_progress(url, user_id=alice, course_id=course)] == ['mastered']
    assert read_progress(url, user_id=bob, course_id=course) == ()
    assert read_progress(url, user_id=alice, course_id=other) == ()


def test_idempotent_and_forced_same_value_write(env):
    url, alice, _, course, _, version = env
    update = [ProgressUpdate('a', 'mastered')]
    first = write_progress(url, user_id=alice, course_id=course, version_id=version,
                           published_kp_ids={'a'}, updates=update)[0]
    second = write_progress(url, user_id=alice, course_id=course, version_id=version,
                            published_kp_ids={'a'}, updates=update)[0]
    assert second == first
    forced = write_progress(url, user_id=alice, course_id=course, version_id=version,
                            published_kp_ids={'a'}, updates=[ProgressUpdate('a', 'mastered', force=True)])[0]
    assert forced.write_seq == first.write_seq + 1
    with connect(url) as db:
        assert db.execute('SELECT value FROM commit_sequence').fetchone()[0] == forced.write_seq


def test_invalid_batch_and_stale_pointer_are_atomic(env):
    url, alice, _, course, _, version = env
    with pytest.raises(InvalidProgressTarget):
        write_progress(url, user_id=alice, course_id=course, version_id=version,
                       published_kp_ids={'a'}, updates=[ProgressUpdate('a', 'mastered'), ProgressUpdate('other', 'learning')])
    assert read_progress(url, user_id=alice, course_id=course) == ()
    with connect(url) as db:
        assert db.execute('SELECT value FROM commit_sequence').fetchone()[0] == 0
        db.execute("UPDATE courses SET published_version_id=?, published_version=2 WHERE id=?", ('1' * 26, course))
    with pytest.raises(StalePublishedVersion):
        write_progress(url, user_id=alice, course_id=course, version_id=version,
                       published_kp_ids={'a'}, updates=[ProgressUpdate('a', 'mastered')])
    assert read_progress(url, user_id=alice, course_id=course) == ()


def test_progress_write_joins_caller_transaction(env):
    url, alice, _, course, _, version = env
    with pytest.raises(RuntimeError, match='abort caller transaction'):
        with immediate(url) as database:
            progress_repository.write_progress_in_transaction(
                database, user_id=alice, course_id=course, version_id=version,
                published_kp_ids={'a'}, updates=[ProgressUpdate('a', 'mastered')],
            )
            assert database.execute(
                'SELECT status FROM learning_progress WHERE user_id=? AND course_id=? AND kp_id=?',
                (alice, course, 'a'),
            ).fetchone() == ('mastered',)
            assert database.execute('SELECT value FROM commit_sequence').fetchone()[0] == 1
            raise RuntimeError('abort caller transaction')
    assert read_progress(url, user_id=alice, course_id=course) == ()
    with connect(url) as database:
        assert database.execute('SELECT value FROM commit_sequence').fetchone()[0] == 0


def test_dormant_row_survives_and_validation(env):
    url, alice, _, course, _, version = env
    write_progress(url, user_id=alice, course_id=course, version_id=version,
                   published_kp_ids={'a', 'b'}, updates=[ProgressUpdate('a', 'learning'), ProgressUpdate('b', 'mastered')])
    assert {row.kp_id for row in read_progress(url, user_id=alice, course_id=course)} == {'a', 'b'}
    with pytest.raises(InvalidProgressTarget):
        write_progress(url, user_id=alice, course_id=course, version_id=version,
                       published_kp_ids={'a'}, updates=[ProgressUpdate('b', 'unknown')])
    assert {row.kp_id for row in read_progress(url, user_id=alice, course_id=course)} == {'a', 'b'}
    with pytest.raises(ValueError):
        write_progress(url, user_id=alice, course_id=course, version_id=version,
                       published_kp_ids={'a'}, updates=[ProgressUpdate('a', 'bad')])


def test_committed_union_keeps_dormant_and_reports_dirty(env, caplog):
    url, alice, _, course, _, version = env
    revision = Revision('rev-1', 'mat-1', 'sha256:' + 'a' * 64, 'txt/1+chunk/1@1500-200')
    node = DraftNode(kp_id='old', name='Old', type='concept', definition='Definition',
                     status='approved', source_refs=('chunk-1',))
    snap = build_snapshot(DraftGraph(course, [revision], [], [node], [], {'chunk-1': 'rev-1'})).snapshot
    with connect(url) as db:
        db.execute("""INSERT INTO graph_versions(version_id, course_id, version, kind, state, expires_at,
                   snapshot_json, digest, committed_at, commit_seq)
                   VALUES (?, ?, 1, 'publish', 'committed', 1, ?, ?, '2026-01-01T00:00:00Z', 1)""",
                   (version, course, snap.canonical.decode(), snap.digest))
        db.execute("UPDATE commit_sequence SET value=1")
        db.execute("""INSERT INTO learning_progress VALUES (?, ?, 'old', 'mastered', '2026-01-01', 2)""",
                   (alice, course))
        db.execute("""INSERT INTO learning_progress VALUES (?, ?, 'foreign', 'learning', '2026-01-01', 3)""",
                   (alice, course))
        db.execute("UPDATE commit_sequence SET value=3")
    rows = read_committed_progress(url, user_id=alice, course_id=course)
    assert [row.kp_id for row in rows] == ['old']
    assert 'foreign' in caplog.text
