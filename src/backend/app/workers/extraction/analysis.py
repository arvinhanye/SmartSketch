"""Small-section semantic analysis, without canonicalization or graph writes (ADR-098)."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict
import hashlib
import json

from app.repositories.chunks import StoredChunk
from app.services.ai.client import ModelAuthError, ModelError
from app.services.ai.policy import CallRecordError, ModelUnavailableError
from app.services.fusion.judge import FusionEntity, FusionEvidence
from app.services.fusion.resolution import SemanticDecision, SemanticResolver
from app.services.fusion.recall import RECALL_VERSION, RecallCard, recall_candidates
from app.workers.extraction.types import TaskEntity


class _AmbiguousEvidence(ValueError):
    pass


def _entity(entity: TaskEntity, chunks: Mapping[str, StoredChunk]) -> FusionEntity:
    if not entity.candidates:
        raise ValueError("empty mention")
    evidence = []
    course = entity.candidates[0].source.course_id
    for i, candidate in enumerate(entity.candidates):
        source = candidate.source
        if source.evidence_ambiguous:
            raise _AmbiguousEvidence("unresolved evidence occurrence")
        chunk = chunks.get(source.chunk_id)
        if (source.course_id != course or chunk is None or
            not 0 <= source.evidence_start < source.evidence_end <= len(chunk.text) or
            chunk.text[source.evidence_start:source.evidence_end] != candidate.evidence):
            raise ValueError("invalid evidence")
        # Full original chunk preserves qualifiers around the exact extraction quote.
        evidence.append(FusionEvidence(f"{entity.entity_id}:{i}", course, source.document_id,
                                       source.revision_id, source.chunk_id, chunk.text))
    return FusionEntity(entity.entity_id, course, entity.name, entity.type,
                        entity.candidates[0].definition, tuple(evidence))


def analyze_section(entities: Sequence[TaskEntity], chunks: Mapping[str, StoredChunk], *,
                    resolver: SemanticResolver | None, max_pairs: int) -> dict:
    if type(max_pairs) is not int or max_pairs < 1:
        raise ValueError("max_pairs must be positive")
    ordered = sorted(entities, key=lambda e: e.entity_id)
    if len({e.entity_id for e in ordered}) != len(ordered):
        raise ValueError("duplicate mention ID")
    courses = {c.source.course_id for e in ordered for c in e.candidates}
    if len(courses) > 1:
        raise ValueError("cross-course analysis is forbidden")
    digest_data = dict(entities=[asdict(e) for e in ordered],
                       chunks={key: c.text for key, c in sorted(chunks.items())},
                       model=None if resolver is None else resolver.model,
                       prompt=None if resolver is None else resolver.template.sha256,
                       input_budget=None if resolver is None else resolver.max_input_bytes,
                       output_budget=None if resolver is None else resolver.max_output_tokens,
                       recall_version=RECALL_VERSION, top_k=8,
                       max_pairs=max_pairs)
    digest = hashlib.sha256(json.dumps(digest_data, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    recall = recall_candidates([RecallCard(e.entity_id, e.candidates[0].source.course_id, e.name,
        e.candidates[0].definition) for e in ordered], top_k=8, max_pairs=max_pairs)
    total = recall.total_possible_pairs
    by_id = {e.entity_id: e for e in ordered}
    decisions = []
    if resolver is not None:
        for pair in recall.pairs:
            left, right = by_id[pair.left_id], by_id[pair.right_id]
            try:
                a, b = _entity(left, chunks), _entity(right, chunks)
            except _AmbiguousEvidence:
                decision = SemanticDecision(left.entity_id, right.entity_id, "deferred", code="ambiguous_evidence")
            except ValueError:
                decision = SemanticDecision(left.entity_id, right.entity_id, "failed", code="invalid_evidence")
            else:
                try:
                    decision = resolver.resolve(a, b)
                except (ModelAuthError, ModelUnavailableError, CallRecordError):
                    raise  # task-level policy and auth failures retain existing lifecycle semantics
                except ModelError:
                    decision = SemanticDecision(left.entity_id, right.entity_id, "failed", code="model_error")
            decisions.append(asdict(decision))
    completed = sum(d["status"] == "complete" for d in decisions)
    return dict(analysis_version=2, input_digest=digest, total_pairs=total, recall=asdict(recall),
                examined_pairs=len(decisions), completed_pairs=completed,
                unprocessed_pairs=total - completed, decisions=decisions,
                completion="complete" if completed == total else "partial",
                reason="analysis_disabled" if resolver is None and total else None)
