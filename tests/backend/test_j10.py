"""J10 chat outcome persistence on the current migration sequence."""

import json
import sqlite3

import pytest

from app.repositories.chat_logs import ChatLog, write_chat_log
from app.repositories.sqlite import connect, migrate


def test_one_log_per_bound_request(tmp_path):
    url = f"sqlite:///{(tmp_path / 'chat.sqlite').as_posix()}"
    assert migrate(url)[-1] == "014"
    user_id = "u" * 32
    course_id = "c" * 32
    version_id = "v" * 26
    with connect(url) as db:
        db.execute(
            "INSERT INTO users(id, username, password_hash, role) VALUES (?, 'teacher', ?, 'teacher')",
            (user_id, "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA"),
        )
        db.execute("INSERT INTO courses(id, name, teacher_id) VALUES (?, 'Course', ?)", (course_id, user_id))
        db.execute(
            "INSERT INTO graph_versions(version_id, course_id, kind, expires_at) VALUES (?, ?, 'publish', 1)",
            (version_id, course_id),
        )

    log = ChatLog(
        request_id="r" * 26, user_id=user_id, course_id=course_id,
        version_id=version_id, question="What is a stack?", outcome="answered",
        latency_ms=42, citations=((1, "chunk-1"),), first_delta_latency_ms=12,
    )
    write_chat_log(url, log)
    with connect(url) as db:
        row = db.execute(
            "SELECT question, outcome, citations_json, first_delta_latency_ms FROM chat_logs WHERE request_id = ?",
            (log.request_id,),
        ).fetchone()
    assert row[:2] == ("What is a stack?", "answered")
    assert json.loads(row[2]) == [[1, "chunk-1"]]
    assert row[3] == 12
    with pytest.raises(sqlite3.IntegrityError):
        write_chat_log(url, log)
