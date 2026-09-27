#!/usr/bin/env python3
"""K04: measure worker stages and optional published-course QA on a fixed fixture.

Generate the input once, then upload it as a *new* document for each sample in an
otherwise idle benchmark course. Run this command with that course's queued tasks
and its worker stopped. The command runs F13's real pipeline; it needs the normal
SQLite, storage and Neo4j services. It never publishes a graph or starts a server.

    python evaluation/benchmark_pipeline.py fixture --out benchmark.md
    python evaluation/benchmark_pipeline.py run --samples 3 --out benchmark.json

For QA, publish the processed course separately and pass --course-id with
BENCHMARK_API_URL and BENCHMARK_STUDENT_TOKEN in the environment. Live model calls
require both LLM_MODE=live and --allow-paid. Fake measurements are labeled as such.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
import time
import urllib.request
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from functools import wraps
from pathlib import Path
from typing import Any
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "backend"))
sys.path.insert(0, str(ROOT))

from app.repositories.model_calls import SqliteCallStore  # noqa: E402
from app.services.ai.entities import EntityExtractor  # noqa: E402
from app.services.ai.fake import FakeModelClient  # noqa: E402
from app.services.ai.policy import ModelCallPolicy  # noqa: E402
from app.services.ai.relations import RelationExtractor  # noqa: E402
from app.workers.extract_task import ExtractionToolkit  # noqa: E402
from evaluation.run_live_extraction import fake_responder  # noqa: E402
from app.config import load_settings  # noqa: E402
from app.repositories.model_calls import BILLED_TOKENS_SQL  # noqa: E402
from app.repositories.neo4j import Neo4jRepository  # noqa: E402
from app.repositories.sqlite import connect  # noqa: E402
from app.workers import persist_graph, runner  # noqa: E402

FIXTURE_SOURCE = ROOT / "evaluation" / "fixtures" / "synthetic.json"
FIXTURE_CHARS = 20_000
STAGES = ("parsing", "extracting", "merging", "persisting")
STAGE_FUNCTIONS = {
    "parsing": "run_parse_stage",
    "extracting": "run_extract_stage",
    "merging": "run_merge_stage",
    "persisting": "run_persist_stage",
}
QUESTION = "栈和队列的操作次序有何不同？"
TARGETS = {"qa_first_token_ms": 3000, "qa_complete_ms": 10000, "qa_contest_ms": 15000}


def fixture_text() -> str:
    """Repeat the repository's self-authored chapter in a stable ~20k character file."""
    source = json.loads(FIXTURE_SOURCE.read_text(encoding="utf-8"))
    chapter = source["documents"][0]["text"].strip()
    parts: list[str] = []
    size = 0
    while size < FIXTURE_CHARS:
        part = f"\n\n# 性能样本 {len(parts) + 1}\n\n{chapter}"
        parts.append(part)
        size += len(part)
    return ("".join(parts)[:FIXTURE_CHARS].rstrip() + "\n")


def queued_fixture_count(sqlite_url: str) -> int:
    """Require an idle queue containing only this fixed Markdown input."""
    expected = "sha256:" + hashlib.sha256(fixture_text().encode("utf-8")).hexdigest()
    with connect(sqlite_url) as database:
        rows = database.execute(
            "SELECT t.stage, m.format, m.content_hash FROM processing_tasks AS t"
            " JOIN materials AS m ON m.id = t.document_id AND m.course_id = t.course_id"
            " WHERE t.stage IN ('queued', 'parsing', 'extracting', 'merging', 'persisting')"
        ).fetchall()
    if any(stage != "queued" or source_format != "markdown" or digest != expected
           for stage, source_format, digest in rows):
        raise ValueError("active queue includes a task other than the fixed K04 fixture")
    return len(rows)


def percentile(values: Sequence[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * p
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower), 2)


