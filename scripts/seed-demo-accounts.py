#!/usr/bin/env python3
"""Create the demo accounts (demo_teacher, demo_student, demo_student2) if they are missing.

The password comes only from SEED_DEMO_PASSWORD; without it the script exits non-zero and
writes nothing (specs/identity-access.md §1.2). Re-running never duplicates accounts and
never resets an existing account's password. Run migrations first:
``python -m app.repositories.sqlite`` from ``src/backend``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "backend"))

from app.config import SettingsError, load_settings  # noqa: E402
from app.repositories.sqlite import MigrationError, pending_migrations  # noqa: E402
from app.services.account_admin import DemoSeedConflict, seed_demo_accounts  # noqa: E402
from app.services.auth import AccountValidationError  # noqa: E402


def main() -> int:
    password = os.environ.get("SEED_DEMO_PASSWORD", "")
    if not password.strip():
        print("SEED_DEMO_PASSWORD is not set; refusing to seed demo accounts", file=sys.stderr)
        return 1
    try:
        settings = load_settings()
        pending = pending_migrations(settings.SQLITE_URL)
    except (SettingsError, MigrationError) as exc:
        print(exc, file=sys.stderr)
        return 1
    if pending:
        print(
            "Database has pending migrations (" + ", ".join(pending) + "); "
            "run `python -m app.repositories.sqlite` first",
            file=sys.stderr,
        )
        return 1
    try:
        outcomes = seed_demo_accounts(settings.SQLITE_URL, password)
    except (AccountValidationError, DemoSeedConflict) as exc:
        print(f"Seed refused: {exc}", file=sys.stderr)
        return 1
    for outcome in outcomes:
        state = "created" if outcome.created else "exists, unchanged"
        print(f"{outcome.username} ({outcome.role}): {state}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
