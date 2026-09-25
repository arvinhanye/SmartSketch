"""C14: account commands and idempotent demo-account seeding (specs/identity-access.md §1.2)."""

import importlib.util
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from app.config import load_settings
from app.repositories.accounts import find_by_username
from app.repositories.sqlite import migrate
from app.services import account_admin
from app.services.account_admin import (
    DEMO_ACCOUNTS,
    AccountNotFound,
    DemoSeedConflict,
)
from app.services.auth import (
    AccountValidationError,
    AuthService,
    InvalidCredentials,
    LoginRateLimiter,
    create_account,
    verify_password,
)

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
PASSWORD = "correct-horse-battery"
NEW_PASSWORD = "another-horse-battery"
SECRET = "c14-test-signing-key-0123456789abcdefghij"


def _url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def _load_script(name: str):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _rows(db_url: str) -> list[tuple]:
    with sqlite3.connect(db_url.removeprefix("sqlite:///")) as database:
        return database.execute(
            "SELECT id, username, password_hash, role, created_at, disabled_at FROM users"
            " ORDER BY username"
        ).fetchall()


@pytest.fixture
def db_url(tmp_path):
    url = _url(tmp_path / "state.sqlite3")
    migrate(url)
    return url


@pytest.fixture
def auth(db_url):
    settings = load_settings({"SQLITE_URL": db_url, "AUTH_JWT_SECRET": SECRET})
    return AuthService(settings, LoginRateLimiter())


# --- service: disable / enable / reset / list ---------------------------------------------


def test_disable_blocks_login_and_is_visible_in_listing(db_url, auth):
    create_account(db_url, "demo_teacher", PASSWORD, "teacher")
    auth.login("demo_teacher", PASSWORD)

    disabled = account_admin.set_disabled(db_url, "Demo_Teacher", True)

    assert disabled.disabled_at is not None
    with pytest.raises(InvalidCredentials):
        auth.login("demo_teacher", PASSWORD)
    [listed] = account_admin.list_accounts(db_url)
    assert (listed.username, listed.role, listed.disabled_at) == (
        "demo_teacher",
        "teacher",
        disabled.disabled_at,
    )


def test_disabling_twice_keeps_the_first_timestamp(db_url):
    create_account(db_url, "demo_student", PASSWORD, "student")
    first = account_admin.set_disabled(db_url, "demo_student", True)

    again = account_admin.set_disabled(db_url, "demo_student", True)

    assert again.disabled_at == first.disabled_at


def test_enable_restores_login_without_touching_other_columns(db_url, auth):
    create_account(db_url, "demo_student", PASSWORD, "student")
    account_admin.set_disabled(db_url, "demo_student", True)
    before = _rows(db_url)

    enabled = account_admin.set_disabled(db_url, "demo_student", False)

    assert enabled.disabled_at is None
    assert _rows(db_url)[0][:5] == before[0][:5]
    auth.login("demo_student", PASSWORD)


def test_reset_password_replaces_the_hash(db_url, auth):
    original = create_account(db_url, "demo_student", PASSWORD, "student")

    updated = account_admin.reset_password(db_url, "demo_student", NEW_PASSWORD)

    assert updated.id == original.id and updated.password_hash != original.password_hash
    assert verify_password(updated.password_hash, NEW_PASSWORD)
    with pytest.raises(InvalidCredentials):
        auth.login("demo_student", PASSWORD)
    auth.login("demo_student", NEW_PASSWORD)


def test_reset_password_rejects_invalid_password_without_writing(db_url):
    create_account(db_url, "demo_student", PASSWORD, "student")
    before = _rows(db_url)

    with pytest.raises(AccountValidationError, match="password"):
        account_admin.reset_password(db_url, "demo_student", "short")

    assert _rows(db_url) == before


@pytest.mark.parametrize(
    "action",
    [
        lambda url: account_admin.set_disabled(url, "nobody", True),
        lambda url: account_admin.set_disabled(url, "nobody", False),
        lambda url: account_admin.reset_password(url, "nobody", NEW_PASSWORD),
    ],
)
def test_unknown_username_raises_not_found(db_url, action):
    with pytest.raises(AccountNotFound):
        action(db_url)
    assert _rows(db_url) == []


# --- service: demo seed --------------------------------------------------------------------


def test_seed_creates_one_teacher_and_two_students(db_url, auth):
    outcomes = account_admin.seed_demo_accounts(db_url, PASSWORD)

    assert [(o.username, o.role, o.created) for o in outcomes] == [
        ("demo_teacher", "teacher", True),
        ("demo_student", "student", True),
        ("demo_student2", "student", True),
    ]
    assert DEMO_ACCOUNTS == tuple((o.username, o.role) for o in outcomes)
    for username, _ in DEMO_ACCOUNTS:
        auth.login(username, PASSWORD)


def test_reseeding_neither_duplicates_nor_resets_passwords(db_url):
    account_admin.seed_demo_accounts(db_url, PASSWORD)
    account_admin.reset_password(db_url, "demo_student", NEW_PASSWORD)
    account_admin.set_disabled(db_url, "demo_student2", True)
    before = _rows(db_url)

    outcomes = account_admin.seed_demo_accounts(db_url, "a-different-seed-password")

    assert [o.created for o in outcomes] == [False, False, False]
    assert _rows(db_url) == before  # same ids, hashes and disabled state


def test_seed_fills_only_missing_accounts(db_url):
    existing = create_account(db_url, "demo_student", NEW_PASSWORD, "student")

    outcomes = account_admin.seed_demo_accounts(db_url, PASSWORD)

    assert [o.created for o in outcomes] == [True, False, True]
    assert find_by_username(db_url, "demo_student") == existing


