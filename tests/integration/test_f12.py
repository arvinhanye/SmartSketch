"""F12：删除（F09）与合并（F10）的图编辑审计（``app.services.graph.audit``；ADR-061）。

两者都在一个 Neo4j 写事务里执行，``draft_revision + 1`` 与 ``pending`` 审计行在事务内的校验通过后写入，
所以这里连真实 Neo4j 5.26 + 真实 SQLite 验证：谁/何时/何版本/摘要齐全；事务内失败记 ``aborted``；
审计更新失败后下一次写入持锁对账补齐；合并的直接父子关系只在审计里（ADR-012 修订 3）。

只在设置 ``SMARTSKETCH_TEST_NEO4J_URI/USER/PASSWORD`` 时运行；夹具沿用 ``test_f09``。
"""

from __future__ import annotations

import dataclasses
import sqlite3

import pytest

from app.repositories import edit_logs, graph_edit
from app.services.access import AccessDenied
from app.services.graph import audit
from app.services.graph.delete_node import delete_node
from app.services.graph.edit_node import RevisionConflict, update_node
from app.services.graph.merge_nodes import merge_nodes
from app.services.graph.relations import CycleDetectedError
from test_f09 import _draft_revision, env, live  # noqa: F401  (shared live fixture)


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch):
    monkeypatch.setattr(audit, "_sleep", lambda seconds: None)


def _ctx(env):
    return dataclasses.replace(env.ctx, actor_id=env.teacher.id)


def _logs(env):
    return edit_logs.list_logs(env.url, env.course)


@live
def test_delete_is_logged_with_actor_versions_and_relation_count(env):
    g = env.g
    for kp in ("a", "x", "y"):
        g.node(kp)
    g.node("m", revision=3)
    g.edge("PREREQUISITE", "m", "x")
    g.edge("RELATED_TO", "y", "m")
    before = _draft_revision(env)

    delete_node(_ctx(env), env.course, "m", 3)

    [entry] = _logs(env)
    assert (entry.action, entry.kp_id, entry.state, entry.resolved_by) == ("delete", "m", "committed", "writer")
    assert entry.actor_id == env.teacher.id and entry.draft_revision == before + 1 == _draft_revision(env)
    assert (entry.kp_revision_before, entry.kp_revision_after) == (3, None)
    assert entry.summary == {"fields": {"name": "M", "aliases": [], "type": "concept", "definition": "m 的定义",
                                        "status": "draft"},
                             "locked": False, "relations_deleted": 2}
    assert entry.created_at <= entry.resolved_at


@live
def test_rejected_delete_writes_no_log(env):
    env.g.node("a", revision=2)
    with pytest.raises(RevisionConflict):
        delete_node(_ctx(env), env.course, "a", 1)
    with pytest.raises(AccessDenied):
        delete_node(_ctx(env), env.course, "missing")
    assert _logs(env) == []


@live
def test_merge_records_direct_children_and_flattened_lineage(env):
    g = env.g
    for kp in ("a", "b", "c", "x"):
        g.node(kp)
    g.edge("PREREQUISITE", "a", "x")
    g.edge("PREREQUISITE", "b", "x")
    g.evidence("a", "ch-1")

    merge_nodes(_ctx(env), env.course, "b", ["a"])
    merged = merge_nodes(_ctx(env), env.course, "c", ["b"])

    first, second = _logs(env)
    assert (first.action, first.kp_id, first.state) == ("merge", "b", "committed")
    assert first.summary["merged"] == [{"kp_id": "a", "name": "A", "revision": 1}]
    assert first.summary["merged_from"] == ["a"]
    assert (first.summary["relations_removed"], first.summary["relations_created"],
            first.summary["evidence_moved"]) == (2, 1, 1)
    assert (first.kp_revision_before, first.kp_revision_after) == (1, 2)
    # 第二次合并：直接子节点只有 b；展平谱系含 a、b（ADR-012 修订 3，决定 15）
    assert second.summary["primary"] == {"kp_id": "c", "name": "C"}
    assert [m["kp_id"] for m in second.summary["merged"]] == ["b"]
    assert second.summary["merged_from"] == ["a", "b"]
    assert (second.kp_revision_before, second.kp_revision_after) == (1, merged.revision)
    assert [e.draft_revision for e in (first, second)] == [_draft_revision(env) - 1, _draft_revision(env)]
    assert {e.actor_id for e in (first, second)} == {env.teacher.id}


