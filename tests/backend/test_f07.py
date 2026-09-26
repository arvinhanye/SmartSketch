"""F07 graph reads: ``getGraph`` / ``getKnowledgePoint`` through the real app and SQLite.

The Neo4j side is a fake ``GraphReader`` that records the scope it was asked for; the
Cypher itself (draft visibility V, published copies) runs against a real server in
``tests/integration/test_f07.py``. Chunks come from a fake ``get_chunks`` keyed by course,
so a chunk of another course is simply absent, as D10 guarantees.
"""

from __future__ import annotations

import copy
import hashlib
import json
import time
import uuid
from pathlib import Path

import jsonschema
import pytest
import yaml
from fastapi.testclient import TestClient

from app.main import create_app
from app.repositories.accounts import insert_account
from app.repositories.chunks import StoredChunk
from app.repositories.graph_read import NodeEvidence
from app.repositories.neo4j import RepositoryConnectionError
from app.repositories.courses import add_member, create_course
from app.repositories.sqlite import connect, migrate
from app.services.auth import issue_access_token
from app.services.chunking import ChunkSource
from app.services.graph import read as graph_read
from app.services.parsers.models import SourceLocator

ROOT = Path(__file__).resolve().parents[2]
SECRET = "f07-test-signing-key-0123456789abcdefghij"
VALID_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA"

# --- contract validation (same approach as test_c11) --------------------------------------

_SPEC = yaml.safe_load((ROOT / "src/contracts/api.v1.yaml").read_text(encoding="utf-8"))


def _rewrite(node):
    if isinstance(node, dict):
        return {
            key: (value.replace("#/components/schemas/", "#/$defs/")
                  if key == "$ref" and isinstance(value, str) else _rewrite(value))
            for key, value in node.items()
        }
    if isinstance(node, list):
        return [_rewrite(item) for item in node]
    return node


_DEFS = _rewrite(copy.deepcopy(_SPEC["components"]["schemas"]))


def assert_schema(name: str, instance) -> None:
    jsonschema.Draft202012Validator({"$defs": _DEFS, "$ref": f"#/$defs/{name}"}).validate(instance)


# --- fakes -------------------------------------------------------------------------------


def kp(kp_id, name=None, **extra):
    props = {"kp_id": kp_id, "name": name or kp_id.upper(), "type": "concept", "definition": f"{kp_id} 的定义",
             "confidence": 0.9, "status": "draft", "source": "ai", "locked": False, "revision": 1}
    props.update(extra)
    return props


def edge(kind, a, b, **extra):
    props = {"rel_id": f"rel_{kind}_{a}_{b}", "confidence": 0.8, "status": "draft", "source": "ai"}
    props.update(extra)
    return {"type": kind, "from_id": a, "to_id": b, "p": props}


class FakeReader:
    """Stands in for ``GraphReader``; one graph per ``version_id``."""

    def __init__(self):
        self.graphs: dict[str, dict] = {}
        self.calls: list[tuple[str, object, str]] = []
        self.fail = False

    def put(self, version_id, *, nodes=(), edges=(), evidence=(), chapters=()):
        self.graphs[version_id] = {"nodes": list(nodes), "edges": list(edges), "evidence": list(evidence),
                                   "chapters": list(chapters)}

    def _graph(self, method, scope, reader):
        self.calls.append((method, scope, reader))
        if self.fail:
            raise RepositoryConnectionError()
        return self.graphs.get(scope.version_id, {"nodes": [], "edges": [], "evidence": [], "chapters": []})

    def nodes(self, scope, reader, kp_ids=None):
        nodes = self._graph("nodes", scope, reader)["nodes"]
        return [n for n in nodes if kp_ids is None or n["kp_id"] in kp_ids]

    def edges(self, scope, reader, kp_ids=None):
        edges = self._graph("edges", scope, reader)["edges"]
        return [e for e in edges if kp_ids is None or e["from_id"] in kp_ids or e["to_id"] in kp_ids]

    def evidence(self, scope, reader, kp_ids):
        return [e for e in self._graph("evidence", scope, reader)["evidence"] if e.kp_id in set(kp_ids)]

    def chapters(self, scope, reader):
        return self._graph("chapters", scope, reader)["chapters"]


