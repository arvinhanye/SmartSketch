#!/usr/bin/env python3
"""K03: offline evaluation of grounded course answers (standard library only).

Input JSON has ``dataset_id``, ``model: {id, is_fake}``, and ``cases``.
Each case has ``id``, ``question``, ``covered`` (gold boolean), ``kind``
(``normal``, ``uncovered``, or ``injection``), ``evidence`` (the published
chunks allowed for this request), and ``response`` (the final JSON answer).
An evidence item has ``chunk_id``, ``document_id``, ``text`` and ``page`` or
``section_path``. A response uses the wire fields ``status``, ``reason``
(when not covered), ``answer``, and ``citations``. A citation uses ``index``,
``chunk_id``, ``document_id``, ``text``, and ``page`` or ``section_path``.

The optional judgments JSON has ``dataset_id`` and ``citations``: a list of
``{case_id, index, statement, supported, note}``. ``supported`` is a human
boolean: the cited passage alone must support *every* answer statement that
uses that index. An injection case also has an entry in ``injections``:
``{case_id, followed, note}``, where ``followed`` says whether the answer
obeyed instructions embedded in retrieved evidence. Notes preserve false
positive findings for human review. Missing judgments remain unjudged; they
are never silently counted as supported or as safe.

Usage: python evaluation/evaluate_qa.py --input cases.json
       python evaluation/evaluate_qa.py --input cases.json --judgments review.json --out report.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REASONS = (
    "no_retrieval_hit",
    "below_similarity_threshold",
    "insufficient_evidence",
    "all_citations_invalidated",
)
SUBTYPES = ("no_markers", "unknown_only", "uncited_sentence")


def ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _location(item: dict[str, Any]) -> tuple[str, Any] | None:
    if item.get("page") is not None:
        return ("page", item["page"])
    if item.get("section_path"):
        return ("section_path", item["section_path"])
    return None


def citation_is_valid(citation: dict[str, Any], evidence: list[dict[str, Any]]) -> bool:
    """Check the citation against the bound published chunks, not its number."""
    for chunk in evidence:
        if (
            chunk["chunk_id"] == citation.get("chunk_id")
            and chunk["document_id"] == citation.get("document_id")
            and _location(chunk) is not None
            and _location(chunk) == _location(citation)
            and isinstance(citation.get("text"), str)
            and bool(citation["text"])
            and citation["text"] in chunk["text"]
        ):
            return True
    return False


def evaluate(data: dict[str, Any], judgments: dict[str, Any] | None = None) -> dict[str, Any]:
    cases = data["cases"]
    _require(isinstance(cases, list), "cases must be a list")
    case_ids = [case["id"] for case in cases]
    _require(len(case_ids) == len(set(case_ids)), "case IDs must be unique")
    if judgments is not None:
        _require(judgments["dataset_id"] == data["dataset_id"], "judgment dataset_id differs")

    support_reviews = {}
    injection_reviews = {}
    if judgments:
        for item in judgments.get("citations", []):
            key = (item["case_id"], item["index"])
            _require(key not in support_reviews, f"duplicate citation judgment: {key}")
            _require(isinstance(item["supported"], bool), f"supported must be boolean: {key}")
            support_reviews[key] = item
        for item in judgments.get("injections", []):
            key = item["case_id"]
            _require(key not in injection_reviews, f"duplicate injection judgment: {key}")
            _require(isinstance(item["followed"], bool), f"followed must be boolean: {key}")
            injection_reviews[key] = item

    confusion = {"covered_answered": 0, "covered_not_covered": 0,
                 "uncovered_answered": 0, "uncovered_not_covered": 0}
    reasons = {reason: 0 for reason in REASONS}
    subtypes = {subtype: 0 for subtype in SUBTYPES}
    citation_total = valid_total = supported_total = judged_total = 0
    generated_total = injection_total = injection_followed = injection_judged = 0
    details = []
    false_positives = []

    for case in cases:
        case_id = case["id"]
        _require(isinstance(case["covered"], bool), f"{case_id}: covered must be boolean")
        _require(case["kind"] in ("normal", "uncovered", "injection"), f"{case_id}: unknown kind")
        response = case["response"]
        status = response["status"]
        _require(status in ("answered", "not_covered"), f"{case_id}: unknown status")
        reason = response.get("reason")
        if status == "not_covered":
            _require(reason in REASONS, f"{case_id}: unknown not_covered reason")
            reasons[reason] += 1
            if reason == "all_citations_invalidated":
                subtype = case.get("withdrawal_subtype")
                _require(subtype in SUBTYPES, f"{case_id}: withdrawal_subtype required")
                subtypes[subtype] += 1
        if status == "answered" or reason in ("insufficient_evidence", "all_citations_invalidated"):
            generated_total += 1

        cell = ("covered" if case["covered"] else "uncovered") + "_" + status
        confusion[cell] += 1
        if cell == "uncovered_answered":
            false_positives.append({"case_id": case_id, "type": "hallucinated_answer"})

        citation_results = []
        citations = response.get("citations", [])
        _require(isinstance(citations, list), f"{case_id}: citations must be a list")
        if status == "not_covered":
            _require(not citations, f"{case_id}: not_covered must have no citations")
        seen_indices = set()
        for citation in citations:
            index = citation["index"]
            _require(index not in seen_indices, f"{case_id}: duplicate citation index")
            seen_indices.add(index)
            citation_total += 1
            valid = citation_is_valid(citation, case["evidence"])
            result = {"index": index, "valid": valid, "supported": None}
            if valid:
                valid_total += 1
                review = support_reviews.get((case_id, index))
                if review is not None:
                    judged_total += 1
                    result["supported"] = review["supported"]
                    if review["supported"]:
                        supported_total += 1
                    else:
                        false_positives.append({"case_id": case_id, "index": index,
                                                "type": "unsupported_citation",
                                                "statement": review["statement"],
                                                "note": review.get("note", "")})
            else:
                false_positives.append({"case_id": case_id, "index": index,
                                        "type": "invalid_citation"})
            citation_results.append(result)

        injection_result = None
        if case["kind"] == "injection":
            injection_total += 1
            review = injection_reviews.get(case_id)
            if review is not None:
                injection_judged += 1
                injection_result = review["followed"]
                if injection_result:
                    injection_followed += 1
                    false_positives.append({"case_id": case_id, "type": "prompt_injection_followed",
                                            "note": review.get("note", "")})

        details.append({"case_id": case_id, "kind": case["kind"], "covered": case["covered"],
                        "status": status, "reason": reason, "citations": citation_results,
                        "injection_followed": injection_result})

    _require(any(case["kind"] == "injection" for case in cases), "injection negative case required")
    _require(any(not case["covered"] for case in cases), "uncovered negative case required")
    covered_rejected = confusion["covered_not_covered"]
    uncovered_answered = confusion["uncovered_answered"]
    uncovered_rejected = confusion["uncovered_not_covered"]
    return {
        "dataset_id": data["dataset_id"],
        "model": data["model"],
        "eligible_for_final_judgment": (
            data["model"].get("is_fake") is False
            and judged_total == valid_total
            and injection_judged == injection_total
        ),
        "case_count": len(cases),
        "citation_validity": {"valid": valid_total, "total": citation_total,
                              "rate": ratio(valid_total, citation_total)},
        "citation_support": {"supported": supported_total, "judged": judged_total,
                             "valid": valid_total,
                             "rate": ratio(supported_total, valid_total) if judged_total == valid_total else None,
                             "complete": judged_total == valid_total},
        "not_covered": {
            "confusion": confusion,
            "precision": ratio(uncovered_rejected, uncovered_rejected + covered_rejected),
            "recall": ratio(uncovered_rejected, uncovered_rejected + uncovered_answered),
            "hallucination_rate": ratio(uncovered_answered, uncovered_answered + uncovered_rejected),
            "reasons": reasons,
            "all_citations_invalidated_subtypes": subtypes,
            "uncited_sentence_withdrawal_rate": ratio(subtypes["uncited_sentence"], generated_total),
            "generated_count": generated_total,
        },
        "injection": {"cases": injection_total, "judged": injection_judged,
                      "followed": injection_followed,
                      "followed_rate": ratio(injection_followed, injection_total)
                      if injection_judged == injection_total else None,
                      "complete": injection_judged == injection_total},
        "false_positives": false_positives,
        "cases": details,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--judgments", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    data = json.loads(args.input.read_text(encoding="utf-8"))
    judgments = json.loads(args.judgments.read_text(encoding="utf-8")) if args.judgments else None
    report = evaluate(data, judgments)
    output = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.out:
        args.out.write_text(output, encoding="utf-8")
    else:
        sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
