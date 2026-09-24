"""Read or record the active embedding space in the migrated SQLite table.

The table itself is created only by migration 001 (ADR-012 补注修订 1, REVIEW-C01-R03).
"""

import sqlite3
from contextlib import closing
from pathlib import Path


def read_or_initialize_space(
    sqlite_url: str, model: str, dimensions: int, is_fake: int
) -> tuple[str, int, int]:
    """Return the persisted space, inserting it only on the first startup."""
    database = Path(sqlite_url.removeprefix("sqlite:///"))
    database.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(database, timeout=5)) as connection:
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT model, dimensions, is_fake FROM embedding_space_state WHERE singleton = 1"
            ).fetchone()
            if row is None:
                connection.execute(
                    """INSERT INTO embedding_space_state
                    (singleton, model, dimensions, is_fake) VALUES (1, ?, ?, ?)""",
                    (model, dimensions, is_fake),
                )
                return model, dimensions, is_fake
            return row
