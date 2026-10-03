"""J06: validate streamed answer markers against one bound published version."""

from __future__ import annotations

import re
import logging
import unicodedata
from dataclasses import dataclass
from collections.abc import Iterable
from typing import Any

from app.services.versions.resolver import PublishedVersion


SENTINEL = "<<INSUFFICIENT_EVIDENCE>>"
_LOGGER = logging.getLogger(__name__)
_BRACKETS = {"[": "]", "【": "】", "［": "］"}
_NUMBER_LIST = re.compile(r"[1-9][0-9]*(?:\s*[,，、]\s*[1-9][0-9]*)*")
_CLASS_LIKE = re.compile(r"\s*[0-9０-９].*")
_CITATION = re.compile(r"\[[1-9][0-9]*\]")
_BOUNDARY = re.compile(r"[。！？!?]+|\.(?=\s|$)|\n")
_TEMPLATES = {
    "no_retrieval_hit": "课程资料中没有找到与这个问题相关的内容。",
    "below_similarity_threshold": "课程资料中与这个问题相关的内容不够充分，无法给出有出处的回答。",
    "insufficient_evidence": "检索到的课程资料不足以回答这个问题。",
    "all_citations_invalidated": "生成的回答无法与课程资料对应，已撤回。可以换一种问法或缩小问题范围。",
}


class TruncatedAnswer(Exception):
    """The answer hit the output limit and failed citation validation (ADR-082 decision 2).

    A generation fault, not missing course material: the caller reports ``LLM_UNAVAILABLE`` /
    ``truncated`` instead of ``not_covered``. Audit fields are already set when this is raised.
    """


@dataclass(frozen=True, slots=True)
class Evidence:
    index: int
    chunk_id: str
    document_id: str
    course_id: str
    revision_id: str
    text: str
    page: int | None = None
    section_path: str | None = None

    def citation(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "index": self.index, "chunk_id": self.chunk_id,
            "document_id": self.document_id, "text": self.text,
        }
        if self.page is not None and self.page >= 1:
            result["page"] = self.page
        if self.section_path:
            result["section_path"] = self.section_path
        return result


def not_covered(
    reason: str, *, graph_version: int, request_id: str, latency_ms: int,
    related_kp_ids: Iterable[str] = (),
) -> dict[str, Any]:
    """Construct a safe response without copying any model output."""
    return {
        "status": "not_covered", "reason": reason, "answer": _TEMPLATES[reason],
        "citations": [], "related_kp_ids": list(dict.fromkeys(related_kp_ids)),
        "graph_version": graph_version, "request_id": request_id, "latency_ms": latency_ms,
    }


def _marker(content: str, allowed: dict[int, Evidence], opening: str, closing: str) -> tuple[str, list[int], int]:
    if _NUMBER_LIST.fullmatch(content):
        output: list[str] = []
        valid: list[int] = []
        unknown = 0
        seen: set[int] = set()
        for part in re.split(r"\s*[,，、]\s*", content):
            index = int(part)
            if index in seen:
                continue
            seen.add(index)
            if index in allowed:
                output.append(f"[{index}]")
                valid.append(index)
            else:
                unknown += 1
        return "".join(output), valid, unknown
    if _CLASS_LIKE.fullmatch(content):
        return "", [], 1
    return f"{opening}{content}{closing}", [], 0


def _scan(raw: str, allowed: dict[int, Evidence], *, complete: bool) -> tuple[str, list[int], int]:
    out: list[str] = []
    valid: list[int] = []
    unknown = 0
    i = 0
    fence: str | None = None
    inline: int | None = None
    while i < len(raw):
        char = raw[i]
        line_start = i == 0 or raw[i - 1] == "\n"
        if inline is None and line_start and char in "`~":
            run = len(raw[i:]) - len(raw[i:].lstrip(char))
            if not complete and i + run == len(raw) and run < 3:
                break
            if run >= 3 and (fence is None or fence == char):
                fence = None if fence else char
                out.append(raw[i:i + run])
                i += run
                continue
        if fence is not None:
            out.append(char)
            i += 1
            continue
        if char == "`":
            run = len(raw[i:]) - len(raw[i:].lstrip("`"))
            if inline is None:
                inline = run
            elif inline == run:
                inline = None
            out.append(raw[i:i + run])
            i += run
            continue
        if inline is not None:
            out.append(char)
            i += 1
            continue
        if char == "<":
            remaining = raw[i:]
            if remaining.startswith(SENTINEL):
                i += len(SENTINEL)
                continue
            if not complete and SENTINEL.startswith(remaining):
                break
        if char in _BRACKETS:
            closing = _BRACKETS[char]
            end = raw.find(closing, i + 1, i + 34)
            if end >= 0:
                content = raw[i + 1:end]
                replacement, numbers, rejected = _marker(content, allowed, char, closing)
                out.append(replacement)
                valid.extend(numbers)
                unknown += rejected
                i = end + 1
                continue
            if not complete and len(raw) - i <= 32 and re.fullmatch(r"[0-9０-９,，、\s-]*", raw[i + 1:]):
                break
        out.append(char)
        i += 1
    return "".join(out), valid, unknown


