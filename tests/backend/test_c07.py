"""C07：资料上传与资料列表 API（uploadDocument / listDocuments）。

全部用临时目录作 STORAGE_DIR 与 SQLite，不发真实网络。
"""

from __future__ import annotations

import sqlite3
import time
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import load_settings
from app.main import create_app
from app.repositories import materials as materials_repo
from app.repositories.accounts import insert_account
from app.repositories.courses import add_member, create_course
from app.repositories.sqlite import connect, migrate
from app.services import materials as materials_service
from app.services.auth import issue_access_token

SECRET = "c07-test-signing-key-0123456789abcdefghij"
VALID_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA"
LIMIT = 64
PDF_BYTES = b"%PDF-1.4\n% c07 minimal\n"
DOCUMENT_KEYS = {"id", "course_id", "filename", "format", "size_bytes", "parse_status", "uploaded_at"}


def _account(url: str, username: str, role: str):
    return insert_account(
        url,
        account_id=uuid.uuid4().hex,
        username=username,
        password_hash=VALID_HASH,
        role=role,
    )


def _token(user) -> str:
    return issue_access_token(
        user_id=user.id,
        role=user.role,
        secret=SECRET.encode(),
        issued_at=int(time.time()),
        ttl_seconds=3600,
    )


class World:
    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.url = f"sqlite:///{(tmp_path / 'state.sqlite3').as_posix()}"
        migrate(self.url)
        self.storage = tmp_path / "storage"
        self.teacher = _account(self.url, "teacher1", "teacher")
        self.student = _account(self.url, "student1", "student")
        self.outsider = _account(self.url, "teacher2", "teacher")
        self.course = create_course(self.url, name="A", description=None, creator_id=self.teacher.id)
        self.other_course = create_course(
            self.url, name="B", description=None, creator_id=self.outsider.id
        )
        add_member(
            self.url,
            course_id=self.course.id,
            user_id=self.student.id,
            role="student",
            added_by=self.teacher.id,
        )
        monkeypatch.setenv("SQLITE_URL", self.url)
        monkeypatch.setenv("AUTH_JWT_SECRET", SECRET)
        monkeypatch.setenv("STORAGE_DIR", str(self.storage))
        monkeypatch.setenv("UPLOAD_MAX_BYTES", str(LIMIT))
        self.app = create_app()

    def headers(self, user) -> dict[str, str]:
        return {"Authorization": f"Bearer {_token(user)}"}

    def path(self, course_id: str | None = None) -> str:
        return f"/api/v1/courses/{course_id or self.course.id}/documents"

    def stored_files(self) -> list[str]:
        if not self.storage.exists():
            return []
        return sorted(p.name for p in self.storage.iterdir())

    def count(self, table: str) -> int:
        with connect(self.url) as database:
            return database.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


@pytest.fixture
def world(tmp_path, monkeypatch) -> World:
    return World(tmp_path, monkeypatch)


@pytest.fixture
def client(world):
    with TestClient(world.app) as test_client:
        yield test_client


def upload(client, world, user=None, *, name="notes.txt", data=b"course notes", media="text/plain", course_id=None):
    headers = world.headers(user or world.teacher) if user is not False else {}
    return client.post(world.path(course_id), headers=headers, files={"file": (name, data, media)})


# ---------------------------------------------------------------- 上传：成功路径


def test_upload_returns_202_with_task_and_document_ids(client, world):
    response = upload(client, world)

    assert response.status_code == 202
    body = response.json()
    assert set(body) == {"task_id", "document_id"}
    with connect(world.url) as database:
        material = database.execute(
            "SELECT course_id, filename, format, size_bytes, content_hash, storage_name "
            "FROM materials WHERE id = ?",
            (body["document_id"],),
        ).fetchone()
        task = database.execute(
            "SELECT course_id, document_id, stage, progress FROM processing_tasks WHERE id = ?",
            (body["task_id"],),
        ).fetchone()
    assert material[:4] == (world.course.id, "notes.txt", "txt", 12)
    assert material[4].startswith("sha256:")
    # 只建任务，不在请求内解析：任务停在 queued、进度 0。
    assert task == (world.course.id, body["document_id"], "queued", 0)
    assert world.stored_files() == [material[5]]


@pytest.mark.parametrize(
    ("name", "data", "media", "expected_format"),
    [
        ("slides.pdf", PDF_BYTES, "application/pdf", "pdf"),
        ("notes.md", b"# Title\n\ntext", "text/markdown", "markdown"),
        ("notes.markdown", b"# Title", "application/octet-stream", "markdown"),
        ("notes.txt", b"plain", "text/plain", "txt"),
    ],
)
def test_upload_accepts_supported_formats(client, world, name, data, media, expected_format):
    response = upload(client, world, name=name, data=data, media=media)

    assert response.status_code == 202
    listed = client.get(world.path(), headers=world.headers(world.teacher)).json()
    assert [item["format"] for item in listed] == [expected_format]


