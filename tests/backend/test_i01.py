"""I01 学习进度仓储，连真实迁移后的 SQLite（specs/learning-path.md §5，ADR-014 修订 1，ADR-012 修订 3，ADR-049）。

验收：用户/课程隔离；重复写幂等（同值写入按 A08S-R01 判定）；未知节点（草稿独有、已删除、他课、
从未存在）整批拒绝、零写入；版本迁移按 A08 §5 读时投影（改名保留、删除 dormant、合并继承与显式写入
覆盖、回滚重现、链式合并、LP-8/9/17/18/19/20）。版本由 G01 ``build_snapshot`` 生成、G02 仓储提交，
学生请求按 G07 ``resolve_published`` 绑定。
"""

from __future__ import annotations

import logging
import sqlite3
import uuid

import pytest

from app.repositories import progress, versions
from app.repositories.accounts import insert_account
from app.repositories.courses import create_course
from app.repositories.progress import (
    InheritedSource,
    ProgressEntry,
    ProgressNotInPublishedVersion,
    ProgressValidationError,
    project_progress,
    read_rows,
    write_progress,
)
from app.repositories.sqlite import MIGRATIONS_DIR, connect, migrate
from app.services.access import AccessDenied
from app.services.versions import resolver
from app.services.versions.resolver import VersionIntegrityError, resolve_published
from app.services.versions.snapshot import (
    DraftGraph,
    DraftNode,
    Revision,
    build_snapshot,
    canonical_bytes,
    digest_of,
)

VALID_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA"
LEASE = 60
EXCLUDED = {"low_confidence_nodes": 0, "low_confidence_edges": 0, "cascaded_edges": 0}


@pytest.fixture(autouse=True)
def fresh_cache():
    resolver.clear_cache()
    progress.clear_cache()
    yield
    resolver.clear_cache()
    progress.clear_cache()


def account(url, name, role="student"):
    return insert_account(url, account_id=uuid.uuid4().hex, username=name, password_hash=VALID_HASH, role=role).id


@pytest.fixture
def env(tmp_path):
    url = f"sqlite:///{(tmp_path / 'state.sqlite3').as_posix()}"
    migrate(url)
    teacher = account(url, "teacher1", "teacher")
    course = create_course(url, name="A", description=None, creator_id=teacher).id
    other = create_course(url, name="B", description=None, creator_id=teacher).id
    return url, teacher, course, other, account(url, "alice"), account(url, "bob")


# --- helpers -------------------------------------------------------------------------------------


def snapshot_for(course_id, nodes):
    """``nodes``：``{kp_id: merged_from}`` 或 ``{kp_id: (merged_from, name)}``。"""
    rev = Revision("rev-a", "mat-a", "sha256:" + "a" * 64, "txt/1+chunk/1@1500-200")
    draft_nodes = []
    for kp_id, spec in nodes.items():
        merged, name = spec if len(spec) == 2 and isinstance(spec[0], tuple) else (spec, f"name-{kp_id}")
        draft_nodes.append(DraftNode(kp_id=kp_id, name=name, type="concept", definition="d", status="approved",
                                     source_refs=("ch-a",), merged_from=tuple(merged)))
    draft = DraftGraph(course_id, [rev], [], draft_nodes, [], {"ch-a": "rev-a"})
    return build_snapshot(draft).snapshot


def pointer_id(url, course_id):
    with connect(url) as db:
        return db.execute("SELECT published_version_id FROM courses WHERE id = ?", (course_id,)).fetchone()[0]


def commit_raw(url, course_id, teacher, raw: bytes, digest: str, node_count: int):
    attempt = versions.begin_attempt(url, course_id, kind="publish", created_by=teacher, lease_seconds=LEASE)
    assert versions.record_snapshot(url, attempt.version_id, snapshot=raw, digest=digest, node_count=node_count,
                                    edge_count=0, excluded=EXCLUDED, draft_revision=1, task_watermark=0,
                                    embedding_space="bge-m3@1024")
    assert versions.mark_materialized(url, attempt.version_id)
    with versions.immediate(url) as db:
        return versions.commit_attempt(db, attempt.version_id, expected_pointer=pointer_id(url, course_id),
                                       published_from_revision=1)


def publish(url, course_id, teacher, nodes):
    snap = snapshot_for(course_id, nodes)
    return commit_raw(url, course_id, teacher, snap.canonical, snap.digest, len(nodes))