def _mask_code(answer: str) -> str:
    """Keep line breaks and citation syntax, masking only Markdown code spans."""
    chars = list(answer)
    fence: str | None = None
    inline: int | None = None
    i = 0
    while i < len(answer):
        char = answer[i]
        line_start = i == 0 or answer[i - 1] == "\n"
        if inline is None and line_start and char in "`~":
            run = len(answer[i:]) - len(answer[i:].lstrip(char))
            if run >= 3 and (fence is None or fence == char):
                fence = None if fence else char
                chars[i:i + run] = " " * run
                i += run
                continue
        if fence is not None:
            if char != "\n":
                chars[i] = " "
            i += 1
            continue
        if char == "`":
            run = len(answer[i:]) - len(answer[i:].lstrip("`"))
            if inline is None:
                inline = run
            elif inline == run:
                inline = None
            chars[i:i + run] = " " * run
            i += run
            continue
        if inline is not None and char != "\n":
            chars[i] = " "
        i += 1
    return "".join(chars)


def _uncited_units(answer: str) -> int:
    masked = _mask_code(answer)
    units: list[str] = []
    start = 0
    for match in _BOUNDARY.finditer(masked):
        units.append(masked[start:match.end()])
        start = match.end()
    units.append(masked[start:])
    count = 0
    previous: int | None = None
    for pos, unit in enumerate(units):
        if previous is not None:
            leading = re.match(r"^\s*(?:\[[1-9][0-9]*\]\s*)+", unit)
            if leading:
                units[previous] += leading.group()
                unit = unit[leading.end():]
                units[pos] = unit
        if re.match(r"^#{1,6} ", unit):
            previous = None
            continue
        without_refs = _CITATION.sub("", unit)
        if any(unicodedata.category(ch)[0] in "LN" for ch in without_refs):
            previous = pos
        else:
            previous = None
    for unit in units:
        if re.match(r"^#{1,6} ", unit):
            continue
        without_refs = _CITATION.sub("", unit)
        if any(unicodedata.category(ch)[0] in "LN" for ch in without_refs) and not _CITATION.search(unit):
            count += 1
    return count


class CitationStream:
    """Feed model chunks, emit only stable validated text, then build the terminal response."""

    def __init__(self, version: PublishedVersion, request_id: str, evidence: Iterable[Evidence]):
        self.version = version
        self.request_id = request_id
        self.allowed: dict[int, Evidence] = {}
        self.integrity_rejections = 0
        for item in evidence:
            if (item.course_id != version.course_id or not version.covers_revision(item.revision_id)
                or not item.text or not item.chunk_id or not item.document_id
                or not ((item.page is not None and item.page >= 1) or (item.section_path and item.section_path.strip()))):
                self.integrity_rejections += 1
                _LOGGER.error("J06 rejected out-of-scope or unlocatable evidence index=%s chunk_id=%s", item.index, item.chunk_id)
                continue
            if item.index < 1 or item.index in self.allowed:
                raise ValueError("evidence indexes must be unique positive integers")
            self.allowed[item.index] = item
        self._raw = ""
        self._emitted = ""
        self._valid: list[int] = []
        self.unknown_count = 0
        self.stop_supplier = False
        self._ended = False
        self.invalidation_subtype: str | None = None
        self.uncited_units = 0
        self.truncated = False

    def feed(self, chunk: str) -> str:
        if self._ended or self.stop_supplier:
            return ""
        self._raw += chunk
        stripped = self._raw.lstrip()
        if not self._emitted and stripped:
            if stripped.startswith(SENTINEL):
                self.stop_supplier = True
                return ""
            if SENTINEL.startswith(stripped):
                return ""
        source = self._raw.lstrip()
        processed, valid, unknown = _scan(source, self.allowed, complete=False)
        if not processed.startswith(self._emitted):
            raise RuntimeError("stream parser changed already emitted text")
        delta = processed[len(self._emitted):]
        self._emitted = processed
        self._valid = valid
        self.unknown_count = unknown
        return delta

    def finish(self) -> str:
        if self._ended:
            return ""
        self._ended = True
        if self.stop_supplier:
            return ""
        processed, self._valid, self.unknown_count = _scan(self._raw.lstrip(), self.allowed, complete=True)
        delta = processed[len(self._emitted):]
        self._emitted = processed
        return delta

    def finalize(self, *, latency_ms: int, truncated: bool = False, related_kp_ids: Iterable[str] = ()) -> dict[str, Any]:
        if not self._ended:
            raise RuntimeError("finish the stream before constructing the final response")
        self.truncated = truncated
        if self.stop_supplier:
            return not_covered("insufficient_evidence", graph_version=self.version.graph_version,
                               request_id=self.request_id, latency_ms=latency_ms, related_kp_ids=related_kp_ids)
        if not self._valid:
            self.invalidation_subtype = "unknown_only" if self.unknown_count else "no_markers"
        else:
            self.uncited_units = _uncited_units(self._emitted)
            if self.uncited_units:
                self.invalidation_subtype = "uncited_sentence"
        if self.invalidation_subtype and truncated:
            raise TruncatedAnswer()
        if self.invalidation_subtype:
            return not_covered("all_citations_invalidated", graph_version=self.version.graph_version,
                               request_id=self.request_id, latency_ms=latency_ms, related_kp_ids=related_kp_ids)
        ordered = list(dict.fromkeys(self._valid))
        return {
            "status": "answered", "answer": self._emitted,
            "citations": [self.allowed[index].citation() for index in ordered],
            "related_kp_ids": list(dict.fromkeys(related_kp_ids)),
            "graph_version": self.version.graph_version, "request_id": self.request_id,
            "latency_ms": latency_ms,
        }
