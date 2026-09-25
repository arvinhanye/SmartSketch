"""C07 upload and course document listing through the served API boundary."""

from __future__ import annotations

import time
import uuid
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.repositories.accounts import insert_account
from app.repositories.courses import add_member, create_course
from app.repositories.sqlite import connect, migrate
from app.services.auth import issue_access_token
from app.services.materials import upload_material


SECRET = "c07-test-signing-key-0123456789abcdefghij"
VALID_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA"


@pytest.fixture
def scenario(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    url = f"sqlite:///{(tmp_path / 'state.sqlite3').as_posix()}"
    storage_dir = tmp_path / "uploads"
    migrate(url)
    teacher = insert_account(
        url, account_id=uuid.uuid4().hex, username="teacher-c07",
        password_hash=VALID_HASH, role="teacher",
    )
    outsider = insert_account(
        url, account_id=uuid.uuid4().hex, username="outsider-c07",
        password_hash=VALID_HASH, role="teacher",
    )
    student = insert_account(
        url, account_id=uuid.uuid4().hex, username="student-c07",
        password_hash=VALID_HASH, role="student",
    )
    course = create_course(url, name="Course A", description=None, creator_id=teacher.id)
    other = create_course(url, name="Course B", description=None, creator_id=outsider.id)
    add_member(url, course_id=course.id, user_id=student.id, role="student", added_by=teacher.id)
    monkeypatch.setenv("SQLITE_URL", url)
    monkeypatch.setenv("STORAGE_DIR", str(storage_dir))
    monkeypatch.setenv("UPLOAD_MAX_BYTES", "64")
    monkeypatch.setenv("AUTH_JWT_SECRET", SECRET)
    app = create_app()

    def bearer(user):
        token = issue_access_token(
            user_id=user.id, role=user.role, secret=SECRET.encode(),
            issued_at=int(time.time()), ttl_seconds=3600,
        )
        return {"Authorization": f"Bearer {token}"}

    with TestClient(app) as client:
        yield client, url, storage_dir, course.id, other.id, bearer(teacher), bearer(student), bearer(outsider)


def _upload(client, cid, headers, filename="notes.txt", data=b"Course notes", media_type="text/plain"):
    return client.post(
        f"/api/v1/courses/{cid}/documents", headers=headers,
        files={"file": (filename, data, media_type)},
    )


def test_upload_creates_queued_task_and_course_list_returns_document(scenario):
    client, url, storage_dir, cid, other_cid, teacher, student, outsider = scenario

    response = _upload(client, cid, teacher)

    assert response.status_code == 202
    accepted = response.json()
    assert set(accepted) == {"task_id", "document_id"}
    with connect(url) as database:
        task = database.execute(
            "SELECT document_id, stage FROM processing_tasks WHERE id = ?", (accepted["task_id"],)
        ).fetchone()
        material = database.execute(
            "SELECT storage_name FROM materials WHERE id = ?", (accepted["document_id"],)
        ).fetchone()
    assert task == (accepted["document_id"], "queued")
    assert material is not None
    assert (storage_dir / material[0]).read_bytes() == b"Course notes"
    listed = client.get(f"/api/v1/courses/{cid}/documents", headers=teacher)
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0] | {"uploaded_at": None} == {
        "id": accepted["document_id"], "course_id": cid, "filename": "notes.txt",
        "format": "txt", "size_bytes": 12, "parse_status": "queued", "uploaded_at": None,
    }
    assert client.get(f"/api/v1/courses/{other_cid}/documents", headers=outsider).json() == []


def test_upload_denies_non_teacher_before_writing_file(scenario):
    client, url, storage_dir, cid, _, teacher, student, outsider = scenario
    assert _upload(client, cid, student).status_code == 403
    assert _upload(client, cid, outsider).status_code == 403
    assert _upload(client, cid, {}).status_code == 401
    with connect(url) as database:
        assert database.execute("SELECT count(*) FROM materials").fetchone() == (0,)
    assert not storage_dir.exists() or list(storage_dir.iterdir()) == []


