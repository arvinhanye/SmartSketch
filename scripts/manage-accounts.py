#!/usr/bin/env python3
"""Operator commands for local accounts: create, disable, enable, reset-password, list.

There is no registration endpoint (specs/identity-access.md §1.2); this script is the only
way to manage accounts. Passwords are never taken as a command-line argument (they would
land in shell history and the process list): they are prompted for, or read from the
environment variable named by ``--password-env``. Output never includes passwords or hashes.

Examples (from the repository root, with SQLITE_URL etc. in the environment)::

    python3 scripts/manage-accounts.py create alice --role teacher
    python3 scripts/manage-accounts.py disable alice
    python3 scripts/manage-accounts.py list
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "backend"))

from app.config import SettingsError, load_settings  # noqa: E402
from app.repositories.accounts import AccountRecord, DuplicateUsername  # noqa: E402
from app.repositories.sqlite import MigrationError, pending_migrations  # noqa: E402
from app.services import account_admin  # noqa: E402
from app.services.auth import ROLES, AccountValidationError, create_account  # noqa: E402


class CommandError(Exception):
    """A refusal to report on stderr with exit status 1."""


def build_parser() -> argparse.ArgumentParser:
    # allow_abbrev=False: otherwise `--password SECRET` would be accepted as an abbreviation of
    # --password-env and the secret would be echoed back in the "variable not set" error.
    parser = argparse.ArgumentParser(
        description="Manage SmartSketch local accounts.", allow_abbrev=False
    )
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create", help="create an enabled account", allow_abbrev=False)
    create.add_argument("username")
    create.add_argument("--role", choices=ROLES, required=True)
    create.add_argument("--password-env", metavar="VAR", help="read the password from $VAR")

    for name, text in (("disable", "disable an account"), ("enable", "re-enable an account")):
        commands.add_parser(name, help=text, allow_abbrev=False).add_argument("username")

    reset = commands.add_parser("reset-password", help="set a new password", allow_abbrev=False)
    reset.add_argument("username")
    reset.add_argument("--password-env", metavar="VAR", help="read the password from $VAR")

    commands.add_parser("list", help="list accounts (never shows password hashes)")
    return parser


def _read_password(env_name: str | None) -> str:
    if env_name:
        value = os.environ.get(env_name)
        if not value:
            raise CommandError(f"environment variable {env_name} is not set")
        return value
    first = getpass.getpass("Password: ")
    if first != getpass.getpass("Repeat password: "):
        raise CommandError("passwords do not match")
    return first


def _describe(record: AccountRecord) -> str:
    state = f"disabled since {record.disabled_at}" if record.disabled_at else "enabled"
    return f"{record.username}\t{record.role}\tcreated {record.created_at}\t{state}"


def run(args: argparse.Namespace, sqlite_url: str) -> None:
    if args.command == "list":
        for record in account_admin.list_accounts(sqlite_url):
            print(_describe(record))
        return
    if args.command == "create":
        password = _read_password(args.password_env)
        try:
            record = create_account(sqlite_url, args.username, password, args.role)
        except DuplicateUsername:
            raise CommandError(f"username already exists: {args.username.lower()}") from None
    elif args.command == "reset-password":
        record = account_admin.reset_password(
            sqlite_url, args.username, _read_password(args.password_env)
        )
    else:
        record = account_admin.set_disabled(sqlite_url, args.username, args.command == "disable")
    print(f"{args.command}: {_describe(record)}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args, extras = parser.parse_known_args(argv)
    if extras:
        # argparse would echo the stray tokens back, and a mistyped `--password SECRET`
        # is the likely one; name the fix without repeating what was typed.
        parser.print_usage(sys.stderr)
        print(
            "unrecognized arguments (not shown); passwords are never accepted on the "
            "command line, use the prompt or --password-env VAR",
            file=sys.stderr,
        )
        return 2
    try:
        settings = load_settings()
        pending = pending_migrations(settings.SQLITE_URL)
        if pending:
            raise CommandError(
                "database has pending migrations (" + ", ".join(pending) + "); "
                "run `python -m app.repositories.sqlite` first"
            )
        run(args, settings.SQLITE_URL)
    except account_admin.AccountNotFound as exc:
        print(f"no such account: {exc}", file=sys.stderr)
        return 1
    except (CommandError, AccountValidationError, SettingsError, MigrationError) as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
