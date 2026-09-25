"""D03：Markdown AST 解析（markdown-it-py）→ D01 `ParsedDocument`。

覆盖三类路径：
- 成功：自编 fixture 的完整块序列（类型、章节路径、行号）；ATX 与 Setext 标题；标题层级跳跃；
  表格、嵌套列表、围栏/缩进代码块保留为独立块；front matter、HTML 块、引用块、分隔线的处理；
  CRLF/CR 换行与 BOM 不改变行号；块文本等于原文对应行。
- 边界：代码块与引用块中的 `#` 不当标题；`#标题`（无空格）按 CommonMark 不是标题；
  空标题被忽略；标题中的行内标记与半角 `>`；同一路径重复出现时段落号接续；未闭合的 front matter。
- 失败：空文件、只有空白（含全角空格与 BOM）、只有标题/front matter/HTML 注释/分隔线/空代码块
  → `DocumentUnreadableError(no_text)`；非 UTF-8 字节与 NUL 字节 → `corrupted`；非 bytes 输入 → TypeError。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.parsers import (
    BlockKind,
    DocumentUnreadableError,
    ParsedDocument,
    SourceFormat,
    UnreadableReason,
)
from app.services.parsers.markdown import PARSER_VERSION, parse_markdown

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "documents"

P, L, T, C = BlockKind.PARAGRAPH, BlockKind.LIST, BlockKind.TABLE, BlockKind.CODE


def md(text: str) -> ParsedDocument:
    return parse_markdown(text.encode("utf-8"))


def shape(doc: ParsedDocument) -> list[tuple[BlockKind, str, int, int]]:
    """(类型, section_path, line_start, line_end) 序列，便于整体断言。"""
    return [
        (b.kind, b.locator.section_path, b.locator.line_start, b.locator.line_end) for b in doc.blocks
    ]


def source_lines(data: bytes) -> list[str]:
    text = data.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    return text.split("\n")


def assert_blocks_map_back_to_source(doc: ParsedDocument, data: bytes) -> None:
    """来源可回到原文：块文本就是原文第 line_start～line_end 行，首尾不是空行。"""
    lines = source_lines(data)
    for b in doc.blocks:
        loc = b.locator
        assert b.text == "\n".join(lines[loc.line_start - 1 : loc.line_end]), f"块 {b.ordinal}"
        assert lines[loc.line_start - 1].strip(), f"块 {b.ordinal} 以空行开头"
        assert lines[loc.line_end - 1].strip(), f"块 {b.ordinal} 以空行结尾"


# ── 成功路径 ──────────────────────────────────────────────


def test_parser_version_is_declared_and_stamped():
    assert PARSER_VERSION == "markdown/1"
    doc = md("正文。\n")
    assert doc.parser_version == PARSER_VERSION
    assert doc.source_format is SourceFormat.MARKDOWN


def test_fixture_stack_queue_notes_full_block_sequence():
    data = (FIXTURE_DIR / "stack-queue-notes.md").read_bytes()
    doc = parse_markdown(data)
    ch3 = "第3章 栈与队列"
    s31 = f"{ch3} > 3.1 顺序栈"
    assert shape(doc) == [
        (P, "第1段", 1, 1),
        (P, f"{ch3} > 第1段", 5, 6),
        (P, f"{s31} > 第1段", 10, 10),
        (T, f"{s31} > 第2段", 12, 15),
        (L, f"{s31} > 第3段", 17, 18),
        (C, f"{s31} > 第4段", 20, 24),
        (P, f"{ch3} > 3.2 链栈 > 第1段", 28, 28),
        (P, "第4章 队列 > 第1段", 32, 32),
        (P, "第4章 队列 > 4.1 循环队列 > 第1段", 36, 36),
    ]
    assert [b.ordinal for b in doc.blocks] == list(range(9))
    # 代码块里以 # 开头的行保留在代码块文本中，没有变成标题
    assert "# 这一行以井号开头" in doc.blocks[5].text
    assert all("这一行以井号开头" not in t for b in doc.blocks for t in b.locator.section_titles)
    assert all(b.locator.page is None for b in doc.blocks)
    assert_blocks_map_back_to_source(doc, data)


def test_hash_lines_in_fenced_and_indented_code_are_not_headings():
    src = (
        "# 第1章\n"
        "\n"
        "```\n"
        "# 围栏代码中的注释\n"
        "```\n"
        "\n"
        "~~~bash\n"
        "## 波浪线围栏中的注释\n"
        "~~~\n"
        "\n"
        "    # 缩进代码块中的注释\n"
        "    x = 1\n"
        "\n"
        "代码之后的正文。\n"
    )
    doc = md(src)
    assert shape(doc) == [
        (C, "第1章 > 第1段", 3, 5),
        (C, "第1章 > 第2段", 7, 9),
        (C, "第1章 > 第3段", 11, 12),
        (P, "第1章 > 第4段", 14, 14),
    ]
    assert {b.locator.section_titles for b in doc.blocks} == {("第1章",)}
    assert doc.blocks[2].text == "    # 缩进代码块中的注释\n    x = 1"
    assert_blocks_map_back_to_source(doc, src.encode())


def test_setext_headings_build_section_path():
    src = "第1章 绪论\n==========\n\n引言正文。\n\n1.1 背景\n--------\n\n背景正文。\n"
    doc = md(src)
    assert shape(doc) == [
        (P, "第1章 绪论 > 第1段", 4, 4),
        (P, "第1章 绪论 > 1.1 背景 > 第1段", 9, 9),
    ]


def test_heading_level_jumps_keep_only_real_ancestors():
    src = (
        "# 第1章\n\n甲。\n\n"
        "### 1.0.1 跳级小节\n\n乙。\n\n"
        "## 1.1 节\n\n丙。\n\n"
        "#### 1.1.0.1 再跳级\n\n丁。\n\n"
        "# 第2章\n\n戊。\n"
    )
    doc = md(src)
    assert [b.locator.section_titles for b in doc.blocks] == [
        ("第1章",),
        ("第1章", "1.0.1 跳级小节"),
        ("第1章", "1.1 节"),  # 同级以上的 ### 被 ## 关闭
        ("第1章", "1.1 节", "1.1.0.1 再跳级"),
        ("第2章",),
    ]
    assert all(b.locator.paragraph == 1 for b in doc.blocks)


def test_document_starting_with_deep_heading_has_single_level_path():
    doc = md("### 只有三级标题\n\n正文。\n")
    assert doc.blocks[0].locator.section_path == "只有三级标题 > 第1段"


def test_table_is_one_block_with_all_rows():
    src = "# 表\n\n| 操作 | 复杂度 |\n| :--- | ---: |\n| 入栈 | O(1) |\n| 出栈 | O(1) |\n\n表后正文。\n"
    doc = md(src)
    assert shape(doc) == [(T, "表 > 第1段", 3, 6), (P, "表 > 第2段", 8, 8)]
    table = doc.blocks[0].text
    assert table.splitlines() == [
        "| 操作 | 复杂度 |",
        "| :--- | ---: |",
        "| 入栈 | O(1) |",
        "| 出栈 | O(1) |",
    ]


def test_nested_list_is_one_block_covering_all_items():
    src = (
        "# 列表\n"
        "\n"
        "- 线性结构\n"
        "  - 栈\n"
        "    1. 顺序栈\n"
        "    2. 链栈\n"
        "  - 队列\n"
        "- 非线性结构\n"
        "\n"
        "1. 第一步\n"
        "2. 第二步\n"
        "\n"
        "列表后正文。\n"
    )
    doc = md(src)
    assert shape(doc) == [
        (L, "列表 > 第1段", 3, 8),
        (L, "列表 > 第2段", 10, 11),
        (P, "列表 > 第3段", 13, 13),
    ]
    nested = doc.blocks[0].text
    for item in ("线性结构", "  - 栈", "    2. 链栈", "非线性结构"):
        assert item in nested
    assert_blocks_map_back_to_source(doc, src.encode())


def test_loose_list_with_code_and_hash_inside_item_stays_one_list():
    src = "- 第一项\n\n  ```\n  # 列表项内代码\n  ```\n\n- 第二项\n"
    doc = md(src)
    assert shape(doc) == [(L, "第1段", 1, 7)]
    assert "# 列表项内代码" in doc.blocks[0].text


def test_yaml_front_matter_is_skipped_without_shifting_lines():
    src = "---\ntitle: 栈与队列\ntags: [ds]\n---\n\n# 第3章\n\n正文。\n"
    doc = md(src)
    # front matter 不产生块，也不会被误读成 Setext 标题「tags: [ds]」
    assert shape(doc) == [(P, "第3章 > 第1段", 8, 8)]


def test_front_matter_closed_with_dots_is_skipped():
    doc = md("---\ntitle: x\n...\n正文。\n")
    assert shape(doc) == [(P, "第1段", 4, 4)]


def test_unclosed_front_matter_is_parsed_as_plain_markdown():
    doc = md("---\n没有闭合的前言\n")
    assert shape(doc) == [(P, "第1段", 2, 2)]


def test_front_matter_only_recognized_at_first_line():
    src = "正文。\n\n---\n\n后文。\n"
    doc = md(src)
    assert shape(doc) == [(P, "第1段", 1, 1), (P, "第2段", 5, 5)]


def test_html_comment_is_dropped_and_other_html_block_kept_as_paragraph():
    src = "<!-- 编辑备注，不是正文 -->\n\n<div>\n图示说明\n</div>\n\n正文。\n"
    doc = md(src)
    assert shape(doc) == [(P, "第1段", 3, 5), (P, "第2段", 7, 7)]
    assert doc.blocks[0].text == "<div>\n图示说明\n</div>"


def test_blockquote_is_one_paragraph_and_inner_heading_is_not_a_section():
    src = "# 第1章\n\n> # 引用中的标题\n> 引用正文。\n\n引用后正文。\n"
    doc = md(src)
    assert shape(doc) == [(P, "第1章 > 第1段", 3, 4), (P, "第1章 > 第2段", 6, 6)]


def test_thematic_break_is_not_a_block():
    doc = md("甲。\n\n***\n\n乙。\n")
    assert shape(doc) == [(P, "第1段", 1, 1), (P, "第2段", 5, 5)]


def test_heading_text_is_plain_and_normalized():
    src = (
        "# 第 **3** 章 `栈` 与 [队列](#q)\n\n甲。\n\n"
        "## x > 0 的情形 ##\n\n乙。\n\n"
        "## ![图](a.png) 图示\n\n丙。\n"
    )
    doc = md(src)
    assert [b.locator.section_titles for b in doc.blocks] == [
        ("第 3 章 栈 与 队列",),
        ("第 3 章 栈 与 队列", "x ＞ 0 的情形"),
        ("第 3 章 栈 与 队列", "图 图示"),
    ]


def test_empty_heading_is_ignored():
    doc = md("# 第1章\n\n甲。\n\n##\n\n乙。\n")
    assert [b.locator.section_path for b in doc.blocks] == ["第1章 > 第1段", "第1章 > 第2段"]


def test_hash_without_space_is_not_a_heading_per_commonmark():
    doc = md("#不是标题\n")
    assert shape(doc) == [(P, "第1段", 1, 1)]
    assert doc.blocks[0].text == "#不是标题"


def test_repeated_section_path_continues_paragraph_numbering():
    src = "# 第1章\n\n## 小结\n\n甲。\n\n## 1.1 节\n\n乙。\n\n## 小结\n\n丙。\n"
    doc = md(src)
    assert [b.locator.section_path for b in doc.blocks] == [
        "第1章 > 小结 > 第1段",
        "第1章 > 1.1 节 > 第1段",
        "第1章 > 小结 > 第2段",
    ]


@pytest.mark.parametrize("newline", ["\r\n", "\r"])
def test_crlf_and_cr_line_endings_count_physical_lines(newline):
    lf = "# 第1章\n\n甲一。\n甲二。\n\n```\n# 注释\n```\n"
    data = lf.replace("\n", newline).encode("utf-8")
    assert shape(parse_markdown(data)) == shape(md(lf)) == [
        (P, "第1章 > 第1段", 3, 4),
        (C, "第1章 > 第2段", 6, 8),
    ]
    assert "\r" not in "".join(b.text for b in parse_markdown(data).blocks)


def test_utf8_bom_is_ignored():
    data = "﻿# 第1章\n\n正文。\n".encode("utf-8")
    doc = parse_markdown(data)
    assert shape(doc) == [(P, "第1章 > 第1段", 3, 3)]


def test_block_text_keeps_inline_markup_and_indentation_verbatim():
    src = "正文含 **粗体** 与 [链接](#a)。\n  第二行缩进。\n"
    doc = md(src)
    assert doc.blocks[0].text == "正文含 **粗体** 与 [链接](#a)。\n  第二行缩进。"


def test_whitespace_only_paragraph_line_does_not_become_block():
    # U+3000 在 CommonMark 中不是空白，markdown-it 会生成段落，但它没有可提取文本
    doc = md("甲。\n\n　　\n\n乙。\n")
    assert shape(doc) == [(P, "第1段", 1, 1), (P, "第2段", 5, 5)]


def test_mixed_document_satisfies_d01_invariants():
    src = (
        "前言。\n\n"
        "第1章\n===\n\n"
        "- a\n- b\n\n"
        "| h |\n| - |\n| v |\n\n"
        "```\n#x\n```\n\n"
        "> 引用\n\n"
        "## 1.1\n\n"
        "    code\n\n"
        "<p>html</p>\n\n"
        "尾。\n"
    )
    data = src.encode()
    doc = parse_markdown(data)
    assert [b.kind for b in doc.blocks] == [P, L, T, C, P, C, P, P]
    ends = [0] + [b.locator.line_end for b in doc.blocks]
    starts = [b.locator.line_start for b in doc.blocks]
    assert all(s > e for s, e in zip(starts, ends))
    assert_blocks_map_back_to_source(doc, data)


# ── 失败路径：没有可提取文本 ──────────────────────────────


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"   ",
        b"\n\n\t\n",
        "　\n".encode("utf-8"),
        "﻿".encode("utf-8"),
        "﻿ \r\n".encode("utf-8"),
    ],
    ids=["empty", "spaces", "blank-lines", "fullwidth-space", "bom-only", "bom-crlf"],
)
def test_empty_or_whitespace_only_is_no_text(data):
    with pytest.raises(DocumentUnreadableError) as exc:
        parse_markdown(data)
    assert exc.value.reason is UnreadableReason.NO_TEXT


@pytest.mark.parametrize(
    "src",
    [
        "# 第1章\n\n## 1.1 节\n",
        "---\ntitle: 只有前言\n---\n",
        "<!-- 只有注释 -->\n",
        "---\n",
        "```\n```\n",
        "```python\n   \n```\n",
        "[ref]: #anchor\n",
    ],
    ids=["headings-only", "front-matter-only", "html-comment-only", "hr-only", "empty-fence",
         "blank-fence", "link-reference-only"],
)
def test_documents_without_body_text_are_no_text(src):
    with pytest.raises(DocumentUnreadableError) as exc:
        md(src)
    assert exc.value.reason is UnreadableReason.NO_TEXT


def test_empty_fixture_is_no_text():
    with pytest.raises(DocumentUnreadableError) as exc:
        parse_markdown((FIXTURE_DIR / "empty.txt").read_bytes())
    assert exc.value.reason is UnreadableReason.NO_TEXT


# ── 失败路径：编码与输入类型 ──────────────────────────────


def test_gbk_encoded_markdown_is_corrupted():
    data = (FIXTURE_DIR / "stack-queue-notes.md").read_text(encoding="utf-8").encode("gbk")
    with pytest.raises(DocumentUnreadableError) as exc:
        parse_markdown(data)
    assert exc.value.reason is UnreadableReason.CORRUPTED
    assert "UTF-8" in exc.value.detail


def test_truncated_utf8_is_corrupted():
    data = "# 第1章\n\n正文".encode("utf-8")[:-1]
    with pytest.raises(DocumentUnreadableError) as exc:
        parse_markdown(data)
    assert exc.value.reason is UnreadableReason.CORRUPTED


def test_nul_byte_is_corrupted():
    with pytest.raises(DocumentUnreadableError) as exc:
        parse_markdown(b"# title\n\nbody\x00more\n")
    assert exc.value.reason is UnreadableReason.CORRUPTED
    assert "NUL" in exc.value.detail


@pytest.mark.parametrize("value", ["# 字符串不是字节", None, 123])
def test_non_bytes_input_is_type_error(value):
    with pytest.raises(TypeError):
        parse_markdown(value)  # type: ignore[arg-type]


def test_bytearray_and_memoryview_are_accepted():
    data = "正文。\n".encode("utf-8")
    assert shape(parse_markdown(bytearray(data))) == shape(parse_markdown(memoryview(data)))
