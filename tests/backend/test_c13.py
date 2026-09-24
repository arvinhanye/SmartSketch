"""C13: local account login and HS256 access-token issuance (specs/identity-access.md §1–§2.1)."""

import base64
import hashlib
import hmac
import json
import logging
import os
import socket
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import SettingsError, check_auth_settings, load_settings
from app.main import create_app
from app.repositories.accounts import DuplicateUsername, find_by_username
from app.repositories.sqlite import migrate
from app.services import auth as auth_service
from app.services.auth import (
    AccountValidationError,
    LoginRateLimiter,
    create_account,
    hash_password,
    verify_password,
)

BACKEND = Path(__file__).resolve().parents[2] / "src" / "backend"
SECRET = "c13-test-signing-key-0123456789abcdefghij"  # 41 bytes, test only
PASSWORD = "correct-horse-battery"
LOGIN = "/api/v1/auth/login"
VALID_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA"


class FakeClock:
    def __init__(self, now: float) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def _url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def _b64decode(segment: str) -> bytes:
    return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))


def _decode(token: str) -> tuple[dict, dict, bytes, bytes]:
    header, payload, signature = token.split(".")
    return (
        json.loads(_b64decode(header)),
        json.loads(_b64decode(payload)),
        f"{header}.{payload}".encode("ascii"),
        _b64decode(signature),
    )


@pytest.fixture
def db_url(tmp_path):
    url = _url(tmp_path / "state.sqlite3")
    migrate(url)
    return url


@pytest.fixture
def clocks():
    return {"wall": FakeClock(1_900_000_000.0), "mono": FakeClock(1000.0)}


@pytest.fixture
def client(db_url, clocks, monkeypatch):
    monkeypatch.setenv("SQLITE_URL", db_url)
    monkeypatch.setenv("AUTH_JWT_SECRET", SECRET)
    monkeypatch.delenv("AUTH_ACCESS_TOKEN_TTL_SECONDS", raising=False)
    application = create_app()
    application.state.login_limiter = LoginRateLimiter(clock=clocks["mono"])
    application.state.auth_clock = clocks["wall"]
    with TestClient(application) as test_client:
        yield test_client


@pytest.fixture
def teacher(db_url):
    return create_account(db_url, "Demo_Teacher", PASSWORD, "teacher")


def _disable(db_url: str, user_id: str) -> None:
    with sqlite3.connect(db_url.removeprefix("sqlite:///")) as database:
        database.execute(
            "UPDATE users SET disabled_at = '2026-09-24T00:00:00Z' WHERE id = ?", (user_id,)
        )


def _count_verifications(monkeypatch) -> list[str]:
    calls: list[str] = []
    original = auth_service.verify_password

    def counting(stored: str, password: str) -> bool:
        calls.append(stored)
        return original(stored, password)

    monkeypatch.setattr(auth_service, "verify_password", counting)
    return calls


# --- migration 002 -----------------------------------------------------------------------


def test_migration_002_adds_users_after_001_and_keeps_a_restorable_backup(tmp_path):
    path = tmp_path / "state.sqlite3"
    base_only = tmp_path / "base-only"
    base_only.mkdir()
    (base_only / "001_base.sql").write_bytes((BACKEND / "migrations" / "001_base.sql").read_bytes())
    assert migrate(_url(path), base_only) == ["001"]
    with sqlite3.connect(path) as database:
        database.execute("INSERT INTO embedding_space_state VALUES (1, 'model-a', 768, 0)")

    assert migrate(_url(path)) == ["002"]
    assert migrate(_url(path)) == []

    with sqlite3.connect(path) as database:
        columns = {row[1] for row in database.execute("PRAGMA table_info(users)")}
        assert database.execute("SELECT model FROM embedding_space_state").fetchone() == ("model-a",)
        assert [row[0] for row in database.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        )] == ["001", "002"]
    assert columns == {"id", "username", "password_hash", "role", "created_at", "disabled_at"}

    backup = next((tmp_path / "backups").glob("*-before-002.sqlite"))
    with sqlite3.connect(backup) as copy:
        assert copy.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert copy.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'users'"
        ).fetchone() is None
        assert copy.execute("SELECT model FROM embedding_space_state").fetchone() == ("model-a",)


