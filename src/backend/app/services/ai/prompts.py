"""Versioned prompt templates (E01).

One file per purpose: ``prompts/<purpose>.yaml``. The file is a strict YAML subset
(flat scalars, a ``variables`` list and a trailing ``template: |`` block literal) so
it stays valid YAML while the backend carries no YAML dependency. Any deviation is
rejected instead of being guessed at.

Callers pin the version they were written against; a template change must bump
``version`` and the callers' pin together, so cache keys and ``model_calls``
audits move with it. ``sha256`` is computed over the parsed template body only
(UTF-8, LF line endings), see ``prompts/MANIFEST.md``.

Error messages name files, fields and variables but never echo template text or
variable values: values are course material or student questions.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_PROMPTS_DIR = Path(__file__).resolve().parents[5] / "prompts"

_NAME = re.compile(r"[a-z][a-z0-9_]*")
_PLACEHOLDER = re.compile(r"\{\{([a-z][a-z0-9_]*)\}\}")
_VERSION = re.compile(r"[1-9][0-9]*")
_SCALAR_BAD_START = set("'\"[]{}&*!|>%@`,#-?:")
_REQUIRED = ("id", "version", "purpose", "evaluation", "variables", "template")
_EVALUATION_PREFIX = "evaluation/"


class PromptError(Exception):
    """Base class for every prompt loading or rendering failure."""


class PromptNotFoundError(PromptError):
    """No template exists for the requested purpose."""


class PromptVersionError(PromptError):
    """The purpose exists but not in the requested version."""


class PromptTemplateError(PromptError):
    """A template file violates the format rules."""


class PromptVariableError(PromptError):
    """Render variables are missing, unexpected or not strings."""


@dataclass(frozen=True)
class RenderedPrompt:
    purpose: str
    version: int
    template_sha256: str
    text: str = field(repr=False)


@dataclass(frozen=True)
class PromptTemplate:
    purpose: str
    version: int
    evaluation: str
    variables: tuple[str, ...]
    template: str = field(repr=False)
    sha256: str

    def render(self, variables: Mapping[str, object]) -> RenderedPrompt:
        declared = set(self.variables)
        given = set(variables)
        missing = sorted(declared - given)
        if missing:
            raise PromptVariableError(f"{self.purpose}@{self.version}: missing variables: {', '.join(missing)}")
        unexpected = sorted(given - declared)
        if unexpected:
            raise PromptVariableError(
                f"{self.purpose}@{self.version}: unexpected variables: {', '.join(unexpected)}"
            )
        wrong = sorted(name for name, value in variables.items() if not isinstance(value, str))
        if wrong:
            raise PromptVariableError(f"{self.purpose}@{self.version}: variables must be str: {', '.join(wrong)}")
        # Single pass: values are inserted verbatim and never re-scanned for placeholders.
        text = _PLACEHOLDER.sub(lambda m: variables[m.group(1)], self.template)  # type: ignore[arg-type,return-value]
        return RenderedPrompt(self.purpose, self.version, self.sha256, text)


class PromptLibrary:
    """Loads ``<root>/<purpose>.yaml`` on first use and caches it for the library's lifetime."""

    def __init__(self, root: Path | None = None) -> None:
        self._root = Path(root) if root is not None else DEFAULT_PROMPTS_DIR
        self._cache: dict[str, PromptTemplate] = {}

    def get(self, purpose: str, version: int) -> PromptTemplate:
        if not isinstance(purpose, str) or not _NAME.fullmatch(purpose):
            raise PromptNotFoundError(f"unknown prompt purpose: {purpose!r}")
        if type(version) is not int:
            raise PromptVersionError(f"{purpose}: version must be int, got {type(version).__name__}")
        template = self._cache.get(purpose)
        if template is None:
            template = self._cache[purpose] = self._load(purpose)
        if version != template.version:
            raise PromptVersionError(
                f"{purpose}: unknown version {version} (available: {template.version})"
            )
        return template

    def render(self, purpose: str, version: int, variables: Mapping[str, object]) -> RenderedPrompt:
        return self.get(purpose, version).render(variables)

    def _load(self, purpose: str) -> PromptTemplate:
        path = self._root / f"{purpose}.yaml"
        if not path.is_file():
            raise PromptNotFoundError(f"unknown prompt purpose: {purpose!r} (no {path.name})")
        try:
            # Universal newlines: CRLF files read (and hash) the same as LF files.
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            raise PromptTemplateError(f"{path.name}: file is not UTF-8") from None
        return _parse(path.name, purpose, text)


