"""J10: turn one chat request's events into exactly one ``chat_logs`` row (Q10).

The recorder is created only after P2 (request bound to a published version and
given a ``request_id``). It observes the events actually delivered to the client
and writes once: ``done`` → answered / not_covered, ``error`` → error, and no
terminal event → aborted. A logging failure never changes the chat response.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from typing import Any

from app.repositories.chat_logs import ChatLog, ChatLogScopeError, write_chat_log
from app.services.versions.resolver import PublishedVersion

logger = logging.getLogger(__name__)


class ChatAudit:
    def __init__(self, sqlite_url: str, *, request_id: str, user_id: str,
                 version: PublishedVersion, question: str, started: float) -> None:
        self.sqlite_url = sqlite_url
        self.request_id = request_id
        self.user_id = user_id
        self.version = version
        self.question = question
        self.started = started
        self.first_delta_ms: int | None = None
        self.unknown_citation_count = 0
        self.invalidation_subtype: str | None = None
        self.uncovered_unit_count = 0
        self.truncated = False
        self._terminal: dict[str, Any] | None = None
        self.written = False

    def _elapsed_ms(self) -> int:
        return max(0, int((time.monotonic() - self.started) * 1000))

    def diagnose(self, *, unknown_count: int, invalidation_subtype: str | None,
                 uncited_units: int, truncated: bool) -> None:
        """Citation-validation facts that the public ``final`` does not carry."""
        self.unknown_citation_count = unknown_count
        self.invalidation_subtype = invalidation_subtype
        self.uncovered_unit_count = uncited_units
        self.truncated = truncated

    def observe(self, event: dict[str, Any]) -> None:
        """Feed each event as it is delivered; the first terminal event wins."""
        if self._terminal is not None:
            return
        kind = event.get("event")
        if kind == "delta" and self.first_delta_ms is None:
            self.first_delta_ms = self._elapsed_ms()
        elif kind in ("done", "error"):
            self._terminal = event

    def fail(self, body: dict[str, Any]) -> None:
        """Record a failure that happened before any event (P3～P4)."""
        self.observe({"event": "error", "error": body})

    def build(self) -> ChatLog:
        common = dict(
            request_id=self.request_id, user_id=self.user_id,
            course_id=self.version.course_id, version_id=self.version.version_id,
            question=self.question, first_delta_latency_ms=self.first_delta_ms,
        )
        terminal = self._terminal
        if terminal is None:
            return ChatLog(**common, outcome="aborted", latency_ms=self._elapsed_ms(),
                           truncated=self.truncated)
        if terminal["event"] == "error":
            error = terminal["error"]
            return ChatLog(**common, outcome="error", latency_ms=self._elapsed_ms(),
                           error_code=error.get("code"),
                           error_reason=(error.get("details") or {}).get("reason"),
                           truncated=self.truncated)
        final = terminal["final"]
        outcome = final["status"]
        return ChatLog(
            **common, outcome=outcome, latency_ms=int(final["latency_ms"]),
            reason=final.get("reason") if outcome == "not_covered" else None,
            citations=tuple((int(item["index"]), str(item["chunk_id"]))
                            for item in final.get("citations", ())),
            unknown_citation_count=self.unknown_citation_count,
            invalidation_subtype=self.invalidation_subtype,
            uncovered_unit_count=self.uncovered_unit_count,
            truncated=self.truncated,
        )

    def record(self) -> bool:
        """Write the row once; later calls are no-ops. Returns whether a row was written."""
        if self.written:
            return False
        self.written = True
        log = self.build()
        try:
            write_chat_log(self.sqlite_url, log)
        except (sqlite3.Error, ChatLogScopeError) as error:
            logger.warning("chat log not written request_id=%s outcome=%s error_type=%s",
                           self.request_id, log.outcome, type(error).__name__)
            return False
        return True