def rollback(url, course_id, teacher, source_version):
    attempt = versions.begin_attempt(url, course_id, kind="rollback", created_by=teacher, lease_seconds=LEASE,
                                     source_version=source_version)
    assert versions.mark_materialized(url, attempt.version_id)
    with versions.immediate(url) as db:
        return versions.commit_attempt(db, attempt.version_id, expected_pointer=pointer_id(url, course_id),
                                       published_from_revision=1)


def sql(url, statement, *params):
    with connect(url) as db:
        return db.execute(statement, params).fetchall()


def seq_value(url):
    return sql(url, "SELECT value FROM commit_sequence")[0][0]


def raw_rows(url):
    return sql(url, "SELECT user_id, course_id, kp_id, status, write_seq, updated_at FROM learning_progress "
                    "ORDER BY user_id, course_id, kp_id")


def view(url, user, course, version=None):
    return project_progress(url, user, resolve_published(url, course, version=version))


def by_kp(result):
    return {entry.kp_id: entry for entry in result.entries}


def status_of(result):
    return {entry.kp_id: entry.status for entry in result.entries}


def put(url, user, course, *items):
    return write_progress(url, user, course, [{"kp_id": k, "status": s} for k, s in items])


# --- migration ----------------------------------------------------------------------------------


def test_migration_011_creates_the_progress_table(env):
    url, *_ = env
    columns = [row[1] for row in sql(url, "PRAGMA table_info(learning_progress)")]
    assert columns == ["user_id", "course_id", "kp_id", "status", "write_seq", "updated_at"]
    assert sql(url, "SELECT filename FROM schema_migrations WHERE version = '011'") == [("011_progress.sql",)]


def test_table_constraints_reject_bad_rows(env):
    url, teacher, course, _, alice, _ = env
    good = (alice, course, "kp-a", "mastered", 1)
    insert = "INSERT INTO learning_progress (user_id, course_id, kp_id, status, write_seq) VALUES (?, ?, ?, ?, ?)"
    for bad in [(alice, course, "kp-a", "skipped", 1), (alice, course, "", "mastered", 1),
                (alice, course, "kp-a", "mastered", 0), ("ghost-user", course, "kp-a", "mastered", 1),
                (alice, "ghost-course", "kp-a", "mastered", 1)]:
        with pytest.raises(sqlite3.IntegrityError):
            sql(url, insert, *bad)
    sql(url, insert, *good)
    with pytest.raises(sqlite3.IntegrityError):  # 主键 (user_id, course_id, kp_id)
        sql(url, insert, alice, course, "kp-a", "learning", 2)


def test_migration_011_rolls_back_and_reapplies(env):
    url, teacher, course, _, alice, _ = env
    target = next(MIGRATIONS_DIR.glob("*_progress.sql"))

    def rollback_lines(path):
        text = path.read_text(encoding="utf-8")
        return [line.split("ROLLBACK:", 1)[1].strip() for line in text.splitlines() if "ROLLBACK:" in line]

    assert rollback_lines(target)
    publish(url, course, teacher, {"kp-a": ()})
    before = seq_value(url)
    later = sorted((p for p in MIGRATIONS_DIR.glob("*.sql") if p.name > target.name), reverse=True)
    database = sqlite3.connect(url.removeprefix("sqlite:///"))
    try:
        with database:
            for path in [*later, target]:
                for line in rollback_lines(path):
                    database.execute(line)
        names = {row[0] for row in database.execute("SELECT name FROM sqlite_master")}
        assert "learning_progress" not in names
        assert "commit_sequence" in names and "graph_versions" in names  # G02 的表不受影响
    finally:
        database.close()
    migrate(url)
    assert seq_value(url) == before
    assert put(url, alice, course, ("kp-a", "mastered")).view.entries[0].status == "mastered"


# --- 写入与读取 -----------------------------------------------------------------------------------


