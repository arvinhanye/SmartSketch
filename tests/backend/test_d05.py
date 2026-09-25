"""D05：PDF 正文与页码提取（`app.services.parsers.pdf`）。

测试用 PDF 全部在本文件中手写字节生成（标准 14 字体、CID 字体、图片 XObject、RC4 加密字典），
不入库、不新增测试依赖。

覆盖三类路径：
- 成功：多页页码、行顺序（按版面而非绘制顺序）、字号 / 粗体 / 字体名 / 坐标进入中间结构、
  中文 CID 字体、转为满足 D01 校验的 `ParsedDocument`、D07 删行后仍保留原页码。
- 边界：空白页与只有空白字符的页跳过但不打乱页码、行内空格保留、单页单行、
  `to_parsed_document` 只收到部分行。
- 失败：全空白、只有图片（扫描件）、字形无法映射为 Unicode 均为 `no_text` 且写明未做 OCR；
  加密（密码错误与空用户密码都拒绝）为 `encrypted`；截断、缺 `%%EOF`、非 PDF、空字节、
  无页面为 `corrupted`；非 bytes 入参为 `TypeError`。
"""

from __future__ import annotations

import hashlib
import re
import struct
import tomllib
from pathlib import Path

import pytest

from app.services.parsers import (
    DocumentUnreadableError,
    ParsedDocument,
    RevisionKey,
    SourceFormat,
    UnreadableReason,
)
from app.services.parsers import pdf as pdf_mod
from app.services.parsers.pdf import (
    PARSER_VERSION,
    PdfExtraction,
    PdfLine,
    PdfPage,
    extract_pdf,
    parse_pdf,
    to_parsed_document,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
PAGE_W, PAGE_H = 595, 842

# ---------------------------------------------------------------------------
# 最小 PDF 生成器
# ---------------------------------------------------------------------------

STANDARD_FONTS = {
    "F1": b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    "F2": b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
    "F3": b"<< /Type /Font /Subtype /Type1 /BaseFont /Times-Roman /Encoding /WinAnsiEncoding >>",
}


def _escape(text: str) -> bytes:
    raw = text.encode("latin-1")
    return raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def text_op(text: str, *, x: float = 72, y: float = 700, size: float = 12, font: str = "F1") -> bytes:
    """一行文字的内容流片段（标准字体，文字按 latin-1 编码）。"""
    return b"BT /%s %g Tf %g %g Td (%s) Tj ET\n" % (font.encode(), size, x, y, _escape(text))


def hex_text_op(hex_codes: str, *, x: float = 72, y: float = 700, size: float = 12, font: str) -> bytes:
    """一行文字的内容流片段（CID 字体，直接给出十六进制编码）。"""
    return b"BT /%s %g Tf %g %g Td <%s> Tj ET\n" % (font.encode(), size, x, y, hex_codes.encode())


class PdfBuilder:
    """按对象编号顺序写出一个带 xref 与 trailer 的经典 PDF。"""

    def __init__(self) -> None:
        self.objects: list[bytes] = []

    def add(self, body: bytes) -> int:
        self.objects.append(body)
        return len(self.objects)

    def reserve(self) -> int:
        return self.add(b"null")

    def set(self, num: int, body: bytes) -> None:
        self.objects[num - 1] = body

    def stream(self, content: bytes, extra: bytes = b"") -> int:
        return self.add(b"<< /Length %d %s>>\nstream\n%s\nendstream" % (len(content), extra, content))

    def serialize(self, root: int, trailer_extra: bytes = b"") -> bytes:
        out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = []
        for num, body in enumerate(self.objects, start=1):
            offsets.append(len(out))
            out += b"%d 0 obj\n%s\nendobj\n" % (num, body)
        xref_at = len(out)
        out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(self.objects) + 1)
        for off in offsets:
            out += b"%010d 00000 n \n" % off
        out += b"trailer\n<< /Size %d /Root %d 0 R %s>>\nstartxref\n%d\n%%%%EOF\n" % (
            len(self.objects) + 1,
            root,
            trailer_extra,
            xref_at,
        )
        return bytes(out)


