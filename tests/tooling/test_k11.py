"""K11 quality gate: a report is only green when tests ran, none failed, and every skip is
registered for the current mode; verify.sh modes are explicit and unknown modes fail."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "scripts" / "verify" / "gate.py"
sys.path.insert(0, str(GATE.parent))
import gate  # noqa: E402


def report(tmp_path: Path, *cases: str) -> Path:
    path = tmp_path / "report.xml"
    body = "".join(f'<testcase classname="t" name="c{i}">{case}</testcase>' for i, case in enumerate(cases))
    path.write_text(f'<?xml version="1.0"?><testsuites><testsuite>{body}</testsuite></testsuites>',
                    encoding="utf-8")
    return path


RULES = [gate.Rule("full", gate.re.compile(r"^needs neo4j$"), "why"),
         gate.Rule("*", gate.re.compile(r"^platform$"), "why")]


def test_passing_report_passes(tmp_path):
    assert gate.judge("x", "full", report(tmp_path, "", ""), RULES) == []


def test_zero_tests_is_a_gap(tmp_path):
    problems = gate.judge("x", "full", report(tmp_path), RULES)
    assert any("zero tests is a gap" in p for p in problems)


def test_all_skipped_is_also_zero_executed(tmp_path):
    problems = gate.judge("x", "full", report(tmp_path, '<skipped message="needs neo4j"/>'), RULES)
    assert any("0 test(s) executed" in p for p in problems)


def test_minimum_test_count_is_enforced(tmp_path):
    assert gate.judge("x", "full", report(tmp_path, "", ""), RULES, min_tests=3)


@pytest.mark.parametrize("element", ['<failure message="boom"/>', '<error message="boom"/>'])
def test_failures_and_errors_fail(tmp_path, element):
    problems = gate.judge("x", "full", report(tmp_path, "", element), RULES)
    assert problems == ["failed: t::c1"]


def test_unregistered_skip_fails_even_when_everything_else_passes(tmp_path):
    problems = gate.judge("x", "full", report(tmp_path, "", '<skipped message="TODO later"/>'), RULES)
    assert problems == ["skipped without an allowed reason (1×): TODO later"]


def test_skip_allowed_only_in_its_mode(tmp_path):
    xml = report(tmp_path, "", '<skipped message="needs neo4j"/>')
    assert gate.judge("x", "full", xml, RULES) == []
    assert gate.judge("x", "integration", xml, RULES) != []


def test_wildcard_rule_applies_to_every_mode(tmp_path):
    xml = report(tmp_path, "", '<skipped message="platform"/>')
    assert gate.judge("x", "integration", xml, RULES) == []


def test_skip_without_reason_is_not_allowed(tmp_path):
    problems = gate.judge("x", "full", report(tmp_path, "", "<skipped/>"), RULES)
    assert problems == ["skipped without an allowed reason (1×): (no reason)"]


def test_unreadable_report_fails(tmp_path):
    (tmp_path / "bad.xml").write_text("<not xml", encoding="utf-8")
    assert gate.judge("x", "full", tmp_path / "bad.xml", RULES)[0].startswith("cannot read")
    assert gate.judge("x", "full", tmp_path / "missing.xml", RULES)[0].startswith("cannot read")


def test_cli_exit_codes(tmp_path):
    ok = report(tmp_path, "")
    run = lambda *args: subprocess.run([sys.executable, str(GATE), *args], capture_output=True, text=True)
    assert run("x", "full", str(ok)).returncode == 0
    (tmp_path / "zero.xml").write_text("<testsuites/>", encoding="utf-8")
    failed = run("x", "full", str(tmp_path / "zero.xml"))
    assert failed.returncode == 1 and "FAIL x gate" in failed.stderr
    bad_rules = tmp_path / "rules.txt"
    bad_rules.write_text("full only-two-fields\n", encoding="utf-8")
    assert run("x", "full", str(ok), "--allowlist", str(bad_rules)).returncode == 2


def test_repository_allowlist_is_well_formed_and_explained():
    rules = gate.load_rules()
    assert rules, "allowlist must not be empty while graph tests need Neo4j"
    assert all(rule.mode in {"basic", "full", "integration", "*"} for rule in rules)
    assert all(len(rule.why) >= 10 for rule in rules)
    # A blanket rule would make every skip silent again.
    assert not any(rule.pattern.search("anything at all") for rule in rules)


def test_verify_rejects_unknown_mode():
    result = subprocess.run([str(ROOT / "scripts" / "verify.sh"), "fast"], capture_output=True, text=True, cwd=ROOT)
    assert result.returncode == 2 and "Unknown verify mode" in result.stderr


@pytest.mark.parametrize("script", ["backend.sh", "frontend.sh", "integration.sh"])
def test_stage_scripts_judge_their_reports(script):
    text = (ROOT / "scripts" / "verify" / script).read_text(encoding="utf-8")
    assert "gate.py" in text and "--junitxml" in text or "outputFile.junit" in text
    assert "|| status=" in text and 'exit "$status"' in text
    result = subprocess.run(["bash", "-n", str(ROOT / "scripts" / "verify" / script)], capture_output=True)
    assert result.returncode == 0


def test_verify_full_and_integration_run_the_stage_scripts():
    text = (ROOT / "scripts" / "verify.sh").read_text(encoding="utf-8")
    for needle in ("scripts/verify/backend.sh", "scripts/verify/frontend.sh", "scripts/verify/integration.sh"):
        assert needle in text
