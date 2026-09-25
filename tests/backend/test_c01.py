"""C01: SQLite connection, forward migrations, and recoverable backups."""

import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import SettingsError
from app.main import create_app
from app.repositories.embedding_space import read_or_initialize_space
from app.repositories.sqlite import (
    MigrationError,
    _check_no_live_leases,
    connect,
    migrate,
    pending_migrations,
)

ROOT = Path(__file__).resolve().parents[2]
# C01 之前 B06 启动门禁自己建出的表（ADR-012 补注第 1 条），用于模拟已有数据库。
LEGACY_B06_DDL = """CREATE TABLE embedding_space_state (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    model TEXT NOT NULL,
    dimensions INTEGER NOT NULL CHECK (dimensions >= 1),
    is_fake INTEGER NOT NULL CHECK (is_fake IN (0, 1))
)"""


def _url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def _base_only(tmp_path: Path) -> Path:
    """Only the real 001_base.sql, so these 001 assertions hold after later migrations land."""
    directory = tmp_path / "base-only-migrations"
    directory.mkdir()
    shutil.copyfile(ROOT / "src/backend/migrations/001_base.sql", directory / "001_base.sql")
    return directory


def test_connection_enables_wal_foreign_keys_and_busy_timeout(tmp_path):
    with connect(_url(tmp_path / "db.sqlite3")) as database:
        assert database.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert database.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert database.execute("PRAGMA busy_timeout").fetchone()[0] == 5000


def test_base_migration_adopts_existing_embedding_space_and_is_repeatable(tmp_path):
    path = tmp_path / "db.sqlite3"
    url = _url(path)
    with sqlite3.connect(path) as database:
        database.execute(LEGACY_B06_DDL)
        database.execute("INSERT INTO embedding_space_state VALUES (1, 'model-a', 768, 0)")

    base = _base_only(tmp_path)
    assert migrate(url, base) == ["001"]
    assert migrate(url, base) == []
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
    assert migrate(url, _base_only(tmp_path)) == ["001"]
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
    assert migrate(_url(path), _base_only(tmp_path)) == ["001"]
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


def test_task_table_without_lease_columns_does_not_block_later_migrations(tmp_path):
    # C06 的 003_tasks.sql 建 processing_tasks 时尚无租约列（C09 才加）；没有租约列就不可能有租约，
    # 不应让 003 之后的任何迁移都报 "Cannot inspect processing_tasks lease state"。
    path = tmp_path / "db.sqlite3"
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    for name in ("001_base.sql", "002_accounts.sql", "003_tasks.sql"):
        shutil.copyfile(ROOT / "src/backend/migrations" / name, migrations / name)
    assert migrate(_url(path), migrations) == ["001", "002", "003"]
    (migrations / "004_next.sql").write_text("CREATE TABLE next_table (id INTEGER);", encoding="utf-8")

    assert migrate(_url(path), migrations) == ["004"]


@pytest.mark.parametrize("table", ["processing_tasks", "course_locks"])
def test_lease_table_without_lease_column_has_no_live_lease(tmp_path, table):
    with sqlite3.connect(tmp_path / "db.sqlite3") as database:
        database.execute(f"CREATE TABLE {table} (id INTEGER)")
        database.execute(f"INSERT INTO {table} VALUES (1)")
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


# ── REVIEW-C01 R01：校验和不受换行符影响 ─────────────────────────────────────

def test_checksum_is_the_same_for_crlf_and_lf_checkouts(tmp_path):
    url = _url(tmp_path / "db.sqlite3")
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    sql = migrations / "001_base.sql"
    sql.write_bytes(b"-- base\r\nCREATE TABLE example (id INTEGER PRIMARY KEY);\r\n")
    assert migrate(url, migrations) == ["001"]

    sql.write_bytes(b"-- base\nCREATE TABLE example (id INTEGER PRIMARY KEY);\n")
    assert migrate(url, migrations) == []
    assert pending_migrations(url, migrations) == []

    sql.write_bytes(b"-- changed\nCREATE TABLE example (id INTEGER PRIMARY KEY);\n")
    with pytest.raises(MigrationError, match="checksum"):
        migrate(url, migrations)


def test_repository_pins_migration_files_to_lf():
    result = subprocess.run(
        ["git", "check-attr", "eol", "--", "src/backend/migrations/001_base.sql"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    )
    assert result.stdout.strip().endswith("eol: lf")


# ── REVIEW-C01 R02：启动前确认迁移已是最新 ────────────────────────────────────

def test_pending_migrations_is_read_only_and_validates_history(tmp_path):
    path = tmp_path / "db.sqlite3"
    url = _url(path)
    base = _base_only(tmp_path)
    assert pending_migrations(url, base) == ["001"]
    assert not path.exists(), "只读检查不得创建数据库文件"

    migrate(url, base)
    assert pending_migrations(url, base) == []

    with sqlite3.connect(path) as database:
        database.execute("UPDATE schema_migrations SET checksum = 'x' WHERE version = '001'")
    with pytest.raises(MigrationError, match="checksum"):
        pending_migrations(url, base)


def test_api_refuses_to_start_before_migrations_run(tmp_path, monkeypatch):
    path = tmp_path / "db.sqlite3"
    monkeypatch.setenv("SQLITE_URL", _url(path))
    with pytest.raises(SettingsError, match="not migrated.*001.*app.repositories.sqlite"):
        with TestClient(create_app()):
            pass
    assert not path.exists()

    migrate(_url(path))
    with TestClient(create_app()) as client:
        assert client.get("/health").status_code == 200


# ── REVIEW-C01 R03：建表只在迁移里 ───────────────────────────────────────────

def test_space_gate_reads_and_writes_the_row_but_never_creates_the_table(tmp_path):
    source = (ROOT / "src/backend/app/repositories/embedding_space.py").read_text(encoding="utf-8")
    assert "CREATE TABLE" not in source.upper()

    path = tmp_path / "db.sqlite3"
    sqlite3.connect(path).close()
    with pytest.raises(sqlite3.OperationalError, match="embedding_space_state"):
        read_or_initialize_space(_url(path), "model-a", 768, 0)
    with sqlite3.connect(path) as database:
        assert database.execute(
            "SELECT name FROM sqlite_master WHERE name = 'embedding_space_state'"
        ).fetchone() is None

    migrate(_url(path))
    assert read_or_initialize_space(_url(path), "model-a", 768, 0) == ("model-a", 768, 0)