def test_write_returns_every_node_of_the_bound_version(env):
    url, teacher, course, _, alice, _ = env
    v1 = publish(url, course, teacher, {"kp-a": (), "kp-b": (), "kp-c": ()})
    result = put(url, alice, course, ("kp-b", "mastered"), ("kp-a", "learning"))
    assert (result.view.course_id, result.view.version_id, result.view.graph_version) == (course, v1.version_id, 1)
    entries = by_kp(result.view)
    assert list(entries) == ["kp-a", "kp-b", "kp-c"]
    assert entries["kp-b"].status == entries["kp-b"].own_status == "mastered"
    assert entries["kp-a"].status == "learning"
    assert entries["kp-c"] == ProgressEntry("kp-c", "unknown", None, (), None)
    assert entries["kp-b"].updated_at is not None
    assert result.written == ("kp-a", "kp-b")
    assert result.view.mastered == frozenset({"kp-b"})
    assert result.view.to_dict()["entries"][2] == {"kp_id": "kp-c", "status": "unknown", "own_status": None,
                                                   "inherited_from": [], "updated_at": None}
    assert view(url, alice, course) == result.view


def test_one_write_transaction_takes_one_number_from_the_shared_sequence(env):
    url, teacher, course, _, alice, _ = env
    v1 = publish(url, course, teacher, {"kp-a": (), "kp-b": ()})
    assert v1.commit_seq == 1
    result = put(url, alice, course, ("kp-a", "mastered"), ("kp-b", "learning"))
    assert result.write_seq == 2 and seq_value(url) == 2
    assert {row[2]: row[4] for row in raw_rows(url)} == {"kp-a": 2, "kp-b": 2}
    v2 = publish(url, course, teacher, {"kp-a": (), "kp-b": ()})
    assert v2.commit_seq == 3
    assert put(url, alice, course, ("kp-a", "learning")).write_seq == 4


def test_users_are_isolated(env):
    url, teacher, course, _, alice, bob = env
    publish(url, course, teacher, {"kp-a": (), "kp-b": ()})
    put(url, alice, course, ("kp-a", "mastered"))
    put(url, bob, course, ("kp-a", "learning"), ("kp-b", "mastered"))
    assert status_of(view(url, alice, course)) == {"kp-a": "mastered", "kp-b": "unknown"}
    assert status_of(view(url, bob, course)) == {"kp-a": "learning", "kp-b": "mastered"}
    assert set(read_rows(url, alice, course)) == {"kp-a"}
    assert read_rows(url, alice, course)["kp-a"].status == "mastered"


def test_courses_are_isolated(env):
    url, teacher, course, other, alice, _ = env
    publish(url, course, teacher, {"kp-a": ()})
    publish(url, other, teacher, {"kp-z": ()})
    put(url, alice, course, ("kp-a", "mastered"))
    assert read_rows(url, alice, other) == {}
    assert status_of(view(url, alice, other)) == {"kp-z": "unknown"}
    # 他课节点写入本课程：不在本课程发布版中，整批拒绝
    with pytest.raises(ProgressNotInPublishedVersion):
        put(url, alice, course, ("kp-z", "mastered"))
    with pytest.raises(ProgressNotInPublishedVersion):
        put(url, alice, other, ("kp-a", "mastered"))
    assert [row[1:4] for row in raw_rows(url)] == [(course, "kp-a", "mastered")]


def test_a_foreign_row_with_the_same_kp_id_in_another_course_does_not_leak(env):
    url, teacher, course, other, alice, _ = env
    publish(url, course, teacher, {"kp-same": ()})
    publish(url, other, teacher, {"kp-same": ()})
    put(url, alice, other, ("kp-same", "mastered"))
    assert status_of(view(url, alice, course)) == {"kp-same": "unknown"}
    assert status_of(view(url, alice, other)) == {"kp-same": "mastered"}


# --- 幂等 -----------------------------------------------------------------------------------------


def test_repeating_the_same_write_is_a_no_op(env):
    url, teacher, course, _, alice, _ = env
    publish(url, course, teacher, {"kp-a": (), "kp-b": ()})
    first = put(url, alice, course, ("kp-a", "mastered"), ("kp-b", "unknown"))
    rows, seq = raw_rows(url), seq_value(url)
    second = put(url, alice, course, ("kp-a", "mastered"), ("kp-b", "unknown"))
    assert second.written == () and second.write_seq is None
    assert raw_rows(url) == rows and seq_value(url) == seq
    assert second.view == first.view


