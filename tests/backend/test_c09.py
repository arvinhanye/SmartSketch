"""C09: atomic worker claim and task leases (specs/task-processing.md §8.2, §8.3; ADR-011)."""

from __future__ import annotations

import json
import shutil
import sqlite3
import threading
from pathlib import Path

import pytest

from app.config import SettingsError, load_settings
from app.repositories import task_leases, tasks
from app.repositories.sqlite import MigrationError, connect, migrate
from app.repositories.task_leases import LeaseLost
from app.services.file_storage import StoredFile
from app.services.task_state import Applied, TaskError, TaskState, TransitionEvent, apply_event

MIGRATIONS = Path(__file__).resolve().parents[2] / "src" / "backend" / "migrations"
LEASE_SECONDS = 60
MAX_ATTEMPTS = 3


def _url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def _lease_migration() -> Path:
    # D-10 可能在合并前改号：按文件名后缀找，不写死版本号。
    (path,) = MIGRATIONS.glob("*_task_leases.sql")
    return path


def _copy_migrations_through(target: Path, last: Path) -> None:
    """Copy real migrations up to and including ``last`` only; later ones never matter here."""
    target.mkdir()
    for path in sorted(MIGRATIONS.glob("*.sql")):
        if path.name[:3] <= last.name[:3]:
            shutil.copyfile(path, target / path.name)


_counter = iter(range(10**6))


def _stored_file(tmp_path: Path) -> StoredFile:
    n = next(_counter)
    storage_name = f"{n:032x}.txt"
    path = tmp_path / storage_name
    path.write_text("course notes", encoding="utf-8")
    return StoredFile(
        storage_name=storage_name,
        path=path,
        original_filename="notes.txt",
        format="txt",
        size_bytes=12,
        content_hash="sha256:" + "a" * 64,
    )


@pytest.fixture
def db_url(tmp_path: Path) -> str:
    url = _url(tmp_path / "state.sqlite3")
    assert _lease_migration().name[:3] in migrate(url)
    return url


@pytest.fixture
def new_task(db_url, tmp_path):
    def _make(course_id: str = "course-a", *, created_at: str | None = None) -> str:
        result = tasks.create_material_task(
            db_url,
            course_id=course_id,
            stored_file=_stored_file(tmp_path),
            idempotency_key=f"key-{next(_counter)}",
        )
        if created_at is not None:
            _sql(db_url, "UPDATE processing_tasks SET created_at = ? WHERE id = ?", created_at, result.task.id)
        return result.task.id

    return _make


def _sql(url: str, statement: str, *params: object) -> None:
    with connect(url) as database:
        database.execute(statement, params)


def _row(url: str, task_id: str) -> dict[str, object]:
    with connect(url) as database:
        database.row_factory = sqlite3.Row
        row = database.execute("SELECT * FROM processing_tasks WHERE id = ?", (task_id,)).fetchone()
    return dict(row)


def _now(url: str) -> int:
    with connect(url) as database:
        return database.execute("SELECT unixepoch()").fetchone()[0]


def _expire(url: str, task_id: str) -> None:
    _sql(url, "UPDATE processing_tasks SET lease_expires_at = unixepoch() - 1 WHERE id = ?", task_id)


def _claim(url: str, owner: str = "worker-a"):
    return task_leases.claim_next(url, owner=owner, lease_seconds=LEASE_SECONDS, max_attempts=MAX_ATTEMPTS)


def _reclaim(url: str):
    return task_leases.reclaim_expired(url, max_attempts=MAX_ATTEMPTS)


# --- migration ---------------------------------------------------------------------------


def test_lease_migration_adds_columns_backfills_existing_tasks_and_keeps_a_backup(tmp_path):
    lease_sql = _lease_migration()
    version = lease_sql.name[:3]
    everything = tmp_path / "all"
    _copy_migrations_through(everything, lease_sql)
    earlier = tmp_path / "before-leases"
    earlier.mkdir()
    for path in everything.glob("*.sql"):
        if path.name != lease_sql.name:
            shutil.copyfile(path, earlier / path.name)

    url = _url(tmp_path / "state.sqlite3")
    migrate(url, earlier)
    existing = tasks.create_material_task(
        url, course_id="course-a", stored_file=_stored_file(tmp_path), idempotency_key="old"
    ).task

    assert migrate(url, everything) == [version]
    assert migrate(url, everything) == []

    with connect(url) as database:
        columns = {row[1] for row in database.execute("PRAGMA table_info(processing_tasks)")}
    assert {
        "lease_owner", "lease_token", "lease_expires_at", "attempt", "not_before", "cleanup_pending",
        "error_code", "error_message", "error_details",
    } <= columns
    row = _row(url, existing.id)
    assert row["lease_owner"] is None and row["lease_token"] is None and row["lease_expires_at"] is None
    assert row["attempt"] == 0
    assert row["cleanup_pending"] == 0
    assert row["error_code"] is None
    with connect(url) as database:
        created = database.execute("SELECT unixepoch(?)", (existing.created_at,)).fetchone()[0]
    assert row["not_before"] == created

    backup = next((tmp_path / "backups").glob(f"*-before-{version}.sqlite"))
    with sqlite3.connect(backup) as copy:
        assert copy.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        backup_columns = {row[1] for row in copy.execute("PRAGMA table_info(processing_tasks)")}
        assert "lease_token" not in backup_columns
        assert copy.execute("SELECT id FROM processing_tasks").fetchall() == [(existing.id,)]