def build_pdf(
    pages: list[bytes],
    *,
    extra_fonts: dict[str, bytes] | None = None,
    image_pages: frozenset[int] = frozenset(),
    trailer_extra: bytes = b"",
    builder: PdfBuilder | None = None,
) -> bytes:
    """`pages` 为每页的内容流；`image_pages` 中的页（从 0 起）额外引用一张 1×1 灰度图。"""
    b = builder or PdfBuilder()
    catalog = b.reserve()
    pages_num = b.reserve()
    font_refs = {}
    for key, body in {**STANDARD_FONTS, **(extra_fonts or {})}.items():
        font_refs[key] = b.add(body)
    fonts = b" ".join(b"/%s %d 0 R" % (k.encode(), n) for k, n in font_refs.items())
    image = b.stream(
        b"\x80",
        b"/Type /XObject /Subtype /Image /Width 1 /Height 1 /ColorSpace /DeviceGray /BitsPerComponent 8 ",
    )
    kids = []
    for index, content in enumerate(pages):
        if index in image_pages:
            content = b"q 400 0 0 600 90 120 cm /Im1 Do Q\n" + content
        content_num = b.stream(content)
        kids.append(
            b.add(
                b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %d %d] "
                b"/Resources << /Font << %s >> /XObject << /Im1 %d 0 R >> >> /Contents %d 0 R >>"
                % (pages_num, PAGE_W, PAGE_H, fonts, image, content_num)
            )
        )
    b.set(catalog, b"<< /Type /Catalog /Pages %d 0 R >>" % pages_num)
    b.set(
        pages_num,
        b"<< /Type /Pages /Kids [%s] /Count %d >>"
        % (b" ".join(b"%d 0 R" % k for k in kids), len(kids)),
    )
    return b.serialize(catalog, trailer_extra)


def cid_font(builder: PdfBuilder, *, encoding: bytes, registry: bytes, ordering: bytes, supplement: int) -> bytes:
    """未嵌入字形的 Type0 CID 字体；返回字体字典（放进 extra_fonts）。"""
    descriptor = builder.add(
        b"<< /Type /FontDescriptor /FontName /SimSun /Flags 4 /FontBBox [0 -141 1000 859] "
        b"/ItalicAngle 0 /Ascent 859 /Descent -141 /CapHeight 700 /StemV 80 >>"
    )
    descendant = builder.add(
        b"<< /Type /Font /Subtype /CIDFontType0 /BaseFont /SimSun "
        b"/CIDSystemInfo << /Registry (%s) /Ordering (%s) /Supplement %d >> "
        b"/FontDescriptor %d 0 R /DW 1000 >>" % (registry, ordering, supplement, descriptor)
    )
    return b"<< /Type /Font /Subtype /Type0 /BaseFont /SimSun /Encoding /%s /DescendantFonts [%d 0 R] >>" % (
        encoding,
        descendant,
    )


def truetype_font(builder: PdfBuilder, base_font: bytes) -> bytes:
    """带宽度表与字体描述的非标准 TrueType 字体（例：子集前缀 + 粗体名）。"""
    descriptor = builder.add(
        b"<< /Type /FontDescriptor /FontName /%s /Flags 32 /FontBBox [-600 -300 2000 1000] "
        b"/ItalicAngle 0 /Ascent 900 /Descent -200 /CapHeight 700 /StemV 120 >>" % base_font
    )
    widths = b" ".join([b"600"] * 95)
    return (
        b"<< /Type /Font /Subtype /TrueType /BaseFont /%s /FirstChar 32 /LastChar 126 "
        b"/Widths [%s] /Encoding /WinAnsiEncoding /FontDescriptor %d 0 R >>" % (base_font, widths, descriptor)
    )


# --- RC4 标准安全处理器（R2，40 位），用于生成「空用户密码即可打开」的加密 PDF ---

_PASSWORD_PAD = bytes.fromhex("28BF4E5E4E758A4164004E56FFFA01082E2E00B6D0683E802F0CA9FE6453697A")
_FILE_ID = bytes.fromhex("0123456789abcdef0123456789abcdef")


