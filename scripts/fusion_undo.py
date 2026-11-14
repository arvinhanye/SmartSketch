#!/usr/bin/env python3
"""Inspect automatic merge groups or preview/apply one undo. Never calls a model.

Uses the normal SQLITE_URL/NEO4J_* environment. No migration is run here.
List: --course C --actor TEACHER
Preview: additionally --plan P --group G --expected-revision N
Apply: same arguments plus --apply. Published versions are unaffected.
"""
from __future__ import annotations
import argparse
from contextlib import closing
from dataclasses import asdict
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src' / 'backend'))
from app.config import load_settings
from app.repositories import fusion
from app.repositories.neo4j import Neo4jRepository
from app.repositories.sqlite import connect
from app.services.fusion.undo import preview_undo, undo_merge


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--course', required=True)
    parser.add_argument('--actor', required=True)
    parser.add_argument('--plan')
    parser.add_argument('--group')
    parser.add_argument('--expected-revision', type=int)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args(argv)
    action = args.plan is not None or args.group is not None or args.expected_revision is not None or args.apply
    if action and (not args.plan or not args.group or args.expected_revision is None):
        parser.error('--plan, --group and --expected-revision are all required for preview/apply')
    settings = load_settings()
    with connect(settings.SQLITE_URL) as db:
        fusion.require_teacher(db, args.course, args.actor)
        if not action:
            value = dict(head=asdict(fusion.read_draft_head(db, args.course)), plans=[dict(
                plan_id=p.plan_id, task_id=p.task_id, state=p.state, applied=p.applied, reason=p.reason,
                groups=p.payload['groups'], undone_groups=fusion.undone_groups(db, args.course, p.plan_id),
                completion=p.payload.get('completion'), recall=p.payload.get('recall'))
                for p in fusion.list_plans(db, args.course)])
            print(json.dumps(value, ensure_ascii=False, indent=2)); return 0
    with closing(Neo4jRepository.from_settings(settings)) as repo:
        result = (undo_merge if args.apply else preview_undo)(sqlite_url=settings.SQLITE_URL, repo=repo,
            course_id=args.course, actor_id=args.actor, plan_id=args.plan, group_id=args.group,
            expected_revision=args.expected_revision, lock_seconds=settings.TASK_LEASE_SECONDS,
            wait_seconds=settings.COURSE_LOCK_WAIT_SECONDS)
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    return 2 if result.status == 'conflict' else 0


if __name__ == '__main__':
    raise SystemExit(main())
