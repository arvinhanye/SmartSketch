"""Persistence for ``model_calls`` (migration 001; docs/integrations.md「调用记录」, ADR-011 修订 2/3).

One row per physical provider request, keyed by the ``call_id`` generated before sending.
``prewrite`` checks the soft budgets and inserts the ``sent`` row in one write transaction;
``finish`` overwrites the outcome by ``call_id``. Replays of either never add rows.

Billed amount per row (修订 3):

- usage present → ``usage_input + usage_output``;
- no usage and the error was rejected before generation (HTTP 400/401/403/404/413/422/429)
  → 0; such rows store ``error_class`` as ``"<class>:rejected_before_generation"``;
- otherwise (still ``sent``, ``ok`` without usage, 408/5xx/stream break/unparseable) →
  ``input_tokens_est + max_output_tokens`` (``usage_estimated``).

Vector calls (``purpose = "embedding"``) are recorded but never billed nor budget-checked.
The daily budget groups rows by the Beijing (UTC+8) calendar day of ``created_at``, which
SQLite evaluates at prewrite time, so several processes share one allowance.

Rows hold IDs, counts and classifications only: never prompt text, model output or keys.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from typing import Any, Literal

from app.repositories.sqlite import connect

EMBEDDING_PURPOSE = "embedding"
REJECTED_SUFFIX = ":rejected_before_generation"
BEIJING_OFFSET = "+8 hours"

ProviderRole = Literal["primary", "fallback"]
FinishStatus = Literal["ok", "error"]

# Billed tokens of one row; see the module docstring.
BILLED_TOKENS_SQL = (
    "CASE"
    " WHEN usage_input IS NOT NULL AND usage_output IS NOT NULL THEN usage_input + usage_output"
    f" WHEN status = 'error' AND error_class LIKE '%{REJECTED_SUFFIX}' THEN 0"
    " ELSE input_tokens_est + max_output_tokens"
    " END"
)
_DAY = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
# UTC bounds of one Beijing day, in the created_at text format, so the index is usable.
_DAY_START = "strftime('%Y-%m-%dT%H:%M:%fZ', {day}, '-8 hours')"
_DAY_END = "strftime('%Y-%m-%dT%H:%M:%fZ', {day}, '+1 day', '-8 hours')"
_TODAY = f"date('now', '{BEIJING_OFFSET}')"


class BudgetRejected(Exception):
    """The soft budget is used up (``used >= limit``); nothing was written."""

    def __init__(self, scope: Literal["task", "daily"], used: int, limit: int) -> None:
        self.scope = scope
        self.used = used
        self.limit = limit
        super().__init__(f"{scope} token budget used up ({used} >= {limit})")


@dataclass(frozen=True)
class CallRecord:
    """The prewrite: attribution plus the two estimates (字段见「调用记录」)."""

    call_id: str
    course_id: str
    task_id: str | None
    chunk_id: str | None
    request_id: str | None
    purpose: str
    task_attempt: int | None
    chunk_attempt: int | None
    call_seq: int | None
    provider_role: ProviderRole
    is_repair: bool
    model_requested: str
    input_tokens_est: int
    max_output_tokens: int


@dataclass(frozen=True)
class CallOutcome:
    """The write-back after a response (or a provider error) arrived."""

    call_id: str
    status: FinishStatus
    model_responded: str | None
    usage_input: int | None
    usage_output: int | None
    latency_ms: int | None
    error_class: str | None
    rejected_before_generation: bool


def _billed_where(database: sqlite3.Connection, where: str, params: tuple[Any, ...]) -> int:
    row = database.execute(
        f"SELECT COALESCE(SUM({BILLED_TOKENS_SQL}), 0) FROM model_calls"
        f" WHERE purpose <> ? AND {where}",
        (EMBEDDING_PURPOSE, *params),
    ).fetchone()
    return int(row[0])


def _task_billed(database: sqlite3.Connection, task_id: str) -> int:
    return _billed_where(database, "task_id = ?", (task_id,))


def _day_billed(database: sqlite3.Connection, day: str | None) -> int:
    day_sql = _TODAY if day is None else "?"
    params: tuple[Any, ...] = () if day is None else (day, day)
    where = (f"created_at >= {_DAY_START.format(day=day_sql)}"
             f" AND created_at < {_DAY_END.format(day=day_sql)}")
    return _billed_where(database, where, params)


def billed_for_task(sqlite_url: str, task_id: str) -> int:
    """Billed LLM tokens of every attempt of ``task_id`` (ADR-011: not reset by L3)."""
    with connect(sqlite_url) as database:
        return _task_billed(database, task_id)


def billed_for_day(sqlite_url: str, day: str | None = None) -> int:
    """Billed LLM tokens of one Beijing calendar day (``YYYY-MM-DD``; default: today)."""
    if day is not None and not _DAY.fullmatch(day):
        raise ValueError("day must be YYYY-MM-DD")
    with connect(sqlite_url) as database:
        return _day_billed(database, day)


def get_call(sqlite_url: str, call_id: str) -> dict[str, Any] | None:
    with connect(sqlite_url) as database:
        database.row_factory = sqlite3.Row
        row = database.execute("SELECT * FROM model_calls WHERE call_id = ?", (call_id,)).fetchone()
    return dict(row) if row is not None else None


class SqliteCallStore:
    """``CallStore`` over the project SQLite file (one short connection per operation)."""

    def __init__(self, sqlite_url: str) -> None:
        self._sqlite_url = sqlite_url

    def __repr__(self) -> str:
        return "SqliteCallStore()"

    def prewrite(self, record: CallRecord, *, task_budget: int, daily_budget: int) -> None:
        """Check ``used >= limit`` for the task and the day, then insert the ``sent`` row.

        A replay of an existing ``call_id`` is a no-op (not re-checked). Vector calls skip
        the budget check. Raises ``BudgetRejected``; storage errors propagate.
        """
        with connect(self._sqlite_url) as database:
            database.execute("BEGIN IMMEDIATE")
            try:
                exists = database.execute(
                    "SELECT 1 FROM model_calls WHERE call_id = ?", (record.call_id,)
                ).fetchone()
                if exists is None:
                    if record.purpose != EMBEDDING_PURPOSE:
                        if record.task_id is not None:
                            used = _task_billed(database, record.task_id)
                            if used >= task_budget:
                                raise BudgetRejected("task", used, task_budget)
                        used = _day_billed(database, None)
                        if used >= daily_budget:
                            raise BudgetRejected("daily", used, daily_budget)
                    database.execute(
                        "INSERT INTO model_calls (call_id, status, course_id, task_id, chunk_id,"
                        " request_id, purpose, task_attempt, chunk_attempt, call_seq, provider_role,"
                        " is_repair, model_requested, input_tokens_est, max_output_tokens)"
                        " VALUES (?, 'sent', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                        " ON CONFLICT(call_id) DO NOTHING",
                        (
                            record.call_id, record.course_id, record.task_id, record.chunk_id,
                            record.request_id, record.purpose, record.task_attempt,
                            record.chunk_attempt, record.call_seq, record.provider_role,
                            1 if record.is_repair else 0, record.model_requested,
                            record.input_tokens_est, record.max_output_tokens,
                        ),
                    )
                database.execute("COMMIT")
            except BaseException:
                if database.in_transaction:
                    database.execute("ROLLBACK")
                raise

    def finish(self, outcome: CallOutcome) -> None:
        """Overwrite the outcome of ``call_id`` (replays overwrite; unknown IDs change nothing)."""
        error_class = outcome.error_class
        if error_class is not None and outcome.rejected_before_generation:
            error_class += REJECTED_SUFFIX
        if (outcome.usage_input is None) != (outcome.usage_output is None):
            raise ValueError("usage_input and usage_output must both be set or both be None")
        with connect(self._sqlite_url) as database:
            database.execute(
                "UPDATE model_calls SET status = ?, model_responded = ?, usage_input = ?,"
                " usage_output = ?, latency_ms = ?, error_class = ?,"
                " finished_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')"
                " WHERE call_id = ?",
                (
                    outcome.status, outcome.model_responded,
                    outcome.usage_input, outcome.usage_output,
                    outcome.latency_ms, error_class, outcome.call_id,
                ),
            )


__all__ = [
    "BILLED_TOKENS_SQL",
    "EMBEDDING_PURPOSE",
    "REJECTED_SUFFIX",
    "BudgetRejected",
    "CallOutcome",
    "CallRecord",
    "SqliteCallStore",
    "billed_for_day",
    "billed_for_task",
    "get_call",
]
