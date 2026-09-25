"""Persistence for one-time SSE event tickets (migration 006, specs/identity-access.md §5).

Only ``sha256(ticket)`` is stored. ``issue_ticket`` backs ``POST /tasks/{tid}/event-ticket``
(C16); ``redeem_ticket`` is the §5.2 step-1 conditional UPDATE that C11's
``GET /tasks/{tid}/events`` must call before re-running the §4.1 steps 2-4 checks.
"""

from __future__ import annotations

import hashlib
import math
import secrets

from app.repositories.sqlite import connect

# Fixed by specs/identity-access.md §5.1 and §6: not configurable, never longer.
TICKET_TTL_SECONDS = 60
# Claims delete rows whose expiry is more than this many seconds in the past.
STALE_TICKET_RETENTION_SECONDS = 3600
# 32 random bytes = 256 bits; token_urlsafe yields 43 URL-safe characters.
_TICKET_BYTES = 32
# Anything longer cannot be a ticket we issued; refuse without hashing arbitrary input.
_MAX_TICKET_LENGTH = 128


def hash_ticket(ticket: str) -> str:
    return hashlib.sha256(ticket.encode("utf-8")).hexdigest()


def _epoch_seconds(now: float) -> int:
    # Floor: a ticket issued at 100.9 expires at 160, so it never lives longer than 60 s.
    return math.floor(now)


def issue_ticket(sqlite_url: str, *, user_id: str, task_id: str, now: float) -> str:
    """Store a fresh ticket's hash for (user, task) and return the plaintext exactly once.

    The caller must already have authorized ``user_id`` as a teacher member of the task's
    course (§4.1). Rows whose expiry is more than one hour old are deleted in the same
    transaction.
    """
    ticket = secrets.token_urlsafe(_TICKET_BYTES)
    issued_at = _epoch_seconds(now)
    with connect(sqlite_url) as database:
        database.execute("BEGIN IMMEDIATE")
        try:
            database.execute(
                "DELETE FROM event_tickets WHERE expires_at < ?",
                (issued_at - STALE_TICKET_RETENTION_SECONDS,),
            )
            database.execute(
                "INSERT INTO event_tickets"
                " (ticket_hash, user_id, task_id, expires_at, used_at, created_at)"
                " VALUES (?, ?, ?, ?, NULL, ?)",
                (hash_ticket(ticket), user_id, task_id, issued_at + TICKET_TTL_SECONDS, issued_at),
            )
            database.execute("COMMIT")
        except BaseException:
            if database.in_transaction:
                database.execute("ROLLBACK")
            raise
    return ticket


def redeem_ticket(sqlite_url: str, *, ticket: str, task_id: str, now: float) -> str | None:
    """Consume ``ticket`` for ``task_id``; return the issuing ``user_id`` or ``None``.

    ``None`` (unknown, already used, expired, or issued for another task — including a regular
    access token passed as a ticket) must be answered with 401 ``UNAUTHENTICATED``. Success
    only proves the ticket: the caller still re-checks the account and course membership.
    """
    if not ticket or len(ticket) > _MAX_TICKET_LENGTH:
        return None
    ticket_hash = hash_ticket(ticket)
    at = _epoch_seconds(now)
    with connect(sqlite_url) as database:
        database.execute("BEGIN IMMEDIATE")
        try:
            updated = database.execute(
                "UPDATE event_tickets SET used_at = ?"
                " WHERE ticket_hash = ? AND task_id = ? AND used_at IS NULL AND expires_at > ?",
                (at, ticket_hash, task_id, at),
            ).rowcount
            row = None
            if updated == 1:
                row = database.execute(
                    "SELECT user_id FROM event_tickets WHERE ticket_hash = ?", (ticket_hash,)
                ).fetchone()
            database.execute("COMMIT")
        except BaseException:
            if database.in_transaction:
                database.execute("ROLLBACK")
            raise
    return row[0] if row else None