@pytest.mark.parametrize(
    ("username", "password_hash", "role"),
    [
        ("plain", "correct-horse-battery", "student"),  # plaintext never fits the argon2id format
        ("UPPER", VALID_HASH, "student"),
        ("bad name", VALID_HASH, "student"),
        ("ab", VALID_HASH, "student"),
        ("ok_user", VALID_HASH, "admin"),
        ("ok_user", "$2b$12$bcrypthashbcrypthashbcrypthashbcrypthashbcrypthashbcry", "student"),
    ],
)
def test_users_table_rejects_rows_breaking_the_account_rules(db_url, username, password_hash, role):
    with sqlite3.connect(db_url.removeprefix("sqlite:///")) as database:
        with pytest.raises(sqlite3.IntegrityError):
            database.execute(
                "INSERT INTO users (id, username, password_hash, role) VALUES (?, ?, ?, ?)",
                ("0" * 32, username, password_hash, role),
            )
        # the same statement with valid values succeeds, so each case fails for its own reason
        database.execute(
            "INSERT INTO users (id, username, password_hash, role) VALUES (?, ?, ?, ?)",
            ("1" * 32, "ok_user", VALID_HASH, "student"),
        )


# --- accounts and password hashing ------------------------------------------------------


def test_create_account_stores_argon2id_hash_and_random_id(db_url):
    account = create_account(db_url, "Demo_Student", PASSWORD, "student")

    assert account.username == "demo_student"
    assert account.role == "student"
    assert account.disabled_at is None
    assert not account.id.isdigit() and len(account.id) >= 32
    assert account.password_hash.startswith("$argon2id$")
    assert PASSWORD not in account.password_hash
    assert find_by_username(db_url, "demo_student") == account
    with sqlite3.connect(db_url.removeprefix("sqlite:///")) as database:
        stored = database.execute("SELECT password_hash FROM users").fetchone()[0]
    assert stored == account.password_hash
    assert verify_password(stored, PASSWORD)
    assert not verify_password(stored, PASSWORD + "x")


def test_hashes_are_salted_and_invalid_hashes_never_verify():
    first, second = hash_password(PASSWORD), hash_password(PASSWORD)
    assert first != second
    assert not verify_password("not-a-hash", PASSWORD)


@pytest.mark.parametrize(
    ("username", "password", "role"),
    [
        ("ab", PASSWORD, "student"),
        ("x" * 33, PASSWORD, "student"),
        ("bad name", PASSWORD, "student"),
        ("ok_user", "short7!", "student"),
        ("ok_user", "p" * 129, "student"),
        ("ok_user", PASSWORD, "admin"),
    ],
)
def test_create_account_rejects_invalid_input_without_writing(db_url, username, password, role):
    with pytest.raises(AccountValidationError):
        create_account(db_url, username, password, role)
    assert find_by_username(db_url, "ok_user") is None


def test_create_account_rejects_case_insensitive_duplicates(db_url, teacher):
    with pytest.raises(DuplicateUsername):
        create_account(db_url, "DEMO_TEACHER", "another-password", "student")


# --- login success ------------------------------------------------------------------------


def test_correct_password_returns_contract_shaped_login_response(client, teacher):
    response = client.post(LOGIN, json={"username": "demo_teacher", "password": PASSWORD})

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"access_token", "token_type", "expires_in", "user"}
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 28800
    assert body["user"] == {"id": teacher.id, "username": "demo_teacher", "role": "teacher"}


def test_token_is_hs256_with_exactly_sub_role_iat_exp(client, teacher, clocks):
    token = client.post(LOGIN, json={"username": "demo_teacher", "password": PASSWORD}).json()[
        "access_token"
    ]
    header, payload, signed, signature = _decode(token)

    assert header == {"alg": "HS256", "typ": "JWT"}
    assert payload == {
        "sub": teacher.id,
        "role": "teacher",
        "iat": int(clocks["wall"].now),
        "exp": int(clocks["wall"].now) + 28800,
    }
    assert hmac.compare_digest(
        signature, hmac.new(SECRET.encode(), signed, hashlib.sha256).digest()
    )
    assert not hmac.compare_digest(
        signature, hmac.new(b"x" * 41, signed, hashlib.sha256).digest()
    )


def test_ttl_comes_from_environment(db_url, teacher, monkeypatch):
    monkeypatch.setenv("SQLITE_URL", db_url)
    monkeypatch.setenv("AUTH_JWT_SECRET", SECRET)
    monkeypatch.setenv("AUTH_ACCESS_TOKEN_TTL_SECONDS", "60")
    with TestClient(create_app()) as test_client:
        body = test_client.post(
            LOGIN, json={"username": "demo_teacher", "password": PASSWORD}
        ).json()
    _, payload, _, _ = _decode(body["access_token"])
    assert body["expires_in"] == 60
    assert payload["exp"] - payload["iat"] == 60


