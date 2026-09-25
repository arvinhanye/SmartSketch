"""B07: contract checks report an unambiguous outcome and fail closed."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
SHIM = ROOT / "tests/contracts/_shim"
WORKSPACE_FILES = [
    "scripts/check_contracts.py",
    "src/contracts/api.v1.yaml",
    "src/contracts/events.v1.md",
    "src/contracts/errors.v1.md",
    "src/contracts/README.md",
    "src/contracts/toolchain.txt",
    "docs/architecture.md",
    "specs/course-knowledge-graph.md",
    "specs/learning-path.md",
    "specs/grounded-qa.md",
    "specs/teacher-review-publish.md",
    "AGENTS.md",
]


def run_gate(cwd: Path = ROOT, *args: str, blocked: str = "") -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SHIM) if blocked else ""
    env["BLOCK_MODULES"] = blocked
    return subprocess.run(
        [sys.executable, "scripts/check_contracts.py", *args],
        cwd=cwd, env=env, text=True, capture_output=True, check=False,
    )


def test_valid_contract_reports_pass():
    result = run_gate()
    assert result.returncode == 0, result.stderr
    assert "PASS" in result.stdout
    assert "SKIP" not in result.stdout


@pytest.mark.parametrize("module,package", [
    ("yaml", "pyyaml"),
    ("openapi_spec_validator", "openapi-spec-validator"),
    ("jsonschema", "jsonschema"),
])
def test_missing_dependency_reports_fail(module: str, package: str):
    result = run_gate(blocked=module)
    assert result.returncode != 0
    assert "FAIL" in result.stderr
    assert package in result.stderr
    assert "PASS" not in result.stdout


def test_explicit_scaffold_skip_is_labeled_incomplete():
    result = run_gate(ROOT, "--allow-scaffold", blocked="yaml")
    assert result.returncode == 0
    assert "SKIP" in result.stdout
    assert "INCOMPLETE" in result.stdout
    assert "PASS" not in result.stdout


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    for name in WORKSPACE_FILES:
        destination = tmp_path / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, destination)
    assert run_gate(tmp_path).returncode == 0
    return tmp_path


@pytest.mark.parametrize("broken", ["reference", "relation_enum"])
def test_invalid_contract_reports_fail(workspace: Path, broken: str):
    path = workspace / "src/contracts/api.v1.yaml"
    spec = yaml.safe_load(path.read_text(encoding="utf-8"))
    if broken == "reference":
        spec["components"]["schemas"]["Citation"]["properties"]["chunk_id"] = {
            "$ref": "#/components/schemas/MissingB07"
        }
    else:
        spec["components"]["schemas"]["RelationType"]["enum"].append("RELATED")
    path.write_text(yaml.safe_dump(spec, allow_unicode=True, sort_keys=False), encoding="utf-8")
    result = run_gate(workspace)
    assert result.returncode != 0
    assert "FAIL" in result.stderr
    assert "PASS" not in result.stdout


@pytest.mark.parametrize("field", ["components", "paths", "schemas", "relation_type"])
def test_malformed_structure_reports_fail_not_traceback(workspace: Path, field: str):
    path = workspace / "src/contracts/api.v1.yaml"
    spec = yaml.safe_load(path.read_text(encoding="utf-8"))
    if field == "schemas":
        spec["components"]["schemas"] = None
    elif field == "relation_type":
        spec["components"]["schemas"]["RelationType"] = None
    else:
        spec[field] = None
    path.write_text(yaml.safe_dump(spec, allow_unicode=True, sort_keys=False), encoding="utf-8")
    result = run_gate(workspace)
    assert result.returncode != 0
    assert "FAIL" in result.stderr
    assert "Traceback" not in result.stderr


def test_backend_test_extra_declares_contract_check_dependencies():
    project = tomllib.loads((ROOT / "src/backend/pyproject.toml").read_text(encoding="utf-8"))
    dependencies = project["project"]["optional-dependencies"]["test"]
    for requirement in (
        "pyyaml==6.0.2", "openapi-spec-validator==0.9.0", "jsonschema==4.26.0",
    ):
        assert requirement in dependencies


@pytest.fixture
def shell_workspace(tmp_path: Path) -> Path:
    """Keep the real dispatcher while replacing slow checks at process boundaries."""
    script = tmp_path / "scripts/verify/contracts.sh"
    script.parent.mkdir(parents=True)
    shutil.copy2(ROOT / "scripts/verify/contracts.sh", script)
    (tmp_path / "scripts/check_contracts.py").write_text(
        "import os, sys\nprint('source checked')\nsys.exit(int(os.getenv('SOURCE_RC', '0')))\n",
        encoding="utf-8",
    )
    generator = tmp_path / "scripts/gen-contracts.sh"
    generator.write_text("#!/bin/sh\necho generated\nexit 0\n", encoding="utf-8")
    generator.chmod(0o755)
    negative = tmp_path / "tests/contracts/test_contracts.py"
    negative.parent.mkdir(parents=True)
    negative.write_text("print('✓ negative checks passed')\n", encoding="utf-8")
    for name in ("test_b08.py", "test_b09.py", "test_b10.py", "test_b12.py", "test_b13.py", "test_b14.py"):
        (negative.parent / name).write_text("def test_contract_placeholder(): pass\n", encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize("source_rc, expected", [(0, "PASS"), (1, "FAIL")])
def test_dispatcher_reports_aggregate_status(shell_workspace: Path, source_rc: int, expected: str):
    env = os.environ.copy()
    env["SOURCE_RC"] = str(source_rc)
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
    result = subprocess.run(
        ["bash", "scripts/verify/contracts.sh"], cwd=shell_workspace,
        env=env, text=True, capture_output=True, check=False,
    )
    assert result.returncode == source_rc
    assert expected in result.stdout + result.stderr