def _rc4(key: bytes, data: bytes) -> bytes:
    s = list(range(256))
    j = 0
    for i in range(256):
        j = (j + s[i] + key[i % len(key)]) % 256
        s[i], s[j] = s[j], s[i]
    i = j = 0
    out = bytearray()
    for byte in data:
        i = (i + 1) % 256
        j = (j + s[i]) % 256
        s[i], s[j] = s[j], s[i]
        out.append(byte ^ s[(s[i] + s[j]) % 256])
    return bytes(out)


def encrypted_pdf(*, empty_user_password: bool) -> bytes:
    owner = hashlib.md5(b"owner-secret").digest() * 2
    permissions = -44
    if empty_user_password:
        key = hashlib.md5(_PASSWORD_PAD + owner + struct.pack("<i", permissions) + _FILE_ID).digest()[:5]
        user = _rc4(key, _PASSWORD_PAD)
    else:
        user = hashlib.sha256(b"not-the-empty-password").digest()
    b = PdfBuilder()
    enc = b.add(
        b"<< /Filter /Standard /V 1 /R 2 /Length 40 /P %d /O <%s> /U <%s> >>"
        % (permissions, owner.hex().encode(), user.hex().encode())
    )
    trailer = b"/Encrypt %d 0 R /ID [<%s> <%s>] " % (enc, _FILE_ID.hex().encode(), _FILE_ID.hex().encode())
    return build_pdf([text_op("Secret lecture notes")], trailer_extra=trailer, builder=b)


def assert_unreadable(data: object, reason: UnreadableReason) -> DocumentUnreadableError:
    with pytest.raises(DocumentUnreadableError) as info:
        extract_pdf(data)  # type: ignore[arg-type]
    assert info.value.reason is reason, info.value
    with pytest.raises(DocumentUnreadableError) as again:
        parse_pdf(data)  # type: ignore[arg-type]
    assert again.value.reason is reason
    return info.value


def texts(extraction: PdfExtraction) -> list[tuple[int, str]]:
    return [(line.page, line.text) for line in extraction.lines]


# ---------------------------------------------------------------------------
# 成功路径
# ---------------------------------------------------------------------------


def test_parser_version_is_pdf_1_and_valid_for_revision_key() -> None:
    assert PARSER_VERSION == "pdf/1"
    RevisionKey("doc-1", "sha256:" + "0" * 64, PARSER_VERSION)


def test_multi_page_lines_keep_their_page_numbers() -> None:
    data = build_pdf(
        [
            text_op("Chapter one intro", y=760) + text_op("Stack basics", y=700),
            text_op("Queue basics", y=760),
            text_op("Deque basics", y=760),
        ]
    )
    extraction = extract_pdf(data)

    assert isinstance(extraction, PdfExtraction)
    assert [p.number for p in extraction.pages] == [1, 2, 3]
    assert texts(extraction) == [
        (1, "Chapter one intro"),
        (1, "Stack basics"),
        (2, "Queue basics"),
        (3, "Deque basics"),
    ]
    assert all(isinstance(line, PdfLine) for line in extraction.lines)
    assert all(isinstance(page, PdfPage) for page in extraction.pages)
    assert extraction.parser_version == PARSER_VERSION


def test_blank_pages_are_skipped_without_renumbering() -> None:
    data = build_pdf(
        [
            text_op("First page text"),
            b"",  # 完全空白页
            text_op("   "),  # 只有空白字符
            text_op("Fourth page text"),
        ]
    )
    extraction = extract_pdf(data)

    assert [p.number for p in extraction.pages] == [1, 2, 3, 4]
    assert extraction.pages[1].lines == ()
    assert extraction.pages[2].lines == ()
    assert texts(extraction) == [(1, "First page text"), (4, "Fourth page text")]

    doc = parse_pdf(data)
    assert [b.locator.page for b in doc.blocks] == [1, 4]


def test_lines_follow_visual_order_not_drawing_order() -> None:
    # 内容流先画页面下方的行，再画上方的行；输出应按从上到下的阅读顺序。
    content = (
        text_op("Third line at bottom", y=300)
        + text_op("First line at top", y=760)
        + text_op("Second line in middle", y=530)
    )
    extraction = extract_pdf(build_pdf([content]))

    assert [line.text for line in extraction.lines] == [
        "First line at top",
        "Second line in middle",
        "Third line at bottom",
    ]
    assert [line.index for line in extraction.lines] == [0, 1, 2]
    ys = [line.y1 for line in extraction.lines]
    assert ys == sorted(ys, reverse=True)


