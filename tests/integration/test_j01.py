"""J01 against a real Neo4j: vector search over the shared ``Chunk`` vectors of a published version.

Acceptance: scope by course and by the bound version's revision list, over-fetching until recall is
filled; chunks of other courses or of revisions outside the version never come back
(specs/teacher-review-publish.md V8「向量检索」, specs/grounded-qa.md Q3.1 conditions 1–2, ADR-046).
"""

from __future__ import annotations

import logging
import math
import os
import uuid
from types import SimpleNamespace

import pytest

from app.repositories.graph_migrations import GraphVectorWriter, VectorSpaceError, apply_migrations, vector_property
from app.repositories.neo4j import GraphScope, GraphScopeError, Neo4jRepository, RepositoryError
from app.repositories.vector_search import ChunkHit, search_chunks

_ENV = ("SMARTSKETCH_TEST_NEO4J_URI", "SMARTSKETCH_TEST_NEO4J_USER", "SMARTSKETCH_TEST_NEO4J_PASSWORD")
pytestmark = pytest.mark.skipif(not all(os.environ.get(n) for n in _ENV),
                                reason="isolated Neo4j fixture not configured")

SPACE = "fake/4"
REV1, REV2, NEW_REV = "rev_" + "1" * 64, "rev_" + "2" * 64, "rev_" + "9" * 64


def vec(*values, space=SPACE):
    return SimpleNamespace(space=space, values=list(values))


def angle(degrees):
    """Unit vector at ``degrees`` from the query ``(1, 0, 0, 0)`` in the first plane."""
    radians = math.radians(degrees)
    return [math.cos(radians), math.sin(radians), 0.0, 0.0]


QUERY = vec(1.0, 0.0, 0.0, 0.0)


class Env:
    def __init__(self, driver):
        self.driver = driver
        self.repo = Neo4jRepository(driver)
        self.course = "c_" + uuid.uuid4().hex
        self.other = "c_" + uuid.uuid4().hex
        self.prop = vector_property(SPACE)

    def q(self, query, **params):
        return [dict(r) for r in self.driver.execute_query(query, parameters_=params, routing_="w",
                                                           database_="neo4j").records]

    def chunk(self, chunk_id, degrees, *, course=None, revision=REV1, vector=None):
        self.q(f"CREATE (c:Chunk {{course_id: $c, chunk_id: $id, document_id: 'm1', revision_id: $r}}) "
               f"SET c.{self.prop} = $v",
               c=course or self.course, id=chunk_id, r=revision, v=vector or angle(degrees))

    def scope(self, course=None):
        return GraphScope(course or self.course, "01VERSION")

    def search(self, *, revisions=(REV1, REV2), course=None, vector=QUERY, space=SPACE, limit=3, **kwargs):
        return search_chunks(self.repo, self.scope(course), frozenset(revisions), vector, space=space,
                             limit=limit, **kwargs)


@pytest.fixture
def env():
    neo4j = pytest.importorskip("neo4j")
    driver = neo4j.GraphDatabase.driver(os.environ[_ENV[0]], auth=(os.environ[_ENV[1]], os.environ[_ENV[2]]))
    apply_migrations(driver)
    GraphVectorWriter(driver, lambda: SPACE).ensure_vector_indexes(SPACE)
    driver.execute_query("CALL db.awaitIndexes(60)", database_="neo4j")
    state = Env(driver)
    try:
        yield state
    finally:
        state.q("MATCH (c:Chunk) WHERE c.course_id IN $ids DETACH DELETE c", ids=[state.course, state.other])
        driver.close()


def ids(hits):
    return [h.chunk_id for h in hits]


def test_hits_are_ranked_limited_and_carry_their_revision(env):
    for n, degrees in enumerate((40, 10, 70, 25)):
        env.chunk(f"k{n}", degrees, revision=REV1 if n % 2 else REV2)
    hits = env.search(limit=3)
    assert ids(hits) == ["k1", "k3", "k0"]
    assert all(isinstance(h, ChunkHit) for h in hits)
    assert (hits[0].revision_id, hits[0].document_id) == (REV1, "m1")
    assert hits[0].score > hits[1].score > hits[2].score
    assert hits[0].score == pytest.approx((1 + math.cos(math.radians(10))) / 2, abs=2e-3)  # 余弦归一到 [0, 1]；索引近似（量化）


