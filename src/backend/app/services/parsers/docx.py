"""D04：DOCX 段落与表格解析。

输入 DOCX 字节，输出 `ParsedDocument`（D01 模型）。只用标准库 `zipfile` 与
`xml.etree.ElementTree`，不引入第三方依赖。按 D01 规则，DOCX 块不带页码（分页随渲染
变化，`w:br w:type="page"`、`w:lastRenderedPageBreak` 都不当作页码）、不带行号；每块带
「同一标题路径下的段落号」。

**标题判定**（不看样式显示名，如「标题 1」）：

1. 段落直接的 `w:pPr/w:outlineLvl`：0～8 表示第 1～9 级标题，9 表示正文（覆盖样式）；
2. 否则沿 `w:pStyle` → `w:basedOn` 继承链找第一个带 `outlineLvl` 的样式；
   Word（含中文版，样式 ID 为 "1"、"2"…）的内置标题样式都带 `outlineLvl`；
3. 链上某个样式 ID 形如 `HeadingN`（不区分大小写）时按第 N 级，用于缺 `styles.xml`
   或样式未写大纲级别的生成器。未指定 `pStyle` 时使用 `styles.xml` 的默认段落样式。

**块**：普通段落 → `paragraph`；连续的编号/项目符号段落（`w:numPr` 且 `numId ≠ 0`，
同一 `numId`）合为一个 `list` 块，每项一行，不生成编号文字；表格 → 一个 `table` 块，
每行一行、单元格以 ` | ` 分隔并保持顺序，单元格内多段与嵌套表以空格连接，全空行跳过。
标题只进入后续块的 `section_titles`，不成块；空白段落跳过。

**嵌入内容范围**：

- 解析：正文段落（含超链接、内容控件 `w:sdt`、`w:smartTag`、`w:customXml`、
  修订插入 `w:ins`/`w:moveTo`、域结果文字）、正文表格（含嵌套表）。
  `w:tab` 记为制表符，`w:br`/`w:cr` 记为换行。
- 忽略：图片与图形（`w:drawing`、`w:pict`）、文本框（`w:txbxContent`，含
  `mc:AlternateContent` 的两种表示）、嵌入对象（`w:object`）、公式（`m:oMath`）、
  外部导入块（`w:altChunk`）、页眉页脚、脚注尾注、批注（只读 `word/document.xml`，
  这些部件不打开）、修订删除 `w:del`/`w:moveFrom`、域代码 `w:instrText`、
  直接设为隐藏（`w:vanish`）的文字。

**无法解析**（抛 `DocumentUnreadableError`）：

- `encrypted`：OLE 复合文件且含 `EncryptionInfo`/`EncryptedPackage` 流（Office 加密包），
  或 zip 条目带加密标志；
- `corrupted`：不是 zip、zip 损坏或 CRC 错误、缺 `word/document.xml`、XML 不合法或根元素
  不对、含 DOCTYPE（拒绝一切 DTD，杜绝实体膨胀与外部实体）、部件解压后超过
  `max_part_bytes`（按实际读出的字节判定），以及不含加密流的 OLE 文件（旧版 `.doc`）；
- `no_text`：没有任何正文块（空文档、只有标题、只有图片等）。
"""

from __future__ import annotations

import io
import re
import zipfile
import zlib
from collections.abc import Iterator
from dataclasses import dataclass
from xml.etree import ElementTree as ET

from app.services.parsers.models import (
    BlockKind,
    DocumentUnreadableError,
    ParsedBlock,
    ParsedDocument,
    SourceFormat,
    SourceLocator,
    UnreadableReason,
    normalize_heading,
)

__all__ = ["DOCUMENT_PART", "MAX_PART_BYTES", "PARSER_VERSION", "STYLES_PART", "parse_docx"]

#: 解析器版本，进入 `RevisionKey.parser_version`；输出规则变化时递增。
PARSER_VERSION = "docx/1"