def test_upload_at_exact_limit_is_accepted(client, world):
    response = upload(client, world, data=b"x" * LIMIT)

    assert response.status_code == 202
    assert world.count("materials") == 1


def test_each_upload_creates_new_material_and_task(client, world):
    first = upload(client, world).json()
    second = upload(client, world).json()

    assert first["document_id"] != second["document_id"]
    assert first["task_id"] != second["task_id"]
    assert world.count("materials") == 2
    assert world.count("processing_tasks") == 2
    assert len(world.stored_files()) == 2


# ---------------------------------------------------------------- 上传：失败路径


def test_upload_over_limit_is_413_with_limit_bytes_and_leaves_nothing(client, world):
    response = upload(client, world, data=b"x" * (LIMIT + 1))

    assert response.status_code == 413
    assert response.json() == {
        "code": "FILE_TOO_LARGE",
        "message": response.json()["message"],
        "details": {"limit_bytes": LIMIT},
    }
    assert world.stored_files() == []
    assert world.count("materials") == 0
    assert world.count("processing_tasks") == 0


@pytest.mark.parametrize(
    ("name", "data", "media"),
    [
        ("virus.exe", b"MZ....", "application/octet-stream"),
        ("slides.pptx", b"PK\x03\x04", "application/octet-stream"),
        ("fake.pdf", b"not a pdf at all", "application/pdf"),
        ("zip.txt", b"PK\x03\x04rest", "text/plain"),
        ("notes.txt", b"plain", "application/pdf"),
        ("empty.txt", b"", "text/plain"),
    ],
)
def test_unsupported_format_is_415_and_leaves_nothing(client, world, name, data, media):
    response = upload(client, world, name=name, data=data, media=media)

    assert response.status_code == 415
    body = response.json()
    assert body["code"] == "UNSUPPORTED_FORMAT"
    assert body["details"]["supported"] == ["pdf", "docx", "txt", "markdown"]
    assert world.stored_files() == []
    assert world.count("materials") == 0


def test_invalid_filename_is_contract_validation_error(client, world):
    response = upload(client, world, name="a" * 300 + ".txt")

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert response.json()["details"] == {
        "fields": [{"in": "body", "field": "file", "reason": "too_long"}]
    }
    assert world.stored_files() == []


def test_missing_file_field_is_validation_error(client, world):
    response = client.post(
        world.path(), headers=world.headers(world.teacher), data={"other": "x"}
    )

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert {"in": "body", "field": "file", "reason": "missing"} in response.json()["details"]["fields"]
    assert world.count("materials") == 0


def test_unwritable_storage_is_503(tmp_path, monkeypatch):
    world = World(tmp_path, monkeypatch)
    world.storage.write_text("not a directory")
    monkeypatch.setenv("STORAGE_DIR", str(world.storage))
    with TestClient(create_app()) as client:
        response = upload(client, world)

    assert response.status_code == 503
    assert response.json()["code"] == "STORAGE_UNAVAILABLE"
    assert world.count("materials") == 0


# ---------------------------------------------------------------- 上传：补偿


