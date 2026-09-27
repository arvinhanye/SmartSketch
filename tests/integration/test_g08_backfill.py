"""G08 backfill against a real Neo4j and a migrated SQLite: ``scripts/backfill_chunk_vectors.py``.

Versions committed before G08 (ADR-066) have no chunk vectors, and publishing again does not help
(the idempotent path skips P8; superseded revisions are never re-indexed). The command indexes every
chunk of every selected committed version's snapshot revisions in the recorded space, refuses on a
space mismatch (V12) and never calls the model in ``--dry-run``.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import uuid
from pathlib import Path

import pytest

from app.repositories import versions
from app.repositories.courses import create_course
from app.repositories.graph_migrations import GraphVectorWriter, vector_property
from app.repositories.neo4j import GraphScope
from app.repositories.vector_search import search_chunks
from app.services.ai.fake import FakeEmbeddingClient
from app.services.versions.publish import PublishContext, publish
from app.services.versions.resolver import clear_cache
from app.services.versions.snapshot import load_snapshot
from test_g04 import C0, C1, OTHER_REV, REV, SPACE, _ENV, base_graph, embedder, env, live, run, sha

pytestmark = live
__all__ = ["env"]  # 夹具取自 test_g04

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("backfill_chunk_vectors", ROOT / "scripts" / "backfill_chunk_vectors.py")
backfill = importlib.util.module_from_spec(_spec)
sys.modules["backfill_chunk_vectors"] = backfill
_spec.loader.exec_module(backfill)

PROP = vector_property(SPACE)
C2 = f"{REV}-2"
NEW0, NEW1 = f"{OTHER_REV}-0", f"{OTHER_REV}-1"
THIRD_REV = "rev_" + "c" * 64


class SpyClient:
    """Wraps the deterministic fake client and records every text sent to the model."""

    def __init__(self):
        self.inner = FakeEmbeddingClient()
        self.texts: list[str] = []

    def embed(self, request):
        self.texts.extend(request.texts)
        return self.inner.embed(request)


class NoModel:
    def embed(self, request):
        pytest.fail("the embedding model must not be called")


def add_chunk(env, chunk_id, ordinal, text, *, revision=REV, course=None, material="m1"):
    env.sql("INSERT INTO chunks (chunk_id, revision_id, course_id, material_id, ordinal, text, text_sha256, "
            "section_titles, sources) VALUES (?, ?, ?, ?, ?, ?, ?, '[]', ?)",
            chunk_id, revision, course or env.course, material, ordinal, text, sha(text),
            json.dumps([{"block_ordinal": 0, "start": 0, "end": 2, "locator": {"section_titles": [], "paragraph": 1}}]))


def vectors(env, course=None):
    rows = env.q(f"MATCH (c:Chunk {{course_id: $c}}) RETURN c.chunk_id AS id, size(c.{PROP}) AS dims",
                 c=course or env.course)
    return {r["id"]: r["dims"] for r in rows}


def strip(env, course=None):
    """Simulate a version committed before G08: no chunk has a vector."""
    env.q(f"MATCH (c:Chunk {{course_id: $c}}) REMOVE c.{PROP}", c=course or env.course)


def environ(env, *, dims=4, neo4j=False):
    values = {"SQLITE_URL": env.url, "EMBEDDING_MODE": "fake", "EMBEDDING_DIMENSIONS": str(dims),
              "EMBEDDING_BATCH_SIZE": "8"}
    if neo4j:
        values.update({"NEO4J_URI": os.environ[_ENV[0]], "NEO4J_USER": os.environ[_ENV[1]],
                       "NEO4J_PASSWORD": os.environ[_ENV[2]]})
    return values


def main(env, *args, client=None, dims=4):
    return backfill.main(list(args), environ=environ(env, dims=dims), repo=env.repo,
                         client=client if client is not None else SpyClient())


def revisions_of(env, version, course=None):
    record = versions.get_committed(env.url, course or env.course, version)
    return {r["revision_id"] for r in load_snapshot(versions.read_snapshot(env.url, record.version_id)).data["revisions"]}


@pytest.fixture
def bf(env):
    GraphVectorWriter(env.repo._driver, lambda: SPACE).ensure_vector_indexes(SPACE)
    env.q("CALL db.awaitIndexes(60)")
    env.sql("INSERT OR IGNORE INTO embedding_space_state (singleton, model, dimensions, is_fake) VALUES (1, '', 4, 1)")
    add_chunk(env, C2, 2, "没有被任何知识点引用的块")
    clear_cache()
    extra: list[str] = []
    env.extra_courses = extra
    try:
        yield env
    finally:
        for course in extra:
            env.q("MATCH (n {course_id: $c}) DETACH DELETE n", c=course)


def supersede(env):
    """v2 replaces REV by OTHER_REV: t1 is cancelled, the draft now rests on t2 only."""
    env.sql("INSERT INTO material_revisions (revision_id, course_id, material_id, content_hash, parser_version) "
            "VALUES (?, ?, 'm1', ?, 'txt/1+chunk/1')", OTHER_REV, env.course, sha(OTHER_REV))
    add_chunk(env, NEW0, 0, "新修订的块0", revision=OTHER_REV)
    add_chunk(env, NEW1, 1, "新修订的块1", revision=OTHER_REV)
    env.sql("UPDATE processing_tasks SET stage = 'cancelled', cancel_requested = 1 WHERE id = 't1'")
    env.q("MATCH (n:KnowledgePoint {course_id: $c, version_id: 'draft'}) DETACH DELETE n", c=env.course)
    env.task("t2", "awaiting_review", 2, revision=OTHER_REV)
    env.node("x", tasks=("t2",), chunk=NEW0)
    return run(env)


def other_course(env):
    """A second, published course in the same SQLite and Neo4j; returns its id."""
    course = create_course(env.url, name="操作系统", description=None, creator_id=env.teacher.id).id
    env.extra_courses.append(course)
    env.sql("INSERT INTO materials (id, course_id, filename, format, size_bytes, content_hash, storage_name) "
            "VALUES ('m2', ?, 'b.txt', 'txt', 10, ?, ?)", course, sha("m2"), uuid.uuid4().hex)
    env.sql("INSERT INTO material_revisions (revision_id, course_id, material_id, content_hash, parser_version) "
            "VALUES (?, ?, 'm2', ?, 'txt/1+chunk/1')", THIRD_REV, course, sha("m2"))
    add_chunk(env, f"{THIRD_REV}-0", 0, "另一门课的块", revision=THIRD_REV, course=course, material="m2")
    env.sql("INSERT INTO processing_tasks (id, course_id, document_id, stage, progress, idempotency_key, t6_seq) "
            "VALUES ('u1', ?, 'm2', 'awaiting_review', 0.95, 'u1', 1)", course)
    env.sql("INSERT INTO task_revisions (task_id, revision_id, course_id, material_id) VALUES ('u1', ?, ?, 'm2')",
            THIRD_REV, course)
    env.sql("UPDATE courses SET draft_revision = draft_revision + 1 WHERE id = ?", course)
    env.q("CREATE (n:KnowledgePoint {course_id: $c, version_id: 'draft', kp_id: 'p', name: 'p', type: 'concept', "
          "definition: '定义', status: 'approved', source: 'ai', confidence: 0.9, locked: false, revision: 1, "
          "contrib_manual: false, contrib_tasks: ['u1']}) "
          "MERGE (ch:Chunk {course_id: $c, chunk_id: $chunk}) ON CREATE SET ch.document_id = 'm2' "
          "CREATE (n)-[:EVIDENCED_BY {chunk_id: $chunk, evidence_start: 0, evidence_end: 2, task_id: 'u1'}]->(ch)",
          c=course, chunk=f"{THIRD_REV}-0")
    publish(PublishContext(**env.ctx.__dict__), course, created_by=env.teacher.id)
    return course


# ---------------------------------------------------------------- 成功路径


def test_backfill_restores_every_chunk_of_a_pre_g08_version_and_j01_finds_them(bf, capsys):
    base_graph(bf)
    run(bf)
    strip(bf)
    assert set(vectors(bf).values()) == {None}
    spy = SpyClient()
    # 不注入 repo：走 Neo4jRepository.from_settings 的正式路径
    code = backfill.main([], environ=environ(bf, neo4j=True), client=spy)
    assert code == 0
    assert vectors(bf) == {C0: 4, C1: 4, C2: 4}
    assert sorted(spy.texts) == sorted(["块0", "块1", "没有被任何知识点引用的块"])
    out = capsys.readouterr().out
    assert bf.course in out and "3" in out
    assert bf.url.removeprefix("sqlite:///") not in out  # 不回显配置

    record = versions.get_committed(bf.url, bf.course, 1)
    query = embedder().embed(["没有被任何知识点引用的块"])[0]
    hits = search_chunks(bf.repo, GraphScope(bf.course, record.version_id), [REV], query, space=SPACE, limit=3)
    assert hits[0].chunk_id == C2
    assert {h.chunk_id for h in hits} == {C0, C1, C2}


def test_second_run_embeds_nothing(bf, capsys):
    base_graph(bf)
    run(bf)
    strip(bf)
    assert main(bf) == 0
    capsys.readouterr()
    again = SpyClient()
    assert main(bf, client=again) == 0
    assert again.texts == []
    assert vectors(bf) == {C0: 4, C1: 4, C2: 4}


def test_already_indexed_version_embeds_nothing(bf):
    base_graph(bf)
    run(bf)  # G08 之后发布：已补齐
    assert main(bf, client=NoModel()) == 0


def test_superseded_revision_only_an_old_version_references_is_indexed(bf):
    base_graph(bf)
    run(bf)
    supersede(bf)
    assert revisions_of(bf, 1) == {REV}
    assert revisions_of(bf, 2) == {OTHER_REV}
    strip(bf)
    spy = SpyClient()
    assert main(bf, client=spy) == 0
    assert vectors(bf) == {C0: 4, C1: 4, C2: 4, NEW0: 4, NEW1: 4}
    assert len(spy.texts) == 5  # 每块只算一次


def test_revisions_shared_by_several_versions_are_read_once(bf, monkeypatch):
    base_graph(bf)
    run(bf)
    bf.set_def("a", "二版")
    run(bf)  # v2 与 v1 共用 REV
    bf.set_def("a", "三版")
    run(bf)
    strip(bf)
    calls: list[tuple[str, tuple[str, ...]]] = []
    real = backfill.index_chunks

    def spy(sqlite_url, repo, embedder, scope, revision_ids, space, **kwargs):
        calls.append((scope.course_id, tuple(sorted(revision_ids))))
        return real(sqlite_url, repo, embedder, scope, revision_ids, space, **kwargs)

    monkeypatch.setattr(backfill, "index_chunks", spy)
    assert main(bf) == 0
    assert calls == [(bf.course, (REV,))]
    assert vectors(bf) == {C0: 4, C1: 4, C2: 4}


def test_course_and_version_limit_the_scope(bf):
    base_graph(bf)
    run(bf)
    supersede(bf)
    other = other_course(bf)
    strip(bf)
    strip(bf, other)
    spy = SpyClient()
    assert main(bf, "--course", bf.course, "--version", "2", client=spy) == 0
    assert vectors(bf) == {C0: None, C1: None, C2: None, NEW0: 4, NEW1: 4}  # v1 独有的 REV 未动
    assert set(vectors(bf, other).values()) == {None}  # 另一门课未动
    assert sorted(spy.texts) == ["新修订的块0", "新修订的块1"]

    assert main(bf, "--course", bf.course) == 0  # 本课程全部版本
    assert set(vectors(bf).values()) == {4}
    assert set(vectors(bf, other).values()) == {None}

    assert main(bf) == 0  # 缺省：全部课程
    assert vectors(bf, other) == {f"{THIRD_REV}-0": 4}


# ---------------------------------------------------------------- 边界与失败路径


def test_dry_run_calls_no_model_and_changes_nothing(bf, capsys):
    base_graph(bf)
    run(bf)
    strip(bf)
    before = bf.q("MATCH (c:Chunk {course_id: $c}) RETURN c.chunk_id AS id, properties(c) AS p ORDER BY id",
                  c=bf.course)
    assert main(bf, "--dry-run", client=NoModel()) == 0
    after = bf.q("MATCH (c:Chunk {course_id: $c}) RETURN c.chunk_id AS id, properties(c) AS p ORDER BY id",
                 c=bf.course)
    assert after == before
    out = capsys.readouterr().out
    assert "缺向量 3" in out


def test_dry_run_counts_only_missing_chunks(bf, capsys):
    base_graph(bf)
    run(bf)
    bf.q(f"MATCH (c:Chunk {{course_id: $c, chunk_id: $id}}) REMOVE c.{PROP}", c=bf.course, id=C1)
    assert main(bf, "--dry-run", client=NoModel()) == 0
    assert "缺向量 1" in capsys.readouterr().out


def test_version_space_mismatch_refuses_without_calling_the_model(bf, capsys):
    base_graph(bf)
    run(bf)
    strip(bf)
    bf.sql("UPDATE graph_versions SET embedding_space = 'fake/8' WHERE course_id = ? AND state = 'committed'",
           bf.course)
    assert main(bf, client=NoModel()) == 2
    assert set(vectors(bf).values()) == {None}
    assert "reembed.py" in capsys.readouterr().err


def test_mismatch_in_one_course_refuses_before_writing_any_course(bf):
    base_graph(bf)
    run(bf)
    other = other_course(bf)
    strip(bf)
    strip(bf, other)
    bf.sql("UPDATE graph_versions SET embedding_space = 'fake/8' WHERE course_id = ?", other)
    assert main(bf, client=NoModel()) == 2
    assert set(vectors(bf).values()) == {None}


def test_configured_space_differing_from_recorded_refuses(bf, capsys):
    base_graph(bf)
    run(bf)
    strip(bf)
    assert main(bf, client=NoModel(), dims=8) == 2
    assert set(vectors(bf).values()) == {None}
    assert "reembed.py" in capsys.readouterr().err


def test_uninitialised_recorded_space_is_refused(bf):
    base_graph(bf)
    run(bf)
    bf.sql("DELETE FROM embedding_space_state")
    assert main(bf, client=NoModel()) == 2


def test_version_requires_course_and_unknown_selection_is_refused(bf, capsys):
    base_graph(bf)
    run(bf)
    assert main(bf, "--version", "1", client=NoModel()) == 2
    assert main(bf, "--course", bf.course, "--version", "9", client=NoModel()) == 2
    assert main(bf, "--course", "no-such-course", client=NoModel()) == 2
    assert main(bf, "--version", "x", client=NoModel()) == 2
    capsys.readouterr()


def test_course_without_committed_versions_is_a_no_op(bf, capsys):
    assert main(bf, "--course", bf.course, client=NoModel()) == 0
    assert main(bf, client=NoModel()) == 0


def test_model_failure_exits_1_without_leaking_details(bf, capsys):
    base_graph(bf)
    run(bf)
    strip(bf)

    class Down:
        def embed(self, request):
            raise RuntimeError("secret-bearing provider detail")

    assert main(bf, client=Down()) == 1
    err = capsys.readouterr().err
    assert "secret-bearing" not in err
    assert set(vectors(bf).values()) == {None}
