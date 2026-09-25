# B14 handoff — contract export and drift checking

## Delivered
- Added `tests/contracts/test_b14.py` covering deterministic repeated generation, tamper detection without `--check` mutation, missing-stage detection, and canonical restoration by regeneration.
- Existing generator implementation already satisfies these invariants; no generated output was hand-edited and no generator logic change was necessary.
- Review fix: `scripts/verify/contracts.sh` now runs the B14 regression suite in the normal CI/scaffold gate. `tests/contracts/test_contracts.py` asserts the gate keeps this invocation.
- Scope expansion: wiring the new B14 suite into the existing contract gate and adding its self-gate assertion; required so deterministic/read-only/missing-output regressions run continuously rather than only by manual command.

## Verification
- Focused B14 suite: `PATH="$HOME/.local/share/smartsketch/contracts-venv/bin:$PATH" /opt/anaconda3/bin/pytest -q -p no:cacheprovider tests/contracts/test_b14.py` — **3 passed**.
- Gate integration regression was first observed failing because `scripts/verify/contracts.sh` omitted the suite, then passed after wiring: **1 passed**.
- `PATH="/private/tmp/c06-venv/bin:$PATH" PYTHONPATH="$PWD/src/backend" PYTEST_ADDOPTS="-p no:cacheprovider" ./scripts/verify.sh` — **exit 0**, including B14 3 passed, 25 gate negative checks, B08 5, B09 5, B10 45, B12 93, B13 53, and `Scaffold verification passed`.
- `PATH="$HOME/.local/share/smartsketch/contracts-venv/bin:$PATH" ./scripts/gen-contracts.sh --check` — passed.
- `git diff --check` — passed.

## Contract/interface changes and risks
- None. `src/contracts/api.v1.yaml` and generated contract exports are unchanged.
- The system default Python lacks contract validation packages; the complete gate passed when run with `/private/tmp/c06-venv` and an absolute backend `PYTHONPATH` as shown above.
- Two accidental tracked `.superpowers/sdd` report/ledger files were removed from the PR index while their local scratch copies were preserved.

## Next step
- B14 implementation and regression coverage are ready for coordinator integration.
