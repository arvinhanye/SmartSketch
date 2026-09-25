"""C16：SSE 一次性票据申领与核销（specs/identity-access.md §5）。

- 申领端点 ``POST /api/v1/tasks/{tid}/event-ticket`` 的授权矩阵、响应形状与只存哈希；
- 仓储层核销 ``redeem_ticket``（§5.2 第 1 步的条件 UPDATE），供 C11 的 GET SSE 端点使用；
- 迁移 006 只在临时目录上执行（不断言真实迁移目录全集），并演练备份恢复。
"""

from __future__ import annotations

import base64
import hashlib
import re
import shutil
import sqlite3
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.repositories import event_tickets
from app.repositories.accounts import insert_account
from app.repositories.courses import add_member, create_course
from app.repositories.sqlite import MIGRATIONS_DIR, connect, migrate, pending_migrations
from app.services.auth import issue_access_token

SECRET = "c16-test-signing-key-0123456789abcdefghij"
VALID_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA"
T0 = 1_900_000_000  # 固定时钟起点；全部时间由注入时钟决定，不 sleep
URL_SAFE = re.compile(r"^[A-Za-z0-9_-]+$")


def _url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


class Clock:
    def __init__(self, now: float) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def _insert_task(url: str, course_id: str, task_id: str) -> None:
    with connect(url) as db:
        db.execute(
            "INSERT INTO materials (id, course_id, filename, format, size_bytes, content_hash,"
            " storage_name) VALUES (?, ?, 'a.txt', 'txt', 1, ?, ?)",
            (f"doc-{task_id}", course_id, "sha256:" + "a" * 64, f"stored-{task_id}"),
        )
        db.execute(
            "INSERT INTO processing_tasks (id, course_id, document_id, idempotency_key)"
            " VALUES (?, ?, ?, ?)",
            (task_id, course_id, f"doc-{task_id}", f"key-{task_id}"),
        )


@pytest.fixture
def scenario(tmp_path, monkeypatch):
    url = _url(tmp_path / "state.sqlite3")
    migrate(url)

    def account(name: str, role: str):
        return insert_account(
            url, account_id=uuid.uuid4().hex, username=name, password_hash=VALID_HASH, role=role
        )

    teacher = account("teacher1", "teacher")
    student = account("student1", "student")
    outsider = account("teacher2", "teacher")
    course = create_course(url, name="A", description=None, creator_id=teacher.id)
    other_course = create_course(url, name="B", description=None, creator_id=outsider.id)
    add_member(url, course_id=course.id, user_id=student.id, role="student", added_by=teacher.id)
    _insert_task(url, course.id, "task1")
    _insert_task(url, course.id, "task2")
    _insert_task(url, other_course.id, "task-b")

    monkeypatch.setenv("SQLITE_URL", url)
    monkeypatch.setenv("AUTH_JWT_SECRET", SECRET)
    application = create_app()
    clock = Clock(T0)
    application.state.auth_clock = clock
    with TestClient(application) as client:
        yield {
            "client": client,
            "url": url,
            "clock": clock,
            "teacher": teacher,
            "student": student,
            "outsider": outsider,
        }


def bearer(user, *, now: int = T0) -> str:
    return issue_access_token(
        user_id=user.id, role=user.role, secret=SECRET.encode(), issued_at=now, ttl_seconds=3600
    )


def claim(client, tid: str, token: str | None = None):
    headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
    return client.post(f"/api/v1/tasks/{tid}/event-ticket", headers=headers)


def rows(url: str) -> list[tuple]:
    with connect(url) as db:
        return db.execute(
            "SELECT ticket_hash, user_id, task_id, expires_at, used_at, created_at"
            " FROM event_tickets ORDER BY created_at, ticket_hash"
        ).fetchall()


# --- 申领：响应形状、只存哈希 ------------------------------------------------------------------


def test_teacher_claims_ticket_and_only_its_sha256_is_stored(scenario, tmp_path):
    client, url, teacher = scenario["client"], scenario["url"], scenario["teacher"]
    token = bearer(teacher)
    response = claim(client, "task1", token)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"ticket", "expires_in"}
    assert body["expires_in"] == 60
    ticket = body["ticket"]
    assert URL_SAFE.fullmatch(ticket) and len(ticket) >= 22
    raw = base64.urlsafe_b64decode(ticket + "=" * (-len(ticket) % 4))
    assert len(raw) * 8 >= 128
    # 响应不回显访问令牌、用户或票据哈希
    text = response.text
    digest = hashlib.sha256(ticket.encode("ascii")).hexdigest()
    for secret in (token, teacher.id, digest):
        assert secret not in text
    assert "no-store" in response.headers.get("cache-control", "")

    assert rows(url) == [(digest, teacher.id, "task1", T0 + 60, None, T0)]

    # 数据库任何位置都查不到明文（逻辑转储 + 主库/WAL 原始字节）
    with connect(url) as db:
        dump = "\n".join(db.iterdump())
    assert ticket not in dump
    for suffix in ("", "-wal"):
        file = tmp_path / f"state.sqlite3{suffix}"
        if file.exists():
            assert ticket.encode("ascii") not in file.read_bytes()

    second = claim(client, "task1", token).json()["ticket"]
    assert second != ticket
    assert len(rows(url)) == 2


