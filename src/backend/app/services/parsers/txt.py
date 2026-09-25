"""D02：TXT 解析器——编码检测、按行分段与中文编号标题识别。

输入原始字节，输出 D01 的 `ParsedDocument(SourceFormat.TXT, "txt/1", blocks)`。只用标准库，无 I/O。

编码检测（`decode_txt`），按顺序：

1. 以 UTF-8 BOM（EF BB BF）开头：视为声明了 UTF-8，去掉 BOM 后严格按 UTF-8 解码；
   解不开即 `corrupted`，不再尝试 GBK。
2. 否则严格按 UTF-8 解码，成功即为 UTF-8。
3. UTF-8 失败时，若第一个错误就是文末被截断的多字节字符、且此前已有合法的非 ASCII 字符，
   判定为被截断的 UTF-8 并报 `corrupted`：这类字节常常恰好能按 GBK 解码，回退 GBK 只会得到乱码。
4. 否则严格按 GBK 解码，成功即为 GBK；仍失败则 `corrupted`。
5. 解码结果含 NUL（U+0000）时报 `corrupted`：通常是改了扩展名的二进制或 UTF-16。

无法解码用 `corrupted`：`DOCUMENT_UNREADABLE.reason` 闭集只有 corrupted / encrypted / no_text，
字节存在但无法还原为文本属于资料损坏；`no_text` 只用于解码成功但没有可见文本（空文件、只有空白或 BOM）。

分段（`parse_txt`）：

- 物理行只按 CRLF、CR、LF 切分（不用 `str.splitlines`，避免 \\f、U+2028 等额外断行），行号从 1 起。
  文末的 Ctrl-Z（\\x1a，DOS 文件结束符）忽略。
- 空行（只含空白，包括全角空格）分隔段落；标题行本身也结束当前段落，标题不成块。
- 以全角空格（U+3000）开头的行开始新段落，适配「首行缩进两字、段间无空行」的中文排版。
- 块文本是该块各物理行原文按 `\\n` 连接，不去首尾空白，可按 `line_start..line_end` 映射回源文本。
- 段落号按 D01 规则：同一 `section_titles` 下从 1 起连续，同一路径再次出现时接续。
- 整篇只有标题、没有正文时，关闭标题判定重新分段，把这些行当普通段落输出，而不是丢弃文本。

标题判定（`heading_rank`，对去掉首尾空白的整行）：

- 通用条件：非空、不超过 40 字；不含「。」「；」「;」；不以「，,、：:….．」结尾。
- 编号形式与层级（数字越小层级越高）：

  | 形式 | 例 | 层级 |
  | --- | --- | --- |
  | 第X章 / 讲 / 课 / 单元 / 部分 / 篇 | 第一章 线性表、第3讲：栈 | 1 |
  | 第X节 | 第一节 顺序栈 | 2 |
  | 中文数字 + 「、」 | 一、基本术语 | 3 |
  | 两级数字编号 | 1.1 顺序表 | 3 |
  | （中文数字） | （一）入栈 | 4 |
  | 三级 / 四级数字编号 | 1.1.1 逻辑结构 | 4 / 5 |

  X 可为中文数字、阿拉伯数字或全角数字。「第X章」后必须是行尾、空白或「：:、.．」之一；
  中文数字编号和括号编号后必须有标题文字；数字编号的首段为 1～99、其余各段为 0～99 且无前导零，
  最多四级，后接空白再接标题，或直接接汉字。
- 单级阿拉伯编号（「1.」「1、」「(1)」）一律视为列表项，不当标题；没有编号的行不当标题。
- 紧跟在以冒号结尾的正文行之后的编号行（中间没有空行）视为列表项，直到下一个空行。
- 新标题弹出层级 ≥ 自身的所有祖先后入栈；`section_titles` 即当前标题栈（已 `normalize_heading`）。
"""

from __future__ import annotations

import re
from typing import NamedTuple

