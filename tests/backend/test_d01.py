"""D01：解析输出模型（ParsedBlock / SourceLocator / ParsedDocument）与自编 fixture。

覆盖三类路径：
- 成功：四种格式各自的合法定位、章节路径与段落兜底的渲染、来源字段只输出存在的键。
- 边界：最小合法值（页码 1、段落 1、块序号 0、单行块）、首尾空白原样保留、单块文档。
- 失败：空文本、两种定位都缺、页码 < 1、块序号为负、无页码格式带页码、PDF 缺页码、
  段落编号断档、行号重叠、fixture 目录混入二进制或未声明自编。
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path

import pytest

from app.services.parsers import (
    SECTION_SEPARATOR,
    BlockKind,
    DocumentUnreadableError,
    ParsedBlock,
    ParsedDocument,
    ParseModelError,
    RevisionKey,
    SourceFormat,
    SourceLocator,
    UnreadableReason,
    normalize_heading,
)
from app.services import parsers as parsers_pkg
from app.services.file_storage import SUPPORTED_FORMATS, FileStorage

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "documents"
SAMPLE_HASH = "sha256:ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def txt_block(ordinal: int, text: str, paragraph: int, lines: tuple[int, int], titles=()):
    return ParsedBlock(
        ordinal=ordinal,
        text=text,
        locator=SourceLocator(
            section_titles=titles, paragraph=paragraph, line_start=lines[0], line_end=lines[1]
        ),
    )


def pdf_block(ordinal: int, text: str, page: int, titles=()):
    return ParsedBlock(ordinal=ordinal, text=text, locator=SourceLocator(page=page, section_titles=titles))


# ── 成功路径 ──────────────────────────────────────────────


def test_pdf_locator_uses_page_and_optional_section():
    only_page = SourceLocator(page=3)
    assert only_page.section_path is None
    assert only_page.to_source_fields() == {"page": 3}

    both = SourceLocator(page=12, section_titles=("第3章 栈与队列", "3.1 顺序栈"))
    assert both.section_path == "第3章 栈与队列 > 3.1 顺序栈"
    assert both.to_source_fields() == {"page": 12, "section_path": "第3章 栈与队列 > 3.1 顺序栈"}


def test_pageless_locator_appends_paragraph_to_heading_path():
    """R02（ArvinHan 决定）：有标题时 section_path =「标题路径 > 第N段」。"""
    loc = SourceLocator(section_titles=("第3章", "3.1 栈"), paragraph=2)
    assert loc.section_path == "第3章" + SECTION_SEPARATOR + "3.1 栈" + SECTION_SEPARATOR + "第2段"
    assert loc.section_path == "第3章 > 3.1 栈 > 第2段"
    # 无页码的来源不带 page 键（不是 null），与 SourceRef 一致
    assert loc.to_source_fields() == {"section_path": "第3章 > 3.1 栈 > 第2段"}


def test_pageless_locator_without_headings_falls_back_to_paragraph():
    loc = SourceLocator(paragraph=2)
    assert loc.section_path == "第2段"
    assert loc.to_source_fields() == {"section_path": "第2段"}


def test_section_titles_are_coerced_to_immutable_tuple():
    loc = SourceLocator(section_titles=["第1章 绪论"], paragraph=1)
    assert loc.section_titles == ("第1章 绪论",)
    with pytest.raises(dataclasses.FrozenInstanceError):
        loc.page = 1  # type: ignore[misc]
    block = ParsedBlock(ordinal=0, text="正文", locator=loc)
    with pytest.raises(dataclasses.FrozenInstanceError):
        block.text = "改写"  # type: ignore[misc]


def test_only_pdf_is_paginated():
    assert SourceFormat.PDF.paginated is True
    assert {f for f in SourceFormat if not f.paginated} == {
        SourceFormat.TXT,
        SourceFormat.MARKDOWN,
        SourceFormat.DOCX,
    }


def test_markdown_document_numbers_paragraphs_per_section():
    ch = ("第3章 栈与队列",)
    sec = ("第3章 栈与队列", "3.1 顺序栈")
    doc = ParsedDocument(
        source_format=SourceFormat.MARKDOWN,
        parser_version="markdown/1",
        blocks=(
            txt_block(0, "本讲义为虚构示例。", 1, (1, 1)),
            txt_block(1, "栈是一种受限的线性表。", 1, (3, 4), ch),
            txt_block(2, "只允许在一端插入和删除。", 2, (6, 6), ch),
            txt_block(3, "顺序栈用数组存储元素。", 1, (8, 9), sec),
            ParsedBlock(
                ordinal=4,
                text="| 操作 | 复杂度 |\n| --- | --- |\n| 入栈 | O(1) |",
                kind=BlockKind.TABLE,
                locator=SourceLocator(section_titles=sec, paragraph=2, line_start=11, line_end=13),
            ),
        ),
    )
    assert [b.locator.section_path for b in doc.blocks] == [
        "第1段",
        "第3章 栈与队列 > 第1段",
        "第3章 栈与队列 > 第2段",
        "第3章 栈与队列 > 3.1 顺序栈 > 第1段",
        "第3章 栈与队列 > 3.1 顺序栈 > 第2段",
    ]
    assert doc.blocks[4].kind is BlockKind.TABLE


def test_repeated_identical_section_path_continues_paragraph_numbering():
    """同一路径出现两次（如同级重名小节）时段落号接续，保证 (章节路径, 段落) 在文档内唯一。"""
    sec = ("第2章 线性表", "小结")
    other = ("第2章 线性表", "2.2 链表")
    doc = ParsedDocument(
        source_format=SourceFormat.TXT,
        parser_version="txt/1",
        blocks=(
            txt_block(0, "第一段小结。", 1, (1, 1), sec),
            txt_block(1, "链表正文。", 1, (3, 3), other),
            txt_block(2, "第二段小结。", 2, (5, 5), sec),
        ),
    )
    assert [b.locator.section_path for b in doc.blocks] == [
        "第2章 线性表 > 小结 > 第1段",
        "第2章 线性表 > 2.2 链表 > 第1段",
        "第2章 线性表 > 小结 > 第2段",
    ]


def test_docx_document_has_sections_but_no_pages_or_lines():
    doc = ParsedDocument(
        source_format=SourceFormat.DOCX,
        parser_version="docx/1",
        blocks=(
            ParsedBlock(
                ordinal=0,
                text="队列遵循先进先出。",
                locator=SourceLocator(section_titles=("第4章 队列",), paragraph=1),
            ),
        ),
    )
    assert doc.blocks[0].locator.to_source_fields() == {"section_path": "第4章 队列 > 第1段"}


def test_pdf_document_requires_pages_only():
    doc = ParsedDocument(
        source_format=SourceFormat.PDF,
        parser_version="pdf/1",
        blocks=(
            pdf_block(0, "封面之后的正文。", 1),
            pdf_block(1, "第二页正文。", 2, ("第1章 绪论",)),
        ),
    )
    assert [b.locator.page for b in doc.blocks] == [1, 2]
    # R02：PDF 的 section_path 只取标题路径，无标题则省略该键
    assert [b.locator.to_source_fields() for b in doc.blocks] == [
        {"page": 1},
        {"page": 2, "section_path": "第1章 绪论"},
    ]


def test_normalize_heading_collapses_whitespace_and_replaces_separator_char():
    assert normalize_heading("  第3章\t 栈与队列 \n") == "第3章 栈与队列"
    assert normalize_heading("x > 0 的情形") == "x ＞ 0 的情形"
    assert normalize_heading("a>b") == "a＞b"


def test_revision_key_accepts_content_hash_from_c05_file_storage(tmp_path):
    """R04：内容哈希唯一来源是 C05 FileStorage.save() 的 StoredFile.content_hash，D01 不重算。"""
    stored = FileStorage(tmp_path, max_bytes=4096).save(
        "示例讲义.txt", "text/plain", ["第一章 绪论\n".encode("utf-8")]
    )
    key = RevisionKey(document_id="doc_01", content_hash=stored.content_hash, parser_version="txt/1")
    assert key.content_hash == stored.content_hash


def test_parsers_package_does_not_define_its_own_hash():
    assert not hasattr(parsers_pkg, "sha256_digest")
    assert "sha256_digest" not in parsers_pkg.__all__


def test_source_format_values_match_c05_supported_formats():
    assert {f.value for f in SourceFormat} == set(SUPPORTED_FORMATS)


def test_document_unreadable_error_carries_wire_reason():
    err = DocumentUnreadableError("encrypted", "PDF 需要口令")
    assert err.reason is UnreadableReason.ENCRYPTED
    assert {r.value for r in UnreadableReason} == {"corrupted", "encrypted", "no_text"}
    assert "encrypted" in str(err)


# ── 边界 ──────────────────────────────────────────────────


def test_minimum_valid_values():
    block = ParsedBlock(
        ordinal=0,
        text="x",
        locator=SourceLocator(paragraph=1, line_start=1, line_end=1),
    )
    assert block.ordinal == 0
    assert SourceLocator(page=1).page == 1


def test_text_is_kept_verbatim_including_edge_whitespace():
    text = "    push(x)\n    pop()"
    block = ParsedBlock(ordinal=0, text=text, kind="code", locator=SourceLocator(paragraph=1))
    assert block.text == text
    assert block.kind is BlockKind.CODE


def test_single_block_document_is_valid():
    doc = ParsedDocument(
        source_format=SourceFormat.TXT,
        parser_version="txt/1",
        blocks=[txt_block(0, "唯一的一段。", 1, (1, 1))],
    )
    assert isinstance(doc.blocks, tuple)


# ── 失败路径：块与定位 ────────────────────────────────────


@pytest.mark.parametrize("text", ["", "   ", "\n\t　"])
def test_empty_text_is_rejected(text):
    with pytest.raises(ParseModelError, match="text"):
        ParsedBlock(ordinal=0, text=text, locator=SourceLocator(paragraph=1))


def test_non_string_text_is_rejected():
    with pytest.raises(ParseModelError, match="text"):
        ParsedBlock(ordinal=0, text=b"bytes", locator=SourceLocator(paragraph=1))  # type: ignore[arg-type]


@pytest.mark.parametrize("ordinal", [-1, True, 1.0, "0"])
def test_invalid_ordinal_is_rejected(ordinal):
    with pytest.raises(ParseModelError, match="ordinal"):
        ParsedBlock(ordinal=ordinal, text="正文", locator=SourceLocator(paragraph=1))


def test_locator_must_be_source_locator():
    with pytest.raises(ParseModelError, match="locator"):
        ParsedBlock(ordinal=0, text="正文", locator={"page": 1})  # type: ignore[arg-type]


def test_unknown_block_kind_is_rejected():
    with pytest.raises(ParseModelError, match="kind"):
        ParsedBlock(ordinal=0, text="正文", kind="heading", locator=SourceLocator(paragraph=1))


def test_locator_without_page_section_or_paragraph_is_rejected():
    with pytest.raises(ParseModelError, match="至少"):
        SourceLocator()
    with pytest.raises(ParseModelError, match="至少"):
        SourceLocator(line_start=1, line_end=2)


@pytest.mark.parametrize("page", [0, -3, True, 1.0, "1"])
def test_invalid_page_is_rejected(page):
    with pytest.raises(ParseModelError, match="page"):
        SourceLocator(page=page)


@pytest.mark.parametrize("paragraph", [0, -1, False])
def test_invalid_paragraph_is_rejected(paragraph):
    with pytest.raises(ParseModelError, match="paragraph"):
        SourceLocator(paragraph=paragraph)


@pytest.mark.parametrize(
    "titles",
    [
        ("",),
        ("   ",),
        ("第1章", " 1.1 概述"),
        ("第1章\n绪论",),
        ("a > b",),
        ("x>0",),
        (3,),
        "第1章 绪论",
    ],
)
def test_invalid_section_titles_are_rejected(titles):
    with pytest.raises(ParseModelError, match="section_titles"):
        SourceLocator(section_titles=titles, paragraph=1)


@pytest.mark.parametrize(
    "lines",
    [(1, None), (None, 2), (0, 1), (3, 2), (True, 1)],
)
def test_invalid_line_range_is_rejected(lines):
    with pytest.raises(ParseModelError, match="line"):
        SourceLocator(paragraph=1, line_start=lines[0], line_end=lines[1])


# ── 失败路径：文档级规则 ──────────────────────────────────


def test_empty_document_must_be_reported_as_no_text():
    with pytest.raises(ParseModelError, match="no_text"):
        ParsedDocument(source_format=SourceFormat.TXT, parser_version="txt/1", blocks=())


def test_blocks_argument_is_required():
    """R05：blocks 无默认值，漏传是调用错误而不是空文档。"""
    with pytest.raises(TypeError):
        ParsedDocument(source_format=SourceFormat.TXT, parser_version="txt/1")  # type: ignore[call-arg]


@pytest.mark.parametrize("version", ["", "  ", "txt 1", 1])
def test_invalid_parser_version_is_rejected(version):
    with pytest.raises(ParseModelError, match="parser_version"):
        ParsedDocument(
            source_format=SourceFormat.TXT,
            parser_version=version,
            blocks=(txt_block(0, "正文", 1, (1, 1)),),
        )


def test_unknown_source_format_is_rejected():
    with pytest.raises(ParseModelError, match="source_format"):
        ParsedDocument(source_format="pptx", parser_version="x/1", blocks=(pdf_block(0, "正文", 1),))


@pytest.mark.parametrize("ordinals", [(1, 2), (0, 2), (1, 0), (0, 0)])
def test_block_ordinals_must_be_contiguous_from_zero(ordinals):
    blocks = tuple(pdf_block(o, f"第{i}块", i + 1) for i, o in enumerate(ordinals))
    with pytest.raises(ParseModelError, match="ordinal"):
        ParsedDocument(source_format=SourceFormat.PDF, parser_version="pdf/1", blocks=blocks)


@pytest.mark.parametrize("fmt", [SourceFormat.TXT, SourceFormat.MARKDOWN, SourceFormat.DOCX])
def test_pageless_formats_must_not_invent_pages(fmt):
    lines = {} if fmt is SourceFormat.DOCX else {"line_start": 1, "line_end": 1}
    block = ParsedBlock(ordinal=0, text="正文", locator=SourceLocator(page=1, paragraph=1, **lines))
    with pytest.raises(ParseModelError, match="page"):
        ParsedDocument(source_format=fmt, parser_version="x/1", blocks=(block,))


def test_pageless_block_needs_paragraph_even_with_headings():
    block = ParsedBlock(
        ordinal=0,
        text="正文",
        locator=SourceLocator(section_titles=("第1章",), line_start=1, line_end=1),
    )
    with pytest.raises(ParseModelError, match="paragraph"):
        ParsedDocument(source_format=SourceFormat.TXT, parser_version="txt/1", blocks=(block,))


def test_pdf_block_with_paragraph_is_rejected():
    """R01（ArvinHan 决定）：PDF 以 page + 可选 section_titles 定位，不填 paragraph。"""
    block = ParsedBlock(ordinal=0, text="正文", locator=SourceLocator(page=1, paragraph=1))
    with pytest.raises(ParseModelError, match="paragraph"):
        ParsedDocument(source_format=SourceFormat.PDF, parser_version="pdf/1", blocks=(block,))


def test_pdf_paragraph_rejected_even_when_numbered_per_page():
    blocks = (
        ParsedBlock(ordinal=0, text="第一页", locator=SourceLocator(page=1, paragraph=1)),
        ParsedBlock(ordinal=1, text="第二页", locator=SourceLocator(page=2, paragraph=1)),
    )
    with pytest.raises(ParseModelError, match="PDF"):
        ParsedDocument(source_format=SourceFormat.PDF, parser_version="pdf/1", blocks=blocks)


def test_pdf_block_without_page_is_rejected():
    block = ParsedBlock(ordinal=0, text="正文", locator=SourceLocator(section_titles=("第1章",)))
    with pytest.raises(ParseModelError, match="page"):
        ParsedDocument(source_format=SourceFormat.PDF, parser_version="pdf/1", blocks=(block,))


@pytest.mark.parametrize("fmt", [SourceFormat.TXT, SourceFormat.MARKDOWN])
def test_text_formats_require_line_numbers(fmt):
    block = ParsedBlock(ordinal=0, text="正文", locator=SourceLocator(paragraph=1))
    with pytest.raises(ParseModelError, match="line"):
        ParsedDocument(source_format=fmt, parser_version="x/1", blocks=(block,))


@pytest.mark.parametrize("fmt", [SourceFormat.DOCX, SourceFormat.PDF])
def test_non_text_formats_reject_line_numbers(fmt):
    block = ParsedBlock(
        ordinal=0,
        text="正文",
        locator=SourceLocator(page=1, line_start=1, line_end=1)
        if fmt is SourceFormat.PDF
        else SourceLocator(paragraph=1, line_start=1, line_end=1),
    )
    with pytest.raises(ParseModelError, match="line"):
        ParsedDocument(source_format=fmt, parser_version="x/1", blocks=(block,))


def test_overlapping_or_backward_lines_are_rejected():
    with pytest.raises(ParseModelError, match="line"):
        ParsedDocument(
            source_format=SourceFormat.TXT,
            parser_version="txt/1",
            blocks=(txt_block(0, "甲", 1, (1, 3)), txt_block(1, "乙", 2, (3, 4))),
        )


@pytest.mark.parametrize("paragraphs", [(1, 3), (2,), (1, 1), (2, 1)])
def test_paragraph_numbering_must_be_consecutive_within_section(paragraphs):
    blocks = tuple(
        txt_block(i, f"第{i}段", p, (2 * i + 1, 2 * i + 1), ("第1章",)) for i, p in enumerate(paragraphs)
    )
    with pytest.raises(ParseModelError, match="paragraph"):
        ParsedDocument(source_format=SourceFormat.TXT, parser_version="txt/1", blocks=blocks)


def test_document_blocks_must_be_parsed_blocks():
    with pytest.raises(ParseModelError, match="blocks"):
        ParsedDocument(source_format=SourceFormat.PDF, parser_version="pdf/1", blocks=({"text": "x"},))


# ── 失败路径：修订与不可读 ────────────────────────────────


@pytest.mark.parametrize(
    "content_hash",
    [
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
        "sha256:BA7816BF8F01CFEA414140DE5DAE2223B00361A396177A9CB410FF61F20015AD",
        "sha256:abc",
        "md5:900150983cd24fb0d6963f7d28e17f72",
    ],
)
def test_revision_key_rejects_malformed_content_hash(content_hash):
    with pytest.raises(ParseModelError, match="content_hash"):
        RevisionKey(document_id="doc_01", content_hash=content_hash, parser_version="txt/1")


def test_revision_key_rejects_empty_document_id_and_version():
    digest = SAMPLE_HASH
    with pytest.raises(ParseModelError, match="document_id"):
        RevisionKey(document_id=" ", content_hash=digest, parser_version="txt/1")
    with pytest.raises(ParseModelError, match="parser_version"):
        RevisionKey(document_id="doc_01", content_hash=digest, parser_version="")


def test_unreadable_reason_outside_wire_set_is_rejected():
    with pytest.raises(ParseModelError, match="reason"):
        DocumentUnreadableError("scanned")


# ── fixture：自编、纯文本、无个人信息 ─────────────────────


FIXTURE_TEXT_SUFFIXES = {".md", ".txt"}


def fixture_files() -> list[Path]:
    return sorted(p for p in FIXTURE_DIR.rglob("*") if p.is_file())


def test_fixture_directory_has_readme_and_samples():
    names = {p.name for p in fixture_files()}
    assert "README.md" in names
    samples = [p for p in fixture_files() if p.name != "README.md"]
    assert {p.suffix for p in samples} >= {".md", ".txt"}


def test_fixture_directory_contains_only_utf8_text():
    for path in fixture_files():
        assert path.suffix in FIXTURE_TEXT_SUFFIXES, f"fixture 只允许 .md/.txt：{path.name}"
        data = path.read_bytes()
        assert b"\x00" not in data, f"疑似二进制：{path.name}"
        data.decode("utf-8")  # 严格解码，失败即非文本


def test_readme_declares_self_authored_and_lists_every_sample():
    readme = (FIXTURE_DIR / "README.md").read_text(encoding="utf-8")
    assert "自编" in readme
    assert "不含真实课程资料" in readme
    for path in fixture_files():
        if path.name != "README.md":
            assert f"`{path.name}`" in readme, f"README 未说明 {path.name} 的用途"
    # DOCX / PDF 不入库，由 D04 / D05 在测试中生成
    assert "D04" in readme and "D05" in readme


PERSONAL_DATA_PATTERNS = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "邮箱"),
    (re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"), "手机号"),
    (re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"), "身份证号"),
    (re.compile(r"https?://"), "外部链接"),
    (re.compile(r"(?<!\d)20\d{8}(?!\d)"), "疑似学号"),
]


def test_fixtures_contain_no_personal_data_markers():
    for path in fixture_files():
        text = path.read_text(encoding="utf-8")
        for pattern, label in PERSONAL_DATA_PATTERNS:
            assert not pattern.search(text), f"{path.name} 含{label}样式内容"


# ── R03：定位规则写入架构文档 ─────────────────────────────


def test_architecture_documents_parse_locator_rules():
    arch = (REPO_ROOT / "docs" / "architecture.md").read_text(encoding="utf-8")
    heading = "## 解析输出与来源定位（D01）"
    assert heading in arch
    section = arch.split(heading, 1)[1].split("\n## ", 1)[0]
    for needle in ("第N段", "＞", "parser_version", "paragraph", "line_start", "content_hash"):
        assert needle in section, f"架构文档 D01 小节缺少 {needle}"