def token_usage(sqlite_url: str, column: str, identity: str) -> dict[str, int]:
    """Use E04 billing rules; returned usage and estimated usage stay separate."""
    if column not in ("task_id", "request_id"):
        raise ValueError("unsupported model-call identity")
    with connect(sqlite_url) as database:
        row = database.execute(
            f"SELECT COUNT(*), COALESCE(SUM(usage_input), 0),"
            f" COALESCE(SUM(usage_output), 0), COALESCE(SUM({BILLED_TOKENS_SQL}), 0),"
            " COALESCE(SUM(CASE WHEN usage_input IS NULL OR usage_output IS NULL THEN 1 ELSE 0 END), 0)"
            f" FROM model_calls WHERE {column} = ? AND purpose <> 'embedding'",
            (identity,),
        ).fetchone()
    return dict(zip(("calls", "input", "output", "billed", "estimated_calls"), map(int, row)))


def build_toolkit(settings: Any) -> ExtractionToolkit:
    if settings.LLM_MODE == "live":
        return runner.build_toolkit(settings)
    primary = FakeModelClient(responder=fake_responder)
    policy = ModelCallPolicy.from_settings(
        settings, primary=primary, store=SqliteCallStore(settings.SQLITE_URL)
    )
    return ExtractionToolkit(
        policy=policy,
        entities=lambda client: EntityExtractor(client, model=runner.FAKE_MODEL_ID,
                                                 max_output_tokens=runner.MAX_OUTPUT_TOKENS),
        relations=lambda client: RelationExtractor(client, model=runner.FAKE_MODEL_ID,
                                                   max_output_tokens=runner.MAX_OUTPUT_TOKENS),
    )


def measure_worker(settings: Any, toolkit: Any, repo: Any) -> dict[str, Any] | None:
    """Wrap F13's four imported stage functions for one claimed queued task."""
    observations: list[dict[str, Any]] = []
    original = {stage: getattr(persist_graph, name) for stage, name in STAGE_FUNCTIONS.items()}
    patches = []
    for stage, name in STAGE_FUNCTIONS.items():
        function = original[stage]

        def timed(*args: Any, _stage: str = stage, _function: Callable[..., Any] = function,
                  **kwargs: Any) -> Any:
            lease = args[1]
            before = token_usage(settings.SQLITE_URL, "task_id", lease.task_id)
            start = time.perf_counter_ns()
            result = _function(*args, **kwargs)
            elapsed = (time.perf_counter_ns() - start) / 1_000_000
            after = token_usage(settings.SQLITE_URL, "task_id", lease.task_id)
            observations.append({
                "stage": _stage,
                "elapsed_ms": round(elapsed, 2),
                "tokens_billed": after["billed"] - before["billed"],
                "model_calls": after["calls"] - before["calls"],
            })
            return result

        patches.append(patch.object(persist_graph, name, wraps(function)(timed)))
    try:
        for active in patches:
            active.start()
        start = time.perf_counter_ns()
        result = persist_graph.run_pipeline_once(settings, toolkit=toolkit, repo=repo)
        elapsed = (time.perf_counter_ns() - start) / 1_000_000
    finally:
        for active in reversed(patches):
            active.stop()
    if result.lease is None:
        return None
    return {
        "task_id": result.lease.task_id,
        "elapsed_ms": round(elapsed, 2),
        "stages": observations,
        "outcomes": dict(result.stages),
        "complete": len(result.stages) == len(STAGES)
        and all(stage == expected and status == "advanced"
                for (stage, status), expected in zip(result.stages, STAGES)),
        "tokens": token_usage(settings.SQLITE_URL, "task_id", result.lease.task_id),
    }


def measure_qa(sqlite_url: str, course_id: str, base_url: str, token: str) -> dict[str, Any]:
    url = base_url.rstrip("/") + f"/api/v1/courses/{course_id}/chat"
    body = json.dumps({"question": QUESTION}, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json",
                 "Content-Type": "application/json"},
    )
    start = time.perf_counter_ns()
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.load(response)
    elapsed = (time.perf_counter_ns() - start) / 1_000_000
    request_id = payload.get("request_id")
    return {
        "elapsed_ms": round(elapsed, 2),
        "status": payload.get("status"),
        "request_id": request_id,
        "tokens": token_usage(sqlite_url, "request_id", request_id) if request_id else None,
    }