def test_new_task_not_before_defaults_to_its_creation_time(db_url, new_task):
    task_id = new_task()
    row = _row(db_url, task_id)
    with connect(db_url) as database:
        created = database.execute("SELECT unixepoch(?)", (row["created_at"],)).fetchone()[0]
    assert row["not_before"] == created
    assert row["attempt"] == 0 and row["lease_token"] is None


def _migrations_with_probe(tmp_path: Path) -> tuple[Path, str]:
    lease_sql = _lease_migration()
    directory = tmp_path / "with-probe"
    _copy_migrations_through(directory, lease_sql)
    probe_version = f"{int(lease_sql.name[:3]) + 1:03d}"
    (directory / f"{probe_version}_lease_probe.sql").write_text(
        "CREATE TABLE lease_probe (id INTEGER PRIMARY KEY);\n", encoding="utf-8"
    )
    return directory, probe_version


def test_live_lease_on_the_migrated_task_table_blocks_the_next_migration(tmp_path):
    # FIX-MIGRATE-LEASE 交接要求的回归：真实迁移后的 processing_tasks 上，有效租约阻止后续迁移。
    directory, probe_version = _migrations_with_probe(tmp_path)
    earlier = tmp_path / "no-probe"
    earlier.mkdir()
    for path in directory.glob("*.sql"):
        if not path.name.startswith(probe_version):
            shutil.copyfile(path, earlier / path.name)
    url = _url(tmp_path / "state.sqlite3")
    migrate(url, earlier)
    tasks.create_material_task(url, course_id="course-a", stored_file=_stored_file(tmp_path), idempotency_key="k")
    lease = _claim(url)
    assert lease is not None

    with pytest.raises(MigrationError, match="Active task lease"):
        migrate(url, directory)
    with connect(url) as database:
        assert database.execute("SELECT name FROM sqlite_master WHERE name = 'lease_probe'").fetchone() is None
        assert database.execute(
            "SELECT 1 FROM schema_migrations WHERE version = ?", (probe_version,)
        ).fetchone() is None
    assert _row(url, lease.task_id)["lease_token"] == lease.token

    _expire(url, lease.task_id)
    assert migrate(url, directory) == [probe_version]


def test_released_lease_does_not_block_the_next_migration(tmp_path):
    directory, probe_version = _migrations_with_probe(tmp_path)
    url = _url(tmp_path / "state.sqlite3")
    earlier = tmp_path / "no-probe"
    earlier.mkdir()
    for path in directory.glob("*.sql"):
        if not path.name.startswith(probe_version):
            shutil.copyfile(path, earlier / path.name)
    migrate(url, earlier)
    tasks.create_material_task(url, course_id="course-a", stored_file=_stored_file(tmp_path), idempotency_key="k")
    lease = _claim(url)
    assert task_leases.release_on_shutdown(url, lease.task_id, lease.token) is True
    assert migrate(url, directory) == [probe_version]


@pytest.mark.parametrize(
    "statement",
    [
        # I4：failed ⇔ error 非空
        "UPDATE processing_tasks SET stage = 'failed' WHERE id = :id",
        "UPDATE processing_tasks SET error_code = 'INTERNAL_ERROR', error_message = 'x' WHERE id = :id",
        "UPDATE processing_tasks SET stage = 'failed', error_code = 'INTERNAL_ERROR' WHERE id = :id",
        # 令牌与到期时间成对出现
        "UPDATE processing_tasks SET lease_token = :token WHERE id = :id",
        "UPDATE processing_tasks SET lease_expires_at = unixepoch() WHERE id = :id",
        "UPDATE processing_tasks SET lease_token = 'short', lease_expires_at = unixepoch(),"
        " lease_owner = 'w' WHERE id = :id",
        "UPDATE processing_tasks SET attempt = -1 WHERE id = :id",
        "UPDATE processing_tasks SET cleanup_pending = 2 WHERE id = :id",
        "UPDATE processing_tasks SET not_before = NULL WHERE id = :id",
    ],
)
def test_schema_rejects_rows_that_break_lease_or_error_invariants(db_url, new_task, statement):
    task_id = new_task()
    before = _row(db_url, task_id)
    with connect(db_url) as database, pytest.raises(sqlite3.IntegrityError):
        database.execute(statement, {"id": task_id, "token": "a" * 32})
    assert _row(db_url, task_id) == before


