"""D05：文本型 PDF 的正文与页码提取。

输入 PDF 字节，输出**分页文本行**（`PdfExtraction` → `PdfPage` → `PdfLine`），这是 D06 标题判定与
D07 页眉页脚清洗共同的中间结构；另提供 `to_parsed_document` 把（清洗后的）行转成 D01
`ParsedDocument` 的简单路径：暂不判定标题，`section_titles` 为空，每块只以 `page` 定位。

实现基于 `pdfminer.six`（MIT）的版面分析：字符 → 行（`LTTextLine`）→ 文本框（`LTTextBox`），
行序取 pdfminer 的阅读顺序（文本框按版面排序，框内从上到下），而不是内容流的绘制顺序。

失败一律抛 `DocumentUnreadableError`，不返回空结果：

- `encrypted`：trailer 带 `/Encrypt`。即使空用户密码可以打开（只设了权限限制）也拒绝，
  不绕过作者设置的加密与权限；不为解密引入额外处理。
- `corrupted`：不是 PDF、被截断（缺 `%%EOF`）、结构损坏（pdfminer 解析出错）或没有任何页面。
- `no_text`：没有可提取的文本层，典型是扫描件或纯图片 PDF；系统**没有 OCR**，detail 中写明。
  字形全部无法映射为 Unicode（只剩 `(cid:N)` 占位）也按 `no_text` 处理。

页码 `page` 是从 1 起的物理页序号（与阅读器「跳到第 N 页」一致），不读页面标签（如罗马数字）。
空白页不产生行，但保留在 `PdfExtraction.pages` 中，后续页的页码不受影响。
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from io import BytesIO

from pdfminer.converter import PDFPageAggregator
from pdfminer.layout import LAParams, LTChar, LTFigure, LTPage, LTTextBox, LTTextLine
from pdfminer.pdfdocument import PDFDocument, PDFEncryptionError
from pdfminer.pdfexceptions import PDFObjectNotFound
from pdfminer.pdfinterp import PDFPageInterpreter, PDFResourceManager
from pdfminer.pdfpage import PDFPage
from pdfminer.pdfparser import PDFParser

from app.services.parsers.models import (
    BlockKind,
    DocumentUnreadableError,
    ParsedBlock,
    ParsedDocument,
    SourceFormat,
    SourceLocator,
    UnreadableReason,
)

__all__ = [
    "PARSER_VERSION",
    "PdfExtraction",
    "PdfLine",
    "PdfPage",
    "extract_pdf",
    "parse_pdf",
    "to_parsed_document",
]

#: 解析器版本，进入 `RevisionKey.parser_version`。行切分、行序或过滤规则变化时递增。
PARSER_VERSION = "pdf/1"

#: PDF 规范允许文件头出现在前 1024 字节内、`%%EOF` 出现在末尾 1024 字节内。
_HEADER_WINDOW = 1024
_EOF_WINDOW = 1024

_SUBSET_PREFIX_RE = re.compile(r"^[A-Z]{6}\+")
_BOLD_NAME_RE = re.compile(r"bold|black|heavy|semibold|demibold|demi\b", re.IGNORECASE)
_CID_PLACEHOLDER_RE = re.compile(r"\(cid:\d+\)")

_NO_TEXT_DETAIL = "PDF 没有可提取的文本层（可能是扫描件或纯图片）；系统未提供 OCR，请上传带文本层的 PDF"
_NO_UNICODE_DETAIL = (
    "PDF 的字形无法映射为 Unicode（字体缺少 ToUnicode 映射），提取不到可读文本；"
    "系统未提供 OCR，请重新导出带文本层的 PDF"
)


@dataclass(frozen=True, slots=True)
class PdfLine:
    """版面分析得到的一行文字，是 D06/D07 的输入单元。

    - `page`：从 1 起的物理页序号；`index`：本页内按阅读顺序从 0 起的行号；
      `box`：本页内所属文本框（近似段落）从 0 起的序号，同框的行在 `to_parsed_document` 中合为一块。
    - `text`：行文本，去掉首尾空白，行内空格原样保留；不会为空。
    - `font_name`：行内非空白字符最多的字体名（已去掉 `ABCDEF+` 子集前缀）；
      `font_size`：该主字体的有效字号（已乘文本矩阵缩放，单位 pt，保留两位小数）。
    - `bold`：主字体是否为粗体；`bold_ratio`：行内非空白字符中粗体字符的占比（0～1）。
      粗体只按字体名判定（Bold/Black/Heavy/Semibold/Demi，含 Word 的 `,Bold` 伪粗体名）。
    - `x0, y0, x1, y1`：行外框，PDF 用户空间坐标（原点在页面左下角，y 向上增大），保留两位小数；
      页面尺寸见 `PdfPage.width` / `height`，D07 可用 `y1 / height` 判断是否在页眉区。
    """

    page: int
    index: int
    box: int
    text: str
    font_name: str
    font_size: float
    bold: bool
    bold_ratio: float
    x0: float
    y0: float
    x1: float
    y1: float


@dataclass(frozen=True, slots=True)
class PdfPage:
    """一页：`number` 从 1 起；空白页的 `lines` 为空元组。"""

    number: int
    width: float
    height: float
    lines: tuple[PdfLine, ...]


@dataclass(frozen=True, slots=True)
class PdfExtraction:
    """整份 PDF 的分页文本行。至少有一行文字（否则 `extract_pdf` 已抛 `no_text`）。"""

    pages: tuple[PdfPage, ...]
    parser_version: str = PARSER_VERSION

    @property
    def lines(self) -> tuple[PdfLine, ...]:
        """全部行，按页序、页内阅读顺序排列。"""
        return tuple(line for page in self.pages for line in page.lines)


def extract_pdf(data: bytes) -> PdfExtraction:
    """把文本型 PDF 字节提取为分页文本行；无法提取时抛 `DocumentUnreadableError`。"""
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError(f"extract_pdf 需要 PDF 字节，收到 {type(data).__name__}")
    data = bytes(data)
    _check_envelope(data)

    try:
        pages, saw_unmapped = _extract_pages(data)
    except DocumentUnreadableError:
        raise
    except PDFEncryptionError as exc:
        raise DocumentUnreadableError(UnreadableReason.ENCRYPTED, f"PDF 已加密，无法读取：{exc}") from exc
    except MemoryError:
        raise
    except Exception as exc:  # pdfminer 处理不可信输入时可能抛出任意异常
        raise DocumentUnreadableError(
            UnreadableReason.CORRUPTED, f"PDF 结构损坏，无法解析（{type(exc).__name__}）"
        ) from exc

    if not pages:
        raise DocumentUnreadableError(UnreadableReason.CORRUPTED, "PDF 没有任何页面")
    if not any(page.lines for page in pages):
        detail = _NO_UNICODE_DETAIL if saw_unmapped else _NO_TEXT_DETAIL
        raise DocumentUnreadableError(UnreadableReason.NO_TEXT, detail)
    return PdfExtraction(pages=tuple(pages))


def to_parsed_document(lines: Iterable[PdfLine], parser_version: str = PARSER_VERSION) -> ParsedDocument:
    """把行（可以是 D07 清洗后的子集）转成 D01 `ParsedDocument`。

    相邻且 `(page, box)` 相同的行合为一块，行间用换行连接；每块只带原始 `page`，
    不填 `paragraph`、行号与标题（标题判定归 D06）。没有任何行时抛 `no_text`。
    """
    groups: list[tuple[int, list[str]]] = []
    last_key: tuple[int, int] | None = None
    for line in lines:
        key = (line.page, line.box)
        if key != last_key:
            groups.append((line.page, []))
            last_key = key
        groups[-1][1].append(line.text)

    if not groups:
        raise DocumentUnreadableError(UnreadableReason.NO_TEXT, _NO_TEXT_DETAIL)
    blocks = tuple(
        ParsedBlock(
            ordinal=ordinal,
            text="\n".join(texts),
            locator=SourceLocator(page=page),
            kind=BlockKind.PARAGRAPH,
        )
        for ordinal, (page, texts) in enumerate(groups)
    )
    return ParsedDocument(SourceFormat.PDF, parser_version, blocks)


def parse_pdf(data: bytes) -> ParsedDocument:
    """`extract_pdf` + `to_parsed_document`：不做标题判定与页眉页脚清洗的最简路径。"""
    return to_parsed_document(extract_pdf(data).lines)


# ---------------------------------------------------------------------------
# 内部实现
# ---------------------------------------------------------------------------


def _check_envelope(data: bytes) -> None:
    """文件头与结尾标记：非 PDF 与被截断的上传在交给 pdfminer 之前就拒绝。

    pdfminer 遇到损坏的 xref 会退回全文扫描，截断文件可能只解析出部分页面而不报错；
    这里要求末尾有 `%%EOF`，避免静默丢页。
    """
    if b"%PDF-" not in data[:_HEADER_WINDOW]:
        raise DocumentUnreadableError(UnreadableReason.CORRUPTED, "不是 PDF 文件：缺少 %PDF- 文件头")
    if b"%%EOF" not in data[-_EOF_WINDOW:]:
        raise DocumentUnreadableError(UnreadableReason.CORRUPTED, "PDF 文件不完整：末尾缺少 %%EOF（可能被截断）")


class _TrackingDocument(PDFDocument):
    """记录解析中遇到的缺失对象。

    pdfminer 对找不到的间接对象静默返回 None，文件中段损坏时页面会被当成空白页，
    进而被误报为扫描件；这里记下缺失对象，提取结束后按 `corrupted` 拒绝。
    """

    def __init__(self, parser: PDFParser) -> None:
        self.missing_objids: set[int] = set()
        super().__init__(parser)

    def getobj(self, objid: int) -> object:
        try:
            return super().getobj(objid)
        except PDFObjectNotFound:
            self.missing_objids.add(objid)
            raise


def _extract_pages(data: bytes) -> tuple[list[PdfPage], bool]:
    parser = PDFParser(BytesIO(data))
    document = _TrackingDocument(parser)  # 带 /Encrypt 且空密码打不开时在此抛 PDFEncryptionError
    if document.encryption is not None:
        raise DocumentUnreadableError(
            UnreadableReason.ENCRYPTED, "PDF 已加密（含仅限制权限的加密），请上传未加密的版本"
        )

    manager = PDFResourceManager(caching=True)
    device = PDFPageAggregator(manager, laparams=LAParams(all_texts=True))
    interpreter = PDFPageInterpreter(manager, device)

    pages: list[PdfPage] = []
    saw_unmapped = False
    for number, page in enumerate(PDFPage.create_pages(document), start=1):
        interpreter.process_page(page)
        layout = device.get_result()
        lines, unmapped = _page_lines(layout, number)
        saw_unmapped = saw_unmapped or unmapped
        pages.append(PdfPage(number=number, width=_r(layout.width), height=_r(layout.height), lines=lines))
    if document.missing_objids:
        raise DocumentUnreadableError(
            UnreadableReason.CORRUPTED,
            f"PDF 结构损坏：{len(document.missing_objids)} 个被引用的对象缺失（文件可能被截断或改写）",
        )
    return pages, saw_unmapped


def _page_lines(layout: LTPage, number: int) -> tuple[tuple[PdfLine, ...], bool]:
    lines: list[PdfLine] = []
    unmapped = False
    box_index = -1
    for box in _text_boxes(layout):
        box_used = False
        for item in box:
            if not isinstance(item, LTTextLine):
                continue
            text = item.get_text().strip()
            if not _CID_PLACEHOLDER_RE.sub("", text).strip():
                unmapped = unmapped or bool(text)
                continue
            if not box_used:
                box_index += 1
                box_used = True
            lines.append(_make_line(item, text, number, len(lines), box_index))
    return tuple(lines), unmapped


def _text_boxes(container: Iterable[object]) -> Iterator[LTTextBox]:
    """按 pdfminer 的阅读顺序给出文本框；表单 XObject（`LTFigure`）中的文字一并纳入。"""
    for obj in container:
        if isinstance(obj, LTTextBox):
            yield obj
        elif isinstance(obj, LTFigure):
            yield from _text_boxes(obj)


def _make_line(item: LTTextLine, text: str, page: int, index: int, box: int) -> PdfLine:
    chars = [c for c in item if isinstance(c, LTChar) and c.get_text().strip()]
    weights: Counter[tuple[str, float]] = Counter()
    bold_chars = 0
    for char in chars:
        name = _clean_font_name(char.fontname)
        weights[(name, _r(char.size))] += 1
        bold_chars += _is_bold(name)
    # Counter.most_common 在计数相同时保持首次出现的顺序
    (font_name, font_size), _ = weights.most_common(1)[0] if weights else (("", 0.0), 0)
    return PdfLine(
        page=page,
        index=index,
        box=box,
        text=text,
        font_name=font_name,
        font_size=font_size,
        bold=_is_bold(font_name),
        bold_ratio=round(bold_chars / len(chars), 4) if chars else 0.0,
        x0=_r(item.x0),
        y0=_r(item.y0),
        x1=_r(item.x1),
        y1=_r(item.y1),
    )


def _clean_font_name(raw: object) -> str:
    name = raw.decode("latin-1") if isinstance(raw, bytes) else str(raw)
    return _SUBSET_PREFIX_RE.sub("", name.lstrip("/"))


def _is_bold(font_name: str) -> bool:
    return bool(font_name) and _BOLD_NAME_RE.search(font_name) is not None


def _r(value: float) -> float:
    return round(float(value), 2)