# --- 授权矩阵：issueEventTicket 行 -------------------------------------------------------------


@pytest.mark.parametrize(
    "who,tid,status,code",
    [
        ("anonymous", "task1", 401, "UNAUTHENTICATED"),
        ("garbage", "task1", 401, "UNAUTHENTICATED"),
        ("outsider", "task1", 404, "NOT_FOUND"),
        ("outsider", "missing", 404, "NOT_FOUND"),
        ("teacher", "missing", 404, "NOT_FOUND"),
        ("teacher", "task-b", 404, "NOT_FOUND"),
        ("student", "task1", 403, "ROLE_FORBIDDEN"),
    ],
)
def test_denied_claims_follow_matrix_and_write_nothing(scenario, who, tid, status, code):
    client, url = scenario["client"], scenario["url"]
    if who == "anonymous":
        token = None
    elif who == "garbage":
        token = "not.a.jwt"
    else:
        token = bearer(scenario[who])
    response = claim(client, tid, token)
    assert response.status_code == status
    assert response.json()["code"] == code
    assert set(response.json()) == {"code", "message"}
    assert "ticket" not in response.text and tid not in response.text
    assert rows(url) == []


def test_nonmember_and_missing_task_are_indistinguishable(scenario):
    client, outsider = scenario["client"], scenario["outsider"]
    denied = claim(client, "task1", bearer(outsider))
    missing = claim(client, "missing", bearer(outsider))
    assert denied.status_code == missing.status_code == 404
    assert denied.json() == missing.json()


def test_disabled_teacher_cannot_claim(scenario):
    from app.repositories.accounts import set_disabled

    client, url, teacher = scenario["client"], scenario["url"], scenario["teacher"]
    token = bearer(teacher)
    set_disabled(url, "teacher1", True)
    response = claim(client, "task1", token)
    assert (response.status_code, response.json()["code"]) == (401, "UNAUTHENTICATED")
    assert rows(url) == []


# --- 核销（C11 使用）---------------------------------------------------------------------------


def _issued(scenario, tid: str = "task1") -> str:
    return claim(scenario["client"], tid, bearer(scenario["teacher"])).json()["ticket"]


def test_ticket_redeems_once_then_is_rejected(scenario):
    url, teacher = scenario["url"], scenario["teacher"]
    ticket = _issued(scenario)
    assert event_tickets.redeem_ticket(url, ticket=ticket, task_id="task1", now=T0 + 1) == teacher.id
    assert rows(url)[0][4] == T0 + 1  # used_at
    assert event_tickets.redeem_ticket(url, ticket=ticket, task_id="task1", now=T0 + 2) is None
    assert rows(url)[0][4] == T0 + 1


@pytest.mark.parametrize("elapsed,accepted", [(0, True), (59, True), (59.999, True), (60, False), (61, False), (7200, False)])
def test_ticket_expires_after_sixty_seconds(scenario, elapsed, accepted):
    url, teacher = scenario["url"], scenario["teacher"]
    ticket = _issued(scenario)
    result = event_tickets.redeem_ticket(url, ticket=ticket, task_id="task1", now=T0 + elapsed)
    assert result == (teacher.id if accepted else None)
    assert (rows(url)[0][4] is not None) is accepted


def test_claim_time_comes_from_injected_clock(scenario):
    url, clock = scenario["url"], scenario["clock"]
    clock.now = T0 + 500.7
    ticket = claim(scenario["client"], "task1", bearer(scenario["teacher"], now=T0 + 500)).json()["ticket"]
    assert rows(url)[0][3] - rows(url)[0][5] == 60
    assert rows(url)[0][5] == T0 + 500
    # 有效期不会因取整而超过 60 秒
    assert event_tickets.redeem_ticket(url, ticket=ticket, task_id="task1", now=T0 + 560.7) is None