@pytest.mark.parametrize("value", ["0", "-1", "abc", "1.5"])
def test_invalid_ttl_names_the_variable(value):
    with pytest.raises(SettingsError, match="AUTH_ACCESS_TOKEN_TTL_SECONDS"):
        load_settings({"AUTH_ACCESS_TOKEN_TTL_SECONDS": value})


def test_username_is_matched_case_insensitively(client, teacher):
    for username in ("Demo_Teacher", "demo_teacher", "DEMO_TEACHER"):
        response = client.post(LOGIN, json={"username": username, "password": PASSWORD})
        assert response.status_code == 200
        assert response.json()["user"]["id"] == teacher.id


# --- login failures -----------------------------------------------------------------------


def test_wrong_password_unknown_user_and_disabled_account_are_indistinguishable(
    client, teacher, db_url, monkeypatch
):
    create_account(db_url, "retired", PASSWORD, "student")
    _disable(db_url, find_by_username(db_url, "retired").id)
    verifications = _count_verifications(monkeypatch)

    responses = [
        client.post(LOGIN, json={"username": "demo_teacher", "password": "wrong-password"}),
        client.post(LOGIN, json={"username": "nobody_here", "password": PASSWORD}),
        client.post(LOGIN, json={"username": "retired", "password": PASSWORD}),
        client.post(LOGIN, json={"username": "Not A Valid Name!", "password": PASSWORD}),
    ]

    assert {response.status_code for response in responses} == {401}
    bodies = [response.content for response in responses]
    assert len(set(bodies)) == 1
    assert json.loads(bodies[0])["code"] == "UNAUTHENTICATED"
    assert "access_token" not in json.loads(bodies[0])
    # every path runs exactly one slow-hash verification, unknown users against the dummy hash
    assert len(verifications) == 4
    assert all(stored.startswith("$argon2id$") for stored in verifications)


def test_disabled_account_cannot_log_in_after_previous_success(client, teacher, db_url):
    assert client.post(LOGIN, json={"username": "demo_teacher", "password": PASSWORD}).status_code == 200
    _disable(db_url, teacher.id)
    response = client.post(LOGIN, json={"username": "demo_teacher", "password": PASSWORD})
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHENTICATED"


def test_request_shape_errors_are_rejected_before_authentication(client):
    assert client.post(LOGIN, json={"username": "demo_teacher"}).status_code == 422
    assert client.post(LOGIN, json={"password": PASSWORD}).status_code == 422
    assert client.get(LOGIN).status_code == 405


# --- rate limiting ------------------------------------------------------------------------


def test_sixth_attempt_within_60_seconds_is_rate_limited_without_checking_password(
    client, teacher, clocks, monkeypatch
):
    for _ in range(5):
        wrong = client.post(LOGIN, json={"username": "demo_teacher", "password": "wrong-password"})
        assert wrong.status_code == 401
    verifications = _count_verifications(monkeypatch)
    clocks["mono"].now += 59

    limited = client.post(LOGIN, json={"username": "DEMO_teacher", "password": PASSWORD})

    assert limited.status_code == 429
    assert limited.json()["code"] == "RATE_LIMITED"
    assert "access_token" not in limited.json()
    assert limited.headers["Retry-After"] == "1"
    assert verifications == []

    clocks["mono"].now += 1
    assert client.post(LOGIN, json={"username": "demo_teacher", "password": PASSWORD}).status_code == 200


def test_unknown_username_is_limited_exactly_like_an_existing_one(client, teacher):
    def attempts(username: str) -> list[tuple[int, bytes]]:
        return [
            (response.status_code, response.content)
            for response in (
                client.post(LOGIN, json={"username": username, "password": "wrong-password"})
                for _ in range(6)
            )
        ]

    existing, unknown = attempts("demo_teacher"), attempts("ghost_user")
    assert [status for status, _ in existing] == [401] * 5 + [429]
    assert existing == unknown


def test_limit_is_per_username_and_success_clears_the_counter(client, teacher, db_url):
    create_account(db_url, "other_user", PASSWORD, "student")
    for _ in range(4):
        client.post(LOGIN, json={"username": "demo_teacher", "password": "wrong-password"})
    assert client.post(LOGIN, json={"username": "demo_teacher", "password": PASSWORD}).status_code == 200
    for _ in range(4):
        assert client.post(
            LOGIN, json={"username": "demo_teacher", "password": "wrong-password"}
        ).status_code == 401
    for _ in range(5):
        client.post(LOGIN, json={"username": "ghost_user", "password": "wrong-password"})
    assert client.post(LOGIN, json={"username": "other_user", "password": PASSWORD}).status_code == 200


