"""F08 teacher knowledge-point edits and the manual-edit lock (ADR-035), through the real app and SQLite.

Acceptance (``docs/atomic-tasks.json`` F08): a later write never overwrites an earlier one
(``expected_revision``); a teacher edit locks the node; unlocking is a separate, explicit action;
automated flows respect the lock. The Neo4j side is an in-memory ``FakeStore`` that applies the
same conditional-update rule as the Cypher in ``app.repositories.graph_edit``; the Cypher itself,
and the automated-flow guard (F04 skips locked nodes, then writes again after an unlock), run
against a real server in ``tests/integration/test_f08.py``.
"""

from __future__ import annotations

import copy
import time
import uuid
from pathlib import Path

import jsonschema
import pytest
import yaml
from fastapi.testclient import TestClient

from app.main import create_app
from app.repositories.accounts import insert_account
from app.repositories.chunks import persist_revision_chunks
from app.repositories.courses import add_member, create_course
from app.repositories.neo4j import RepositoryConnectionError
from app.repositories.sqlite import connect, migrate
from app.services.auth import issue_access_token
from app.services.chunking import ChunkSource, SemanticChunk, chunking_version
from app.services.parsers.models import RevisionKey, SourceLocator

ROOT = Path(__file__).resolve().parents[2]
SECRET = "f08-test-signing-key-0123456789abcdefghij"
VALID_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA"
PARSER = "txt/1+" + chunking_version(1500, 200)
CHUNK_TEXT = "栈是一种后进先出的线性表。"

_SPEC = yaml.safe_load((ROOT / "src/contracts/api.v1.yaml").read_text(encoding="utf-8"))


def _rewrite(node):
    if isinstance(node, dict):
        return {key: (value.replace("#/components/schemas/", "#/$defs/")
                      if key == "$ref" and isinstance(value, str) else _rewrite(value))
                for key, value in node.items()}
    if isinstance(node, list):
        return [_rewrite(item) for item in node]
    return node


_DEFS = _rewrite(copy.deepcopy(_SPEC["components"]["schemas"]))


def assert_schema(name, instance):
    jsonschema.Draft202012Validator({"$defs": _DEFS, "$ref": f"#/$defs/{name}"}).validate(instance)


# --- fakes -------------------------------------------------------------------------------


def kp(kp_id, **extra):
    props = {"kp_id": kp_id, "name": kp_id.upper(), "aliases": [], "type": "concept", "definition": f"{kp_id} 的定义",
             "confidence": 0.9, "status": "draft", "source": "ai", "locked": False, "revision": 1,
             "contrib_tasks": ["t-done"], "contrib_manual": False}
    props.update(extra)
    return props


class FakeStore:
    """In-memory draft: visibility by V, and updates conditional on ``revision`` like the Cypher."""

    def __init__(self):
        self.nodes: dict[str, dict] = {}
        self.chapters: set[str] = set()
        self.evidence: list[tuple[str, dict]] = []
        self.writes: list[tuple[str, object]] = []
        self.fail = False

    def _visible(self, scope, p):
        return p.get("contrib_manual") or any(t in scope.effective_task_ids for t in p.get("contrib_tasks", []))

    def _check(self, scope):
        assert scope.version_id == "draft" and scope.effective_task_ids is not None
        if self.fail:
            raise RepositoryConnectionError()

    @staticmethod
    def _public(p):
        return {k: v for k, v in p.items() if k not in ("contrib_tasks", "contrib_manual")}

    def node(self, scope, kp_id):
        self._check(scope)
        p = self.nodes.get(kp_id)
        return self._public(p) if p is not None and self._visible(scope, p) else None

    def chapter_visible(self, scope, chapter_id):
        self._check(scope)
        return chapter_id in self.chapters

    def _conditional(self, scope, kp_id, expected, changes, locked):
        p = self.nodes.get(kp_id)
        if p is None or not self._visible(scope, p) or p["revision"] != expected:
            return None
        p.update(changes)
        p.update(locked=locked, contrib_manual=True, revision=p["revision"] + 1)
        return self._public(p)

    def update(self, scope, kp_id, expected_revision, changes):
        self._check(scope)
        self.writes.append(("update", (kp_id, dict(changes))))
        return self._conditional(scope, kp_id, expected_revision, changes, True)

    def unlock(self, scope, kp_id, expected_revision):
        self._check(scope)
        self.writes.append(("unlock", kp_id))
        return self._conditional(scope, kp_id, expected_revision, {}, False)

    def create(self, scope, kp_id, props, sources):
        self._check(scope)
        assert sources
        self.writes.append(("create", kp_id))
        self.nodes[kp_id] = {"kp_id": kp_id, **props, "source": "manual", "locked": True, "contrib_manual": True,
                             "contrib_tasks": [], "revision": 1}
        self.evidence.extend((kp_id, dict(s)) for s in sources)
        return self._public(self.nodes[kp_id])

    # GraphReader subset used for ``level``
    def nodes_of(self, scope):
        return [self._public(p) for p in self.nodes.values() if self._visible(scope, p)]