def test_writing_unknown_to_a_node_without_a_row_creates_the_row(env):
    url, teacher, course, _, alice, _ = env
    publish(url, course, teacher, {"kp-a": ()})
    result = put(url, alice, course, ("kp-a", "unknown"))
    assert result.written == ("kp-a",)
    entry = by_kp(result.view)["kp-a"]
    assert (entry.status, entry.own_status) == ("unknown", "unknown") and entry.updated_at is not None
    assert put(url, alice, course, ("kp-a", "unknown")).written == ()


def test_changing_the_status_takes_a_new_number_and_refreshes_updated_at(env):
    url, teacher, course, _, alice, _ = env
    publish(url, course, teacher, {"kp-a": ()})
    put(url, alice, course, ("kp-a", "mastered"))
    [(_, _, _, _, seq1, _)] = raw_rows(url)
    result = put(url, alice, course, ("kp-a", "learning"))
    [(_, _, _, status, seq2, _)] = raw_rows(url)
    assert status == "learning" and seq2 > seq1 and result.write_seq == seq2


def test_partial_repeat_writes_only_the_changed_items(env):
    url, teacher, course, _, alice, _ = env
    publish(url, course, teacher, {"kp-a": (), "kp-b": ()})
    put(url, alice, course, ("kp-a", "mastered"))
    before = {row[2]: row for row in raw_rows(url)}
    result = put(url, alice, course, ("kp-a", "mastered"), ("kp-b", "learning"))
    after = {row[2]: row for row in raw_rows(url)}
    assert result.written == ("kp-b",)
    assert after["kp-a"] == before["kp-a"]


# --- 校验与拒绝（零写入） -------------------------------------------------------------------------


@pytest.mark.parametrize("batch", [
    [],
    [{"kp_id": "kp-a", "status": "skipped"}],
    [{"kp_id": "", "status": "mastered"}],
    [{"kp_id": 7, "status": "mastered"}],
    [{"kp_id": "kp-a"}],
    [{"kp_id": "kp-a", "status": "mastered", "user_id": "someone"}],
    [{"kp_id": "kp-a", "status": "mastered"}, {"kp_id": "kp-a", "status": "learning"}],
    [{"kp_id": "kp-b", "status": "mastered"}, "kp-a"],
])
def test_malformed_or_duplicate_batches_write_nothing(env, batch):
    url, teacher, course, _, alice, _ = env
    publish(url, course, teacher, {"kp-a": (), "kp-b": ()})
    seq = seq_value(url)
    with pytest.raises(ProgressValidationError):
        write_progress(url, alice, course, batch)
    assert raw_rows(url) == [] and seq_value(url) == seq


def test_unknown_nodes_reject_the_whole_batch_with_indices(env):
    url, teacher, course, other, alice, _ = env
    publish(url, course, teacher, {"kp-a": (), "kp-b": ()})
    publish(url, course, teacher, {"kp-a": ()})  # v2 删除 kp-b
    publish(url, other, teacher, {"kp-z": ()})
    seq = seq_value(url)
    with pytest.raises(ProgressNotInPublishedVersion) as caught:
        put(url, alice, course, ("kp-a", "mastered"), ("kp-b", "mastered"), ("kp-draft-only", "learning"),
            ("kp-z", "mastered"))
    error = caught.value
    assert error.code == "VALIDATION_ERROR"
    assert error.indices == (1, 2, 3) and error.graph_version == 2
    assert error.details() == {"fields": [{"in": "body", "field": f"{i}.kp_id",
                                           "reason": "not_in_published_version"} for i in (1, 2, 3)],
                               "graph_version": 2}
    assert raw_rows(url) == [] and seq_value(url) == seq


def test_writing_to_an_unpublished_or_missing_course_is_refused(env):
    url, teacher, course, _, alice, _ = env
    with pytest.raises(AccessDenied) as caught:
        put(url, alice, course, ("kp-a", "mastered"))
    assert (caught.value.status_code, caught.value.code) == (404, "GRAPH_NOT_PUBLISHED")
    with pytest.raises(AccessDenied) as caught:
        put(url, alice, "no-such-course", ("kp-a", "mastered"))
    assert (caught.value.status_code, caught.value.code) == (404, "NOT_FOUND")
    assert raw_rows(url) == []


