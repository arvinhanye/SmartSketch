"""D07：重复页眉页脚清洗（`app.services.parsers.cleanup`）。

输入是 D05 的分页行（`PdfPage` / `PdfLine`），全部在本文件中用代码构造；端到端用例手写
最小 PDF 字节交给 `extract_pdf`，不入库、不使用真实课程资料。

覆盖三类路径：
- 成功：跨页重复的页眉、页脚、页码被删；奇偶页交替页眉；数字变化的页眉（含页码）按同一模式识别；
  保留行带原始物理页码，转 `ParsedDocument` 后定位不变；清洗后位置能映射回原始页、行与原文偏移。
- 边界：正文中重复的句子、与页眉同文但位于正文区的行、只出现一次的页首章节标题、
  次数不足阈值的页首行、页边带外或不是最外侧的行都不删；只有页眉页码的页整页清空但不影响后续页码；
  空白页不计入阈值；两页文档、单页文档；清洗会删光全部行时放弃清洗；关闭清洗时输出与输入等价、
  映射为恒等。
- 失败：非法参数、行与页码不一致、页序倒置、越界偏移均明确报错。
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from app.services.parsers import SourceFormat
from app.services.parsers.cleanup import (
    CleanupOptions,
    CleanupResult,
    LineSpan,
    RemovalReason,
    clean_pages,
)
from app.services.parsers.pdf import PdfExtraction, PdfLine, PdfPage, extract_pdf, to_parsed_document

PAGE_W, PAGE_H = 595.0, 842.0
HEADER_Y = 800.0  # 页眉行底边：位于顶部 10% 页边带内（y0 ≥ 757.8）
FOOTER_Y = 40.0  # 页脚行底边：行顶 50.5 位于底部 10% 页边带内（y1 ≤ 84.2）
BODY_TOP = 740.0  # 正文首行底边：在页边带外
HEADER = "Data Structures Lecture Notes"


# ---------------------------------------------------------------------------
# 构造分页行
# ---------------------------------------------------------------------------


def make_line(page: int, index: int, text: str, y0: float, *, size: float = 10.5) -> PdfLine:
    return PdfLine(
        page=page,
        index=index,
        box=index,
        text=text,
        font_name="SimSun",
        font_size=size,
        bold=False,
        bold_ratio=0.0,
        x0=72.0,
        y0=y0,
        x1=72.0 + 6.0 * len(text),
        y1=round(y0 + size, 2),
    )


def make_page(number: int, rows: list[tuple[str, float]]) -> PdfPage:
    """`rows` 按阅读顺序给出 `(文本, 行底 y0)`。"""
    lines = tuple(make_line(number, i, text, y0) for i, (text, y0) in enumerate(rows))
    return PdfPage(number=number, width=PAGE_W, height=PAGE_H, lines=lines)


def body_rows(*texts: str, top: float = BODY_TOP) -> list[tuple[str, float]]:
    return [(text, top - 20.0 * i) for i, text in enumerate(texts)]


def default_body(p: int) -> list[str]:
    return [f"Body text of page {p}."]


def furnished_page(
    p: int,
    *,
    header: str | None = HEADER,
    footer_number: bool = True,
    body: Callable[[int], list[str]] = default_body,
) -> PdfPage:
    """一页讲义：页眉（可选）、若干正文行、底部阿拉伯数字页码（可选）。"""
    rows: list[tuple[str, float]] = []
    if header is not None:
        rows.append((header, HEADER_Y))
    rows += body_rows(*body(p))
    if footer_number:
        rows.append((str(p), FOOTER_Y))
    return make_page(p, rows)


def book(n: int, **kwargs: object) -> list[PdfPage]:
    return [furnished_page(p, **kwargs) for p in range(1, n + 1)]  # type: ignore[arg-type]


def all_lines(pages: list[PdfPage]) -> tuple[PdfLine, ...]:
    return tuple(line for page in pages for line in page.lines)


def texts(result: CleanupResult) -> list[tuple[int, str]]:
    return [(line.page, line.text) for line in result.lines]


def removed(result: CleanupResult) -> list[tuple[int, str, RemovalReason]]:
    return [(r.line.page, r.line.text, r.reason) for r in result.removed]


def assert_mapping_invariants(result: CleanupResult) -> None:
    """清洗后每个字符都映射回原文中同一个字符，且每个位置都能定位到原始页与行。"""
    for offset, char in enumerate(result.text):
        assert result.original_text[result.to_original(offset)] == char
        assert result.locate(offset).line in result.lines
    for span in result.spans:
        assert result.text[span.start : span.end] == span.line.text
        original_end = span.original_start + len(span.line.text)
        assert result.original_text[span.original_start : original_end] == span.line.text
        assert (span.page, span.index) == (span.line.page, span.line.index)


# ---------------------------------------------------------------------------
# 成功路径
# ---------------------------------------------------------------------------


def test_repeated_header_and_page_numbers_are_removed() -> None:
    result = clean_pages(book(4))

    assert result.applied is True
    assert texts(result) == [(p, f"Body text of page {p}.") for p in range(1, 5)]
    assert removed(result) == [
        item
        for p in range(1, 5)
        for item in ((p, HEADER, RemovalReason.HEADER), (p, str(p), RemovalReason.PAGE_NUMBER))
    ]
    assert result.text == "\n".join(f"Body text of page {p}." for p in range(1, 5))
    assert_mapping_invariants(result)


def test_repeated_footer_text_is_removed_as_footer() -> None:
    pages = [
        make_page(p, body_rows(f"Section {p} content.") + [("Tsinghua University Press", FOOTER_Y)])
        for p in range(1, 4)
    ]
    result = clean_pages(pages)
    assert texts(result) == [(p, f"Section {p} content.") for p in range(1, 4)]
    assert [r.reason for r in result.removed] == [RemovalReason.FOOTER] * 3


def test_kept_lines_keep_original_physical_page_after_page_numbers_are_removed() -> None:
    # 前 2 页是罗马数字页码的前言，正文印刷页码从 1 起：物理第 3 页印着「1」。
    printed = ["i", "ii", "1", "2", "3"]
    pages = [
        make_page(
            p,
            [("Algorithms Handout", HEADER_Y)] + body_rows(f"Paragraph on sheet {p}.") + [(printed[p - 1], FOOTER_Y)],
        )
        for p in range(1, 6)
    ]
    result = clean_pages(pages)

    assert texts(result) == [(p, f"Paragraph on sheet {p}.") for p in range(1, 6)]
    number_removals = [(r.line.page, r.line.text) for r in result.removed if r.reason is RemovalReason.PAGE_NUMBER]
    assert number_removals == [(p, printed[p - 1]) for p in range(1, 6)]

    doc = to_parsed_document(result.lines)
    assert doc.source_format is SourceFormat.PDF
    # 定位用物理页码，而不是被删掉的印刷页码
    assert [(b.locator.page, b.text) for b in doc.blocks] == [(p, f"Paragraph on sheet {p}.") for p in range(1, 6)]
    assert [b.locator.to_source_fields() for b in doc.blocks] == [{"page": p} for p in range(1, 6)]


def test_cleaned_position_maps_back_to_original_page_and_line() -> None:
    result = clean_pages(book(3, body=lambda p: [f"Alpha {p}.", f"Beta {p}."]))
    assert_mapping_invariants(result)

    offset = result.text.index("Beta 3.") + 2
    span = result.locate(offset)
    assert isinstance(span, LineSpan)
    assert (span.page, span.index, span.line.text) == (3, 2, "Beta 3.")
    original = result.to_original(offset)
    assert result.original_text[original - 2 : original + 5] == "Beta 3."

    # 换行分隔符归属前一行；末尾位置归属最后一行，映射到原文中该行之后（被删页码「3」前的换行）
    newline = result.text.index("\n")
    assert result.locate(newline).line.text == "Alpha 1."
    assert result.original_text[result.to_original(newline)] == "\n"
    assert result.locate(len(result.text)).line.text == "Beta 3."
    assert result.to_original(len(result.text)) == len(result.original_text) - len("\n3")


def test_spans_between_reports_lines_and_pages_covered_by_a_cleaned_range() -> None:
    result = clean_pages(book(3, body=lambda p: [f"Alpha {p}.", f"Beta {p}."]))
    start = result.text.index("Beta 1.")
    end = result.text.index("Alpha 3.") + 1
    spans = result.spans_between(start, end)
    assert [(s.page, s.line.text) for s in spans] == [
        (1, "Beta 1."),
        (2, "Alpha 2."),
        (2, "Beta 2."),
        (3, "Alpha 3."),
    ]
    assert result.spans_between(0, 0) == (result.spans[0],)


def test_alternating_odd_even_headers_are_both_removed() -> None:
    pages = [
        make_page(
            p,
            [("Data Structures" if p % 2 == 0 else "Chapter 3 Stacks and Queues", HEADER_Y)]
            + body_rows(f"Stack content {p}."),
        )
        for p in range(1, 7)
    ]
    result = clean_pages(pages)
    assert texts(result) == [(p, f"Stack content {p}.") for p in range(1, 7)]
    assert [r.reason for r in result.removed] == [RemovalReason.HEADER] * 6


def test_header_with_varying_numbers_is_recognised_as_one_pattern() -> None:
    pages = [
        make_page(p, [(f"《数据结构》讲义 2024 第 {p} 页", HEADER_Y)] + body_rows(f"第{p}页的正文内容。"))
        for p in range(1, 4)
    ]
    result = clean_pages(pages)
    assert texts(result) == [(p, f"第{p}页的正文内容。") for p in range(1, 4)]
    assert [r.reason for r in result.removed] == [RemovalReason.HEADER] * 3


@pytest.mark.parametrize(
    "fmt",
    ["{p}", "- {p} -", "— {p} —", "第 {p} 页", "第{p}页 共 9 页", "Page {p}", "Page {p} of 9", "{p} / 9", "p. {p}"],
)
def test_page_number_variants_are_classified_as_page_numbers(fmt: str) -> None:
    pages = [make_page(p, body_rows(f"Content {p}.") + [(fmt.format(p=p), FOOTER_Y)]) for p in range(1, 4)]
    result = clean_pages(pages)
    assert texts(result) == [(p, f"Content {p}.") for p in range(1, 4)]
    assert [r.reason for r in result.removed] == [RemovalReason.PAGE_NUMBER] * 3


def test_fullwidth_digit_page_numbers_are_recognised() -> None:
    fullwidth = ["１", "２", "３"]
    pages = [make_page(p, body_rows(f"Content {p}.") + [(fullwidth[p - 1], FOOTER_Y)]) for p in range(1, 4)]
    result = clean_pages(pages)
    assert [r.reason for r in result.removed] == [RemovalReason.PAGE_NUMBER] * 3


def test_page_left_with_only_furniture_becomes_empty_without_shifting_later_pages() -> None:
    pages = book(4)
    pages[2] = make_page(3, [(HEADER, HEADER_Y), ("3", FOOTER_Y)])  # 章节间只有页眉与页码的页
    result = clean_pages(pages)
    assert texts(result) == [(1, "Body text of page 1."), (2, "Body text of page 2."), (4, "Body text of page 4.")]
    assert [b.locator.page for b in to_parsed_document(result.lines).blocks] == [1, 2, 4]


def test_accepts_extraction_object_and_page_iterables_equally() -> None:
    pages = book(3)
    assert clean_pages(PdfExtraction(pages=tuple(pages))) == clean_pages(pages)
    assert clean_pages(iter(pages)) == clean_pages(pages)


def test_end_to_end_with_generated_pdf() -> None:
    contents = [
        text_op(HEADER, y=800, size=9) + text_op(f"Main content of page {p}.", y=600) + text_op(str(p), x=290, y=40, size=9)
        for p in (1, 2, 3)
    ]
    extraction = extract_pdf(build_pdf(contents))
    result = clean_pages(extraction)

    assert texts(result) == [(p, f"Main content of page {p}.") for p in (1, 2, 3)]
    assert sorted((r.line.page, r.reason.value) for r in result.removed) == sorted(
        (p, reason) for p in (1, 2, 3) for reason in ("header", "page_number")
    )
    doc = to_parsed_document(result.lines)
    assert [(b.locator.page, b.text) for b in doc.blocks] == [(p, f"Main content of page {p}.") for p in (1, 2, 3)]
    assert_mapping_invariants(result)


# ---------------------------------------------------------------------------
# 边界：重复正文不被误删
# ---------------------------------------------------------------------------


def test_sentence_repeated_in_body_of_every_page_is_kept() -> None:
    repeated = "Remember: a stack is last-in, first-out."
    result = clean_pages(book(4, body=lambda p: [f"Intro {p}.", repeated, f"Outro {p}."]))
    assert [t for _, t in texts(result)].count(repeated) == 4
    assert all(r.line.text != repeated for r in result.removed)


def test_header_text_repeated_inside_body_is_kept_there() -> None:
    result = clean_pages(book(4, body=lambda p: [f"Intro {p}.", HEADER] if p == 2 else [f"Intro {p}."]))
    # 页首的 4 次都删，正文区的那一次保留
    assert [(r.line.page, r.line.index) for r in result.removed if r.line.text == HEADER] == [
        (p, 0) for p in range(1, 5)
    ]
    assert (2, HEADER) in texts(result)


def test_chapter_title_at_top_of_single_page_is_kept() -> None:
    pages = book(4, header=None)
    pages[0] = make_page(1, [("Chapter 1 Introduction", HEADER_Y)] + body_rows("Body text of page 1.") + [("1", FOOTER_Y)])
    result = clean_pages(pages)
    assert (1, "Chapter 1 Introduction") in texts(result)
    assert [r.reason for r in result.removed] == [RemovalReason.PAGE_NUMBER] * 4


def test_top_line_repeated_on_fewer_pages_than_threshold_is_kept() -> None:
    pages = book(6, header=None, footer_number=False)
    for p in (2, 3):  # 只在 2 页的页首出现（默认至少 3 页）
        pages[p - 1] = furnished_page(p, header="Running title", footer_number=False)
    result = clean_pages(pages)
    assert result.removed == ()
    assert result.lines == all_lines(pages)


def test_repeated_line_outside_the_edge_band_is_kept() -> None:
    # 正文首行 y0 = 740 < 757.8，在页边带外：即使每页相同也不删
    pages = [make_page(p, body_rows("Definition 2.1 (Stack)", f"Body {p}.")) for p in range(1, 5)]
    assert clean_pages(pages).removed == ()


def test_only_outermost_lines_in_band_are_candidates() -> None:
    # 页边带内堆了 3 行且都跨页重复：只删最靠边的 2 行（默认 edge_lines=2）
    rows = [("Line A", 820.0), ("Line B", 805.0), ("Line C", 790.0)]
    result = clean_pages([make_page(p, rows + body_rows(f"Body {p}.")) for p in range(1, 4)])
    assert {r.line.text for r in result.removed} == {"Line A", "Line B"}
    assert [t for _, t in texts(result)].count("Line C") == 3


def test_edge_ranking_uses_geometry_not_reading_order() -> None:
    # 页眉在阅读顺序中排在正文之后（有些 PDF 最后才绘制页眉），仍按位置识别
    pages = [make_page(p, body_rows(f"Body {p}.") + [("Course Handout", HEADER_Y)]) for p in range(1, 4)]
    result = clean_pages(pages)
    assert texts(result) == [(p, f"Body {p}.") for p in range(1, 4)]


def test_two_page_document_needs_repetition_on_both_pages() -> None:
    result = clean_pages(book(2))
    assert texts(result) == [(1, "Body text of page 1."), (2, "Body text of page 2.")]

    only_first = book(2, header=None, footer_number=False)
    only_first[0] = furnished_page(1, header="Course Handout", footer_number=False)
    assert clean_pages(only_first).removed == ()


def test_single_page_document_is_never_cleaned() -> None:
    pages = book(1)
    result = clean_pages(pages)
    assert result.removed == ()
    assert result.lines == all_lines(pages)


def test_blank_pages_do_not_count_towards_threshold() -> None:
    # 物理 5 页：第 2、5 页空白；有文字的 3 页都带页眉页码，仍达到默认 3 页阈值
    pages = [
        furnished_page(1),
        PdfPage(2, PAGE_W, PAGE_H, ()),
        furnished_page(3),
        furnished_page(4),
        PdfPage(5, PAGE_W, PAGE_H, ()),
    ]
    result = clean_pages(pages)
    assert [page for page, _ in texts(result)] == [1, 3, 4]
    assert len(result.removed) == 6


def test_cleanup_that_would_remove_everything_is_abandoned() -> None:
    pages = [make_page(p, [("Same title", HEADER_Y)]) for p in range(1, 4)]
    result = clean_pages(pages)
    assert result.applied is False
    assert result.removed == ()
    assert result.lines == all_lines(pages)
    assert result.text == result.original_text


# ---------------------------------------------------------------------------
# 关闭清洗
# ---------------------------------------------------------------------------


def test_disabled_cleanup_is_identity() -> None:
    pages = book(4)
    result = clean_pages(pages, CleanupOptions(enabled=False))

    assert result.applied is False
    assert result.removed == ()
    assert result.lines == all_lines(pages)
    assert result.text == result.original_text == "\n".join(line.text for line in all_lines(pages))
    for offset in range(len(result.text) + 1):
        assert result.to_original(offset) == offset
    assert all(span.start == span.original_start for span in result.spans)
    assert_mapping_invariants(result)
    # 与 D05 不清洗的最简路径得到同样的 ParsedDocument
    assert to_parsed_document(result.lines) == to_parsed_document(all_lines(pages))


def test_enabled_and_disabled_differ_on_the_same_input() -> None:
    pages = book(4)
    assert clean_pages(pages).text != clean_pages(pages, CleanupOptions(enabled=False)).text


def test_result_is_immutable() -> None:
    result = clean_pages(book(3))
    with pytest.raises(AttributeError):
        result.text = "x"  # type: ignore[misc]
    assert isinstance(result.lines, tuple) and isinstance(result.removed, tuple) and isinstance(result.spans, tuple)


# ---------------------------------------------------------------------------
# 失败路径
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs",
    [{"header_ratio": 0.0}, {"header_ratio": 0.6}, {"footer_ratio": -0.1}, {"edge_lines": 0}, {"min_pages": 1}],
)
def test_invalid_options_are_rejected(kwargs: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        CleanupOptions(**kwargs)  # type: ignore[arg-type]


def test_line_page_mismatch_is_rejected() -> None:
    bad = PdfPage(number=2, width=PAGE_W, height=PAGE_H, lines=(make_line(1, 0, "Wrong page", 600.0),))
    with pytest.raises(ValueError, match="page"):
        clean_pages([make_page(1, body_rows("ok")), bad])


def test_non_increasing_page_numbers_are_rejected() -> None:
    with pytest.raises(ValueError, match="页"):
        clean_pages([make_page(2, body_rows("a")), make_page(1, body_rows("b"))])


def test_out_of_range_offsets_are_rejected() -> None:
    result = clean_pages(book(3))
    with pytest.raises(IndexError):
        result.locate(-1)
    with pytest.raises(IndexError):
        result.locate(len(result.text) + 1)
    with pytest.raises(IndexError):
        result.to_original(len(result.text) + 1)
    with pytest.raises(ValueError):
        result.spans_between(5, 2)


def test_empty_input_yields_empty_result() -> None:
    result = clean_pages([])
    assert result.lines == () and result.text == "" and result.spans == ()
    with pytest.raises(IndexError):
        result.locate(0)


# ---------------------------------------------------------------------------
# 最小 PDF 生成器（只用标准 14 字体 Helvetica）
# ---------------------------------------------------------------------------


def text_op(text: str, *, x: float = 72, y: float = 700, size: float = 12) -> bytes:
    raw = text.encode("latin-1").replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")
    return b"BT /F1 %g Tf %g %g Td (%s) Tj ET\n" % (size, x, y, raw)


def build_pdf(contents: list[bytes]) -> bytes:
    objects: list[bytes] = [b"", b""]  # 1: Catalog，2: Pages，最后填
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    font = len(objects)
    kids = []
    for content in contents:
        objects.append(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(content), content))
        stream_num = len(objects)
        objects.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] /Resources << /Font << /F1 %d 0 R >> >> "
            b"/Contents %d 0 R >>" % (int(PAGE_W), int(PAGE_H), font, stream_num)
        )
        kids.append(len(objects))
    objects[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objects[1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (b" ".join(b"%d 0 R" % k for k in kids), len(kids))

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for num, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (num, body)
    xref_at = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref_at)
    return bytes(out)