class FakeReader:
    def __init__(self, store):
        self.store = store
        self.edges_list: list[dict] = []

    def nodes(self, scope, reader, kp_ids=None):
        return [p for p in self.store.nodes_of(scope) if kp_ids is None or p["kp_id"] in kp_ids]

    def edges(self, scope, reader, kp_ids=None):
        return list(self.edges_list)


# --- scenario ----------------------------------------------------------------------------


def _account(url, name, role):
    return insert_account(url, account_id=uuid.uuid4().hex, username=name, password_hash=VALID_HASH, role=role)


def token(user):
    return issue_access_token(user_id=user.id, role=user.role, secret=SECRET.encode(),
                              issued_at=int(time.time()), ttl_seconds=3600)


class Scenario:
    def __init__(self, client, url, teacher, teacher2, student, outsider, course, store, reader):
        self.client, self.url, self.store, self.reader = client, url, store, reader
        self.teacher, self.teacher2, self.student, self.outsider = teacher, teacher2, student, outsider
        self.course = course

    def call(self, method, path, user, body=None, course_id=None):
        headers = {"Authorization": f"Bearer {token(user)}"}
        return self.client.request(method, f"/api/v1/courses/{course_id or self.course.id}{path}",
                                   headers=headers, json=body)

    def patch(self, kid, body, user=None):
        return self.call("PATCH", f"/kp/{kid}", user or self.teacher, body)

    def unlock(self, kid, body, user=None):
        return self.call("POST", f"/kp/{kid}/unlock", user or self.teacher, body)

    def create(self, body, user=None):
        return self.call("POST", "/kp", user or self.teacher, body)

    def draft_revision(self, course_id=None):
        with connect(self.url) as db:
            return db.execute("SELECT draft_revision FROM courses WHERE id = ?",
                              (course_id or self.course.id,)).fetchone()[0]

    def locks(self):
        with connect(self.url) as db:
            return db.execute("SELECT course_id, holder FROM course_locks").fetchall()

    def task(self, task_id, stage, course_id=None, doc="doc1"):
        course_id = course_id or self.course.id
        with connect(self.url) as db:
            if db.execute("SELECT 1 FROM materials WHERE id = ?", (doc,)).fetchone() is None:
                db.execute(
                    "INSERT INTO materials (id, course_id, filename, format, size_bytes, content_hash, storage_name)"
                    " VALUES (?, ?, 'a.txt', 'txt', 1, ?, ?)",
                    (doc, course_id, "sha256:" + uuid.uuid4().hex * 2, "stored-" + doc))
            failed = stage == "failed"
            db.execute("INSERT INTO processing_tasks (id, course_id, document_id, idempotency_key, stage, progress,"
                       " error_code, error_message) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                       (task_id, course_id, doc, task_id, stage, 0 if stage == "queued" else 0.5,
                        "INTERNAL_ERROR" if failed else None, "失败" if failed else None))

    def chunk(self, task_id, course_id=None, doc="doc1", text=CHUNK_TEXT):
        """Record a revision for ``task_id`` with one chunk; return the chunk id."""
        course_id = course_id or self.course.id
        key = RevisionKey(document_id=doc, content_hash="sha256:" + uuid.uuid4().hex * 2, parser_version=PARSER)
        chunk = SemanticChunk(0, text, ("第二章",), (ChunkSource(0, 0, len(text), SourceLocator(page=3)),))
        _, written = persist_revision_chunks(self.url, course_id=course_id, task_id=task_id, key=key, chunks=[chunk])
        return (written.inserted + written.existing)[0]