DOCUMENT_PART = "word/document.xml"
STYLES_PART = "word/styles.xml"

#: 单个 XML 部件解压后的上限。上传上限 50 MiB（D-11），正常课程资料的 document.xml
#: 远小于此；超过即视为解压炸弹或异常文件，同时限制 ElementTree 的内存占用。
MAX_PART_BYTES = 64 * 1024 * 1024

_W_NAMESPACES = frozenset(
    {
        "http://schemas.openxmlformats.org/wordprocessingml/2006/main",  # Transitional
        "http://purl.oclc.org/ooxml/wordprocessingml/main",  # Strict
    }
)
_OLE_MAGIC = bytes.fromhex("D0CF11E0A1B11AE1")
_OLE_ENCRYPTION_STREAMS = tuple(
    name.encode("utf-16-le") for name in ("EncryptionInfo", "EncryptedPackage")
)
_HEADING_ID_RE = re.compile(r"^heading\s*([1-9])$", re.IGNORECASE)
_OFF_VALUES = frozenset({"0", "false", "off"})
_MAX_HEADING_LEVEL = 9

#: 段落内这些容器只包装文字，递归取其内容；未列出的元素（删除、图片等）整体忽略。
_INLINE_WRAPPERS = frozenset(
    {"hyperlink", "ins", "moveTo", "smartTag", "customXml", "sdt", "sdtContent", "fldSimple", "dir", "bdo"}
)
#: 正文与单元格中只起包装作用的块级容器。
_BLOCK_WRAPPERS = frozenset({"sdt", "sdtContent", "customXml"})


def parse_docx(data: bytes | bytearray | memoryview, *, max_part_bytes: int = MAX_PART_BYTES) -> ParsedDocument:
    """把 DOCX 字节解析为 `ParsedDocument`；无法解析时抛 `DocumentUnreadableError`。"""
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError(f"parse_docx 需要 bytes，收到 {type(data).__name__}")
    data = bytes(data)

    if data.startswith(_OLE_MAGIC):
        if any(marker in data for marker in _OLE_ENCRYPTION_STREAMS):
            raise DocumentUnreadableError(UnreadableReason.ENCRYPTED, "受密码保护的 Office 加密包")
        raise DocumentUnreadableError(
            UnreadableReason.CORRUPTED, "OLE 复合文件而非 DOCX（可能是旧版 .doc），不支持"
        )

    document_bytes, styles_bytes = _read_parts(data, max_part_bytes)

    root = _parse_xml(document_bytes, DOCUMENT_PART)
    ns = _namespace(root)
    if ns not in _W_NAMESPACES or root.tag != f"{{{ns}}}document":
        raise DocumentUnreadableError(UnreadableReason.CORRUPTED, f"{DOCUMENT_PART} 的根元素不是 w:document")
    body = root.find(f"{{{ns}}}body")
    if body is None:
        raise DocumentUnreadableError(UnreadableReason.CORRUPTED, f"{DOCUMENT_PART} 缺少 w:body")

    styles = _StyleTable.parse(styles_bytes) if styles_bytes is not None else _StyleTable.empty()
    blocks = _BodyWalker(ns, styles).walk(body)
    if not blocks:
        raise DocumentUnreadableError(UnreadableReason.NO_TEXT, "文档没有可提取的正文段落或表格")
    return ParsedDocument(SourceFormat.DOCX, PARSER_VERSION, tuple(blocks))


# ---------------------------------------------------------------- zip 与 XML


def _read_parts(data: bytes, limit: int) -> tuple[bytes, bytes | None]:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            # OPC 部件名不区分大小写
            members = {info.filename.lower(): info for info in zf.infolist()}
            document = _read_member(zf, members.get(DOCUMENT_PART), limit)
            if document is None:
                raise DocumentUnreadableError(UnreadableReason.CORRUPTED, f"缺少 {DOCUMENT_PART}")
            styles = _read_member(zf, members.get(STYLES_PART), limit)
    except DocumentUnreadableError:
        raise
    except (zipfile.BadZipFile, zipfile.LargeZipFile, NotImplementedError, RuntimeError,
            EOFError, OSError, ValueError, zlib.error) as exc:
        raise DocumentUnreadableError(UnreadableReason.CORRUPTED, f"zip 包无法读取：{exc}") from None
    return document, styles