def test_ticket_for_one_task_cannot_open_another_and_is_not_consumed(scenario):
    url, teacher = scenario["url"], scenario["teacher"]
    ticket = _issued(scenario, "task1")
    assert event_tickets.redeem_ticket(url, ticket=ticket, task_id="task2", now=T0 + 1) is None
    assert event_tickets.redeem_ticket(url, ticket=ticket, task_id="task-b", now=T0 + 1) is None
    assert rows(url)[0][4] is None
    assert event_tickets.redeem_ticket(url, ticket=ticket, task_id="task1", now=T0 + 1) == teacher.id


def test_bearer_token_or_stored_hash_is_not_a_ticket(scenario):
    url, teacher = scenario["url"], scenario["teacher"]
    ticket = _issued(scenario)
    token = bearer(teacher)
    stored_hash = rows(url)[0][0]
    for candidate in (token, stored_hash, "", "x" * 10_000, ticket + "x", ticket[:-1]):
        assert event_tickets.redeem_ticket(url, ticket=candidate, task_id="task1", now=T0 + 1) is None
    assert rows(url)[0][4] is None


def test_claim_deletes_rows_expired_more_than_one_hour_ago(scenario):
    url, clock, teacher = scenario["url"], scenario["clock"], scenario["teacher"]
    now = T0 + 10_000
    stale, boundary, fresh_used = ("a" * 64, "b" * 64, "c" * 64)
    with connect(url) as db:
        for ticket_hash, expires_at, used_at in (
            (stale, now - 3601, None),
            (boundary, now - 3600, now - 3630),
            (fresh_used, now - 10, now - 20),
        ):
            db.execute(
                "INSERT INTO event_tickets (ticket_hash, user_id, task_id, expires_at, used_at,"
                " created_at) VALUES (?, ?, 'task1', ?, ?, ?)",
                (ticket_hash, teacher.id, expires_at, used_at, expires_at - 60),
            )
    clock.now = now
    assert claim(scenario["client"], "task1", bearer(teacher, now=now)).status_code == 200
    kept = {row[0] for row in rows(url)}
    assert stale not in kept
    assert {boundary, fresh_used} <= kept
    assert len(kept) == 3


def test_schema_rejects_lifetimes_longer_than_sixty_seconds(scenario):
    url, teacher = scenario["url"], scenario["teacher"]
    with connect(url) as db, pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO event_tickets (ticket_hash, user_id, task_id, expires_at, created_at)"
            " VALUES (?, ?, 'task1', ?, ?)",
            ("d" * 64, teacher.id, T0 + 61, T0),
        )
    with connect(url) as db, pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO event_tickets (ticket_hash, user_id, task_id, expires_at, created_at)"
            " VALUES (?, ?, 'task1', ?, ?)",
            ("not-a-sha256", teacher.id, T0 + 60, T0),
        )


# --- 迁移 006：只在临时目录执行，并可恢复 -------------------------------------------------------


def test_migration_006_applies_on_temp_dir_and_backup_restores(tmp_path):
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    for name in ("001_base.sql", "002_accounts.sql", "003_tasks.sql", "004_courses.sql"):
        shutil.copyfile(MIGRATIONS_DIR / name, migrations / name)
    path = tmp_path / "state.sqlite3"
    url = _url(path)
    assert migrate(url, migrations) == ["001", "002", "003", "004"]

    shutil.copyfile(MIGRATIONS_DIR / "006_event_tickets.sql", migrations / "006_event_tickets.sql")
    assert migrate(url, migrations) == ["006"]
    assert migrate(url, migrations) == []
    with connect(url) as db:
        columns = [row[1] for row in db.execute("PRAGMA table_info(event_tickets)")]
        primary = [row[1] for row in db.execute("PRAGMA table_info(event_tickets)") if row[5]]
    assert columns == ["ticket_hash", "user_id", "task_id", "expires_at", "used_at", "created_at"]
    assert primary == ["ticket_hash"]

    # 回滚演练：停服后用迁移前备份覆盖主库（并移走 WAL 附属文件），006 重新变为待执行
    backup = next((tmp_path / "backups").glob("*-before-006.sqlite"))
    for suffix in ("-wal", "-shm"):
        (tmp_path / f"state.sqlite3{suffix}").unlink(missing_ok=True)
    shutil.copyfile(backup, path)
    with sqlite3.connect(path) as db:
        assert db.execute(
            "SELECT name FROM sqlite_master WHERE name = 'event_tickets'"
        ).fetchone() is None
        assert db.execute("SELECT max(version) FROM schema_migrations").fetchone() == ("004",)
    assert pending_migrations(url, migrations) == ["006"]
    assert migrate(url, migrations) == ["006"]