def test_database_failure_after_store_deletes_new_file_and_is_503(client, world, monkeypatch):
    def broken(*args, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(materials_service, "create_material_task", broken)
    response = upload(client, world)

    assert response.status_code == 503
    assert response.json()["code"] == "STORAGE_UNAVAILABLE"
    assert "locked" not in response.text
    assert world.stored_files() == []
    assert world.count("materials") == 0


def test_unexpected_failure_after_store_deletes_new_file(world, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(materials_service, "create_material_task", broken)
    with TestClient(world.app, raise_server_exceptions=False) as client:
        response = upload(client, world)

    assert response.status_code == 500
    assert world.stored_files() == []


def test_idempotent_replay_deletes_newly_stored_unreferenced_file(world):
    settings = load_settings()
    first = materials_service.upload_material(
        settings,
        course_id=world.course.id,
        filename="notes.txt",
        content_type="text/plain",
        chunks=[b"course notes"],
        idempotency_key="fixed-key",
    )
    files_after_first = world.stored_files()
    second = materials_service.upload_material(
        settings,
        course_id=world.course.id,
        filename="notes.txt",
        content_type="text/plain",
        chunks=[b"other notes"],
        idempotency_key="fixed-key",
    )

    assert second == first
    assert world.stored_files() == files_after_first
    assert len(files_after_first) == 1
    assert world.count("materials") == 1


def test_default_idempotency_keys_are_unique_per_request(world):
    settings = load_settings()
    kwargs = dict(
        course_id=world.course.id,
        filename="notes.txt",
        content_type="text/plain",
        chunks=[b"course notes"],
    )
    first = materials_service.upload_material(settings, **kwargs)
    second = materials_service.upload_material(settings, **kwargs)

    assert first.document_id != second.document_id
    assert world.count("processing_tasks") == 2


# ---------------------------------------------------------------- 访问矩阵


@pytest.mark.parametrize("method", ["get", "post"])
@pytest.mark.parametrize(
    ("who", "status", "code"),
    [
        ("anonymous", 401, "UNAUTHENTICATED"),
        ("outsider", 403, "COURSE_FORBIDDEN"),
        ("student", 403, "ROLE_FORBIDDEN"),
    ],
)
def test_access_matrix_rejects_before_touching_storage(client, world, method, who, status, code):
    headers = {} if who == "anonymous" else world.headers(getattr(world, who))
    if method == "get":
        response = client.get(world.path(), headers=headers)
    else:
        response = client.post(
            world.path(), headers=headers, files={"file": ("notes.txt", b"x", "text/plain")}
        )

    assert response.status_code == status
    assert response.json()["code"] == code
    assert world.stored_files() == []
    assert world.count("materials") == 0


@pytest.mark.parametrize("method", ["get", "post"])
def test_unknown_course_is_course_forbidden(client, world, method):
    path = world.path("no-such-course")
    headers = world.headers(world.teacher)
    if method == "get":
        response = client.get(path, headers=headers)
    else:
        response = client.post(path, headers=headers, files={"file": ("n.txt", b"x", "text/plain")})

    assert response.status_code == 403
    assert response.json()["code"] == "COURSE_FORBIDDEN"


def test_anonymous_without_file_is_401_not_422(client, world):
    response = client.post(world.path(), data={"other": "x"})

    assert response.status_code == 401


def test_teacher_cannot_upload_into_other_teachers_course(client, world):
    response = upload(client, world, course_id=world.other_course.id)

    assert response.status_code == 403
    assert world.count("materials") == 0


# ---------------------------------------------------------------- 先授权、再有界解析（移植自 #229）

# 超过 UPLOAD_MAX_BYTES + 16 KiB 表单开销（LIMIT=64 时为 16 448 字节）。
OVERSIZE_BODY = b"x" * 17000


def _forbid_multipart_parsing(monkeypatch, reason):
    from starlette.formparsers import MultiPartParser

    def must_not_parse(*args, **kwargs):
        raise AssertionError(reason)

    monkeypatch.setattr(MultiPartParser, "parse", must_not_parse)


def test_unauthenticated_upload_is_rejected_before_multipart_parsing(client, world, monkeypatch):
    _forbid_multipart_parsing(monkeypatch, "multipart parsed before authorization")

    response = upload(client, world, user=False)

    assert (response.status_code, response.json()["code"]) == (401, "UNAUTHENTICATED")


def test_huge_content_length_is_413_before_multipart_parsing(client, world, monkeypatch):
    _forbid_multipart_parsing(monkeypatch, "oversize body parsed before length rejection")

    response = upload(client, world, data=OVERSIZE_BODY)

    assert response.status_code == 413
    assert response.json()["code"] == "FILE_TOO_LARGE"
    assert response.json()["details"] == {"limit_bytes": LIMIT}
    assert world.stored_files() == []
    assert world.count("materials") == 0


def test_body_limit_counts_received_bytes_when_content_length_is_unreliable(client, world, monkeypatch):
    from app.services.file_storage import FileStorage

    def must_not_save(*args, **kwargs):
        raise AssertionError("oversize body reached the storage service")

    monkeypatch.setattr(FileStorage, "save", must_not_save)
    response = client.post(
        world.path(),
        headers=world.headers(world.teacher) | {"Content-Length": "0"},
        files={"file": ("notes.txt", OVERSIZE_BODY, "text/plain")},
    )

    assert response.status_code == 413
    assert response.json()["code"] == "FILE_TOO_LARGE"
    assert response.json()["details"] == {"limit_bytes": LIMIT}
    assert world.stored_files() == []
    assert world.count("materials") == 0


# ---------------------------------------------------------------- 列表


def _insert_material(world, course_id, *, material_id=None, uploaded_at=None, filename="m.txt"):
    material_id = material_id or uuid.uuid4().hex
    with connect(world.url) as database:
        materials_repo.insert_material(
            database,
            material_id=material_id,
            course_id=course_id,
            filename=filename,
            format="txt",
            size_bytes=5,
            content_hash="sha256:" + "b" * 64,
            storage_name=uuid.uuid4().hex + ".txt",
        )
        if uploaded_at is not None:
            database.execute(
                "UPDATE materials SET uploaded_at = ? WHERE id = ?", (uploaded_at, material_id)
            )
    return material_id


def _insert_task(world, course_id, document_id, *, stage, created_at, updated_at=None):
    progress = 0 if stage == "queued" else 0.5
    cancel = 1 if stage == "cancelled" else 0
    with connect(world.url) as database:
        database.execute(
            """INSERT INTO processing_tasks
               (id, course_id, document_id, stage, progress, cancel_requested,
                created_at, updated_at, idempotency_key)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                uuid.uuid4().hex,
                course_id,
                document_id,
                stage,
                progress,
                cancel,
                created_at,
                updated_at or created_at,
                uuid.uuid4().hex,
            ),
        )


def _list(client, world):
    response = client.get(world.path(), headers=world.headers(world.teacher))
    assert response.status_code == 200
    return response.json()


def test_empty_course_lists_nothing(client, world):
    assert _list(client, world) == []


def test_list_returns_contract_documents_after_upload(client, world):
    accepted = upload(client, world, name="slides.pdf", data=PDF_BYTES, media="application/pdf").json()

    listed = _list(client, world)

    assert len(listed) == 1
    item = listed[0]
    assert set(item) == DOCUMENT_KEYS
    assert item["id"] == accepted["document_id"]
    assert item["course_id"] == world.course.id
    assert item["filename"] == "slides.pdf"
    assert item["format"] == "pdf"
    assert item["size_bytes"] == len(PDF_BYTES)
    assert item["parse_status"] == "queued"
    assert item["uploaded_at"].endswith("Z")


def test_list_is_isolated_by_course(client, world):
    _insert_material(world, world.other_course.id, filename="secret.txt")
    mine = _insert_material(world, world.course.id, filename="mine.txt")

    listed = _list(client, world)

    assert [item["id"] for item in listed] == [mine]
    assert all(item["course_id"] == world.course.id for item in listed)
    assert materials_repo.list_materials(world.url, course_id=world.other_course.id)[0].filename == "secret.txt"


def test_parse_status_follows_latest_created_task_not_column(client, world):
    material = _insert_material(world, world.course.id)
    _insert_task(
        world,
        world.course.id,
        material,
        stage="completed",  # 不用 failed：C09 迁移 005 要求 failed 行带 error_code
        created_at="2026-09-25T01:00:00.000Z",
        updated_at="2026-09-25T09:00:00.000Z",  # 最近更新的是旧任务
    )
    _insert_task(world, world.course.id, material, stage="parsing", created_at="2026-09-25T02:00:00.000Z")

    listed = _list(client, world)

    assert listed[0]["parse_status"] == "parsing"
    with connect(world.url) as database:
        column = database.execute(
            "SELECT parse_status FROM materials WHERE id = ?", (material,)
        ).fetchone()[0]
    assert column == "queued"  # D-16：列不再维护，读时取任务


def test_parse_status_tie_on_created_at_prefers_later_inserted_task(client, world):
    material = _insert_material(world, world.course.id)
    same = "2026-09-25T02:00:00.000Z"
    _insert_task(world, world.course.id, material, stage="completed", created_at=same)
    _insert_task(world, world.course.id, material, stage="cancelled", created_at=same)

    assert _list(client, world)[0]["parse_status"] == "cancelled"


def test_parse_status_without_task_falls_back_to_column_default(client, world):
    _insert_material(world, world.course.id)

    assert _list(client, world)[0]["parse_status"] == "queued"


def test_list_orders_by_uploaded_at_then_id(client, world):
    late = _insert_material(world, world.course.id, material_id="a-late", uploaded_at="2026-09-25T03:00:00.000Z")
    tie_b = _insert_material(world, world.course.id, material_id="b-tie", uploaded_at="2026-09-25T01:00:00.000Z")
    tie_a = _insert_material(world, world.course.id, material_id="a-tie", uploaded_at="2026-09-25T01:00:00.000Z")

    assert [item["id"] for item in _list(client, world)] == [tie_a, tie_b, late]


def test_openapi_exposes_contract_operations(world):
    paths = world.app.openapi()["paths"]["/api/v1/courses/{cid}/documents"]

    assert paths["get"]["operationId"] == "listDocuments"
    assert paths["post"]["operationId"] == "uploadDocument"
    assert "202" in paths["post"]["responses"]
    assert {"413", "415"} <= set(paths["post"]["responses"])
    body = paths["post"]["requestBody"]["content"]["multipart/form-data"]["schema"]
    assert body["required"] == ["file"]
    assert body["properties"]["file"] == {"type": "string", "format": "binary"}
