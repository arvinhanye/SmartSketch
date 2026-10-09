"""Formal-mode failure path M11/C2: an oversize question must be refused as input (422), not surface as 503.

A 200,000-character question used to reach the embedding provider, which rejected it, and the user saw
``LLM_UNAVAILABLE`` ("model temporarily unavailable"). The contract now caps ``ChatRequest.question``.
"""
import pytest
from pydantic import ValidationError

from app.schemas.contracts import ChatRequest

QUESTION_MAX_LENGTH = 2000


def test_question_at_the_limit_is_accepted() -> None:
    assert ChatRequest(question="栈" * QUESTION_MAX_LENGTH).question


@pytest.mark.parametrize("question", ["", "栈" * (QUESTION_MAX_LENGTH + 1), "x" * 200_000],
                         ids=["empty", "one-over-limit", "200k-chars"])
def test_empty_or_oversize_question_is_rejected_before_any_model_call(question: str) -> None:
    with pytest.raises(ValidationError):
        ChatRequest(question=question)