def summarize(samples: Sequence[dict[str, Any]], key: str) -> dict[str, Any]:
    values = [sample[key] for sample in samples]
    return {"count": len(values), "p50": percentile(values, 0.50), "p95": percentile(values, 0.95)}


def build_report(settings: Any, workers: list[dict[str, Any]], qa: list[dict[str, Any]]) -> dict[str, Any]:
    stages = {
        stage: summarize(
            [item for worker in workers for item in worker["stages"] if item["stage"] == stage],
            "elapsed_ms",
        )
        for stage in STAGES
    }
    return {
        "status": "measured" if workers and all(worker["complete"] for worker in workers)
        else "incomplete",
        "measured_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "fixture": {"source": str(FIXTURE_SOURCE.relative_to(ROOT)), "characters": len(fixture_text())},
        "environment": {
            "machine": platform.node(), "os": platform.platform(),
            "python": platform.python_version(), "cpu": platform.processor(),
            "llm_mode": settings.LLM_MODE,
            "model": settings.LLM_EXTRACTION_MODEL if settings.LLM_MODE == "live" else "fake",
            "worker_processes": settings.WORKER_PROCESSES,
            "llm_max_concurrency": settings.LLM_MAX_CONCURRENCY,
        },
        "targets_ms": TARGETS,
        "observed": {
            "worker_samples": len(workers), "worker_total_ms": summarize(workers, "elapsed_ms"),
            "stages_ms": stages, "qa_samples": len(qa), "qa_complete_ms": summarize(qa, "elapsed_ms"),
        },
        "worker_runs": workers,
        "qa_runs": qa,
        "notes": [
            "目标值与实测值分列；没有样本的 p50/p95 为 null。",
            "JSON 问答测量为完整响应时间，不提供首字时间。",
            "假模型结果只代表本地流程，不代表真实模型性能。" if settings.LLM_MODE == "fake"
            else "真实模型调用会产生费用。",
        ],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    fixture = commands.add_parser("fixture", help="write the fixed self-authored Markdown fixture")
    fixture.add_argument("--out", type=Path, required=True)
    run = commands.add_parser("run", help="run queued tasks and write a JSON measurement report")
    run.add_argument("--samples", type=int, required=True)
    run.add_argument("--out", type=Path, required=True)
    run.add_argument("--course-id")
    run.add_argument("--qa-samples", type=int, default=0)
    run.add_argument("--allow-paid", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "fixture":
        args.out.write_text(fixture_text(), encoding="utf-8")
        return 0
    if args.samples < 1 or args.qa_samples < 0:
        parser.error("--samples must be positive and --qa-samples cannot be negative")
    settings = load_settings()
    if settings.LLM_MODE == "live" and not args.allow_paid:
        parser.error("live model calls require --allow-paid")
    if args.qa_samples and not args.allow_paid:
        parser.error("QA calls require --allow-paid because the API may use a live model")
    base_url = os.environ.get("BENCHMARK_API_URL", "")
    student_token = os.environ.get("BENCHMARK_STUDENT_TOKEN", "")
    if args.qa_samples and not (args.course_id and base_url and student_token):
        parser.error("QA requires --course-id, BENCHMARK_API_URL and BENCHMARK_STUDENT_TOKEN")
    if queued_fixture_count(settings.SQLITE_URL) < args.samples:
        parser.error("upload one fresh K04 fixture for each requested worker sample")
    toolkit = build_toolkit(settings)
    repo = Neo4jRepository.from_settings(settings)
    workers = []
    for _ in range(args.samples):
        measured = measure_worker(settings, toolkit, repo)
        if measured is None:
            break
        workers.append(measured)
        if not measured["complete"]:
            break
    qa = [measure_qa(settings.SQLITE_URL, args.course_id, base_url, student_token)
          for _ in range(args.qa_samples)] if all(worker["complete"] for worker in workers) else []
    args.out.write_text(json.dumps(build_report(settings, workers, qa), ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    return 0 if len(workers) == args.samples and all(worker["complete"] for worker in workers) else 1


if __name__ == "__main__":
    raise SystemExit(main())