# --- claim -------------------------------------------------------------------------------


def test_claim_moves_a_queued_task_to_parsing_with_a_fresh_lease(db_url, new_task):
    task_id = new_task()
    before = _now(db_url)
    lease = _claim(db_url, owner="host:123:abc")
    after = _now(db_url)

    assert lease is not None
    assert lease.task_id == task_id and lease.course_id == "course-a"
    assert lease.stage == "parsing" and lease.progress == 0 and lease.attempt == 1
    assert lease.owner == "host:123:abc"
    assert len(lease.token) >= 32 and int(lease.token, 16) >= 0
    assert before + LEASE_SECONDS <= lease.expires_at <= after + LEASE_SECONDS
    row = _row(db_url, task_id)
    assert (row["stage"], row["attempt"], row["lease_token"], row["lease_owner"], row["lease_expires_at"]) == (
        "parsing", 1, lease.token, "host:123:abc", lease.expires_at,
    )
    assert _claim(db_url, owner="other") is None


def test_two_connections_claiming_the_same_task_exactly_one_wins(db_url, new_task):
    # LEASE-1：两个真实连接并发领取同一 queued 任务，恰好一个成功，另一个影响 0 行。
    for _ in range(10):
        task_id = new_task()
        barrier = threading.Barrier(2)
        results: list[object] = []
        errors: list[BaseException] = []

        def worker(name: str) -> None:
            try:
                barrier.wait()
                results.append(_claim(db_url, owner=name))
            except BaseException as exc:  # pragma: no cover - surfaced below
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(f"w{i}",)) for i in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert errors == []
        winners = [result for result in results if result is not None]
        assert len(winners) == 1 and winners[0].task_id == task_id
        row = _row(db_url, task_id)
        assert row["attempt"] == 1 and row["stage"] == "parsing" and row["lease_token"] == winners[0].token


