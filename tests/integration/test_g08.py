"""G08 against a real Neo4j and a migrated SQLite: publishing indexes every text chunk of the version.

Acceptance: after a publish, every chunk of every revision in the version has a ``Chunk`` node with a
current-space vector, so J01 can find it; chunks already indexed are not embedded again; revisions
outside the version are left alone; a failure keeps the old pointer (ADR-047, V5 P8/P9).
"""

from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace

import pytest

from app.repositories.graph_migrations import GraphVectorWriter, VectorSpaceError, vector_property
from app.repositories.neo4j import GraphScope
from app.repositories.vector_search import search_chunks
from app.services.versions import chunk_vectors, publish as publishing
from app.services.versions.chunk_vectors import index_chunks, verify_chunks
from app.services.versions.materialize import VerificationError
from app.services.versions.publish import PublishFailed
from app.services.versions.resolver import clear_cache, resolve_published
from test_g04 import C0, C1, OTHER_REV, REV, SPACE, base_graph, embedder, env, live, pointer, run

pytestmark = live
__all__ = ["env"]  # 夹具取自 test_g04

C2 = f"{REV}-2"
PROP = vector_property(SPACE)


class SpyEmbedder:
    def __init__(self, fail_on=None):
        self.inner = embedder()
        self.space = self.inner.space
        self.texts: list[str] = []
        self.fail_on = fail_on

    def embed(self, texts):
        if self.fail_on is not None and any(self.fail_on in t for t in texts):
            raise RuntimeError("embedding service down")
        self.texts.extend(texts)
        return self.inner.embed(texts)


def sha(text):
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()


def add_chunk(env, chunk_id, ordinal, text, *, revision=REV):
    env.sql("INSERT INTO chunks (chunk_id, revision_id, course_id, material_id, ordinal, text, text_sha256, "
            "section_titles, sources) VALUES (?, ?, ?, 'm1', ?, ?, ?, '[]', ?)",
            chunk_id, revision, env.course, ordinal, text, sha(text),
            json.dumps([{"block_ordinal": 0, "start": 0, "end": 2, "locator": {"section_titles": [], "paragraph": 1}}]))


def add_revision(env, revision):
    env.sql("INSERT INTO material_revisions (revision_id, course_id, material_id, content_hash, parser_version) "
            "VALUES (?, ?, 'm1', ?, 'txt/1+chunk/1')", revision, env.course, sha(revision))


def indexed(env):
    rows = env.q(f"MATCH (c:Chunk {{course_id: $c}}) RETURN c.chunk_id AS id, c.revision_id AS rev, "
                 f"c.document_id AS doc, size(c.{PROP}) AS dims", c=env.course)
    return {r["id"]: (r["rev"], r["doc"], r["dims"]) for r in rows}


@pytest.fixture
def g08(env):
    GraphVectorWriter(env.repo._driver, lambda: SPACE).ensure_vector_indexes(SPACE)
    env.q("CALL db.awaitIndexes(60)")
    add_chunk(env, C2, 2, "没有被任何知识点引用的块")
    clear_cache()
    return env


def test_publish_indexes_every_chunk_of_the_version(g08):
    base_graph(g08)
    spy = SpyEmbedder()
    run(g08, embedder=spy)
    assert indexed(g08) == {c: (REV, "m1", 4) for c in (C0, C1, C2)}  # 未被引用的 C1、C2 也建节点并写向量
    assert {"块0", "块1", "没有被任何知识点引用的块"} <= set(spy.texts)


def test_already_indexed_chunks_are_not_embedded_again(g08):
    base_graph(g08)
    run(g08)
    g08.set_def("a", "新定义")
    spy = SpyEmbedder()
    run(g08, embedder=spy)
    assert not {"块0", "块1", "没有被任何知识点引用的块"} & set(spy.texts)  # 只重算知识点
    assert indexed(g08) == {c: (REV, "m1", 4) for c in (C0, C1, C2)}


def test_revisions_outside_the_version_are_left_alone(g08):
    add_revision(g08, OTHER_REV)
    add_chunk(g08, f"{OTHER_REV}-0", 0, "新修订的块", revision=OTHER_REV)
    base_graph(g08)
    spy = SpyEmbedder()
    run(g08, embedder=spy)
    assert f"{OTHER_REV}-0" not in indexed(g08)
    assert "新修订的块" not in spy.texts


