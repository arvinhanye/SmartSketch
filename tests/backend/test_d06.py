"""D06：PDF 标题判定（`app.services.parsers.pdf_headings`）。

输入是 D05 的 `PdfLine` 序列（字号、粗体占比、坐标、页码、文本框），输出标题列表、章节树，以及带
`section_titles` 的 `ParsedDocument`。行数据全部在本文件中手工构造；另有一个端到端用例在测试里
手写 PDF 字节，不入库、不用真实课程资料。

覆盖三类路径：
- 成功：字号层级、多行标题合并、正文字号的加粗编号标题、跨页标题（续页正文沿用标题、标题本身跨页）、
  无字号层级时退回编号正则、章节树形状、`section_path`、端到端 PDF。
- 边界：行内加粗词、整段加粗正文、整篇正文加粗、段中/段首编号、冒号后的列表、目录引导点、
  字号细微差异、标题在文本框中间、只有标题、D07 删行后的子集。
- 失败：没有任何行时 `no_text`；只有一个大字号标题时不当作字号层级。
"""

from __future__ import annotations

import pytest

from app.services.parsers import (
    DocumentUnreadableError,
    ParsedDocument,
    SourceFormat,
    UnreadableReason,
)
from app.services.parsers import pdf as pdf_mod
from app.services.parsers.pdf import PdfLine
from app.services.parsers.pdf_headings import (
    HEADINGS_VERSION,
    PARSER_VERSION,
    HeadingResult,
    HeadingStrategy,
    PdfHeading,
    SectionNode,
    build_section_tree,
    detect_headings,
    parse_pdf_with_headings,
    to_sectioned_document,
)

BODY = 10.5
LEFT, RIGHT = 72.0, 523.0
TOP = 770.0
LINE_GAP = 16.0

# ---------------------------------------------------------------------------
# 行数据构造
# ---------------------------------------------------------------------------


def ln(text: str, *, size: float = BODY, bold: float = 0.0, full: bool | None = None) -> dict:
    """一行的规格。`bold` 是粗体字符占比；`full` 表示行是否排满到右边距（默认按长度推断）。"""
    return {"text": text, "size": size, "bold": bold, "full": full}


def para(*texts: str, size: float = BODY, bold: float = 0.0) -> list[dict]:
    """一段正文：除最后一行外都排满（模拟自动换行）。"""
    return [ln(t, size=size, bold=bold, full=i < len(texts) - 1) for i, t in enumerate(texts)]


def make(*pages: list[list[dict]]) -> tuple[PdfLine, ...]:
    """`pages` 的每个元素是一页，页内每个元素是一个文本框（行规格列表）。"""
    out: list[PdfLine] = []
    for page_no, boxes in enumerate(pages, start=1):
        index = 0
        y = TOP
        for box_no, box in enumerate(boxes):
            for spec in box:
                full = spec["full"] if spec["full"] is not None else len(spec["text"]) >= 30
                width = len(spec["text"]) * spec["size"] * 0.9
                x1 = RIGHT if full else min(LEFT + width, RIGHT - 60)
                ratio = spec["bold"]
                out.append(
                    PdfLine(
                        page=page_no,
                        index=index,
                        box=box_no,
                        text=spec["text"],
                        font_name="SimHei" if ratio >= 0.5 else "SimSun",
                        font_size=spec["size"],
                        bold=ratio >= 0.5,
                        bold_ratio=ratio,
                        x0=LEFT,
                        y0=round(y - spec["size"], 2),
                        x1=round(x1, 2),
                        y1=round(y, 2),
                    )
                )
                index += 1
                y -= LINE_GAP
            y -= LINE_GAP
    return tuple(out)


BODY_A = para(
    "数据结构是计算机存储和组织数据的方式，研究数据元素之间的逻辑关系、",
    "存储表示以及在这些结构上定义的运算。",
)
BODY_B = para(
    "线性表是由 n 个数据元素组成的有限序列，除首尾元素外每个元素都恰有一个",
    "直接前驱和一个直接后继。",
)
BODY_C = para("栈是只允许在一端进行插入和删除的线性表，遵循后进先出的原则。")


def joined(spec_lines: list[dict]) -> str:
    return "\n".join(s["text"] for s in spec_lines)


def titles(doc: ParsedDocument) -> list[tuple[str, ...]]:
    return [b.locator.section_titles for b in doc.blocks]


def heading_titles(result: HeadingResult) -> list[str]:
    return [h.title for h in result.headings]


