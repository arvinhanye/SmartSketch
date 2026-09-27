"""问答领域服务（J 组）：问题改写（J03）、有证据问答生成（J05）等。"""

from app.services.qa.generate import (
    ANSWER_CALL_PURPOSE,
    ANSWER_MAX_OUTPUT_TOKENS,
    ANSWER_PROMPT_PURPOSE,
    ANSWER_PROMPT_VERSION,
    AnswerGeneration,
    AnswerGenerator,
    GenerationError,
    GenerationErrorKind,
    GenerationResult,
    SkippedGeneration,
)
from app.services.qa.rewrite import (
    HistoryTurn,
    QueryRewrite,
    QueryRewriter,
    RewriteReason,
    prepare_history,
    strip_citation_markers,
)

__all__ = [
    "ANSWER_CALL_PURPOSE",
    "ANSWER_MAX_OUTPUT_TOKENS",
    "ANSWER_PROMPT_PURPOSE",
    "ANSWER_PROMPT_VERSION",
    "AnswerGeneration",
    "AnswerGenerator",
    "GenerationError",
    "GenerationErrorKind",
    "GenerationResult",
    "HistoryTurn",
    "QueryRewrite",
    "QueryRewriter",
    "RewriteReason",
    "SkippedGeneration",
    "prepare_history",
    "strip_citation_markers",
]
