"""F12 teacher graph-edit audit log (ADR-061), through the real app and a real migrated SQLite database.

Acceptance (``docs/atomic-tasks.json`` F12): every audit record carries who / when / which version /
a change summary; a cross-store failure (Neo4j committed, SQLite audit update failed) can be retried
and is never lost; no secret is recorded.

Create / update / unlock run through the API with the in-memory ``FakeStore`` of ``test_f08``;
delete and merge (one Neo4j transaction each) are covered against a real server in
``tests/integration/test_f12.py``.
"""

from __future__ import annotations

import json
import re
import sqlite3
from types import SimpleNamespace

import pytest

from app.repositories import edit_logs
from app.repositories.courses import create_course
from app.repositories.neo4j import GraphScope
from app.repositories.sqlite import MIGRATIONS_DIR, connect, migrate
from app.services.graph import audit
from app.services.graph.edit_node import EditContext, update_node
from test_f08 import CHUNK_TEXT, SECRET, kp, token  # noqa: F401  (fixture helpers shared with F08)
from test_f08 import s  # noqa: F401  (the F08 scenario fixture: app + SQLite + FakeStore)

ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


def logs(s, course_id=None):
    return edit_logs.list_logs(s.url, course_id or s.course.id)


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch):
    monkeypatch.setattr(audit, "_sleep", lambda seconds: None)


# --- who / when / which version / summary --------------------------------------------------


def test_update_is_logged_with_actor_time_versions_and_field_diff(s):
    s.store.nodes["a"] = kp("a", name="栈", importance=0.5)
    before = s.draft_revision()

    assert s.patch("a", {"expected_revision": 1, "name": "  顺序栈 ", "importance": 0.8}).status_code == 200

    [entry] = logs(s)
    assert entry.state == "committed" and entry.resolved_by == "writer" and entry.failure_reason is None
    assert entry.actor_id == s.teacher.id and entry.course_id == s.course.id
    assert entry.action == "update" and entry.kp_id == "a"
    assert entry.draft_revision == before + 1 == s.draft_revision()
    assert (entry.kp_revision_before, entry.kp_revision_after) == (1, 2)
    assert ISO.match(entry.created_at) and ISO.match(entry.resolved_at) and entry.created_at <= entry.resolved_at
    assert entry.summary == {
        "changes": {"name": {"before": "栈", "after": "顺序栈"}, "importance": {"before": 0.5, "after": 0.8}},
        "locked": {"before": False, "after": True},
    }


def test_each_teacher_is_recorded_as_themselves_and_versions_are_consecutive(s):
    s.store.nodes["a"] = kp("a")
    assert s.patch("a", {"expected_revision": 1, "definition": "甲"}).status_code == 200
    assert s.patch("a", {"expected_revision": 2, "definition": "乙"}, user=s.teacher2).status_code == 200
    assert s.unlock("a", {"expected_revision": 3}).status_code == 200

    entries = logs(s)
    assert [(e.action, e.actor_id) for e in entries] == [
        ("update", s.teacher.id), ("update", s.teacher2.id), ("unlock", s.teacher.id)]
    assert [e.draft_revision for e in entries] == list(range(entries[0].draft_revision,
                                                             entries[0].draft_revision + 3))
    assert [(e.kp_revision_before, e.kp_revision_after) for e in entries] == [(1, 2), (2, 3), (3, 4)]
    assert entries[1].summary["changes"] == {"definition": {"before": "甲", "after": "乙"}}
    assert entries[1].summary["locked"] == {"before": True, "after": True}
    assert entries[2].summary == {"locked": {"before": True, "after": False}}
    assert [e.seq for e in entries] == sorted(e.seq for e in entries)


def test_create_is_logged_with_fields_and_sources(s):
    chunk_id = s.chunk("t-done")
    response = s.create({"name": "栈", "type": "concept", "definition": "后进先出",
                         "sources": [{"chunk_id": chunk_id, "evidence_start": 0, "evidence_end": 2}]})
    assert response.status_code == 201, response.text
    kp_id = response.json()["id"]

    [entry] = logs(s)
    assert (entry.action, entry.kp_id, entry.state, entry.actor_id) == ("create", kp_id, "committed", s.teacher.id)
    assert (entry.kp_revision_before, entry.kp_revision_after) == (None, 1)
    assert entry.draft_revision == s.draft_revision()
    assert entry.summary["fields"] == {"name": "栈", "type": "concept", "definition": "后进先出", "aliases": [],
                                       "status": "approved"}
    assert entry.summary["sources"] == [{"chunk_id": chunk_id, "evidence_start": 0, "evidence_end": 2}]