def textbook() -> tuple[PdfLine, ...]:
    """两章、三节，章 18pt、节 14pt、正文 10.5pt。"""
    return make(
        [
            [ln("第1章 绪论", size=18, bold=1.0)],
            BODY_A,
            [ln("1.1 基本概念", size=14, bold=1.0)],
            BODY_B,
            [ln("1.2 算法分析", size=14, bold=1.0)],
            BODY_C,
        ],
        [
            [ln("第2章 线性表", size=18, bold=1.0)],
            BODY_B,
            [ln("2.1 顺序表", size=14, bold=1.0)],
            BODY_C,
        ],
    )


# ---------------------------------------------------------------------------
# 版本
# ---------------------------------------------------------------------------


def test_parser_version_extends_d05_version_without_whitespace():
    assert HEADINGS_VERSION == "headings/1"
    assert PARSER_VERSION == f"{pdf_mod.PARSER_VERSION}+{HEADINGS_VERSION}"
    assert not any(ch.isspace() for ch in PARSER_VERSION)
    assert PARSER_VERSION != pdf_mod.PARSER_VERSION


# ---------------------------------------------------------------------------
# 字号层级
# ---------------------------------------------------------------------------


def test_font_size_hierarchy_gives_levels_and_body_size():
    result = detect_headings(textbook())
    assert result.strategy is HeadingStrategy.FONT
    assert result.body_size == BODY
    assert [(h.level, h.title, h.page) for h in result.headings] == [
        (1, "第1章 绪论", 1),
        (2, "1.1 基本概念", 1),
        (2, "1.2 算法分析", 1),
        (1, "第2章 线性表", 2),
        (2, "2.1 顺序表", 2),
    ]


def test_sectioned_document_carries_section_titles_and_original_pages():
    doc = to_sectioned_document(textbook())
    assert isinstance(doc, ParsedDocument)
    assert doc.source_format is SourceFormat.PDF
    assert doc.parser_version == PARSER_VERSION
    assert titles(doc) == [
        ("第1章 绪论",),
        ("第1章 绪论", "1.1 基本概念"),
        ("第1章 绪论", "1.2 算法分析"),
        ("第2章 线性表",),
        ("第2章 线性表", "2.1 顺序表"),
    ]
    assert [b.locator.page for b in doc.blocks] == [1, 1, 1, 2, 2]
    # 标题不成块，块文本只含正文行
    assert [b.text for b in doc.blocks] == [joined(BODY_A), joined(BODY_B), joined(BODY_C), joined(BODY_B), joined(BODY_C)]
    assert doc.blocks[1].locator.to_source_fields() == {
        "page": 1,
        "section_path": "第1章 绪论 > 1.1 基本概念",
    }
    assert all(b.locator.paragraph is None and b.locator.line_start is None for b in doc.blocks)


def test_section_tree_nests_sections_under_chapters():
    result = detect_headings(textbook())
    tree = result.tree
    assert tree == build_section_tree(result.headings)
    assert [(n.title, n.level, n.page) for n in tree] == [("第1章 绪论", 1, 1), ("第2章 线性表", 1, 2)]
    assert [c.title for c in tree[0].children] == ["1.1 基本概念", "1.2 算法分析"]
    assert [c.title for c in tree[1].children] == ["2.1 顺序表"]
    assert all(isinstance(n, SectionNode) and n.children == () for n in tree[0].children)


def test_section_tree_handles_level_skips_and_leading_low_level_headings():
    def h(level: int, title: str) -> PdfHeading:
        return PdfHeading(level=level, title=title, page=1, lines=())

    tree = build_section_tree([h(3, "前言"), h(1, "第1章"), h(3, "1.1.1 细节"), h(2, "1.1"), h(1, "第2章")])
    assert [n.title for n in tree] == ["前言", "第1章", "第2章"]
    assert [c.title for c in tree[1].children] == ["1.1.1 细节", "1.1"]
    assert build_section_tree([]) == ()


def test_multi_line_heading_in_one_box_is_merged():
    lines = make(
        [
            [ln("第3章 栈与队列的", size=18, bold=1.0), ln("基本操作", size=18, bold=1.0)],
            BODY_C,
            [ln("3.1 Stack and", size=14, bold=1.0), ln("Queue", size=14, bold=1.0)],
            BODY_A,
        ]
    )
    result = detect_headings(lines)
    assert heading_titles(result) == ["第3章 栈与队列的基本操作", "3.1 Stack and Queue"]
    assert [len(h.lines) for h in result.headings] == [2, 2]