def test_consecutive_lines_of_a_paragraph_stay_in_order_and_share_a_box() -> None:
    content = (
        text_op("A stack is a linear list", y=700)
        + text_op("that only allows insertion", y=686)
        + text_op("and deletion at one end.", y=672)
    )
    extraction = extract_pdf(build_pdf([content]))

    assert [line.text for line in extraction.lines] == [
        "A stack is a linear list",
        "that only allows insertion",
        "and deletion at one end.",
    ]
    assert len({line.box for line in extraction.lines}) == 1

    doc = parse_pdf(build_pdf([content]))
    assert len(doc.blocks) == 1
    assert doc.blocks[0].text == "A stack is a linear list\nthat only allows insertion\nand deletion at one end."


def test_font_size_bold_font_name_and_position_are_exposed_per_line() -> None:
    content = (
        text_op("Chapter 3 Stacks", y=760, size=20, font="F2")
        + text_op("A stack is last in first out.", y=600, size=11, font="F1")
        + text_op("Footnote in Times", y=80, size=8, font="F3")
    )
    extraction = extract_pdf(build_pdf([content]))
    title, body, foot = extraction.lines

    assert title.font_size == pytest.approx(20, abs=0.01)
    assert title.font_name == "Helvetica-Bold"
    assert title.bold is True
    assert title.bold_ratio == pytest.approx(1.0)

    assert body.font_size == pytest.approx(11, abs=0.01)
    assert body.font_name == "Helvetica"
    assert body.bold is False
    assert body.bold_ratio == pytest.approx(0.0)

    assert foot.font_size == pytest.approx(8, abs=0.01)
    assert foot.font_name == "Times-Roman"

    # 坐标为 PDF 用户空间（原点在页面左下角）；页面尺寸在 PdfPage 上。
    page = extraction.pages[0]
    assert (page.width, page.height) == (PAGE_W, PAGE_H)
    assert title.x0 == pytest.approx(72, abs=0.5)
    assert title.y0 < title.y1 <= PAGE_H
    assert title.y0 > body.y1 > body.y0 > foot.y1
    assert foot.y0 < 80 < foot.y1


def test_dominant_font_decides_line_attributes_for_mixed_runs() -> None:
    # 同一行：短粗体引导词 + 较长正文。行的主字体取非空白字符最多的那种。
    content = (
        b"BT /F2 11 Tf 72 700 Td (Note: ) Tj /F1 11 Tf (the top pointer moves on every push) Tj ET\n"
    )
    (line,) = extract_pdf(build_pdf([content])).lines

    assert line.text == "Note: the top pointer moves on every push"
    assert line.font_name == "Helvetica"
    assert line.bold is False
    assert 0 < line.bold_ratio < 0.5


def test_subset_prefix_is_stripped_and_bold_is_read_from_font_name() -> None:
    b = PdfBuilder()
    font = truetype_font(b, b"ABCDEF+Arial-BoldMT")
    data = build_pdf([text_op("Subset bold heading", size=16, font="T1")], extra_fonts={"T1": font}, builder=b)
    (line,) = extract_pdf(data).lines

    assert line.font_name == "Arial-BoldMT"
    assert line.bold is True
    assert line.font_size == pytest.approx(16, abs=0.01)


def test_inner_spaces_are_kept_and_outer_whitespace_trimmed() -> None:
    (line,) = extract_pdf(build_pdf([text_op("  Linked  list node  ")])).lines
    assert line.text == "Linked  list node"


