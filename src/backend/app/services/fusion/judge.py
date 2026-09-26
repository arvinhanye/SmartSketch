"""E10: evidence-backed duplicate judgments, without graph writes or candidate selection."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.services.ai.client import ModelClient
from app.services.ai.entities import ENTITY_TYPES
from app.services.ai.prompts import PromptLibrary


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
    name: str
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
    def __init__(self, client: ModelClient, *, model: str, max_output_tokens: int, prompts: PromptLibrary | None = None) -> None:
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