def test_heading_text_is_normalized():
    lines = make(
        [
            [ln("第1章   A > B", size=18)],
            BODY_A,
            [ln("1.1　小节", size=14)],
            BODY_B,
        ]
    )
    assert heading_titles(detect_headings(lines)) == ["第1章 A ＞ B", "1.1 小节"]


def test_slightly_different_sizes_are_one_level():
    lines = make(
        [
            [ln("第1章 绪论", size=16.0)],
            BODY_A,
            [ln("第2章 线性表", size=16.3)],
            BODY_B,
            [ln("2.1 顺序表", size=13.0)],
            BODY_C,
        ]
    )
    result = detect_headings(lines)
    assert [h.level for h in result.headings] == [1, 1, 2]


def test_bold_ranks_above_regular_at_the_same_size():
    lines = make(
        [
            [ln("第1章 绪论", size=14, bold=1.0)],
            BODY_A,
            [ln("1.1 概念", size=14)],
            BODY_B,
        ]
    )
    assert [h.level for h in detect_headings(lines).headings] == [1, 2]


def test_heading_in_the_middle_of_a_box_splits_the_block():
    lines = make(
        [
            [ln("第1章 绪论", size=18)],
            [*BODY_A, ln("1.1 基本概念", size=14), *BODY_B],
            [ln("1.2 其他", size=14)],
            BODY_C,
        ]
    )
    doc = to_sectioned_document(lines)
    assert titles(doc) == [("第1章 绪论",), ("第1章 绪论", "1.1 基本概念"), ("第1章 绪论", "1.2 其他")]
    assert doc.blocks[0].text == joined(BODY_A)
    assert doc.blocks[1].text == joined(BODY_B)


# ---------------------------------------------------------------------------
# 正文加粗不误判
# ---------------------------------------------------------------------------


def test_bold_words_inside_body_lines_are_not_headings():
    lines = make(
        [
            [ln("第1章 绪论", size=18, bold=1.0)],
            [
                ln("本章的重点是时间复杂度，务必掌握大 O 记号的含义与推导方法，", bold=0.2, full=True),
                ln("这是后续各章的基础。", bold=0.1),
            ],
            [ln("第2章 线性表", size=18, bold=1.0)],
            [ln("关键词", bold=0.3, full=False)],
            BODY_B,
        ]
    )
    assert heading_titles(detect_headings(lines)) == ["第1章 绪论", "第2章 线性表"]


def test_fully_bold_body_paragraphs_and_short_bold_lines_are_not_headings():
    lines = make(
        [
            [ln("第1章 绪论", size=18, bold=1.0)],
            para("注意：算法的正确性必须经过证明，不能只凭几个测试用例就下结论，", "这一点在考试中经常出现。", bold=1.0),
            [ln("重要提示", bold=1.0)],
            BODY_A,
            [ln("第2章 线性表", size=18, bold=1.0)],
            [ln("本节小结", bold=1.0)],
            BODY_B,
        ]
    )
    result = detect_headings(lines)
    assert result.strategy is HeadingStrategy.FONT
    assert heading_titles(result) == ["第1章 绪论", "第2章 线性表"]


def test_whole_document_in_bold_body_font_only_takes_larger_headings():
    def bolded(spec_lines: list[dict]) -> list[dict]:
        return [dict(spec, bold=1.0) for spec in spec_lines]

    lines = make(
        [
            [ln("第1章 绪论", size=18, bold=1.0)],
            bolded(BODY_A + BODY_B),
            [ln("1.1 基本概念", size=14, bold=1.0)],
            bolded(BODY_C),
            [ln("注意事项", bold=1.0)],
            bolded(BODY_A),
        ]
    )
    result = detect_headings(lines)
    assert heading_titles(result) == ["第1章 绪论", "1.1 基本概念"]
    doc = to_sectioned_document(lines)
    assert len(doc.blocks) == 4