def stored_chunk(course_id, chunk_id, blocks):
    """A chunk laid out exactly as D08 renders it: ``path\\nbody`` segments joined by blank lines."""
    parts, sources = [], []
    for ordinal, (locator, body) in enumerate(blocks):
        path = locator.section_path
        parts.append(f"{path}\n{body}" if path else body)
        sources.append(ChunkSource(ordinal, 0, len(body), locator))
    text = "\n\n".join(parts)
    return StoredChunk(chunk_id=chunk_id, course_id=course_id, material_id="doc-" + chunk_id, revision_id="rev",
                       ordinal=0, text=text, text_sha256=hashlib.sha256(text.encode()).hexdigest(),
                       section_titles=(), sources=tuple(sources))


# --- scenario ----------------------------------------------------------------------------


def _account(url, name, role):
    return insert_account(url, account_id=uuid.uuid4().hex, username=name, password_hash=VALID_HASH, role=role)


def token(user):
    return issue_access_token(user_id=user.id, role=user.role, secret=SECRET.encode(),
                              issued_at=int(time.time()), ttl_seconds=3600)


class Scenario:
    def __init__(self, client, url, teacher, student, outsider, course, reader, chunks):
        self.client, self.url, self.reader, self.chunks = client, url, reader, chunks
        self.teacher, self.student, self.outsider, self.course = teacher, student, outsider, course

    def get(self, path, user=None, **params):
        headers = {} if user is None else {"Authorization": f"Bearer {token(user)}"}
        return self.client.get(f"/api/v1/courses/{self.course.id}{path}", headers=headers, params=params)

    def publish(self, version=1):
        version_id = f"ver-{version}"
        with connect(self.url) as db:
            db.execute("UPDATE courses SET published_version = ?, published_version_id = ? WHERE id = ?",
                       (version, version_id, self.course.id))
        return version_id

    def task(self, task_id, stage):
        with connect(self.url) as db:
            if db.execute("SELECT 1 FROM materials WHERE id = 'doc1'").fetchone() is None:
                db.execute(
                    "INSERT INTO materials (id, course_id, filename, format, size_bytes, content_hash, storage_name)"
                    " VALUES ('doc1', ?, 'a.txt', 'txt', 1, ?, 'stored')",
                    (self.course.id, "sha256:" + "0" * 64))
            db.execute("INSERT INTO processing_tasks (id, course_id, document_id, idempotency_key, stage, progress)"
                       " VALUES (?, ?, 'doc1', ?, ?, ?)",
                       (task_id, self.course.id, task_id, stage, 0 if stage == "queued" else 0.5))

    def add_chunk(self, chunk_id, blocks, course_id=None):
        self.chunks[chunk_id] = stored_chunk(course_id or self.course.id, chunk_id, blocks)


@pytest.fixture
def s(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'state.sqlite3').as_posix()}"
    migrate(url)
    teacher = _account(url, "teacher1", "teacher")
    student = _account(url, "student1", "student")
    outsider = _account(url, "teacher2", "teacher")
    course = create_course(url, name="数据结构", description=None, creator_id=teacher.id)
    add_member(url, course_id=course.id, user_id=student.id, role="student", added_by=teacher.id)
    monkeypatch.setenv("SQLITE_URL", url)
    monkeypatch.setenv("AUTH_JWT_SECRET", SECRET)

    chunks: dict[str, StoredChunk] = {}

    def fake_get_chunks(sqlite_url, *, course_id, chunk_ids):
        return tuple(chunks[c] for c in dict.fromkeys(chunk_ids) if c in chunks and chunks[c].course_id == course_id)

    monkeypatch.setattr(graph_read, "get_chunks", fake_get_chunks)
    application = create_app()
    reader = FakeReader()
    application.state.graph_reader = reader
    with TestClient(application) as client:
        yield Scenario(client, url, teacher, student, outsider, course, reader, chunks)


PAGE = SourceLocator(page=3)
SECTION = SourceLocator(section_titles=("第二章 栈",), paragraph=2)


def _two_block_chunk(s, chunk_id="c1"):
    s.add_chunk(chunk_id, [(PAGE, "栈是一种后进先出的线性表。"), (SECTION, "队列是一种先进先出的线性表。")])
    return s.chunks[chunk_id]


# --- read entry: teacher draft vs published ------------------------------------------------


