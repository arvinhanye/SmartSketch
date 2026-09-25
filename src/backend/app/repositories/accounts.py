"""Persistence for local accounts in the SQLite ``users`` table (migration 002)."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from app.repositories.sqlite import connect


class DuplicateUsername(ValueError):
    """The (already lower-cased) username is taken."""


@dataclass(frozen=True)
class AccountRecord:
    id: str
    username: str
    password_hash: str
    role: str
    created_at: str
    disabled_at: str | None

    def __repr__(self) -> str:  # keep the password hash out of logs and tracebacks
        return (
            f"AccountRecord(id={self.id!r}, username={self.username!r}, role={self.role!r}, "
            f"disabled={self.disabled_at is not None})"
        )


_COLUMNS = "id, username, password_hash, role, created_at, disabled_at"


def find_by_username(sqlite_url: str, username: str) -> AccountRecord | None:
    """Return the account stored under ``username`` exactly (callers lower-case first)."""
    with connect(sqlite_url) as database:
        row = database.execute(
            f"SELECT {_COLUMNS} FROM users WHERE username = ?", (username,)
        ).fetchone()
    return AccountRecord(*row) if row else None


def find_by_id(sqlite_url: str, user_id: str) -> AccountRecord | None:
    """Resolve a verified token subject on every request (C03)."""
    with connect(sqlite_url) as database:
        row = database.execute(
            f"SELECT {_COLUMNS} FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    return AccountRecord(*row) if row else None


def insert_account(
    sqlite_url: str, *, account_id: str, username: str, password_hash: str, role: str
) -> AccountRecord:
    """Insert one enabled account and return the stored row."""
    with connect(sqlite_url) as database:
        try:
            database.execute(
                "INSERT INTO users (id, username, password_hash, role) VALUES (?, ?, ?, ?)",
                (account_id, username, password_hash, role),
            )
        except sqlite3.IntegrityError as exc:
            if database.execute(
                "SELECT 1 FROM users WHERE username = ?", (username,)
            ).fetchone():
                raise DuplicateUsername(username) from None
            raise ValueError("account row rejected by the users table constraints") from exc
        row = database.execute(f"SELECT {_COLUMNS} FROM users WHERE id = ?", (account_id,)).fetchone()
    return AccountRecord(*row)


def list_accounts(sqlite_url: str) -> list[AccountRecord]:
    """All accounts, oldest first, for the account command's listing (C14)."""
    with connect(sqlite_url) as database:
        rows = database.execute(
            f"SELECT {_COLUMNS} FROM users ORDER BY created_at, username"
        ).fetchall()
    return [AccountRecord(*row) for row in rows]


def set_disabled(sqlite_url: str, username: str, disabled: bool) -> AccountRecord | None:
    """Disable (keeping the first timestamp) or re-enable; ``None`` if the username is unknown."""
    with connect(sqlite_url) as database:
        database.execute(
            "UPDATE users SET disabled_at = CASE WHEN ? THEN"
            " COALESCE(disabled_at, strftime('%Y-%m-%dT%H:%M:%fZ', 'now')) ELSE NULL END"
            " WHERE username = ?",
            (disabled, username),
        )
        row = database.execute(
            f"SELECT {_COLUMNS} FROM users WHERE username = ?", (username,)
        ).fetchone()
    return AccountRecord(*row) if row else None


def update_password_hash(
    sqlite_url: str, username: str, password_hash: str
) -> AccountRecord | None:
    """Replace the stored hash; ``None`` if the username is unknown."""
    with connect(sqlite_url) as database:
        database.execute(
            "UPDATE users SET password_hash = ? WHERE username = ?", (password_hash, username)
        )
        row = database.execute(
            f"SELECT {_COLUMNS} FROM users WHERE username = ?", (username,)
        ).fetchone()
    return AccountRecord(*row) if row else None