def _read_member(zf: zipfile.ZipFile, info: zipfile.ZipInfo | None, limit: int) -> bytes | None:
    if info is None:
        return None
    if info.flag_bits & 0x1:
        raise DocumentUnreadableError(UnreadableReason.ENCRYPTED, f"{info.filename} 已加密")
    # 不信任头部声明的大小：最多读 limit + 1 字节，读满即判定超限。
    with zf.open(info) as handle:
        content = handle.read(limit + 1)
    if len(content) > limit:
        raise DocumentUnreadableError(
            UnreadableReason.CORRUPTED, f"{info.filename} 解压后超过 {limit} 字节上限"
        )
    return content


class _ForbiddenDtd(Exception):
    pass


class _NoDtdTreeBuilder(ET.TreeBuilder):
    """expat 在读到 DOCTYPE 开头时回调 `doctype`，此时内部子集的实体声明尚未处理。"""

    def doctype(self, name: str, pubid: str | None, system: str | None) -> None:
        raise _ForbiddenDtd(name)


def _parse_xml(content: bytes, part: str) -> ET.Element:
    parser = ET.XMLParser(target=_NoDtdTreeBuilder())
    try:
        parser.feed(content)
        return parser.close()
    except _ForbiddenDtd:
        raise DocumentUnreadableError(UnreadableReason.CORRUPTED, f"{part} 含 DOCTYPE，拒绝解析") from None
    except ET.ParseError as exc:
        raise DocumentUnreadableError(UnreadableReason.CORRUPTED, f"{part} 不是合法 XML：{exc}") from None


def _namespace(elem: ET.Element) -> str:
    tag = elem.tag
    return tag[1:].split("}", 1)[0] if isinstance(tag, str) and tag.startswith("{") else ""


def _is_on(elem: ET.Element, ns: str) -> bool:
    """OOXML 开关属性：缺省 `w:val` 表示开，`0`/`false`/`off` 表示关。"""
    value = elem.get(f"{{{ns}}}val")
    return value is None or value.lower() not in _OFF_VALUES


def _int_val(elem: ET.Element | None, ns: str) -> int | None:
    if elem is None:
        return None
    try:
        return int(elem.get(f"{{{ns}}}val", ""))
    except ValueError:
        return None


# ---------------------------------------------------------------- 样式


def _outline_to_level(outline: int) -> int | None:
    """outlineLvl 0～8 → 第 1～9 级标题；9（正文级别）及其他值 → 非标题。"""
    return outline + 1 if 0 <= outline < _MAX_HEADING_LEVEL else None


@dataclass(frozen=True, slots=True)
class _Style:
    based_on: str | None
    outline: int | None  # 样式 pPr 中的 outlineLvl 原值
    num_id: str | None  # 样式 pPr 中的 numId（"0" 表示取消编号）


