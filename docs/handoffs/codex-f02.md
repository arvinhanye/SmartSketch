# Codex handoff — F02 scoped Neo4j repository

- Task: F02 / issue #94; implementation ready for coordinator review.
- Branch: `codex/f02-neo4j`; final base: `130e6b637b63d684bc3d315f248bce1c66e4874e` (rebased from `a7a0be0` with edits preserved).
- Worktree: `/Users/arvinhan/Desktop/SmartSketch/.claude/worktrees/codex-f02-neo4j`.
- Scope: repository boundary, driver dependency and fake-driver unit tests only. The coordinator owns the task ledger update and publication.

## Changes and interface

- `src/backend/app/repositories/neo4j.py`: synchronous, injectable driver boundary; no import-time connections.
- `src/backend/pyproject.toml`: exact official `neo4j==5.28.2` dependency.
- `tests/backend/test_f02.py`: 64 offline cases.
- This handoff; no other source, schema, configuration, migrations or data changes.

```python
GraphScope(course_id: str, version_id: str,
           effective_task_ids: Sequence[str] | None = None)
Neo4jRepository(driver: GraphDriver)
Neo4jRepository.from_settings(settings: Settings) -> Neo4jRepository
repo.read(query: str, scope: GraphScope, *, reader: Literal["teacher", "student"],
          parameters: Mapping[str, Any] | None = None) -> list[dict[str, Any]]
repo.write(query: str, scope: GraphScope, *,
           parameters: Mapping[str, Any] | None = None) -> list[dict[str, Any]]
repo.close() -> None
```

`GraphDriver` uses the official `verify_connectivity()`, `execute_query(query, parameters_=..., routing_=..., database_=...)`, and `close()` signatures. Results are consumed eagerly and converted to dictionaries. Each call is one managed transaction with driver retry semantics; multi-call atomicity is not promised. Reads use `routing_="r"`, writes `"w"`; database is explicitly `"neo4j"` (F01 community setup; no new setting).

`from_settings` uses existing `NEO4J_URI`, `NEO4J_USER`, and `NEO4J_PASSWORD.get_secret_value()`, verifies connectivity, and closes the pool if verification fails. `close()` also closes an injected driver. No credentials or driver exception text are logged by this module. Connection/authentication/session failures raise `RepositoryConnectionError`, with stable code/message `NEO4J_CONNECTION_FAILED`; other execution failures raise `RepositoryError` with `NEO4J_QUERY_FAILED`. Exception chaining is suppressed. Invalid scopes raise `GraphScopeError` before execution.

## Spec-led decisions and caller contract

Sources: atomic F02 row; task-processing §8.4 / LEASE-23; teacher-review-publish V2/V3/V8 / PUB-27; F01 handoff.

1. Every business query must contain actual `$course_id` and `$version_id` parameter tokens. Quoted strings, backtick identifiers, comments and suffix lookalikes do not satisfy this check. Values are passed separately and never interpolated by the repository. Repository scope overrides caller extras.
2. Every draft query requires both a non-`None` V in `GraphScope` and an executable `$effective_task_ids` token. Empty V is valid. Scope copies V into an immutable tuple and sends a new list to the driver, so later caller mutation does not alter the snapshot. Extra parameters never supply/override V.
3. Conservative interpretation of LEASE-23's “draft query”: draft writes require V too, because writes can read via `MATCH`/`MERGE` or cycle checks. This avoids an alternate draft-read entrance; even a pure draft write carries V.
4. The service reads V **once from SQLite** for the same course (`awaiting_review` / `completed`, and watermarked for publication), authenticates teacher membership, and passes it explicitly. The repository does not query SQLite or claim to prove V's provenance. Existing task schema/lifecycle work and published-version resolution remain their owning tasks.
5. Reads require explicit teacher/student intent; student `draft` reads are rejected even with V. Published reads do not need V. `write` is an internal teacher/worker API, not a student route.
6. Cypher must be trusted repository code, not user-supplied text. Token checks detect omissions, **not semantic authorization**: callers still implement course/version predicates, per-contribution visibility, relationship endpoint visibility, and evidence visibility. F04/F07/F13/G04 own those domain queries and integration acceptance (LEASE-19/20, PUB-35). No speculative domain schema was added here.

## Dependency compatibility