def test_limiter_lock_expires_and_capacity_evicts_least_recently_used():
    clock = FakeClock(0.0)
    limiter = LoginRateLimiter(clock=clock, capacity=2)
    for _ in range(5):
        limiter.record_failure("a")
    assert limiter.retry_after("a") == 60
    clock.now = 30.5
    assert limiter.retry_after("a") == 30
    clock.now = 60.0
    assert limiter.retry_after("a") is None
    limiter.record_failure("a")  # a fresh streak after the lock expired
    assert limiter.retry_after("a") is None

    for _ in range(5):
        limiter.record_failure("b")
    limiter.record_failure("c")
    limiter.record_failure("d")  # evicts the least recently used key ("b")
    assert limiter.retry_after("b") is None
    assert len(limiter) == 2


def test_limiter_bounds_key_length_for_impossible_usernames(client):
    for index in range(3):
        client.post(LOGIN, json={"username": "z" * 40 + str(index), "password": "wrong-password"})
    assert len(client.app.state.login_limiter) == 1


# --- configuration and startup ------------------------------------------------------------


@pytest.mark.parametrize("value", [None, "", " " * 40, "s" * 31, "密" * 10])
def test_missing_or_short_signing_secret_is_rejected(value):
    environ = {} if value is None else {"AUTH_JWT_SECRET": value}
    settings = load_settings(environ)
    with pytest.raises(SettingsError, match="AUTH_JWT_SECRET") as error:
        check_auth_settings(settings)
    if value and value.strip():
        assert value not in str(error.value)


@pytest.mark.parametrize("value", ["s" * 32, "密" * 11])
def test_signing_secret_of_at_least_32_bytes_is_accepted(value):
    check_auth_settings(load_settings({"AUTH_JWT_SECRET": value}))


def _entry_env(secret: str | None) -> dict[str, str]:
    env = {key: val for key, val in os.environ.items() if key != "AUTH_JWT_SECRET"}
    env["PYTHONPATH"] = str(BACKEND)
    if secret is not None:
        env["AUTH_JWT_SECRET"] = secret
    return env


@pytest.mark.parametrize("secret", [None, "short-secret-canary"])
def test_api_entry_points_refuse_to_start_without_a_valid_secret(secret):
    imported = subprocess.run(
        [sys.executable, "-c", "import app.main"],
        env=_entry_env(secret), capture_output=True, text=True, check=False, timeout=60,
    )
    assert imported.returncode != 0
    assert "AUTH_JWT_SECRET" in imported.stderr
    if secret:
        assert secret not in imported.stderr

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    served = subprocess.run(
        [sys.executable, "-m", "app"],
        env={**_entry_env(secret), "API_PORT": str(port)},
        capture_output=True, text=True, check=False, timeout=60,
    )
    assert served.returncode != 0
    assert "AUTH_JWT_SECRET" in served.stderr + served.stdout


def test_api_entry_module_imports_with_a_valid_secret():
    result = subprocess.run(
        [sys.executable, "-c", "import app.main"],
        env=_entry_env(SECRET), capture_output=True, text=True, check=False, timeout=60,
    )
    assert result.returncode == 0, result.stderr


def test_factory_app_without_secret_never_issues_a_token(db_url, teacher, monkeypatch):
    monkeypatch.setenv("SQLITE_URL", db_url)
    monkeypatch.delenv("AUTH_JWT_SECRET", raising=False)
    with TestClient(create_app(), raise_server_exceptions=False) as test_client:
        response = test_client.post(LOGIN, json={"username": "demo_teacher", "password": PASSWORD})
    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_ERROR"
    assert "access_token" not in response.json()


def test_password_and_token_never_reach_logs(client, teacher, caplog):
    caplog.set_level(logging.DEBUG)
    token = client.post(LOGIN, json={"username": "demo_teacher", "password": PASSWORD}).json()[
        "access_token"
    ]
    client.post(LOGIN, json={"username": "demo_teacher", "password": "wrong-password-canary"})

    assert PASSWORD not in caplog.text
    assert "wrong-password-canary" not in caplog.text
    assert token not in caplog.text
    assert SECRET not in caplog.text


def test_login_operation_matches_contract(client):
    operation = client.app.openapi()["paths"][LOGIN]["post"]

    assert operation["operationId"] == "login"
    assert not operation.get("security")
    assert {"200", "401", "422", "429"} <= set(operation["responses"])
    schemas = client.app.openapi()["components"]["schemas"]
    request_ref = operation["requestBody"]["content"]["application/json"]["schema"]["$ref"]
    assert set(schemas[request_ref.split("/")[-1]]["required"]) == {"username", "password"}
    response_ref = operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    assert set(schemas[response_ref.split("/")[-1]]["required"]) == {
        "access_token", "token_type", "user"
    }