def test_teacher_reads_draft_with_effective_tasks_from_sqlite(s):
    s.task("t-review", "awaiting_review")
    s.task("t-done", "completed")
    s.task("t-running", "extracting")
    s.reader.put("draft", nodes=[kp("a"), kp("b")], edges=[edge("PREREQUISITE", "a", "b")])

    response = s.get("/graph", s.teacher)

    assert response.status_code == 200
    body = response.json()
    assert_schema("GraphExchange", body)
    assert body["graph_version"] is None and "graph_version" in body
    assert body["course_id"] == s.course.id and body["format_version"] == "1.0"
    assert [n["id"] for n in body["nodes"]] == ["a", "b"]
    scopes = {(scope.version_id, scope.effective_task_ids, reader) for _, scope, reader in s.reader.calls}
    assert scopes == {("draft", ("t-done", "t-review"), "teacher")}


def test_teacher_empty_draft_is_an_empty_graph_not_an_error(s):
    body = s.get("/graph", s.teacher).json()
    assert_schema("GraphExchange", body)
    assert body["nodes"] == [] and body["edges"] == [] and body["graph_version"] is None
    assert body["stats"] == {"node_count": 0, "edge_count": 0, "edges_by_type": {}, "isolated_count": 0}


def test_student_on_unpublished_course_gets_graph_not_published_without_reading_graph(s):
    s.reader.put("draft", nodes=[kp("a")])
    for path in ("/graph", "/kp/a"):
        response = s.get(path, s.student)
        assert response.status_code == 404
        assert response.json()["code"] == "GRAPH_NOT_PUBLISHED"
    assert s.reader.calls == []


def test_teacher_asking_for_a_version_of_an_unpublished_course_gets_graph_not_published(s):
    response = s.get("/graph", s.teacher, version=1)
    assert response.status_code == 404 and response.json()["code"] == "GRAPH_NOT_PUBLISHED"


def test_student_reads_latest_published_version_never_the_draft(s):
    version_id = s.publish(2)
    s.reader.put("draft", nodes=[kp("draft-only")])
    s.reader.put(version_id, nodes=[kp("a", status="approved")])

    body = s.get("/graph", s.student).json()

    assert_schema("GraphExchange", body)
    assert body["graph_version"] == 2
    assert [n["id"] for n in body["nodes"]] == ["a"]
    assert {(scope.version_id, scope.effective_task_ids, reader) for _, scope, reader in s.reader.calls} == \
        {(version_id, None, "student")}


def test_published_empty_graph_is_200_and_differs_from_unpublished(s):
    s.publish(1)
    response = s.get("/graph", s.student)
    assert response.status_code == 200
    assert response.json()["nodes"] == [] and response.json()["graph_version"] == 1


def test_teacher_with_version_reads_the_published_copy(s):
    version_id = s.publish(1)
    s.reader.put(version_id, nodes=[kp("a", status="approved")])
    s.reader.put("draft", nodes=[kp("a"), kp("b")])
    body = s.get("/graph", s.teacher, version=1).json()
    assert body["graph_version"] == 1 and [n["id"] for n in body["nodes"]] == ["a"]
    assert {reader for _, _, reader in s.reader.calls} == {"teacher"}


def test_unknown_version_is_not_found_and_invalid_version_is_rejected(s):
    s.publish(2)
    for user in (s.teacher, s.student):
        response = s.get("/graph", user, version=1)
        assert response.status_code == 404 and response.json()["code"] == "NOT_FOUND"
    assert s.get("/graph", s.student, version=0).status_code == 422
    assert s.get("/graph", s.student, type="lemma").status_code == 422
    assert s.get("/graph", s.student, relation_types="IS_A").status_code == 422


def test_access_matrix(s):
    s.publish(1)
    assert s.get("/graph").status_code == 401
    assert s.get("/kp/a").status_code == 401
    assert s.get("/graph", s.outsider).status_code == 403
    assert s.get("/kp/a", s.outsider).status_code == 403
    assert s.reader.calls == []


def test_graph_database_down_is_storage_unavailable(s):
    s.reader.fail = True
    for path in ("/graph", "/kp/a"):
        response = s.get(path, s.teacher)
        assert response.status_code == 503
        assert response.json()["code"] == "STORAGE_UNAVAILABLE"


# --- assembly: filters, levels, relations ---------------------------------------------------


