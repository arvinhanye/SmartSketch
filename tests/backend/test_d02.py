"""D02：TXT 编码检测与标题解析（`app.services.parsers.txt`）。

覆盖三类路径：
- 成功：UTF-8 / 带 BOM 的 UTF-8 / GBK 三种编码得到同一结果；LF、CRLF、单独 CR 换行的行号一致；
  中文编号标题（第X章、第X节、一、、（一）、1.1、1.1.1）的层级与章节路径；无标题文档按「第N段」定位；
  块文本逐行保留原文，可按行号映射回解码后的源文本。
- 边界：标题紧贴正文、多空行、全角缩进分段、只有标题的文档、重复章节路径的段落接续编号、
  标题中的全角空格与半角 `>`、结尾 Ctrl-Z。
- 失败：空文件、只有空白（含只有 BOM）→ `no_text`；两种编码都解不开、UTF-8 中夹坏字节、
  带 BOM 却不是 UTF-8、含 NUL 的二进制或 UTF-16 → `corrupted`；非 bytes 输入 → `TypeError`；
  以及一组「看起来像编号、但应当是正文」的误判用例。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.services.parsers import (
    BlockKind,
    DocumentUnreadableError,
    ParsedDocument,
    SourceFormat,
    UnreadableReason,
)
from app.services.parsers.txt import PARSER_VERSION, decode_txt, heading_rank, parse_txt

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "documents"
NUMBERED = FIXTURE_DIR / "linear-list-numbered.txt"
PLAIN = FIXTURE_DIR / "sorting-plain.txt"
EMPTY = FIXTURE_DIR / "empty.txt"

NUMBERED_EXPECTED = [
    # (section_path, line_start, line_end, 首行开头)
    ("第1段", 1, 1, "示例数据结构讲义"),
    ("第一章 线性表 > 第1段", 5, 5, "线性表是由 n 个"),
    ("第一章 线性表 > 1.1 顺序表 > 第1段", 9, 10, "顺序表用一组"),
    ("第一章 线性表 > 1.2 单链表 > 第1段", 14, 15, "单链表的每个结点"),
    ("第二章 树 > 二、基本术语 > 第1段", 21, 21, "结点的度"),
    ("第二章 树 > 三、二叉树的遍历 > 第1段", 25, 25, "先序遍历"),
]


def summary(doc: ParsedDocument) -> list[tuple[str | None, int | None, int | None]]:
    return [(b.locator.section_path, b.locator.line_start, b.locator.line_end) for b in doc.blocks]


def paths(doc: ParsedDocument) -> list[str | None]:
    return [b.locator.section_path for b in doc.blocks]


def source_lines(text: str) -> list[str]:
    """解码后源文本的物理行：只认 CRLF、CR、LF 三种换行。"""
    return re.split(r"\r\n|\r|\n", text)


def assert_blocks_map_back(doc: ParsedDocument, text: str) -> None:
    """每块的文本恰为源文本第 line_start..line_end 行按 \\n 连接，块间行号递增不重叠。"""
    lines = source_lines(text.removeprefix("\ufeff"))
    last = 0
    for block in doc.blocks:
        loc = block.locator
        assert loc.line_start > last
        assert block.text == "\n".join(lines[loc.line_start - 1 : loc.line_end])
        last = loc.line_end


# ── 成功路径 ──────────────────────────────────────────────


def test_parser_version_is_declared():
    assert PARSER_VERSION == "txt/1"


def test_numbered_fixture_keeps_line_numbers_and_chinese_section_paths():
    raw = NUMBERED.read_bytes()
    doc = parse_txt(raw)
    assert doc.source_format is SourceFormat.TXT
    assert doc.parser_version == PARSER_VERSION
    assert summary(doc) == [(p, s, e) for p, s, e, _ in NUMBERED_EXPECTED]
    for block, (_, _, _, head) in zip(doc.blocks, NUMBERED_EXPECTED):
        assert block.text.startswith(head)
        assert block.kind is BlockKind.PARAGRAPH
        assert block.locator.page is None
    # 标题本身不成块
    assert all(not b.text.startswith(("第一章", "1.1", "二、")) for b in doc.blocks)
    assert doc.blocks[2].text == (
        "顺序表用一组地址连续的存储单元依次存放线性表的元素。\n按下标访问任一元素的时间复杂度为 O(1)。"
    )
    assert_blocks_map_back(doc, raw.decode("utf-8"))


def test_plain_fixture_without_headings_falls_back_to_paragraph_numbers():
    raw = PLAIN.read_bytes()
    doc = parse_txt(raw)
    assert summary(doc) == [("第1段", 1, 1), ("第2段", 3, 4), ("第3段", 6, 7), ("第4段", 9, 9)]
    assert all(b.locator.section_titles == () for b in doc.blocks)
    assert [b.ordinal for b in doc.blocks] == [0, 1, 2, 3]
    assert doc.blocks[0].locator.to_source_fields() == {"section_path": "第1段"}
    assert_blocks_map_back(doc, raw.decode("utf-8"))


@pytest.mark.parametrize("fixture", [NUMBERED, PLAIN], ids=["numbered", "plain"])
def test_gbk_encoding_gives_same_result_as_utf8(fixture):
    text = fixture.read_text(encoding="utf-8")
    gbk = text.encode("gbk")
    assert decode_txt(gbk) == (text, "gbk")
    assert parse_txt(gbk) == parse_txt(text.encode("utf-8"))


@pytest.mark.parametrize("fixture", [NUMBERED, PLAIN], ids=["numbered", "plain"])
def test_utf8_bom_is_dropped_without_shifting_lines(fixture):
    text = fixture.read_text(encoding="utf-8")
    with_bom = b"\xef\xbb\xbf" + text.encode("utf-8")
    assert decode_txt(with_bom) == (text, "utf-8-sig")
    doc = parse_txt(with_bom)
    assert doc == parse_txt(text.encode("utf-8"))
    assert not doc.blocks[0].text.startswith("\ufeff")


def test_plain_utf8_is_reported_as_utf8():
    assert decode_txt("栈与队列\n".encode("utf-8")) == ("栈与队列\n", "utf-8")


@pytest.mark.parametrize("newline", ["\r\n", "\r"], ids=["crlf", "cr"])
def test_crlf_and_cr_newlines_keep_the_same_line_numbers(newline):
    text = NUMBERED.read_text(encoding="utf-8")
    converted = text.replace("\n", newline)
    for encoding in ("utf-8", "gbk"):
        doc = parse_txt(converted.encode(encoding))
        assert doc == parse_txt(text.encode("utf-8"))
        assert all("\r" not in b.text for b in doc.blocks)


def test_mixed_newlines_count_each_physical_line_once():
    doc = parse_txt("第一段\r\n\r第二段第一行\n第二段第二行\r\n\n第三段".encode())
    assert summary(doc) == [("第1段", 1, 1), ("第2段", 3, 4), ("第3段", 6, 6)]
    assert doc.blocks[1].text == "第二段第一行\n第二段第二行"


def test_only_cr_and_lf_break_lines():
    """换页符、NEL、行/段分隔符不算换行：行号与编辑器按 CR/LF 看到的一致。"""
    text = "甲\f乙\n丙\x85丁\u2028戊\u2029己\v庚\n\n辛"
    doc = parse_txt(text.encode())
    assert summary(doc) == [("第1段", 1, 2), ("第2段", 4, 4)]
    assert doc.blocks[0].text == "甲\f乙\n丙\x85丁\u2028戊\u2029己\v庚"


def test_heading_hierarchy_textbook_style():
    text = "\n".join(
        [
            "第1章 绪论",  # 1
            "",  # 2
            "本章概述。",  # 3
            "",  # 4
            "1.1 数据结构",  # 5
            "数据结构研究数据的组织方式。",  # 6
            "1.1.1 逻辑结构",  # 7
            "逻辑结构描述元素之间的关系。",  # 8
            "1.2 算法",  # 9
            "算法是解决问题的有限步骤。",  # 10
            "第2章 线性表",  # 11
            "线性表是有限序列。",  # 12
        ]
    )
    doc = parse_txt(text.encode())
    assert summary(doc) == [
        ("第1章 绪论 > 第1段", 3, 3),
        ("第1章 绪论 > 1.1 数据结构 > 第1段", 6, 6),
        ("第1章 绪论 > 1.1 数据结构 > 1.1.1 逻辑结构 > 第1段", 8, 8),
        ("第1章 绪论 > 1.2 算法 > 第1段", 10, 10),
        ("第2章 线性表 > 第1段", 12, 12),
    ]


def test_heading_hierarchy_chinese_enumeration_style():
    text = "\n".join(
        [
            "第三讲 栈",  # 1
            "第一节 顺序栈",  # 2
            "一、基本操作",  # 3
            "（一）入栈",  # 4
            "把元素放到栈顶。",  # 5
            "(二) 出栈",  # 6
            "取出栈顶元素。",  # 7
            "二、应用",  # 8
            "括号匹配是栈的典型应用。",  # 9
            "第二节 链栈",  # 10
            "链栈没有栈满问题。",  # 11
        ]
    )
    doc = parse_txt(text.encode())
    assert summary(doc) == [
        ("第三讲 栈 > 第一节 顺序栈 > 一、基本操作 > （一）入栈 > 第1段", 5, 5),
        ("第三讲 栈 > 第一节 顺序栈 > 一、基本操作 > (二) 出栈 > 第1段", 7, 7),
        ("第三讲 栈 > 第一节 顺序栈 > 二、应用 > 第1段", 9, 9),
        ("第三讲 栈 > 第二节 链栈 > 第1段", 11, 11),
    ]


@pytest.mark.parametrize(
    "line",
    [
        "第一章 线性表",
        "第十二章\u3000图",  # 全角空格分隔
        "第3章 栈与队列",
        "第１２章 排序",  # 全角数字
        "第二十讲：散列",
        "第一部分 基础",
        "第五单元 查找",
        "第三章",  # 只有编号
        "第一节 顺序栈",
        "一、基本术语",
        "十一、小结",
        "（三）应用",
        "(四) 练习",
        "1.1 顺序表",
        "2.3.1 二叉树的遍历",
        "3.2顺序栈",  # 数字后直接跟汉字
        "10.12 小结",
        "1.1. 顺序表",
        "1.3 什么是栈？",  # 以问号结尾的问句标题
    ],
)
def test_numbered_lines_are_headings(line):
    assert heading_rank(line) is not None


def test_heading_ranks_follow_the_documented_order():
    assert heading_rank("第一章 线性表") == 1
    assert heading_rank("第一节 顺序表") == 2
    assert heading_rank("1.1 顺序表") == 3
    assert heading_rank("一、基本术语") == 3
    assert heading_rank("1.1.1 逻辑结构") == 4
    assert heading_rank("（一）入栈") == 4
    assert heading_rank("1.1.1.1 细节") == 5


def test_heading_directly_followed_by_body_without_blank_line():
    doc = parse_txt("第一章 绪论\n正文第一行\n正文第二行\n一、概念\n概念正文".encode())
    assert summary(doc) == [
        ("第一章 绪论 > 第1段", 2, 3),
        ("第一章 绪论 > 一、概念 > 第1段", 5, 5),
    ]


def test_multiple_blank_and_whitespace_lines_separate_paragraphs():
    text = "\n\n  \n甲段\n\t\n\u3000\u3000\n\n乙段\n\n\n"
    doc = parse_txt(text.encode())
    assert summary(doc) == [("第1段", 4, 4), ("第2段", 8, 8)]


def test_full_width_indent_starts_a_new_paragraph():
    text = "第一章 绪论\n\u3000\u3000第一段第一行，\n接着写完第一段。\n\u3000\u3000第二段。\n\u3000\u3000第三段。"
    doc = parse_txt(text.encode())
    assert summary(doc) == [
        ("第一章 绪论 > 第1段", 2, 3),
        ("第一章 绪论 > 第2段", 4, 4),
        ("第一章 绪论 > 第3段", 5, 5),
    ]
    # 缩进原样保留在块文本中
    assert doc.blocks[1].text == "\u3000\u3000第二段。"


def test_repeated_section_path_continues_paragraph_numbering():
    text = "第一章 线性表\n一、小结\n甲\n二、例题\n乙\n一、小结\n丙"
    doc = parse_txt(text.encode())
    assert paths(doc) == [
        "第一章 线性表 > 一、小结 > 第1段",
        "第一章 线性表 > 二、例题 > 第1段",
        "第一章 线性表 > 一、小结 > 第2段",
    ]


def test_paragraphs_before_first_heading_have_no_section_titles():
    doc = parse_txt("前言一\n\n前言二\n\n第一章 绪论\n\n正文".encode())
    assert paths(doc) == ["第1段", "第2段", "第一章 绪论 > 第1段"]


def test_heading_text_is_normalized():
    doc = parse_txt("第一章\u3000 线性表  \n\n1.1 a>b 的比较\n\n正文".encode())
    assert doc.blocks[0].locator.section_titles == ("第一章 线性表", "1.1 a＞b 的比较")


def test_heading_only_document_keeps_lines_as_paragraphs():
    """只有标题、没有正文时，不丢弃文本：关闭标题判定，按普通段落输出。"""
    doc = parse_txt("第一章 线性表\n第二章 树\n\n第三章 图".encode())
    assert summary(doc) == [("第1段", 1, 2), ("第2段", 4, 4)]
    assert doc.blocks[0].text == "第一章 线性表\n第二章 树"


def test_trailing_heading_without_body_is_dropped_but_body_is_kept():
    doc = parse_txt("第一章 绪论\n正文\n第二章 树\n".encode())
    assert summary(doc) == [("第一章 绪论 > 第1段", 2, 2)]


def test_trailing_ctrl_z_eof_marker_is_ignored():
    doc = parse_txt("正文。\r\n\x1a".encode())
    assert summary(doc) == [("第1段", 1, 1)]
    assert doc.blocks[0].text == "正文。"


def test_block_text_keeps_edge_whitespace_of_original_lines():
    doc = parse_txt("  缩进的正文  \n第二行\t".encode())
    assert doc.blocks[0].text == "  缩进的正文  \n第二行\t"


def test_mostly_ascii_gbk_text_is_decoded_as_gbk():
    text = "Stack and queue notes. The stack is LIFO.\n栈是后进先出的线性表。\n"
    assert decode_txt(text.encode("gbk")) == (text, "gbk")


# ── 误判边界：像编号但应是正文 ──────────────────────────────


@pytest.mark.parametrize(
    "line",
    [
        "示例数据结构讲义（虚构，仅供解析测试）",  # 无编号
        "栈",  # 无编号的短行
        "第一章讲的是线性表",  # 「章」后没有分隔符
        "一、线性表是由若干元素组成的有限序列。",  # 以句号结尾
        "一、线性表，",  # 以逗号结尾
        "一、例如：",  # 以冒号结尾
        "二、栈只允许在一端插入；队列在两端操作",  # 含分号
        "一、" + "很长的标题" * 9,  # 超过 40 字
        "1. 先比较相邻元素",  # 单级阿拉伯编号视为列表项
        "1、先比较相邻元素",
        "(1) 先比较相邻元素",
        "（1）先比较相邻元素",
        "1.1",  # 只有编号
        "一、",
        "（一）",
        "0.5 秒后超时",  # 首段为 0
        "3.05 倍",  # 后续段有前导零
        "2024.10 版讲义",  # 首段超过两位
        "1.1.1.1.1 过深",  # 超过四级
        "1.1% 的元素",
        "1.1x 加速",
        "第 一 章",  # 编号中间有空格
        "",
        "   ",
    ],
)
def test_lines_that_look_numbered_are_not_headings(line):
    assert heading_rank(line) is None


def test_enumeration_after_colon_stays_in_the_paragraph():
    text = "第一章 线性表\n线性表的存储方式分为两类：\n一、顺序存储\n二、链式存储\n\n下一段。"
    doc = parse_txt(text.encode())
    assert summary(doc) == [("第一章 线性表 > 第1段", 2, 4), ("第一章 线性表 > 第2段", 6, 6)]
    assert doc.blocks[0].text == "线性表的存储方式分为两类：\n一、顺序存储\n二、链式存储"


def test_ascii_colon_also_keeps_enumeration_in_paragraph():
    doc = parse_txt("Steps:\n1.1 compare\n1.2 swap".encode())
    assert summary(doc) == [("第1段", 1, 3)]


# ── 失败路径 ──────────────────────────────────────────────


def assert_unreadable(data: bytes, reason: UnreadableReason) -> DocumentUnreadableError:
    with pytest.raises(DocumentUnreadableError) as info:
        parse_txt(data)
    assert info.value.reason is reason
    return info.value


def test_empty_fixture_is_no_text():
    assert EMPTY.read_bytes() == b""
    assert_unreadable(EMPTY.read_bytes(), UnreadableReason.NO_TEXT)


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"   ",
        b"\n\n\r\n",
        b" \t\r\n\x0c",
        "\u3000\u3000\n".encode("utf-8"),
        "\u3000\u3000\n".encode("gbk"),
        b"\xef\xbb\xbf",  # 只有 BOM
        b"\xef\xbb\xbf \r\n",
        b"\x1a",  # 只有 Ctrl-Z
    ],
    ids=["empty", "spaces", "newlines", "ascii-ws", "fullwidth-utf8", "fullwidth-gbk", "bom", "bom-ws", "ctrl-z"],
)
def test_blank_documents_are_no_text(data):
    assert_unreadable(data, UnreadableReason.NO_TEXT)


@pytest.mark.parametrize(
    "data",
    [
        b"\xff\xfe\xfd\xfc",  # 两种编码都不合法
        b"\x81",  # GBK 双字节被截断
        "栈是线性表".encode("gbk") + b"\xff",
        "abc".encode("utf-16"),  # 带 BOM 的 UTF-16：不在支持范围
        "abc 栈".encode("utf-16-le"),  # 无 BOM 的 UTF-16：解出 NUL
        b"%PDF-1.7\n\x00\x01binary",  # 改了扩展名的二进制
    ],
    ids=["invalid-both", "truncated-gbk", "gbk-trailing-ff", "utf16-bom", "utf16-le", "binary-nul"],
)
def test_undecodable_bytes_are_corrupted(data):
    err = assert_unreadable(data, UnreadableReason.CORRUPTED)
    assert err.detail


def test_damaged_utf8_is_corrupted():
    """UTF-8 正文中夹一个坏字节，或文末截断在多字节字符中间：报 corrupted。"""
    text = PLAIN.read_text(encoding="utf-8")
    raw = text.encode("utf-8")
    cut = raw.index("冒泡".encode())
    damaged = raw[:cut] + b"\x80" + raw[cut:]
    assert_unreadable(damaged, UnreadableReason.CORRUPTED)
    # 截断在多字节字符中间同样如此
    truncated = raw[: raw.index("插入".encode()) + 1]
    assert_unreadable(truncated, UnreadableReason.CORRUPTED)


def test_truncated_utf8_that_happens_to_be_valid_gbk_is_corrupted():
    """截断的 UTF-8 恰好能按 GBK 解码（得到乱码）时，仍按损坏的 UTF-8 报 corrupted。"""
    truncated = NUMBERED.read_bytes()[:14]  # 「示例数据」+ 半个字符
    with pytest.raises(UnicodeDecodeError):
        truncated.decode("utf-8")
    assert truncated.decode("gbk")  # 前提：直接回退 GBK 会得到一串乱码而不报错
    assert_unreadable(truncated, UnreadableReason.CORRUPTED)


def test_bom_declared_utf8_that_does_not_decode_is_corrupted():
    """带 UTF-8 BOM 即声明为 UTF-8，解不开时不再尝试 GBK。"""
    assert_unreadable(b"\xef\xbb\xbf" + "栈是线性表".encode("gbk"), UnreadableReason.CORRUPTED)


def test_decode_txt_raises_the_same_errors():
    with pytest.raises(DocumentUnreadableError) as info:
        decode_txt(b"\xff\xfe\xfd\xfc")
    assert info.value.reason is UnreadableReason.CORRUPTED


@pytest.mark.parametrize("data", ["文本", None, 1])
def test_non_bytes_input_is_rejected(data):
    with pytest.raises(TypeError):
        parse_txt(data)  # type: ignore[arg-type]