def test_many_concurrent_workers_each_task_is_owned_once(db_url, new_task):
    task_ids = {new_task() for _ in range(5)}
    barrier = threading.Barrier(8)
    claimed: list[object] = []
    lock = threading.Lock()

    def worker(name: str) -> None:
        barrier.wait()
        while (lease := _claim(db_url, owner=name)) is not None:
            with lock:
                claimed.append(lease)

    threads = [threading.Thread(target=worker, args=(f"w{i}",)) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(lease.task_id for lease in claimed) == sorted(task_ids)
    assert len({lease.token for lease in claimed}) == len(task_ids)


def test_claim_order_is_created_at_then_id_across_courses(db_url, new_task):
    late = new_task("course-a", created_at="2026-01-01T00:00:02.000Z")
    early_b = new_task("course-b", created_at="2026-01-01T00:00:01.000Z")
    early_a = new_task("course-a", created_at="2026-01-01T00:00:01.000Z")
    expected = sorted([early_a, early_b]) + [late]
    got = [_claim(db_url) for _ in range(3)]
    assert [lease.task_id for lease in got] == expected
    assert {lease.course_id for lease in got} == {"course-a", "course-b"}
    assert _claim(db_url) is None


def test_claim_skips_tasks_outside_the_claimable_condition(db_url, new_task):
    future = new_task()
    _sql(db_url, "UPDATE processing_tasks SET not_before = unixepoch() + 30 WHERE id = ?", future)
    cancelled = new_task()
    _sql(db_url, "UPDATE processing_tasks SET stage = 'cancelled', cancel_requested = 1 WHERE id = ?", cancelled)
    flagged = new_task()
    _sql(
        db_url,
        "UPDATE processing_tasks SET stage = 'extracting', progress = 0.2, cancel_requested = 1 WHERE id = ?",
        flagged,
    )
    exhausted = new_task()
    _sql(db_url, "UPDATE processing_tasks SET stage = 'merging', progress = 0.7, attempt = 3 WHERE id = ?", exhausted)
    finished = new_task()
    _sql(db_url, "UPDATE processing_tasks SET stage = 'awaiting_review', progress = 0.95 WHERE id = ?", finished)
    live = new_task()
    held = _claim(db_url, owner="holder")
    assert held.task_id == live

    assert _claim(db_url) is None
    assert _row(db_url, future)["attempt"] == 0

    _sql(db_url, "UPDATE processing_tasks SET not_before = unixepoch() WHERE id = ?", future)
    lease = _claim(db_url)
    assert lease.task_id == future


def test_expired_lease_is_taken_over_without_changing_stage_or_progress(db_url, new_task):
    task_id = new_task()
    first = _claim(db_url, owner="a")
    _sql(db_url, "UPDATE processing_tasks SET stage = 'extracting', progress = 0.3 WHERE id = ?", task_id)
    assert _claim(db_url, owner="b") is None

    _expire(db_url, task_id)
    second = _claim(db_url, owner="b")
    assert second is not None and second.task_id == task_id
    assert second.stage == "extracting" and second.progress == pytest.approx(0.3)
    assert second.attempt == 2 and second.token != first.token and second.owner == "b"


def test_unexpired_lease_is_not_taken_over(db_url, new_task):
    # 未到期的租约不可被接管（领取前把到期时间改为 5 秒后，避免秒边界造成的偶发）。
    task_id = new_task()
    _claim(db_url)
    _sql(db_url, "UPDATE processing_tasks SET lease_expires_at = unixepoch() + 5 WHERE id = ?", task_id)
    assert _claim(db_url, owner="b") is None


def test_claim_and_cancel_race_has_a_deterministic_winner(db_url, new_task):
    # TASK-8：取消先写 → 领取影响 0 行；领取先写 → 取消只能走置标志分支。
    cancel_first = new_task()
    _sql(
        db_url,
        "UPDATE processing_tasks SET stage = 'cancelled', cancel_requested = 1 WHERE id = ? AND stage = 'queued'",
        cancel_first,
    )
    assert _claim(db_url) is None

    claim_first = new_task()
    lease = _claim(db_url)
    assert lease.task_id == claim_first
    with connect(db_url) as database:
        changed = database.execute(
            "UPDATE processing_tasks SET stage = 'cancelled', cancel_requested = 1 WHERE id = ? AND stage = 'queued'",
            (claim_first,),
        ).rowcount
    assert changed == 0
    assert _row(db_url, claim_first)["stage"] == "parsing"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"owner": "", "lease_seconds": 60, "max_attempts": 3},
        {"owner": "w", "lease_seconds": 0, "max_attempts": 3},
        {"owner": "w", "lease_seconds": 60, "max_attempts": 0},
        {"owner": "w", "lease_seconds": True, "max_attempts": 3},
    ],
)
def test_claim_rejects_invalid_arguments_without_touching_tasks(db_url, new_task, kwargs):
    task_id = new_task()
    with pytest.raises(ValueError):
        task_leases.claim_next(db_url, **kwargs)
    assert _row(db_url, task_id)["stage"] == "queued"


# --- renew -------------------------------------------------------------------------------


def test_renew_extends_the_lease_for_the_current_token(db_url, new_task):
    # LEASE-5：心跳续约让即将到期的租约不被接管。
    task_id = new_task()
    lease = _claim(db_url)
    _sql(db_url, "UPDATE processing_tasks SET lease_expires_at = unixepoch() WHERE id = ?", task_id)
    before = _now(db_url)
    expires = task_leases.renew_lease(db_url, task_id, lease.token, lease_seconds=LEASE_SECONDS)
    assert expires is not None and expires >= before + LEASE_SECONDS
    assert _row(db_url, task_id)["lease_expires_at"] == expires
    assert _claim(db_url, owner="b") is None


def test_old_token_cannot_renew_after_takeover(db_url, new_task):
    # LEASE-4（续约）：A 的租约过期、被 B 接管后，A 续约影响 0 行，B 的租约不变。
    task_id = new_task()
    a = _claim(db_url, owner="a")
    _expire(db_url, task_id)
    b = _claim(db_url, owner="b")
    before = _row(db_url, task_id)
    assert task_leases.renew_lease(db_url, task_id, a.token, lease_seconds=LEASE_SECONDS) is None
    assert _row(db_url, task_id) == before
    assert before["lease_token"] == b.token


def test_renew_with_unknown_task_or_empty_token_returns_none(db_url, new_task):
    task_id = new_task()
    _claim(db_url)
    assert task_leases.renew_lease(db_url, "missing", "a" * 32, lease_seconds=LEASE_SECONDS) is None
    with pytest.raises(ValueError):
        task_leases.renew_lease(db_url, task_id, "", lease_seconds=LEASE_SECONDS)


# --- fenced writes -----------------------------------------------------------------------


