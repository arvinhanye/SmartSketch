"""Bounded requests must cover source characters and cross-table entity pairs."""
from dataclasses import replace
from itertools import combinations

import pytest

from app.services.ai.entities import EntityExtractor
from app.services.ai.fake import FakeModelClient
from app.services.ai.relations import RelationExtractor, SectionEntity, SourceChunk
from app.services.chunk_identity import ChunkIdentity, text_sha256
from app.services.chunking import ChunkSource
from app.services.parsers.models import SourceLocator


def source(text, index=0):
    revision = 'rev_' + 'a' * 64
    return SourceChunk(ChunkIdentity('c', 'd', revision, f'{revision}-{index}', index,
        text_sha256(text), (ChunkSource(index, 0, len(text), SourceLocator(page=index+7)),)), text)


def policy(**kwargs):
    from app.services.ai.extraction_windows import WindowPolicy
    return WindowPolicy(**({'max_input_bytes':5000, 'overlap_chars':64, 'max_windows':64} | kwargs))


def test_long_unicode_windows_cover_all_original_characters_with_overlap():
    from app.services.ai.extraction_windows import entity_windows
    chunk = source('开头🙂' + '甲乙丙丁' * 2500 + '中间限定条件' + '😀汉字' * 2500 + '尾部否定')
    extractor = EntityExtractor(FakeModelClient(), model='m', max_output_tokens=32)
    windows = entity_windows(extractor, chunk, policy())
    assert len(windows) > 2
    assert windows[0].start == 0 and windows[-1].end == len(chunk.text)
    assert all(b.start <= a.end - 64 for a, b in zip(windows, windows[1:]))
    assert all(w.chunk == chunk and w.sliced.text == chunk.text[w.start:w.end] for w in windows)
    assert all(w.sliced.identity.chunk_id == chunk.identity.chunk_id for w in windows)
    assert all(len(extractor.prompt().render({'chunk_text': w.sliced.text}).text.encode()) + 256 + 128 <= 5000
               for w in windows)


def test_short_source_keeps_one_whole_request():
    from app.services.ai.extraction_windows import entity_windows, relation_windows
    chunk = source('散列表也称哈希表。')
    client = FakeModelClient()
    e = EntityExtractor(client, model='m', max_output_tokens=32)
    r = RelationExtractor(client, model='m', max_output_tokens=32)
    nodes = (SectionEntity('a', 'c', '散列表', 'concept'), SectionEntity('b', 'c', '哈希表', 'concept'))
    windows = entity_windows(e, chunk, policy())
    assert [(w.start, w.end) for w in windows] == [(0, len(chunk.text))]
    rel = relation_windows(r, nodes, (chunk,), policy())
    assert len(rel) == 1 and rel[0].entities == nodes
    assert rel[0].sources[0].sliced == chunk
    assert not client.calls


def test_large_entity_table_preserves_every_cross_pair_and_all_source_windows():
    from app.services.ai.extraction_windows import relation_windows
    chunks = (source('第一段。' * 100), source('第二段。' * 100, 1))
    nodes = tuple(SectionEntity(str(i), 'c', '概念' + str(i), 'concept', '条件' * 150) for i in range(4))
    r = RelationExtractor(FakeModelClient(), model='m', max_output_tokens=32)
    windows = relation_windows(r, nodes, chunks, policy())
    assert len(windows) > 1
    for a, b in combinations(nodes, 2):
        matching = [w for w in windows if a in w.entities and b in w.entities]
        for chunk in chunks:
            spans = sorted((s.start, s.end) for w in matching for s in w.sources if s.chunk == chunk)
            cursor = 0
            for start, end in spans:
                assert start <= cursor
                cursor = max(cursor, end)
            assert cursor == len(chunk.text)
    assert all(r.request_size(w.entities, tuple(s.sliced for s in w.sources)) <= 5000 for w in windows)


def test_window_and_huge_table_caps_fail_before_any_model_call():
    from app.services.ai.extraction_windows import WindowBudgetError, WindowPolicy, entity_windows, relation_windows
    client = FakeModelClient()
    e = EntityExtractor(client, model='m', max_output_tokens=32)
    r = RelationExtractor(client, model='m', max_output_tokens=32)
    p = WindowPolicy(max_input_bytes=5000, overlap_chars=64, max_windows=2)
    with pytest.raises(WindowBudgetError, match='window_limit'):
        entity_windows(e, source('甲' * 20000), p)
    nodes = tuple(SectionEntity(str(i), 'c', '概念', 'concept', '条件' * 150) for i in range(2000))
    with pytest.raises(WindowBudgetError, match='window_limit'):
        relation_windows(r, nodes, (source('原文'),), p)
    assert not client.calls


def test_complete_entity_card_or_output_reservation_cannot_be_silently_cut():
    from app.services.ai.extraction_windows import WindowBudgetError, entity_windows, relation_windows
    client = FakeModelClient()
    e = EntityExtractor(client, model='m', max_output_tokens=2000)
    with pytest.raises(WindowBudgetError, match='input_budget'):
        entity_windows(e, source('短文'), policy())
    r = RelationExtractor(client, model='m', max_output_tokens=32)
    nodes = (SectionEntity('a', 'c', '甲', 'concept', '限定' * 10000), SectionEntity('b', 'c', '乙', 'concept'))
    with pytest.raises(WindowBudgetError, match='input_budget'):
        relation_windows(r, nodes, (source('甲乙相关'),), policy())
    assert not client.calls


def test_source_hash_and_course_mismatch_are_rejected_before_planning():
    from app.services.ai.extraction_windows import entity_windows, relation_windows
    chunk = source('材料')
    e = EntityExtractor(FakeModelClient(), model='m', max_output_tokens=32)
    with pytest.raises(ValueError):
        entity_windows(e, replace(chunk, text='篡改'), policy())
    r = RelationExtractor(FakeModelClient(), model='m', max_output_tokens=32)
    with pytest.raises(ValueError):
        relation_windows(r, (SectionEntity('a','c','甲','concept'),SectionEntity('b','other','乙','concept')), (chunk,), policy())
