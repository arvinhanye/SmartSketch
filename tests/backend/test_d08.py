"""D08: chapter-aware chunking with exact parser-block source offsets."""

from app.services.chunking import chunk_blocks
from app.services.parsers.models import ParsedBlock, SourceLocator


def block(index: int, text: str, chapter: str = "第1章") -> ParsedBlock:
    return ParsedBlock(
        ordinal=index,
        text=text,
        locator=SourceLocator(section_titles=(chapter,), paragraph=index + 1),
    )


def test_empty_input_has_no_chunks():
    assert chunk_blocks([]) == ()


def test_short_blocks_merge_with_path_prefix_and_exact_sources():
    blocks = [block(0, "第一段。"), block(1, "第二段。")]
    chunks = chunk_blocks(blocks)
    assert len(chunks) == 1
    assert chunks[0].ordinal == 0
    assert chunks[0].section_titles == ("第1章",)
    assert chunks[0].text == "第1章 > 第1段\n第一段。\n\n第1章 > 第2段\n第二段。"
    assert [(s.block_ordinal, s.start, s.end, s.locator) for s in chunks[0].sources] == [
        (0, 0, len(blocks[0].text), blocks[0].locator),
        (1, 0, len(blocks[1].text), blocks[1].locator),
    ]


def test_chapter_change_never_mixes_even_if_both_are_short():
    chunks = chunk_blocks([block(0, "甲"), block(1, "乙", "第2章")])
    assert len(chunks) == 2
    assert [c.section_titles for c in chunks] == [("第1章",), ("第2章",)]
    assert "乙" not in chunks[0].text
    assert "甲" not in chunks[1].text
    assert [c.ordinal for c in chunks] == [0, 1]


def test_long_paragraph_hard_splits_with_overlap_and_forward_progress():
    source = block(0, "字" * 3600)
    chunks = chunk_blocks([source])
    assert len(chunks) >= 3
    assert all(0 < len(c.text) <= 1550 for c in chunks)
    assert chunks[0].sources[0].start == 0
    assert chunks[-1].sources[-1].end == len(source.text)
    for previous, current in zip(chunks, chunks[1:]):
        assert 150 <= previous.sources[-1].end - current.sources[0].start <= 250
        assert current.sources[0].start > previous.sources[0].start
    assert all(source.text[s.start:s.end] in c.text for c in chunks for s in c.sources)


def test_sentence_break_preferred_near_target():
    source = block(0, "甲" * 1199 + "。" + "乙" * 1100)
    chunks = chunk_blocks([source])
    assert chunks[0].sources[-1].end == 1200
    assert chunks[0].text.endswith("。")
    assert chunks[1].sources[0].start == 1000


def test_overlap_across_blocks_preserves_offsets_and_each_path():
    blocks = [block(0, "甲" * 1000), block(1, "乙" * 1000)]
    chunks = chunk_blocks(blocks)
    assert len(chunks) == 2
    assert [(s.block_ordinal, s.start, s.end) for s in chunks[0].sources] == [
        (0, 0, 1000), (1, 0, 478)
    ]
    assert chunks[1].sources[0].block_ordinal == 1
    assert chunks[1].sources[0].start == 278
    assert chunks[1].sources[-1].end == 1000
    assert chunks[1].text.startswith("第1章 > 第2段\n")


def test_many_short_paragraphs_count_prefixes_toward_target():
    chunks = chunk_blocks([block(i, "正文" * 10) for i in range(90)])
    assert len(chunks) >= 2
    assert all(len(chunk.text) <= 1600 for chunk in chunks)
    assert [chunk.ordinal for chunk in chunks] == list(range(len(chunks)))


def test_pdf_without_section_path_keeps_page_source():
    source = ParsedBlock(0, "PDF 正文", SourceLocator(page=3))
    chunk, = chunk_blocks([source])
    assert chunk.text == source.text
    assert chunk.sources[0].locator.page == 3
    assert chunk.sources[0].locator.section_path is None


def test_invalid_window_configuration_is_rejected():
    import pytest

    for target, overlap in ((0, 0), (10, -1), (10, 10), (True, 0)):
        with pytest.raises(ValueError):
            chunk_blocks([], target_chars=target, overlap_chars=overlap)