5.28.2 is an exact official 5.x driver pin, chosen for the established 5.26 LTS server generation rather than introducing a 6.x migration. Its [versioned official source/README](https://github.com/neo4j/neo4j-python-driver/tree/5.28.2) explicitly supports Python 3.11 and 3.13; the installed driver's `execute_query` API and Bolt 5.x handlers were inspected. The official [Python upgrade guide](https://neo4j.com/docs/python-manual/current/upgrade/) identifies 5.28 as the prior series and documents its forward compatibility with later server generations. This is a compatibility-informed pin, **not a live-server verification claim**. No database was contacted in F02.

## Verification

- RED before implementation: focused pytest ran with existing Anaconda pytest 8.3.4; **64 setup assertion errors**, each `F02 scoped repository is missing`. This is missing-module feature evidence, not 64 separate behavior failures. The initial default-Python `No module named pytest` attempt was an environment failure, not RED evidence.
- GREEN: focused suite **64 passed in 0.39s** with the pinned real driver imported and an injected fake for all I/O.
- Mutation checks on scratch copies only: remove required-token guard → **16 failed**; remove draft-V guard → **2 failed**; remove student-draft guard → **1 failed**; remove authoritative binding → **1 failed**; expose original connection exceptions → **4 failed**. All five commands exited 1 as expected, without editing production files.
- `./scripts/verify.sh`: **exit 0**, hook regression and contract gate passed, including **201** contract pytest cases and **24** gate negative checks.
- Updated-base focused command: `python3 -m pytest tests/backend/test_f02.py -q` → **64 passed in 0.81s**, exit 0.
- Updated-base backend command: `python3 -m pytest tests/backend -q` → **1114 passed, 1 warning in 29.78s**, exit 0. Warning is Starlette/httpx TestClient deprecation, unrelated to F02.
- Updated-base `./scripts/verify.sh` → **exit 0**: hook regression, **25** contract negative checks, B14 **3** tests and other contract pytest suites **201** tests all passed.
- Updated-base full command: `python3 -m pytest -q` with `SMARTSKETCH_SKIP_DOCKER=1` → **1395 passed, 3 skipped, 1 failed, 1 warning in 227.46s**, exit 1. All three skips are the real-Docker F01 tests, deliberately excluded from this task.
- Sole full-suite failure: `tests/tooling/test_b07.py::test_dispatcher_reports_aggregate_status[0-PASS]`. Its fake workspace does not contain `tests/contracts/test_b14.py`, newly required by the B14 gate; therefore expected PASS returns exit 1. Reproduced on a **clean archive of base `130e6b637`**, without F02 files: `python3 -m pytest --rootdir=. 'tests/tooling/test_b07.py::test_dispatcher_reports_aggregate_status[0-PASS]' -q` → **1 failed in 4.26s** with the identical missing-B14 message. No out-of-scope tooling change was made.
- `git diff --check` passed; final staged check passed before commit. Code/tests stayed byte-identical across the rebase; self-review found no F02 defect.

Final command environment (all packages/runtime outside the repository):

```sh
export PATH=/Users/arvinhan/Documents/Codex/2026-09-25/jia/work/f02-venv/bin:/opt/anaconda3/bin:$PATH
export PYTHONPATH=/Users/arvinhan/Desktop/SmartSketch/.claude/worktrees/codex-f02-neo4j/src/backend
export PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
export PYTEST_ADDOPTS='-p no:cacheprovider' SMARTSKETCH_SKIP_DOCKER=1
```

An earlier backend invocation in the restricted sandbox failed C13's two loopback-port probes (`PermissionError`); an initial relative source path also failed E02's changed-directory subprocess import. The absolute scratch runtime path fixed E02, and approved loopback test execution passed all backend cases on the updated base. No test was removed or weakened.

Environment: default Python 3.11 lacked test dependencies. Existing Anaconda Python 3.13 had pytest/Pydantic and contract tooling but lacked FastAPI/PDFMiner. Its optional NumPy/Pandas/PyArrow native imports stalled on Neo4j import. A task-scratch venv reuses installed dependencies via links while excluding those unused optional packages; this imports the real pinned driver successfully. Additional declared pins were downloaded into scratch only. No repository bootstrap files or global package changes were made.

## Risks / next action / rollback

- Coordinator: review this API boundary and evidence, track the pre-existing B07 fake-workspace/B14 regression, update `docs/tasks.md`, then publish. Domain owners should call this boundary with resolved course/version/V and add real isolated-server query tests as their queries land.
- Live Neo4j authentication, routing, failover, Cypher syntax and query semantics remain unverified here by design; tests perform no network I/O or graph writes. Arbitrary-Cypher authorization and multi-query transaction APIs are out of scope.
- Returning eager records may be inappropriate for unbounded queries; callers should parameterize pagination/limits.
- Rollback: revert the F02 commit, reinstall backend dependencies from the reverted `pyproject.toml`, and restart consumers. There are no migrations or database changes to reverse. Retain existing Neo4j data untouched.
