"""Persistence for per-user model configurations and per-task key snapshots (ADR-080).

Rows hold ciphertext only; this module never sees a plaintext key.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from app.repositories.sqlite import connect

_NOW = "strftime('%Y-%m-%dT%H:%M:%fZ', 'now')"
_TERMINAL = "('awaiting_review', 'completed', 'failed', 'cancelled')"
_CONFIG_COLUMNS = ("user_id, base_url, model, key_ciphertext, key_nonce, key_hint, version, updated_at, "
                   "last_test_at, last_test_ok, last_test_error_class")


class KeyRequired(Exception):
    """No stored key can be kept: there is no configuration yet, or ``base_url`` changed."""


@dataclass(frozen=True)
class SealedKey:
    """AES-GCM ciphertext and nonce of one API key; sealed and opened only by the service layer."""

    ciphertext: bytes = field(repr=False)
    nonce: bytes = field(repr=False)


@dataclass(frozen=True)
class ModelConfigRow:
    user_id: str
    base_url: str
    model: str
    sealed: SealedKey
    key_hint: str
    version: int
    updated_at: str
    last_test_at: str | None
    last_test_ok: bool | None
    last_test_error_class: str | None


@dataclass(frozen=True)
class TaskBindingRow:
    task_id: str
    user_id: str
    config_version: int
    base_url: str
    model: str
    sealed: SealedKey | None
    scrub_reason: str | None


def _config(row: tuple | None) -> ModelConfigRow | None:
    if row is None:
        return None
    return ModelConfigRow(
        user_id=row[0], base_url=row[1], model=row[2], sealed=SealedKey(bytes(row[3]), bytes(row[4])),
        key_hint=row[5], version=row[6], updated_at=row[7], last_test_at=row[8],
        last_test_ok=None if row[9] is None else bool(row[9]), last_test_error_class=row[10],
    )


def _read(database: sqlite3.Connection, user_id: str) -> ModelConfigRow | None:
    return _config(database.execute(
        f"SELECT {_CONFIG_COLUMNS} FROM user_model_configs WHERE user_id = ?", (user_id,)
    ).fetchone())


def get_config(sqlite_url: str, user_id: str) -> ModelConfigRow | None:
    with connect(sqlite_url) as database:
        return _read(database, user_id)


def save_config(sqlite_url: str, *, user_id: str, base_url: str, model: str,
                sealed: SealedKey | None, key_hint: str | None) -> ModelConfigRow:
    """Insert or update; ``sealed=None`` keeps the stored key and requires an unchanged ``base_url``."""
    with connect(sqlite_url) as database:
        database.execute("BEGIN IMMEDIATE")
        try:
            current = _read(database, user_id)
            if sealed is None:
                if current is None or current.base_url != base_url:
                    raise KeyRequired()
                database.execute(
                    f"UPDATE user_model_configs SET model = ?, version = version + 1, updated_at = {_NOW},"
                    " last_test_at = NULL, last_test_ok = NULL, last_test_error_class = NULL WHERE user_id = ?",
                    (model, user_id),
                )
            else:
                if not key_hint:
                    raise ValueError("key_hint is required with a new key")
                database.execute(
                    "INSERT INTO user_model_configs"
                    " (user_id, base_url, model, key_ciphertext, key_nonce, key_hint, version)"
                    " VALUES (?, ?, ?, ?, ?, ?, 1)"
                    " ON CONFLICT(user_id) DO UPDATE SET base_url = excluded.base_url, model = excluded.model,"
                    " key_ciphertext = excluded.key_ciphertext, key_nonce = excluded.key_nonce,"
                    f" key_hint = excluded.key_hint, version = user_model_configs.version + 1, updated_at = {_NOW},"
                    " last_test_at = NULL, last_test_ok = NULL, last_test_error_class = NULL",
                    (user_id, base_url, model, sealed.ciphertext, sealed.nonce, key_hint),
                )
            row = _read(database, user_id)
            database.execute("COMMIT")
        except BaseException:
            if database.in_transaction:
                database.execute("ROLLBACK")
            raise
    if row is None:
        raise RuntimeError("model configuration save did not return a row")
    return row


def delete_config(sqlite_url: str, user_id: str) -> bool:
    """Delete the configuration and revoke the owner's open task snapshots in one transaction."""
    with connect(sqlite_url) as database:
        database.execute("BEGIN IMMEDIATE")
        try:
            deleted = database.execute("DELETE FROM user_model_configs WHERE user_id = ?", (user_id,)).rowcount
            database.execute(
                f"UPDATE task_model_bindings SET key_ciphertext = NULL, key_nonce = NULL, scrubbed_at = {_NOW},"
                " scrub_reason = 'revoked' WHERE user_id = ? AND key_ciphertext IS NOT NULL",
                (user_id,),
            )
            database.execute("COMMIT")
        except BaseException:
            if database.in_transaction:
                database.execute("ROLLBACK")
            raise
    return deleted == 1


def record_test(sqlite_url: str, user_id: str, *, ok: bool, error_class: str | None) -> None:
    with connect(sqlite_url) as database:
        database.execute(
            f"UPDATE user_model_configs SET last_test_at = {_NOW}, last_test_ok = ?, last_test_error_class = ?"
            " WHERE user_id = ?",
            (1 if ok else 0, error_class, user_id),
        )


def bind_task(database: sqlite3.Connection, *, task_id: str, user_id: str) -> bool:
    """Copy the owner's current configuration into the task snapshot on the caller's transaction."""
    return database.execute(
        "INSERT INTO task_model_bindings (task_id, user_id, config_version, base_url, model, key_ciphertext, key_nonce)"
        " SELECT ?, user_id, version, base_url, model, key_ciphertext, key_nonce"
        " FROM user_model_configs WHERE user_id = ?",
        (task_id, user_id),
    ).rowcount == 1


def get_binding(sqlite_url: str, task_id: str) -> TaskBindingRow | None:
    with connect(sqlite_url) as database:
        row = database.execute(
            "SELECT task_id, user_id, config_version, base_url, model, key_ciphertext, key_nonce, scrub_reason"
            " FROM task_model_bindings WHERE task_id = ?", (task_id,)
        ).fetchone()
    if row is None:
        return None
    sealed = None if row[5] is None else SealedKey(bytes(row[5]), bytes(row[6]))
    return TaskBindingRow(row[0], row[1], row[2], row[3], row[4], sealed, row[7])


def binding_active(sqlite_url: str, task_id: str) -> bool:
    with connect(sqlite_url) as database:
        return database.execute(
            "SELECT 1 FROM task_model_bindings WHERE task_id = ? AND key_ciphertext IS NOT NULL", (task_id,)
        ).fetchone() is not None


def scrub_terminal_bindings(sqlite_url: str) -> int:
    """Null the key snapshot of every task that no longer needs a model call."""
    with connect(sqlite_url) as database:
        return database.execute(
            f"UPDATE task_model_bindings SET key_ciphertext = NULL, key_nonce = NULL, scrubbed_at = {_NOW},"
            " scrub_reason = 'terminal' WHERE key_ciphertext IS NOT NULL"
            f" AND task_id IN (SELECT id FROM processing_tasks WHERE stage IN {_TERMINAL})"
        ).rowcount
