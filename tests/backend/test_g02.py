"""G02 version metadata and publish/rollback attempts against a real migrated SQLite database.

Acceptance: the same idempotency key (attempt ``version_id``) never yields two versions; one
version number per course; failures stay queryable (specs/teacher-review-publish.md V2, V5, V6).
"""

from __future__ import annotations

import hashlib
import sqlite3
import uuid

import pytest

from app.repositories import versions
from app.repositories.accounts import insert_account
from app.repositories.courses import create_course
from app.repositories.sqlite import MIGRATIONS_DIR, connect, migrate
from app.repositories.versions import CommitRejected, PublishInProgress, VersionNotFound

VALID_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA"
LEASE = 60
EXCLUDED = {"low_confidence_nodes": 1, "low_confidence_edges": 0, "cascaded_edges": 2}


@pytest.fixture
def env(tmp_path):
    url = f"sqlite:///{(tmp_path / 'state.sqlite3').as_posix()}"
    migrate(url)
    teacher = insert_account(url, account_id=uuid.uuid4().hex, username="teacher1", password_hash=VALID_HASH,
                             role="teacher")
    course = create_course(url, name="A", description=None, creator_id=teacher.id)
    other = create_course(url, name="B", description=None, creator_id=teacher.id)
    return url, teacher, course.id, other.id


def sql(url, query, *params):
    with connect(url) as db:
        return db.execute(query, params).fetchall()


def snapshot_bytes(tag="v1"):
    return f'{{"snapshot_format":1,"tag":"{tag}"}}'.encode()


