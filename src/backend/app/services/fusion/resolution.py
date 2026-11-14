"""Bounded, evidence-addressable semantic analysis. Never writes or merges graph nodes."""
from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Literal

from app.services.ai.client import Message, ModelAuthError, ModelClient, ModelError, ModelOutputError, ModelRequest
from app.services.ai.policy import BudgetExceededError, CallRecordError, ModelUnavailableError
from app.services.ai.prompts import PromptLibrary
from app.services.fusion.judge import FusionEntity, validate_pair

PURPOSE = "resolve_duplicate"
VERSION = 1
Verdict = Literal["SAME", "DIFFERENT", "UNCERTAIN"]


@dataclass(frozen=True)
class SemanticDecision:
    left_id: str
    right_id: str
    status: Literal["complete", "failed", "deferred"]
    verdict: Verdict | None = None
    basis: str | None = None
    reason: str | None = field(default=None, repr=False)
    left_source_ids: tuple[str, ...] = ()
    right_source_ids: tuple[str, ...] = ()
    differences: tuple[str, ...] = field(default=(), repr=False)
    code: str | None = None
    model_calls: int = 0
    model_ids: tuple[str, ...] = ()
    prompt_sha256: str = ""
    prompt_version: int = VERSION


def _card(entity: FusionEntity) -> dict:
    return dict(id=entity.entity_id, course_id=entity.course_id, name=entity.name,
                type=entity.type, definition=entity.definition,
                sources=[dict(source_id=s.source_id, document_id=s.document_id,
                              revision_id=s.revision_id, chunk_id=s.chunk_id, quote=s.quote)
                         for s in entity.evidence])


def _parse(value: object, left: FusionEntity, right: FusionEntity) -> dict | None:
    if not isinstance(value, dict):
        return None
    if value.get("verdict") not in ("SAME", "DIFFERENT", "UNCERTAIN"):
        return None
    if value.get("basis") not in ("material", "model_knowledge", "mixed"):
        return None
    reason, differences = value.get("reason"), value.get("differences")
    if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 500:
        return None
    if (not isinstance(differences, list) or len(differences) > 12 or
        any(not isinstance(s, str) or not 1 <= len(s.strip()) <= 500 for s in differences)):
        return None
    if (value["verdict"] == "SAME" and differences) or (value["verdict"] == "DIFFERENT" and not differences):
        return None
    for key, entity in (("left_source_ids", left), ("right_source_ids", right)):
        refs, allowed = value.get(key), {s.source_id for s in entity.evidence}
        if (not isinstance(refs, list) or not refs or
            any(not isinstance(s, str) or s not in allowed for s in refs) or len(set(refs)) != len(refs)):
            return None
    return dict(verdict=value["verdict"], basis=value["basis"], reason=reason.strip(),
                left_source_ids=tuple(value["left_source_ids"]), right_source_ids=tuple(value["right_source_ids"]),
                differences=tuple(s.strip() for s in differences))


class SemanticResolver:
    def __init__(self, client: ModelClient, *, model: str, max_output_tokens: int = 1024,
                 max_input_bytes: int = 24000, prompts: PromptLibrary | None = None) -> None:
        if not isinstance(client, ModelClient):
            raise TypeError("client must implement ModelClient")
        if not isinstance(model, str) or not model.strip():
            raise ValueError("model must be non-blank")
        for value in (max_output_tokens, max_input_bytes):
            if type(value) is not int or value < 1:
                raise ValueError("limits must be positive integers")
        self.client, self.model = client, model
        self.max_output_tokens, self.max_input_bytes = max_output_tokens, max_input_bytes
        self.template = (prompts or PromptLibrary()).get(PURPOSE, VERSION)

    def resolve(self, left: FusionEntity, right: FusionEntity) -> SemanticDecision:
        validate_pair(left, right)
        data = json.dumps(dict(left=_card(left), right=_card(right)), ensure_ascii=False, sort_keys=True)
        calls, repairs_left = 0, 1
        models: list[str] = []

        def finish(status, code=None, parsed=None):
            return SemanticDecision(left.entity_id, right.entity_id, status, code=code,
                                    model_calls=calls, model_ids=tuple(dict.fromkeys(models)),
                                    prompt_sha256=self.template.sha256, **(parsed or {}))

        first = None
        for phase in ("初次同义判断", "独立差异复核"):
            rendered = self.template.render(dict(phase=phase, pair_json=data)).text
            # Conservative byte ceiling, not a claim about a provider's effective window.
            # Include wrapper overhead and output reservation; never cut evidence silently.
            if len(rendered.encode("utf-8")) + 256 + 4 * self.max_output_tokens > self.max_input_bytes:
                return finish("deferred", "input_budget")
            purpose = PURPOSE
            while True:
                request = ModelRequest(purpose=purpose, model=self.model,
                                       messages=(Message("user", rendered),),
                                       max_output_tokens=self.max_output_tokens, response_format="json")
                calls += 1
                try:
                    result = self.client.complete(request)
                except BudgetExceededError:
                    return finish("deferred", "budget_exceeded")
                except (ModelAuthError, ModelUnavailableError, CallRecordError):
                    raise
                except ModelError:
                    return finish("failed", "model_error")
                models.append(result.model_responded or result.model_requested)
                try:
                    parsed = None if result.finish_reason == "length" else _parse(result.json(), left, right)
                except ModelOutputError:
                    parsed = None
                if parsed is not None:
                    break
                if not repairs_left:
                    return finish("failed", "invalid_output")
                repairs_left -= 1
                purpose = "repair"
            if first is None:
                if parsed["verdict"] != "SAME":
                    return finish("complete", parsed=parsed)
                first = parsed
            elif parsed["verdict"] != "SAME":
                parsed["verdict"] = "UNCERTAIN"
                return finish("complete", "verification_disagreed", parsed)
            else:
                parsed["basis"] = first["basis"] if first["basis"] == parsed["basis"] else "mixed"
                return finish("complete", parsed=parsed)
        raise AssertionError("unreachable resolution state")
