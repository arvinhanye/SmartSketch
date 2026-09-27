#!/usr/bin/env python3
"""K11: judge a JUnit XML test report so that "green" means tests really ran and passed.

A report fails the gate when
- it cannot be read, or holds zero executed tests ("零测试视为缺口");
- any test failed or errored;
- any test was skipped (or marked todo) for a reason not allowed in the current mode
  ("已实现模块无静默 SKIP"). Allowed reasons live in scripts/verify/allowed-skips.txt as
  ``<mode>\t<regex>\t<why>`` lines; ``*`` as mode applies to every mode.

Usage: gate.py <label> <mode> <junit.xml> [--min-tests N]
Exit 0 pass, 1 gate failure, 2 usage error. Prints a one-line summary either way.
"""

from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

ALLOWLIST = Path(__file__).with_name("allowed-skips.txt")


@dataclass(frozen=True)
class Rule:
    mode: str
    pattern: re.Pattern[str]
    why: str


def load_rules(path: Path = ALLOWLIST) -> list[Rule]:
    rules = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) != 3 or not all(part.strip() for part in parts):
            raise ValueError(f"{path}:{number}: expected <mode>\\t<regex>\\t<why>")
        rules.append(Rule(parts[0].strip(), re.compile(parts[1].strip()), parts[2].strip()))
    return rules


def judge(label: str, mode: str, report: Path, rules: list[Rule], min_tests: int = 1) -> list[str]:
    try:
        root = ET.parse(report).getroot()
    except (OSError, ET.ParseError) as error:
        return [f"cannot read test report {report}: {error}"]
    problems: list[str] = []
    executed = 0
    unexpected: dict[str, int] = {}
    for case in root.iter("testcase"):
        name = f"{case.get('classname', '')}::{case.get('name', '')}"
        failure = case.find("failure")
        error = case.find("error")
        skipped = case.find("skipped")
        if failure is not None or error is not None:
            problems.append(f"failed: {name}")
            executed += 1
        elif skipped is not None:
            reason = (skipped.get("message") or skipped.text or "").strip() or "(no reason)"
            if not any(rule.mode in ("*", mode) and rule.pattern.search(reason) for rule in rules):
                unexpected[reason] = unexpected.get(reason, 0) + 1
        else:
            executed += 1
    for reason, count in sorted(unexpected.items()):
        problems.append(f"skipped without an allowed reason ({count}×): {reason}")
    if executed < min_tests:
        problems.append(f"only {executed} test(s) executed (minimum {min_tests}); zero tests is a gap, not a pass")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("label")
    parser.add_argument("mode")
    parser.add_argument("report", type=Path)
    parser.add_argument("--min-tests", type=int, default=1)
    parser.add_argument("--allowlist", type=Path, default=ALLOWLIST)
    try:
        args = parser.parse_args(argv)
        rules = load_rules(args.allowlist)
    except (SystemExit, ValueError, OSError) as error:
        print(f"gate: {error}", file=sys.stderr)
        return 2
    problems = judge(args.label, args.mode, args.report, rules, args.min_tests)
    if problems:
        print(f"FAIL {args.label} gate ({args.mode}):", file=sys.stderr)
        for problem in problems[:50]:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    print(f"PASS {args.label} gate ({args.mode})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