def test_other_courses_and_revisions_outside_the_version_never_come_back(env):
    env.chunk("mine", 30)
    env.chunk("foreign", 0, course=env.other)  # 他课，与问题完全同向
    env.chunk("newer", 0, revision=NEW_REV)  # 同课，版本之外的新修订
    assert ids(env.search(limit=5)) == ["mine"]
    assert ids(env.search(course=env.other, revisions=(REV1,), limit=5)) == ["foreign"]
    assert ids(env.search(revisions=(NEW_REV,), limit=5)) == ["newer"]


def test_recall_is_topped_up_past_nearer_foreign_chunks(env):
    for n in range(30):  # 30 个更近的他课 / 版本外文本块挤在前面
        env.chunk(f"f{n}", 1 + n * 0.1, course=env.other if n % 2 else None, revision=REV1 if n % 2 else NEW_REV)
    for n, degrees in enumerate((50, 55, 60)):
        env.chunk(f"own{n}", degrees)
    hits = env.search(limit=3, fetch_factor=2, max_fetch=200)
    assert ids(hits) == ["own0", "own1", "own2"]


def test_fetch_cap_returns_what_it_has_and_warns(env, caplog):
    for n in range(10):
        env.chunk(f"f{n}", 1 + n, course=env.other)
    env.chunk("own", 60)
    with caplog.at_level(logging.WARNING, logger="app.repositories.vector_search"):
        assert env.search(limit=2, fetch_factor=2, max_fetch=8) == ()
    assert "max_fetch" in caplog.text
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="app.repositories.vector_search"):
        assert ids(env.search(limit=2, fetch_factor=2, max_fetch=1000)) == ["own"]  # 索引取尽，不是封顶
    assert "max_fetch" not in caplog.text


def test_no_match_or_empty_revision_list_is_empty(env):
    assert env.search() == ()
    env.chunk("own", 10)
    assert env.search(revisions=()) == ()


def test_chunks_without_a_vector_in_this_space_are_skipped(env):
    env.q("CREATE (:Chunk {course_id: $c, chunk_id: 'bare', document_id: 'm1', revision_id: $r})",
          c=env.course, r=REV1)
    env.chunk("own", 20)
    assert ids(env.search()) == ["own"]


@pytest.mark.parametrize("vector,space,error", [
    (vec(1.0, 0.0, 0.0, 0.0, space="fake/8"), SPACE, VectorSpaceError),  # 查询向量不在当前空间
    (vec(1.0, 0.0, 0.0), SPACE, VectorSpaceError),  # 维度不符
    (vec(1.0, math.nan, 0.0, 0.0), SPACE, VectorSpaceError),
    (vec(1.0, 0.0, 0.0, 0.0, space="bogus"), "bogus", VectorSpaceError),
])
def test_bad_query_vectors_are_rejected_before_querying(env, vector, space, error):
    with pytest.raises(error):
        env.search(vector=vector, space=space)


@pytest.mark.parametrize("kwargs", [{"limit": 0}, {"limit": True}, {"fetch_factor": 0}, {"max_fetch": 1}])
def test_bad_bounds_are_rejected(env, kwargs):
    with pytest.raises(ValueError):
        env.search(**{"limit": 3, **kwargs})


def test_draft_scope_is_refused(env):
    with pytest.raises(GraphScopeError):
        search_chunks(env.repo, GraphScope(env.course, "draft", effective_task_ids=()), frozenset({REV1}), QUERY,
                      space=SPACE, limit=3)


def test_missing_index_for_the_space_is_a_repository_error(env):
    with pytest.raises(RepositoryError):
        space = "real/j01-no-index/3"  # 没有为该空间建索引
        env.search(vector=vec(1.0, 0.0, 0.0, space=space), space=space)
