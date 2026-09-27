"""Shell scripts must brace a variable that is directly followed by a non-ASCII character.

macOS ships bash 3.2, which in a UTF-8 locale reads the leading bytes of a character such as
"）" or "。" as part of the variable name: ``"$API_PORT）"`` fails with
``API_PORT\xef: unbound variable`` under ``set -u`` (reported on scripts/start-demo.sh).
Write ``"${API_PORT}）"`` instead.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UNBRACED_BEFORE_MULTIBYTE = re.compile(r"\$[A-Za-z_][A-Za-z0-9_]*(?=[^\x00-\x7f])")


def _shell_scripts() -> list[Path]:
    found = []
    for base in ("scripts", "tests", ".claude"):
        for path in (ROOT / base).rglob("*.sh"):
            if "node_modules" not in path.parts:
                found.append(path)
    return sorted(found)


def test_scripts_are_found() -> None:
    assert ROOT / "scripts" / "start-demo.sh" in _shell_scripts()


def test_no_unbraced_variable_before_a_multibyte_character() -> None:
    offenders = [
        f"{path.relative_to(ROOT)}:{lineno}: {line.strip()}"
        for path in _shell_scripts()
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if not line.lstrip().startswith("#") and UNBRACED_BEFORE_MULTIBYTE.search(line)
    ]
    assert offenders == [], "brace these variables, e.g. ${VAR}）:\n" + "\n".join(offenders)


def test_the_pattern_catches_the_reported_line() -> None:
    assert UNBRACED_BEFORE_MULTIBYTE.search('die "（macOS：lsof -i :$API_PORT）。"')
    assert not UNBRACED_BEFORE_MULTIBYTE.search('die "（macOS：lsof -i :${API_PORT}）。"')