def test_requests_that_write_nothing_are_not_logged(s):
    s.store.nodes["a"] = kp("a", revision=2)
    assert s.patch("a", {"expected_revision": 1, "name": "x"}).status_code == 409      # stale revision
    assert s.patch("missing", {"expected_revision": 1, "name": "x"}).status_code == 404
    assert s.patch("a", {"expected_revision": 2, "name": " "}).status_code == 422      # invalid
    assert s.unlock("a", {"expected_revision": 2}).status_code == 200                  # already unlocked: no-op
    assert s.patch("a", {"expected_revision": 2, "name": "x"}, user=s.student).status_code == 403
    assert s.create({"name": "栈", "type": "concept", "definition": "d", "sources": []}).status_code == 422
    assert logs(s) == []


def test_logs_are_isolated_per_course_and_page_by_seq(s):
    s.store.nodes["a"] = kp("a")
    for revision in range(1, 6):
        assert s.patch("a", {"expected_revision": revision, "importance": revision / 10}).status_code == 200
    first = edit_logs.list_logs(s.url, s.course.id, limit=2)
    rest = edit_logs.list_logs(s.url, s.course.id, after_seq=first[-1].seq, limit=10)
    assert [e.kp_revision_before for e in first + rest] == [1, 2, 3, 4, 5]
    assert edit_logs.list_logs(s.url, "other-course") == []
    assert edit_logs.pending(s.url, s.course.id) == []


# --- Neo4j write fails: the log says so --------------------------------------------------


def test_neo4j_failure_after_bump_is_logged_as_aborted(s):
    s.store.nodes["a"] = kp("a")
    original = s.store.update

    def broken(*args, **kwargs):
        s.store.fail = True
        return original(*args, **kwargs)

    s.store.update = broken
    response = s.patch("a", {"expected_revision": 1, "name": "x"})

    assert response.status_code == 503
    [entry] = logs(s)
    assert (entry.state, entry.failure_reason, entry.resolved_by) == ("aborted", "NEO4J_CONNECTION_FAILED",
                                                                     "writer")
    assert entry.kp_revision_after is None and entry.draft_revision == s.draft_revision()
    assert s.locks() == []


def test_conditional_update_miss_is_logged_as_aborted_conflict(s):
    s.store.nodes["a"] = kp("a")
    original = s.store.update

    def raced(scope, kp_id, expected, changes):  # someone bypassed the course lock
        s.store.nodes["a"]["revision"] = 7
        return original(scope, kp_id, expected, changes)

    s.store.update = raced
    assert s.patch("a", {"expected_revision": 1, "name": "x"}).status_code == 409
    [entry] = logs(s)
    assert (entry.state, entry.failure_reason) == ("aborted", "REVISION_CONFLICT")


# --- cross-store failure: retried, then reconciled ---------------------------------------


def _flaky_resolve(monkeypatch, failures):
    real = edit_logs.resolve
    calls = {"n": 0}

    def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] <= failures:
            raise sqlite3.OperationalError("database is locked")
        return real(*args, **kwargs)

    monkeypatch.setattr(edit_logs, "resolve", flaky)
    return calls


def test_transient_sqlite_failure_after_neo4j_commit_is_retried(s, monkeypatch):
    s.store.nodes["a"] = kp("a")
    # 退避预算写成字面量，断言不得由被测常量派生：否则把 RETRY_DELAYS 归零（重试预算消失）
    # 仍会全绿，验收行「跨库失败可重试」就失去可失效的证据（独立审查 2026-09-26 M2）。
    assert len(audit.RETRY_DELAYS) == 3
    calls = _flaky_resolve(monkeypatch, failures=3)  # succeeds on the last attempt

    assert s.patch("a", {"expected_revision": 1, "name": "x"}).status_code == 200

    assert calls["n"] == 4
    [entry] = logs(s)
    assert (entry.state, entry.kp_revision_after) == ("committed", 2)


def test_persistent_sqlite_failure_leaves_pending_and_the_edit_still_succeeds(s, monkeypatch, caplog):
    s.store.nodes["a"] = kp("a")
    real = edit_logs.resolve
    _flaky_resolve(monkeypatch, failures=10**6)

    response = s.patch("a", {"expected_revision": 1, "name": "x"})

    assert response.status_code == 200 and response.json()["revision"] == 2   # Neo4j committed: not an error
    [entry] = edit_logs.pending(s.url, s.course.id)
    assert (entry.action, entry.kp_revision_before) == ("update", 1)
    assert "left pending for reconcile" in caplog.text

    monkeypatch.setattr(edit_logs, "resolve", real)   # SQLite is back; the next write reconciles first
    assert s.patch("a", {"expected_revision": 2, "name": "y"}).status_code == 200
    first, second = logs(s)
    assert (first.state, first.resolved_by, first.kp_revision_after) == ("committed", "reconcile", 2)
    assert first.summary["changes"]["name"] == {"before": "A", "after": "x"}
    assert (second.state, second.resolved_by) == ("committed", "writer")


