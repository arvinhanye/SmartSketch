"""Conservative complete-message size; this is not a model tokenizer."""
from app.services.ai.client import ModelRequest


class WindowBudgetError(ValueError):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def rendered_request_size(text: str, max_output_tokens: int) -> int:
    return len(text.encode('utf-8')) + 256 + 4 * max_output_tokens


def check_request_budget(request: ModelRequest, max_input_bytes: int) -> None:
    size = sum(len(m.content.encode('utf-8')) + 256 for m in request.messages)
    if size + 4 * request.max_output_tokens > max_input_bytes:
        raise WindowBudgetError('input_budget')