from app.services.parsers.models import (
    DocumentUnreadableError,
    ParsedBlock,
    ParsedDocument,
    SourceFormat,
    SourceLocator,
    UnreadableReason,
    normalize_heading,
)

__all__ = ["PARSER_VERSION", "DecodedText", "decode_txt", "heading_rank", "parse_txt"]

#: 解析器版本；标题或分段规则有任何改变都要递增，使资料修订（ADR-012 修订 1）随之变化。
PARSER_VERSION = "txt/1"

_UTF8_BOM = b"\xef\xbb\xbf"
_EOF_MARKER = "\x1a"
_FULL_WIDTH_SPACE = "\u3000"
_NEWLINE_RE = re.compile(r"\r\n|\r|\n")

_MAX_HEADING_CHARS = 40
_FORBIDDEN_IN_HEADING = frozenset("。；;")
_FORBIDDEN_HEADING_ENDINGS = tuple("，,、：:….．")
_COLON_ENDINGS = (":", "：")

_CN_DIGITS = "〇零一二三四五六七八九十百千两"
_ANY_NUMBER = rf"[{_CN_DIGITS}0-9０-９]+"
_AFTER_UNIT = r"(?:$|[\s:：、.．])"

_CHAPTER_RE = re.compile(rf"^第{_ANY_NUMBER}(?:章|讲|课|单元|部分|篇){_AFTER_UNIT}")
_SECTION_RE = re.compile(rf"^第{_ANY_NUMBER}节{_AFTER_UNIT}")
_CN_ENUM_RE = re.compile(rf"^[{_CN_DIGITS}]+、\s*\S")
_CN_PAREN_RE = re.compile(rf"^[（(][{_CN_DIGITS}]+[）)]\s*\S")
_DOTTED_RE = re.compile(
    r"^([1-9][0-9]?(?:\.(?:0|[1-9][0-9]?)){1,3})\.?(?:\s+\S|(?=[\u4e00-\u9fff]))"
)


class DecodedText(NamedTuple):
    text: str
    #: `utf-8`、`utf-8-sig`（带 BOM）或 `gbk`
    encoding: str


def _corrupted(detail: str) -> DocumentUnreadableError:
    return DocumentUnreadableError(UnreadableReason.CORRUPTED, detail)


def _is_truncated_utf8(data: bytes, error: UnicodeDecodeError) -> bool:
    """第一个 UTF-8 错误就是文末被截断的多字节字符，且此前已有合法的非 ASCII 字符。"""
    if error.reason != "unexpected end of data" or error.end != len(data):
        return False
    return any(ch > "\x7f" for ch in data[: error.start].decode("utf-8"))


def decode_txt(data: bytes) -> DecodedText:
    """按模块说明的顺序把字节解码为文本；无法解码抛 `DocumentUnreadableError(corrupted)`。

    只负责解码：空文本不在这里报错（由 `parse_txt` 报 `no_text`）。
    """
    if not isinstance(data, bytes):
        raise TypeError(f"TXT 解析器只接受 bytes，收到 {type(data).__name__}")

    if data.startswith(_UTF8_BOM):
        try:
            decoded = DecodedText(data[len(_UTF8_BOM) :].decode("utf-8"), "utf-8-sig")
        except UnicodeDecodeError as exc:
            raise _corrupted(f"带 UTF-8 BOM，但第 {exc.start + len(_UTF8_BOM)} 字节起不是合法 UTF-8") from None
    else:
        try:
            decoded = DecodedText(data.decode("utf-8"), "utf-8")
        except UnicodeDecodeError as exc:
            if _is_truncated_utf8(data, exc):
                raise _corrupted(f"UTF-8 文本在第 {exc.start} 字节处被截断") from None
            try:
                decoded = DecodedText(data.decode("gbk"), "gbk")
            except UnicodeDecodeError:
                raise _corrupted("既不是合法的 UTF-8，也不是合法的 GBK") from None

    if "\x00" in decoded.text:
        raise _corrupted(f"按 {decoded.encoding} 解码后含 NUL 字符，疑似二进制文件或 UTF-16 文本")
    return decoded


