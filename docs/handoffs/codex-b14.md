# B14 handoff — contract export and drift checking

## Delivered
- Added `tests/contracts/test_b14.py` covering deterministic repeated generation, tamper detection without `--check` mutation, missing-stage detection, and canonical restoration by regeneration.
- Existing generator behavior already satisfies these invariants; no generated output was hand-edited and no generator logic change was necessary.

## Verification
- Focused regression: 3 passed using the documented contracts venv for generator subprocesses and the available pytest executable (`/opt/anaconda3/bin/pytest -q -p no:cacheprovider tests/contracts/test_b14.py`).
- `./scripts/gen-contracts.sh --check`: passed before and after repeat generation.
- Two full regeneration SHA-256 aggregate hashes matched exactly: `5e7b1b6ab76ebd3ca93e6f9aaa1b83227f46132fec94cfe2a9361269383a0757`.
- `./scripts/verify.sh`: contracts gate reports missing `openapi-spec-validator` and `jsonschema` in the interpreter environment; generated-output check passed.
- `git diff --check`: run separately as part of final commit review.

## Contract/interface changes and risks
- None. `src/contracts/api.v1.yaml` and generated contract exports are unchanged.
- Local default `python3` lacks the generator/test dependencies; use the pinned contracts environment in `PATH` for generation. Full scaffold verification remains environment-limited until the missing validators are installed.

## Next step
- No follow-up implementation needed; install the missing pinned validation dependencies in the intended Python environment before treating `scripts/verify.sh` as green.