class _StyleTable:
    def __init__(self, styles: dict[str, _Style], default_id: str | None) -> None:
        self._styles = styles
        self.default_id = default_id

    @classmethod
    def empty(cls) -> _StyleTable:
        return cls({}, None)

    @classmethod
    def parse(cls, content: bytes) -> _StyleTable:
        root = _parse_xml(content, STYLES_PART)
        ns = _namespace(root)
        if ns not in _W_NAMESPACES or root.tag != f"{{{ns}}}styles":
            raise DocumentUnreadableError(UnreadableReason.CORRUPTED, f"{STYLES_PART} 的根元素不是 w:styles")
        w = f"{{{ns}}}"
        styles: dict[str, _Style] = {}
        default_id = None
        for elem in root.iter(f"{w}style"):
            if elem.get(f"{w}type", "paragraph") != "paragraph":
                continue
            style_id = elem.get(f"{w}styleId")
            if not style_id:
                continue
            based_on = elem.find(f"{w}basedOn")
            ppr = elem.find(f"{w}pPr")
            num = ppr.find(f"{w}numPr/{w}numId") if ppr is not None else None
            styles[style_id] = _Style(
                based_on=based_on.get(f"{w}val") if based_on is not None else None,
                outline=_int_val(ppr.find(f"{w}outlineLvl"), ns) if ppr is not None else None,
                num_id=num.get(f"{w}val") if num is not None else None,
            )
            if default_id is None and _is_default(elem, w):
                default_id = style_id
        return cls(styles, default_id)

    def _chain(self, style_id: str | None) -> Iterator[tuple[str, _Style | None]]:
        seen: set[str] = set()
        while style_id and style_id not in seen:  # basedOn 成环时停止
            seen.add(style_id)
            style = self._styles.get(style_id)
            yield style_id, style
            style_id = style.based_on if style is not None else None

    def heading_level(self, style_id: str | None) -> int | None:
        for sid, style in self._chain(style_id):
            if style is not None and style.outline is not None:
                return _outline_to_level(style.outline)
            match = _HEADING_ID_RE.match(sid)
            if match:
                return int(match.group(1))
        return None

    def num_id(self, style_id: str | None) -> str | None:
        for _sid, style in self._chain(style_id):
            if style is not None and style.num_id is not None:
                return style.num_id
        return None


def _is_default(elem: ET.Element, w: str) -> bool:
    value = elem.get(f"{w}default")
    return value is not None and value.lower() in {"1", "true", "on"}


# ---------------------------------------------------------------- 正文遍历


