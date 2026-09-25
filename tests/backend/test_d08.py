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


def test_ascii_period_is_a_sentence_boundary_near_target():
    source = block(0, "A" * 24 + ". " + "B" * 40)
    chunks = chunk_blocks([source], target_chars=40, overlap_chars=5)
    assert chunks[0].sources[-1].end == 25
    assert chunks[0].text.endswith(".")


def test_decimal_point_is_not_treated_as_sentence_end():
    source = block(0, "A" * 22 + "3.14" + "B" * 40)
    chunks = chunk_blocks([source], target_chars=40, overlap_chars=5)
    assert chunks[0].sources[-1].end == 30


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


def test_long_section_path_bounds_rendered_chunks_without_losing_source_text():
    target = 1500
    prefix_chars = 700  # section_path plus its presentation newline
    suffix = " > 第1段"
    title = "章" * (prefix_chars - 1 - len(suffix))
    sources = (
        ParsedBlock(
            0,
            "正文" * 2500,
            SourceLocator(section_titles=(title,), paragraph=1),
        ),
        ParsedBlock(
            1,
            "尾文" * 1000,
            SourceLocator(section_titles=(title + "乙",), paragraph=2),
        ),
    )
    chunks = chunk_blocks(sources, target_chars=target, overlap_chars=200)

    assert all(len(chunk.text) <= target for chunk in chunks)
    covered_until = {source.ordinal: 0 for source in sources}
    for chunk in chunks:
        assert len({item.block_ordinal for item in chunk.sources}) == 1
        for item in chunk.sources:
            assert item.start <= covered_until[item.block_ordinal]
            covered_until[item.block_ordinal] = max(covered_until[item.block_ordinal], item.end)
    assert covered_until == {source.ordinal: len(source.text) for source in sources}


def test_path_prefix_that_fills_or_exceeds_target_is_rejected():
    import pytest

    target = 40
    suffix = " > 第1段"
    for prefix_chars in (target, target + 1):
        title = "章" * (prefix_chars - 1 - len(suffix))
        source = ParsedBlock(
            0,
            "正文",
            SourceLocator(section_titles=(title,), paragraph=1),
        )
        assert len(source.locator.section_path + "\n") == prefix_chars
        with pytest.raises(ValueError, match="section_path prefix leaves no room"):
            chunk_blocks([source], target_chars=target, overlap_chars=5)


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
