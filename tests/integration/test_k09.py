"""K09 demo import against real Neo4j 5.26: the real worker pipeline processes the upload,
the real G05 publish runs, and a second import changes nothing.

Runs only with ``SMARTSKETCH_TEST_NEO4J_URI/USER/PASSWORD`` (same convention as F13 and the
demo-mode integration tests); cleans up only the courses it created.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest

from app.config import load_settings
from app.repositories.accounts import insert_account
from app.repositories.graph_migrations import GraphVectorWriter, apply_migrations, sqlite_current_space
from app.repositories.neo4j import Neo4jRepository
from app.repositories.sqlite import connect, migrate
from app.services.ai.embeddings import EmbeddingAdapter
from app.services.ai.factory import build_embedding_client
from app.services.demo_import import import_demo, load_manifest
from app.services.startup import validate_embedding_space
from app.services.versions.publish import PublishContext, publish
from app.workers import persist_graph, runner

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "datasets" / "demo" / "manifest.json"
VALID_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA"
_ENV = ("SMARTSKETCH_TEST_NEO4J_URI", "SMARTSKETCH_TEST_NEO4J_USER", "SMARTSKETCH_TEST_NEO4J_PASSWORD")
pytestmark = pytest.mark.skipif(not all(os.environ.get(n) for n in _ENV),
                                reason="isolated Neo4j fixture not configured")


@pytest.fixture
def env(tmp_path):
    neo4j = pytest.importorskip("neo4j")
    uri, auth = os.environ[_ENV[0]], (os.environ[_ENV[1]], os.environ[_ENV[2]])
    driver = neo4j.GraphDatabase.driver(uri, auth=auth)
    apply_migrations(driver)
    url = f"sqlite:///{(tmp_path / 'state.sqlite3').as_posix()}"
    migrate(url)
    settings = load_settings({
        "SQLITE_URL": url, "STORAGE_DIR": str(tmp_path / "files"), "LLM_MODE": "demo", "EMBEDDING_MODE": "demo",
        "NEO4J_URI": os.environ[_ENV[0]], "NEO4J_USER": os.environ[_ENV[1]], "NEO4J_PASSWORD": os.environ[_ENV[2]],
        "TASK_LEASE_SECONDS": "15", "LLM_MAX_CONCURRENCY": "1", "COURSE_LOCK_WAIT_SECONDS": "0",
    })
    validate_embedding_space(settings)
    embedder = EmbeddingAdapter(settings, build_embedding_client(settings))
    GraphVectorWriter(driver, lambda: embedder.space).ensure_vector_indexes(embedder.space)
    driver.execute_query("CALL db.awaitIndexes(300)", database_="neo4j")
    for name, role in (("demo_teacher", "teacher"), ("demo_student", "student"), ("demo_student2", "student")):
        insert_account(url, account_id=uuid.uuid4().hex, username=name, password_hash=VALID_HASH, role=role)
    repo = Neo4jRepository(driver, persist_driver_factory=lambda: neo4j.AsyncGraphDatabase.driver(uri, auth=auth))
    created: list[str] = []
    try:
        yield settings, url, repo, driver, created
    finally:
        for course in created:
            driver.execute_query("MATCH (n {course_id: $c}) DETACH DELETE n", parameters_={"c": course},
                                 database_="neo4j")
        driver.close()


def test_import_processes_publishes_and_is_idempotent(env):
    settings, url, repo, driver, created = env
    toolkit = runner.build_toolkit(settings)

    def worker(_seconds: float) -> None:
        persist_graph.run_pipeline_once(settings, toolkit=toolkit, repo=repo, owner="k09-test")

    def publisher(course_id: str, teacher_id: str) -> tuple[int, bool]:
        ctx = PublishContext(url, repo, EmbeddingAdapter(settings, build_embedding_client(settings)),
                             sqlite_current_space(url), lease_seconds=30, lock_wait_seconds=5)
        outcome = publish(ctx, course_id, created_by=teacher_id)
        return outcome.version, outcome.unchanged

    manifest = load_manifest(MANIFEST)
    first = import_demo(settings, manifest, publisher=publisher, sleep=worker, poll_seconds=0, wait_seconds=120)
    created.append(first.course_id)
    assert first.course_created and first.uploaded == ["ch3-stack-queue.md"]
    assert first.published_version == 1 and first.publish_unchanged is False
    [record] = driver.execute_query(
        "MATCH (n:KnowledgePoint {course_id: $c}) WHERE n.version_id <> 'draft' RETURN count(n) AS n",
        parameters_={"c": first.course_id}, database_="neo4j").records
    assert record["n"] >= 10

    second = import_demo(settings, manifest, publisher=publisher, sleep=worker, poll_seconds=0, wait_seconds=120)
    assert second.course_id == first.course_id and not second.course_created
    assert second.uploaded == [] and second.members_added == []
    assert (second.published_version, second.publish_unchanged) == (1, True)
    with connect(url) as db:
        assert db.execute("SELECT COUNT(*) FROM courses").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM processing_tasks").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM graph_versions WHERE course_id = ? AND kind = 'publish'",
                          (first.course_id,)).fetchone()[0] == 1
