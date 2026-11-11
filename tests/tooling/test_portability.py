"""Historical Windows fixes: real checkout bytes, temporary paths and gate output."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_demo_checkout_keeps_manifest_hash_with_autocrlf():
    manifest = json.loads((ROOT / "datasets/demo/manifest.json").read_text(encoding="utf-8"))
    for document in manifest["documents"]:
        relative = "datasets/demo/" + document["path"]
        data = subprocess.check_output(
            ["git", "-c", "core.autocrlf=true", "cat-file", "--filters", f"HEAD:{relative}"],
            cwd=ROOT,
        )
        assert hashlib.sha256(data).hexdigest() == document["sha256"]


def test_pdf_checkout_is_not_subject_to_text_conversion():
    relative = "datasets/contest/course1-ds-ch3/ch3-stack-queue.pdf"
    source = subprocess.check_output(["git", "show", f"HEAD:{relative}"], cwd=ROOT)
    filtered = subprocess.check_output(
        ["git", "-c", "core.autocrlf=true", "cat-file", "--filters", f"HEAD:{relative}"], cwd=ROOT,
    )
    assert filtered == source


@pytest.mark.parametrize("override", [False, True])
def test_worker_heartbeat_uses_platform_temp_or_explicit_override(tmp_path, override):
    platform_temp = tmp_path / "platform temp"
    platform_temp.mkdir()
    explicit = tmp_path / "explicit heartbeat"
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src/backend"),
               TMPDIR=str(platform_temp), TEMP=str(platform_temp), TMP=str(platform_temp),
               PYTHONIOENCODING="utf-8")
    env.pop("WORKER_HEARTBEAT_FILE", None)
    if override:
        env["WORKER_HEARTBEAT_FILE"] = str(explicit)
    expected = explicit if override else platform_temp / "smartsketch-worker.heartbeat"
    env["EXPECTED_TEST_HEARTBEAT"] = str(expected.resolve())
    code = """
import json
import os
from app.workers.runner import heartbeat_path
path = heartbeat_path()
if str(path.resolve()) == os.environ['EXPECTED_TEST_HEARTBEAT']:
    path.touch()
print(json.dumps({'path': str(path.resolve()), 'exists': path.is_file()}))
"""
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env,
                            capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert Path(payload["path"]) == expected.resolve()
    assert payload["exists"] is True


@pytest.mark.parametrize("encoding", ["cp1252", "gbk", "ascii"])
def test_contract_success_output_survives_legacy_console_encoding(encoding):
    result = subprocess.run(
        [sys.executable, "scripts/check_contracts.py"], cwd=ROOT,
        env=dict(os.environ, PYTHONIOENCODING=encoding), capture_output=True,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
    output = result.stdout.decode("utf-8")
    assert "PASS contracts:" in output and "✓" in output


@pytest.mark.parametrize("message,text,allowed", [
    ("collection skipped", "needs neo4j", True),
    ("collection skipped", "unregistered reason", False),
    ("unregistered reason", "needs neo4j", False),
    ("collection skipped", "", False),
])
def test_collection_skip_uses_actual_reason_without_relaxing_allowlist(tmp_path, message, text, allowed):
    report = tmp_path / "report.xml"
    report.write_text(
        '<testsuites><testsuite><testcase name="executed"/>'
        f'<testcase name="skip"><skipped message="{message}">{text}</skipped></testcase>'
        '</testsuite></testsuites>', encoding="utf-8",
    )
    rules = tmp_path / "allowed.txt"
    rules.write_text("full\t^needs neo4j$\tRegistered integration prerequisite\n", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "scripts/verify/gate.py", "portability", "full", str(report),
         "--allowlist", str(rules)], cwd=ROOT, capture_output=True,
    )
    assert result.returncode == (0 if allowed else 1), result.stderr
    if not allowed:
        assert b"skipped without an allowed reason" in result.stderr


@pytest.mark.parametrize("reason,allowed", [("needs neo4j", True), ("unregistered reason", False)])
def test_real_pytest_collection_skip_is_checked_against_allowlist(tmp_path, reason, allowed):
    (tmp_path / "test_skip.py").write_text(
        f"import pytest\npytest.skip({reason!r}, allow_module_level=True)\n", encoding="utf-8",
    )
    (tmp_path / "test_run.py").write_text("def test_runs():\n    assert True\n", encoding="utf-8")
    report = tmp_path / "report.xml"
    run = subprocess.run(
        [sys.executable, "-m", "pytest", str(tmp_path), "-q", "-p", "no:cacheprovider",
         f"--junitxml={report}"], cwd=tmp_path, capture_output=True,
    )
    assert run.returncode == 0, run.stderr
    rules = tmp_path / "allowed.txt"
    rules.write_text("full\t^needs neo4j$\tRegistered integration prerequisite\n", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "scripts/verify/gate.py", "portability", "full", str(report),
         "--allowlist", str(rules)], cwd=ROOT, capture_output=True,
    )
    assert result.returncode == (0 if allowed else 1), result.stderr
    if not allowed:
        assert b"skipped without an allowed reason" in result.stderr