def test_published_chunks_are_found_by_j01(g08):
    base_graph(g08)
    run(g08)
    bound = resolve_published(g08.url, g08.course)
    query = embedder().embed(["没有被任何知识点引用的块"])[0]
    hits = search_chunks(g08.repo, bound.graph_scope(), bound.revision_ids, query, space=SPACE, limit=3)
    assert hits[0].chunk_id == C2
    assert {h.chunk_id for h in hits} == {C0, C1, C2}


def test_embedding_failure_fails_the_publish_and_keeps_the_pointer(g08):
    base_graph(g08)
    first = run(g08)
    g08.set_def("a", "二版")
    add_revision(g08, OTHER_REV)
    add_chunk(g08, f"{OTHER_REV}-0", 0, "新资料的块", revision=OTHER_REV)
    g08.task("t2", "awaiting_review", 2, revision=OTHER_REV)
    with pytest.raises(PublishFailed) as caught:
        run(g08, embedder=SpyEmbedder(fail_on="新资料"))
    assert caught.value.step == "P8"
    assert pointer(g08)[:2] == (first.version_id, 1)


def test_verify_catches_a_chunk_without_a_vector(g08, monkeypatch):
    base_graph(g08)
    real = chunk_vectors.index_chunks

    def skip_one(*args, **kwargs):
        result = real(*args, **kwargs)
        g08.q(f"MATCH (c:Chunk {{course_id: $c, chunk_id: $id}}) REMOVE c.{PROP}", c=g08.course, id=C2)
        return result

    monkeypatch.setattr(publishing, "index_chunks", skip_one)
    with pytest.raises(PublishFailed) as caught:
        run(g08)
    assert caught.value.step == "P9"
    assert pointer(g08)[0] is None


def test_index_chunks_is_idempotent_and_batches(g08):
    base_graph(g08)
    scope = GraphScope(g08.course, "01VERSION")
    spy = SpyEmbedder()
    first = index_chunks(g08.url, g08.repo, spy, scope, [REV], SPACE, batch_size=2)
    assert (first.total, first.embedded) == (3, 3)
    again = index_chunks(g08.url, g08.repo, spy, scope, [REV], SPACE, batch_size=2)
    assert (again.total, again.embedded) == (3, 0)
    assert len(spy.texts) == 3
    verify_chunks(g08.url, g08.repo, scope, [REV], SPACE)
    assert index_chunks(g08.url, g08.repo, spy, scope, [], SPACE).total == 0


def test_wrong_dimensions_are_repaired_and_verified(g08):
    base_graph(g08)
    scope = GraphScope(g08.course, "01VERSION")
    index_chunks(g08.url, g08.repo, embedder(), scope, [REV], SPACE)
    g08.q(f"MATCH (c:Chunk {{course_id: $c, chunk_id: $id}}) SET c.{PROP} = [1.0, 2.0]", c=g08.course, id=C1)
    with pytest.raises(VerificationError):
        verify_chunks(g08.url, g08.repo, scope, [REV], SPACE)
    assert index_chunks(g08.url, g08.repo, embedder(), scope, [REV], SPACE).embedded == 1
    verify_chunks(g08.url, g08.repo, scope, [REV], SPACE)


def test_embedder_in_another_space_is_refused(g08):
    base_graph(g08)
    other = SimpleNamespace(space="fake/8", embed=lambda texts: pytest.fail("must not embed"))
    with pytest.raises(VectorSpaceError):
        index_chunks(g08.url, g08.repo, other, GraphScope(g08.course, "01VERSION"), [REV], SPACE)


def test_node_with_a_vector_but_no_revision_is_repaired(g08):  # J01 按 revision_id 过滤
    base_graph(g08)
    scope = GraphScope(g08.course, "01VERSION")
    index_chunks(g08.url, g08.repo, embedder(), scope, [REV], SPACE)
    g08.q("MATCH (c:Chunk {course_id: $c, chunk_id: $id}) REMOVE c.revision_id", c=g08.course, id=C1)
    with pytest.raises(VerificationError):
        verify_chunks(g08.url, g08.repo, scope, [REV], SPACE)
    assert index_chunks(g08.url, g08.repo, embedder(), scope, [REV], SPACE).embedded == 1
    assert indexed(g08)[C1] == (REV, "m1", 4)