def _checkpoint_table(url: str) -> None:
    # 模拟附属表（块检查点由 E12 建表）；只用来证明令牌条件与附属写入同事务。
    _sql(url, "CREATE TABLE IF NOT EXISTS fake_checkpoints (task_id TEXT, chunk_id TEXT, token TEXT)")


def test_stale_token_writes_are_rolled_back_and_leave_the_new_owner_untouched(db_url, new_task):
    # LEASE-4：旧令牌的进度上报、块检查点、T6 写入全部影响 0 行；A 停止，B 不受影响。
    _checkpoint_table(db_url)
    task_id = new_task()
    a = _claim(db_url, owner="a")
    _sql(db_url, "UPDATE processing_tasks SET stage = 'extracting', progress = 0.3 WHERE id = ?", task_id)
    _expire(db_url, task_id)
    b = _claim(db_url, owner="b")
    before = _row(db_url, task_id)

    attempts = [
        lambda db: db.execute("UPDATE processing_tasks SET progress = 0.5 WHERE id = ?", (task_id,)),
        lambda db: db.execute("INSERT INTO fake_checkpoints VALUES (?, 'c1', ?)", (task_id, a.token)),
        lambda db: db.execute(
            "UPDATE processing_tasks SET stage = 'awaiting_review', progress = 0.95 WHERE id = ?", (task_id,)
        ),
    ]
    for write in attempts:
        with pytest.raises(LeaseLost):
            with task_leases.leased_transaction(db_url, task_id, a.token) as database:
                write(database)
    assert _row(db_url, task_id) == before
    with connect(db_url) as database:
        assert database.execute("SELECT count(*) FROM fake_checkpoints").fetchone() == (0,)

    with task_leases.leased_transaction(db_url, task_id, b.token) as database:
        database.execute("INSERT INTO fake_checkpoints VALUES (?, 'c1', ?)", (task_id, b.token))
        database.execute("UPDATE processing_tasks SET progress = 0.4 WHERE id = ?", (task_id,))
    assert _row(db_url, task_id)["progress"] == pytest.approx(0.4)
    with connect(db_url) as database:
        assert database.execute("SELECT token FROM fake_checkpoints").fetchall() == [(b.token,)]


def test_leased_transaction_rolls_back_caller_writes_on_error(db_url, new_task):
    _checkpoint_table(db_url)
    task_id = new_task()
    lease = _claim(db_url)
    with pytest.raises(RuntimeError, match="boom"):
        with task_leases.leased_transaction(db_url, task_id, lease.token) as database:
            database.execute("INSERT INTO fake_checkpoints VALUES (?, 'c1', ?)", (task_id, lease.token))
            raise RuntimeError("boom")
    with connect(db_url) as database:
        assert database.execute("SELECT count(*) FROM fake_checkpoints").fetchone() == (0,)


def test_fence_in_a_caller_managed_transaction(db_url, new_task):
    task_id = new_task()
    lease = _claim(db_url)
    with connect(db_url) as database:
        database.execute("BEGIN IMMEDIATE")
        task_leases.fence(database, task_id, lease.token)
        with pytest.raises(LeaseLost):
            task_leases.fence(database, task_id, "f" * 32)
        database.execute("ROLLBACK")


def test_fence_refuses_to_run_outside_a_transaction(db_url, new_task):
    task_id = new_task()
    lease = _claim(db_url)
    with connect(db_url) as database, pytest.raises(RuntimeError):
        task_leases.fence(database, task_id, lease.token)


# --- reclaim -----------------------------------------------------------------------------


def test_reclaim_cancels_an_expired_task_with_a_cancel_request(db_url, new_task):
    # LEASE-8：租约过期且已请求取消 → 回收者转 cancelled，此后不再被领取。
    task_id = new_task("course-b")
    _claim(db_url)
    _sql(
        db_url,
        "UPDATE processing_tasks SET stage = 'extracting', progress = 0.4, cancel_requested = 1 WHERE id = ?",
        task_id,
    )
    _expire(db_url, task_id)

    result = _reclaim(db_url)
    assert [(t.task_id, t.course_id, t.stage) for t in result.cancelled] == [(task_id, "course-b", "cancelled")]
    assert result.failed == ()
    row = _row(db_url, task_id)
    assert row["stage"] == "cancelled" and row["cancel_requested"] == 1
    assert row["progress"] == pytest.approx(0.4)
    assert row["lease_token"] is None and row["lease_expires_at"] is None and row["lease_owner"] is None
    assert _claim(db_url) is None
    assert _reclaim(db_url).cancelled == ()