def test_bold_numbered_body_size_line_is_lowest_level_heading():
    lines = make(
        [
            [ln("第1章 绪论", size=18, bold=1.0)],
            [ln("1.1 数据结构", size=14, bold=1.0)],
            [ln("1.1.1 逻辑结构", bold=1.0)],
            BODY_A,
            [ln("1.1.2 存储结构", bold=1.0), *BODY_B],
            [ln("1.2 算法", size=14, bold=1.0)],
            BODY_C,
        ]
    )
    result = detect_headings(lines)
    assert [(h.level, h.title) for h in result.headings] == [
        (1, "第1章 绪论"),
        (2, "1.1 数据结构"),
        (3, "1.1.1 逻辑结构"),
        (3, "1.1.2 存储结构"),
        (2, "1.2 算法"),
    ]
    doc = to_sectioned_document(lines)
    assert titles(doc)[1] == ("第1章 绪论", "1.1 数据结构", "1.1.2 存储结构")


def test_partially_bold_or_regular_numbered_body_lines_are_not_headings_when_fonts_give_levels():
    lines = make(
        [
            [ln("第1章 绪论", size=18, bold=1.0)],
            [ln("1.1.1 逻辑结构", bold=0.5)],
            BODY_A,
            [ln("第2章 线性表", size=18, bold=1.0)],
            [ln("（一）顺序存储")],
            BODY_B,
        ]
    )
    assert heading_titles(detect_headings(lines)) == ["第1章 绪论", "第2章 线性表"]


def test_large_font_wrapped_paragraph_is_not_a_heading():
    lines = make(
        [
            [ln("第1章 绪论", size=18, bold=1.0)],
            para(
                "本书面向计算机专业本科二年级学生，假定读者已经学过程序设计基础课程",
                "并能熟练使用一种高级语言编写程序，也具备离散数学的基本知识，",
                "学完本书后可以继续学习算法设计与分析",
                size=14,
            ),
            BODY_A,
            [ln("第2章 线性表", size=18, bold=1.0)],
            para("本章导读：线性表是最简单也最常用的数据结构。", size=14),
            BODY_B,
        ]
    )
    assert heading_titles(detect_headings(lines)) == ["第1章 绪论", "第2章 线性表"]


def test_large_page_numbers_and_symbols_are_not_headings():
    lines = make(
        [
            [ln("第1章 绪论", size=18)],
            BODY_A,
            [ln("12", size=18)],
            [ln("- 3 -", size=14)],
            [ln("第2章 线性表", size=18)],
            BODY_B,
        ]
    )
    assert heading_titles(detect_headings(lines)) == ["第1章 绪论", "第2章 线性表"]


# ---------------------------------------------------------------------------
# 跨页
# ---------------------------------------------------------------------------


def test_heading_at_bottom_of_page_applies_to_body_on_next_page():
    lines = make(
        [
            [ln("第1章 绪论", size=18)],
            BODY_A,
            [ln("1.1 基本概念", size=14)],
        ],
        [BODY_B, BODY_C],
    )
    doc = to_sectioned_document(lines)
    assert [(b.locator.page, b.locator.section_titles) for b in doc.blocks] == [
        (1, ("第1章 绪论",)),
        (2, ("第1章 绪论", "1.1 基本概念")),
        (2, ("第1章 绪论", "1.1 基本概念")),
    ]


def test_heading_split_across_pages_is_merged_and_keeps_first_page():
    lines = make(
        [
            [ln("第1章 绪论", size=18)],
            BODY_A,
            [ln("第2章 线性表的顺序存储与", size=18)],
        ],
        [
            [ln("链式存储", size=18)],
            BODY_B,
        ],
    )
    result = detect_headings(lines)
    assert heading_titles(result) == ["第1章 绪论", "第2章 线性表的顺序存储与链式存储"]
    split = result.headings[1]
    assert split.page == 1
    assert [(line.page, line.index) for line in split.lines] == [(1, 3), (2, 0)]
    doc = to_sectioned_document(lines)
    assert doc.blocks[-1].locator.page == 2
    assert doc.blocks[-1].locator.section_titles == ("第2章 线性表的顺序存储与链式存储",)
    assert all("链式存储" not in b.text for b in doc.blocks)


def test_numbered_heading_at_top_of_next_page_is_not_merged_into_previous_heading():
    lines = make(
        [
            BODY_A,
            [ln("第1章 绪论", size=18)],
        ],
        [
            [ln("第2章 线性表", size=18)],
            BODY_B,
        ],
    )
    assert heading_titles(detect_headings(lines)) == ["第1章 绪论", "第2章 线性表"]


