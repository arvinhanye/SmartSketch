"""C01: SQLite connection, forward migrations, and recoverable backups."""

import shutil
import sqlite3
from pathlib import Path

import pytest

from app.repositories.embedding_space import read_or_initialize_space
from app.repositories.sqlite import MigrationError, _check_no_live_leases, connect, migrate


def _url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def test_connection_enables_wal_foreign_keys_and_busy_timeout(tmp_path):
    with connect(_url(tmp_path / "db.sqlite3")) as database:
        assert database.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert database.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert database.execute("PRAGMA busy_timeout").fetchone()[0] == 5000


def test_base_migration_adopts_existing_embedding_space_and_is_repeatable(tmp_path):
    path = tmp_path / "db.sqlite3"
    url = _url(path)
    read_or_initialize_space(url, "model-a", 768, 0)

    assert migrate(url) == ["001"]
    assert migrate(url) == []
    with sqlite3.connect(path) as database:
        assert database.execute(
            "SELECT model, dimensions, is_fake FROM embedding_space_state"
        ).fetchone() == ("model-a", 768, 0)
        assert database.execute(
            "SELECT version, filename, length(checksum) FROM schema_migrations"
        ).fetchall() == [("001", "001_base.sql", 64)]


def test_model_calls_prewrite_replay_and_attribution_query(tmp_path):
    path = tmp_path / "db.sqlite3"
    url = _url(path)
    assert migrate(url) == ["001"]
    prewrite = (
        "call-1", "course-1", "task-1", "chunk-1", None,
        "entity", 1, 2, 1, "primary", 0, "model-a", 120, 50,
    )
    sql = """INSERT OR IGNORE INTO model_calls (
        call_id, course_id, task_id, chunk_id, request_id, purpose,
        task_attempt, chunk_attempt, call_seq, provider_role, is_repair,
        model_requested, input_tokens_est, max_output_tokens
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
    with sqlite3.connect(path) as database:
        database.execute(sql, prewrite)
        database.execute(sql, prewrite)
        database.execute(sql, (
            "call-2", "course-1", None, None, "request-1",
            "answer", None, None, None, "primary", 0, "model-a", 40, 20,
        ))
        assert database.execute(
            "SELECT call_id, status, input_tokens_est, max_output_tokens "
            "FROM model_calls WHERE task_id = ?", ("task-1",)
        ).fetchall() == [("call-1", "sent", 120, 50)]
        assert database.execute(
            "SELECT call_id FROM model_calls WHERE request_id = ?", ("request-1",)
        ).fetchall() == [("call-2",)]
        assert database.execute("SELECT COUNT(*) FROM model_calls").fetchone() == (2,)
        with pytest.raises(sqlite3.IntegrityError):
            database.execute("INSERT INTO model_calls (call_id) VALUES (NULL)")


def test_backup_can_be_moved_immediately_after_migration_returns(tmp_path):
    path = tmp_path / "db.sqlite3"
    assert migrate(_url(path)) == ["001"]
    backup = next((tmp_path / "backups").glob("*-before-001.sqlite"))
    moved = tmp_path / "moved-backup.sqlite"
    shutil.move(backup, moved)
    assert moved.is_file()
    with sqlite3.connect(moved) as database:
        assert database.execute("PRAGMA integrity_check").fetchone() == ("ok",)


def test_failed_migration_rolls_back_schema_and_version(tmp_path):
    path = tmp_path / "db.sqlite3"
    url = _url(path)
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "001_base.sql").write_text(
        "CREATE TABLE example (id INTEGER PRIMARY KEY);", encoding="utf-8"
    )
    assert migrate(url, migrations) == ["001"]
    (migrations / "002_bad.sql").write_text(
        "CREATE TABLE temporary_table (id INTEGER);\nINSERT INTO missing_table VALUES (1);",
        encoding="utf-8",
    )

    with pytest.raises(MigrationError):
        migrate(url, migrations)
    with sqlite3.connect(path) as database:
        assert database.execute(
            "SELECT name FROM sqlite_master WHERE name = 'temporary_table'"
        ).fetchone() is None
        assert database.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall() == [("001",)]


def test_migration_cannot_commit_its_own_transaction(tmp_path):
    path = tmp_path / "db.sqlite3"
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "001_bad.sql").write_text(
        "CREATE TABLE escaped (id INTEGER); COMMIT; INSERT INTO missing_table VALUES (1);",
        encoding="utf-8",
    )

    with pytest.raises(MigrationError):
        migrate(_url(path), migrations)
    with sqlite3.connect(path) as database:
        assert database.execute(
            "SELECT name FROM sqlite_master WHERE name = 'escaped'"
        ).fetchone() is None
        assert database.execute(
            "SELECT name FROM sqlite_master WHERE name = 'schema_migrations'"
        ).fetchone() is None


@pytest.mark.parametrize("table,column", [("processing_tasks", "lease_expires_at"), ("course_locks", "expires_at")])
def test_live_lease_rejects_migration_without_changing_database(tmp_path, table, column):
    path = tmp_path / "db.sqlite3"
    url = _url(path)
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "001_base.sql").write_text(
        "CREATE TABLE example (id INTEGER PRIMARY KEY);", encoding="utf-8"
    )
    migrate(url, migrations)
    with sqlite3.connect(path) as database:
        database.execute(f"CREATE TABLE {table} ({column} INTEGER)")
        database.execute(f"INSERT INTO {table} VALUES (unixepoch() + 60)")
    (migrations / "002_next.sql").write_text(
        "CREATE TABLE next_table (id INTEGER);", encoding="utf-8"
    )
    before = list((tmp_path / "backups").glob("*.sqlite"))

    with pytest.raises(MigrationError, match="lease|lock|租约|锁"):
        migrate(url, migrations)
    with sqlite3.connect(path) as database:
        assert database.execute(
            "SELECT name FROM sqlite_master WHERE name = 'next_table'"
        ).fetchone() is None
    assert list((tmp_path / "backups").glob("*.sqlite")) == before


@pytest.mark.parametrize("table,column", [("processing_tasks", "lease_expires_at"), ("course_locks", "expires_at")])
def test_lease_expiring_at_current_second_still_blocks_migration(tmp_path, table, column):
    with sqlite3.connect(tmp_path / "db.sqlite3") as database:
        database.create_function("unixepoch", 0, lambda: 1000)
        database.execute(f"CREATE TABLE {table} ({column} INTEGER)")
        database.execute(f"INSERT INTO {table} VALUES (1000)")
        with pytest.raises(MigrationError, match="lease|lock"):
            _check_no_live_leases(database)


def test_backup_can_restore_previous_schema_and_applied_checksum_is_immutable(tmp_path):
    path = tmp_path / "db.sqlite3"
    url = _url(path)
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    first = migrations / "001_base.sql"
    first.write_text("CREATE TABLE base (id INTEGER);", encoding="utf-8")
    migrate(url, migrations)
    (migrations / "002_more.sql").write_text(
        "CREATE TABLE later (id INTEGER);", encoding="utf-8"
    )
    assert migrate(url, migrations) == ["002"]
    backup = max((tmp_path / "backups").glob("*-before-002.sqlite"))
    with sqlite3.connect(backup) as database:
        assert database.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    # Rehearse the documented stopped-process replacement, including WAL sidecars.
    for suffix in ("-wal", "-shm"):
        Path(f"{path}{suffix}").write_bytes(b"old database sidecar")
    failed = tmp_path / "failed"
    failed.mkdir()
    shutil.move(path, failed / path.name)
    for suffix in ("-wal", "-shm"):
        sidecar = Path(f"{path}{suffix}")
        if sidecar.exists():
            shutil.move(sidecar, failed / sidecar.name)
    shutil.copy2(backup, path)
    assert (failed / path.name).exists()
    assert all((failed / f"{path.name}{suffix}").exists() for suffix in ("-wal", "-shm"))
    with sqlite3.connect(path) as database:
        assert database.execute(
            "SELECT name FROM sqlite_master WHERE name = 'later'"
        ).fetchone() is None
        assert database.execute(
            "SELECT version FROM schema_migrations"
        ).fetchall() == [("001",)]
    first.write_text("CREATE TABLE changed (id INTEGER);", encoding="utf-8")
    with pytest.raises(MigrationError, match="checksum"):
        migrate(url, migrations)


def test_history_is_validated_before_any_pending_migration_runs(tmp_path):
    path = tmp_path / "db.sqlite3"
    url = _url(path)
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "001_base.sql").write_text(
        "CREATE TABLE base (id INTEGER);", encoding="utf-8"
    )
    migrate(url, migrations)
    (migrations / "002_next.sql").write_text(
        "CREATE TABLE should_not_exist (id INTEGER);", encoding="utf-8"
    )
    (migrations / "003_later.sql").write_text(
        "CREATE TABLE later (id INTEGER);", encoding="utf-8"
    )
    with sqlite3.connect(path) as database:
        database.execute(
            """INSERT INTO schema_migrations(version, filename, checksum, applied_at)
            VALUES ('003', '003_later.sql', 'wrong-checksum', '2026-09-24T00:00:00Z')"""
        )
    with pytest.raises(MigrationError, match="checksum"):
        migrate(url, migrations)
    with sqlite3.connect(path) as database:
        assert database.execute(
            "SELECT name FROM sqlite_master WHERE name = 'should_not_exist'"
        ).fetchone() is None


def test_sql_migration_allows_trailing_comment(tmp_path):
    path = tmp_path / "db.sqlite3"
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "001_base.sql").write_text(
        "CREATE TABLE example (id INTEGER);\n-- end of migration\n", encoding="utf-8"
    )
    assert migrate(_url(path), migrations) == ["001"]
