"""Queued task/material seed with fixed timestamps for task event and cleanup tests."""

from app.repositories.sqlite import connect


def insert_queued_task(url: str, course_id: str, task_id: str) -> str:
    with connect(url) as db:
        db.execute(
            "INSERT INTO materials (id, course_id, filename, format, size_bytes, content_hash,"
            " storage_name) VALUES (?, ?, 'a.txt', 'txt', 1, ?, ?)",
            (f"doc-{task_id}", course_id, "sha256:" + "a" * 64, f"stored-{task_id}"),
        )
        db.execute(
            "INSERT INTO processing_tasks (id, course_id, document_id, idempotency_key,"
            " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (task_id, course_id, f"doc-{task_id}", f"key-{task_id}",
             "2026-09-25T00:00:00.000Z", "2026-09-25T00:00:00.000Z"),
        )
    return task_id