def test_reclaim_fails_a_task_after_three_consecutive_expired_leases(db_url, new_task):
    # LEASE-7 前半：连续 3 次租约过期 → 回收时 failed，TASK_ATTEMPTS_EXHAUSTED，details.attempts = 3。
    task_id = new_task()
    for attempt in range(1, 4):
        lease = _claim(db_url, owner=f"w{attempt}")
        assert lease.attempt == attempt
        if attempt == 1:
            _sql(db_url, "UPDATE processing_tasks SET stage = 'extracting', progress = 0.25 WHERE id = ?", task_id)
        _expire(db_url, task_id)
        if attempt < 3:
            assert _reclaim(db_url).failed == ()
            assert _row(db_url, task_id)["stage"] == "extracting"

    result = _reclaim(db_url)
    assert [(t.task_id, t.stage) for t in result.failed] == [(task_id, "failed")]
    row = _row(db_url, task_id)
    assert row["stage"] == "failed" and row["progress"] == pytest.approx(0.25)
    assert row["error_code"] == "TASK_ATTEMPTS_EXHAUSTED" and row["error_message"]
    assert json.loads(row["error_details"]) == {"attempts": 3, "stage": "extracting"}
    assert row["lease_token"] is None and row["lease_expires_at"] is None
    assert _claim(db_url) is None


def test_reclaim_leaves_live_and_retryable_tasks_alone(db_url, new_task):
    live = new_task()
    live_lease = _claim(db_url)
    _sql(
        db_url,
        "UPDATE processing_tasks SET stage = 'merging', progress = 0.7, cancel_requested = 1, attempt = 3 WHERE id = ?",
        live,
    )
    retryable = new_task()
    _claim(db_url)
    _sql(db_url, "UPDATE processing_tasks SET stage = 'persisting', progress = 0.85 WHERE id = ?", retryable)
    _expire(db_url, retryable)
    queued = new_task()
    review = new_task()
    _sql(db_url, "UPDATE processing_tasks SET stage = 'awaiting_review', progress = 0.95 WHERE id = ?", review)
    snapshot = {task_id: _row(db_url, task_id) for task_id in (live, retryable, queued, review)}

    result = _reclaim(db_url)
    assert result.cancelled == () and result.failed == ()
    assert {task_id: _row(db_url, task_id) for task_id in snapshot} == snapshot
    assert _row(db_url, live)["lease_token"] == live_lease.token


def test_reclaim_prefers_cancel_over_exhaustion(db_url, new_task):
    task_id = new_task()
    _claim(db_url)
    _sql(
        db_url,
        "UPDATE processing_tasks SET stage = 'parsing', attempt = 3, cancel_requested = 1 WHERE id = ?",
        task_id,
    )
    _expire(db_url, task_id)
    result = _reclaim(db_url)
    assert [t.task_id for t in result.cancelled] == [task_id] and result.failed == ()
    assert _row(db_url, task_id)["error_code"] is None


def test_reclaim_fails_an_exhausted_persisting_task_and_treats_released_leases_as_expired(db_url, new_task):
    task_id = new_task()
    lease = _claim(db_url)
    _sql(db_url, "UPDATE processing_tasks SET stage = 'persisting', progress = 0.9 WHERE id = ?", task_id)
    assert task_leases.release_on_shutdown(db_url, lease.task_id, lease.token)
    # 无人持有（lease_expires_at IS NULL）同样属于回收对象；把上限压到 0 次剩余。
    _sql(db_url, "UPDATE processing_tasks SET attempt = 3 WHERE id = ?", task_id)
    result = _reclaim(db_url)
    assert [t.task_id for t in result.failed] == [task_id]
    row = _row(db_url, task_id)
    assert json.loads(row["error_details"]) == {"attempts": 3, "stage": "persisting"}


def test_reclaim_reports_pending_cleanups_and_clearing_is_course_scoped(db_url, new_task):
    task_id = new_task("course-a")
    _sql(
        db_url,
        "UPDATE processing_tasks SET stage = 'failed', progress = 0.9, error_code = 'STORAGE_UNAVAILABLE',"
        " error_message = '存储不可用', cleanup_pending = 1 WHERE id = ?",
        task_id,
    )
    result = _reclaim(db_url)
    assert [(t.task_id, t.course_id) for t in result.cleanup_pending] == [(task_id, "course-a")]

    assert task_leases.clear_cleanup_pending(db_url, task_id, course_id="course-b") is False
    assert _row(db_url, task_id)["cleanup_pending"] == 1
    assert task_leases.clear_cleanup_pending(db_url, task_id, course_id="course-a") is True
    assert _row(db_url, task_id)["cleanup_pending"] == 0
    assert _reclaim(db_url).cleanup_pending == ()


