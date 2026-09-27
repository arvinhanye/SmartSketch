"""G08 遗留修复（ADR-055）：P9 只接受在线的文本块向量索引。仓储打桩，CI 覆盖。"""

from __future__ import annotations

import pytest

from app.repositories.graph_migrations import vector_property
from app.repositories.neo4j import GraphScope
from app.services.versions.chunk_vectors import _index_online

SPACE = "fake/4"


class StubRepo:
    def __init__(self, rows):
        self.rows, self.calls = rows, []

    def read(self, query, scope, *, reader, parameters=None):
        self.calls.append((query, scope, reader, dict(parameters or {})))
        return self.rows


@pytest.mark.parametrize("rows,online", [
    ([{"state": "ONLINE"}], True),
    ([{"state": "POPULATING"}], False),  # 刚建、尚未就绪
    ([{"state": "FAILED"}], False),
    ([], False),  # 未创建
])
def test_only_an_online_index_counts(rows, online):
    repo = StubRepo(rows)
    scope = GraphScope("c1", "01VERSION")
    assert _index_online(repo, scope, SPACE) is online
    [(query, used_scope, reader, parameters)] = repo.calls
    assert "SHOW VECTOR INDEXES" in query and (used_scope, reader) == (scope, "worker")
    assert parameters == {"index": "chunk_" + vector_property(SPACE)}