def test_upload_rejects_unsupported_and_oversize_files_without_rows(scenario):
    client, url, storage_dir, cid, _, teacher, _, _ = scenario
    unsupported = _upload(client, cid, teacher, filename="notes.exe")
    oversized = _upload(client, cid, teacher, data=b"x" * 65)
    assert (unsupported.status_code, unsupported.json()["code"]) == (415, "UNSUPPORTED_FORMAT")
    assert (oversized.status_code, oversized.json()["code"]) == (413, "FILE_TOO_LARGE")
    assert oversized.json()["details"]["limit_bytes"] == 64
    with connect(url) as database:
        assert database.execute("SELECT count(*) FROM materials").fetchone() == (0,)
        assert database.execute("SELECT count(*) FROM processing_tasks").fetchone() == (0,)
    assert list(storage_dir.iterdir()) == []


def test_task_creation_failure_deletes_newly_stored_file(scenario, monkeypatch):
    client, url, storage_dir, cid, _, teacher, _, _ = scenario
    from app.repositories import tasks

    def fail(*args, **kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(tasks, "create_material_task", fail)
    response = _upload(client, cid, teacher)
    assert (response.status_code, response.json()["code"]) == (500, "INTERNAL_ERROR")
    assert list(storage_dir.iterdir()) == []
    with connect(url) as database:
        assert database.execute("SELECT count(*) FROM materials").fetchone() == (0,)


def test_list_requires_course_membership(scenario):
    client, _, _, cid, _, teacher, student, outsider = scenario
    assert client.get(f"/api/v1/courses/{cid}/documents", headers=teacher).status_code == 200
    assert client.get(f"/api/v1/courses/{cid}/documents", headers=student).status_code == 404
    assert client.get(f"/api/v1/courses/{cid}/documents", headers=outsider).status_code == 403


def test_internal_idempotent_replay_removes_only_new_file(scenario):
    client, url, storage_dir, cid, _, _, _, _ = scenario
    settings = client.app.state.settings
    first = upload_material(
        settings, course_id=cid, filename="notes.txt", content_type="text/plain",
        stream=BytesIO(b"first content"), idempotency_key="same-key",
    )
    replay = upload_material(
        settings, course_id=cid, filename="notes.txt", content_type="text/plain",
        stream=BytesIO(b"different content"), idempotency_key="same-key",
    )

    assert first.created is True
    assert replay.created is False
    assert replay.task.id == first.task.id
    assert replay.material.id == first.material.id
    with connect(url) as database:
        stored_name = database.execute("SELECT storage_name FROM materials").fetchone()[0]
        assert database.execute("SELECT count(*) FROM materials").fetchone() == (1,)
    assert [path.name for path in storage_dir.iterdir()] == [stored_name]
    assert (storage_dir / stored_name).read_bytes() == b"first content"


def test_unauthenticated_upload_is_rejected_before_multipart_parsing(scenario, monkeypatch):
    client, _, _, cid, _, _, _, _ = scenario
    from starlette.formparsers import MultiPartParser

    def must_not_parse(*args, **kwargs):
        raise AssertionError("multipart parsed before authorization")

    monkeypatch.setattr(MultiPartParser, "parse", must_not_parse)
    response = _upload(client, cid, {})
    assert (response.status_code, response.json()["code"]) == (401, "UNAUTHENTICATED")


def test_huge_request_is_rejected_before_multipart_parsing(scenario, monkeypatch):
    client, _, _, cid, _, teacher, _, _ = scenario
    from starlette.formparsers import MultiPartParser

    def must_not_parse(*args, **kwargs):
        raise AssertionError("oversize body parsed before length rejection")

    monkeypatch.setattr(MultiPartParser, "parse", must_not_parse)
    response = _upload(client, cid, teacher, data=b"x" * 17000)
    assert (response.status_code, response.json()["code"]) == (413, "FILE_TOO_LARGE")


def test_body_limit_counts_received_bytes_when_length_header_is_unreliable(scenario, monkeypatch):
    client, _, storage_dir, cid, _, teacher, _, _ = scenario
    from app.services.file_storage import FileStorage

    def must_not_save(*args, **kwargs):
        raise AssertionError("oversize body reached the storage service")

    monkeypatch.setattr(FileStorage, "save", must_not_save)
    response = client.post(
        f"/api/v1/courses/{cid}/documents",
        headers=teacher | {"Content-Length": "0"},
        files={"file": ("notes.txt", b"x" * 17000, "text/plain")},
    )
    assert (response.status_code, response.json()["code"]) == (413, "FILE_TOO_LARGE")
    assert not storage_dir.exists()