def test_filters_keep_only_edges_between_kept_nodes(s):
    s.reader.put("draft", nodes=[
        kp("a", chapter_id="ch1"), kp("b", chapter_id="ch1", type="theorem"), kp("c", chapter_id="ch2"),
    ], edges=[
        edge("PREREQUISITE", "a", "b"), edge("RELATED_TO", "a", "c"), edge("EXAMPLE_OF", "b", "a"),
    ], chapters=[{"chapter_id": "ch2", "title": "第二章", "order": 2}, {"chapter_id": "ch1", "title": "第一章", "order": 1}])

    by_chapter = s.get("/graph", s.teacher, chapter_id="ch1").json()
    assert [n["id"] for n in by_chapter["nodes"]] == ["a", "b"]
    assert {e["type"] for e in by_chapter["edges"]} == {"PREREQUISITE", "EXAMPLE_OF"}
    assert [c["id"] for c in by_chapter["chapters"]] == ["ch2", "ch1"]

    by_type = s.get("/graph", s.teacher, type="theorem").json()
    assert [n["id"] for n in by_type["nodes"]] == ["b"] and by_type["edges"] == []

    by_relation = s.client.get(f"/api/v1/courses/{s.course.id}/graph",
                               params=[("relation_types", "RELATED_TO"), ("relation_types", "EXAMPLE_OF")],
                               headers={"Authorization": f"Bearer {token(s.teacher)}"}).json()
    assert sorted(e["type"] for e in by_relation["edges"]) == ["EXAMPLE_OF", "RELATED_TO"]
    assert len(by_relation["nodes"]) == 3
    assert by_relation["stats"]["edges_by_type"] == {"RELATED_TO": 1, "EXAMPLE_OF": 1}
    assert by_relation["stats"]["isolated_count"] == 0


def test_level_is_longest_prerequisite_path_ignoring_rejected_and_filters(s):
    s.reader.put("draft", nodes=[kp("a", chapter_id="x"), kp("b"), kp("c"), kp("d")], edges=[
        edge("PREREQUISITE", "a", "b"), edge("PREREQUISITE", "b", "c"), edge("PREREQUISITE", "a", "c"),
        edge("PREREQUISITE", "c", "d", status="rejected"), edge("RELATED_TO", "a", "d"),
    ])
    levels = {n["id"]: n["level"] for n in s.get("/graph", s.teacher).json()["nodes"]}
    assert levels == {"a": 0, "b": 1, "c": 2, "d": 0}
    # Levels are properties of the whole graph, not of the filtered view.
    filtered = s.get("/graph", s.teacher, relation_types="RELATED_TO").json()["nodes"]
    assert {n["id"]: n["level"] for n in filtered}["c"] == 2


def test_relation_sources_are_located_and_filtered_by_effective_tasks(s):
    s.task("t-ok", "awaiting_review")
    s.task("t-running", "extracting")
    _two_block_chunk(s, "c-page")
    s.add_chunk("c-section", [(SECTION, "只有章节定位的块。")])
    s.add_chunk("c-hidden", [(PAGE, "未完成任务的块。")])
    s.add_chunk("c-foreign", [(PAGE, "别的课程的块。")], course_id="other-course")
    pairs = [json.dumps(p) for p in (["t-ok", "c-page"], [None, "c-section"], ["t-running", "c-hidden"],
                                        ["t-ok", "c-foreign"], ["t-ok", "c-missing"], "not json")]
    s.reader.put("draft", nodes=[kp("a"), kp("b")], edges=[edge("RELATED_TO", "a", "b", source_pairs=pairs)])

    body = s.get("/graph", s.teacher).json()

    assert_schema("GraphExchange", body)
    refs = body["edges"][0]["source_refs"]
    assert refs == [
        {"chunk_id": "c-page", "document_id": "doc-c-page", "page": 3},
        {"chunk_id": "c-section", "document_id": "doc-c-section", "section_path": "第二章 栈 > 第2段"},
    ]


def test_published_relations_use_every_source_pair(s):
    version_id = s.publish(1)
    s.add_chunk("c1", [(PAGE, "块。")])
    s.reader.put(version_id, nodes=[kp("a"), kp("b")],
                 edges=[edge("RELATED_TO", "a", "b", source_pairs=[json.dumps(["t-gone", "c1"])])])
    assert s.get("/graph", s.student).json()["edges"][0]["source_refs"][0]["chunk_id"] == "c1"


