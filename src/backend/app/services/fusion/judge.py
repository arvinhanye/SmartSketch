"""E10: evidence-backed duplicate judgments, without graph writes or candidate selection."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum

from app.services.ai.client import Message, ModelClient, ModelOutputError, ModelRequest, ModelResult
from app.services.ai.entities import DEFINITION_MAX_CHARS, ENTITY_TYPES
from app.services.ai.prompts import PromptLibrary
from app.services.ai.policy import BudgetExceededError

JUDGE_PURPOSE = "judge_duplicate"
JUDGE_VERSION = 2
SUMMARY_PURPOSE = "summarize_definition"
SUMMARY_VERSION = 2


class FusionStatus(StrEnum):
    PROPOSAL = "proposal"
    REVIEW = "review"


class FusionReviewReason(StrEnum):
    NOT_SAME = "not_same"
    INVALID_JUDGMENT = "invalid_judgment"
    INVALID_DEFINITION = "invalid_definition"
    BUDGET_EXCEEDED = "budget_exceeded"


@dataclass(frozen=True, slots=True)
class PromptUse:
    purpose: str
    version: int
    sha256: str
    model_id: str | None


@dataclass(frozen=True, slots=True)
class DuplicateJudgment:
    same: bool | None
    reason: str | None = field(repr=False)
    source_ids: tuple[str, ...]
    review_reason: FusionReviewReason | None
    provenance: PromptUse
    model_calls: int


@dataclass(frozen=True, slots=True)
class FusionDecision:
    left_id: str
    right_id: str
    same: bool | None
    reason: str | None = field(repr=False)
    status: FusionStatus
    review_reason: FusionReviewReason | None
    definition: str | None = field(repr=False)
    source_ids: tuple[str, ...]
    original_sources: tuple[FusionEvidence, ...]
    prompt_uses: tuple[PromptUse, ...]
    model_calls: int

    def __post_init__(self) -> None:
        if self.status is FusionStatus.PROPOSAL and (self.definition is None or not self.source_ids):
            raise ValueError("proposal requires definition and sources")
        if self.status is FusionStatus.REVIEW and self.definition is not None:
            raise ValueError("review cannot contain merged definition")


class _InvalidOutput(Exception):
    pass


class _BudgetAbort(Exception):
    def __init__(self, result: ModelResult | None, calls: int) -> None:
        self.result = result
        self.calls = calls


@dataclass(frozen=True, slots=True)
class FusionEvidence:
    source_id: str
    course_id: str
    document_id: str
    revision_id: str
    chunk_id: str
    quote: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class FusionEntity:
    entity_id: str
    course_id: str
    name: str = field(repr=False)
    type: str
    definition: str = field(repr=False)
    evidence: tuple[FusionEvidence, ...] = ()


def validate_pair(left: FusionEntity, right: FusionEntity) -> None:
    """Reject ambiguous identity, provenance, or content before building a prompt."""
    if not isinstance(left, FusionEntity) or not isinstance(right, FusionEntity):
        raise TypeError("both candidates must be FusionEntity")
    for entity in (left, right):
        if any(not isinstance(value, str) or not value.strip() for value in (entity.entity_id, entity.course_id, entity.name, entity.definition)):
            raise ValueError("candidate fields must be non-blank strings")
        if entity.type not in ENTITY_TYPES:
            raise ValueError("candidate type is outside KnowledgePointType")
        if not isinstance(entity.evidence, tuple) or not entity.evidence:
            raise ValueError("each candidate needs evidence")
    if left.course_id != right.course_id or not left.entity_id < right.entity_id:
        raise ValueError("candidates must share a course and have ordered distinct IDs")
    seen: set[str] = set()
    for entity in (left, right):
        for source in entity.evidence:
            if not isinstance(source, FusionEvidence):
                raise TypeError("evidence must be FusionEvidence")
            if source.course_id != entity.course_id:
                raise ValueError("evidence belongs to a different course")
            if any(not isinstance(value, str) or not value.strip() for value in (
                source.source_id, source.document_id, source.revision_id, source.chunk_id, source.quote
            )):
                raise ValueError("evidence fields must be non-blank strings")
            if source.source_id in seen:
                raise ValueError("source_id must be unique within a pair")
            seen.add(source.source_id)


class FusionJudge:
    def __init__(
        self,
        client: ModelClient,
        *,
        model: str,
        max_output_tokens: int,
        prompts: PromptLibrary | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        if not isinstance(client, ModelClient):
            raise TypeError("client must implement ModelClient")
        if not isinstance(model, str) or not model.strip():
            raise ValueError("model must be non-blank")
        if type(max_output_tokens) is not int or max_output_tokens < 1:
            raise ValueError("max_output_tokens must be a positive int")
        self._client = client
        self._model = model
        self._max_output_tokens = max_output_tokens
        self._prompts = prompts or PromptLibrary()
        self._timeout_seconds = timeout_seconds

    def _request(self, purpose: str, model: str, messages: tuple[Message, ...]) -> ModelRequest:
        return ModelRequest(
            purpose=purpose,
            model=model,
            messages=messages,
            max_output_tokens=self._max_output_tokens,
            response_format="json",
            timeout_seconds=self._timeout_seconds,
        )

    def _call_and_parse(
        self, purpose: str, messages: tuple[Message, ...], parser: Callable[[object], object]
    ) -> tuple[object | None, ModelResult | None, int]:
        """One model call and at most one same-model repair; bad output returns no value."""
        calls = 0
        result: ModelResult | None = None
        for request_purpose in (purpose, "repair"):
            try:
                result = self._client.complete(self._request(request_purpose, result.model_requested if result else self._model, messages))
            except BudgetExceededError:
                raise _BudgetAbort(result, calls) from None
            calls += 1
            try:
                if result.finish_reason == "length":
                    raise _InvalidOutput()
                value = result.json()
                return parser(value), result, calls
            except (ModelOutputError, _InvalidOutput):
                continue
        return None, result, calls

    def judge_duplicate(self, left: FusionEntity, right: FusionEntity) -> DuplicateJudgment:
        validate_pair(left, right)
        template = self._prompts.get(JUDGE_PURPOSE, JUDGE_VERSION)
        def sources(entity: FusionEntity) -> str:
            return json.dumps(
                [{"source_id": item.source_id, "quote": item.quote} for item in entity.evidence],
                ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            )
        rendered = template.render({
            "name_a": left.name, "definition_a": left.definition, "sources_a": sources(left),
            "name_b": right.name, "definition_b": right.definition, "sources_b": sources(right),
        })
        messages = (Message("user", rendered.text),)
        allowed = {item.source_id for item in (*left.evidence, *right.evidence)}

        def parse(value: object) -> tuple[bool, str, tuple[str, ...]]:
            if not isinstance(value, dict) or type(value.get("same")) is not bool:
                raise _InvalidOutput()
            reason = value.get("reason")
            if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 500:
                raise _InvalidOutput()
            raw_ids = value.get("source_ids")
            if (not isinstance(raw_ids, list) or not raw_ids or
                any(not isinstance(item, str) or item not in allowed for item in raw_ids) or
                len(raw_ids) != len(set(raw_ids))):
                raise _InvalidOutput()
            return value["same"], reason.strip(), tuple(sorted(raw_ids))

        try:
            parsed, result, calls = self._call_and_parse(JUDGE_PURPOSE, messages, parse)
        except _BudgetAbort as aborted:
            return DuplicateJudgment(None, None, (), FusionReviewReason.BUDGET_EXCEEDED,
                                     PromptUse(JUDGE_PURPOSE, JUDGE_VERSION, template.sha256,
                                               (aborted.result.model_responded or aborted.result.model_requested)
                                               if aborted.result else None), aborted.calls)
        provenance = PromptUse(JUDGE_PURPOSE, JUDGE_VERSION, template.sha256,
                               (result.model_responded or result.model_requested) if result else None)
        if parsed is None:
            return DuplicateJudgment(None, None, (), FusionReviewReason.INVALID_JUDGMENT, provenance, calls)
        same, reason, ids = parsed
        return DuplicateJudgment(same, reason, ids, None if same else FusionReviewReason.NOT_SAME, provenance, calls)

    def evaluate_pair(self, left: FusionEntity, right: FusionEntity) -> FusionDecision:
        judgment = self.judge_duplicate(left, right)
        originals = (*left.evidence, *right.evidence)

        def review(reason: FusionReviewReason, uses: tuple[PromptUse, ...], calls: int) -> FusionDecision:
            return FusionDecision(left.entity_id, right.entity_id, judgment.same, judgment.reason,
                                  FusionStatus.REVIEW, reason, None, judgment.source_ids, originals, uses, calls)

        uses = (judgment.provenance,)
        if judgment.same is not True:
            return review(judgment.review_reason or FusionReviewReason.INVALID_JUDGMENT, uses, judgment.model_calls)

        template = self._prompts.get(SUMMARY_PURPOSE, SUMMARY_VERSION)
        sources = json.dumps(
            ([{"side": "left", "source_id": source.source_id, "quote": source.quote} for source in left.evidence]
             + [{"side": "right", "source_id": source.source_id, "quote": source.quote} for source in right.evidence]),
            ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        )
        definitions = json.dumps(
            [{"side": "left", "name": left.name, "definition": left.definition},
             {"side": "right", "name": right.name, "definition": right.definition}],
            ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        )
        name = left.name if left.name == right.name else f"{left.name} / {right.name}"
        rendered = template.render({"name": name, "definitions": definitions, "sources": sources})
        messages = (Message("user", rendered.text),)
        left_ids = {item.source_id for item in left.evidence}
        right_ids = {item.source_id for item in right.evidence}
        allowed = left_ids | right_ids

        def parse(value: object) -> tuple[str, tuple[str, ...]]:
            if not isinstance(value, dict):
                raise _InvalidOutput()
            definition = value.get("definition")
            if not isinstance(definition, str) or not 1 <= len(definition.strip()) <= DEFINITION_MAX_CHARS:
                raise _InvalidOutput()
            raw_ids = value.get("source_ids")
            if (not isinstance(raw_ids, list) or not raw_ids or
                any(not isinstance(item, str) or item not in allowed for item in raw_ids) or
                len(raw_ids) != len(set(raw_ids)) or
                not left_ids.intersection(raw_ids) or not right_ids.intersection(raw_ids)):
                raise _InvalidOutput()
            return definition.strip(), tuple(sorted(raw_ids))

        try:
            parsed, result, summary_calls = self._call_and_parse(SUMMARY_PURPOSE, messages, parse)
        except _BudgetAbort as aborted:
            use = PromptUse(SUMMARY_PURPOSE, SUMMARY_VERSION, template.sha256,
                            (aborted.result.model_responded or aborted.result.model_requested)
                            if aborted.result else None)
            return review(FusionReviewReason.BUDGET_EXCEEDED, (*uses, use), judgment.model_calls + aborted.calls)
        use = PromptUse(SUMMARY_PURPOSE, SUMMARY_VERSION, template.sha256,
                        (result.model_responded or result.model_requested) if result else None)
        uses = (*uses, use)
        calls = judgment.model_calls + summary_calls
        if parsed is None:
            return review(FusionReviewReason.INVALID_DEFINITION, uses, calls)
        definition, ids = parsed
        return FusionDecision(left.entity_id, right.entity_id, True, judgment.reason,
                              FusionStatus.PROPOSAL, None, definition, ids, originals, uses, calls)
