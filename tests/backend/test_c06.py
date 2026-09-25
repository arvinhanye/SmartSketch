"""C06: atomically create a material and its initial queued task."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.repositories import materials, tasks
from app.repositories.sqlite import connect, migrate
from app.services.file_storage import StoredFile


def _stored_file(tmp_path: Path, *, storage_name: str = "a" * 32 + ".txt") -> StoredFile:
    path = tmp_path / storage_name
    path.write_text("course notes", encoding="utf-8")
    return StoredFile(
        storage_name=storage_name,
        path=path,
        original_filename="notes.txt",
        format="txt",
        size_bytes=12,
        content_hash="sha256:" + "a" * 64,
    )


@pytest.fixture
def db_url(tmp_path: Path) -> str:
    url = f"sqlite:///{(tmp_path / 'state.sqlite3').as_posix()}"
    # 只断言 001～003 依序应用；后续迁移（如 C02 的 004）不影响本任务。
    assert migrate(url)[:3] == ["001", "002", "003"]
    return url


def test_create_material_and_queued_task_in_one_database_transaction(db_url, tmp_path):
    result = tasks.create_material_task(
        db_url,
        course_id="course-a",
        stored_file=_stored_file(tmp_path),
        idempotency_key="upload-1",
    )

    assert result.created is True
    assert result.material.course_id == "course-a"
    assert result.material.filename == "notes.txt"
    assert result.material.format == "txt"
    assert result.material.size_bytes == 12
    assert result.material.content_hash == "sha256:" + "a" * 64
    assert result.material.storage_name == "a" * 32 + ".txt"
    assert result.material.parse_status == "queued"
    assert result.task.document_id == result.material.id
    assert result.task.course_id == "course-a"
    assert result.task.stage == "queued"
    assert result.task.progress == 0
    assert result.task.cancel_requested is False
    assert result.task.idempotency_key == "upload-1"

    with connect(db_url) as database:
        assert database.execute("SELECT count(*) FROM materials").fetchone() == (1,)
        assert database.execute("SELECT count(*) FROM processing_tasks").fetchone() == (1,)
        assert database.execute("PRAGMA foreign_key_check").fetchall() == []


def test_same_idempotency_key_replays_within_course(db_url, tmp_path):
    first = tasks.create_material_task(
        db_url,
        course_id="course-a",
        stored_file=_stored_file(tmp_path),
        idempotency_key="retry-key",
    )
    second = tasks.create_material_task(
        db_url,
        course_id="course-a",
        stored_file=_stored_file(tmp_path, storage_name="b" * 32 + ".txt"),
        idempotency_key="retry-key",
    )

    assert second.created is False
    assert second.material.id == first.material.id
    assert second.material.storage_name == first.material.storage_name
    assert second.task.id == first.task.id
    with connect(db_url) as database:
        assert database.execute("SELECT count(*) FROM materials").fetchone() == (1,)
        assert database.execute("SELECT count(*) FROM processing_tasks").fetchone() == (1,)


def test_idempotency_key_is_scoped_to_course(db_url, tmp_path):
    first = tasks.create_material_task(
        db_url,
        course_id="course-a",
        stored_file=_stored_file(tmp_path),
        idempotency_key="same-key",
    )
    second = tasks.create_material_task(
        db_url,
        course_id="course-b",
        stored_file=_stored_file(tmp_path, storage_name="b" * 32 + ".txt"),
        idempotency_key="same-key",
    )

    assert second.created is True
    assert second.task.id != first.task.id
    assert second.material.id != first.material.id
    assert second.task.course_id == "course-b"
    with connect(db_url) as database:
        assert database.execute("SELECT count(*) FROM materials").fetchone() == (2,)
        assert database.execute("SELECT count(*) FROM processing_tasks").fetchone() == (2,)


def test_task_insert_failure_rolls_back_material(monkeypatch, db_url, tmp_path):
    def fail_after_material_insert(*args, **kwargs):
        raise sqlite3.IntegrityError("simulated task insert failure")

    monkeypatch.setattr(tasks, "_insert_task", fail_after_material_insert)
    with pytest.raises(sqlite3.IntegrityError, match="simulated task insert failure"):
        tasks.create_material_task(
            db_url,
            course_id="course-a",
            stored_file=_stored_file(tmp_path),
            idempotency_key="rollback-key",
        )

    with connect(db_url) as database:
        assert database.execute("SELECT count(*) FROM materials").fetchone() == (0,)
        assert database.execute("SELECT count(*) FROM processing_tasks").fetchone() == (0,)


def test_database_constraints_reject_empty_course_or_idempotency_key(db_url, tmp_path):
    stored = _stored_file(tmp_path)
    with pytest.raises(ValueError, match="course_id"):
        tasks.create_material_task(
            db_url, course_id=" ", stored_file=stored, idempotency_key="key"
        )
    with pytest.raises(ValueError, match="idempotency_key"):
        tasks.create_material_task(
            db_url, course_id="course-a", stored_file=stored, idempotency_key=""
        )
    with connect(db_url) as database:
        assert database.execute("SELECT count(*) FROM materials").fetchone() == (0,)
        assert database.execute("SELECT count(*) FROM processing_tasks").fetchone() == (0,)


def test_material_reads_require_course_scope(db_url, tmp_path):
    result = tasks.create_material_task(
        db_url,
        course_id="course-a",
        stored_file=_stored_file(tmp_path),
        idempotency_key="read-material",
    )

    with pytest.raises(TypeError):
        materials.get_material(db_url, result.material.id)
    assert materials.get_material(
        db_url, result.material.id, course_id="course-b"
    ) is None


def test_task_reads_require_course_scope(db_url, tmp_path):
    result = tasks.create_material_task(
        db_url,
        course_id="course-a",
        stored_file=_stored_file(tmp_path),
        idempotency_key="read-task",
    )

    with pytest.raises(TypeError):
        tasks.get_task(db_url, result.task.id)
    assert tasks.get_task(
        db_url, result.task.id, course_id="course-b"
    ) is None