def test_headings_on_non_adjacent_pages_are_not_merged():
    lines = make(
        [BODY_A, [ln("概述部分", size=18)]],
        [BODY_B],
        [[ln("背景介绍", size=18)], BODY_C],
    )
    assert heading_titles(detect_headings(lines)) == ["概述部分", "背景介绍"]
    # 删掉整个中间页（模拟 D07 删行）后，第 1 页与第 3 页仍不相邻，不合并
    subset = tuple(line for line in lines if line.page != 2)
    assert heading_titles(detect_headings(subset)) == ["概述部分", "背景介绍"]


# ---------------------------------------------------------------------------
# 无字号层级时退回编号正则
# ---------------------------------------------------------------------------


def flat_numbered() -> tuple[PdfLine, ...]:
    return make(
        [
            [ln("第1章 绪论")],
            BODY_A,
            [ln("第一节 基本概念")],
            BODY_B,
            [ln("1.1 数据与数据元素")],
            BODY_C,
        ],
        [
            [ln("第2章 线性表")],
            BODY_B,
        ],
    )


def test_without_font_levels_numbering_regex_is_used():
    result = detect_headings(flat_numbered())
    assert result.strategy is HeadingStrategy.NUMBERING
    assert [(h.level, h.title) for h in result.headings] == [
        (1, "第1章 绪论"),
        (2, "第一节 基本概念"),
        (3, "1.1 数据与数据元素"),
        (1, "第2章 线性表"),
    ]
    doc = to_sectioned_document(flat_numbered())
    assert titles(doc) == [
        ("第1章 绪论",),
        ("第1章 绪论", "第一节 基本概念"),
        ("第1章 绪论", "第一节 基本概念", "1.1 数据与数据元素"),
        ("第2章 线性表",),
    ]
    assert [n.title for n in result.tree] == ["第1章 绪论", "第2章 线性表"]


def test_single_large_title_is_not_a_font_hierarchy():
    lines = make(
        [
            [ln("数据结构课程讲义", size=22, bold=1.0)],
            [ln("第1章 绪论")],
            BODY_A,
            [ln("1.1 基本概念")],
            BODY_B,
        ]
    )
    result = detect_headings(lines)
    assert result.strategy is HeadingStrategy.NUMBERING
    assert heading_titles(result) == ["第1章 绪论", "1.1 基本概念"]


def test_numbered_line_continuing_a_paragraph_is_not_a_heading():
    lines = make(
        [
            [ln("第1章 绪论")],
            [
                ln("关于时间复杂度的记号，我们在前面已经给出了定义，其具体推导见", full=True),
                ln("1.2 节中的例题"),
            ],
            [
                ln("1.3 节所述的方法同样适用于空间复杂度的分析，读者可以自行推导", full=True),
                ln("并与书中的结论比较。"),
            ],
            BODY_A,
        ]
    )
    assert heading_titles(detect_headings(lines)) == ["第1章 绪论"]


def test_numbered_items_after_a_colon_are_list_items():
    lines = make(
        [
            [ln("第1章 绪论")],
            [
                ln("栈的基本操作如下：", full=False),
                ln("（一）入栈"),
                ln("（二）出栈"),
            ],
            [ln("（三）栈的应用")],
            BODY_C,
        ]
    )
    result = detect_headings(lines)
    assert [(h.level, h.title) for h in result.headings] == [(1, "第1章 绪论"), (4, "（三）栈的应用")]


def test_numbered_line_after_finished_sentence_in_same_box_is_a_heading():
    lines = make(
        [
            [ln("第1章 绪论")],
            [*para("数据结构研究数据的组织方式。"), ln("1.1 基本概念"), *BODY_B],
        ]
    )
    assert heading_titles(detect_headings(lines)) == ["第1章 绪论", "1.1 基本概念"]


def test_table_of_contents_lines_with_leaders_are_not_headings():
    lines = make(
        [
            [ln("第1章 绪论……………1"), ln("1.1 基本概念........3"), ln("第2章 线性表 · · · · · 9")],
        ],
        [
            [ln("第1章 绪论")],
            BODY_A,
        ],
    )
    result = detect_headings(lines)
    assert [(h.title, h.page) for h in result.headings] == [("第1章 绪论", 2)]


def test_single_level_list_numbers_are_not_headings():
    lines = make([[ln("1. 初始化")], [ln("(1) 入栈")], BODY_A])
    result = detect_headings(lines)
    assert result.strategy is HeadingStrategy.NONE
    assert result.headings == ()


# ---------------------------------------------------------------------------
# 无标题、只有标题、空输入
# ---------------------------------------------------------------------------