# --- active release and backoff ----------------------------------------------------------


def test_transient_failure_release_backs_off_thirty_seconds_times_two_to_the_attempt(db_url, new_task):
    task_id = new_task()
    for attempt, delay in ((1, 30), (2, 60)):
        lease = _claim(db_url)
        assert lease.attempt == attempt
        before = _now(db_url)
        outcome = task_leases.release_after_transient_failure(
            db_url, task_id, lease.token, code="STORAGE_UNAVAILABLE", max_attempts=MAX_ATTEMPTS
        )
        after = _now(db_url)
        assert outcome.status == "released"
        row = _row(db_url, task_id)
        assert row["lease_token"] is None and row["lease_owner"] is None and row["lease_expires_at"] is None
        assert before + delay <= row["not_before"] <= after + delay
        assert row["stage"] == "parsing" and row["attempt"] == attempt
        assert _claim(db_url) is None
        _sql(db_url, "UPDATE processing_tasks SET not_before = unixepoch() WHERE id = ?", task_id)


def test_transient_failure_on_the_last_attempt_fails_with_the_fault_code(db_url, new_task):
    # LEASE-7 后半：第 3 次尝试因存储不可用而失败 → failed，STORAGE_UNAVAILABLE，details.attempts = 3。
    task_id = new_task()
    _sql(db_url, "UPDATE processing_tasks SET attempt = 2 WHERE id = ?", task_id)
    lease = _claim(db_url)
    assert lease.attempt == 3
    _sql(db_url, "UPDATE processing_tasks SET stage = 'persisting', progress = 0.85 WHERE id = ?", task_id)
    outcome = task_leases.release_after_transient_failure(
        db_url, task_id, lease.token, code="STORAGE_UNAVAILABLE", max_attempts=MAX_ATTEMPTS
    )
    assert outcome.status == "failed"
    row = _row(db_url, task_id)
    assert row["stage"] == "failed" and row["progress"] == pytest.approx(0.85)
    assert row["error_code"] == "STORAGE_UNAVAILABLE" and row["error_message"]
    assert json.loads(row["error_details"]) == {"attempts": 3, "stage": "persisting"}
    assert row["lease_token"] is None and row["lease_expires_at"] is None


def test_llm_outage_on_the_last_extracting_attempt_fails_with_llm_unavailable(db_url, new_task):
    task_id = new_task()
    _sql(db_url, "UPDATE processing_tasks SET attempt = 2 WHERE id = ?", task_id)
    lease = _claim(db_url)
    _sql(db_url, "UPDATE processing_tasks SET stage = 'extracting', progress = 0.3 WHERE id = ?", task_id)
    outcome = task_leases.release_after_transient_failure(
        db_url, task_id, lease.token, code="LLM_UNAVAILABLE", max_attempts=MAX_ATTEMPTS
    )
    assert outcome.status == "failed"
    assert _row(db_url, task_id)["error_code"] == "LLM_UNAVAILABLE"


def test_release_with_a_stale_token_changes_nothing(db_url, new_task):
    task_id = new_task()
    a = _claim(db_url, owner="a")
    _expire(db_url, task_id)
    _claim(db_url, owner="b")
    before = _row(db_url, task_id)
    outcome = task_leases.release_after_transient_failure(
        db_url, task_id, a.token, code="STORAGE_UNAVAILABLE", max_attempts=MAX_ATTEMPTS
    )
    assert outcome.status == "lost"
    assert task_leases.release_on_shutdown(db_url, task_id, a.token) is False
    assert _row(db_url, task_id) == before


@pytest.mark.parametrize("code", ["INTERNAL_ERROR", "DOCUMENT_UNREADABLE", "TASK_ATTEMPTS_EXHAUSTED", ""])
def test_release_only_accepts_the_two_stage_level_transient_faults(db_url, new_task, code):
    task_id = new_task()
    lease = _claim(db_url)
    before = _row(db_url, task_id)
    with pytest.raises(ValueError):
        task_leases.release_after_transient_failure(
            db_url, task_id, lease.token, code=code, max_attempts=MAX_ATTEMPTS
        )
    assert _row(db_url, task_id) == before


