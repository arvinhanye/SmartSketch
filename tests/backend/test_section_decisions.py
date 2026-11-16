"""Per-pair section decisions survive lease turnover without crossing task boundaries."""

from dataclasses import asdict
from pathlib import Path
import sqlite3

import pytest

from app.repositories.extraction_checkpoints import write_checkpoint
from app.repositories.sqlite import connect, migrate
from app.repositories.task_leases import claim_next
from app.services.fusion.resolution import SemanticDecision
from tests.backend.test_fusion_storage import state


DECISION = asdict(SemanticDecision(
    "mention-a", "mention-b", "complete", verdict="DIFFERENT", basis="material",
    reason="Different operations", left_source_ids=("source-a",),
    right_source_ids=("source-b",), differences=("Different order",),
    model_calls=1, model_ids=("fixture",), prompt_sha256="fixture-prompt",
))


def scope(course_id):
    return dict(course_id=course_id, task_id="task", section_id="sec", input_digest="input")


def test_migration_provides_empty_decision_cache(state):
    url, _ = state
    with connect(url) as db:
        assert db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='task_section_decisions'"
        ).fetchone() == ("task_section_decisions",)
        assert db.execute("SELECT count(*) FROM task_section_decisions").fetchone() == (0,)


def test_first_complete_decision_is_kept_across_reopens(state):
    from app.repositories.section_decisions import put_decision, read_decision

    url, course_id = state
    key = scope(course_id)
    pair = dict(left_id="mention-a", right_id="mention-b")
    with connect(url) as db:
        with pytest.raises(RuntimeError, match="transaction"):
            put_decision(db, **key, decision=DECISION)
        db.execute("BEGIN IMMEDIATE")
        assert put_decision(db, **key, decision=DECISION)
        db.execute("COMMIT")
    with connect(url) as db:
        db.execute("BEGIN IMMEDIATE")
        assert not put_decision(db, **key, decision={**DECISION, "reason": "Replacement"})
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            db.execute("UPDATE task_section_decisions SET decision=decision")
        db.execute("COMMIT")
        saved = read_decision(db, **key, **pair)
        assert saved == {
            **DECISION, "left_source_ids": ["source-a"], "right_source_ids": ["source-b"],
            "differences": ["Different order"], "model_ids": ["fixture"],
        }


def test_cache_lookup_does_not_reuse_a_changed_input_or_scope(state):
    from app.repositories.section_decisions import put_decision, read_decision

    url, course_id = state
    key = scope(course_id)
    pair = dict(left_id="mention-a", right_id="mention-b")
    with connect(url) as db:
        db.execute("BEGIN IMMEDIATE")
        assert put_decision(db, **key, decision=DECISION)
        assert put_decision(db, **{**key, "input_digest": "next-input"}, decision={
            **DECISION, "reason": "New input",
        })
        with pytest.raises(sqlite3.IntegrityError, match="course"):
            put_decision(db, **{**key, "course_id": "other"}, decision=DECISION)
        db.execute("COMMIT")
        for field, wrong_value in (
            ("course_id", "other"), ("task_id", "other"), ("section_id", "other"),
            ("input_digest", "unknown"), ("left_id", "mention-0"), ("right_id", "mention-c"),
        ):
            assert read_decision(db, **{**key, **pair, field: wrong_value}) is None
        assert read_decision(db, **{**key, "input_digest": "next-input"}, **pair)["reason"] == "New input"


@pytest.mark.parametrize("change", [
    {"status": "failed"}, {"status": "deferred"}, {"status": None}, {"verdict": None},
    {"left_id": ""}, {"right_id": "mention-a"},
])
def test_invalid_or_incomplete_decisions_are_not_cached(state, change):
    from app.repositories.section_decisions import put_decision

    url, course_id = state
    with connect(url) as db:
        db.execute("BEGIN IMMEDIATE")
        with pytest.raises(ValueError):
            put_decision(db, **scope(course_id), decision={**DECISION, **change})
        assert db.execute("SELECT count(*) FROM task_section_decisions").fetchone() == (0,)
        db.execute("ROLLBACK")


def test_sqlite_rejects_incomplete_and_mismatched_payloads(state):
    url, course_id = state
    with connect(url) as db:
        for payload in (
            "{",
            "{}",
            '{"status":"failed","verdict":"DIFFERENT","left_id":"mention-a","right_id":"mention-b"}',
            '{"status":"complete","verdict":"DIFFERENT","left_id":"mention-a","right_id":"wrong"}',
        ):
            with pytest.raises(sqlite3.IntegrityError):
                db.execute(
                    """INSERT INTO task_section_decisions
                    (task_id,course_id,section_id,input_digest,left_id,right_id,decision)
                    VALUES ('task',?,'sec','input','mention-a','mention-b',?)""",
                    (course_id, payload),
                )


def test_task_deletion_cascades_to_decision_cache(state):
    from app.repositories.section_decisions import put_decision

    url, course_id = state
    with connect(url) as db:
        db.execute("BEGIN IMMEDIATE")
        assert put_decision(db, **scope(course_id), decision=DECISION)
        db.execute("DELETE FROM processing_tasks WHERE id='task'")
        db.execute("COMMIT")
        assert db.execute("SELECT count(*) FROM task_section_decisions").fetchone() == (0,)


def test_rollback_waits_for_live_lease_and_preserves_extraction_checkpoints(state):
    from app.repositories.section_decisions import put_decision

    url, course_id = state
    migration = Path(__file__).resolve().parents[2] / "src/backend/migrations/024_section_decisions.sql"
    statements = [line.removeprefix("-- ROLLBACK: ") for line in migration.read_text().splitlines()
                  if line.startswith("-- ROLLBACK: ")]
    assert statements
    with connect(url) as db:
        db.execute("BEGIN IMMEDIATE")
        assert put_decision(db, **scope(course_id), decision=DECISION)
        write_checkpoint(db, course_id=course_id, task_id="task", unit_kind="chunk",
                         unit_id="chunk", status="done", attempts=1, result={"entities": []})
        db.execute("COMMIT")
    assert claim_next(url, owner="test-worker", lease_seconds=60, max_attempts=3) is not None
    with connect(url) as db:
        db.execute("BEGIN IMMEDIATE")
        with pytest.raises(sqlite3.IntegrityError):
            for statement in statements:
                db.execute(statement)
        db.execute("ROLLBACK")
        assert db.execute("SELECT count(*) FROM task_section_decisions").fetchone() == (1,)
        db.execute("BEGIN IMMEDIATE")
        # 026 additionally requires active processing to finish or be cancelled.
        db.execute("UPDATE processing_tasks SET stage='cancelled',cancel_requested=1,lease_expires_at=0 WHERE id='task'")
        for newer in sorted(migration.parent.glob('*.sql'), reverse=True):
            if newer.name[:3] <= '024':
                break
            for line in newer.read_text().splitlines():
                if line.startswith('-- ROLLBACK: '):
                    db.execute(line.removeprefix('-- ROLLBACK: '))
        for statement in statements:
            db.execute(statement)
        db.execute("COMMIT")
        assert db.execute("SELECT version FROM schema_migrations WHERE version='024'").fetchone() is None
        assert db.execute("SELECT name FROM sqlite_master WHERE name='task_section_decisions'").fetchone() is None
        assert db.execute("SELECT unit_id FROM task_chunk_checkpoints").fetchone() == ("chunk",)

    migrate(url)
    with connect(url) as db:
        assert db.execute("SELECT count(*) FROM task_section_decisions").fetchone() == (0,)
        assert db.execute("SELECT unit_id FROM task_chunk_checkpoints").fetchone() == ("chunk",)
