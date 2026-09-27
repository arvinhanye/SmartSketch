"""ADR-079: student self-registration (POST /api/v1/auth/register)."""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.repositories.accounts import find_by_username
from app.repositories.sqlite import migrate
from app.services.auth import RegistrationRateLimiter, create_account

SECRET = "adr079-test-signing-key-0123456789abcdefgh"  # test only
PASSWORD = "correct-horse-battery"
REGISTER = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"


class FakeClock:
    def __init__(self, now: float) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def db_url(tmp_path):
    url = f"sqlite:///{(tmp_path / 'state.sqlite3').as_posix()}"
    migrate(url)
    return url


@pytest.fixture
def clock():
    return FakeClock(1000.0)


@pytest.fixture
def app(db_url, clock, monkeypatch):
    monkeypatch.setenv("SQLITE_URL", db_url)
    monkeypatch.setenv("AUTH_JWT_SECRET", SECRET)
    application = create_app()
    application.state.registration_limiter = RegistrationRateLimiter(
        clock=clock, max_attempts=3, window_seconds=60
    )
    return application


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client


def _user_count(db_url: str) -> int:
    with sqlite3.connect(db_url.removeprefix("sqlite:///")) as database:
        return database.execute("SELECT COUNT(*) FROM users").fetchone()[0]


def test_register_creates_a_student_and_signs_in(client, db_url):
    response = client.post(REGISTER, json={"username": "Li_Xiaoming", "password": PASSWORD})

    assert response.status_code == 201
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["username"] == "li_xiaoming"
    assert body["user"]["role"] == "student"
    stored = find_by_username(db_url, "li_xiaoming")
    assert stored is not None and stored.role == "student" and stored.disabled_at is None
    assert PASSWORD not in stored.password_hash

    # the issued token works on a protected endpoint, and the password logs in afterwards
    courses = client.get("/api/v1/courses", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert courses.status_code == 200 and courses.json() == []
    login = client.post(LOGIN, json={"username": "li_xiaoming", "password": PASSWORD})
    assert login.status_code == 200 and login.json()["user"]["id"] == body["user"]["id"]


def test_register_never_creates_a_teacher(client, db_url):
    response = client.post(
        REGISTER, json={"username": "sneaky", "password": PASSWORD, "role": "teacher"}
    )

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert _user_count(db_url) == 0


def test_register_rejects_a_taken_username_case_insensitively(client, db_url):
    create_account(db_url, "demo_teacher", PASSWORD, "teacher")

    response = client.post(REGISTER, json={"username": "Demo_Teacher", "password": "another-pass-123"})

    assert response.status_code == 409
    assert response.json() == {"code": "USERNAME_TAKEN", "message": "用户名已被占用"}
    assert find_by_username(db_url, "demo_teacher").role == "teacher"
    assert _user_count(db_url) == 1


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"username": "ab", "password": PASSWORD}, "username"),
        ({"username": "a" * 33, "password": PASSWORD}, "username"),
        ({"username": "has space", "password": PASSWORD}, "username"),
        ({"username": "中文名字", "password": PASSWORD}, "username"),
        ({"username": "valid_name", "password": "pw7Tiny"}, "password"),
        ({"username": "valid_name", "password": "x" * 129}, "password"),
        ({"username": "valid_name"}, "password"),
    ],
)
def test_register_validates_fields_without_writing(client, db_url, body, field):
    response = client.post(REGISTER, json=body)

    assert response.status_code == 422
    payload = response.json()
    assert payload["code"] == "VALIDATION_ERROR"
    assert [item["field"] for item in payload["details"]["fields"]] == [field]
    assert PASSWORD not in response.text and "pw7Tiny" not in response.text
    assert _user_count(db_url) == 0


def test_register_is_rate_limited_per_window(client, db_url, clock):
    for index in range(3):
        assert client.post(REGISTER, json={"username": f"s{index}xx", "password": PASSWORD}).status_code == 201

    limited = client.post(REGISTER, json={"username": "s9xx", "password": PASSWORD})
    assert limited.status_code == 429
    assert limited.json()["code"] == "RATE_LIMITED"
    assert limited.headers["Retry-After"] == "60"
    assert find_by_username(db_url, "s9xx") is None

    clock.now += 60
    assert client.post(REGISTER, json={"username": "s9xx", "password": PASSWORD}).status_code == 201


def test_failed_attempts_count_toward_the_window(client, db_url, clock):
    create_account(db_url, "taken", PASSWORD, "student")
    for _ in range(3):
        assert client.post(REGISTER, json={"username": "taken", "password": PASSWORD}).status_code == 409

    assert client.post(REGISTER, json={"username": "fresh", "password": PASSWORD}).status_code == 429


def test_registration_limiter_reports_the_remaining_wait():
    clock = FakeClock(0.0)
    limiter = RegistrationRateLimiter(clock=clock, max_attempts=2, window_seconds=60)
    assert limiter.acquire() is None
    clock.now = 10.5
    assert limiter.acquire() is None
    clock.now = 30.0
    assert limiter.acquire() == 30  # oldest attempt at 0 leaves the window at 60
    clock.now = 60.0
    assert limiter.acquire() is None  # the attempt at 0 has expired
    assert limiter.acquire() == 11  # the attempt at 10.5 expires at 70.5


def test_register_is_public_in_the_openapi_document(app):
    operation = app.openapi()["paths"]["/api/v1/auth/register"]["post"]
    assert operation["operationId"] == "register"
    assert set(operation["responses"]) >= {"201", "409", "422", "429"}
