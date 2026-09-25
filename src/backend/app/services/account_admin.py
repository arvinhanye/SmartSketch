"""C14: operator account commands and demo-account seeding (specs/identity-access.md §1.2).

There is no registration endpoint; accounts are created, disabled, re-enabled and given new
passwords only through these functions, which the scripts in ``scripts/`` wrap. Disabling
keeps the row (and its first ``disabled_at``) so foreign keys from progress, chat and edit
logs survive. Passwords and hashes never appear in return values' repr or in messages.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.repositories import accounts
from app.repositories.accounts import AccountRecord, DuplicateUsername
from app.services.auth import (
    PASSWORD_MAX_LENGTH,
    PASSWORD_MIN_LENGTH,
    AccountValidationError,
    create_account,
    hash_password,
    normalize_username,
)

# One teacher and two students, so two students can show that progress is private (§1.2).
DEMO_ACCOUNTS: tuple[tuple[str, str], ...] = (
    ("demo_teacher", "teacher"),
    ("demo_student", "student"),
    ("demo_student2", "student"),
)


class AccountNotFound(LookupError):
    """No account has this (lower-cased) username."""


class DemoSeedConflict(RuntimeError):
    """A demo username already exists with a different account type; nothing was written."""


@dataclass(frozen=True)
class SeedOutcome:
    username: str
    role: str
    created: bool


def _check_password(password: str) -> None:
    if not PASSWORD_MIN_LENGTH <= len(password) <= PASSWORD_MAX_LENGTH:
        raise AccountValidationError(
            f"password must be {PASSWORD_MIN_LENGTH}-{PASSWORD_MAX_LENGTH} characters"
        )


def list_accounts(sqlite_url: str) -> list[AccountRecord]:
    return accounts.list_accounts(sqlite_url)


def set_disabled(sqlite_url: str, username: str, disabled: bool) -> AccountRecord:
    """Disable or re-enable an account; disabling an already disabled account is a no-op."""
    normalized = normalize_username(username)
    record = accounts.set_disabled(sqlite_url, normalized, disabled)
    if record is None:
        raise AccountNotFound(normalized)
    return record


def reset_password(sqlite_url: str, username: str, password: str) -> AccountRecord:
    _check_password(password)
    normalized = normalize_username(username)
    record = accounts.update_password_hash(sqlite_url, normalized, hash_password(password))
    if record is None:
        raise AccountNotFound(normalized)
    return record


def seed_demo_accounts(sqlite_url: str, password: str) -> list[SeedOutcome]:
    """Create whichever demo accounts are missing; never touch existing ones.

    Validation and conflict checks run before any write, so a bad password or a demo
    username held by the wrong account type leaves the database unchanged.
    """
    _check_password(password)
    existing = {
        username: accounts.find_by_username(sqlite_url, username)
        for username, _ in DEMO_ACCOUNTS
    }
    conflicts = [
        username
        for username, role in DEMO_ACCOUNTS
        if existing[username] is not None and existing[username].role != role
    ]
    if conflicts:
        raise DemoSeedConflict(
            "demo usernames held by a different account type: " + ", ".join(conflicts)
        )

    outcomes = []
    for username, role in DEMO_ACCOUNTS:
        created = False
        if existing[username] is None:
            try:
                create_account(sqlite_url, username, password, role)
                created = True
            except DuplicateUsername:  # a concurrent seed got there first
                pass
        outcomes.append(SeedOutcome(username=username, role=role, created=created))
    return outcomes
