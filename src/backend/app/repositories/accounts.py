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
