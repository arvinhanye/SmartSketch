# Teacher course embedding settings — 2026-10-08

Baseline: 80faac7, branch `codex/ui-polish-model-discovery`. User confirmed teacher-owned course scope; student settings remain unchanged. No push or deployment in this task.

## Delivery

- Teacher-only independent API form: provider, endpoint, encrypted key, model discovery/manual input, common/custom dimension, test/save.
- Four embedding-config endpoints, migration019 and generated contracts. Student authorization returns403; browser mounts no embedding component for students.
- Course publication, rollback and student retrieval resolve creator-teacher overrides, otherwise retain environment fallback. Student generation credentials remain independent.
- Additive course-scoped rebuilding verifies draft/published knowledge points and chunks before atomic activation; old properties remain. Global reembed refuses mixed teacher overrides.
- Review fixes: embedding form cannot write generation runtime state; owner locks, active attempts and commit-space checks prevent races with publication/rollback. Regression tests reproduced the original failures before fixes; reviewer rechecked both fixes with no remaining blockers.

## Verification

- Backend related suite: 84 passed; additional commit-space test: embedding suite19 passed (85 distinct related cases in total).
- Frontend four suites:30 passed; `npm run type-check` and `npm run build` passed (existing large-chunk advisory).
- `scripts/verify.sh basic`: PASS,36 paths/133 schemas/423 references, deterministic generation and contract regression gates. Run on Windows with PYTHONUTF8/PYTHONIOENCODING and user Python scripts/node_modules bin in PATH; initial attempts lacked these environment prerequisites and failed honestly, then rerun passed.
- Browser fixture checks: teacher/student1440px and390px, visibility, actions, no horizontal overflow. Live demo_teacher/demo_student2 settings pages passed without JavaScript errors; teacher default1024 visible, student no new component.
- Read-only live graph checks returned200 for teacher/student,63 knowledge points and70 relations each. No newly supplied provider key was persisted or used against real embedding providers by these tests; provider transport tests use controlled responses. Actual provider support is checked when the user tests/saves the form.

## Local migration and recovery

Migration019 applied after services stopped, with verified backup `migration-new-backend/storage/ui-check/backups/20261008T131738004975Z-before-019.sqlite` under the outer workspace. Runtime secrets and DBs remain ignored and unstaged. Existing teacher rows still absent, so course graph data and active default embedding settings remain unchanged.

To undo schema/activation, stop API/worker, restore the corresponding pre-change SQLite backup and previous code, then restart with matching defaults. Do not delete schema_migrations entries. New Neo4j vector properties are additive and may remain unused after recovery; no old property/index cleanup is automatic. Already expired publication attempts must be reclaimed by existing worker/publish cleanup before configuration switching; never simply ignore their state because graph remnants may exist.

Local endpoints: frontend `http://127.0.0.1:5322/settings/model`, API `http://127.0.0.1:8321`. Process registry and logs are ignored `.local-run` files. User manual visual acceptance and a chosen provider's real connection/activation remain to be performed through the page.
