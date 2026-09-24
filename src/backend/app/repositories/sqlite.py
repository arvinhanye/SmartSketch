"""SQLite connections and forward-only, backed-up schema migrations."""

from __future__ import annotations

import hashlib
import re
import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


BUSY_TIMEOUT_MS = 5000
MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"
MIGRATION_NAME = re.compile(r"^([0-9]{3})_[a-z0-9_]+\.sql$")


class MigrationError(RuntimeError):
    """A migration was refused or failed without applying its schema changes."""


def database_path(sqlite_url: str) -> Path:
    """Resolve the project SQLite URL relative to the current process directory."""
    if not sqlite_url.startswith("sqlite:///"):
        raise ValueError("SQLITE_URL must start with sqlite:///")
    raw = sqlite_url[len("sqlite:///") :]
    if not raw or raw == ":memory:" or "?" in raw or "#" in raw:
        raise ValueError("SQLITE_URL must name a file without query parameters")
    return Path(raw).resolve()


@contextmanager
def connect(sqlite_url: str) -> Iterator[sqlite3.Connection]:
    """Open one short-lived connection with the API/worker SQLite invariants."""
    path = database_path(sqlite_url)
    path.parent.mkdir(parents=True, exist_ok=True)
    database = sqlite3.connect(path, timeout=BUSY_TIMEOUT_MS / 1000, isolation_level=None)
    try:
        database.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
        database.execute("PRAGMA journal_mode = WAL")
        database.execute("PRAGMA foreign_keys = ON")
        yield database
    finally:
        database.close()


def _table_exists(database: sqlite3.Connection, name: str) -> bool:
    return database.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
    ).fetchone() is not None


def _check_no_live_leases(database: sqlite3.Connection) -> None:
    # C06 creates the task table; C01 must also guard a database migrated later.
    for table in ("processing_tasks", "tasks"):
        if _table_exists(database, table):
            try:
                active = database.execute(
                    f"SELECT 1 FROM {table} WHERE lease_expires_at >= unixepoch() LIMIT 1"
                ).fetchone()
            except sqlite3.DatabaseError as exc:
                raise MigrationError(f"Cannot inspect {table} lease state") from exc
            if active:
                raise MigrationError("Active task lease: stop API and worker before migration")
    if _table_exists(database, "course_locks"):
        try:
            active = database.execute(
                "SELECT 1 FROM course_locks WHERE expires_at >= unixepoch() LIMIT 1"
            ).fetchone()
        except sqlite3.DatabaseError as exc:
            raise MigrationError("Cannot inspect course_locks lease state") from exc
        if active:
            raise MigrationError("Active course lock: stop API and worker before migration")


def _migration_files(directory: Path) -> list[tuple[str, Path, str]]:
    if not directory.is_dir():
        raise MigrationError(f"Migration directory does not exist: {directory}")
    found: list[tuple[str, Path, str]] = []
    versions: set[str] = set()
    for path in sorted(directory.glob("*.sql")):
        match = MIGRATION_NAME.fullmatch(path.name)
        if match is None:
            raise MigrationError(f"Invalid migration filename: {path.name}")
        version = match.group(1)
        if version in versions:
            raise MigrationError(f"Duplicate migration version: {version}")
        versions.add(version)
        found.append((version, path, hashlib.sha256(path.read_bytes()).hexdigest()))
    return found


def _statements(script: str) -> Iterator[str]:
    current = ""
    for character in script:
        current += character
        if character == ";" and sqlite3.complete_statement(current):
            yield current
            current = ""
    remainder = re.sub(r"--[^\n]*|/\*.*?\*/", "", current, flags=re.DOTALL)
    if not remainder.strip():
        return
    if not sqlite3.complete_statement(current):
        raise MigrationError("Migration SQL ends with an incomplete statement")
    yield current


def _backup(database: sqlite3.Connection, path: Path, version: str) -> Path:
    directory = path.parent / "backups"
    directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup = directory / f"{timestamp}-before-{version}.sqlite"
    database.execute("VACUUM INTO ?", (str(backup),))
    with closing(sqlite3.connect(backup)) as copy:
        result = copy.execute("PRAGMA integrity_check").fetchone()
    if result != ("ok",):
        backup.unlink(missing_ok=True)
        raise MigrationError("Backup integrity_check failed; original database was not migrated")
    return backup


def migrate(sqlite_url: str, migrations_dir: Path | None = None) -> list[str]:
    """Apply pending SQL files once each, backing up before every version.

    Call only while API and worker processes are stopped. Existing live
    leases/locks are an additional fail-closed guard, not a stop detector.
    """
    path = database_path(sqlite_url)
    files = _migration_files(migrations_dir or MIGRATIONS_DIR)
    applied_now: list[str] = []
    with connect(sqlite_url) as database:
        known = (
            dict(database.execute("SELECT version, checksum FROM schema_migrations"))
            if _table_exists(database, "schema_migrations")
            else {}
        )
        file_versions = {version for version, _, _ in files}
        if set(known) - file_versions:
            raise MigrationError("Database has a migration version absent from this codebase")
        for version, _, checksum in files:
            if version in known and known[version] != checksum:
                raise MigrationError(f"Migration {version} checksum changed")
        if known and any(version < max(known) for version, _, _ in files if version not in known):
            raise MigrationError("Cannot apply a migration older than an already applied version")
        for version, sql_file, checksum in files:
            if version in known:
                continue
            _check_no_live_leases(database)
            try:
                _backup(database, path, version)
                database.execute("BEGIN IMMEDIATE")
                _check_no_live_leases(database)
                database.execute(
                    """CREATE TABLE IF NOT EXISTS schema_migrations (
                        version TEXT PRIMARY KEY,
                        filename TEXT NOT NULL,
                        checksum TEXT NOT NULL,
                        applied_at TEXT NOT NULL
                    )"""
                )
                def refuse_transaction_control(action: int, *args: object) -> int:
                    if action in (sqlite3.SQLITE_TRANSACTION, sqlite3.SQLITE_SAVEPOINT):
                        return sqlite3.SQLITE_DENY
                    return sqlite3.SQLITE_OK

                database.set_authorizer(refuse_transaction_control)
                try:
                    for statement in _statements(sql_file.read_text(encoding="utf-8")):
                        database.execute(statement)
                finally:
                    database.set_authorizer(None)
                database.execute(
                    """INSERT INTO schema_migrations(version, filename, checksum, applied_at)
                    VALUES (?, ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))""",
                    (version, sql_file.name, checksum),
                )
                database.execute("COMMIT")
            except (OSError, sqlite3.DatabaseError, MigrationError) as exc:
                if database.in_transaction:
                    database.execute("ROLLBACK")
                raise MigrationError(f"Migration {version} failed: {exc}") from exc
            applied_now.append(version)
    return applied_now


def main() -> int:
    """Run migrations using the environment-only runtime configuration."""
    from app.config import load_settings

    settings = load_settings()
    try:
        versions = migrate(settings.SQLITE_URL)
    except MigrationError as exc:
        print(f"Migration refused: {exc}")
        return 1
    print("Applied migrations: " + (", ".join(versions) if versions else "none"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
