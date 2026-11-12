"""Internal extraction.candidates responsibilities; public compatibility entry: app.workers.extract_task."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from app.repositories.chunks import (
    StoredChunk,
    _sources_from_json,
    _sources_json,
    get_chunks,
    list_chunks,
    list_task_revisions,
)
from app.repositories.extraction_checkpoints import Checkpoint, read_checkpoints
from app.repositories.sqlite import connect
from app.services.ai.entities import EntityCandidate, EntitySource
from app.services.ai.gleaning import entity_name_key, entity_mention_key
from app.services.ai.relations import RelationCandidate, RelationSource
from app.services.chunk_identity import ChunkIdentity, split_chunk_id, text_sha256
from app.workers.extraction.types import (
    ExtractionCandidates,
    FailedChunk,
    FailedSection,
    OUTPUT_INVALID_CODE,
    TaskEntity,
    _Section,
)

def task_entity_id(task_id: str, name: str) -> str:
    """任务内临时实体 ID：任务 + E06 规范化名称键（NFKC、casefold、去空白）的摘要。"""
    digest = hashlib.sha256(json.dumps([task_id, entity_name_key(name)], ensure_ascii=False).encode("utf-8"))
    return "tent_" + digest.hexdigest()[:32]


def mention_entity_id(task_id: str, candidate: EntityCandidate) -> str:
    """Version 2: stable occurrence ID. Confidence is deliberately not identity."""
    payload = json.dumps([task_id, entity_mention_key(candidate)], ensure_ascii=False, separators=(",", ":"))
    return "ment_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


# ---------------------------------------------------------------- 候选编解码


def _source_json(source: EntitySource | RelationSource) -> dict[str, object]:
    result = {
        "document_id": source.document_id,
        "revision_id": source.revision_id,
        "chunk_id": source.chunk_id,
        "evidence_start": source.evidence_start,
        "evidence_end": source.evidence_end,
        "sources": json.loads(_sources_json(source.sources)),
    }
    if isinstance(source, EntitySource) and source.evidence_ambiguous:
        result["evidence_ambiguous"] = True
    return result


def _source_fields(course_id: str, raw: Mapping[str, object]) -> dict[str, object]:
    return {
        "course_id": course_id,
        "document_id": raw["document_id"],
        "revision_id": raw["revision_id"],
        "chunk_id": raw["chunk_id"],
        "evidence_start": raw["evidence_start"],
        "evidence_end": raw["evidence_end"],
        "sources": _sources_from_json(json.dumps(raw["sources"])),
    }


def _encode_entity(candidate: EntityCandidate) -> dict[str, object]:
    result = {
        "name": candidate.name,
        "type": candidate.type,
        "definition": candidate.definition,
        "evidence": candidate.evidence,
        "confidence": candidate.confidence,
        "source": _source_json(candidate.source),
    }
    if candidate.occurrence_index is not None:
        result["occurrence_index"] = candidate.occurrence_index
    return result


def _decode_entity(course_id: str, raw: Mapping[str, object]) -> EntityCandidate:
    return EntityCandidate(
        name=raw["name"],  # type: ignore[arg-type]
        type=raw["type"],  # type: ignore[arg-type]
        definition=raw["definition"],  # type: ignore[arg-type]
        evidence=raw["evidence"],  # type: ignore[arg-type]
        confidence=raw["confidence"],  # type: ignore[arg-type]
        source=EntitySource(**_source_fields(course_id, raw["source"]),  # type: ignore[arg-type]
                            evidence_ambiguous=raw["source"].get("evidence_ambiguous", False)),
        occurrence_index=raw.get("occurrence_index"),  # type: ignore[arg-type]
    )


def _encode_relation(candidate: RelationCandidate) -> dict[str, object]:
    return {
        "from_id": candidate.from_id,
        "to_id": candidate.to_id,
        "type": candidate.type,
        "evidence": candidate.evidence,
        "confidence": candidate.confidence,
        "source": _source_json(candidate.source),
    }


def _decode_relation(course_id: str, raw: Mapping[str, object]) -> RelationCandidate:
    return RelationCandidate(
        from_id=raw["from_id"],  # type: ignore[arg-type]
        to_id=raw["to_id"],  # type: ignore[arg-type]
        type=raw["type"],  # type: ignore[arg-type]
        evidence=raw["evidence"],  # type: ignore[arg-type]
        confidence=raw["confidence"],  # type: ignore[arg-type]
        source=RelationSource(**_source_fields(course_id, raw["source"])),  # type: ignore[arg-type]
    )


def _chunk_order(chunk_id: str) -> tuple[str, int]:
    return split_chunk_id(chunk_id)


def _identity(chunk: StoredChunk) -> ChunkIdentity:
    return ChunkIdentity(
        course_id=chunk.course_id,
        document_id=chunk.material_id,
        revision_id=chunk.revision_id,
        chunk_id=chunk.chunk_id,
        ordinal=chunk.ordinal,
        text_sha256=text_sha256(chunk.text),
        sources=chunk.sources,
    )


def _task_chunks(sqlite_url: str, course_id: str, task_id: str) -> tuple[StoredChunk, ...]:
    chunks: list[StoredChunk] = []
    for revision in list_task_revisions(sqlite_url, course_id=course_id, task_id=task_id):
        chunks.extend(list_chunks(sqlite_url, course_id=course_id, revision_id=revision.revision_id))
    return tuple(sorted(chunks, key=lambda chunk: (chunk.revision_id, chunk.ordinal)))


def _section_path(titles: Sequence[str]) -> str | None:
    return " > ".join(titles) if titles else None


def _sections(chunks: Iterable[StoredChunk]) -> tuple[_Section, ...]:
    grouped: dict[tuple[str, tuple[str, ...]], list[StoredChunk]] = {}
    for chunk in chunks:
        grouped.setdefault((chunk.revision_id, tuple(chunk.section_titles)), []).append(chunk)
    sections = []
    for (revision_id, titles), members in grouped.items():
        digest = hashlib.sha256(json.dumps([revision_id, list(titles)], ensure_ascii=False).encode("utf-8"))
        members.sort(key=lambda chunk: chunk.ordinal)
        sections.append(
            _Section("sec_" + digest.hexdigest(), (revision_id, members[0].ordinal), _section_path(titles),
                     tuple(members))
        )
    return tuple(sorted(sections, key=lambda section: section.order))


def _group_entities(
    task_id: str, course_id: str, checkpoints: Iterable[Checkpoint]
) -> tuple[TaskEntity, ...]:
    ordered = sorted((c for c in checkpoints if c.status == "done"), key=lambda c: _chunk_order(c.unit_id))
    names: dict[str, tuple[str, str]] = {}
    grouped: dict[str, list[EntityCandidate]] = {}
    for checkpoint in ordered:
        assert checkpoint.result is not None
        version = checkpoint.result.get("entity_identity_version", 1)
        if type(version) is not int or version not in (1, 2):
            raise ValueError("unsupported entity identity version")
        for raw in checkpoint.result["entities"]:  # type: ignore[union-attr]
            candidate = _decode_entity(course_id, raw)
            entity_id = (mention_entity_id(task_id, candidate) if version == 2
                         else task_entity_id(task_id, candidate.name))
            names.setdefault(entity_id, (candidate.name, candidate.type))
            grouped.setdefault(entity_id, []).append(candidate)
    return tuple(
        TaskEntity(entity_id, names[entity_id][0], names[entity_id][1], tuple(candidates))
        for entity_id, candidates in grouped.items()
    )


# ---------------------------------------------------------------- 读取待持久化候选


def load_candidates(sqlite_url: str, *, course_id: str, task_id: str) -> ExtractionCandidates:
    """按课程隔离读出一个任务已结束单元的候选；他课任务得到空结果。"""
    with connect(sqlite_url) as database:
        checkpoints = read_checkpoints(database, course_id=course_id, task_id=task_id)
    chunk_rows = [c for c in checkpoints if c.unit_kind == "chunk"]
    section_rows = [c for c in checkpoints if c.unit_kind == "section"]
    entities = _group_entities(task_id, course_id, chunk_rows)

    failed_ids = sorted((c for c in chunk_rows if c.status == "failed"), key=lambda c: _chunk_order(c.unit_id))
    chunks: dict[str, StoredChunk] = {}
    if failed_ids:
        chunks = {c.chunk_id: c for c in get_chunks(sqlite_url, course_id=course_id,
                                                     chunk_ids=[c.unit_id for c in failed_ids])}
    failed_chunks = []
    for checkpoint in failed_ids:
        chunk = chunks.get(checkpoint.unit_id)
        locator = chunk.sources[0].locator if chunk is not None and chunk.sources else None
        failed_chunks.append(FailedChunk(
            checkpoint.unit_id,
            checkpoint.error_code or OUTPUT_INVALID_CODE,
            None if locator is None else locator.page,
            None if locator is None else locator.section_path,
        ))

    relations: list[tuple[tuple[str, int], RelationCandidate]] = []
    failed_sections = []
    known: dict[str, _Section] = {}
    if any(c.status == "failed" for c in section_rows):
        done = {c.unit_id for c in chunk_rows if c.status == "done"}
        known = {
            section.section_id: section
            for section in _sections(c for c in _task_chunks(sqlite_url, course_id, task_id) if c.chunk_id in done)
        }
    for checkpoint in section_rows:
        if checkpoint.status == "done":
            assert checkpoint.result is not None
            head = checkpoint.result["chunk_ids"][0]  # type: ignore[index]
            for raw in checkpoint.result["relations"]:  # type: ignore[union-attr]
                relations.append((_chunk_order(head), _decode_relation(course_id, raw)))
        else:
            section = known.get(checkpoint.unit_id)
            failed_sections.append(FailedSection(
                checkpoint.unit_id,
                checkpoint.error_code or OUTPUT_INVALID_CODE,
                None if section is None else section.path,
                () if section is None else tuple(chunk.chunk_id for chunk in section.chunks),
            ))
    relations.sort(key=lambda item: item[0])
    failed_sections.sort(key=lambda item: _chunk_order(item.chunk_ids[0]) if item.chunk_ids else ("", 0))
    return ExtractionCandidates(
        entities=entities,
        relations=tuple(candidate for _, candidate in relations),
        failed_chunks=tuple(failed_chunks),
        failed_sections=tuple(failed_sections),
    )