def heading_rank(line: str) -> int | None:
    """若整行是编号标题，返回层级（1 最高）；否则返回 None。规则见模块说明。"""
    text = line.strip()
    if not text or len(text) > _MAX_HEADING_CHARS:
        return None
    if any(ch in _FORBIDDEN_IN_HEADING for ch in text) or text.endswith(_FORBIDDEN_HEADING_ENDINGS):
        return None
    if _CHAPTER_RE.match(text):
        return 1
    if _SECTION_RE.match(text):
        return 2
    dotted = _DOTTED_RE.match(text)
    if dotted:
        depth = dotted.group(1).count(".") + 1
        return 1 + depth
    if _CN_ENUM_RE.match(text):
        return 3
    if _CN_PAREN_RE.match(text):
        return 4
    return None


class _BlockBuilder:
    """逐行累积段落，并按当前标题路径分配段落号。"""

    def __init__(self) -> None:
        self.blocks: list[ParsedBlock] = []
        self._headings: list[tuple[int, str]] = []
        self._next_paragraph: dict[tuple[str, ...], int] = {}
        self._lines: list[str] = []
        self._start = 0

    @property
    def in_paragraph(self) -> bool:
        return bool(self._lines)

    def add_line(self, line_no: int, line: str) -> None:
        if not self._lines:
            self._start = line_no
        self._lines.append(line)

    def enter_heading(self, rank: int, line: str) -> None:
        self.flush()
        while self._headings and self._headings[-1][0] >= rank:
            self._headings.pop()
        self._headings.append((rank, normalize_heading(line)))

    def flush(self) -> None:
        if not self._lines:
            return
        titles = tuple(title for _, title in self._headings)
        paragraph = self._next_paragraph.get(titles, 1)
        self._next_paragraph[titles] = paragraph + 1
        self.blocks.append(
            ParsedBlock(
                ordinal=len(self.blocks),
                text="\n".join(self._lines),
                locator=SourceLocator(
                    section_titles=titles,
                    paragraph=paragraph,
                    line_start=self._start,
                    line_end=self._start + len(self._lines) - 1,
                ),
            )
        )
        self._lines = []


def _build_blocks(lines: list[str], *, detect_headings: bool) -> list[ParsedBlock]:
    builder = _BlockBuilder()
    after_colon = False  # 当前段落里已出现以冒号结尾的行：其后的编号行是列表项
    for line_no, line in enumerate(lines, start=1):
        if not line.strip():
            builder.flush()
            after_colon = False
            continue
        rank = heading_rank(line) if detect_headings and not after_colon else None
        if rank is not None:
            builder.enter_heading(rank, line)
            continue
        if builder.in_paragraph and line.startswith(_FULL_WIDTH_SPACE):
            builder.flush()
        builder.add_line(line_no, line)
        if line.rstrip().endswith(_COLON_ENDINGS):
            after_colon = True
    builder.flush()
    return builder.blocks


def parse_txt(data: bytes) -> ParsedDocument:
    """把 TXT 字节解析为带行号、章节路径与段落号的 `ParsedDocument`。

    无法解码抛 `DocumentUnreadableError(corrupted)`；没有可见文本抛 `DocumentUnreadableError(no_text)`。
    """
    text = decode_txt(data).text.rstrip(_EOF_MARKER)
    lines = _NEWLINE_RE.split(text)
    if not any(line.strip() for line in lines):
        raise DocumentUnreadableError(UnreadableReason.NO_TEXT, "TXT 解码后没有可见文本")

    blocks = _build_blocks(lines, detect_headings=True)
    if not blocks:
        blocks = _build_blocks(lines, detect_headings=False)
    return ParsedDocument(source_format=SourceFormat.TXT, parser_version=PARSER_VERSION, blocks=tuple(blocks))
