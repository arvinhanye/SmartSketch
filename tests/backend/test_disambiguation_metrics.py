"""Pair-analysis metrics: abstention and failed checks cannot masquerade as precision."""
import pytest


def test_metrics_count_technical_gaps_and_false_same_in_denominators():
    from evaluation.evaluate_disambiguation import evaluate_decisions
    rows = [
        {"expected": "SAME", "decision": {"status": "complete", "verdict": "SAME"}},
        {"expected": "DIFFERENT", "decision": {"status": "complete", "verdict": "SAME"}},
        {"expected": "SAME", "decision": {"status": "failed", "verdict": None}},
        {"expected": "SAME", "decision": {"status": "complete", "verdict": "UNCERTAIN"}},
        {"expected": "DIFFERENT", "decision": {"status": "complete", "verdict": "DIFFERENT"}},
    ]
    result = evaluate_decisions(rows)
    assert result["same_decision_precision"] == 0.5
    assert result["same_detection_recall"] == pytest.approx(1 / 3)
    assert result["technical_unprocessed"] == 1 and result["uncertain"] == 1
    assert result["false_same"] == 1 and result["total"] == 5


def test_no_same_decisions_does_not_report_perfect_precision():
    from evaluation.evaluate_disambiguation import evaluate_decisions
    assert evaluate_decisions([])["same_decision_precision"] is None


@pytest.mark.parametrize("row", [
    {"expected": "SAME", "decision": {"status": "failed", "verdict": "SAME"}},
    {"expected": "unknown", "decision": {"status": "complete", "verdict": "SAME"}},
    {"expected": "SAME", "decision": {"status": "complete", "verdict": None}},
])
def test_invalid_labels_and_inconsistent_states_are_rejected(row):
    from evaluation.evaluate_disambiguation import evaluate_decisions
    with pytest.raises(ValueError):
        evaluate_decisions([row])
