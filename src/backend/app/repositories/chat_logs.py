"""J10: persist one outcome for each chat request that passed P2 binding.

Rows older than 30 days are removed on each insert. Answers, provisional
deltas, evidence text and raw model output are never stored; usage stays in
model_calls and is joined by request_id. Every read is scoped to one course.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from app.repositories.sqlite import connect

OUTCOMES = ("answered", "not_covered", "error", "aborted")
RETENTION_DAYS = 30
MAX_LIST_LIMIT = 500

_COLUMNS = (
    "request_id, user_id, course_id, version_id, question, outcome, latency_ms,"
    " reason, error_code, error_reason, citations_json, unknown_citation_count,"
    " invalidation_subtype, uncovered_unit_count, truncated, first_delta_latency_ms,"
    " created_at"
)


class ChatLogScopeError(ValueError):
    """The bound version does not belong to the logged course."""


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
    created_at: str | None = None  # set by the database; ignored on write


def write_chat_log(sqlite_url: str, log: ChatLog) -> None:
    """Insert the terminal outcome once; callers invoke this only after P2 succeeds.

    A second write for the same ``request_id`` raises ``sqlite3.IntegrityError``,
    so one request is never counted twice.
    """
    with connect(sqlite_url) as database:
        database.execute("BEGIN IMMEDIATE")
        owner = database.execute(
            "SELECT course_id FROM graph_versions WHERE version_id = ?", (log.version_id,)
        ).fetchone()
        if owner is None or owner[0] != log.course_id:
            database.execute("ROLLBACK")
            raise ChatLogScopeError("chat log version does not belong to its course")
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
        database.execute(
            "DELETE FROM chat_logs WHERE created_at < strftime('%Y-%m-%dT%H:%M:%fZ', 'now', ?)",
            (f"-{RETENTION_DAYS} days",),
        )
        database.execute("COMMIT")


def _row(row: tuple[Any, ...]) -> ChatLog:
    (request_id, user_id, course_id, version_id, question, outcome, latency_ms, reason,
     error_code, error_reason, citations_json, unknown, subtype, uncovered, truncated,
     first_delta, created_at) = row
    return ChatLog(
        request_id=request_id, user_id=user_id, course_id=course_id, version_id=version_id,
        question=question, outcome=outcome, latency_ms=latency_ms, reason=reason,
        error_code=error_code, error_reason=error_reason,
        citations=tuple((int(index), str(chunk)) for index, chunk in json.loads(citations_json)),
        unknown_citation_count=unknown, invalidation_subtype=subtype,
        uncovered_unit_count=uncovered, truncated=bool(truncated),
        first_delta_latency_ms=first_delta, created_at=created_at,
    )


def _filters(course_id: str, user_id: str | None, since: str | None,
             outcome: str | None) -> tuple[str, list[Any]]:
    clauses, params = ["course_id = ?"], [course_id]
    if user_id is not None:
        clauses.append("user_id = ?")
        params.append(user_id)
    if since is not None:
        clauses.append("created_at >= ?")
        params.append(since)
    if outcome is not None:
        if outcome not in OUTCOMES:
            raise ValueError(f"unknown chat outcome: {outcome}")
        clauses.append("outcome = ?")
        params.append(outcome)
    return " AND ".join(clauses), params


def list_chat_logs(sqlite_url: str, *, course_id: str, user_id: str | None = None,
                   since: str | None = None, outcome: str | None = None,
                   limit: int = 100) -> list[ChatLog]:
    """Newest first within one course; ``since`` is an ISO-8601 UTC timestamp."""
    if not 1 <= limit <= MAX_LIST_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_LIST_LIMIT}")
    where, params = _filters(course_id, user_id, since, outcome)
    with connect(sqlite_url) as database:
        rows = database.execute(
            f"SELECT {_COLUMNS} FROM chat_logs WHERE {where}"
            " ORDER BY created_at DESC, request_id DESC LIMIT ?",
            (*params, limit),
        ).fetchall()
    return [_row(row) for row in rows]


def get_chat_log(sqlite_url: str, *, course_id: str, request_id: str) -> ChatLog | None:
    with connect(sqlite_url) as database:
        row = database.execute(
            f"SELECT {_COLUMNS} FROM chat_logs WHERE course_id = ? AND request_id = ?",
            (course_id, request_id),
        ).fetchone()
    return None if row is None else _row(row)


def chat_stats(sqlite_url: str, *, course_id: str, since: str | None = None) -> dict[str, Any]:
    """Per-course request counts; one row is one request, so retries never double count."""
    where, params = _filters(course_id, None, since, None)
    with connect(sqlite_url) as database:
        outcomes = dict(database.execute(
            f"SELECT outcome, COUNT(*) FROM chat_logs WHERE {where} GROUP BY outcome", params
        ).fetchall())
        reasons = dict(database.execute(
            f"SELECT reason, COUNT(*) FROM chat_logs WHERE {where} AND outcome = 'not_covered'"
            " GROUP BY reason", params
        ).fetchall())
        errors = dict(database.execute(
            f"SELECT error_code, COUNT(*) FROM chat_logs WHERE {where} AND outcome = 'error'"
            " GROUP BY error_code", params
        ).fetchall())
        latency = database.execute(
            f"SELECT COUNT(*), AVG(latency_ms), MAX(latency_ms) FROM chat_logs WHERE {where}", params
        ).fetchone()
        users = database.execute(
            f"SELECT COUNT(DISTINCT user_id) FROM chat_logs WHERE {where}", params
        ).fetchone()[0]
    return {
        "requests": latency[0],
        "users": users,
        "outcomes": {outcome: outcomes.get(outcome, 0) for outcome in OUTCOMES},
        "not_covered_reasons": reasons,
        "error_codes": errors,
        "latency_ms": {"avg": None if latency[1] is None else round(latency[1], 1), "max": latency[2]},
    }