def test_write_binds_to_the_pointer_seen_inside_its_transaction(env):
    url, teacher, course, _, alice, _ = env
    publish(url, course, teacher, {"kp-a": (), "kp-b": ()})
    stale = resolve_published(url, course)  # 请求开始时解析到 v1
    publish(url, course, teacher, {"kp-a": (), "kp-c": ()})  # 途中提交 v2，删 kp-b
    with pytest.raises(ProgressNotInPublishedVersion) as caught:
        put(url, alice, course, ("kp-a", "mastered"), ("kp-b", "mastered"))
    assert caught.value.graph_version == 2 and caught.value.indices == (1,)
    assert raw_rows(url) == []
    result = put(url, alice, course, ("kp-a", "mastered"))
    assert result.view.graph_version == 2 and stale.version == 1
    assert list(by_kp(result.view)) == ["kp-a", "kp-c"]


def test_pointer_to_a_corrupt_version_is_an_integrity_error_on_write(env):
    url, teacher, course, _, alice, _ = env
    publish(url, course, teacher, {"kp-a": ()})
    with connect(url) as db:
        db.execute("DROP TRIGGER graph_versions_committed_frozen")
        db.execute("UPDATE graph_versions SET digest = ? WHERE course_id = ?", ("sha256:" + "0" * 64, course))
    with pytest.raises(VersionIntegrityError):
        put(url, alice, course, ("kp-a", "mastered"))
    assert raw_rows(url) == []


# --- 版本迁移（A08 §5） ---------------------------------------------------------------------------


def test_lp8_rename_keeps_status_delete_is_dormant_new_node_is_unknown(env):
    url, teacher, course, _, alice, _ = env
    publish(url, course, teacher, {"kp-a": ((), "栈"), "kp-b": ((), "队列")})
    put(url, alice, course, ("kp-a", "mastered"), ("kp-b", "learning"))
    rows = raw_rows(url)
    publish(url, course, teacher, {"kp-a": ((), "栈（改名）"), "kp-c": ((), "队列")})
    current = by_kp(view(url, alice, course))
    assert list(current) == ["kp-a", "kp-c"]
    assert current["kp-a"].status == "mastered"
    assert current["kp-c"] == ProgressEntry("kp-c", "unknown", None, (), None)
    assert raw_rows(url) == rows  # kp-b 行保留
    assert status_of(view(url, alice, course, version=1)) == {"kp-a": "mastered", "kp-b": "learning"}
    rollback(url, course, teacher, source_version=1)
    assert status_of(view(url, alice, course)) == {"kp-a": "mastered", "kp-b": "learning"}


def test_lp10_projection_uses_the_bound_version_after_a_newer_commit(env):
    url, teacher, course, _, alice, _ = env
    publish(url, course, teacher, {"kp-a": (), "kp-b": ()})
    put(url, alice, course, ("kp-b", "mastered"))
    bound = resolve_published(url, course)
    publish(url, course, teacher, {"kp-a": (), "kp-b": ()})
    publish(url, course, teacher, {"kp-b": ("kp-a",)})
    old = project_progress(url, alice, bound)
    assert old.graph_version == 1 and list(by_kp(old)) == ["kp-a", "kp-b"]
    assert view(url, alice, course).graph_version == 3


def test_lp9_lp17_merge_inherits_to_a_primary_without_a_row(env):
    url, teacher, course, _, alice, _ = env
    publish(url, course, teacher, {"kp-a": (), "kp-b": ()})
    put(url, alice, course, ("kp-a", "mastered"))
    rows = raw_rows(url)
    publish(url, course, teacher, {"kp-b": ("kp-a",)})
    entry = by_kp(view(url, alice, course))["kp-b"]
    assert entry == ProgressEntry("kp-b", "mastered", None, (InheritedSource("kp-a", "mastered"),), None)
    assert view(url, alice, course).mastered == frozenset({"kp-b"})
    assert raw_rows(url) == rows


def test_lp9_primary_row_written_before_the_merge_takes_the_maximum(env):
    url, teacher, course, _, alice, _ = env
    publish(url, course, teacher, {"kp-a": (), "kp-b": ()})
    put(url, alice, course, ("kp-a", "mastered"), ("kp-b", "learning"))
    publish(url, course, teacher, {"kp-b": ("kp-a",)})
    entry = by_kp(view(url, alice, course))["kp-b"]
    assert (entry.status, entry.own_status) == ("mastered", "learning")
    assert entry.inherited_from == (InheritedSource("kp-a", "mastered"),)