def test_chinese_text_from_cid_font_with_predefined_cmap() -> None:
    b = PdfBuilder()
    font = cid_font(b, encoding=b"UniGB-UCS2-H", registry=b"Adobe", ordering=b"GB1", supplement=2)
    # 「第三章 栈」「栈是一种线性表」的 UCS-2 编码
    content = hex_text_op("7B2C4E097AE000206808", y=760, size=18, font="C1") + hex_text_op(
        "6808662F4E0079CD7EBF60278868", y=700, size=12, font="C1"
    )
    extraction = extract_pdf(build_pdf([content], extra_fonts={"C1": font}, builder=b))

    assert [line.text for line in extraction.lines] == ["第三章 栈", "栈是一种线性表"]
    assert extraction.lines[0].font_size == pytest.approx(18, abs=0.01)
    assert extraction.lines[0].font_name == "SimSun"


def test_parse_pdf_returns_a_d01_valid_parsed_document() -> None:
    data = build_pdf(
        [
            text_op("Heading one", y=760, size=18, font="F2") + text_op("Body paragraph one.", y=600),
            b"",
            text_op("Body paragraph three.", y=760),
        ]
    )
    doc = parse_pdf(data)

    assert isinstance(doc, ParsedDocument)
    assert doc.source_format is SourceFormat.PDF
    assert doc.parser_version == PARSER_VERSION
    assert [b.ordinal for b in doc.blocks] == list(range(len(doc.blocks)))
    assert [(b.locator.page, b.text) for b in doc.blocks] == [
        (1, "Heading one"),
        (1, "Body paragraph one."),
        (3, "Body paragraph three."),
    ]
    for block in doc.blocks:
        loc = block.locator
        assert loc.page >= 1
        assert loc.paragraph is None
        assert loc.line_start is None and loc.line_end is None
        assert loc.section_titles == ()  # 标题判定归 D06
        assert loc.to_source_fields() == {"page": loc.page}
    # 重新构造一次，确认满足 D01 的全部文档级校验
    ParsedDocument(doc.source_format, doc.parser_version, doc.blocks)


def test_to_parsed_document_keeps_original_pages_after_lines_are_removed() -> None:
    # 模拟 D07：去掉每页顶部的页眉行后再转换，页码仍是原始页码。
    pages = [
        text_op("Data Structures Course", y=810, size=9) + text_op(f"Content of page {n}", y=600)
        for n in (1, 2, 3)
    ]
    extraction = extract_pdf(build_pdf(pages))
    kept = [line for line in extraction.lines if line.text != "Data Structures Course"]

    doc = to_parsed_document(kept)
    assert [(b.ordinal, b.locator.page, b.text) for b in doc.blocks] == [
        (0, 1, "Content of page 1"),
        (1, 2, "Content of page 2"),
        (2, 3, "Content of page 3"),
    ]


def test_to_parsed_document_without_lines_is_no_text() -> None:
    with pytest.raises(DocumentUnreadableError) as info:
        to_parsed_document([])
    assert info.value.reason is UnreadableReason.NO_TEXT


def test_intermediate_structures_are_immutable() -> None:
    extraction = extract_pdf(build_pdf([text_op("Frozen line")]))
    with pytest.raises(AttributeError):
        extraction.lines[0].text = "changed"  # type: ignore[misc]
    assert isinstance(extraction.pages, tuple)
    assert isinstance(extraction.pages[0].lines, tuple)


# ---------------------------------------------------------------------------
# 失败路径：no_text
# ---------------------------------------------------------------------------


def test_all_blank_pages_are_no_text() -> None:
    err = assert_unreadable(build_pdf([b"", text_op("    ")]), UnreadableReason.NO_TEXT)
    assert "OCR" in err.detail


def test_image_only_scan_is_no_text_and_does_not_claim_ocr() -> None:
    data = build_pdf([b"", b""], image_pages=frozenset({0, 1}))
    err = assert_unreadable(data, UnreadableReason.NO_TEXT)
    assert "OCR" in err.detail
    assert "扫描" in err.detail


def test_glyphs_without_unicode_mapping_are_no_text() -> None:
    # Identity-H 且无 ToUnicode：只能得到 (cid:N) 占位，不能当作正文。
    b = PdfBuilder()
    font = cid_font(b, encoding=b"Identity-H", registry=b"Adobe", ordering=b"Identity", supplement=0)
    data = build_pdf([hex_text_op("0012003400560078", font="C1")], extra_fonts={"C1": font}, builder=b)
    err = assert_unreadable(data, UnreadableReason.NO_TEXT)
    assert "Unicode" in err.detail


