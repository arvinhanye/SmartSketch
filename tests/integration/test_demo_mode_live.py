"""演示模型模式（ADR-076）连真实 Neo4j 5.26 的端到端：上传 → worker 流水线 → 草稿图非空；演示向量写入
Neo4j 余弦索引后，覆盖问题越过建议阈值、无关问题低于阈值。

只在设置 ``SMARTSKETCH_TEST_NEO4J_URI/USER/PASSWORD`` 时运行（与 F13 等集成测试同一约定）；每个用例使用
独立课程 ID，只清理自己的数据。
"""

from __future__ import annotations

import hashlib
import os
import secrets
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.config import load_settings
from app.repositories import tasks
from app.repositories.chunks import list_task_revisions
from app.repositories.graph_migrations import GraphVectorWriter, apply_migrations
from app.repositories.neo4j import GraphScope, Neo4jRepository
from app.repositories.sqlite import connect, migrate
from app.repositories.vector_search import search_chunks
from app.services.ai.embeddings import EmbeddingAdapter
from app.services.ai.factory import build_embedding_client
from app.services.file_storage import FileStorage, StoredFile
from app.services.startup import validate_embedding_space
from app.services.versions.chunk_vectors import index_chunks
from app.workers import persist_graph, runner

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "documents" / "stack-queue-notes.md"
#: 与 tests/backend/test_demo_mode.py、.env.example 注释中的演示建议阈值一致。
DEMO_THRESHOLD = 0.58
PREREQ_TEXT = (
    "# 第4章 队列\n\n"
    "队列是一种先进先出的线性表。\n"
    "循环队列是队列的一种实现。学习循环队列之前需要先掌握队列。\n"
    "学习队列之前需要先掌握循环队列。\n"
    "双端队列建立在队列的基础上。\n"
)

_ENV = ("SMARTSKETCH_TEST_NEO4J_URI", "SMARTSKETCH_TEST_NEO4J_USER", "SMARTSKETCH_TEST_NEO4J_PASSWORD")
_LIVE = all(os.environ.get(name) for name in _ENV)
pytestmark = pytest.mark.skipif(not _LIVE, reason="isolated Neo4j fixture not configured")


@pytest.fixture
def graph():
    neo4j = pytest.importorskip("neo4j")
    course = "demo-" + uuid.uuid4().hex
    driver = neo4j.GraphDatabase.driver(os.environ[_ENV[0]], auth=(os.environ[_ENV[1]], os.environ[_ENV[2]]))
    apply_migrations(driver)

    def q(query: str, **params):
        return [dict(r) for r in driver.execute_query(query, parameters_=params, routing_="w",
                                                      database_="neo4j").records]

    try:
        yield SimpleNamespace(course=course, repo=Neo4jRepository(driver), q=q, driver=driver)
    finally:
        q("MATCH (n {course_id: $c}) DETACH DELETE n", c=course)
        driver.close()


def _settings(tmp_path: Path):
    db_url = f"sqlite:///{(tmp_path / 'state.sqlite3').as_posix()}"
    migrate(db_url)
    return load_settings({"SQLITE_URL": db_url, "STORAGE_DIR": str(tmp_path / "files"), "LLM_MODE": "demo",
                          "EMBEDDING_MODE": "demo", "TASK_LEASE_SECONDS": "15", "LLM_MAX_CONCURRENCY": "1",
                          "COURSE_LOCK_WAIT_SECONDS": "0"})


def _upload(settings, course: str, data: bytes) -> str:
    storage = FileStorage(settings.STORAGE_DIR, settings.UPLOAD_MAX_BYTES)
    name = secrets.token_hex(16) + ".md"
    path = storage.path_for(name)
    path.write_bytes(data)
    stored = StoredFile(storage_name=name, path=path, original_filename="notes.md", format="markdown",  # type: ignore[arg-type]
                        size_bytes=len(data), content_hash="sha256:" + hashlib.sha256(data).hexdigest())
    return tasks.create_material_task(settings.SQLITE_URL, course_id=course, stored_file=stored,
                                      idempotency_key=secrets.token_hex(8)).task.id


