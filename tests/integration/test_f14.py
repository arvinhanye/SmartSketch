"""F14 offline re-vectorisation command (specs/teacher-review-publish.md V12, PUB-39).

Acceptance: runs only while stopped (no live lease, course lock or publish attempt); enumerates
all chunks, all draft knowledge points and every committed version copy from the Neo4j stock;
any failure before the SQLite commit keeps the old space; verifies dimensions, counts and
versions and prints rollback steps.

The in-memory graph below understands exactly the Cypher shapes the command and the F03 writer
send, so every path runs without Docker. ``test_live_*`` repeat the main paths on a real,
disposable Neo4j 5.26 (``SMARTSKETCH_F14_URI/USER/PASSWORD``; the database is wiped).
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import sqlite3
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.repositories.accounts import insert_account
from app.repositories.courses import create_course
from app.repositories.graph_migrations import GraphVectorWriter, VectorSpaceError, sqlite_current_space, vector_property
from app.repositories.sqlite import connect, migrate
from app.services.ai.client import ModelServerError
from app.services.ai.embeddings import EmbeddedVector
from app.services.ai.fake import FakeEmbeddingClient

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("reembed", ROOT / "scripts" / "reembed.py")
reembed = importlib.util.module_from_spec(_spec)
sys.modules["reembed"] = reembed
_spec.loader.exec_module(reembed)

OLD, NEW = "fake/4", "real/next-embed/4"
OLD_PROP, NEW_PROP = vector_property(OLD), vector_property(NEW)
VALID_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA"


def sha(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()


def settings(space: str = NEW, batch: int = 3):
    if space.startswith("fake/"):
        return SimpleNamespace(EMBEDDING_MODE="fake", EMBEDDING_MODEL="", EMBEDDING_DIMENSIONS=int(space[5:]),
                               EMBEDDING_BATCH_SIZE=batch)
    _, model, dims = space.split("/")
    return SimpleNamespace(EMBEDDING_MODE="online", EMBEDDING_MODEL=model, EMBEDDING_DIMENSIONS=int(dims),
                           EMBEDDING_BATCH_SIZE=batch)


def old_vector(seed: int = 1):
    return [float(seed), 0.0, 0.0, 0.0]


# ---------------------------------------------------------------- in-memory graph


class FakeGraph:
    """Nodes are dicts with ``labels``; queries are matched by the shapes the command uses."""

    def __init__(self):
        self.nodes: list[dict] = []
        self.indexes: dict[str, tuple[str, str]] = {}
        self.calls: list[str] = []
        self.fail: dict[str, Exception] = {}
        self.before_query = None

    def add(self, label, **props):
        self.nodes.append({"labels": {label}, **props})

    def kp(self, course, version, kp_id):
        return next(n for n in self.nodes if "KnowledgePoint" in n["labels"] and n["course_id"] == course
                    and n["version_id"] == version and n["kp_id"] == kp_id)

    def chunk(self, course, chunk_id):
        return next(n for n in self.nodes if "Chunk" in n["labels"] and n["course_id"] == course
                    and n["chunk_id"] == chunk_id)

    def execute_query(self, query, *, parameters_, routing_, database_):
        self.calls.append(query)
        for marker, exc in self.fail.items():
            if marker in query:
                raise exc
        if self.before_query is not None:
            self.before_query(query)
        return self._run(query, parameters_)

    def _run(self, q, p):
        rec = lambda rows: SimpleNamespace(records=rows)  # noqa: E731
        m = re.match(r"CREATE VECTOR INDEX (\w+) IF NOT EXISTS FOR \(n:(\w+)\) ON \(n\.(\w+)\)", q)
        if m:
            self.indexes.setdefault(m.group(1), (m.group(2), m.group(3)))
            return rec([])
        if q.startswith("SHOW INDEXES"):
            return rec([{"name": name} for name in self.indexes])
        m = re.match(r"DROP INDEX (\w+) IF EXISTS", q)
        if m:
            self.indexes.pop(m.group(1), None)
            return rec([])
        m = re.match(r"MATCH \(n:(\w+) \{(.*?)\}\) SET n\.(\w+) = \$values RETURN count\(n\) AS matched", q)
        if m:  # F03 writer
            label, prop = m.group(1), m.group(3)
            keys = {"KnowledgePoint": ("course_id", "version_id", "kp_id"), "Chunk": ("course_id", "chunk_id")}[label]
            params = [p["course_id"], p["version_id"], p["entity_id"]] if label == "KnowledgePoint" \
                else [p["course_id"], p["entity_id"]]
            hits = [n for n in self.nodes if label in n["labels"] and [n.get(k) for k in keys] == params]
            for n in hits:
                n[prop] = list(p["values"])
            return rec([{"matched": len(hits)}])
        m = re.match(r"MATCH \(n:(\w+)\) RETURN n\.course_id AS course_id", q)
        if m:  # inventory
            label, prop, dims = m.group(1), p["prop"], p["dims"]
            rows = []
            for n in self.nodes:
                if label not in n["labels"]:
                    continue
                vec = n.get(prop)
                row = {"course_id": n.get("course_id"), "ok": vec is not None and len(vec) == dims}
                if label == "Chunk":
                    row["id"] = n.get("chunk_id")
                else:
                    row.update(id=n.get("kp_id"), version_id=n.get("version_id"), name=n.get("name"),
                               definition=n.get("definition"))
                rows.append(row)
            return rec(rows)
        if "UNWIND keys(n) AS key" in q:
            keys = sorted({k for n in self.nodes if n["labels"] & {"Chunk", "KnowledgePoint"} for k in n
                           if isinstance(k, str) and k.startswith("embedding_")})
            return rec([{"key": k} for k in keys])
        m = re.match(r"MATCH \(n:(\w+)\) WHERE n\.(\w+) IS NOT NULL WITH n LIMIT \$limit REMOVE n\.\w+ RETURN count\(n\) AS removed", q)
        if m:
            label, prop = m.groups()
            hits = [n for n in self.nodes if label in n["labels"] and n.get(prop) is not None][: p["limit"]]
            for n in hits:
                del n[prop]
            return rec([{"removed": len(hits)}])
        raise AssertionError(f"unexpected query: {q}")


# ---------------------------------------------------------------- SQLite fixture


@pytest.fixture
def db(tmp_path):
    url = f"sqlite:///{(tmp_path / 'state.sqlite3').as_posix()}"
    migrate(url)
    teacher = insert_account(url, account_id=uuid.uuid4().hex, username="teacher1", password_hash=VALID_HASH,
                             role="teacher").id
    courses = [create_course(url, name=name, description=None, creator_id=teacher).id for name in ("甲", "乙")]
    with connect(url) as d:
        d.execute("INSERT INTO embedding_space_state (singleton, model, dimensions, is_fake) VALUES (1, '', 4, 1)")
    return SimpleNamespace(url=url, courses=courses, teacher=teacher, path=tmp_path / "state.sqlite3")


def sql(url, query, *params):
    with connect(url) as d:
        return d.execute(query, params).fetchall()


def add_chunk_row(url, course, ordinal, text):
    material = f"m-{course[:6]}"
    rev = "rev_" + hashlib.sha256(course.encode()).hexdigest()
    if not sql(url, "SELECT 1 FROM materials WHERE id = ?", material):
        sql(url, "INSERT INTO materials (id, course_id, filename, format, size_bytes, content_hash, storage_name) "
                 "VALUES (?, ?, 'a.txt', 'txt', 10, ?, ?)", material, course, sha(material), uuid.uuid4().hex)
        sql(url, "INSERT INTO material_revisions (revision_id, course_id, material_id, content_hash, parser_version) "
                 "VALUES (?, ?, ?, ?, 'txt/1+chunk/1')", rev, course, material, sha(material))
    chunk_id = f"{rev}-{ordinal}"
    sql(url, "INSERT INTO chunks (chunk_id, revision_id, course_id, material_id, ordinal, text, text_sha256, "
             "section_titles, sources) VALUES (?, ?, ?, ?, ?, ?, ?, '[]', ?)",
        chunk_id, rev, course, material, ordinal, text, sha(text),
        json.dumps([{"block_ordinal": 0, "start": 0, "end": 1, "locator": {"section_titles": [], "paragraph": 1}}]))
    return chunk_id


def add_version(url, course, *, state="committed", version=1, nodes=1, space=OLD, seq=None):
    version_id = uuid.uuid4().hex[:26].upper()
    committed = state == "committed"
    snapshot = json.dumps({"course_id": course}) if state != "preparing" else None
    sql(url, "INSERT INTO graph_versions (version_id, course_id, version, kind, state, expires_at, snapshot_json, "
             "digest, node_count, edge_count, excluded, embedding_space, failure_reason, commit_seq, committed_at) "
             "VALUES (?, ?, ?, 'publish', ?, unixepoch() + 600, ?, ?, ?, 0, '[]', ?, ?, ?, ?)",
        version_id, course, version if committed else None, state, snapshot,
        sha(version_id) if snapshot else None, nodes if snapshot else None, space if snapshot else None,
        "失败" if state == "failed" else None, (seq or version) if committed else None,
        "2026-09-26T00:00:00Z" if committed else None)
    return version_id


def build_stock(db, graph):
    """Two courses: chunks (one shared text across courses), draft KPs of every status, two
    committed versions, and the orphan copy of a failed attempt."""
    a, b = db.courses
    stock = SimpleNamespace(chunks=[], drafts=[], committed=[], versions=[])
    for course, texts in ((a, ("栈是后进先出", "队列先进先出")), (b, ("栈是后进先出",))):
        for ordinal, text in enumerate(texts):
            chunk_id = add_chunk_row(db.url, course, ordinal, text)
            graph.add("Chunk", course_id=course, chunk_id=chunk_id, **{OLD_PROP: old_vector()})
            stock.chunks.append((course, chunk_id))
    for course, kp, status in ((a, "stack", "approved"), (a, "queue", "rejected"), (a, "heap", "low_confidence"),
                               (b, "stack", "draft")):
        graph.add("KnowledgePoint", course_id=course, version_id="draft", kp_id=kp, name=kp, definition=f"{kp}定义",
                  status=status, **{OLD_PROP: old_vector(2)})
        stock.drafts.append((course, "draft", kp))
    for course, number in ((a, 1), (a, 2)):
        vid = add_version(db.url, course, version=number, nodes=1, seq=number)
        graph.add("KnowledgePoint", course_id=course, version_id=vid, kp_id="stack", name="stack",
                  definition="stack定义", **{OLD_PROP: old_vector(3)})
        stock.committed.append((course, vid, "stack"))
        stock.versions.append(vid)
    failed = add_version(db.url, b, state="failed", nodes=1)
    graph.add("KnowledgePoint", course_id=b, version_id=failed, kp_id="orphan", name="orphan", definition="x",
              **{OLD_PROP: old_vector(4)})
    stock.failed = failed
    for name, label in ((f"chunk_embedding_{OLD_PROP[10:]}", "Chunk"), (f"kp_embedding_{OLD_PROP[10:]}", "KnowledgePoint")):
        graph.indexes[name] = (label, OLD_PROP)
    return stock


def run(db, graph, client=None, *, space=NEW, confirmed=True, **kwargs):
    return reembed.run(sqlite_url=db.url, driver=graph, settings=settings(space), client=client or FakeEmbeddingClient(),
                       neo4j_backup_confirmed=confirmed, **kwargs)


def recorded(db):
    return sqlite_current_space(db.url)()


def all_vector_nodes(graph):
    return [n for n in graph.nodes if n["labels"] & {"Chunk", "KnowledgePoint"}]


# ---------------------------------------------------------------- happy path


def test_switch_embeds_full_stock_commits_and_removes_old_space(db):
    graph = FakeGraph()
    stock = build_stock(db, graph)
    client = FakeEmbeddingClient()
    report = run(db, graph, client)

    assert report.action == "switched" and (report.source_space, report.target_space) == (OLD, NEW)
    assert (report.chunks, report.draft_kps, report.committed_kps, report.versions) == (3, 4, 2, 2)
    assert report.orphans == 1
    # Chunk text "栈是后进先出" appears in both courses, "stack\nstack定义" in a draft and two copies.
    texts = [t for call in client.calls for t in call.request.texts]
    assert len(texts) == len(set(texts)) == report.embedded_texts
    assert all(call.request.model == "next-embed" and call.request.dimensions == 4 for call in client.calls)

    for course, chunk_id in stock.chunks:
        node = graph.chunk(course, chunk_id)
        assert len(node[NEW_PROP]) == 4 and OLD_PROP not in node
    for course, version, kp in stock.drafts + stock.committed:
        node = graph.kp(course, version, kp)
        assert len(node[NEW_PROP]) == 4 and OLD_PROP not in node
    assert not any(OLD_PROP in n for n in all_vector_nodes(graph))
    suffix = NEW_PROP[10:]
    assert set(graph.indexes) == {f"chunk_embedding_{suffix}", f"kp_embedding_{suffix}"}

    assert recorded(db) == NEW
    assert sql(db.url, "SELECT model, dimensions, is_fake FROM embedding_space_state") == [("next-embed", 4, 0)]
    spaces = dict(sql(db.url, "SELECT version_id, embedding_space FROM graph_versions"))
    assert all(spaces[v] == NEW for v in stock.versions)
    assert spaces[stock.failed] == OLD  # non-committed rows are not versions

    calls = sql(db.url, "SELECT course_id, purpose, status, task_id FROM model_calls")
    assert calls and {c[1:] for c in calls} == {("embedding", "ok", None)}
    assert {c[0] for c in calls} <= set(db.courses)

    assert report.backup is not None and report.backup.exists()
    with sqlite3.connect(report.backup) as copy:
        assert copy.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert copy.execute("SELECT is_fake FROM embedding_space_state").fetchone() == (1,)
    assert report.cleanup_error is None


def test_same_text_is_embedded_once_across_nodes_and_courses(db):
    graph = FakeGraph()
    build_stock(db, graph)
    client = FakeEmbeddingClient()
    run(db, graph, client)
    texts = [t for call in client.calls for t in call.request.texts]
    assert texts.count("栈是后进先出") == 1
    assert texts.count("stack\nstack定义") == 1


def test_draft_vectors_follow_current_text_and_are_distinct_per_text(db):
    graph = FakeGraph()
    stock = build_stock(db, graph)
    run(db, graph)
    a = db.courses[0]
    stack = graph.kp(a, "draft", "stack")[NEW_PROP]
    queue = graph.kp(a, "draft", "queue")[NEW_PROP]
    copy = graph.kp(*stock.committed[0])[NEW_PROP]
    assert stack == copy and stack != queue


def test_runtime_writer_uses_new_space_after_switch_and_old_context_is_dead(db):
    graph = FakeGraph()
    build_stock(db, graph)
    run(db, graph)
    writer = GraphVectorWriter(graph, sqlite_current_space(db.url))
    a = db.courses[0]
    writer.write_runtime("KnowledgePoint", a, "draft", "stack", EmbeddedVector((1.0,) * 4, "next-embed", 4, NEW, "h"))
    with pytest.raises(VectorSpaceError):
        writer.write_runtime("KnowledgePoint", a, "draft", "stack", EmbeddedVector((1.0,) * 4, "fake", 4, OLD, "h"))


# ---------------------------------------------------------------- preconditions (stopped system)


def _untouched(db, graph, before_nodes):
    assert recorded(db) == OLD
    assert graph.nodes == before_nodes
    assert not any(NEW_PROP in n for n in graph.nodes)


@pytest.mark.parametrize("blocker", ["lease", "course_lock", "preparing", "materialized", "expired_attempt"])
def test_refuses_while_system_is_not_stopped(db, blocker):
    graph = FakeGraph()
    build_stock(db, graph)
    a = db.courses[0]
    if blocker == "lease":
        sql(db.url, "INSERT INTO processing_tasks (id, course_id, document_id, stage, progress, idempotency_key, "
                    "lease_owner, lease_token, lease_expires_at) VALUES ('t1', ?, ?, 'parsing', 0.1, 'k', 'w', ?, "
                    "unixepoch() + 60)", a, f"m-{a[:6]}", "f" * 32)
    elif blocker == "course_lock":
        sql(db.url, "INSERT INTO course_locks (course_id, holder, token, expires_at) VALUES (?, 'u', ?, unixepoch() + 60)",
            a, "e" * 32)
    elif blocker == "expired_attempt":
        vid = add_version(db.url, a, state="preparing")
        sql(db.url, "UPDATE graph_versions SET expires_at = unixepoch() - 600 WHERE version_id = ?", vid)
    else:
        vid = add_version(db.url, a, state="preparing")
        if blocker == "materialized":
            sql(db.url, "UPDATE graph_versions SET state = 'materialized', snapshot_json = '{}', digest = ?, "
                        "node_count = 0, embedding_space = ? WHERE version_id = ?", sha("x"), OLD, vid)
    before = [dict(n) for n in graph.nodes]
    client = FakeEmbeddingClient()
    with pytest.raises(reembed.OfflineCheckError):
        run(db, graph, client)
    _untouched(db, graph, before)
    assert client.calls == ()
    assert not list(db.path.parent.glob("backups/*-before-reembed.sqlite"))


def test_expired_lease_and_lock_do_not_block(db):
    graph = FakeGraph()
    build_stock(db, graph)
    a = db.courses[0]
    sql(db.url, "INSERT INTO processing_tasks (id, course_id, document_id, stage, progress, idempotency_key, "
                "lease_owner, lease_token, lease_expires_at) VALUES ('t1', ?, ?, 'parsing', 0.1, 'k', 'w', ?, "
                "unixepoch() - 60)", a, f"m-{a[:6]}", "f" * 32)
    sql(db.url, "INSERT INTO course_locks (course_id, holder, token, expires_at) VALUES (?, 'u', ?, unixepoch() - 60)",
        a, "e" * 32)
    assert run(db, graph).action == "switched"


def test_requires_neo4j_backup_confirmation(db):
    graph = FakeGraph()
    build_stock(db, graph)
    before = [dict(n) for n in graph.nodes]
    with pytest.raises(reembed.OfflineCheckError, match="Neo4j"):
        run(db, graph, confirmed=False)
    _untouched(db, graph, before)


def test_committed_version_in_another_space_is_an_invariant_breach(db):
    graph = FakeGraph()
    build_stock(db, graph)
    add_version(db.url, db.courses[1], version=1, nodes=0, space="fake/8", seq=9)
    before = [dict(n) for n in graph.nodes]
    with pytest.raises(reembed.ReembedError, match="embedding_space"):
        run(db, graph)
    _untouched(db, graph, before)


def test_uninitialised_space_is_refused(db):
    sql(db.url, "DELETE FROM embedding_space_state")
    with pytest.raises(reembed.ReembedError):
        run(db, FakeGraph())


# ---------------------------------------------------------------- failure keeps the old space


def test_model_failure_keeps_old_space_and_rerun_reuses_immutable_vectors(db):
    graph = FakeGraph()
    stock = build_stock(db, graph)
    # The first batch succeeds, the second fails.
    failing = FakeEmbeddingClient()
    calls = {"n": 0}
    real_embed = failing.embed

    def flaky(request):
        calls["n"] += 1
        if calls["n"] == 2:
            raise ModelServerError("next-embed", status_code=503)
        return real_embed(request)

    failing.embed = flaky
    with pytest.raises(reembed.ReembedError):
        run(db, graph, failing)
    assert recorded(db) == OLD
    assert sql(db.url, "SELECT DISTINCT embedding_space FROM graph_versions WHERE state = 'committed'") == [(OLD,)]
    assert all(len(n[OLD_PROP]) == 4 for n in all_vector_nodes(graph))
    assert f"kp_embedding_{OLD_PROP[10:]}" in graph.indexes
    assert sql(db.url, "SELECT status FROM model_calls ORDER BY created_at") [-1] == ("error",)
    written = [n for n in all_vector_nodes(graph) if NEW_PROP in n]
    assert written  # partial progress stays in the new property only

    # Re-run: chunks and committed copies that already hold a valid new vector are reused;
    # draft knowledge points are always recomputed (their text may have changed since).
    client = FakeEmbeddingClient()
    report = run(db, graph, client)
    assert report.action == "switched" and recorded(db) == NEW
    reusable = [n for n in written if n.get("version_id") != "draft"]
    assert report.reused == len(reusable)
    assert all(len(n[NEW_PROP]) == 4 for course, version, kp in stock.drafts for n in [graph.kp(course, version, kp)])


def test_changed_draft_definition_is_not_served_from_a_stale_new_vector(db):
    graph = FakeGraph()
    build_stock(db, graph)
    a = db.courses[0]
    node = graph.kp(a, "draft", "stack")
    node[NEW_PROP] = [9.0, 9.0, 9.0, 9.0]  # left over by an interrupted earlier run
    run(db, graph)
    assert node[NEW_PROP] != [9.0, 9.0, 9.0, 9.0]


def test_wrong_dimension_leftover_is_recomputed(db):
    graph = FakeGraph()
    stock = build_stock(db, graph)
    node = graph.chunk(*stock.chunks[0])
    node[NEW_PROP] = [1.0, 2.0]
    report = run(db, graph)
    assert len(node[NEW_PROP]) == 4 and report.reused == 0


def test_committed_copy_count_mismatch_fails_before_any_model_call(db):
    graph = FakeGraph()
    stock = build_stock(db, graph)
    sql(db.url, "DROP TRIGGER graph_versions_committed_frozen")
    sql(db.url, "UPDATE graph_versions SET node_count = 2 WHERE version_id = ?", stock.versions[0])
    client = FakeEmbeddingClient()
    with pytest.raises(reembed.VerificationFailed, match="version"):
        run(db, graph, client)
    assert client.calls == () and recorded(db) == OLD


def test_missing_committed_copy_fails(db):
    graph = FakeGraph()
    stock = build_stock(db, graph)
    graph.nodes.remove(graph.kp(*stock.committed[1]))
    with pytest.raises(reembed.VerificationFailed):
        run(db, graph)
    assert recorded(db) == OLD


def test_chunk_without_stored_text_fails(db):
    graph = FakeGraph()
    build_stock(db, graph)
    graph.add("Chunk", course_id=db.courses[0], chunk_id="ghost", **{OLD_PROP: old_vector()})
    with pytest.raises(reembed.VerificationFailed, match="chunk"):
        run(db, graph)
    assert recorded(db) == OLD


def test_stock_growing_during_run_fails_verification(db):
    graph = FakeGraph()
    build_stock(db, graph)
    state = {"done": False}

    def sneak(query):
        if not state["done"] and "SET n." in query:
            state["done"] = True
            graph.add("KnowledgePoint", course_id=db.courses[0], version_id="draft", kp_id="late", name="late",
                      definition="d", **{OLD_PROP: old_vector()})

    graph.before_query = sneak
    with pytest.raises(reembed.VerificationFailed, match="count"):
        run(db, graph)
    assert recorded(db) == OLD
    assert all(OLD_PROP in n for n in all_vector_nodes(graph))


def test_vector_missing_at_verification_fails(db):
    graph = FakeGraph()
    stock = build_stock(db, graph)
    victim = graph.chunk(*stock.chunks[1])
    state = {"writes": 0}

    def erase(query):
        if "SET n." in query:
            state["writes"] += 1
        if query.startswith("MATCH (n:Chunk) RETURN") and state["writes"]:
            victim.pop(NEW_PROP, None)

    graph.before_query = erase
    with pytest.raises(reembed.VerificationFailed, match="missing"):
        run(db, graph)
    assert recorded(db) == OLD


def test_space_changed_by_someone_else_before_commit_is_refused(db):
    graph = FakeGraph()
    build_stock(db, graph)
    state = {"done": False}

    def tamper(query):
        if not state["done"] and query.startswith("MATCH (n:KnowledgePoint) RETURN") and graph.calls.count(query) == 2:
            state["done"] = True
            sql(db.url, "UPDATE embedding_space_state SET model = 'other', is_fake = 0")

    graph.before_query = tamper
    with pytest.raises(reembed.ReembedError):
        run(db, graph)
    assert recorded(db) == "real/other/4"


# ---------------------------------------------------------------- step 6 and re-runs


def test_cleanup_failure_after_commit_is_reported_and_rerun_finishes_it(db):
    graph = FakeGraph()
    build_stock(db, graph)
    graph.fail["DROP INDEX"] = RuntimeError("driver detail")
    report = run(db, graph)
    assert report.action == "switched" and recorded(db) == NEW
    assert report.cleanup_error and "driver detail" not in report.cleanup_error
    assert any(OLD_PROP in n for n in all_vector_nodes(graph))

    graph.fail.clear()
    client = FakeEmbeddingClient()
    again = run(db, graph, client)
    assert again.action == "cleanup" and client.calls == ()
    assert not any(OLD_PROP in n for n in all_vector_nodes(graph))
    assert all(name.endswith(NEW_PROP[10:]) for name in graph.indexes)


def test_rerun_with_recorded_space_removes_partial_foreign_space(db):
    """Rollback before commit: rerunning with the old configuration clears the half-written new space."""
    graph = FakeGraph()
    build_stock(db, graph)
    graph.kp(db.courses[0], "draft", "stack")[NEW_PROP] = [1.0] * 4
    graph.indexes[f"kp_embedding_{NEW_PROP[10:]}"] = ("KnowledgePoint", NEW_PROP)
    client = FakeEmbeddingClient()
    report = run(db, graph, client, space=OLD)
    assert report.action == "cleanup" and client.calls == () and recorded(db) == OLD
    assert not any(NEW_PROP in n for n in all_vector_nodes(graph))
    assert all(len(n[OLD_PROP]) == 4 for n in all_vector_nodes(graph))
    assert set(graph.indexes) == {f"chunk_embedding_{OLD_PROP[10:]}", f"kp_embedding_{OLD_PROP[10:]}"}


def test_cleanup_mode_still_requires_stopped_system(db):
    graph = FakeGraph()
    build_stock(db, graph)
    sql(db.url, "INSERT INTO course_locks (course_id, holder, token, expires_at) VALUES (?, 'u', ?, unixepoch() + 60)",
        db.courses[0], "e" * 32)
    with pytest.raises(reembed.OfflineCheckError):
        run(db, graph, space=OLD)


def test_empty_stock_switches(db):
    report = run(db, FakeGraph())
    assert report.action == "switched" and report.embedded_texts == 0 and recorded(db) == NEW


# ---------------------------------------------------------------- CLI


def test_main_prints_report_and_rollback_steps(db, capsys, monkeypatch):
    graph = FakeGraph()
    build_stock(db, graph)
    cfg = SimpleNamespace(SQLITE_URL=db.url, NEO4J_URI="bolt://x", NEO4J_USER="neo4j",
                          NEO4J_PASSWORD=SimpleNamespace(get_secret_value=lambda: "SECRET-PW"), **vars(settings()))
    code = reembed.main(["--neo4j-backup-confirmed"], settings=cfg, driver=graph, client=FakeEmbeddingClient())
    out = capsys.readouterr()
    assert code == 0 and recorded(db) == NEW
    assert NEW in out.out and "回滚" in out.out and "SECRET-PW" not in out.out + out.err


def test_main_without_confirmation_exits_nonzero_with_guidance(db, capsys):
    cfg = SimpleNamespace(SQLITE_URL=db.url, NEO4J_URI="bolt://x", NEO4J_USER="neo4j",
                          NEO4J_PASSWORD=SimpleNamespace(get_secret_value=lambda: "SECRET-PW"), **vars(settings()))
    code = reembed.main([], settings=cfg, driver=FakeGraph(), client=FakeEmbeddingClient())
    err = capsys.readouterr().err
    assert code == 2 and "--neo4j-backup-confirmed" in err and recorded(db) == OLD


def test_main_reports_cleanup_failure_with_distinct_exit_code(db, capsys):
    graph = FakeGraph()
    build_stock(db, graph)
    graph.fail["DROP INDEX"] = RuntimeError("x")
    cfg = SimpleNamespace(SQLITE_URL=db.url, NEO4J_URI="bolt://x", NEO4J_USER="neo4j",
                          NEO4J_PASSWORD=SimpleNamespace(get_secret_value=lambda: "p"), **vars(settings()))
    assert reembed.main(["--neo4j-backup-confirmed"], settings=cfg, driver=graph, client=FakeEmbeddingClient()) == 3
    assert recorded(db) == NEW


def test_rollback_steps_cover_both_sides_of_the_commit_point():
    text = reembed.ROLLBACK_STEPS
    assert "第 5 步" in text and "备份" in text and "旧配置" in text


# ---------------------------------------------------------------- real Neo4j

_LIVE = ("SMARTSKETCH_F14_URI", "SMARTSKETCH_F14_USER", "SMARTSKETCH_F14_PASSWORD")
live = pytest.mark.skipif(not all(os.environ.get(n) for n in _LIVE),
                          reason="disposable Neo4j fixture not configured (database is wiped)")


@pytest.fixture
def neo(db):
    neo4j = pytest.importorskip("neo4j")
    driver = neo4j.GraphDatabase.driver(os.environ[_LIVE[0]], auth=(os.environ[_LIVE[1]], os.environ[_LIVE[2]]))

    def q(query, **params):
        return [dict(r) for r in driver.execute_query(query, parameters_=params, routing_="w", database_="neo4j").records]

    q("MATCH (n) DETACH DELETE n")
    for row in q("SHOW INDEXES YIELD name, type WHERE type = 'VECTOR' RETURN name"):
        q(f"DROP INDEX {row['name']} IF EXISTS")
    from app.repositories.graph_migrations import apply_migrations
    apply_migrations(driver)
    # Mirror build_stock on the real database.
    shadow = FakeGraph()
    stock = build_stock(db, shadow)
    writer = GraphVectorWriter(driver, lambda: OLD)
    writer.ensure_vector_indexes(OLD)
    for n in shadow.nodes:
        label = next(iter(n["labels"]))
        props = {k: v for k, v in n.items() if k != "labels"}
        q(f"CREATE (x:{label}) SET x = $p", p=props)
    yield SimpleNamespace(driver=driver, q=q, stock=stock)
    driver.close()


@live
def test_live_switch_on_real_neo4j(db, neo):
    report = run(db, neo.driver)
    assert report.action == "switched" and report.cleanup_error is None
    assert (report.chunks, report.draft_kps, report.committed_kps, report.orphans) == (3, 4, 2, 1)
    rows = neo.q(f"MATCH (n) WHERE n:Chunk OR n:KnowledgePoint RETURN n.{NEW_PROP} AS v, n.{OLD_PROP} AS o, "
                 "n.version_id AS version")
    assert all(r["o"] is None for r in rows)
    assert all(len(r["v"]) == 4 for r in rows if r["version"] != neo.stock.failed)
    names = {r["name"] for r in neo.q("SHOW INDEXES YIELD name, type WHERE type = 'VECTOR' RETURN name")}
    assert names == {f"chunk_embedding_{NEW_PROP[10:]}", f"kp_embedding_{NEW_PROP[10:]}"}
    assert recorded(db) == NEW


@live
def test_live_failure_keeps_old_space_then_rerun_switches(db, neo):
    client = FakeEmbeddingClient()
    client.script(ModelServerError("next-embed", status_code=503))
    with pytest.raises(reembed.ReembedError):
        run(db, neo.driver, client)
    assert recorded(db) == OLD
    rows = neo.q(f"MATCH (n) WHERE n:Chunk OR n:KnowledgePoint RETURN n.{OLD_PROP} AS o")
    assert all(len(r["o"]) == 4 for r in rows)
    names = {r["name"] for r in neo.q("SHOW INDEXES YIELD name, type WHERE type = 'VECTOR' RETURN name")}
    assert f"kp_embedding_{OLD_PROP[10:]}" in names
    assert run(db, neo.driver).action == "switched" and recorded(db) == NEW
