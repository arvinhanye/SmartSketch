"""OPT-04: keep the test index in sync with its three documented file patterns."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATTERNS = (
    "tests/backend/test_*.py",
    "tests/frontend/*.test.ts",
    "tests/integration/test_*.py",
)


def test_index_covers_existing_test_files() -> None:
    index = ROOT / "tests" / "INDEX.md"
    assert index.is_file(), "Missing tests/INDEX.md"
    entries: list[str] = []
    for number, line in enumerate(index.read_text(encoding="utf-8").splitlines(), 1):
        if not line.startswith("|"):
            continue
        cell = line.split("|", 2)[1].strip()
        if cell == "文件" or re.fullmatch(r":?-+:?", cell):
            continue
        match = re.fullmatch(r"\[`(tests/[^`]+)`\]\(([^)]+)\)", cell)
        assert match, f"INDEX.md:{number}: invalid file entry: {cell}"
        path, target = match.groups()
        assert (index.parent / target).resolve() == (ROOT / path).resolve(), (
            f"INDEX.md:{number}: link target does not match {path}: {target}"
        )
        entries.append(path)

    expected = {
        path.relative_to(ROOT).as_posix()
        for pattern in PATTERNS
        for path in ROOT.glob(pattern)
        if path.is_file()
    }
    assert expected, "No test files found for the documented patterns"
    counts = Counter(entries)
    duplicates = sorted(path for path, count in counts.items() if count > 1)
    missing = sorted(expected - counts.keys())
    stale = sorted(counts.keys() - expected)
    assert not (duplicates or missing or stale), (
        f"Duplicate entries: {duplicates}\n"
        f"Missing entries: {missing}\n"
        f"Missing files or out-of-scope entries: {stale}"
    )
