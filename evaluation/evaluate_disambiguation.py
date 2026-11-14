"""Evaluate labelled pair analyses; does not measure merged-cluster or human-review quality.

Input: JSON array of {"expected": "SAME" | "DIFFERENT", "decision": {...}}.
Failed/deferred checks stay in recall/coverage denominators. No LLM is called.
"""
from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Iterable, Mapping
import json
from pathlib import Path


def evaluate_decisions(rows: Iterable[Mapping]) -> dict:
    counts = Counter(total=0, same=0, different=0, uncertain=0, technical_unprocessed=0,
                     correct_same=0, false_same=0, expected_same=0)
    for row in rows:
        if not isinstance(row, Mapping) or row.get("expected") not in ("SAME", "DIFFERENT"):
            raise ValueError("each row needs an independent SAME or DIFFERENT label")
        decision = row.get("decision")
        if not isinstance(decision, Mapping):
            raise ValueError("decision must be an object")
        status, verdict = decision.get("status"), decision.get("verdict")
        if status not in ("complete", "failed", "deferred"):
            raise ValueError("invalid decision status")
        if ((status == "complete" and verdict not in ("SAME", "DIFFERENT", "UNCERTAIN")) or
            (status != "complete" and verdict is not None)):
            raise ValueError("verdict contradicts decision status")
        counts["total"] += 1
        counts["expected_same"] += row["expected"] == "SAME"
        if status != "complete":
            counts["technical_unprocessed"] += 1
            continue
        counts[verdict.lower()] += 1
        if verdict == "SAME":
            counts["correct_same" if row["expected"] == "SAME" else "false_same"] += 1
    return dict(counts,
        same_decision_precision=counts["correct_same"] / counts["same"] if counts["same"] else None,
        same_detection_recall=counts["correct_same"] / counts["expected_same"] if counts["expected_same"] else None,
        analysis_coverage=(counts["total"] - counts["technical_unprocessed"]) / counts["total"] if counts["total"] else None)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    rows = json.loads(args.input.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("input must be a JSON array")
    report = json.dumps(evaluate_decisions(rows), ensure_ascii=False, indent=2) + "\n"
    if args.output is None:
        print(report, end="")
    else:
        args.output.write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()