@pytest.fixture
def s(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'state.sqlite3').as_posix()}"
    migrate(url)
    teacher = _account(url, "teacher1", "teacher")
    teacher2 = _account(url, "teacher3", "teacher")
    student = _account(url, "student1", "student")
    outsider = _account(url, "teacher2", "teacher")
    course = create_course(url, name="数据结构", description=None, creator_id=teacher.id)
    add_member(url, course_id=course.id, user_id=teacher2.id, role="teacher", added_by=teacher.id)
    add_member(url, course_id=course.id, user_id=student.id, role="student", added_by=teacher.id)
    monkeypatch.setenv("SQLITE_URL", url)
    monkeypatch.setenv("AUTH_JWT_SECRET", SECRET)
    monkeypatch.setenv("COURSE_LOCK_WAIT_SECONDS", "0")
    application = create_app()
    store = FakeStore()
    reader = FakeReader(store)
    application.state.graph_node_store = store
    application.state.graph_reader = reader
    scenario = Scenario(None, url, teacher, teacher2, student, outsider, course, store, reader)
    scenario.task("t-done", "completed")
    scenario.task("t-running", "extracting")
    with TestClient(application) as client:
        scenario.client = client
        yield scenario


# --- PATCH: edit locks the node ---------------------------------------------------------


