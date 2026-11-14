"""New occurrence identity must not merge homonyms before semantic analysis."""
from dataclasses import replace
import json

from app.repositories.extraction_checkpoints import Checkpoint
from app.services.ai.entities import EntityCandidate, EntitySource
from app.services.ai.relations import SectionEntity, _render_entities
from app.workers.extraction.candidates import _encode_entity, _group_entities, task_entity_id


def candidate(definition="后进先出的线性结构", *, offset=0, type_="concept"):
    revision = "rev_" + "a" * 64
    source = EntitySource("c", "doc", revision, revision + "-0", offset, offset + 2, ())
    return EntityCandidate("栈", type_, definition, "栈。", 0.9, source)


def checkpoint(*items, version=2):
    result = dict(entities=[_encode_entity(c) for c in items])
    if version is not None:
        result["entity_identity_version"] = version
    return Checkpoint("chunk", items[0].source.chunk_id, "done", 1, None, result)


def test_same_name_different_sense_position_or_type_stays_separate():
    a = candidate()
    items = [a, candidate("运行时调用帧", offset=3), candidate(type_="method")]
    grouped = _group_entities("t", "c", [checkpoint(*items)])
    assert len(grouped) == 3
    assert len({g.entity_id for g in grouped}) == 3
    assert {g.candidates[0].definition for g in grouped} == {"后进先出的线性结构", "运行时调用帧"}


def test_only_same_occurrence_same_content_collapses():
    a = candidate()
    result = _group_entities("t", "c", [checkpoint(a, replace(a, confidence=0.8), candidate(offset=3))])
    assert len(result) == 2
    assert len(result[0].candidates) == 2


def test_occurrence_id_is_stable_and_task_scoped():
    from app.workers.extraction.candidates import mention_entity_id
    a = candidate()
    assert mention_entity_id("t", a) == mention_entity_id("t", replace(a, confidence=0.1))
    assert mention_entity_id("t", a) != mention_entity_id("t2", a)
    assert mention_entity_id("t", a) != mention_entity_id("t", candidate(offset=8))


def test_legacy_checkpoint_keeps_preexisting_relation_endpoint():
    result = _group_entities("t", "c", [checkpoint(candidate(), candidate(offset=3), version=None)])
    assert len(result) == 1 and result[0].entity_id == task_entity_id("t", "栈")


def test_future_identity_version_is_not_silently_interpreted_as_legacy():
    import pytest
    with pytest.raises(ValueError):
        _group_entities("t", "c", [checkpoint(candidate(), version=99)])


def test_relation_input_has_sense_and_qualifiers_for_same_name():
    entities = [SectionEntity("a", "c", "期望", "concept", definition="要求可积", evidence="在可积条件下"),
                SectionEntity("b", "c", "期望", "concept", definition="条件期望", evidence="给定事件 B")]
    rows = json.loads(_render_entities(entities))
    assert rows[0]["definition"] == "要求可积" and rows[1]["definition"] == "条件期望"
    assert rows[0]["evidence"] == "在可积条件下"
    assert "要求可积" not in repr(entities[0])


def test_gleaning_preserves_new_sense_with_same_name_in_mention_mode():
    from app.services.ai.fake import FakeModelClient
    from app.services.ai.entities import EntityExtractor
    from app.services.ai.gleaning import EntityGleaner
    from app.services.chunk_identity import assign_chunk_identities, revision_parser_version
    from app.services.chunking import chunk_blocks, chunking_version
    from app.services.parsers.models import ParsedBlock, RevisionKey, SourceLocator
    text = "栈是一种线性表。栈在此处指调用帧区域。"
    chunks = chunk_blocks([ParsedBlock(0, text, SourceLocator(page=1))])
    identity, = assign_chunk_identities("c", RevisionKey("doc", "sha256:" + "b" * 64,
        revision_parser_version("txt/1", chunking_version())), chunks)
    first = dict(name="栈", type="concept", definition="线性表", evidence="栈是一种线性表")
    other = dict(name="栈", type="concept", definition="调用帧区域", evidence="栈在此处指调用帧区域")
    client = FakeModelClient()
    client.script(json.dumps(dict(entities=[first])), json.dumps(dict(entities=[other])))
    known = EntityExtractor(client, model="m", max_output_tokens=2000).extract(identity, chunks[0].text).candidates
    result = EntityGleaner(client, model="m", max_output_tokens=2000, enabled=True, max_rounds=1).glean(
        identity, chunks[0].text, known, preserve_mentions=True)
    assert len(result.added) == 1 and result.added[0].definition == "调用帧区域"


def _extract_repeated_quote(items):
    from app.services.ai.fake import FakeModelClient
    from app.services.ai.entities import EntityExtractor
    from app.services.chunk_identity import assign_chunk_identities, revision_parser_version
    from app.services.chunking import chunk_blocks, chunking_version
    from app.services.parsers.models import ParsedBlock, RevisionKey, SourceLocator
    text = "栈是一种线性表。这里讨论算法。栈是一种线性表。"
    chunks = chunk_blocks([ParsedBlock(0, text, SourceLocator(page=1))])
    identity, = assign_chunk_identities("c", RevisionKey("doc", "sha256:" + "c" * 64,
        revision_parser_version("txt/1", chunking_version())), chunks)
    client = FakeModelClient(); client.script(json.dumps(dict(entities=items)))
    return EntityExtractor(client, model="m", max_output_tokens=2000).extract(identity, chunks[0].text), chunks[0]


def test_real_extractor_repeated_quote_is_not_assumed_to_be_one_occurrence():
    item = dict(name="栈", type="concept", definition="线性结构", evidence="栈是一种线性表")
    extraction, _ = _extract_repeated_quote([item, item])
    grouped = _group_entities("t", "c", [checkpoint(*extraction.candidates)])
    assert len(grouped) == 2
    assert all(c.source.evidence_ambiguous for c in extraction.candidates)


def test_explicit_verified_occurrence_offset_resolves_repeated_quote():
    text = "栈是一种线性表。这里讨论算法。栈是一种线性表。"
    item = dict(name="栈", type="concept", definition="线性结构", evidence="栈是一种线性表",
                evidence_start=text.rfind("栈是一种线性表"))
    extraction, _ = _extract_repeated_quote([item])
    source = extraction.candidates[0].source
    assert source.evidence_start == text.rfind("栈是一种线性表")
    assert not source.evidence_ambiguous


def test_invalid_explicit_offset_is_rejected_without_guessing_first_match():
    extraction, _ = _extract_repeated_quote([dict(name="栈", type="concept", definition="线性结构",
        evidence="栈是一种线性表", evidence_start=2)])
    assert not extraction.candidates


def test_ambiguous_occurrence_does_not_enter_semantic_same_decision():
    from types import SimpleNamespace
    from app.workers.extraction.analysis import analyze_section
    from app.services.fusion.resolution import SemanticResolver
    from app.services.ai.fake import FakeModelClient
    item = dict(name="栈", type="concept", definition="线性结构", evidence="栈是一种线性表")
    extraction, chunk = _extract_repeated_quote([item, item])
    nodes = _group_entities("t", "c", [checkpoint(*extraction.candidates)])
    client = FakeModelClient()
    result = analyze_section(nodes, {extraction.chunk_id: SimpleNamespace(text=chunk.text)},
                             resolver=SemanticResolver(client, model="m"), max_pairs=1)
    assert result["completion"] == "partial" and result["unprocessed_pairs"] == 1
    assert result["decisions"][0]["code"] == "ambiguous_evidence"
    assert not client.calls