def test_downgraded_relation_keeps_its_contract_shape(s):
    s.reader.put("draft", nodes=[kp("a"), kp("b"), kp("c")], edges=[
        edge("RELATED_TO", "a", "b", status="low_confidence", downgraded_from_type="PREREQUISITE",
             downgrade_cycle=["a", "b", "c"]),
        edge("RELATED_TO", "b", "c"),
    ])
    edges = {e["from_id"] + e["to_id"]: e for e in s.get("/graph", s.teacher).json()["edges"]}
    assert edges["ab"]["downgraded_from_type"] == "PREREQUISITE"
    assert edges["ab"]["downgrade_cycle"] == ["a", "b", "c"]
    assert "downgraded_from_type" not in edges["bc"] and "downgrade_cycle" not in edges["bc"]
    assert_schema("Relation", edges["ab"])


def test_malformed_rows_are_skipped_not_fatal(s):
    s.reader.put("draft", nodes=[kp("a"), {"kp_id": "bad", "name": ""}, kp("b")],
                 edges=[edge("PREREQUISITE", "a", "b"), edge("PREREQUISITE", "a", "b", status="bogus")])
    body = s.get("/graph", s.teacher).json()
    assert [n["id"] for n in body["nodes"]] == ["a", "b"] and len(body["edges"]) == 1
    assert_schema("GraphExchange", body)


# --- knowledge point detail -----------------------------------------------------------------


def test_detail_locates_each_evidence_span_and_lists_neighbours(s):
    chunk = _two_block_chunk(s)
    stack = chunk.text.index("栈是")
    queue = chunk.text.index("队列")
    s.reader.put("draft", nodes=[kp("a"), kp("b", "队列"), kp("c", "栈"), kp("d", "线性表", type="theorem"), kp("e")],
                 edges=[edge("PREREQUISITE", "d", "a"), edge("PREREQUISITE", "a", "c"),
                        edge("RELATED_TO", "b", "a"), edge("PREREQUISITE", "e", "a", status="rejected")],
                 evidence=[NodeEvidence("a", "c1", "doc1", stack, stack + 2),
                           NodeEvidence("a", "c1", "doc1", queue, queue + 2),
                           NodeEvidence("a", "c1", "doc1", queue, queue + 2),
                           NodeEvidence("b", "c1", "doc1", 0, 1)])

    response = s.get("/kp/a", s.teacher)

    assert response.status_code == 200
    body = response.json()
    assert_schema("KnowledgePointDetail", body)
    assert body["source_refs"] == [
        {"chunk_id": "c1", "document_id": "doc1", "page": 3, "text": "栈是"},
        {"chunk_id": "c1", "document_id": "doc1", "section_path": "第二章 栈 > 第2段", "text": "队列"},
    ]
    assert body["prerequisites"] == [{"id": "d", "name": "线性表", "type": "theorem"}]
    assert body["successors"] == [{"id": "c", "name": "栈", "type": "concept"}]
    assert body["related"] == [{"id": "b", "name": "队列", "type": "concept"}]
    assert body["level"] == 1


def test_detail_of_invisible_node_is_not_found(s):
    s.reader.put("draft", nodes=[kp("a")])
    response = s.get("/kp/zzz", s.teacher)
    assert response.status_code == 404 and response.json()["code"] == "NOT_FOUND"


def test_detail_without_any_locatable_source_is_internal_error(s):
    s.add_chunk("c-foreign", [(PAGE, "别的课程。")], course_id="other-course")
    s.reader.put("draft", nodes=[kp("a")], evidence=[NodeEvidence("a", "c-foreign", "doc1", 0, 2),
                                                    NodeEvidence("a", "c-missing", "doc1", 0, 2)])
    response = s.get("/kp/a", s.teacher)
    assert response.status_code == 500 and response.json()["code"] == "INTERNAL_ERROR"


def test_student_detail_reads_published_copy(s):
    version_id = s.publish(1)
    s.add_chunk("c1", [(PAGE, "栈是一种线性表。")])
    s.reader.put(version_id, nodes=[kp("a", status="approved")], evidence=[NodeEvidence("a", "c1", None, 0, 1)])
    body = s.get("/kp/a", s.student).json()
    assert_schema("KnowledgePointDetail", body)
    assert body["source_refs"] == [{"chunk_id": "c1", "document_id": "doc-c1", "page": 3, "text": "栈"}]
    assert {(scope.version_id, reader) for _, scope, reader in s.reader.calls} == {(version_id, "student")}