def test_teacher_edit_writes_fields_locks_node_and_bumps_revisions(s):
    s.store.nodes["a"] = kp("a")
    before = s.draft_revision()

    response = s.patch("a", {"expected_revision": 1, "name": "  栈  ", "definition": "后进先出",
                             "aliases": ["堆栈", "堆栈", " Stack "], "difficulty": 0.3, "status": "approved"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert_schema("KnowledgePoint", body)
    assert body["name"] == "栈" and body["definition"] == "后进先出" and body["aliases"] == ["堆栈", "Stack"]
    assert body["difficulty"] == 0.3 and body["status"] == "approved"
    assert body["locked"] is True and body["revision"] == 2 and body["source"] == "ai"
    assert s.store.nodes["a"]["contrib_manual"] is True
    assert s.draft_revision() == before + 1
    assert s.locks() == []  # released


def test_edit_that_changes_nothing_still_locks(s):
    s.store.nodes["a"] = kp("a", name="栈")
    body = s.patch("a", {"expected_revision": 1, "name": "栈"}).json()
    assert body["locked"] is True and body["revision"] == 2


def test_later_writer_with_stale_revision_gets_conflict_with_current_content_and_nothing_changes(s):
    s.store.nodes["a"] = kp("a", importance=0.5)
    assert s.patch("a", {"expected_revision": 1, "name": "栈（教师甲）"}).status_code == 200
    before = s.draft_revision()

    response = s.patch("a", {"expected_revision": 1, "name": "栈（教师乙）"}, user=s.teacher2)

    assert response.status_code == 409
    body = response.json()
    assert_schema("Error", body)
    assert body["code"] == "REVISION_CONFLICT"
    details = body["details"]
    assert details["kp_id"] == "a" and details["expected_revision"] == 1 and details["current_revision"] == 2
    assert details["current"]["name"] == "栈（教师甲）" and details["current"]["locked"] is True
    assert details["current"]["importance"] == 0.5 and details["current"]["aliases"] == []
    assert s.store.nodes["a"]["name"] == "栈（教师甲）"
    assert s.draft_revision() == before  # rejected before any write
    assert [w for w in s.store.writes if w[0] == "update"] == [("update", ("a", {"name": "栈（教师甲）"}))]
    assert s.locks() == []


def test_retry_with_current_revision_succeeds(s):
    s.store.nodes["a"] = kp("a", revision=4)
    assert s.patch("a", {"expected_revision": 3, "name": "x"}).status_code == 409
    assert s.patch("a", {"expected_revision": 4, "name": "x"}).json()["revision"] == 5


@pytest.mark.parametrize("node", [None, kp("a", contrib_tasks=["t-running"])], ids=["missing", "invisible"])
def test_missing_or_invisible_node_is_404_without_write(s, node):
    if node is not None:
        s.store.nodes["a"] = node
    before = s.draft_revision()
    response = s.patch("a", {"expected_revision": 1, "name": "x"})
    assert response.status_code == 404 and response.json()["code"] == "NOT_FOUND"
    assert s.draft_revision() == before and s.store.writes == []


def test_manual_contribution_is_visible_without_tasks(s):
    s.store.nodes["m"] = kp("m", contrib_tasks=[], contrib_manual=True, source="manual", locked=True)
    assert s.patch("m", {"expected_revision": 1, "definition": "新定义"}).status_code == 200


@pytest.mark.parametrize("body, field, reason", [
    ({"name": "x"}, "expected_revision", "missing"),
    ({"expected_revision": 0, "name": "x"}, "expected_revision", "greater_than_equal"),
    ({"expected_revision": True, "name": "x"}, "expected_revision", "int_type"),
    ({"expected_revision": 1}, "", "no_changes"),
    ({"expected_revision": 1, "locked": False}, "locked", "extra_forbidden"),
    ({"expected_revision": 1, "revision": 9, "name": "x"}, "revision", "extra_forbidden"),
    ({"expected_revision": 1, "name": None}, "name", "string_type"),
    ({"expected_revision": 1, "name": "   "}, "name", "blank"),
    ({"expected_revision": 1, "definition": ""}, "definition", "blank"),
    ({"expected_revision": 1, "aliases": ["ok", " "]}, "aliases.1", "blank"),
    ({"expected_revision": 1, "aliases": "栈"}, "aliases", "list_type"),
    ({"expected_revision": 1, "type": "lemma"}, "type", "enum"),
    ({"expected_revision": 1, "status": "published"}, "status", "enum"),
    ({"expected_revision": 1, "importance": 1.5}, "importance", "out_of_range"),
    ({"expected_revision": 1, "difficulty": None}, "difficulty", "float_type"),
])
def test_patch_body_is_validated_and_cannot_unlock(s, body, field, reason):
    s.store.nodes["a"] = kp("a", locked=True)
    before = s.draft_revision()

    response = s.patch("a", body)

    assert response.status_code == 422
    payload = response.json()
    assert payload["code"] == "VALIDATION_ERROR"
    assert {"in": "body", "field": field, "reason": reason} in payload["details"]["fields"]
    assert s.store.nodes["a"]["locked"] is True and s.store.nodes["a"]["revision"] == 1
    assert s.draft_revision() == before and s.locks() == []


def test_patch_body_must_be_an_object(s):
    s.store.nodes["a"] = kp("a")
    response = s.patch("a", ["name"])
    assert response.status_code == 422 and response.json()["code"] == "VALIDATION_ERROR"


# --- authorization ------------------------------------------------------------------------


@pytest.mark.parametrize("who, code", [("student", "ROLE_FORBIDDEN"), ("outsider", "COURSE_FORBIDDEN")])
@pytest.mark.parametrize("op", ["patch", "unlock", "create"])
def test_only_course_teachers_can_write(s, who, code, op):
    s.store.nodes["a"] = kp("a", locked=True)
    user = getattr(s, who)
    if op == "patch":
        response = s.patch("a", {"expected_revision": 1, "name": "x"}, user=user)
    elif op == "unlock":
        response = s.unlock("a", {"expected_revision": 1}, user=user)
    else:
        response = s.create({"name": "x", "type": "concept", "definition": "d",
                             "sources": [{"chunk_id": "c"}]}, user=user)
    assert response.status_code == 403 and response.json()["code"] == code
    assert s.store.writes == [] and s.store.nodes["a"]["locked"] is True


def test_unauthenticated_write_is_401(s):
    response = s.client.patch(f"/api/v1/courses/{s.course.id}/kp/a", json={"expected_revision": 1, "name": "x"})
    assert response.status_code == 401


# --- course write lock --------------------------------------------------------------------


def _hold_lock(s, holder):
    with connect(s.url) as db:
        db.execute("INSERT INTO course_locks (course_id, holder, token, expires_at) VALUES (?, ?, ?, unixepoch() + 600)",
                   (s.course.id, holder, "t" * 32))


@pytest.mark.parametrize("op", ["patch", "unlock", "create"])
def test_busy_course_lock_is_409_course_busy_with_holder(s, op):
    s.store.nodes["a"] = kp("a", locked=True)
    chunk_id = s.chunk("t-done")
    _hold_lock(s, "publish")
    before = s.draft_revision()

    if op == "patch":
        response = s.patch("a", {"expected_revision": 1, "name": "x"})
    elif op == "unlock":
        response = s.unlock("a", {"expected_revision": 1})
    else:
        response = s.create({"name": "x", "type": "concept", "definition": "d", "sources": [{"chunk_id": chunk_id}]})

    assert response.status_code == 409
    assert response.json() == {"code": "COURSE_BUSY", "message": response.json()["message"],
                               "details": {"holder": "publish"}}
    assert s.store.writes == [] and s.draft_revision() == before
    assert s.locks() == [(s.course.id, "publish")]  # the holder's lock is untouched


def test_expired_foreign_lock_does_not_block(s):
    s.store.nodes["a"] = kp("a")
    with connect(s.url) as db:
        db.execute("INSERT INTO course_locks (course_id, holder, token, expires_at) VALUES (?, 'persisting-w1', ?, "
                   "unixepoch() - 5)", (s.course.id, "t" * 32))
    assert s.patch("a", {"expected_revision": 1, "name": "x"}).status_code == 200
    assert s.locks() == []


def test_edit_holds_the_lock_as_edit_while_writing(s):
    s.store.nodes["a"] = kp("a")
    seen = []
    original = s.store.update

    def spy(*args, **kwargs):
        seen.extend(s.locks())
        return original(*args, **kwargs)

    s.store.update = spy
    assert s.patch("a", {"expected_revision": 1, "name": "x"}).status_code == 200
    assert seen == [(s.course.id, "edit")] and s.locks() == []


def test_neo4j_unavailable_is_503_and_releases_the_lock(s):
    s.store.nodes["a"] = kp("a")
    s.store.fail = True
    response = s.patch("a", {"expected_revision": 1, "name": "x"})
    assert response.status_code == 503 and response.json()["code"] == "STORAGE_UNAVAILABLE"
    assert s.locks() == []


# --- unlock -------------------------------------------------------------------------------


def test_unlock_is_explicit_and_bumps_revision(s):
    s.store.nodes["a"] = kp("a")
    assert s.patch("a", {"expected_revision": 1, "name": "栈"}).json()["locked"] is True
    before = s.draft_revision()

    response = s.unlock("a", {"expected_revision": 2})

    assert response.status_code == 200
    body = response.json()
    assert_schema("KnowledgePoint", body)
    assert body["locked"] is False and body["revision"] == 3 and body["name"] == "栈"
    assert s.store.nodes["a"]["contrib_manual"] is True  # never falls back (§8.4)
    assert s.draft_revision() == before + 1 and s.locks() == []


def test_unlock_with_stale_revision_is_conflict_and_node_stays_locked(s):
    s.store.nodes["a"] = kp("a", locked=True, revision=5)
    response = s.unlock("a", {"expected_revision": 4})
    assert response.status_code == 409 and response.json()["code"] == "REVISION_CONFLICT"
    assert response.json()["details"]["current_revision"] == 5
    assert s.store.nodes["a"]["locked"] is True and s.store.writes == []


def test_unlocking_an_unlocked_node_is_a_no_op(s):
    s.store.nodes["a"] = kp("a", locked=False, revision=2)
    before = s.draft_revision()
    body = s.unlock("a", {"expected_revision": 2}).json()
    assert body["locked"] is False and body["revision"] == 2
    assert s.store.writes == [] and s.draft_revision() == before


@pytest.mark.parametrize("body", [{}, {"expected_revision": 0}, {"expected_revision": 1, "locked": False}])
def test_unlock_body_is_validated(s, body):
    s.store.nodes["a"] = kp("a", locked=True)
    response = s.unlock("a", body)
    assert response.status_code == 422 and response.json()["code"] == "VALIDATION_ERROR"
    assert s.store.nodes["a"]["locked"] is True


def test_unlock_missing_node_is_404(s):
    assert s.unlock("nope", {"expected_revision": 1}).status_code == 404


# --- create: manual node must carry a source -----------------------------------------------


def _create_body(chunk_id, **extra):
    body = {"name": "双端队列", "type": "concept", "definition": "两端都能进出的队列",
            "sources": [{"chunk_id": chunk_id}]}
    body.update(extra)
    return body


def test_create_manual_node_with_whole_chunk_source(s):
    chunk_id = s.chunk("t-done")
    before = s.draft_revision()

    response = s.create(_create_body(chunk_id, aliases=["deque"], importance=0.7))

    assert response.status_code == 201, response.text
    body = response.json()
    assert_schema("KnowledgePoint", body)
    assert body["source"] == "manual" and body["locked"] is True and body["revision"] == 1
    assert body["status"] == "approved" and body["confidence"] == 1.0 and body["level"] == 0
    assert body["name"] == "双端队列" and body["aliases"] == ["deque"] and body["importance"] == 0.7
    assert body["id"].startswith("kp_") and body["course_id"] == s.course.id
    [(kp_id, source)] = s.store.evidence
    assert kp_id == body["id"]
    assert source["chunk_id"] == chunk_id and source["document_id"] == "doc1"
    assert (source["evidence_start"], source["evidence_end"]) == (0, len(CHUNK_TEXT))
    assert s.draft_revision() == before + 1 and s.locks() == []


def test_create_with_evidence_span_and_duplicate_sources(s):
    chunk_id = s.chunk("t-done")
    src = {"chunk_id": chunk_id, "evidence_start": 0, "evidence_end": 1}
    assert s.create(_create_body(chunk_id, sources=[src, dict(src)])).status_code == 201
    assert [e[1]["evidence_end"] for e in s.store.evidence] == [1]


def test_created_node_can_be_edited_with_revision_one(s):
    chunk_id = s.chunk("t-done")
    created = s.create(_create_body(chunk_id)).json()
    edited = s.patch(created["id"], {"expected_revision": 1, "definition": "改"}).json()
    assert edited["revision"] == 2 and edited["locked"] is True


def test_create_without_sources_is_rejected(s):
    for body in ({"name": "x", "type": "concept", "definition": "d"},
                 {"name": "x", "type": "concept", "definition": "d", "sources": []}):
        response = s.create(body)
        assert response.status_code == 422
        assert response.json()["details"]["fields"][0]["field"] == "sources"
    assert s.store.writes == []


def test_create_source_must_be_a_committed_chunk_of_this_course(s):
    other = create_course(s.url, name="他课", description=None, creator_id=s.teacher.id)
    s.task("t-other", "completed", course_id=other.id, doc="doc-other")
    foreign = s.chunk("t-other", course_id=other.id, doc="doc-other")
    s.task("t-failed", "failed", doc="doc2")
    uncommitted = s.chunk("t-failed", doc="doc2")
    before = s.draft_revision()

    response = s.create(_create_body(foreign, sources=[{"chunk_id": foreign}, {"chunk_id": uncommitted},
                                                       {"chunk_id": "no-such-chunk"}]))

    assert response.status_code == 422
    fields = response.json()["details"]["fields"]
    assert fields == [{"in": "body", "field": f"sources.{i}.chunk_id", "reason": "source_not_available"}
                      for i in range(3)]
    assert s.store.writes == [] and s.draft_revision() == before and s.locks() == []


@pytest.mark.parametrize("span, field, reason", [
    ({"evidence_start": 0, "evidence_end": 999}, "sources.0.evidence_end", "evidence_out_of_range"),
    ({"evidence_start": 3, "evidence_end": 3}, "sources.0.evidence_end", "evidence_out_of_range"),
    ({"evidence_start": 2}, "sources.0.evidence_end", "missing"),
    ({"evidence_end": 2}, "sources.0.evidence_start", "missing"),
    ({"evidence_start": None, "evidence_end": 2}, "sources.0.evidence_start", "null_forbidden"),
    ({"evidence_start": -1, "evidence_end": 2}, "sources.0.evidence_start", "greater_than_equal"),
    ({"page": 3}, "sources.0.page", "extra_forbidden"),
])
def test_create_evidence_span_is_validated(s, span, field, reason):
    chunk_id = s.chunk("t-done")
    response = s.create(_create_body(chunk_id, sources=[{"chunk_id": chunk_id, **span}]))
    assert response.status_code == 422
    assert {"in": "body", "field": field, "reason": reason} in response.json()["details"]["fields"]
    assert s.store.writes == []


@pytest.mark.parametrize("extra, field, reason", [
    ({"name": "  "}, "name", "blank"),
    ({"definition": " "}, "definition", "blank"),
    ({"aliases": [""]}, "aliases.0", "blank"),
    ({"chapter_id": None}, "chapter_id", "null_forbidden"),
    ({"chapter_id": "ch-missing"}, "chapter_id", "not_found"),
])
def test_create_fields_are_validated(s, extra, field, reason):
    chunk_id = s.chunk("t-done")
    response = s.create(_create_body(chunk_id, **extra))
    assert response.status_code == 422
    assert {"in": "body", "field": field, "reason": reason} in response.json()["details"]["fields"]
    assert s.store.writes == []


def test_create_in_an_existing_chapter(s):
    s.store.chapters.add("ch-2")
    chunk_id = s.chunk("t-done")
    body = s.create(_create_body(chunk_id, chapter_id="ch-2")).json()
    assert body["chapter_id"] == "ch-2"


# --- contract registration ----------------------------------------------------------------


def test_routes_are_registered_with_contract_operation_ids(s):
    paths = s.client.app.openapi()["paths"]
    assert paths["/api/v1/courses/{cid}/kp"]["post"]["operationId"] == "createKnowledgePoint"
    assert paths["/api/v1/courses/{cid}/kp/{kid}"]["patch"]["operationId"] == "updateKnowledgePoint"
    assert paths["/api/v1/courses/{cid}/kp/{kid}/unlock"]["post"]["operationId"] == "unlockKnowledgePoint"
    contract = _SPEC["paths"]
    assert contract["/api/v1/courses/{cid}/kp/{kid}/unlock"]["post"]["operationId"] == "unlockKnowledgePoint"
    assert "sources" in _SPEC["components"]["schemas"]["KnowledgePointCreate"]["required"]
    assert "REVISION_CONFLICT" in _SPEC["components"]["schemas"]["ErrorCode"]["enum"]