# ---------------------------------------------------------------------------
# 失败路径：encrypted
# ---------------------------------------------------------------------------


def test_encrypted_pdf_with_unknown_password_is_encrypted() -> None:
    assert_unreadable(encrypted_pdf(empty_user_password=False), UnreadableReason.ENCRYPTED)


def test_encrypted_pdf_openable_with_empty_password_is_still_rejected() -> None:
    # 只设了所有者密码（权限限制）的 PDF 也不绕过，统一按 encrypted 拒绝。
    err = assert_unreadable(encrypted_pdf(empty_user_password=True), UnreadableReason.ENCRYPTED)
    assert err.detail


# ---------------------------------------------------------------------------
# 失败路径：corrupted
# ---------------------------------------------------------------------------


def _three_page_pdf() -> bytes:
    return build_pdf([text_op(f"Page {n} text") for n in (1, 2, 3)])


@pytest.mark.parametrize("keep", [0.25, 0.5, 0.9])
def test_truncated_pdf_is_corrupted(keep: float) -> None:
    data = _three_page_pdf()
    assert_unreadable(data[: int(len(data) * keep)], UnreadableReason.CORRUPTED)


@pytest.mark.parametrize("fill", [None, b"\x00"], ids=["middle-cut", "middle-zeroed"])
def test_damaged_middle_with_intact_tail_is_corrupted_not_no_text(fill: bytes | None) -> None:
    # 末尾的 xref/trailer/%%EOF 完好，但中段对象丢失：不能把缺内容的页误报为扫描件。
    data = _three_page_pdf()
    n = len(data)
    middle = b"" if fill is None else fill * (n // 3)
    assert_unreadable(data[: n // 3] + middle + data[2 * n // 3 :], UnreadableReason.CORRUPTED)


def test_page_referencing_a_missing_object_is_corrupted() -> None:
    data = build_pdf([text_op("Only page")])
    broken = re.sub(rb"/Contents \d+ 0 R", b"/Contents 999 0 R", data)
    assert broken != data
    assert_unreadable(broken, UnreadableReason.CORRUPTED)


def test_pdf_missing_eof_marker_is_corrupted() -> None:
    data = _three_page_pdf()
    assert data.rstrip().endswith(b"%%EOF")
    assert_unreadable(data.rstrip()[: -len(b"%%EOF")], UnreadableReason.CORRUPTED)


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"hello, this is plain text and not a PDF\n",
        b"\x89PNG\r\n\x1a\n" + bytes(range(256)),
        b"%PDF-1.4\n" + bytes(range(256)) * 4 + b"\n%%EOF\n",
    ],
    ids=["empty", "plain-text", "png-bytes", "pdf-header-garbage-body"],
)
def test_non_pdf_or_garbage_bytes_are_corrupted(data: bytes) -> None:
    assert_unreadable(data, UnreadableReason.CORRUPTED)


def test_pdf_without_pages_is_corrupted() -> None:
    b = PdfBuilder()
    pages = b.add(b"<< /Type /Pages /Kids [] /Count 0 >>")
    catalog = b.add(b"<< /Type /Catalog /Pages %d 0 R >>" % pages)
    assert_unreadable(b.serialize(catalog), UnreadableReason.CORRUPTED)


def test_non_bytes_input_is_a_type_error() -> None:
    with pytest.raises(TypeError):
        extract_pdf("%PDF-1.4 not bytes")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 依赖约定
# ---------------------------------------------------------------------------


def test_pdf_dependency_is_pinned_and_not_agpl() -> None:
    pyproject = tomllib.loads((REPO_ROOT / "src" / "backend" / "pyproject.toml").read_text("utf-8"))
    deps = pyproject["project"]["dependencies"]
    assert "pdfminer.six==20260107" in deps
    assert not any(re.match(r"(?i)(pymupdf|fitz|pdfplumber|pypdfium2)\b", d) for d in deps)
    source = Path(pdf_mod.__file__).read_text("utf-8")
    assert not re.search(r"^\s*(import|from)\s+(fitz|pymupdf)\b", source, re.M)
