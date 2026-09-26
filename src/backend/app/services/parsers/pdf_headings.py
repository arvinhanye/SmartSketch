"""D06：PDF 标题判定——由逐行字号、粗体占比与编号正则得到章节树。

输入 D05 的 `PdfLine` 序列（可以是 D07 清洗后的子集，每行自带原始 `page`），输出：

- `detect_headings` → `HeadingResult`：采用的判定策略、正文字号、按文档顺序的标题 `PdfHeading`，
  以及 `tree`（`SectionNode` 章节树）；
- `to_sectioned_document` → D01 `ParsedDocument`：标题行不成块，只进入后续块的 `section_titles`；
  块仍按相邻且 `(page, box)` 相同的行合并，页码取原始页码，不填 `paragraph` 与行号；
- `parse_pdf_with_headings`：`extract_pdf` + 上一步，不做页眉页脚清洗（D07 另行接入）。

**版本**（ADR-018 修订 1）：解析器段内各步骤按处理顺序用 `,` 连接，`+` 只留给修订键的分块段。
`PARSER_VERSION`（`pdf/1,headings/1`）对应不清洗的 `parse_pdf_with_headings`；D11 先经 D07 清洗再判定
标题，须用 `CLEANED_PARSER_VERSION`（`pdf/1,cleanup/1,headings/1`）。

**正文字号**：按非空白字符数加权的最常见字号（相同时取较小者）。

**策略 1：字号层级**（`HeadingStrategy.FONT`）。

1. 大字号行：字号 ≥ 正文字号 + `MIN_SIZE_DELTA`（1pt，兼容五号正文配小四标题）。
2. 相邻的大字号行若样式相同（字号簇与是否整行加粗都相同）、且同页同文本框，或前一行是某页最后一行
   而后一行是紧接下一页的第一行（标题跨页），合并为一个候选；后一行本身以编号开头时不合并。
3. 候选需通过通用标题文本条件（见下），否则整段当正文，例如大字号的导读段落。
4. 通过的候选不少于 `MIN_FONT_HEADINGS`（2）个时采用本策略；否则视为「无字号层级」，改用策略 2。
5. 层级：各样式按（字号簇降序、加粗优先）排序，依次为第 1、2…级；字号相差不超过
   `SIZE_TOLERANCE`（0.5pt）的归为同一簇。
6. 正文字号的行只有同时满足「整行加粗（`bold_ratio ≥ BOLD_LINE_RATIO`，0.8）」「以编号开头
   （D02 `heading_rank`）」「独立成行」（见下）时才是标题，层级排在所有字号层级之后，
   再按编号层级细分。因此行内加粗词、整段加粗的正文、没有编号的短粗体行（如「注意」）都不是标题。

**策略 2：编号正则退路**（`HeadingStrategy.NUMBERING`）：不看字号与粗体，满足 D02 `heading_rank`
（第X章/节、一、、1.1、（一）等，单级「1.」「(1)」视为列表项）且独立成行的行为标题，层级即
`heading_rank` 的返回值。一个标题也没有时为 `HeadingStrategy.NONE`，输出与 D05 `to_parsed_document` 相同。

**独立成行**（用于正文字号的编号行，避免把段落中间或段首的「1.2 节所述……」当标题）：

- 同一文本框中、自上一个标题以来已有以冒号结尾的行 → 列表项，不是标题（与 D02 一致）；
- 同框的前一行存在时，它必须是标题、以句末标点结尾，或没有排满到右边距（段落已结束）；
- 本行排满到右边距且同框下一行不是标题 → 自动换行的段首，不是标题。
  「排满」指 `x1 ≥ 本页最右行的 x1 − 2 × 正文字号`。

**通用标题文本条件**：规范化后 1～`MAX_HEADING_CHARS`（60）字；含字母或汉字（排除页码、符号行）；
不含「。；;」；不以「，,、：:….．」结尾；不含目录引导符（连续 `…` 或 4 个以上的点）。

只有标题、没有正文时，与 D02 一致，关闭标题判定，把所有行当普通段落输出。
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from app.services.parsers import pdf as _pdf
from app.services.parsers.cleanup import CLEANUP_VERSION
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
from app.services.parsers.pdf import PdfLine
from app.services.parsers.txt import heading_rank

__all__ = [
    "BOLD_LINE_RATIO",
    "CLEANED_PARSER_VERSION",
    "HEADINGS_VERSION",
    "MAX_HEADING_CHARS",
    "MIN_FONT_HEADINGS",
    "MIN_SIZE_DELTA",
    "PARSER_VERSION",
    "SIZE_TOLERANCE",
    "HeadingResult",
    "HeadingStrategy",
    "PdfHeading",
    "SectionNode",
    "build_section_tree",
    "detect_headings",
    "parse_pdf_with_headings",
    "to_sectioned_document",
]

#: 标题判定规则的版本；阈值或规则变化时递增。
HEADINGS_VERSION = "headings/1"
#: 带标题判定、未清洗的 PDF 解析结果的 `parser_version`（D05 → D06）。
PARSER_VERSION = ",".join((_pdf.PARSER_VERSION, HEADINGS_VERSION))
#: D05 → D07 清洗 → D06 流水线的 `parser_version`；D11 编排 PDF 时用它。清洗只用默认阈值，
#: 阈值或规则变化时递增 `CLEANUP_VERSION`。
CLEANED_PARSER_VERSION = ",".join((_pdf.PARSER_VERSION, CLEANUP_VERSION, HEADINGS_VERSION))

MIN_SIZE_DELTA = 1.0
SIZE_TOLERANCE = 0.5
BOLD_LINE_RATIO = 0.8
MIN_FONT_HEADINGS = 2
MAX_HEADING_CHARS = 60
_FULL_LINE_EMS = 2.0

_FORBIDDEN_IN_HEADING = frozenset("。；;")
_FORBIDDEN_HEADING_ENDINGS = tuple("，,、：:….．")
_COLON_ENDINGS = (":", "：")
_SENTENCE_ENDINGS = tuple("。！？!?；;")
_LEADER_RE = re.compile(r"(?:…\s*){2,}|(?:[.．·•・]\s*){4,}")


class HeadingStrategy(StrEnum):
    FONT = "font"
    NUMBERING = "numbering"
    NONE = "none"


@dataclass(frozen=True, slots=True)
class PdfHeading:
    """一个标题：`level` 从 1 起（越小越高）；`title` 已 `normalize_heading`；
    `page` 为首行页码；`lines` 为组成标题的原始行（跨行、跨页标题有多行）。"""

    level: int
    title: str
    page: int
    lines: tuple[PdfLine, ...]


@dataclass(frozen=True, slots=True)
class SectionNode:
    """章节树节点：子节点为其后、下一个同级或更高级标题之前的更低级标题。"""

    title: str
    level: int
    page: int
    children: tuple[SectionNode, ...] = ()


@dataclass(frozen=True, slots=True)
class HeadingResult:
    strategy: HeadingStrategy
    body_size: float
    headings: tuple[PdfHeading, ...]

    @property
    def tree(self) -> tuple[SectionNode, ...]:
        return build_section_tree(self.headings)


def detect_headings(lines: Iterable[PdfLine]) -> HeadingResult:
    """判定哪些行是标题及其层级。规则见模块说明；不修改输入。"""
    seq = tuple(lines)
    if not seq:
        return HeadingResult(HeadingStrategy.NONE, 0.0, ())
    ctx = _Context(seq)

    large = _font_runs(ctx)
    if len(large) >= MIN_FONT_HEADINGS:
        taken = {i for run in large for i in run.positions}
        bold_runs = _numbered_runs(ctx, require_bold=True, taken=taken)
        keys = sorted({run.style for run in large}, key=lambda k: (-k[0], not k[1]))
        style_level = {key: n for n, key in enumerate(keys, start=1)}
        ranks = sorted({run.rank for run in bold_runs})
        rank_level = {rank: len(keys) + n for n, rank in enumerate(ranks, start=1)}
        levelled = [(run, style_level[run.style]) for run in large]
        levelled += [(run, rank_level[run.rank]) for run in bold_runs]
        strategy = HeadingStrategy.FONT
    else:
        numbered = _numbered_runs(ctx, require_bold=False, taken=set())
        levelled = [(run, run.rank) for run in numbered]
        strategy = HeadingStrategy.NUMBERING if numbered else HeadingStrategy.NONE

    levelled.sort(key=lambda item: item[0].positions[0])
    headings = tuple(
        PdfHeading(
            level=level,
            title=run.title,
            page=seq[run.positions[0]].page,
            lines=tuple(seq[i] for i in run.positions),
        )
        for run, level in levelled
    )
    return HeadingResult(strategy, ctx.body_size, headings)


def build_section_tree(headings: Iterable[PdfHeading]) -> tuple[SectionNode, ...]:
    """按层级把标题序列组织成树；层级跳跃时挂到最近的更高级标题下，之前没有更高级标题时为根。"""
    roots: list[_Draft] = []
    stack: list[_Draft] = []
    for heading in headings:
        draft = _Draft(heading)
        while stack and stack[-1].heading.level >= heading.level:
            stack.pop()
        (stack[-1].children if stack else roots).append(draft)
        stack.append(draft)
    return tuple(d.freeze() for d in roots)


def to_sectioned_document(
    lines: Iterable[PdfLine],
    headings: HeadingResult | None = None,
    parser_version: str = PARSER_VERSION,
) -> ParsedDocument:
    """把行转成带 `section_titles` 的 `ParsedDocument`。

    `headings` 省略时就地调用 `detect_headings`；传入时必须由同一组行算出。
    没有任何行时抛 `DocumentUnreadableError(no_text)`；全部是标题时退回不带标题的段落。
    """
    seq = tuple(lines)
    if not seq:
        raise DocumentUnreadableError(UnreadableReason.NO_TEXT, "PDF 没有可提取的文本行")
    result = detect_headings(seq) if headings is None else headings

    starts = {(h.lines[0].page, h.lines[0].index): h for h in result.headings if h.lines}
    members = {(line.page, line.index) for h in result.headings for line in h.lines}

    stack: list[PdfHeading] = []
    groups: list[tuple[int, tuple[str, ...], list[str]]] = []
    last_key: tuple[int, int] | None = None
    for line in seq:
        key = (line.page, line.index)
        if key in members:
            heading = starts.get(key)
            if heading is not None:
                while stack and stack[-1].level >= heading.level:
                    stack.pop()
                stack.append(heading)
            last_key = None
            continue
        group_key = (line.page, line.box)
        if group_key != last_key:
            groups.append((line.page, tuple(h.title for h in stack), []))
            last_key = group_key
        groups[-1][2].append(line.text)

    if not groups:
        return _pdf.to_parsed_document(seq, parser_version)
    blocks = tuple(
        ParsedBlock(
            ordinal=ordinal,
            text="\n".join(texts),
            locator=SourceLocator(page=page, section_titles=titles),
            kind=BlockKind.PARAGRAPH,
        )
        for ordinal, (page, titles, texts) in enumerate(groups)
    )
    return ParsedDocument(SourceFormat.PDF, parser_version, blocks)


def parse_pdf_with_headings(data: bytes) -> ParsedDocument:
    """`extract_pdf` + 标题判定；不做页眉页脚清洗。"""
    return to_sectioned_document(_pdf.extract_pdf(data).lines)


# ---------------------------------------------------------------------------
# 内部实现
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class _Draft:
    heading: PdfHeading
    children: list[_Draft] = field(default_factory=list)

    def freeze(self) -> SectionNode:
        h = self.heading
        return SectionNode(h.title, h.level, h.page, tuple(c.freeze() for c in self.children))


@dataclass(frozen=True, slots=True)
class _Run:
    positions: tuple[int, ...]
    title: str
    style: tuple[float, bool] = (0.0, False)
    rank: int = 0


class _Context:
    """一次判定所需的派生量：正文字号、字号簇、每页右边距。"""

    def __init__(self, seq: Sequence[PdfLine]) -> None:
        self.seq = seq
        self.body_size = _body_size(seq)
        self.page_right: dict[int, float] = {}
        for line in seq:
            self.page_right[line.page] = max(self.page_right.get(line.page, line.x1), line.x1)
        self.size_cluster = _cluster_sizes(
            {line.font_size for line in seq if self.is_large(line)}
        )

    def is_large(self, line: PdfLine) -> bool:
        return line.font_size >= self.body_size + MIN_SIZE_DELTA

    def style(self, line: PdfLine) -> tuple[float, bool]:
        return (self.size_cluster.get(line.font_size, line.font_size), _bold_line(line))

    def same_box(self, i: int, j: int) -> bool:
        a, b = self.seq[i], self.seq[j]
        return a.page == b.page and a.box == b.box

    def is_full(self, line: PdfLine) -> bool:
        return line.x1 >= self.page_right[line.page] - _FULL_LINE_EMS * self.body_size


def _body_size(seq: Sequence[PdfLine]) -> float:
    weights: Counter[float] = Counter()
    for line in seq:
        weights[line.font_size] += sum(1 for ch in line.text if not ch.isspace())
    return max(weights.items(), key=lambda item: (item[1], -item[0]))[0]


def _cluster_sizes(sizes: set[float]) -> dict[float, float]:
    """降序排列，与前一个相差不超过 `SIZE_TOLERANCE` 的归入同一簇；代表值取簇内最大字号。"""
    mapping: dict[float, float] = {}
    representative = previous = None
    for size in sorted(sizes, reverse=True):
        if previous is None or previous - size > SIZE_TOLERANCE:
            representative = size
        mapping[size] = representative  # type: ignore[assignment]
        previous = size
    return mapping


def _bold_line(line: PdfLine) -> bool:
    return line.bold_ratio >= BOLD_LINE_RATIO


def _join(parts: Iterable[str]) -> str:
    """拼接跨行标题：两侧都是 ASCII 字符时加空格，否则（中文）直接相连。"""
    out = ""
    for part in parts:
        part = part.strip()
        if out and part and out[-1].isascii() and part[0].isascii():
            out += " "
        out += part
    return out


def _plain_title_ok(title: str) -> bool:
    if not title or len(title) > MAX_HEADING_CHARS:
        return False
    if any(ch in _FORBIDDEN_IN_HEADING for ch in title) or title.endswith(_FORBIDDEN_HEADING_ENDINGS):
        return False
    if _LEADER_RE.search(title):
        return False
    return any(ch.isalpha() for ch in title)


def _font_runs(ctx: _Context) -> list[_Run]:
    seq = ctx.seq
    runs: list[_Run] = []
    i = 0
    while i < len(seq):
        if not ctx.is_large(seq[i]):
            i += 1
            continue
        style = ctx.style(seq[i])
        j = i + 1
        while (
            j < len(seq)
            and ctx.is_large(seq[j])
            and ctx.style(seq[j]) == style
            and _continues(seq[j - 1], seq[j], ctx.same_box(j - 1, j))
            and heading_rank(seq[j].text) is None
        ):
            j += 1
        title = normalize_heading(_join(seq[k].text for k in range(i, j)))
        if _plain_title_ok(title):
            runs.append(_Run(tuple(range(i, j)), title, style=style))
        i = j
    return runs


def _continues(prev: PdfLine, cur: PdfLine, same_box: bool) -> bool:
    """同页同框，或 `prev` 是一页的最后一行、`cur` 是紧接下一页的第一行（二者在序列中相邻）。"""
    return same_box or cur.page == prev.page + 1


def _numbered_runs(ctx: _Context, *, require_bold: bool, taken: set[int]) -> list[_Run]:
    seq = ctx.seq
    heading_positions = set(taken)
    runs: list[_Run] = []
    i = 0
    while i < len(seq):
        line = seq[i]
        rank = heading_rank(line.text)
        if (
            i in taken
            or (require_bold and not _bold_line(line))
            or rank is None
            or _LEADER_RE.search(line.text)
            or not _starts_standalone(ctx, i, heading_positions)
        ):
            i += 1
            continue
        j = i + 1
        if require_bold:  # 加粗编号标题自动换行的续行
            while (
                j < len(seq)
                and j not in taken
                and _bold_line(seq[j])
                and ctx.same_box(j - 1, j)
                and heading_rank(seq[j].text) is None
                and heading_rank(_join(seq[k].text for k in range(i, j + 1))) is not None
            ):
                j += 1
        title = normalize_heading(_join(seq[k].text for k in range(i, j)))
        wraps_into_body = (
            j < len(seq) and j not in taken and ctx.same_box(j - 1, j) and ctx.is_full(seq[j - 1])
        )
        if wraps_into_body or not _plain_title_ok(title):
            i += 1
            continue
        runs.append(_Run(tuple(range(i, j)), title, rank=heading_rank(title) or rank))
        heading_positions.update(range(i, j))
        i = j
    return runs


def _starts_standalone(ctx: _Context, i: int, heading_positions: set[int]) -> bool:
    seq = ctx.seq
    k = i - 1
    while k >= 0 and ctx.same_box(k, i) and k not in heading_positions:
        if seq[k].text.rstrip().endswith(_COLON_ENDINGS):
            return False
        k -= 1
    if i == 0 or not ctx.same_box(i - 1, i) or (i - 1) in heading_positions:
        return True
    prev = seq[i - 1]
    return prev.text.rstrip().endswith(_SENTENCE_ENDINGS) or not ctx.is_full(prev)
