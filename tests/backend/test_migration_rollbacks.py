"""Every migration from 007 on documents a manual rollback (the convention the per-version rollback tests rely on).

A migration without ROLLBACK lines leaves its schema_migrations row behind when older versions are rolled back, and the
migrator then correctly refuses to apply an older version after a newer recorded one (see test_f12 / test_g02 / test_f13).
"""

import sqlite3
from contextlib import closing

import pytest

from app.repositories.sqlite import MIGRATIONS_DIR, migrate

FIRST_ROLLBACK_VERSION = "007"
MIGRATIONS = sorted(p for p in MIGRATIONS_DIR.glob("*.sql") if p.name[:3] >= FIRST_ROLLBACK_VERSION)


def _rollback_lines(path):
    return [line.split("ROLLBACK:", 1)[1].strip() for line in path.read_text(encoding="utf-8").splitlines() if "ROLLBACK:" in line]


@pytest.mark.parametrize("path", MIGRATIONS, ids=lambda p: p.name)
def test_migration_documents_rollback_including_its_history_row(path):
    steps = _rollback_lines(path)
    assert steps, f"{path.name} must document manual rollback with '-- ROLLBACK: ' lines"
    assert any(step.startswith("DELETE FROM schema_migrations") for step in steps), f"{path.name} rollback must remove its schema_migrations row"


def test_all_migrations_roll_back_in_reverse_order_and_reapply(tmp_path):
    url = f"sqlite:///{tmp_path / 'state.sqlite3'}"
    applied = migrate(url)
    assert applied[-1] == MIGRATIONS[-1].name[:3]
    with closing(sqlite3.connect(tmp_path / "state.sqlite3")) as database, database:
        for path in reversed(MIGRATIONS):
            for step in _rollback_lines(path):
                database.execute(step)
        remaining = {row[0] for row in database.execute("SELECT version FROM schema_migrations")}
    assert remaining == {p.name[:3] for p in MIGRATIONS_DIR.glob("*.sql") if p.name[:3] < FIRST_ROLLBACK_VERSION}
    assert migrate(url) == [p.name[:3] for p in MIGRATIONS]
