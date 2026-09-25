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
    sqlite_url: str, material_id: str, *, course_id: str
) -> MaterialRecord | None:
    """Return a material constrained to its owning course."""
    with connect(sqlite_url) as database:
        row = database.execute(
            f"SELECT {_COLUMNS} FROM materials WHERE id = ? AND course_id = ?",
            (material_id, course_id),
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


def list_materials(sqlite_url: str, *, course_id: str) -> list[MaterialRecord]:
    """List one course's materials, ``parse_status`` read from the latest created task (D-16).

    The latest task is the one with the greatest ``created_at``; ties fall back to insertion
    order (``rowid``). A material without any task keeps its column value (the ``queued``
    default). Rows are ordered by ``uploaded_at`` then ``id`` so the listing is stable.
    """
    with connect(sqlite_url) as database:
        rows = database.execute(
            """SELECT m.id, m.course_id, m.filename, m.format, m.size_bytes, m.content_hash,
                      m.storage_name,
                      COALESCE(latest.stage, m.parse_status) AS parse_status,
                      m.uploaded_at
               FROM materials AS m
               LEFT JOIN processing_tasks AS latest
                 ON latest.rowid = (
                    SELECT t.rowid FROM processing_tasks AS t
                    WHERE t.course_id = m.course_id AND t.document_id = m.id
                    ORDER BY t.created_at DESC, t.rowid DESC
                    LIMIT 1
                 )
               WHERE m.course_id = ?
               ORDER BY m.uploaded_at, m.id""",
            (course_id,),
        ).fetchall()
    return [MaterialRecord(*row) for row in rows]
