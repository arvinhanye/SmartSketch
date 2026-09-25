"""D03：Markdown AST 解析。

用 markdown-it-py（CommonMark 规则 + GFM 表格）把 UTF-8 Markdown 解析成 token 流，
只取**顶层**块 token 与其 `map` 行号，产出 D01 的 `ParsedDocument`。不按正则逐行猜结构，
因此围栏/缩进代码块、引用块、列表项里以 `#` 开头的行都不会被当成标题。

规则（详见 `docs/handoffs/claude-d03.md`）：

- **解码**：严格 UTF-8，允许并去掉开头的 BOM；解码失败或含 NUL 字节 → `DocumentUnreadableError(corrupted)`。
  不做 GBK 等回退（Markdown 生态默认 UTF-8，编码探测归 D02 的 TXT）。
- **行号**：`\\r\\n` 与单独的 `\\r` 先统一为 `\\n`（与 markdown-it 自身的规范化一致），再按 `\\n` 计物理行，
  从 1 起、闭区间。块的行区间来自顶层 token 的 `map`，并去掉尾部空行；块文本就是这些原文行，原样保留
  行内标记与缩进，D08 可凭行号映射回原文。
- **标题**：顶层 ATX 与 Setext 标题只更新章节路径，不成块。标题文本取行内纯文本（去掉强调、链接、
  行内代码等标记，图片取替代文本），再经 `normalize_heading`。层级跳跃时只保留真实祖先
  （如 `#` 后接 `###`，路径为两级）；新标题关闭所有同级及更深的标题。空标题忽略。
  引用块、列表项内部的标题不改变章节路径，随所在块保留在文本中。
- **放宽的无空格标题**（ArvinHan 决定，仍为 `markdown/1`）：CommonMark 要求 `#` 后有空格；本解析器另外
  接受「行首 1～6 个 `#`，紧跟一个非 ASCII、非空白、非 `#` 的字符」的写法，如 `#第一章`、`##概述`、
  `#（一）背景`，层级按 `#` 数量。紧跟 ASCII 字符的行（`#include`、`#1`、`#tag`、`#!/bin/sh`、
  `###1.1顺序表`）、紧跟全角空格的行、`\\#` 转义、结尾 `#` 紧贴文字的话题标签（`#话题#`）都不放宽。
  实现为 markdown-it 块规则，出现位置与标准 ATX 标题相同（可打断段落，缩进 4 格为代码），
  不改源文本，token 行号不变。
- **块类型**：段落 → PARAGRAPH；有序/无序列表（含嵌套）整体 → LIST；表格 → TABLE；
  围栏与缩进代码块 → CODE；引用块整体 → PARAGRAPH；HTML 块 → PARAGRAPH（纯 HTML 注释丢弃）；
  分隔线、链接引用定义不成块；去掉空白后为空的块（空代码块、全角空格行）丢弃。
- **front matter**：仅当第 1 行是 `---` 且后面有 `---` 或 `...` 闭合行时，视为 YAML front matter，
  整段不成块、不参与标题（避免 `key: v` + `---` 被 CommonMark 读成 Setext 标题）；行号不受影响。
  未闭合时按普通 Markdown 处理。
- **空文**：没有任何正文块（空文件、只有空白、只有标题/front matter/注释/分隔线）→
  `DocumentUnreadableError(no_text)`，不构造空结果。
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from markdown_it import MarkdownIt
from markdown_it.rules_block import StateBlock
from markdown_it.token import Token

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

__all__ = ["PARSER_VERSION", "parse_markdown"]

#: 解析器版本，进入 `RevisionKey.parser_version`。解析规则或依赖版本变化导致输出不同时递增。
PARSER_VERSION = "markdown/1"

#: 放宽的 ATX 标题：行首 1～6 个 `#`，紧跟一个非 ASCII、非空白、非 `#` 的字符（如 `#第一章`）。
_LOOSE_HEADING_RE = re.compile(r"(#{1,6})([^\x00-\x7f\s#].*)\Z", re.DOTALL)
#: 标准 ATX 的收尾序列：空白后接若干 `#`（`#标题 ##` → `标题`）。
_CLOSING_SEQUENCE_RE = re.compile(r"[ \t]+#+\Z")


def _loose_heading(state: StateBlock, start_line: int, end_line: int, silent: bool) -> bool:
    """markdown-it 块规则：把 `#第一章` 这类无空格写法当作 ATX 标题（ArvinHan 决定放宽）。

    与内置 `heading` 规则同样判断缩进代码块、同样可以打断段落/引用块，因此只在标准 ATX 标题能出现的
    位置生效；围栏代码块的行由 `fence` 规则整体吃掉，不会走到这里。引用块、列表项内部产生的标题
    token 位于嵌套层级，`parse_markdown` 只看顶层 token，不改变章节路径。
    """
    if state.is_code_block(start_line):
        return False
    pos = state.bMarks[start_line] + state.tShift[start_line]
    line = state.src[pos : state.eMarks[start_line]]
    match = _LOOSE_HEADING_RE.match(line)
    if match is None:
        return False
    content = match.group(2).rstrip()
    closing = _CLOSING_SEQUENCE_RE.search(content)
    if closing is not None:
        content = content[: closing.start()]
    elif content.endswith("#"):
        return False  # `#话题#` 形式的话题标签，不当标题
    if silent:
        return True

    level = len(match.group(1))
    state.line = start_line + 1
    token = state.push("heading_open", f"h{level}", 1)
    token.markup = match.group(1)
    token.map = [start_line, state.line]
    token = state.push("inline", "", 0)
    token.content = content.strip()
    token.map = [start_line, state.line]
    token.children = []
    token = state.push("heading_close", f"h{level}", -1)
    token.markup = match.group(1)
    return True


_MD = MarkdownIt("commonmark", {"html": True}).enable("table")
_MD.block.ruler.before(
    "heading", "loose_heading", _loose_heading, {"alt": ["paragraph", "reference", "blockquote"]}
)

_BLOCK_KINDS: dict[str, BlockKind] = {
    "paragraph_open": BlockKind.PARAGRAPH,
    "blockquote_open": BlockKind.PARAGRAPH,
    "html_block": BlockKind.PARAGRAPH,
    "bullet_list_open": BlockKind.LIST,
    "ordered_list_open": BlockKind.LIST,
    "table_open": BlockKind.TABLE,
    "fence": BlockKind.CODE,
    "code_block": BlockKind.CODE,
}
_SKIPPED = {"hr", "heading_open"}
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_FRONT_MATTER_OPEN = "---"
_FRONT_MATTER_CLOSE = {"---", "..."}


def parse_markdown(data: bytes | bytearray | memoryview) -> ParsedDocument:
    """把 Markdown 原始字节解析为 `ParsedDocument`。

    Raises:
        TypeError: 输入不是字节。
        DocumentUnreadableError: `corrupted`（非 UTF-8 或含 NUL 字节）、`no_text`（没有正文）。
    """
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError(f"parse_markdown 需要 bytes，收到 {type(data).__name__}")
    text = _decode(bytes(data))
    lines = text.split("\n")
    tokens = _MD.parse("\n".join(_blank_front_matter(lines)))

    blocks: list[ParsedBlock] = []
    headings: list[tuple[int, str]] = []  # (级别, 规范化标题)，即当前章节路径
    next_paragraph: dict[tuple[str, ...], int] = {}
    saw_heading = False

    for i, token in enumerate(tokens):
        if token.level != 0 or token.nesting == -1:
            continue
        if token.type == "heading_open":
            title = normalize_heading(_inline_plain_text(tokens[i + 1]))
            if title:
                saw_heading = True
                level = int(token.tag[1:])
                while headings and headings[-1][0] >= level:
                    headings.pop()
                headings.append((level, title))
            continue
        if token.type in _SKIPPED or token.map is None:
            continue
        if not _has_content(token):
            continue

        start, end = _trim_blank_lines(lines, token.map[0], token.map[1])
        block_text = "\n".join(lines[start:end])
        if not block_text.strip():
            continue

        titles = tuple(title for _, title in headings)
        paragraph = next_paragraph.get(titles, 1)
        next_paragraph[titles] = paragraph + 1
        blocks.append(
            ParsedBlock(
                ordinal=len(blocks),
                text=block_text,
                kind=_BLOCK_KINDS.get(token.type, BlockKind.PARAGRAPH),
                locator=SourceLocator(
                    section_titles=titles,
                    paragraph=paragraph,
                    line_start=start + 1,
                    line_end=end,
                ),
            )
        )

    if not blocks:
        detail = "只有标题，没有正文" if saw_heading else "没有可提取的正文"
        raise DocumentUnreadableError(UnreadableReason.NO_TEXT, detail)
    return ParsedDocument(
        source_format=SourceFormat.MARKDOWN, parser_version=PARSER_VERSION, blocks=tuple(blocks)
    )


def _decode(data: bytes) -> str:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DocumentUnreadableError(
            UnreadableReason.CORRUPTED, f"不是有效的 UTF-8：第 {exc.start} 字节起无法解码"
        ) from None
    if "\x00" in text:
        raise DocumentUnreadableError(UnreadableReason.CORRUPTED, "含 NUL 字节，疑似二进制文件")
    if text.startswith("\ufeff"):
        text = text[1:]
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _blank_front_matter(lines: Sequence[str]) -> list[str]:
    """把开头闭合的 YAML front matter 换成空行后交给 markdown-it，保持行号不变。"""
    out = list(lines)
    if not out or out[0].rstrip() != _FRONT_MATTER_OPEN:
        return out
    for close in range(1, len(out)):
        if out[close].rstrip() in _FRONT_MATTER_CLOSE:
            out[: close + 1] = [""] * (close + 1)
            break
    return out


def _has_content(token: Token) -> bool:
    if token.type in ("fence", "code_block"):
        return bool(token.content.strip())
    if token.type == "html_block":
        return bool(_HTML_COMMENT_RE.sub("", token.content).strip())
    return True


def _trim_blank_lines(lines: Sequence[str], start: int, end: int) -> tuple[int, int]:
    """`map` 是 0 起的半开区间，可能含尾部空行；去掉首尾空行后仍返回半开区间。"""
    end = min(end, len(lines))
    while start < end and not lines[start].strip():
        start += 1
    while end > start and not lines[end - 1].strip():
        end -= 1
    return start, end


def _inline_plain_text(inline: Token) -> str:
    """标题的行内纯文本：保留文字、行内代码与图片替代文本，丢弃标记与内联 HTML。"""
    parts: list[str] = []
    for child in inline.children or ():
        if child.type in ("text", "text_special", "code_inline"):
            parts.append(child.content)
        elif child.type in ("softbreak", "hardbreak"):
            parts.append(" ")
        elif child.type == "image":
            parts.append(_inline_plain_text(child))
    return "".join(parts)
