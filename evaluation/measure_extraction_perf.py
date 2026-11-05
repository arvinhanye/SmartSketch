#!/usr/bin/env python3
"""EXTRACT-PERF-01: isolated, zero-paid-call upload → awaiting_review measurement.

Run from any directory with the project's existing Python/test dependencies::

    .venv/bin/python evaluation/measure_extraction_perf.py --delay-seconds 8 --concurrency 4 \
        --repeats 2 --out-dir /private/tmp/smartsketch-extraction-perf

Uses the real FastAPI routes through TestClient, the real worker loop, the HTTP
handler in scripts/fake_provider.py, and a fresh Docker Neo4j 5.26 container.
Does not read .env, inherit application settings, accept external endpoints, pull
images, or install dependencies. Docker must already have neo4j:5.26-community.
SQLite, files and JSON go in a new run directory; the container is removed on exit.

Timers observe existing worker functions and call-store callbacks without changing
their result or scheduler. Unit queue waits start after parsing / dependency
checkpoints. Model call bounds surround transport, excluding SQLite write-back;
model_calls also retains its native timestamps and latency. Stage handoffs derived
from existing integer-ms log durations have about 1 ms rounding uncertainty.
The worker is deliberately idle immediately before upload (reproducible ~2 s
initial polling wait). There is no browser, API TCP, publish/vectorization,
maintenance sweep, paid-provider quality, throughput or rate-limit measurement.
Neo4j startup/migration is outside upload timing. --repeats 2 measures a new course
and SQLite database on the same Neo4j instance, retaining the first run's query
cache; these are reported as cold and warm, respectively. Query timers cover the
real PersistTransport.run(), including await result.data(), not just submission.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
import logging
import math
import os
import secrets
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FILE = ROOT / "datasets/demo/ch3-stack-queue.md"
TERMINAL = {"awaiting_review", "completed", "failed", "cancelled"}
SOURCE_FILES = ("src/backend/app/workers/extract_task.py", "src/backend/app/workers/persist_graph.py",
                "src/backend/app/workers/runner.py", "scripts/fake_provider.py")
_IMPORTED_BASELINE: dict | None = None
_PROVIDER_MODULE = None


def _provider_module():
    global _PROVIDER_MODULE
    if _PROVIDER_MODULE is None:
        spec = importlib.util.spec_from_file_location("extraction_perf_fake_provider", ROOT / "scripts/fake_provider.py")
        _PROVIDER_MODULE = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_PROVIDER_MODULE)
    return _PROVIDER_MODULE


def capture_runtime() -> dict:
    """Import pipeline once and retain its source identity across warm repetitions.

    Call before any concurrent source edit; Python's module cache keeps this run's
    implementation stable. Disk changes are separately flagged in each report.
    """
    global _IMPORTED_BASELINE
    if _IMPORTED_BASELINE is None:
        sys.path.insert(0, str(ROOT / "src/backend"))
        from app.workers import extract_task, persist_graph, runner  # noqa: F401
        _provider_module()
        _IMPORTED_BASELINE = {
            "source_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "source_sha256": {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in SOURCE_FILES},
            "source_captured_at": datetime.now(timezone.utc).isoformat(),
        }
    return dict(_IMPORTED_BASELINE)


def interval_union(intervals: list[tuple[float, float]]) -> float:
    """Wall time covered by at least one call, not sum of concurrent latencies."""
    total, end = 0.0, -math.inf
    for start, stop in sorted(intervals):
        total += max(0.0, stop - max(start, end))
        end = max(end, stop)
    return total


def purpose_timings(calls: list[dict]) -> dict:
    groups = {}
    for row in calls:
        if "ended_seconds" in row:
            groups.setdefault(row["purpose"], []).append((row["started_seconds"], row["ended_seconds"]))
    return {purpose: {"calls": len(intervals), "first_start_seconds": min(start for start, _ in intervals),
                      "last_end_seconds": max(end for _, end in intervals),
                      "span_seconds": max(end for _, end in intervals) - min(start for start, _ in intervals),
                      "active_wall_seconds": interval_union(intervals),
                      "summed_seconds": sum(end - start for start, end in intervals)}
            for purpose, intervals in sorted(groups.items())}


def query_labels() -> dict[str, str]:
    from app.repositories import graph_nodes, graph_relations
    labels = {}
    for module in (graph_nodes, graph_relations):
        for name, value in vars(module).items():
            if not name.startswith("_") or name.startswith("__"):
                continue
            templates = value.items() if isinstance(value, dict) else (("", value),)
            for suffix, query in templates:
                if isinstance(query, str) and "$course_id" in query:
                    fingerprint = hashlib.sha256(" ".join(query.split()).encode()).hexdigest()
                    labels[fingerprint] = f"{module.__name__}.{name}" + (f"[{suffix}]" if suffix else "")
    return labels


def normalize_graph(nodes: list[dict], relations: list[dict], evidence: list[dict], chunks: dict) -> dict:
    """Comparable graph content and source locations, excluding per-run identifiers."""
    canonical = lambda row: json.dumps(row, ensure_ascii=False, sort_keys=True)
    normalized_nodes = []
    for row in nodes:
        sources = [{**chunks[source["chunk_id"]], "evidence_start": source["evidence_start"],
                    "evidence_end": source["evidence_end"]}
                   for source in evidence if source["kp_id"] == row["kp_id"]]
        normalized_nodes.append({key: row[key] for key in ("name", "type", "definition", "confidence", "status")}
                                | {"aliases": sorted(row.get("aliases") or []), "sources": sorted(sources, key=canonical)})
    normalized_relations = []
    for row in relations:
        sources = [chunks[json.loads(pair)[1]] for pair in row.get("source_pairs") or []]
        normalized_relations.append({key: row[key] for key in (
            "from_name", "from_type", "to_name", "to_type", "type", "confidence", "status", "source")}
                                    | {"sources": sorted(sources, key=canonical)})
    graph = {"nodes": sorted(normalized_nodes, key=canonical),
             "relations": sorted(normalized_relations, key=canonical)}
    return {"sha256": hashlib.sha256(canonical(graph).encode()).hexdigest(), **graph}


def parse_worker_log(message: str, at_seconds: float) -> dict | None:
    if message.startswith("persist steps "):
        result = {"kind": "persist_steps", "at_seconds": at_seconds}
        fields = message[len("persist steps "):]
    elif message.startswith("task stage done "):
        result = {"kind": "stage", "ended_seconds": at_seconds}
        fields = message[len("task stage done "):]
    else:
        return None
    for field in fields.split():
        key, value = field.split("=", 1)
        result[key] = int(value) if key.endswith("_ms") or key == "neo4j_attempts" else value
    if result["kind"] == "stage":
        result["started_seconds"] = at_seconds - result["duration_ms"] / 1000
    return result


def add_queue_times(units: list[dict], checkpoints: list[dict], *, chunks_ready: float) -> None:
    completed = {row["unit_id"]: row["at_seconds"] for row in checkpoints if row["kind"] == "chunk"}
    for unit in units:
        ready = chunks_ready
        if unit["kind"] == "section":
            dependencies = [completed.get(chunk) for chunk in unit["chunk_ids"]]
            ready = max(dependencies) if dependencies and all(t is not None for t in dependencies) else None
        unit["ready_seconds"] = ready
        unit["queue_wait_seconds"] = None if ready is None else max(0.0, unit["started_seconds"] - ready)


def isolated_environment(run_dir: Path, neo4j_uri: str, password: str, *, concurrency: int,
                         delay_seconds: float) -> dict[str, str]:
    """Explicit allowlist: caller must install this using patch.dict(clear=True)."""
    return {
        "APP_ENV": "test", "SQLITE_URL": f"sqlite:///{run_dir / 'state.sqlite3'}",
        "STORAGE_DIR": str(run_dir / "files"), "NEO4J_URI": neo4j_uri,
        "NEO4J_USER": "neo4j", "NEO4J_PASSWORD": password,
        "AUTH_JWT_SECRET": secrets.token_urlsafe(48),
        "MODEL_CREDENTIAL_KEY": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
        "MODEL_ENDPOINT_ALLOW_PRIVATE": "1", "LLM_MODE": "personal", "EMBEDDING_MODE": "demo",
        "LLM_MAX_CONCURRENCY": str(concurrency), "PUBLISH_SWEEP_INTERVAL_SECONDS": "0",
        "FAKE_PROVIDER_SLOW_SECONDS": str(delay_seconds),
    }


class Trace(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.origin = time.monotonic()
        self.units: list[dict] = []
        self.checkpoints: list[dict] = []
        self.calls: dict[str, dict] = {}
        self.logs: list[dict] = []
        self.neo4j_operations: list[dict] = []
        self.raw_logs: list[str] = []
        self.local = threading.local()
        self.data_lock = threading.Lock()

    def now(self) -> float:
        return time.monotonic() - self.origin

    def emit(self, record: logging.LogRecord) -> None:
        message = record.getMessage()
        parsed = parse_worker_log(message, self.now())
        if parsed is not None:
            with self.data_lock:
                self.logs.append(parsed)
                self.raw_logs.append(message)

    @contextmanager
    def observe_units(self):
        from app.workers import extract_task
        from app.repositories.persist_transport import PersistTransport
        labels = query_labels()

        def wrap_unit(original, kind):
            @wraps(original)
            def observed(*args, **kwargs):
                value = args[3] if len(args) > 3 else kwargs["chunk" if kind == "chunk" else "section"]
                unit_id = value.chunk_id if kind == "chunk" else value.section_id
                row = {"kind": kind, "unit_id": unit_id, "started_seconds": self.now()}
                if kind == "section":
                    row.update(section_path=value.path, chunk_ids=[chunk.chunk_id for chunk in value.chunks])
                else:
                    row.update(section_path=" > ".join(value.section_titles), text_chars=len(value.text))
                self.local.unit = {"kind": kind, "unit_id": unit_id}
                try:
                    result = original(*args, **kwargs)
                    row["status"] = result.status
                    return result
                finally:
                    row["ended_seconds"] = self.now()
                    with self.data_lock:
                        self.units.append(row)
                    self.local.unit = None
            return observed

        original_write = extract_task._write_unit

        @wraps(original_write)
        def write(*args, **kwargs):
            result = original_write(*args, **kwargs)
            if result:
                with self.data_lock:
                    self.checkpoints.append({"kind": args[2], "unit_id": args[3], "at_seconds": self.now()})
            return result

        def wrap_transport(original, operation):
            @wraps(original)
            def observed(*args, **kwargs):
                row = {"operation": operation}
                if operation == "run":
                    query = " ".join((args[1] if len(args) > 1 else kwargs["query"]).split())
                    fingerprint = hashlib.sha256(query.encode()).hexdigest()
                    row.update(query_sha256=fingerprint, query_template=query, query_label=labels.get(fingerprint))
                row["started_seconds"] = self.now()
                try:
                    result = original(*args, **kwargs)
                    row["status"] = "ok"
                    if operation == "run":
                        row["result_rows"] = len(result)
                    return result
                except Exception as exc:
                    row.update(status="error", error_type=type(exc).__name__)
                    raise
                finally:
                    row["ended_seconds"] = self.now()
                    row["duration_seconds"] = row["ended_seconds"] - row["started_seconds"]
                    with self.data_lock:
                        self.neo4j_operations.append(row)
            return observed

        with ExitStack() as stack:
            for name, kind in (("_extract_chunk", "chunk"), ("_extract_section", "section")):
                stack.enter_context(patch.object(extract_task, name, wrap_unit(getattr(extract_task, name), kind)))
            stack.enter_context(patch.object(extract_task, "_write_unit", write))
            for name in ("open", "run", "commit", "close"):
                stack.enter_context(patch.object(PersistTransport, name,
                                                 wrap_transport(getattr(PersistTransport, name), name)))
            yield

    def call_store(self, sqlite_url: str):
        from app.repositories.model_calls import SqliteCallStore
        trace = self

        class ObservedStore(SqliteCallStore):
            def prewrite(self, record, **kwargs):
                begin = trace.now()
                result = super().prewrite(record, **kwargs)
                with trace.data_lock:
                    trace.calls[record.call_id] = {
                        "call_id": record.call_id, "purpose": record.purpose,
                        "unit": getattr(trace.local, "unit", None), "is_repair": record.is_repair,
                        "prewrite_begin_seconds": begin, "started_seconds": trace.now(),
                    }
                return result

            def finish(self, outcome):
                ended = trace.now()
                result = super().finish(outcome)
                with trace.data_lock:
                    trace.calls[outcome.call_id].update(ended_seconds=ended, writeback_seconds=trace.now(),
                                                       status=outcome.status)
                return result

        return ObservedStore(sqlite_url)


def _docker_executable() -> str:
    executable = shutil.which("docker")
    if executable is None:
        candidate = Path.home() / ".docker/bin/docker"
        executable = str(candidate) if candidate.is_file() else None
    if executable is None:
        raise RuntimeError("Docker is required; no existing databases are used")
    return executable


@contextmanager
def isolated_neo4j(run_dir: Path):
    """Only a newly owned --rm container, random loopback port, and random auth."""
    from neo4j import GraphDatabase

    docker = _docker_executable()
    image = "neo4j:5.26-community"
    subprocess.run([docker, "image", "inspect", image], cwd=ROOT, check=True, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, timeout=15)
    name = "smartsketch-extraction-perf-" + secrets.token_hex(6)
    password = secrets.token_urlsafe(24)
    command = [docker, "run", "--detach", "--rm", "--pull=never", "--name", name,
               "--publish", "127.0.0.1::7687", "--env", f"NEO4J_AUTH=neo4j/{password}",
               "--env", "NEO4J_server_memory_heap_initial__size=256m",
               "--env", "NEO4J_server_memory_heap_max__size=512m",
               "--env", "NEO4J_dbms_usage__report_enabled=false", image]
    driver = None
    try:
        subprocess.run(command, cwd=ROOT, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=60)
        port = subprocess.check_output([docker, "port", name, "7687/tcp"], cwd=ROOT, text=True,
                                       timeout=15).strip().rsplit(":", 1)[1]
        uri = f"bolt://127.0.0.1:{int(port)}"
        driver = GraphDatabase.driver(uri, auth=("neo4j", password), connection_timeout=1,
                                       max_transaction_retry_time=0)
        deadline = time.monotonic() + 180
        while True:
            try:
                driver.verify_connectivity()
                break
            except Exception:
                if time.monotonic() >= deadline:
                    raise RuntimeError("isolated Neo4j did not become ready in 180 seconds") from None
                time.sleep(0.5)
        yield uri, password, driver, name
    finally:
        if driver is not None:
            driver.close()
        # Container only: never discover or stop another running instance.
        subprocess.run([docker, "rm", "--force", name], cwd=ROOT, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=30)


@contextmanager
def fake_provider():
    """The checked-in HTTP handler, not a replacement model mock."""
    module = _provider_module()
    server = module.ThreadingHTTPServer(("127.0.0.1", 0), module.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)


def _json_response(response, expected: int):
    if response.status_code != expected:
        # Do not dump responses containing tokens, model credentials or passwords.
        raise RuntimeError(f"API setup/upload failed: HTTP {response.status_code}, expected {expected}")
    return response.json()


def run_measurement(args, run_dir: Path, trace: Trace, neo4j) -> dict:
    source_hashes = args.imported_baseline["source_sha256"]
    from fastapi.testclient import TestClient
    from app.config import load_settings
    from app.repositories.graph_migrations import apply_migrations
    from app.repositories.neo4j import Neo4jRepository
    from app.repositories.sqlite import migrate
    from app.services.auth import create_account
    from app.workers import extract_task, persist_graph, runner
    from app.workers.toolkits import TaskToolkits

    uri, password, driver, container = neo4j
    env = isolated_environment(run_dir, uri, password, concurrency=args.concurrency, delay_seconds=args.delay_seconds)
    with patch.dict(os.environ, env, clear=True), fake_provider() as provider_url:
        from app.main import create_app
        settings = load_settings()
        migrate(settings.SQLITE_URL)
        apply_migrations(driver)
        driver.execute_query("CALL db.awaitIndexes(120)", database_="neo4j")
        teacher_password = secrets.token_urlsafe(24)
        create_account(settings.SQLITE_URL, "perf_teacher", teacher_password, "teacher")
        repo = Neo4jRepository.from_settings(settings)
        toolkit = TaskToolkits(settings, store=trace.call_store(settings.SQLITE_URL)).for_lease
        stop, idle = threading.Event(), threading.Event()
        worker_errors: list[str] = []

        def step():
            result = persist_graph.run_pipeline_once(settings, toolkit=toolkit, repo=repo)
            if result.lease is None:
                idle.set()
            return result

        def worker_main():
            try:
                runner.run_loop(settings, stop, step=step)
            except Exception as exc:
                worker_errors.append(type(exc).__name__)

        logger = logging.getLogger("app.workers.persist_graph")
        previous_level = logger.level
        logger.setLevel(logging.INFO)
        logger.addHandler(trace)
        worker = threading.Thread(target=worker_main, daemon=True)
        try:
            with TestClient(create_app()) as client, trace.observe_units():
                token = _json_response(client.post("/api/v1/auth/login", json={
                    "username": "perf_teacher", "password": teacher_password}), 200)["access_token"]
                client.headers["Authorization"] = f"Bearer {token}"
                _json_response(client.put("/api/v1/me/model-config", json={
                    "base_url": provider_url, "model": "fake-model", "api_key": "sk-fake-slow",
                    "disable_thinking": False}), 200)
                course = _json_response(client.post("/api/v1/courses", json={"name": "EXTRACT-PERF-01"}), 201)
                worker.start()
                if not idle.wait(5):
                    raise RuntimeError("worker did not enter its initial idle poll")
                trace.origin = time.monotonic()
                started_at = datetime.now(timezone.utc).isoformat()
                accepted = _json_response(client.post(f"/api/v1/courses/{course['id']}/documents",
                    files={"file": (args.file.name, args.file.read_bytes(), "text/markdown")}), 202)
                upload_seconds = trace.now()
                task_id = accepted["task_id"]
                transitions = []
                stage = None
                while trace.now() <= args.max_seconds:
                    snapshot = _json_response(client.get(f"/api/v1/tasks/{task_id}"), 200)
                    if snapshot["stage"] != stage:
                        stage = snapshot["stage"]
                        transitions.append({"stage": stage, "observed_seconds": trace.now()})
                    if stage in TERMINAL or worker_errors:
                        break
                    time.sleep(args.poll_seconds)
                elapsed = trace.now()
                if stage not in TERMINAL:
                    client.post(f"/api/v1/tasks/{task_id}/cancel")
                stop.set()
                worker.join(settings.LLM_REQUEST_TIMEOUT_SECONDS + 10)
                if worker.is_alive():
                    raise RuntimeError("worker did not exit after cancellation")
        finally:
            stop.set()
            if worker.is_alive():
                worker.join(settings.LLM_REQUEST_TIMEOUT_SECONDS + 10)
            logger.removeHandler(trace)
            logger.setLevel(previous_level)
            repo.close()

        stages = [row for row in trace.logs if row["kind"] == "stage"]
        persist = [row for row in trace.logs if row["kind"] == "persist_steps"]
        parsed = next((row for row in stages if row["stage"] == "parsing"), None)
        add_queue_times(trace.units, trace.checkpoints, chunks_ready=parsed["ended_seconds"] if parsed else 0)
        with sqlite3.connect(run_dir / "state.sqlite3") as database:
            database.row_factory = sqlite3.Row
            ledger = [dict(row) for row in database.execute(
                "SELECT call_id, purpose, chunk_id, task_attempt, chunk_attempt, call_seq, is_repair, "
                "status, created_at, finished_at, latency_ms, usage_input, usage_output, error_class "
                "FROM model_calls WHERE task_id = ? ORDER BY created_at, call_id", (task_id,))]
        for row in ledger:
            row["timing"] = trace.calls.get(row["call_id"])
        def query(cypher):
            return [dict(row) for row in driver.execute_query(cypher, course=course["id"],
                                                              database_="neo4j").records]

        nodes = query("MATCH (n:KnowledgePoint {course_id: $course, version_id: 'draft'}) "
                      "RETURN n.kp_id AS kp_id, n.name AS name, n.type AS type, n.definition AS definition, "
                      "n.confidence AS confidence, n.status AS status, n.aliases AS aliases")
        relations = query("MATCH (a:KnowledgePoint)-[r {course_id: $course, version_id: 'draft'}]->(b:KnowledgePoint) "
                          "WHERE type(r) IN ['CONTAINS','PREREQUISITE','RELATED_TO','EXAMPLE_OF'] "
                          "RETURN a.name AS from_name, a.type AS from_type, b.name AS to_name, b.type AS to_type, "
                          "type(r) AS type, r.confidence AS confidence, r.status AS status, r.source AS source, "
                          "r.source_pairs AS source_pairs")
        evidence = query("MATCH (n:KnowledgePoint {course_id: $course, version_id: 'draft'})"
                         "-[e:EVIDENCED_BY]->(c:Chunk) RETURN n.kp_id AS kp_id, c.chunk_id AS chunk_id, "
                         "e.evidence_start AS evidence_start, e.evidence_end AS evidence_end")
        chunks = {chunk.chunk_id: {"ordinal": chunk.ordinal, "section_titles": list(chunk.section_titles),
                                   "text_sha256": hashlib.sha256(chunk.text.encode()).hexdigest()}
                  for chunk in extract_task._task_chunks(settings.SQLITE_URL, course["id"], task_id)}
        normalized = normalize_graph(nodes, relations, evidence, chunks)
        calls = list(trace.calls.values())
        intervals = [(row["started_seconds"], row["ended_seconds"]) for row in calls if "ended_seconds" in row]
        entities = [row for row in trace.units if row["kind"] == "chunk"]
        sections = [row for row in trace.units if row["kind"] == "section"]
        last_chunk_end = max((row["ended_seconds"] for row in entities), default=None)
        first_section_start = min((row["started_seconds"] for row in sections), default=None)
        handoffs = [{"from": left["stage"], "to": right["stage"],
                     "gap_seconds": right["started_seconds"] - left["ended_seconds"]}
                    for left, right in zip(stages, stages[1:])]
        active_seconds = interval_union(intervals)
        timings = purpose_timings(calls)
        entity_intervals = [(row["started_seconds"], row["ended_seconds"]) for row in calls
                            if row["purpose"] == "extract_entities" and "ended_seconds" in row]
        relation_intervals = [(row["started_seconds"], row["ended_seconds"]) for row in calls
                              if row["purpose"] == "extract_relations" and "ended_seconds" in row]
        generation_union = interval_union(entity_intervals + relation_intervals)
        return {
            "schema_version": 1, "started_at": started_at, "file": str(args.file),
            "file_bytes": args.file.stat().st_size, "delay_seconds": args.delay_seconds,
            "concurrency": args.concurrency, "stage": stage, "error": snapshot.get("error"),
            "worker_errors": worker_errors, "task_id": task_id, "course_id": course["id"],
            "run_dir": str(run_dir), "neo4j_container": container, "neo4j_uri": uri,
            "provider_url": provider_url, "paid_calls": 0,
            "boundary": "TestClient upload request start to terminal task snapshot; includes initial worker idle poll",
            "poll_seconds": args.poll_seconds, "stage_rounding_uncertainty_seconds": 0.001,
            "cold_graph_write": args.repeat_index == 0, "repeat_index": args.repeat_index,
            "neo4j_temperature": "cold" if args.repeat_index == 0 else "warm",
            "upload_response_seconds": upload_seconds,
            "elapsed_seconds": elapsed, "initial_queue_seconds": stages[0]["started_seconds"] if stages else None,
            "model_active_wall_seconds": active_seconds,
            "outside_model_calls_seconds": elapsed - active_seconds,
            "model_call_count": len(ledger), "chunk_count": len(entities), "section_count": len(sections),
            "graph_counts": {"knowledge_points": len(nodes), "relations": len(relations)},
            "normalized_graph": normalized, "purpose_timings": timings,
            "entity_relation_union_seconds": generation_union,
            "entity_relation_overlap_seconds": max(0.0, interval_union(entity_intervals)
                                                     + interval_union(relation_intervals) - generation_union),
            **args.imported_baseline, "source_identity": "imported baseline (same cached modules for all repetitions)",
            "source_changed_during_measurement": any(hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != digest
                                                      for path, digest in source_hashes.items()),
            "effective_settings": settings.model_dump(include={
                "LLM_MODE", "EMBEDDING_MODE", "LLM_MAX_CONCURRENCY", "LLM_REQUEST_TIMEOUT_SECONDS",
                "LLM_MAX_RETRIES", "LLM_TASK_TOKEN_BUDGET", "LLM_DAILY_TOKEN_BUDGET",
                "TASK_MAX_FAILED_CHUNK_RATIO", "TASK_LEASE_SECONDS", "TASK_CHUNK_MAX_ATTEMPTS",
                "TASK_MAX_ATTEMPTS", "TASK_PERSIST_COMMIT_TIMEOUT_SECONDS", "TASK_PERSIST_CLEANUP_TIMEOUT_SECONDS"}),
            "host_load_average": os.getloadavg(), "concurrent_work_note": args.concurrent_work_note,
            "chunk_to_section_gap_seconds": None if last_chunk_end is None or first_section_start is None
                else first_section_start - last_chunk_end,
            "stage_handoffs": handoffs, "stages": stages, "persist_steps": persist,
            "neo4j_operations": trace.neo4j_operations,
            "neo4j_timing_boundary": "PersistTransport open/run/commit/close; run includes async result.data() consumption",
            "persist_overlap_note": "t6_ms is within neo4j_ms; do not sum them. total_ms is wall time.",
            "units": sorted(trace.units, key=lambda row: row["started_seconds"]),
            "checkpoints": trace.checkpoints, "model_calls": ledger, "observed_stages": transitions,
            "limitations": ["No browser rendering or API TCP overhead", "No publication/vectorization",
                            "Fake output does not measure paid-model quality, token latency or rate limits",
                            "Initial queue deliberately begins just after the worker's empty poll",
                            "Stage handoff may be slightly negative due to millisecond log rounding",
                            "No maintenance sweep; migrations and startup excluded; repeats share Neo4j query cache"],
        }


def _delay(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or not 0 <= number <= 120:
        raise argparse.ArgumentTypeError("delay must be finite and between 0 and 120 seconds")
    return number


def _positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--file", type=Path, default=DEFAULT_FILE)
    parser.add_argument("--out-dir", type=Path, default=Path("/private/tmp/smartsketch-extraction-perf"))
    parser.add_argument("--delay-seconds", type=_delay, default=8.0)
    parser.add_argument("--concurrency", type=_positive_int, default=4)
    parser.add_argument("--repeats", type=_positive_int, default=1)
    parser.add_argument("--max-seconds", type=_positive_int, default=600)
    parser.add_argument("--poll-seconds", type=float, default=0.1)
    parser.add_argument("--concurrent-work-note", default="Other local workloads are uncontrolled; record them when known")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    args.file = args.file.resolve(strict=True)
    if not math.isfinite(args.poll_seconds) or args.poll_seconds <= 0:
        raise SystemExit("poll-seconds must be finite and positive")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    group = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(4)
    first_dir = args.out_dir.resolve() / group
    first_dir.mkdir(mode=0o700)
    args.imported_baseline = capture_runtime()
    run_dir, trace = first_dir, Trace()
    status = 0
    try:
        with isolated_neo4j(first_dir) as neo4j:
            for args.repeat_index in range(args.repeats):
                if args.repeat_index:
                    run_dir = args.out_dir.resolve() / (group + f"-repeat{args.repeat_index + 1:02d}")
                    run_dir.mkdir(mode=0o700)
                trace = Trace()
                report = run_measurement(args, run_dir, trace, neo4j)
                output = run_dir / "measurement.json"
                output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                (run_dir / "worker-timing.log").write_text("\n".join(trace.raw_logs) + "\n", encoding="utf-8")
                print(json.dumps({"report": str(output), "stage": report["stage"],
                    "neo4j_temperature": report["neo4j_temperature"], "elapsed_seconds": report["elapsed_seconds"],
                    "calls": report["model_call_count"], "chunks": report["chunk_count"],
                    "sections": report["section_count"]}, ensure_ascii=False), flush=True)
                if report["stage"] != "awaiting_review" or report["worker_errors"]:
                    status = 1
                    break
    except Exception as exc:
        # Keep diagnostics useful without serializing supplied config or exception messages.
        failure = {"stage": "harness_error", "error_type": type(exc).__name__, "run_dir": str(run_dir)}
        (run_dir / "failure.json").write_text(json.dumps(failure, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(failure), file=sys.stderr)
        raise
    finally:
        (run_dir / "worker-timing.log").write_text("\n".join(trace.raw_logs) + "\n", encoding="utf-8")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
