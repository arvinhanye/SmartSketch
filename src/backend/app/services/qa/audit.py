"""J10: assemble and persist the outcome of a bound chat request."""

from __future__ import annotations

import time
from typing import Any

from app.repositories.chat_logs import ChatLog, write_chat_log
from app.services.qa.chat import ChatAudit


def record_outcome(
    sqlite_url: str, *, request_id: str, user_id: str, course_id: str,
    version_id: str, question: str, started: float,
    terminal: dict[str, Any] | None, audit: ChatAudit | None = None,
) -> None:
    audit = audit or ChatAudit()
    latency_ms = max(0, int((time.monotonic() - started) * 1000))
    reason = error_code = error_reason = None
    citations: tuple[tuple[int, str], ...] = ()
    if terminal is None:
        outcome = "aborted"
    elif terminal["event"] == "done":
        final = terminal["final"]
        outcome = final["status"]
        reason = final.get("reason")
        latency_ms = final["latency_ms"]
        citations = tuple((item["index"], item["chunk_id"]) for item in final["citations"])
    else:
        outcome = "error"
        error = terminal["error"]
        error_code = error["code"]
        error_reason = error.get("details", {}).get("reason")
    write_chat_log(sqlite_url, ChatLog(
        request_id=request_id, user_id=user_id, course_id=course_id,
        version_id=version_id, question=question, outcome=outcome,
        latency_ms=latency_ms, reason=reason, error_code=error_code,
        error_reason=error_reason, citations=citations,
        unknown_citation_count=audit.unknown_citation_count,
        invalidation_subtype=audit.invalidation_subtype,
        uncovered_unit_count=audit.uncovered_unit_count,
        truncated=audit.truncated,
        first_delta_latency_ms=audit.first_delta_latency_ms,
    ))