class _BodyWalker:
    def __init__(self, ns: str, styles: _StyleTable) -> None:
        self._w = f"{{{ns}}}"
        self._ns = ns
        self._styles = styles
        self._blocks: list[ParsedBlock] = []
        self._headings: list[tuple[int, str]] = []  # (级别, 规范化标题)
        self._next_paragraph: dict[tuple[str, ...], int] = {}
        self._list_items: list[str] = []
        self._list_num_id: str | None = None

    def walk(self, body: ET.Element) -> list[ParsedBlock]:
        self._walk_container(body)
        self._flush_list()
        return self._blocks

    # -- 结构

    def _local(self, elem: ET.Element) -> str | None:
        tag = elem.tag
        if isinstance(tag, str) and tag.startswith(self._w):
            return tag[len(self._w):]
        return None  # 其他命名空间（mc:AlternateContent、m:oMath 等）一律忽略

    def _children(self, elem: ET.Element) -> Iterator[tuple[str, ET.Element]]:
        """逐个给出 w: 子元素，透明展开内容控件等块级包装。"""
        for child in elem:
            name = self._local(child)
            if name is None:
                continue
            if name in _BLOCK_WRAPPERS:
                yield from self._children(child)
            else:
                yield name, child

    def _walk_container(self, container: ET.Element) -> None:
        for name, child in self._children(container):
            if name == "p":
                self._paragraph(child)
            elif name == "tbl":
                self._flush_list()
                text = self._table_text(child)
                if text:
                    self._emit(text, BlockKind.TABLE)
            # sectPr、bookmarkStart、altChunk 等不含正文，忽略

    def _paragraph(self, p: ET.Element) -> None:
        w = self._w
        ppr = p.find(f"{w}pPr")
        text = self._paragraph_text(p).strip()

        level = self._heading_level(ppr)
        if level is not None:
            title = normalize_heading(text)
            if title:
                self._flush_list()
                while self._headings and self._headings[-1][0] >= level:
                    self._headings.pop()
                self._headings.append((level, title))
            return

        if not text:
            return
        num_id = self._list_num_id_of(ppr)
        if num_id is not None:
            if self._list_items and num_id != self._list_num_id:
                self._flush_list()
            self._list_num_id = num_id
            self._list_items.append(text)
            return
        self._flush_list()
        self._emit(text, BlockKind.PARAGRAPH)

    def _style_id(self, ppr: ET.Element | None) -> str | None:
        if ppr is not None:
            pstyle = ppr.find(f"{self._w}pStyle")
            if pstyle is not None and pstyle.get(f"{self._w}val"):
                return pstyle.get(f"{self._w}val")
        return self._styles.default_id

    def _heading_level(self, ppr: ET.Element | None) -> int | None:
        if ppr is not None:
            outline = _int_val(ppr.find(f"{self._w}outlineLvl"), self._ns)
            if outline is not None:
                return _outline_to_level(outline)
        return self._styles.heading_level(self._style_id(ppr))

    def _list_num_id_of(self, ppr: ET.Element | None) -> str | None:
        w = self._w
        num_id = None
        if ppr is not None:
            num = ppr.find(f"{w}numPr/{w}numId")
            if num is not None:
                num_id = num.get(f"{w}val")
        if num_id is None:
            num_id = self._styles.num_id(self._style_id(ppr))
        return None if num_id in (None, "", "0") else num_id

    # -- 输出

    def _emit(self, text: str, kind: BlockKind) -> None:
        titles = tuple(title for _level, title in self._headings)
        paragraph = self._next_paragraph.get(titles, 1)
        self._next_paragraph[titles] = paragraph + 1
        self._blocks.append(
            ParsedBlock(
                ordinal=len(self._blocks),
                text=text,
                locator=SourceLocator(section_titles=titles, paragraph=paragraph),
                kind=kind,
            )
        )

    def _flush_list(self) -> None:
        if self._list_items:
            self._emit("\n".join(self._list_items), BlockKind.LIST)
        self._list_items = []
        self._list_num_id = None

    # -- 文字

    def _paragraph_text(self, p: ET.Element) -> str:
        out: list[str] = []
        self._collect_inline(p, out)
        return "".join(out)

    def _collect_inline(self, elem: ET.Element, out: list[str]) -> None:
        for child in elem:
            name = self._local(child)
            if name == "r":
                self._run_text(child, out)
            elif name in _INLINE_WRAPPERS:
                self._collect_inline(child, out)
            # del、moveFrom、pPr、批注/书签标记等：忽略

    def _run_text(self, run: ET.Element, out: list[str]) -> None:
        w = self._w
        rpr = run.find(f"{w}rPr")
        if rpr is not None:
            vanish = rpr.find(f"{w}vanish")
            if vanish is not None and _is_on(vanish, self._ns):
                return
        for child in run:
            name = self._local(child)
            if name == "t":
                out.append(child.text or "")
            elif name in ("tab", "ptab"):
                out.append("\t")
            elif name in ("br", "cr"):
                out.append("\n")
            elif name == "noBreakHyphen":
                out.append("-")
            # drawing、pict、object、instrText、delText、fldChar、脚注/批注引用等：忽略

    def _table_text(self, tbl: ET.Element) -> str:
        lines = []
        for name, row in self._children(tbl):
            if name != "tr":
                continue
            cells = [self._cell_text(tc) for cname, tc in self._children(row) if cname == "tc"]
            if any(cells):
                lines.append(" | ".join(cells))
        return "\n".join(lines)

    def _cell_text(self, container: ET.Element) -> str:
        parts: list[str] = []
        for name, child in self._children(container):
            if name == "p":
                text = self._paragraph_text(child).replace("\n", " ").strip()
            elif name == "tbl":
                nested = (
                    self._cell_text(tc)
                    for rname, row in self._children(child)
                    if rname == "tr"
                    for cname, tc in self._children(row)
                    if cname == "tc"
                )
                text = " ".join(t for t in nested if t)
            else:
                continue
            if text:
                parts.append(text)
        return " ".join(parts)
