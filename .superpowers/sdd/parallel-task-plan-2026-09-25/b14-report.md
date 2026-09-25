# B14 implementation report

## Scope and ruling
The B14 acceptance is deterministic generation, read-only drift checks, detection of tampered/missing outputs, and restoration through regeneration. Inspection of the existing `scripts/gen-contracts.sh` showed that it already implements temporary-directory checking, recursive comparison (excluding only `__pycache__`), non-zero drift exits, and canonical regeneration. The B14 change therefore adds regression coverage without duplicating or altering a working generator implementation. No ambiguity required broadening scope.

## Test-first evidence
Added `tests/contracts/test_b14.py` before implementation changes. Initial focused run exposed an environment mismatch rather than a B14 defect: pytest was available under the Anaconda interpreter, while the generator's `python3` lacked PyYAML. With the contracts venv prepended to `PATH` and pytest launched from the available installation, all three tests passed. The test suite exercises the real script in a temporary copied fixture tree, so deliberate corruption cannot mutate the checkout.

## Verification evidence
- Focused tests: `/opt/anaconda3/bin/pytest -q -p no:cacheprovider tests/contracts/test_b14.py` with `$HOME/.local/share/smartsketch/contracts-venv/bin` prepended to `PATH`: **3 passed**.
- `./scripts/gen-contracts.sh --check`: **passed**.
- Two consecutive full generations: aggregate SHA-256 equal on both runs: `5e7b1b6ab76ebd3ca93e6f9aaa1b83227f46132fec94cfe2a9361269383a0757`.
- Tampered `openapi.json`: `--check` returns non-zero and output hash remains unchanged after check.
- Missing `typescript/` stage: `--check` returns non-zero without recreating it; regeneration restores it and a subsequent check passes.
- `./scripts/verify.sh`: hook tests passed; contract checker reports the Python environment is missing `openapi-spec-validator` and `jsonschema`; generator consistency check passed. This is an environment limitation, not a reported green gate.
- `git diff --check`: see final task status.

## Files
- Added test: `tests/contracts/test_b14.py`.
- Handoff: `docs/handoffs/codex-b14.md`.
- Generated output and source spec remain unchanged.