def test_document_without_headings_matches_d05_output():
    lines = make([BODY_A, BODY_B], [BODY_C])
    result = detect_headings(lines)
    assert result.strategy is HeadingStrategy.NONE
    assert result.tree == ()
    doc = to_sectioned_document(lines)
    assert doc == pdf_mod.to_parsed_document(lines, PARSER_VERSION)
    assert all(b.locator.to_source_fields() == {"page": b.locator.page} for b in doc.blocks)


def test_heading_only_document_keeps_lines_as_paragraphs():
    lines = make([[ln("第1章 绪论", size=18)], [ln("第2章 线性表", size=18)]])
    assert len(detect_headings(lines).headings) == 2
    doc = to_sectioned_document(lines)
    assert [b.text for b in doc.blocks] == ["第1章 绪论", "第2章 线性表"]
    assert titles(doc) == [(), ()]


def test_empty_input_has_no_headings_and_sectioned_document_is_no_text():
    result = detect_headings([])
    assert result.strategy is HeadingStrategy.NONE
    assert result.headings == ()
    with pytest.raises(DocumentUnreadableError) as exc:
        to_sectioned_document([])
    assert exc.value.reason is UnreadableReason.NO_TEXT


def test_accepts_iterators_and_precomputed_result():
    lines = textbook()
    result = detect_headings(iter(lines))
    assert heading_titles(result) == heading_titles(detect_headings(lines))
    assert to_sectioned_document(iter(lines), result) == to_sectioned_document(lines)


def test_lines_removed_by_cleanup_keep_original_pages():
    lines = textbook()
    kept = tuple(line for line in lines if not (line.page == 1 and line.box == 1))  # 删掉第 1 页第一段
    doc = to_sectioned_document(kept)
    assert titles(doc)[0] == ("第1章 绪论", "1.1 基本概念")
    assert [b.locator.page for b in doc.blocks] == [1, 1, 2, 2]


# ---------------------------------------------------------------------------
# 端到端：手写 PDF 字节 → extract_pdf → 标题判定
# ---------------------------------------------------------------------------


def _pdf(pages: list[list[tuple[str, str, float, float]]]) -> bytes:
    """最小 PDF：每行 (字体键, 文字, 字号, y)。F1=Helvetica，F2=Helvetica-Bold。"""
    fonts = {
        "F1": b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        "F2": b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
    }
    objects: list[bytes] = [b"", b""]  # 1 catalog, 2 pages
    font_ref = {}
    for key, body in fonts.items():
        objects.append(body)
        font_ref[key] = len(objects)
    font_dict = b" ".join(b"/%s %d 0 R" % (k.encode(), n) for k, n in font_ref.items())
    kids = []
    for page in pages:
        content = b"".join(
            b"BT /%s %g Tf 72 %g Td (%s) Tj ET\n" % (font.encode(), size, y, text.encode("latin-1"))
            for font, text, size, y in page
        )
        objects.append(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(content), content))
        content_ref = len(objects)
        objects.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            b"/Resources << /Font << %s >> >> /Contents %d 0 R >>" % (font_dict, content_ref)
        )
        kids.append(len(objects))
    objects[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objects[1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (
        b" ".join(b"%d 0 R" % k for k in kids),
        len(kids),
    )
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for num, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (num, body)
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % off for off in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    return bytes(out)


def test_end_to_end_pdf_bytes_get_section_titles():
    data = _pdf(
        [
            [
                ("F2", "Chapter 1 Introduction", 18, 760),
                ("F1", "Data structures organize data so that it can be used efficiently.", 10, 720),
                ("F1", "This paragraph continues in the same plain body font.", 10, 706),
                ("F2", "1.1 Basic Terms", 14, 670),
                ("F1", "A data element is the basic unit of data.", 10, 640),
            ],
            [
                ("F2", "Chapter 2 Linear Lists", 18, 760),
                ("F1", "A linear list is a finite sequence of elements.", 10, 720),
            ],
        ]
    )
    doc = parse_pdf_with_headings(data)
    assert doc.parser_version == PARSER_VERSION
    assert [(b.locator.page, b.locator.section_titles) for b in doc.blocks] == [
        (1, ("Chapter 1 Introduction",)),
        (1, ("Chapter 1 Introduction", "1.1 Basic Terms")),
        (2, ("Chapter 2 Linear Lists",)),
    ]
    assert all("Chapter" not in b.text for b in doc.blocks)