class Crash(BaseException):
    """Stands for the process dying: nothing after it runs to completion."""


def test_reconcile_marks_a_write_that_never_reached_neo4j_as_aborted(s, monkeypatch):
    s.store.nodes["a"] = kp("a")
    real_update, real_resolve = s.store.update, edit_logs.resolve

    def died(*args, **kwargs):  # between begin and the Neo4j write; the abort cannot be recorded either
        raise Crash

    s.store.update = died
    _flaky_resolve(monkeypatch, failures=10**6)
    ctx = EditContext(s.url, s.store, s.reader, lock_seconds=30, wait_seconds=0, actor_id=s.teacher.id)
    with pytest.raises(Crash):
        update_node(ctx, s.course.id, "a", 1, {"name": "x"})
    s.store.update = real_update
    monkeypatch.setattr(edit_logs, "resolve", real_resolve)
    [entry] = edit_logs.pending(s.url, s.course.id)
    assert s.store.nodes["a"]["revision"] == 1 and s.locks() == []

    assert s.patch("a", {"expected_revision": 1, "name": "y"}).status_code == 200
    first, second = logs(s)
    assert (first.event_id, first.state, first.failure_reason, first.resolved_by) == (
        entry.event_id, "aborted", "not_applied", "reconcile")
    assert (second.state, second.kp_revision_after) == ("committed", 2)


def _scope(s):
    return GraphScope(s.course.id, "draft", effective_task_ids=("t-done",))


def _ctx(s):
    return SimpleNamespace(sqlite_url=s.url, store=s.store, actor_id=s.teacher.id)


@pytest.mark.parametrize("action, before, node, applied", [
    ("update", 1, kp("a", revision=2, locked=True), True),
    ("update", 1, kp("a", revision=1, locked=True), False),   # locked earlier, write never landed
    ("update", 1, kp("a", revision=2, locked=False), False),  # an automated flow bumped it instead
    ("update", 1, None, False),
    ("merge", 3, kp("a", revision=4, locked=True), True),
    ("merge", 3, kp("a", revision=3, locked=False), False),
    ("unlock", 2, kp("a", revision=3, locked=False), True),
    ("unlock", 2, kp("a", revision=5, locked=False), True),   # automated flows may touch it once unlocked
    ("unlock", 2, kp("a", revision=2, locked=True), False),
    ("create", None, kp("a", revision=1, locked=True, contrib_manual=True), True),
    ("create", None, None, False),
    ("delete", 4, None, True),
    ("delete", 4, kp("a", revision=4), False),
])
def test_reconcile_rules(s, action, before, node, applied):
    if node is not None:
        s.store.nodes["a"] = node
    event_id, _ = edit_logs.begin(s.url, course_id=s.course.id, actor_id=s.teacher.id, action=action, kp_id="a",
                                  kp_revision_before=before, summary={"k": 1})

    assert audit.reconcile(_ctx(s), _scope(s)) == [(event_id, "committed" if applied else "aborted")]
    [entry] = logs(s)
    assert entry.resolved_by == "reconcile" and entry.summary == {"k": 1}
    assert entry.failure_reason == (None if applied else "not_applied")
    assert audit.reconcile(_ctx(s), _scope(s)) == []   # idempotent


def test_reconcile_only_touches_its_own_course(s):
    other = create_course(s.url, name="操作系统", description=None, creator_id=s.teacher.id).id
    edit_logs.begin(s.url, course_id=other, actor_id=s.teacher.id, action="delete", kp_id="a",
                    kp_revision_before=1, summary={})
    assert audit.reconcile(_ctx(s), _scope(s)) == []
    assert [e.state for e in edit_logs.list_logs(s.url, other)] == ["pending"]


def test_resolve_is_idempotent_and_resolved_rows_are_frozen(s):
    event_id, _ = edit_logs.begin(s.url, course_id=s.course.id, actor_id=s.teacher.id, action="update", kp_id="a",
                                  kp_revision_before=1, summary={})
    assert edit_logs.resolve(s.url, event_id, state="committed", resolved_by="writer", kp_revision_after=2)
    assert not edit_logs.resolve(s.url, event_id, state="aborted", resolved_by="reconcile", failure_reason="x")
    with connect(s.url) as db:
        with pytest.raises(sqlite3.IntegrityError, match="frozen"):
            db.execute("UPDATE graph_edit_logs SET actor_id = actor_id WHERE event_id = ?", (event_id,))
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            db.execute("DELETE FROM graph_edit_logs WHERE event_id = ?", (event_id,))
    [entry] = logs(s)
    assert (entry.state, entry.kp_revision_after) == ("committed", 2)


