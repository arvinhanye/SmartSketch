#!/usr/bin/env python3
"""K09: import the demo course from datasets/demo/manifest.json, idempotently.

Prerequisites: migrations applied, demo accounts seeded (scripts/seed-demo-accounts.py),
Neo4j reachable, and the worker running (``python -m app.workers``) to process uploads.
Configuration comes only from the environment, like the API and worker.

Safe to re-run: existing course, members and processed documents are reused; failed
documents are uploaded again; publishing an unchanged draft keeps the current version.
Only the demo course is written and nothing is deleted.

Exit codes: 0 imported; 1 refused or failed (message on stderr, re-run to retry);
2 configuration error.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "backend"))

from app.config import SettingsError, load_settings  # noqa: E402
from app.repositories.graph_migrations import sqlite_current_space  # noqa: E402
from app.repositories.neo4j import Neo4jRepository  # noqa: E402
from app.repositories.sqlite import MigrationError, pending_migrations  # noqa: E402
from app.services.ai.embeddings import EmbeddingAdapter  # noqa: E402
from app.services.ai.factory import build_embedding_client  # noqa: E402
from app.services.demo_import import DemoImportError, import_demo, load_manifest  # noqa: E402
from app.services.versions.publish import PublishContext, publish  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--manifest", type=Path, default=ROOT / "datasets" / "demo" / "manifest.json")
    parser.add_argument("--wait-seconds", type=float, default=300.0,
                        help="how long to wait for the worker to process uploads (default 300)")
    parser.add_argument("--no-publish", action="store_true", help="import and process only")
    args = parser.parse_args(argv)
    # Neo4j 对尚未出现的可选属性（importance 等）会发 UnknownPropertyKey 通知，对导入无影响
    logging.getLogger("neo4j").setLevel(logging.ERROR)

    try:
        settings = load_settings()
        pending = pending_migrations(settings.SQLITE_URL)
    except (SettingsError, MigrationError) as error:
        print(error, file=sys.stderr)
        return 2
    if pending:
        print("Database has pending migrations (" + ", ".join(pending) + "); run "
              "`python -m app.repositories.sqlite` first", file=sys.stderr)
        return 2

    def publisher(course_id: str, teacher_id: str) -> tuple[int, bool]:
        ctx = PublishContext(
            settings.SQLITE_URL,
            Neo4jRepository.from_settings(settings),
            EmbeddingAdapter(settings, build_embedding_client(settings)),
            sqlite_current_space(settings.SQLITE_URL),
            lease_seconds=settings.PUBLISH_LEASE_SECONDS,
            lock_wait_seconds=settings.COURSE_LOCK_WAIT_SECONDS,
        )
        outcome = publish(ctx, course_id, created_by=teacher_id)
        return outcome.version, outcome.unchanged

    try:
        manifest = load_manifest(args.manifest)
        report = import_demo(settings, manifest, publisher=None if args.no_publish else publisher,
                             wait_seconds=args.wait_seconds)
    except DemoImportError as error:
        print(f"import-demo: {error}", file=sys.stderr)
        return 1
    except Exception as error:  # publish/storage failures: report and let the user re-run
        print(f"import-demo failed ({type(error).__name__}): {error}; re-run to retry", file=sys.stderr)
        return 1
    print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
