"""D2（ADR-082 决定 6）：发布的文本块与知识点向量每次实际请求各记一行 ``model_calls``，归属本课程与
``publish:<version_id>``；内容未变的重复发布与回滚复制向量不调用供应商、不新增行。需要一次性 Neo4j。"""
from __future__ import annotations

from app.config import Settings
from app.repositories.model_calls import EMBEDDING_PURPOSE, SqliteCallStore
from app.repositories.sqlite import connect
from app.services.ai.embeddings import EmbeddingAdapter
from app.services.ai.fake import FakeEmbeddingClient
from app.services.versions.rollback import rollback
from test_g04 import base_graph, env, run  # noqa: F401  (fixture)


def _recording_embedder(url):
    settings = Settings(EMBEDDING_MODE="fake", EMBEDDING_MODEL="", EMBEDDING_DIMENSIONS=4, EMBEDDING_BATCH_SIZE=8)
    return EmbeddingAdapter(settings, FakeEmbeddingClient(), store=SqliteCallStore(url))


def _vector_rows(url):
    with connect(url) as database:
        return database.execute("SELECT course_id, request_id, status, task_id FROM model_calls WHERE purpose = ?",
                                (EMBEDDING_PURPOSE,)).fetchall()


def test_publish_records_vector_calls_and_rollback_records_none(env):
    base_graph(env)
    embedder = _recording_embedder(env.url)
    first = run(env, embedder=embedder)
    rows = _vector_rows(env.url)
    assert rows, "publish embedded chunks and nodes"
    assert {row[:2] for row in rows} == {(env.course, f"publish:{first.version_id}")}
    assert all(row[2] == "ok" and row[3] is None for row in rows)

    again = run(env, embedder=embedder)                       # 内容未变：不再向量化
    assert again.unchanged and len(_vector_rows(env.url)) == len(rows)

    env.set_def("a", "新的定义")
    second = run(env, embedder=embedder)
    assert second.version == first.version + 1
    after_second = _vector_rows(env.url)
    assert len(after_second) > len(rows)

    from app.services.versions.publish import PublishContext
    ctx = PublishContext(**{**env.ctx.__dict__, "embedder": embedder})
    rollback(ctx, env.course, first.version, created_by=env.teacher.id)   # 复制已有向量
    assert len(_vector_rows(env.url)) == len(after_second)
