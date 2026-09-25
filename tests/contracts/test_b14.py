"""B14: generated contract exports are deterministic and drift-checkable."""

import hashlib
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = Path("src/contracts/v1/generated")


def _copy_generator_tree(destination: Path) -> Path:
    for relative in ("scripts/gen-contracts.sh", "scripts/gen_contracts.py", "src/contracts/api.v1.yaml",
                     "src/contracts/toolchain.txt", OUTPUT):
        source = ROOT / relative
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            shutil.copy2(source, target)
    return destination


def _run(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", "scripts/gen-contracts.sh", *args], cwd=root,
                          capture_output=True, text=True)


def _hashes(root: Path) -> dict[str, str]:
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted((root / OUTPUT).rglob("*")) if path.is_file()}


@pytest.fixture
def generator_tree(tmp_path):
    return _copy_generator_tree(tmp_path / "repo")


def test_generation_is_byte_identical_across_two_runs(generator_tree):
    assert _run(generator_tree).returncode == 0
    first = _hashes(generator_tree)
    assert _run(generator_tree).returncode == 0
    assert _hashes(generator_tree) == first


def test_check_detects_tampering_without_mutating_checkout(generator_tree):
    target = generator_tree / OUTPUT / "openapi.json"
    target.write_bytes(target.read_bytes() + b"\n tampered")
    before = _hashes(generator_tree)

    result = _run(generator_tree, "--check")

    assert result.returncode != 0
    assert _hashes(generator_tree) == before


def test_check_detects_missing_stage_and_regeneration_restores_it(generator_tree):
    stage = generator_tree / OUTPUT / "typescript"
    shutil.rmtree(stage)

    result = _run(generator_tree, "--check")

    assert result.returncode != 0
    assert not stage.exists(), "--check must not recreate missing generated files"
    assert _run(generator_tree).returncode == 0
    assert stage.is_dir()
    assert _run(generator_tree, "--check").returncode == 0