def digest(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def pointer(url, course_id):
    return sql(url, "SELECT published_version_id, published_version, published_from_revision FROM courses "
                    "WHERE id = ?", course_id)[0]


def prepare(url, course_id, teacher, tag="v1", revision=3):
    attempt = versions.begin_attempt(url, course_id, kind="publish", created_by=teacher.id, lease_seconds=LEASE)
    data = snapshot_bytes(tag)
    assert versions.record_snapshot(url, attempt.version_id, snapshot=data, digest=digest(data), node_count=5,
                                    edge_count=4, excluded=EXCLUDED, draft_revision=revision, task_watermark=7,
                                    embedding_space="bge-m3@1024")
    assert versions.mark_materialized(url, attempt.version_id)
    return attempt


def commit(url, version_id, expected, revision=3):
    with versions.immediate(url) as db:
        return versions.commit_attempt(db, version_id, expected_pointer=expected, published_from_revision=revision)


def publish(url, course_id, teacher, tag="v1", revision=3):
    attempt = prepare(url, course_id, teacher, tag, revision)
    return commit(url, attempt.version_id, pointer(url, course_id)[0], revision)


# --- attempts ---------------------------------------------------------------------------------


def test_begin_creates_a_preparing_attempt_with_a_ulid_and_lease(env):
    url, teacher, course, _ = env
    attempt = versions.begin_attempt(url, course, kind="publish", created_by=teacher.id, lease_seconds=LEASE)
    assert len(attempt.version_id) == 26 and attempt.version_id.isalnum()
    assert (attempt.state, attempt.kind, attempt.version, attempt.commit_seq) == ("preparing", "publish", None, None)
    [(remaining,)] = sql(url, "SELECT expires_at - unixepoch() FROM graph_versions WHERE version_id = ?",
                         attempt.version_id)
    assert LEASE - 2 <= remaining <= LEASE
    assert versions.new_version_id() != versions.new_version_id()


def test_one_active_attempt_per_course(env):
    url, teacher, course, other = env
    first = versions.begin_attempt(url, course, kind="publish", created_by=teacher.id, lease_seconds=LEASE)
    with pytest.raises(PublishInProgress):
        versions.begin_attempt(url, course, kind="publish", created_by=teacher.id, lease_seconds=LEASE)
    versions.begin_attempt(url, other, kind="publish", created_by=teacher.id, lease_seconds=LEASE)
    assert versions.fail_attempt(url, first.version_id, "blocked")
    versions.begin_attempt(url, course, kind="publish", created_by=None, lease_seconds=LEASE)


def test_reusing_a_version_id_is_rejected(env):
    url, teacher, course, other = env
    attempt = versions.begin_attempt(url, course, kind="publish", created_by=teacher.id, lease_seconds=LEASE)
    versions.fail_attempt(url, attempt.version_id, "x")
    with pytest.raises(sqlite3.IntegrityError):
        versions.begin_attempt(url, other, kind="publish", created_by=teacher.id, lease_seconds=LEASE,
                               version_id=attempt.version_id)


def test_record_snapshot_checks_digest_and_state(env):
    url, teacher, course, _ = env
    attempt = versions.begin_attempt(url, course, kind="publish", created_by=teacher.id, lease_seconds=LEASE)
    data = snapshot_bytes()
    common = dict(node_count=1, edge_count=0, excluded=EXCLUDED, draft_revision=0, task_watermark=0,
                  embedding_space="s")
    with pytest.raises(ValueError):
        versions.record_snapshot(url, attempt.version_id, snapshot=data, digest=digest(b"other"), **common)
    assert not versions.mark_materialized(url, attempt.version_id)  # no snapshot yet
    assert versions.record_snapshot(url, attempt.version_id, snapshot=data, digest=digest(data), **common)
    assert versions.read_snapshot(url, attempt.version_id) == data
    assert versions.mark_materialized(url, attempt.version_id)
    assert not versions.record_snapshot(url, attempt.version_id, snapshot=data, digest=digest(data), **common)
    record = versions.get_version(url, attempt.version_id)
    assert record.excluded == EXCLUDED and record.embedding_space == "s" and record.state == "materialized"


def test_heartbeat_extends_only_live_attempts(env):
    url, teacher, course, _ = env
    attempt = versions.begin_attempt(url, course, kind="publish", created_by=teacher.id, lease_seconds=5)
    assert versions.heartbeat(url, attempt.version_id, lease_seconds=LEASE)
    sql(url, "UPDATE graph_versions SET expires_at = unixepoch() - 1 WHERE version_id = ?", attempt.version_id)
    assert not versions.heartbeat(url, attempt.version_id, lease_seconds=LEASE)
    versions.fail_attempt(url, attempt.version_id, "lease expired")
    assert not versions.heartbeat(url, attempt.version_id, lease_seconds=LEASE)


# --- commit -----------------------------------------------------------------------------------


def test_commit_assigns_gapless_numbers_sequence_and_moves_the_pointer(env):
    url, teacher, course, other = env
    first = publish(url, course, teacher, "a", revision=3)
    assert (first.state, first.version, first.commit_seq) == ("committed", 1, 1)
    assert first.committed_at is not None
    assert pointer(url, course) == (first.version_id, 1, 3)

    failed = prepare(url, course, teacher, "b")
    versions.fail_attempt(url, failed.version_id, "P9 digest mismatch")
    in_other = publish(url, other, teacher, "c")
    second = publish(url, course, teacher, "d", revision=9)

    assert second.version == 2  # the failed attempt used no number
    assert in_other.version == 1 and in_other.commit_seq == 2 and second.commit_seq == 3  # one global sequence
    assert pointer(url, course) == (second.version_id, 2, 9)
    assert [v.version for v in versions.list_versions(url, course)] == [2, 1]
    assert versions.current_version(url, course).version_id == second.version_id
    assert versions.get_committed(url, course, 1).version_id == first.version_id
    assert versions.get_committed(url, other, 2) is None


def test_same_attempt_never_becomes_two_versions(env):
    url, teacher, course, _ = env
    attempt = prepare(url, course, teacher)
    commit(url, attempt.version_id, None)
    with pytest.raises(CommitRejected):
        commit(url, attempt.version_id, attempt.version_id)
    assert sql(url, "SELECT count(*) FROM graph_versions WHERE course_id = ? AND state = 'committed'", course) == [(1,)]
    assert sql(url, "SELECT value FROM commit_sequence") == [(1,)]


@pytest.mark.parametrize("setup, expected_pointer", [
    ("preparing", None),
    ("expired", None),
    ("failed", None),
    ("pointer_moved", "someone-else"),
])
def test_rejected_commit_rolls_back_the_whole_transaction(env, setup, expected_pointer):
    url, teacher, course, _ = env
    attempt = versions.begin_attempt(url, course, kind="publish", created_by=teacher.id, lease_seconds=LEASE)
    if setup != "preparing":
        data = snapshot_bytes()
        versions.record_snapshot(url, attempt.version_id, snapshot=data, digest=digest(data), node_count=1,
                                 edge_count=0, excluded=EXCLUDED, draft_revision=0, task_watermark=0,
                                 embedding_space="s")
        versions.mark_materialized(url, attempt.version_id)
    if setup == "expired":
        sql(url, "UPDATE graph_versions SET expires_at = unixepoch() - 1 WHERE version_id = ?", attempt.version_id)
    if setup == "failed":
        versions.fail_attempt(url, attempt.version_id, "swept")
    before = versions.get_version(url, attempt.version_id)
    with pytest.raises(CommitRejected):
        with versions.immediate(url) as db:
            db.execute("UPDATE courses SET draft_revision = draft_revision + 100 WHERE id = ?", (course,))
            versions.commit_attempt(db, attempt.version_id, expected_pointer=expected_pointer,
                                    published_from_revision=0)
    assert versions.get_version(url, attempt.version_id) == before
    assert pointer(url, course) == (None, None, None)
    assert sql(url, "SELECT value FROM commit_sequence") == [(0,)]
    assert sql(url, "SELECT draft_revision FROM courses WHERE id = ?", course) == [(0,)]


def test_version_numbers_are_unique_per_course_even_for_raw_writes(env):
    url, teacher, course, _ = env
    first = publish(url, course, teacher)
    attempt = prepare(url, course, teacher, "b")
    with pytest.raises(sqlite3.IntegrityError):
        sql(url, "UPDATE graph_versions SET state = 'committed', version = 1, commit_seq = 99, "
                 "committed_at = 'x' WHERE version_id = ?", attempt.version_id)
    assert first.version == 1


def test_commit_helpers_require_the_callers_transaction(env):
    url, teacher, course, _ = env
    attempt = prepare(url, course, teacher)
    with connect(url) as db:
        for call in (lambda: versions.next_commit_seq(db),
                     lambda: versions.commit_attempt(db, attempt.version_id, expected_pointer=None,
                                                     published_from_revision=0),
                     lambda: versions.discard_attempt(db, attempt.version_id, expected_pointer=None,
                                                      published_from_revision=0)):
            with pytest.raises(RuntimeError):
                call()


# --- idempotent path, failure, audit -------------------------------------------------------------


def test_discard_removes_the_attempt_and_records_the_revision(env):
    url, teacher, course, _ = env
    current = publish(url, course, teacher, revision=3)
    attempt = versions.begin_attempt(url, course, kind="publish", created_by=teacher.id, lease_seconds=LEASE)
    with versions.immediate(url) as db:
        versions.discard_attempt(db, attempt.version_id, expected_pointer=current.version_id,
                                 published_from_revision=8)
    assert versions.get_version(url, attempt.version_id) is None
    assert pointer(url, course) == (current.version_id, 1, 8)
    assert [a.version_id for a in versions.list_attempts(url, course)] == [current.version_id]


@pytest.mark.parametrize("case", ["failed", "pointer_moved", "never_published"])
def test_discard_is_rejected_when_its_conditions_fail(env, case):
    url, teacher, course, _ = env
    current = publish(url, course, teacher) if case != "never_published" else None
    attempt = versions.begin_attempt(url, course, kind="publish", created_by=teacher.id, lease_seconds=LEASE)
    if case == "failed":
        versions.fail_attempt(url, attempt.version_id, "swept")
    expected = "moved" if case == "pointer_moved" else (current.version_id if current else None)
    with pytest.raises(CommitRejected):
        with versions.immediate(url) as db:
            versions.discard_attempt(db, attempt.version_id, expected_pointer=expected, published_from_revision=8)
    assert versions.get_version(url, attempt.version_id) is not None


def test_failures_are_kept_queryable_and_only_active_attempts_fail(env):
    url, teacher, course, _ = env
    committed = publish(url, course, teacher)
    attempt = versions.begin_attempt(url, course, kind="publish", created_by=teacher.id, lease_seconds=LEASE)
    assert versions.fail_attempt(url, attempt.version_id, "PUBLISH_BLOCKED")
    assert not versions.fail_attempt(url, attempt.version_id, "again")
    assert not versions.fail_attempt(url, committed.version_id, "late sweep")
    assert versions.set_cleanup_pending(url, attempt.version_id, True)
    assert not versions.set_cleanup_pending(url, committed.version_id, True)

    audit = {a.version_id: a for a in versions.list_attempts(url, course)}
    assert audit[attempt.version_id].state == "failed"
    assert audit[attempt.version_id].failure_reason == "PUBLISH_BLOCKED"
    assert audit[attempt.version_id].cleanup_pending is True
    assert audit[attempt.version_id].created_by == teacher.id
    assert [v.version_id for v in versions.list_versions(url, course)] == [committed.version_id]
    assert versions.set_cleanup_pending(url, attempt.version_id, False)
    assert versions.get_version(url, attempt.version_id).cleanup_pending is False


def test_committed_versions_are_never_deleted_or_changed(env):
    url, teacher, course, _ = env
    committed = publish(url, course, teacher)
    for statement in ("DELETE FROM graph_versions WHERE version_id = ?",
                      "UPDATE graph_versions SET digest = 'sha256:' || substr(digest, 8) WHERE version_id = ?",
                      "UPDATE graph_versions SET state = 'failed', failure_reason = 'x' WHERE version_id = ?"):
        with pytest.raises(sqlite3.IntegrityError):
            sql(url, statement, committed.version_id)
    sql(url, "UPDATE graph_versions SET embedding_space = 'new-space' WHERE version_id = ?", committed.version_id)
    assert versions.get_version(url, committed.version_id).embedding_space == "new-space"


# --- rollback attempts --------------------------------------------------------------------------


def test_rollback_attempt_copies_the_source_snapshot(env):
    url, teacher, course, _ = env
    v1 = publish(url, course, teacher, "one")
    publish(url, course, teacher, "two")
    attempt = versions.begin_attempt(url, course, kind="rollback", created_by=teacher.id, lease_seconds=LEASE,
                                     source_version=1)
    assert (attempt.kind, attempt.source_version, attempt.digest) == ("rollback", 1, v1.digest)
    assert versions.read_snapshot(url, attempt.version_id) == snapshot_bytes("one")
    assert (attempt.node_count, attempt.excluded, attempt.embedding_space) == (5, EXCLUDED, "bge-m3@1024")
    assert attempt.draft_revision is None and attempt.task_watermark is None
    assert not versions.record_snapshot(url, attempt.version_id, snapshot=b"{}", digest=digest(b"{}"),
                                        node_count=0, edge_count=0, excluded=EXCLUDED, draft_revision=0,
                                        task_watermark=0, embedding_space="s")
    assert versions.mark_materialized(url, attempt.version_id)
    rolled = commit(url, attempt.version_id, pointer(url, course)[0], revision=-1)
    assert rolled.version == 3 and rolled.digest == v1.digest
    assert pointer(url, course) == (attempt.version_id, 3, -1)


def test_rollback_source_must_be_a_committed_version_of_the_course(env):
    url, teacher, course, other = env
    publish(url, other, teacher)
    for source in (1, 7):
        with pytest.raises(VersionNotFound):
            versions.begin_attempt(url, course, kind="rollback", created_by=teacher.id, lease_seconds=LEASE,
                                   source_version=source)
    assert versions.list_attempts(url, course) == []
    with pytest.raises(ValueError):
        versions.begin_attempt(url, course, kind="rollback", created_by=teacher.id, lease_seconds=LEASE)
    with pytest.raises(ValueError):
        versions.begin_attempt(url, course, kind="publish", created_by=teacher.id, lease_seconds=LEASE,
                               source_version=1)


# --- migration ----------------------------------------------------------------------------------


def test_migration_010_rolls_back_and_reapplies(env):
    url, *_ = env
    target = next(MIGRATIONS_DIR.glob("*_versions.sql"))

    def rollback_lines(path):
        text = path.read_text(encoding="utf-8")
        return [line.split("ROLLBACK:", 1)[1].strip() for line in text.splitlines() if "ROLLBACK:" in line]

    assert len(rollback_lines(target)) == 5
    later = sorted((p for p in MIGRATIONS_DIR.glob("*.sql") if p.name > target.name), reverse=True)
    database = sqlite3.connect(url.removeprefix("sqlite:///"))
    try:
        with database:
            for path in [*later, target]:
                for line in rollback_lines(path):
                    database.execute(line)
        names = {row[0] for row in database.execute("SELECT name FROM sqlite_master")}
        assert not names & {"graph_versions", "commit_sequence", "graph_versions_committed_frozen"}
    finally:
        database.close()
    migrate(url)
    assert sql(url, "SELECT value FROM commit_sequence") == [(0,)]