def test_lower_source_does_not_lower_the_primary(env):
    url, teacher, course, _, alice, _ = env
    publish(url, course, teacher, {"kp-a": (), "kp-b": ()})
    put(url, alice, course, ("kp-a", "learning"), ("kp-b", "mastered"))
    publish(url, course, teacher, {"kp-b": ("kp-a",)})
    entry = by_kp(view(url, alice, course))["kp-b"]
    assert entry.status == "mastered" and entry.inherited_from == (InheritedSource("kp-a", "learning"),)


def test_a_source_without_a_row_is_not_listed(env):
    url, teacher, course, _, alice, _ = env
    publish(url, course, teacher, {"kp-a": (), "kp-b": ()})
    put(url, alice, course, ("kp-b", "learning"))
    publish(url, course, teacher, {"kp-b": ("kp-a",)})
    entry = by_kp(view(url, alice, course))["kp-b"]
    assert (entry.status, entry.inherited_from) == ("learning", ())


def test_lp9_chain_merge_inherits_the_highest_and_lists_sources_in_utf8_order(env):
    url, teacher, course, _, alice, _ = env
    publish(url, course, teacher, {"kp-a": (), "kp-b": (), "kp-c": (), "kp-é": ()})
    put(url, alice, course, ("kp-a", "learning"), ("kp-b", "mastered"), ("kp-é", "learning"))
    publish(url, course, teacher, {"kp-c": ("kp-a", "kp-b", "kp-é")})
    entry = by_kp(view(url, alice, course))["kp-c"]
    assert entry.status == "mastered" and entry.own_status is None
    assert [s.kp_id for s in entry.inherited_from] == ["kp-a", "kp-b", "kp-é"]


def test_lp9_rollback_restores_the_source_to_its_own_row(env):
    url, teacher, course, _, alice, _ = env
    publish(url, course, teacher, {"kp-a": (), "kp-b": ()})
    put(url, alice, course, ("kp-a", "mastered"))
    publish(url, course, teacher, {"kp-b": ("kp-a",)})
    put(url, alice, course, ("kp-b", "learning"))  # 合并后写 B：覆盖 A
    rollback(url, course, teacher, source_version=1)
    current = by_kp(view(url, alice, course))
    assert current["kp-a"].status == "mastered"
    assert (current["kp-b"].status, current["kp-b"].inherited_from) == ("learning", ())


def test_lp18_explicit_write_after_the_merge_overrides_the_sources(env):
    url, teacher, course, _, alice, _ = env
    publish(url, course, teacher, {"kp-a": (), "kp-b": ()})
    put(url, alice, course, ("kp-a", "mastered"))
    publish(url, course, teacher, {"kp-b": ("kp-a",)})
    a_row = [r for r in raw_rows(url) if r[2] == "kp-a"]
    result = put(url, alice, course, ("kp-b", "unknown"))
    entry = by_kp(result.view)["kp-b"]
    assert (entry.status, entry.own_status, entry.inherited_from) == ("unknown", "unknown", ())
    assert result.view.mastered == frozenset()
    assert [r for r in raw_rows(url) if r[2] == "kp-a"] == a_row
    assert view(url, alice, course) == result.view


def test_lp18_same_value_write_still_overrides_uncovered_sources_then_replays_as_no_op(env):
    url, teacher, course, _, alice, _ = env
    publish(url, course, teacher, {"kp-a": (), "kp-b": ()})
    put(url, alice, course, ("kp-a", "mastered"), ("kp-b", "unknown"))
    publish(url, course, teacher, {"kp-b": ("kp-a",)})
    entry = by_kp(view(url, alice, course))["kp-b"]
    assert (entry.status, entry.own_status) == ("mastered", "unknown")
    assert entry.inherited_from == (InheritedSource("kp-a", "mastered"),)
    seq = seq_value(url)
    first = put(url, alice, course, ("kp-b", "unknown"))  # A08S-R01：同值但仍有未被覆盖的来源 → 显式写入
    assert first.written == ("kp-b",) and first.write_seq == seq + 1
    entry = by_kp(first.view)["kp-b"]
    assert (entry.status, entry.own_status, entry.inherited_from) == ("unknown", "unknown", ())
    rows = raw_rows(url)
    replay = put(url, alice, course, ("kp-b", "unknown"))
    assert replay.written == () and replay.write_seq is None
    assert raw_rows(url) == rows and seq_value(url) == seq + 1
    assert replay.view == first.view


