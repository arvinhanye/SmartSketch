# PR review fixes implementation plan

> For agentic workers: execute the two independent repair scopes with test-driven development, then use an independent final review and sequential integration. The user has explicitly authorized implementation and merging; no additional design approval is needed.

**Goal:** Fix R348-1/2 and R351-1–5 from the 2026-11-14 review, verify them, then merge #348 → #350 → #351.

**Architecture:** Preserve existing API contracts and versioned draft projections. Backend undo keeps node concurrency tokens monotonic while preserving independent undo groups; material deletion cleans only unapplied task-owned plans after existing deletion guards. Frontend history operations remain course-scoped and busy until authoritative state has synchronized.

**Tech Stack:** Python/FastAPI/SQLite/Neo4j; Vue 3/TypeScript/Vitest.

**Spec:** `docs/reviews/codex-pr-review-20261114.md`, `specs/generation-disambiguation.md`, `specs/course-knowledge-graph.md`.

## Global constraints

- No new public API, dependency upgrades, real model calls or development database migrations.
- Keep immutable audit snapshots and applied-plan history; do not cascade away effective graph contributions.
- Keep locked/edited-content conflicts, repeated undo idempotency and independent-group undo behavior.
- Preserve unrelated worktrees and changes. Each PR receives only its repair scope and necessary integration records.

## Review focus

- Restored absorbed nodes and repeated merge/undo cycles must never reuse an old edit revision.
- Undoing independent groups in either order must continue to work without ignoring real teacher edits.
- Cancelled/failed task cleanup must not delete a committed/applied plan, another course's plan, or undo audit.
- Course switch/unmount during PATCH, unlock or refresh must invalidate every late UI/history result.
- Partial writes, failed reads and unsaved input must not produce false success or stale usable redo.

## Task 1: Backend repairs for #348

Files: `services/fusion/undo.py`, `repositories/materials.py`, supporting fusion repository only if required; `tests/backend/test_fusion_undo.py`, material deletion tests and relevant integration tests; generation-disambiguation spec and backend handoff.

- [x] Add persistent tests for revision ABA, restored nodes and independent-group undo; run against the old code and confirm the intended failures.
- [x] Keep `inverse_patch(payload, group_id, current, *, undone)` compatible while assigning fresh revisions only to changed/restored nodes, preserving current revisions of unrelated nodes and all exact changed-content conflict checks. Verify independent undo order before adding any audit reconstruction mechanism.
- [x] Add real SQLite tests for prepared-plan cancellation/failure deletion, course scoping, cleanup_pending and contributed/applied-plan protection; confirm failure before fixing.
- [x] Clean only safe unapplied plans in the existing material deletion transaction after its guards, retaining migration 021 and audits.
- [x] Run targeted tests, backend full, basic and relevant isolated Neo4j integration; commit the repair with actual evidence.

## Task 2: Frontend repairs for #351

Files: `useEditHistory.ts`, `TeacherGraphView.vue`, `useTeacherGraph.ts`, `NodeEditor.vue` or a focused composable if needed, related tests and graph spec.

- [x] Move the five temporary reproductions into existing persistent test modules and confirm they fail on the fixed PR head.
- [x] Bind history runs to a generation so `clear()` and disposal invalidate late completions; bind node writes and refresh to the original course/request scope.
- [x] Prevent editing from being silently overwritten during undo; invalidate redo on every successful new write even if that write cannot be undone.
- [x] Synchronize authoritative node/graph state after possible partial writes, distinguish incomplete undo, and await refresh before finishing history work.
- [x] Cover slow reads, failed unlock/read, course switch/unmount and repeated actions; run targeted tests and frontend full. Deliver a patch against `a1f0864` without mixing #348 changes.

## Task 3: Review, CI and dependency integration

- [x] Independent reviewers assess both repair diffs, original seven failures and the five review-focus boundaries. Fix confirmed blockers with regression evidence.
- [x] Update #348 from current main, verify, push to its existing branch, wait for CI and merge with an expected-head SHA guard.
- [x] Update #350 to merged main, resolve task/index and test-helper parameter overlap while preserving both sides, rerun affected tests/basic and CI, retarget main and merge with an expected-head SHA guard.
- [ ] Apply the isolated #351 repair patch, integrate current main, verify frontend/full compatibility and CI, then merge with an expected-head SHA guard.
- [ ] Verify all three PR states and final main SHA; update tasks, review disposition and handoff with actual results and remaining acceptance limits.