def test_llm_outage_on_the_last_merging_attempt_fails_with_llm_unavailable(db_url, new_task):
    # ADR-017 决定 6：merging 尝试耗尽、最后一次为模型不可用 → 直接 T9，LLM_UNAVAILABLE，
    # details = {attempts, stage}；不再报错后等租约过期、由回收改记 TASK_ATTEMPTS_EXHAUSTED。
    task_id = new_task()
    _sql(db_url, "UPDATE processing_tasks SET attempt = 2 WHERE id = ?", task_id)
    lease = _claim(db_url)
    assert lease.attempt == MAX_ATTEMPTS
    _sql(db_url, "UPDATE processing_tasks SET stage = 'merging', progress = 0.7 WHERE id = ?", task_id)
    outcome = task_leases.release_after_transient_failure(
        db_url, task_id, lease.token, code="LLM_UNAVAILABLE", max_attempts=MAX_ATTEMPTS
    )
    assert outcome == task_leases.ReleaseOutcome("failed")
    row = _row(db_url, task_id)
    assert row["stage"] == "failed" and row["progress"] == pytest.approx(0.7)
    assert row["error_code"] == "LLM_UNAVAILABLE" and row["error_message"]
    assert json.loads(row["error_details"]) == {"attempts": MAX_ATTEMPTS, "stage": "merging"}
    assert row["lease_owner"] is None and row["lease_token"] is None and row["lease_expires_at"] is None
    # 写入的错误能被 C08 的 fail 事件原样接受（同一张码表与耗尽约束）。
    error = TaskError(row["error_code"], row["error_message"], json.loads(row["error_details"]))
    assert isinstance(apply_event(TaskState("merging", 0.7), TransitionEvent("fail", error=error)), Applied)
    # 已是终态：之后的回收既不改码也不重复报告。
    result = _reclaim(db_url)
    assert result.failed == () and result.cancelled == ()
    assert _row(db_url, task_id)["error_code"] == "LLM_UNAVAILABLE"


def test_llm_outage_before_the_last_merging_attempt_backs_off_instead_of_failing(db_url, new_task):
    task_id = new_task()
    lease = _claim(db_url)
    _sql(db_url, "UPDATE processing_tasks SET stage = 'merging', progress = 0.7 WHERE id = ?", task_id)
    outcome = task_leases.release_after_transient_failure(
        db_url, task_id, lease.token, code="LLM_UNAVAILABLE", max_attempts=MAX_ATTEMPTS
    )
    assert outcome.status == "released"
    row = _row(db_url, task_id)
    assert row["stage"] == "merging" and row["error_code"] is None and row["lease_token"] is None


@pytest.mark.parametrize(("stage", "progress"), [("parsing", 0.05), ("persisting", 0.85)])
def test_exhausting_code_not_allowed_in_the_stage_is_refused_without_writing(db_url, new_task, stage, progress):
    # C08 码表：LLM_UNAVAILABLE 只属于 extracting 与（尝试耗尽时的）merging；parsing、persisting 不调用模型。
    task_id = new_task()
    _sql(db_url, "UPDATE processing_tasks SET attempt = 2 WHERE id = ?", task_id)
    lease = _claim(db_url)
    _sql(db_url, "UPDATE processing_tasks SET stage = ?, progress = ? WHERE id = ?", stage, progress, task_id)
    before = _row(db_url, task_id)
    with pytest.raises(ValueError):
        task_leases.release_after_transient_failure(
            db_url, task_id, lease.token, code="LLM_UNAVAILABLE", max_attempts=MAX_ATTEMPTS
        )
    assert _row(db_url, task_id) == before


# --- graceful shutdown -------------------------------------------------------------------


def test_shutdown_release_does_not_count_the_attempt(db_url, new_task):
    # LEASE-9：正常退出主动释放，attempt 回退；重启后再次领取，attempt 与退出前相同。
    task_id = new_task()
    first = _claim(db_url)
    _sql(db_url, "UPDATE processing_tasks SET stage = 'extracting', progress = 0.2 WHERE id = ?", task_id)
    before = _now(db_url)
    assert task_leases.release_on_shutdown(db_url, task_id, first.token) is True
    row = _row(db_url, task_id)
    assert row["attempt"] == 0 and row["lease_token"] is None and row["lease_expires_at"] is None
    assert row["lease_owner"] is None and before <= row["not_before"] <= _now(db_url)
    again = _claim(db_url)
    assert again.task_id == task_id and again.attempt == first.attempt == 1
    assert again.stage == "extracting"


# --- configuration -----------------------------------------------------------------------


@pytest.mark.parametrize("name,value", [("TASK_MAX_ATTEMPTS", "0"), ("TASK_LEASE_SECONDS", "5")])
def test_invalid_lease_configuration_is_refused_by_name(name, value):
    # LEASE-16：非法取值拒绝启动并指出变量名（校验由 B06 的配置加载器提供，worker 启动时调用）。
    with pytest.raises(SettingsError, match=name):
        load_settings({"AUTH_JWT_SECRET": "x" * 40, name: value})