def test_lp19_source_whose_primary_was_deleted_is_dormant(env):
    url, teacher, course, _, alice, _ = env
    publish(url, course, teacher, {"kp-a": (), "kp-b": (), "kp-c": ()})
    put(url, alice, course, ("kp-a", "mastered"), ("kp-b", "learning"))
    publish(url, course, teacher, {"kp-b": ("kp-a",), "kp-c": ()})
    rows = raw_rows(url)
    publish(url, course, teacher, {"kp-c": ()})  # 删除 B（谱系随之丢弃）
    assert by_kp(view(url, alice, course)) == {"kp-c": ProgressEntry("kp-c", "unknown", None, (), None)}
    assert raw_rows(url) == rows


def test_lp20_continuity_restarts_after_a_rollback(env):
    url, teacher, course, _, alice, _ = env
    publish(url, course, teacher, {"kp-a": (), "kp-b": ()})             # v1
    put(url, alice, course, ("kp-a", "learning"))
    publish(url, course, teacher, {"kp-b": ("kp-a",)})                  # v2 合并 A→B
    put(url, alice, course, ("kp-b", "unknown"))                        # 覆盖 A
    rollback(url, course, teacher, source_version=1)                    # v3 A 重现
    v3 = by_kp(view(url, alice, course))
    assert (v3["kp-a"].status, v3["kp-b"].status, v3["kp-b"].inherited_from) == ("learning", "unknown", ())
    put(url, alice, course, ("kp-a", "mastered"))
    publish(url, course, teacher, {"kp-b": ("kp-a",)})                  # v4 再次合并
    entry = by_kp(view(url, alice, course))["kp-b"]
    assert (entry.status, entry.own_status) == ("mastered", "unknown")
    assert entry.inherited_from == (InheritedSource("kp-a", "mastered"),)
    # 绑定历史 v2：A 连续归属从 v2 起算，B 的 unknown 写于 v2 之后 → A 被覆盖
    v2 = by_kp(view(url, alice, course, version=2))["kp-b"]
    assert (v2.status, v2.inherited_from) == ("unknown", ())
    after = put(url, alice, course, ("kp-b", "unknown"))
    entry = by_kp(after.view)["kp-b"]
    assert (entry.status, entry.inherited_from) == ("unknown", ())


def test_continuous_attribution_across_several_versions_counts_from_the_first(env):
    url, teacher, course, _, alice, _ = env
    publish(url, course, teacher, {"kp-a": (), "kp-b": ()})             # v1
    put(url, alice, course, ("kp-a", "mastered"))
    publish(url, course, teacher, {"kp-b": ("kp-a",)})                  # v2：k = v2
    put(url, alice, course, ("kp-b", "learning"))                       # 写于 v2 之后
    publish(url, course, teacher, {"kp-b": ("kp-a",), "kp-n": ()})      # v3：仍连续，k 仍为 v2
    entry = by_kp(view(url, alice, course))["kp-b"]
    assert (entry.status, entry.inherited_from) == ("learning", ())


def test_reattribution_to_another_primary_restarts_continuity(env):
    url, teacher, course, _, alice, _ = env
    publish(url, course, teacher, {"kp-a": (), "kp-b": (), "kp-c": ()})  # v1
    put(url, alice, course, ("kp-a", "mastered"))
    publish(url, course, teacher, {"kp-b": ("kp-a",), "kp-c": ()})     # v2：A 归 B
    put(url, alice, course, ("kp-c", "learning"))                      # C 写于 v2 之后、v3 之前
    publish(url, course, teacher, {"kp-c": ("kp-a", "kp-b")})          # v3：A 改归 C，k = v3
    entry = by_kp(view(url, alice, course))["kp-c"]
    assert entry.status == "mastered"
    assert entry.inherited_from == (InheritedSource("kp-a", "mastered"),)


# --- 脏行与完整性 ---------------------------------------------------------------------------------