def _run(settings, graph, data: bytes) -> str:
    task_id = _upload(settings, graph.course, data)
    result = persist_graph.run_pipeline_once(settings, toolkit=runner.build_toolkit(settings), repo=graph.repo,
                                             owner="w")
    assert result.lease is not None and result.lease.task_id == task_id
    assert [stage for stage, _ in result.stages] == ["parsing", "extracting", "merging", "persisting"]
    assert all(status == "advanced" for _, status in result.stages), result.stages
    with connect(settings.SQLITE_URL) as database:
        [(stage, error)] = database.execute(
            "SELECT stage, error_code FROM processing_tasks WHERE id = ?", (task_id,)).fetchall()
    assert (stage, error) == ("awaiting_review", None)
    return task_id


def test_upload_to_awaiting_review_with_non_empty_draft_graph(tmp_path, graph):
    settings = _settings(tmp_path)
    _run(settings, graph, FIXTURE.read_bytes())
    names = {row["name"] for row in graph.q(
        "MATCH (n:KnowledgePoint {course_id: $c, version_id: 'draft'}) RETURN n.name AS name", c=graph.course)}
    assert {"栈", "队列", "顺序栈", "链栈", "循环队列", "后进先出", "先进先出"} <= names
    rels = graph.q("MATCH (a)-[r {course_id: $c, version_id: 'draft'}]->(b) "
                   "RETURN type(r) AS type, a.name AS a, b.name AS b", c=graph.course)
    assert ("CONTAINS", "栈与队列", "顺序栈") in {(r["type"], r["a"], r["b"]) for r in rels}


def test_prerequisites_in_draft_graph_are_acyclic(tmp_path, graph):
    settings = _settings(tmp_path)
    _run(settings, graph, PREREQ_TEXT.encode("utf-8"))
    edges = graph.q("MATCH (a)-[r:PREREQUISITE {course_id: $c, version_id: 'draft'}]->(b) "
                    "RETURN a.name AS a, b.name AS b", c=graph.course)
    assert {(e["a"], e["b"]) for e in edges} == {("队列", "循环队列"), ("队列", "双端队列")}
    [row] = graph.q("MATCH p = (a:KnowledgePoint {course_id: $c, version_id: 'draft'})"
                    "-[:PREREQUISITE*1..10]->(a) RETURN count(p) AS cycles", c=graph.course)
    assert row["cycles"] == 0


def test_demo_vectors_gate_questions_in_neo4j_index(tmp_path, graph):
    settings = _settings(tmp_path)
    validate_embedding_space(settings)
    task_id = _run(settings, graph, FIXTURE.read_bytes())
    embedder = EmbeddingAdapter(settings, build_embedding_client(settings))
    GraphVectorWriter(graph.driver, lambda: embedder.space).ensure_vector_indexes(embedder.space)
    graph.q("CALL db.awaitIndexes(300)")
    revisions = [r.revision_id for r in list_task_revisions(settings.SQLITE_URL, course_id=graph.course,
                                                           task_id=task_id)]
    scope = GraphScope(graph.course, "v-demo")
    assert index_chunks(settings.SQLITE_URL, graph.repo, embedder, scope, revisions, embedder.space).embedded > 0

    def best(question: str) -> float:
        [vector] = embedder.embed((question,))
        hits = search_chunks(graph.repo, scope, revisions, vector, space=embedder.space, limit=5)
        return max((hit.score for hit in hits), default=0.0)

    assert best("什么是栈") >= DEMO_THRESHOLD
    assert best("队列的特点") >= DEMO_THRESHOLD
    assert best("今天天气怎么样") < DEMO_THRESHOLD
    assert best("如何做红烧肉") < DEMO_THRESHOLD