def _parse(filename: str, purpose: str, text: str) -> PromptTemplate:
    def fail(message: str) -> PromptTemplateError:
        return PromptTemplateError(f"{filename}: {message}")

    lines = text.split("\n")
    fields: dict[str, object] = {}
    index = 0
    while index < len(lines):
        line = lines[index]
        lineno = index + 1
        index += 1
        if not line.strip() or line.startswith("#"):
            continue
        key, sep, rest = line.partition(":")
        if not sep or not _NAME.fullmatch(key) or (rest and not rest.startswith(" ")):
            raise fail(f"line {lineno}: expected 'key: value' at column 0")
        value = rest.strip()
        if key in fields:
            raise fail(f"line {lineno}: duplicate field {key!r}")
        if key == "evals":
            raise fail(f"line {lineno}: field 'evals' is not allowed; use 'evaluation'")
        if key not in _REQUIRED:
            raise fail(f"line {lineno}: unknown field {key!r}")
        if key == "variables":
            fields[key], index = _parse_variables(value, lines, index, fail)
        elif key == "template":
            if value != "|":
                raise fail(f"line {lineno}: template must be a '|' block literal")
            fields[key] = _parse_block(lines[index:], index, fail)
            index = len(lines)
        else:
            if not value or value[0] in _SCALAR_BAD_START or ": " in value or " #" in value:
                raise fail(f"line {lineno}: {key} must be a plain scalar without quotes, ': ' or ' #'")
            fields[key] = value

    missing = [key for key in _REQUIRED if key not in fields]
    if missing:
        raise fail(f"missing required fields: {', '.join(missing)}")

    if fields["id"] != purpose:
        raise fail("id does not match the file name")
    raw_version = str(fields["version"])
    if not _VERSION.fullmatch(raw_version):
        raise fail("version must be a positive integer")
    evaluation = str(fields["evaluation"])
    if not evaluation.startswith(_EVALUATION_PREFIX) or ".." in evaluation:
        raise fail(f"evaluation must be a path under {_EVALUATION_PREFIX}")

    variables: tuple[str, ...] = fields["variables"]  # type: ignore[assignment]
    body = str(fields["template"])
    stripped = _PLACEHOLDER.sub("", body)
    if "{{" in stripped:
        raise fail("malformed placeholder; use {{name}} with a lowercase identifier and no spaces")
    used = set(_PLACEHOLDER.findall(body))
    undeclared = sorted(used - set(variables))
    if undeclared:
        raise fail(f"template uses undeclared variables: {', '.join(undeclared)}")
    unused = sorted(set(variables) - used)
    if unused:
        raise fail(f"declared variables are not used in template: {', '.join(unused)}")

    return PromptTemplate(
        purpose=purpose,
        version=int(raw_version),
        evaluation=evaluation,
        variables=variables,
        template=body,
        sha256=hashlib.sha256(body.encode("utf-8")).hexdigest(),
    )


def _parse_variables(value, lines, index, fail):  # type: ignore[no-untyped-def]
    if value == "[]":
        return (), index
    if value:
        raise fail(f"line {index}: variables must be '[]' or a '  - name' list")
    names: list[str] = []
    while index < len(lines) and lines[index].startswith("  - "):
        name = lines[index][4:].strip()
        if not _NAME.fullmatch(name):
            raise fail(f"line {index + 1}: invalid variable name (lowercase identifier required)")
        if name in names:
            raise fail(f"line {index + 1}: duplicate variable {name!r}")
        names.append(name)
        index += 1
    if not names:
        raise fail(f"line {index}: variables list is empty; write 'variables: []'")
    return tuple(names), index


def _parse_block(body_lines: list[str], offset: int, fail) -> str:  # type: ignore[no-untyped-def]
    """YAML '|' (clip) with indentation fixed at two spaces; runs to end of file."""
    content: list[str] = []
    for number, line in enumerate(body_lines, start=offset + 1):
        if not line.strip():
            content.append("")
            continue
        if not line.startswith("  "):
            raise fail(f"line {number}: template lines must be indented by two spaces")
        if not any(content_line for content_line in content) and line.startswith("   "):
            raise fail(f"line {number}: first template line must be indented by exactly two spaces")
        content.append(line[2:])
    while content and not content[-1]:
        content.pop()
    if not content:
        raise fail("template is empty")
    return "\n".join(content) + "\n"
