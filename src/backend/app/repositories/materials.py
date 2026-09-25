"""Persistence for uploaded course materials in the SQLite ``materials`` table."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Literal

from app.repositories.sqlite import connect

MaterialFormat = Literal["pdf", "docx", "txt", "markdown"]


@dataclass(frozen=True)
class MaterialRecord:
    id: str
    course_id: str
    filename: str
    format: MaterialFormat
    size_bytes: int
    content_hash: str
    storage_name: str
    parse_status: str
    uploaded_at: str


_COLUMNS = (
    "id, course_id, filename, format, size_bytes, content_hash, storage_name, "
    "parse_status, uploaded_at"
)


def insert_material(
    database: sqlite3.Connection,
    *,
    material_id: str,
    course_id: str,
    filename: str,
    format: MaterialFormat,
    size_bytes: int,
    content_hash: str,
    storage_name: str,
) -> MaterialRecord:
    """Insert a material on the caller's connection and in its transaction."""
    database.execute(
        """INSERT INTO materials
           (id, course_id, filename, format, size_bytes, content_hash, storage_name)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (material_id, course_id, filename, format, size_bytes, content_hash, storage_name),
    )
    row = database.execute(
        f"SELECT {_COLUMNS} FROM materials WHERE id = ?", (material_id,)
    ).fetchone()
    if row is None:
        raise RuntimeError("material insert did not return a row")
    return MaterialRecord(*row)


def get_material(
    sqlite_url: str, material_id: str, *, course_id: str | None = None
) -> MaterialRecord | None:
    """Return a material, optionally constrained to its owning course."""
    where = "id = ?" if course_id is None else "id = ? AND course_id = ?"
    parameters = (material_id,) if course_id is None else (material_id, course_id)
    with connect(sqlite_url) as database:
        row = database.execute(
            f"SELECT {_COLUMNS} FROM materials WHERE {where}", parameters
        ).fetchone()
    return MaterialRecord(*row) if row else None


def get_material_in_connection(
    database: sqlite3.Connection, material_id: str, *, course_id: str
) -> MaterialRecord | None:
    """Read a material using an existing transaction/connection."""
    row = database.execute(
        f"SELECT {_COLUMNS} FROM materials WHERE id = ? AND course_id = ?",
        (material_id, course_id),
    ).fetchone()
    return MaterialRecord(*row) if row else None