def test_begin_is_atomic_with_the_draft_revision_bump(s):
    before = s.draft_revision()
    with pytest.raises(sqlite3.IntegrityError):  # unknown actor violates the users FK
        edit_logs.begin(s.url, course_id=s.course.id, actor_id="nobody", action="update", kp_id="a",
                        kp_revision_before=1, summary={})
    assert s.draft_revision() == before and logs(s) == []
    with pytest.raises(LookupError):
        edit_logs.begin(s.url, course_id="missing", actor_id=s.teacher.id, action="update", kp_id="a",
                        kp_revision_before=1, summary={})
    with pytest.raises(ValueError):
        edit_logs.begin(s.url, course_id=s.course.id, actor_id=s.teacher.id, action="publish", kp_id="a",
                        kp_revision_before=1, summary={})


def test_internal_calls_without_actor_bump_but_do_not_log(s):
    before = s.draft_revision()
    ctx = SimpleNamespace(sqlite_url=s.url, store=s.store, actor_id=None)
    pending = audit.begin(ctx, s.course.id, "update", "a", revision_before=1, summary={})
    assert pending.event_id is None and pending.draft_revision == before + 1 == s.draft_revision()
    assert audit.commit(ctx, pending, revision_after=2) and audit.abort(ctx, pending, RuntimeError())
    assert logs(s) == []


# --- no secrets -----------------------------------------------------------------------------

_SECRETS = [
    "sk-live0123456789abcdefghijklmnop",
    "Bearer abcdefghijklmnop.qrstuvwx",
    "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.c2lnbmF0dXJlLXZhbHVl",
    "AKIAABCDEFGHIJKLMNOP",
    "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA",
    "-----BEGIN RSA PRIVATE KEY-----\nMIIEow\n-----END RSA PRIVATE KEY-----",
]


def test_no_token_password_or_key_reaches_the_log(s):
    s.store.nodes["a"] = kp("a")
    definition = "栈的定义。" + " ".join(_SECRETS) + " password=hunter2 api_key: abc123"

    response = s.patch("a", {"expected_revision": 1, "definition": definition, "aliases": [_SECRETS[0]]})

    assert response.status_code == 200
    with connect(s.url) as db:
        dump = json.dumps(db.execute("SELECT * FROM graph_edit_logs").fetchall(), ensure_ascii=False)
    request_token = token(s.teacher)
    for secret in [*_SECRETS, "hunter2", "abc123", "MIIEow", SECRET, request_token.split(".")[2]]:
        assert secret not in dump
    [entry] = logs(s)
    after = entry.summary["changes"]["definition"]["after"]
    assert after.startswith("栈的定义。") and "password=[REDACTED]" in after and "api_key: [REDACTED]" in after
    assert entry.summary["changes"]["aliases"]["after"] == ["[REDACTED]"]
    assert set(entry.summary) == {"changes", "locked"}


def test_summary_keeps_only_whitelisted_fields_and_truncates_long_text():
    node = {"name": "栈", "definition": "长" * 2000, "contrib_tasks": ["t1"], "embedding": [0.1] * 8,
            "merged_from": ["x"], "source": "ai", "locked": True}
    summary = audit.delete_summary(node, relations=3)
    assert summary == {"fields": {"name": "栈", "definition": "长" * (audit.MAX_TEXT - 1) + "…"}, "locked": True,
                       "relations_deleted": 3}
    assert audit.redact("普通文本 token 与 secret 两个词") == "普通文本 token 与 secret 两个词"


# --- migration -------------------------------------------------------------------------------


def test_migration_012_rolls_back_and_reapplies(s):
    target = next(MIGRATIONS_DIR.glob("*_edit_logs.sql"))

    def rollback_lines(path):
        text = path.read_text(encoding="utf-8")
        return [line.split("ROLLBACK:", 1)[1].strip() for line in text.splitlines() if "ROLLBACK:" in line]

    assert len(rollback_lines(target)) == 6
    later = sorted((p for p in MIGRATIONS_DIR.glob("*.sql") if p.name > target.name), reverse=True)
    database = sqlite3.connect(s.url.removeprefix("sqlite:///"))
    try:
        with database:
            for path in [*later, target]:
                for line in rollback_lines(path):
                    database.execute(line)
        names = {row[0] for row in database.execute("SELECT name FROM sqlite_master")}
        assert not {n for n in names if "edit_logs" in n}
    finally:
        database.close()
    migrate(s.url)
    s.store.nodes["a"] = kp("a")
    assert s.patch("a", {"expected_revision": 1, "name": "x"}).status_code == 200
    assert [e.state for e in logs(s)] == ["committed"]
