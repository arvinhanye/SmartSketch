"""ADR-021：资料列表带最新任务 ID（Document.task_id）；删除未产生图谱贡献的资料（deleteDocument）。

全部用临时目录作 STORAGE_DIR 与 SQLite，不发真实网络。
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.repositories import chunks as chunk_store
from app.repositories import materials as materials_repo
from app.repositories.accounts import insert_account
from app.repositories.courses import add_member, create_course
from app.repositories.event_tickets import issue_ticket
from app.repositories.sqlite import connect, migrate
from app.services import materials as materials_service
from app.services.auth import issue_access_token
from app.services.chunking import chunk_blocks, chunking_version
from app.services.parsers.models import ParsedBlock, RevisionKey, SourceLocator

SECRET = "adr021-test-signing-key-0123456789abcdef"
VALID_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA"
PV = "txt/1+" + chunking_version(40, 10)

PROCESSING = ("queued", "parsing", "extracting", "merging", "persisting")
CONTRIBUTED = ("awaiting_review", "completed")


def _account(url: str, username: str, role: str):
    return insert_account(url, account_id=uuid.uuid4().hex, username=username, password_hash=VALID_HASH, role=role)


def _token(user) -> str:
    return issue_access_token(
        user_id=user.id, role=user.role, secret=SECRET.encode(), issued_at=int(time.time()), ttl_seconds=3600
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
        self.other_course = create_course(self.url, name="B", description=None, creator_id=self.outsider.id)
        add_member(self.url, course_id=self.course.id, user_id=self.student.id, role="student", added_by=self.teacher.id)
        monkeypatch.setenv("SQLITE_URL", self.url)
        monkeypatch.setenv("AUTH_JWT_SECRET", SECRET)
        monkeypatch.setenv("STORAGE_DIR", str(self.storage))
        monkeypatch.setenv("UPLOAD_MAX_BYTES", "1024")
        self.app = create_app()

    def headers(self, user) -> dict[str, str]:
        return {"Authorization": f"Bearer {_token(user)}"}

    def path(self, course_id: str | None = None) -> str:
        return f"/api/v1/courses/{course_id or self.course.id}/documents"

    def stored_files(self) -> list[str]:
        return sorted(p.name for p in self.storage.iterdir()) if self.storage.exists() else []

    def count(self, table: str, where: str = "", *params: object) -> int:
        with connect(self.url) as database:
            return database.execute(f"SELECT count(*) FROM {table} {where}", params).fetchone()[0]

    def sql(self, statement: str, *params: object) -> None:
        with connect(self.url) as database:
            database.execute(statement, params)


@pytest.fixture
def world(tmp_path, monkeypatch) -> World:
    return World(tmp_path, monkeypatch)


@pytest.fixture
def client(world):
    with TestClient(world.app) as test_client:
        yield test_client


def upload(client, world, course_id=None, user=None) -> dict[str, str]:
    response = client.post(
        world.path(course_id),
        headers=world.headers(user or world.teacher),
        files={"file": ("notes.txt", b"course notes", "text/plain")},
    )
    assert response.status_code == 202, response.text
    return response.json()


def set_stage(world: World, task_id: str, stage: str, *, cleanup_pending: bool = False) -> None:
    """把任务直接置为某阶段（测试夹具；满足迁移 003/005 的约束）。"""
    progress = 0 if stage == "queued" else 0.5
    cancel = 1 if stage == "cancelled" else 0
    failed = stage == "failed"
    world.sql(
        """UPDATE processing_tasks
           SET stage = ?, progress = ?, cancel_requested = ?, cleanup_pending = ?,
               error_code = ?, error_message = ?
           WHERE id = ?""",
        stage,
        progress,
        cancel,
        1 if cleanup_pending else 0,
        "INTERNAL_ERROR" if failed else None,
        "处理失败" if failed else None,
        task_id,
    )


def add_task(world: World, document_id: str, stage: str, *, created_at: str, course_id: str | None = None) -> str:
    task_id = uuid.uuid4().hex
    world.sql(
        """INSERT INTO processing_tasks (id, course_id, document_id, created_at, updated_at, idempotency_key)
           VALUES (?, ?, ?, ?, ?, ?)""",
        task_id,
        course_id or world.course.id,
        document_id,
        created_at,
        created_at,
        uuid.uuid4().hex,
    )
    set_stage(world, task_id, stage)
    return task_id


def add_chunks(world: World, document_id: str, task_id: str) -> None:
    blocks = [ParsedBlock(0, "栈是一种后进先出的线性表。", SourceLocator(section_titles=("第3章",)))]
    chunk_store.persist_revision_chunks(
        world.url,
        course_id=world.course.id,
        task_id=task_id,
        key=RevisionKey(document_id=document_id, content_hash="sha256:" + "a" * 64, parser_version=PV),
        chunks=chunk_blocks(blocks, target_chars=40, overlap_chars=10),
    )


def delete(client, world, document_id: str, user=None, course_id=None):
    headers = world.headers(user or world.teacher) if user is not False else {}
    return client.delete(f"{world.path(course_id)}/{document_id}", headers=headers)


def listed(client, world) -> list[dict[str, object]]:
    response = client.get(world.path(), headers=world.headers(world.teacher))
    assert response.status_code == 200
    return response.json()


# ---------------------------------------------------------------- Document.task_id


def test_list_includes_latest_task_id(client, world):
    accepted = upload(client, world)

    (item,) = listed(client, world)

    assert item["task_id"] == accepted["task_id"]
    assert item["parse_status"] == "queued"


def test_task_id_follows_the_same_latest_task_as_parse_status(client, world):
    accepted = upload(client, world)
    set_stage(world, accepted["task_id"], "failed")
    newer = add_task(world, accepted["document_id"], "parsing", created_at="2999-01-01T00:00:00.000Z")

    (item,) = listed(client, world)

    assert (item["task_id"], item["parse_status"]) == (newer, "parsing")


def test_task_id_is_null_without_any_task(client, world):
    materials_repo_insert(world)

    (item,) = listed(client, world)

    assert item["task_id"] is None
    assert item["parse_status"] == "queued"


def materials_repo_insert(world: World) -> str:
    material_id = uuid.uuid4().hex
    with connect(world.url) as database:
        materials_repo.insert_material(
            database,
            material_id=material_id,
            course_id=world.course.id,
            filename="m.txt",
            format="txt",
            size_bytes=5,
            content_hash="sha256:" + "b" * 64,
            storage_name=uuid.uuid4().hex + ".txt",
        )
    return material_id


# ---------------------------------------------------------------- 删除：成功路径


@pytest.mark.parametrize("stage", ["failed", "cancelled"])
def test_teacher_deletes_material_whose_tasks_all_ended_without_contribution(client, world, stage):
    accepted = upload(client, world)
    task_id, document_id = accepted["task_id"], accepted["document_id"]
    add_chunks(world, document_id, task_id)
    issue_ticket(world.url, user_id=world.teacher.id, task_id=task_id, now=time.time())
    set_stage(world, task_id, stage)
    world.sql(
        "INSERT INTO model_calls (call_id, status, course_id, task_id, purpose, provider_role, is_repair,"
        " model_requested, input_tokens_est, max_output_tokens)"
        " VALUES (?, 'sent', ?, ?, 'extract_entities', 'primary', 0, 'm', 1, 1)",
        "call-1",
        world.course.id,
        task_id,
    )
    assert world.stored_files() and world.count("chunks") == 1

    response = delete(client, world, document_id)

    assert response.status_code == 204
    assert response.content == b""
    assert listed(client, world) == []
    for table in ("materials", "processing_tasks", "material_revisions", "task_revisions", "chunks", "event_tickets"):
        assert world.count(table) == 0, table
    assert world.stored_files() == []
    assert world.count("model_calls") == 1  # 预算与审计记录保留


def test_delete_with_several_ended_tasks_removes_all_of_them(client, world):
    accepted = upload(client, world)
    set_stage(world, accepted["task_id"], "failed")
    add_task(world, accepted["document_id"], "cancelled", created_at="2999-01-01T00:00:00.000Z")

    assert delete(client, world, accepted["document_id"]).status_code == 204
    assert world.count("processing_tasks") == 0


def test_delete_material_without_any_task(client, world):
    material_id = materials_repo_insert(world)

    assert delete(client, world, material_id).status_code == 204
    assert world.count("materials") == 0


def test_delete_only_touches_the_target_material(client, world):
    keep = upload(client, world)
    gone = upload(client, world)
    set_stage(world, gone["task_id"], "cancelled")
    other = upload(client, world, course_id=world.other_course.id, user=world.outsider)
    set_stage(world, other["task_id"], "cancelled")

    assert delete(client, world, gone["document_id"]).status_code == 204

    assert [item["id"] for item in listed(client, world)] == [keep["document_id"]]
    assert world.count("materials") == 2
    assert len(world.stored_files()) == 2


def test_file_deletion_failure_after_commit_still_returns_204(client, world, monkeypatch, caplog):
    accepted = upload(client, world)
    set_stage(world, accepted["task_id"], "failed")

    def broken(self, storage_name):
        raise materials_service.StorageWriteError()

    monkeypatch.setattr(materials_service.FileStorage, "delete", broken)

    assert delete(client, world, accepted["document_id"]).status_code == 204
    assert world.count("materials") == 0
    assert len(world.stored_files()) == 1  # 孤儿文件留给运维清理
    assert any("orphan" in record.getMessage() for record in caplog.records)


# ---------------------------------------------------------------- 删除：拒绝路径


@pytest.mark.parametrize("stage", PROCESSING)
def test_material_with_unfinished_task_is_not_deletable(client, world, stage):
    accepted = upload(client, world)
    set_stage(world, accepted["task_id"], stage)

    response = delete(client, world, accepted["document_id"])

    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "DOCUMENT_NOT_DELETABLE"
    assert body["details"] == {"stage": stage, "reason": "processing"}
    assert world.count("materials") == 1 and world.stored_files()


@pytest.mark.parametrize("stage", CONTRIBUTED)
def test_material_that_reached_review_is_not_deletable(client, world, stage):
    accepted = upload(client, world)
    set_stage(world, accepted["task_id"], stage)

    response = delete(client, world, accepted["document_id"])

    assert response.status_code == 409
    assert response.json()["details"] == {"stage": stage, "reason": "contributed"}


def test_older_contributing_task_blocks_even_if_latest_failed(client, world):
    accepted = upload(client, world)
    set_stage(world, accepted["task_id"], "completed")
    add_task(world, accepted["document_id"], "failed", created_at="2999-01-01T00:00:00.000Z")

    response = delete(client, world, accepted["document_id"])

    assert response.status_code == 409
    assert response.json()["details"] == {"stage": "completed", "reason": "contributed"}
    assert world.count("processing_tasks") == 2


def test_failed_task_with_pending_cleanup_blocks(client, world):
    accepted = upload(client, world)
    set_stage(world, accepted["task_id"], "failed", cleanup_pending=True)

    response = delete(client, world, accepted["document_id"])

    assert response.status_code == 409
    assert response.json()["details"] == {"stage": "failed", "reason": "cleanup_pending"}


def test_processing_takes_priority_over_contributed(client, world):
    accepted = upload(client, world)
    set_stage(world, accepted["task_id"], "completed")
    add_task(world, accepted["document_id"], "parsing", created_at="2999-01-01T00:00:00.000Z")

    assert delete(client, world, accepted["document_id"]).json()["details"] == {
        "stage": "parsing",
        "reason": "processing",
    }


def test_blocking_stage_is_taken_from_the_latest_created_task(client, world):
    accepted = upload(client, world)
    set_stage(world, accepted["task_id"], "awaiting_review")
    add_task(world, accepted["document_id"], "completed", created_at="2999-01-01T00:00:00.000Z")

    assert delete(client, world, accepted["document_id"]).json()["details"] == {
        "stage": "completed",
        "reason": "contributed",
    }


def test_missing_material_is_404(client, world):
    response = delete(client, world, "no-such-document")

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_material_of_another_course_is_404_through_own_course_path(client, world):
    other = upload(client, world, course_id=world.other_course.id, user=world.outsider)
    set_stage(world, other["task_id"], "cancelled")

    response = delete(client, world, other["document_id"])

    assert response.status_code == 404
    assert world.count("materials") == 1


def test_second_delete_is_404(client, world):
    accepted = upload(client, world)
    set_stage(world, accepted["task_id"], "cancelled")

    assert delete(client, world, accepted["document_id"]).status_code == 204
    assert delete(client, world, accepted["document_id"]).status_code == 404


@pytest.mark.parametrize(
    ("who", "status", "code"),
    [
        ("anonymous", 401, "UNAUTHENTICATED"),
        ("student", 403, "ROLE_FORBIDDEN"),
        ("outsider", 403, "COURSE_FORBIDDEN"),
    ],
)
def test_access_matrix(client, world, who, status, code):
    accepted = upload(client, world)
    set_stage(world, accepted["task_id"], "cancelled")
    user = {"anonymous": False, "student": world.student, "outsider": world.outsider}[who]

    response = delete(client, world, accepted["document_id"], user=user)

    assert response.status_code == status
    assert response.json()["code"] == code
    assert world.count("materials") == 1


# ---------------------------------------------------------------- 仓储与契约


def test_openapi_exposes_delete_operation(world):
    operation = world.app.openapi()["paths"]["/api/v1/courses/{cid}/documents/{did}"]["delete"]

    assert operation["operationId"] == "deleteDocument"
    assert {"204", "404", "409"} <= set(operation["responses"])