def test_seed_refuses_role_conflict_before_writing_anything(db_url):
    create_account(db_url, "demo_teacher", PASSWORD, "student")
    before = _rows(db_url)

    with pytest.raises(DemoSeedConflict, match="demo_teacher"):
        account_admin.seed_demo_accounts(db_url, PASSWORD)

    assert _rows(db_url) == before


def test_seed_rejects_invalid_password_before_writing_anything(db_url):
    with pytest.raises(AccountValidationError, match="password"):
        account_admin.seed_demo_accounts(db_url, "short")

    assert _rows(db_url) == []


# --- scripts -------------------------------------------------------------------------------


def _script_env(db_url: str, **extra: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in {"SEED_DEMO_PASSWORD", "C14_PW"}}
    env.update(SQLITE_URL=db_url, **extra)
    return env


def _run(name: str, *args: str, env: dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / f"{name}.py"), *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_seed_script_without_password_exits_nonzero_and_writes_nothing(db_url):
    result = _run("seed-demo-accounts", env=_script_env(db_url))

    assert result.returncode != 0
    assert "SEED_DEMO_PASSWORD" in result.stderr
    assert _rows(db_url) == []


def test_seed_script_with_blank_password_exits_nonzero(db_url):
    result = _run("seed-demo-accounts", env=_script_env(db_url, SEED_DEMO_PASSWORD=" " * 12))  # long enough to pass length checks

    assert result.returncode != 0
    assert _rows(db_url) == []


def test_seed_script_is_idempotent_and_never_prints_the_password(db_url):
    env = _script_env(db_url, SEED_DEMO_PASSWORD=PASSWORD)

    first = _run("seed-demo-accounts", env=env)
    second = _run("seed-demo-accounts", env=env)

    assert (first.returncode, second.returncode) == (0, 0)
    assert "created" in first.stdout and "created" not in second.stdout
    assert len(_rows(db_url)) == 3
    for output in (first.stdout, first.stderr, second.stdout, second.stderr):
        assert PASSWORD not in output and "$argon2id$" not in output


def test_seed_script_refuses_unmigrated_database(tmp_path):
    url = _url(tmp_path / "fresh.sqlite3")

    result = _run("seed-demo-accounts", env=_script_env(url, SEED_DEMO_PASSWORD=PASSWORD))

    assert result.returncode != 0
    assert "migrat" in result.stderr.lower()
    assert not (tmp_path / "fresh.sqlite3").exists()


def test_manage_script_create_list_disable_enable_round_trip(db_url):
    env = _script_env(db_url, C14_PW=PASSWORD)

    created = _run("manage-accounts", "create", "Teacher_Two", "--role", "teacher",
                   "--password-env", "C14_PW", env=env)
    disabled = _run("manage-accounts", "disable", "teacher_two", env=env)
    listing = _run("manage-accounts", "list", env=env)
    enabled = _run("manage-accounts", "enable", "teacher_two", env=env)

    assert [r.returncode for r in (created, disabled, listing, enabled)] == [0, 0, 0, 0]
    line = next(l for l in listing.stdout.splitlines() if "teacher_two" in l)
    assert "teacher" in line and "disabled" in line
    assert find_by_username(db_url, "teacher_two").disabled_at is None
    for result in (created, disabled, listing, enabled):
        assert PASSWORD not in result.stdout + result.stderr
        assert "$argon2id$" not in result.stdout + result.stderr


def test_manage_script_reset_password_reads_env_variable(db_url, auth):
    create_account(db_url, "demo_student", PASSWORD, "student")

    result = _run("manage-accounts", "reset-password", "demo_student",
                  "--password-env", "C14_PW", env=_script_env(db_url, C14_PW=NEW_PASSWORD))

    assert result.returncode == 0
    auth.login("demo_student", NEW_PASSWORD)


@pytest.mark.parametrize(
    ("args", "extra"),
    [
        (("disable", "nobody"), {}),
        (("create", "demo_teacher", "--role", "teacher", "--password-env", "C14_PW"),
         {"C14_PW": PASSWORD}),  # duplicate
        (("create", "x", "--role", "teacher", "--password-env", "C14_PW"),
         {"C14_PW": PASSWORD}),  # invalid username
        (("create", "new_user", "--role", "teacher", "--password-env", "C14_PW"), {}),  # unset
    ],
)
def test_manage_script_failures_exit_nonzero_without_writing(db_url, args, extra):
    create_account(db_url, "demo_teacher", PASSWORD, "teacher")
    before = _rows(db_url)

    result = _run("manage-accounts", *args, env=_script_env(db_url, **extra))

    assert result.returncode != 0
    assert _rows(db_url) == before
    assert PASSWORD not in result.stdout + result.stderr


def test_manage_script_has_no_password_argument():
    module = _load_script("manage-accounts")
    parser = module.build_parser()

    args, extras = parser.parse_known_args(
        ["create", "u_one", "--role", "student", "--password", PASSWORD]
    )

    assert args.password_env is None  # not taken as an abbreviation of --password-env
    assert extras == ["--password", PASSWORD]


@pytest.mark.parametrize("flag", [["--password", PASSWORD], [f"--password={PASSWORD}"]])
def test_manage_script_rejects_password_flag_without_echoing_it(db_url, flag):
    result = _run("manage-accounts", "create", "u_one", "--role", "student", *flag,
                  env=_script_env(db_url))

    assert result.returncode != 0
    assert "--password-env" in result.stderr
    assert PASSWORD not in result.stdout + result.stderr
    assert _rows(db_url) == []
