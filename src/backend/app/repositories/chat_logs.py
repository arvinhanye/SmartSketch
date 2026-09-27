"""J10: persist one outcome for each chat request that passed P2 binding.

Rows older than 30 days are removed on each insert. Answers, provisional
deltas, and raw model output are never stored; usage stays in model_calls.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from app.repositories.sqlite import connect


@dataclass(frozen=True, slots=True)
class ChatLog:
    request_id: str
    user_id: str
    course_id: str
    version_id: str
    question: str
    outcome: str
    latency_ms: int
    reason: str | None = None
    error_code: str | None = None
    error_reason: str | None = None
    citations: tuple[tuple[int, str], ...] = ()  # (citation index, text chunk ID)
    unknown_citation_count: int = 0
    invalidation_subtype: str | None = None
    uncovered_unit_count: int = 0
    truncated: bool = False
    first_delta_latency_ms: int | None = None


def write_chat_log(sqlite_url: str, log: ChatLog) -> None:
    """Insert the terminal outcome once; callers invoke this only after P2 succeeds."""
    with connect(sqlite_url) as database:
        database.execute("BEGIN IMMEDIATE")
        database.execute(
            """INSERT INTO chat_logs (
                   request_id, user_id, course_id, version_id, question, outcome,
                   reason, error_code, error_reason, citations_json,
                   unknown_citation_count, invalidation_subtype, uncovered_unit_count,
                   truncated, latency_ms, first_delta_latency_ms
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                log.request_id, log.user_id, log.course_id, log.version_id,
                log.question, log.outcome, log.reason, log.error_code,
                log.error_reason, json.dumps(log.citations),
                log.unknown_citation_count, log.invalidation_subtype,
                log.uncovered_unit_count, int(log.truncated), log.latency_ms,
                log.first_delta_latency_ms,
            ),
        )
        database.execute("DELETE FROM chat_logs WHERE created_at < strftime('%Y-%m-%dT%H:%M:%fZ', 'now', '-30 days')")
        database.execute("COMMIT")


def list_chat_logs(
    sqlite_url: str, *, user_id: str, course_id: str, request_id: str | None = None,
) -> tuple[ChatLog, ...]:
    """Read outcomes only within one student's course scope."""
    query = """SELECT request_id, user_id, course_id, version_id, question, outcome,
                      latency_ms, reason, error_code, error_reason, citations_json,
                      unknown_citation_count, invalidation_subtype, uncovered_unit_count,
                      truncated, first_delta_latency_ms
               FROM chat_logs WHERE user_id=? AND course_id=?"""
    params: tuple[str, ...] = (user_id, course_id)
    if request_id is not None:
        query += " AND request_id=?"
        params += (request_id,)
    query += " ORDER BY created_at DESC, request_id DESC"
    with connect(sqlite_url) as database:
        rows = database.execute(query, params).fetchall()
    return tuple(
        ChatLog(
            request_id=row[0], user_id=row[1], course_id=row[2], version_id=row[3],
            question=row[4], outcome=row[5], latency_ms=row[6], reason=row[7],
            error_code=row[8], error_reason=row[9],
            citations=tuple(tuple(item) for item in json.loads(row[10])),
            unknown_citation_count=row[11], invalidation_subtype=row[12],
            uncovered_unit_count=row[13], truncated=bool(row[14]),
            first_delta_latency_ms=row[15],
        )
        for row in rows
    )


def count_chat_outcomes(sqlite_url: str, *, user_id: str, course_id: str) -> dict[str, int]:
    """Count unique logged requests by terminal outcome in one course scope."""
    with connect(sqlite_url) as database:
        rows = database.execute(
            "SELECT outcome, COUNT(*) FROM chat_logs WHERE user_id=? AND course_id=? GROUP BY outcome",
            (user_id, course_id),
        ).fetchall()
    return dict(rows)