@live
def test_merge_rejected_before_any_write_is_not_logged(env):
    g = env.g
    for kp in ("a", "b", "x"):
        g.node(kp)
    g.edge("PREREQUISITE", "a", "x")
    g.edge("PREREQUISITE", "x", "b")
    with pytest.raises(CycleDetectedError):
        merge_nodes(_ctx(env), env.course, "a", ["b"])
    with pytest.raises(RevisionConflict):
        merge_nodes(_ctx(env), env.course, "a", ["x"], {"x": 9})
    assert _logs(env) == []


@live
def test_failure_inside_the_merge_transaction_is_logged_as_aborted(env, monkeypatch):
    g = env.g
    for kp in ("a", "b"):
        g.node(kp)
    before_graph = g.dump("draft")

    def broken(tx, *, removed, created):
        raise RuntimeError("boom")

    monkeypatch.setattr(graph_edit, "replace_relations", broken)
    with pytest.raises(RuntimeError):
        merge_nodes(_ctx(env), env.course, "a", ["b"])

    [entry] = _logs(env)
    assert (entry.state, entry.failure_reason, entry.kp_revision_after) == ("aborted", "RuntimeError", None)
    assert entry.draft_revision == _draft_revision(env)
    assert g.dump("draft") == before_graph   # Neo4j rolled back


@live
def test_failure_inside_the_delete_transaction_is_logged_as_aborted(env, monkeypatch):
    env.g.node("a")

    def broken(tx, kp_id, expected_revision):
        raise RuntimeError("boom")

    monkeypatch.setattr(graph_edit, "delete_draft_node", broken)
    with pytest.raises(RuntimeError):
        delete_node(_ctx(env), env.course, "a")

    [entry] = _logs(env)
    assert (entry.action, entry.state, entry.failure_reason) == ("delete", "aborted", "RuntimeError")
    assert env.g.props("a") is not None


def _unresolvable(monkeypatch):
    real = edit_logs.resolve

    def fail(*args, **kwargs):
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(edit_logs, "resolve", fail)
    return real


@live
def test_merge_whose_audit_update_failed_is_reconciled_as_committed_by_the_next_edit(env, monkeypatch):
    g = env.g
    for kp in ("a", "b", "z"):
        g.node(kp)
    real = _unresolvable(monkeypatch)

    merged = merge_nodes(_ctx(env), env.course, "a", ["b"])   # Neo4j committed; the edit still succeeds
    assert merged.revision == 2 and g.props("b") is None
    [pending] = edit_logs.pending(env.url, env.course)

    monkeypatch.setattr(edit_logs, "resolve", real)
    update_node(_ctx(env), env.course, "z", 1, {"name": "Z2"})   # any later write reconciles first

    first, second = _logs(env)
    assert (first.event_id, first.state, first.resolved_by, first.kp_revision_after) == (
        pending.event_id, "committed", "reconcile", 2)
    assert first.summary["merged"] == [{"kp_id": "b", "name": "B", "revision": 1}]
    assert first.summary["merged_from"] == ["b"]   # recorded at begin, before the counts were known
    assert (second.action, second.state) == ("update", "committed")


@live
def test_delete_whose_audit_update_failed_is_reconciled_as_committed(env, monkeypatch):
    for kp in ("a", "z"):
        env.g.node(kp)
    real = _unresolvable(monkeypatch)
    delete_node(_ctx(env), env.course, "a")
    monkeypatch.setattr(edit_logs, "resolve", real)

    delete_node(_ctx(env), env.course, "z")

    first, second = _logs(env)
    assert (first.kp_id, first.state, first.resolved_by) == ("a", "committed", "reconcile")
    assert (second.kp_id, second.state, second.resolved_by) == ("z", "committed", "writer")