def test_dirty_rows_are_ignored_with_a_warning_and_dormant_rows_are_silent(env, caplog):
    url, teacher, course, _, alice, _ = env
    publish(url, course, teacher, {"kp-a": (), "kp-b": ()})
    put(url, alice, course, ("kp-b", "mastered"))
    publish(url, course, teacher, {"kp-a": (), "kp-c": ("kp-dirty",)})  # kp-b dormant
    sql(url, "INSERT INTO learning_progress (user_id, course_id, kp_id, status, write_seq) VALUES (?, ?, ?, ?, ?)",
        alice, course, "kp-dirty", "mastered", 1)
    with caplog.at_level(logging.WARNING, logger="app.repositories.progress"):
        result = view(url, alice, course)
    assert status_of(result) == {"kp-a": "unknown", "kp-c": "unknown"}
    messages = [r.getMessage() for r in caplog.records]
    assert len(messages) == 1 and "kp-dirty" in messages[0] and "diagnostic_id=" in messages[0]
    assert "kp-b" not in messages[0]
    assert len(raw_rows(url)) == 2


def lineage_snapshot(course_id, nodes):
    """绕过 G01 的发布校验，直接组装规范快照（模拟已提交版的谱系损坏）。"""
    good = snapshot_for(course_id, {"kp-seed": ()}).data
    [template] = good["nodes"]
    data = {**good, "nodes": [{**template, "kp_id": kp, "name": f"name-{kp}", "merged_from": sorted(nodes[kp])}
                              for kp in sorted(nodes)]}
    raw = canonical_bytes(data)
    return raw, digest_of(raw)


@pytest.mark.parametrize("nodes", [
    {"kp-a": (), "kp-b": ("kp-a",)},                     # 来源是本快照节点
    {"kp-b": ("kp-b",)},                                 # 包含自身
    {"kp-b": ("kp-x",), "kp-c": ("kp-x",)},              # 同一来源归属两个节点
])
def test_invalid_lineage_in_the_bound_version_is_an_integrity_error(env, nodes):
    url, teacher, course, _, alice, _ = env
    raw, digest = lineage_snapshot(course, nodes)
    commit_raw(url, course, teacher, raw, digest, len(nodes))
    with pytest.raises(VersionIntegrityError):
        view(url, alice, course)
    with pytest.raises(VersionIntegrityError):
        put(url, alice, course, ("kp-b", "mastered"))
    assert raw_rows(url) == []


def test_an_empty_committed_version_is_an_integrity_error(env):
    url, teacher, course, _, alice, _ = env
    raw, digest = lineage_snapshot(course, {})
    commit_raw(url, course, teacher, raw, digest, 0)
    with pytest.raises(VersionIntegrityError):
        view(url, alice, course)


def test_bound_version_of_another_course_is_refused(env):
    url, teacher, course, other, alice, _ = env
    publish(url, course, teacher, {"kp-a": ()})
    publish(url, other, teacher, {"kp-z": ()})
    theirs = resolve_published(url, other)
    forged = type(theirs)(course, theirs.version_id, theirs.version, theirs.revision_ids)
    with pytest.raises(VersionIntegrityError):
        project_progress(url, alice, forged)


def test_a_historical_version_holding_another_courses_snapshot_is_an_integrity_error(env):
    url, teacher, course, other, alice, _ = env
    v1 = publish(url, course, teacher, {"kp-a": ()})
    publish(url, course, teacher, {"kp-a": ()})
    theirs = publish(url, other, teacher, {"kp-a": ()})
    bound = resolve_published(url, course)  # 绑定 v2（完好）
    with connect(url) as db:
        db.execute("DROP TRIGGER graph_versions_committed_frozen")
        db.execute("""UPDATE graph_versions SET (snapshot_json, digest) =
                      (SELECT snapshot_json, digest FROM graph_versions WHERE version_id = ?)
                      WHERE version_id = ?""", (theirs.version_id, v1.version_id))
    with pytest.raises(VersionIntegrityError):
        project_progress(url, alice, bound)


def test_parsed_versions_are_cached_per_version_id(env, monkeypatch):
    url, teacher, course, _, alice, _ = env
    publish(url, course, teacher, {"kp-a": ()})
    publish(url, course, teacher, {"kp-b": ("kp-a",)})
    view(url, alice, course)
    calls = []
    original = progress.load_snapshot
    monkeypatch.setattr(progress, "load_snapshot", lambda raw: calls.append(1) or original(raw))
    view(url, alice, course)
    put(url, alice, course, ("kp-b", "mastered"))
    assert calls == []
