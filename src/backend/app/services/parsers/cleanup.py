"""D07：PDF 分页行的重复页眉、页脚与页码清洗。

输入 D05 的分页行（`PdfExtraction` 或 `PdfPage` 序列），输出 `CleanupResult`：

- `lines`：保留下来的原始 `PdfLine` 对象，顺序不变，**每行仍带原始物理页码** `page`，
  可直接交给 `pdf.to_parsed_document`，删掉页码行不影响来源定位；
- `removed`：被删的行及原因（页眉 / 页脚 / 页码）；
- `text` 与 `spans`：清洗后文本（保留行以 `\\n` 连接）及其位置映射。`locate(offset)` 给出
  清洗后任一位置所在的原始页与页内行号，`to_original(offset)` 给出它在原始全文
  （全部行以 `\\n` 连接，即 `original_text`）中的偏移。

判定规则（只删「位于页首/页尾且跨页重复」的行，重复正文不动）：

1. **页边位置**：一行必须同时满足
   - 整行落在页边带内：页眉带要求行底 `y0 ≥ 页高 × (1 − header_ratio)`，
     页脚带要求行顶 `y1 ≤ 页高 × footer_ratio`（PDF 坐标原点在左下角）；
   - 且按几何位置是本页最靠上（页眉）或最靠下（页脚）的 `edge_lines` 行之一。
     按坐标而不是阅读顺序排名，页眉被最后绘制时也能识别。
2. **跨页重复**：把候选行归一成「模式」——NFKC（全角数字转半角）、合并空白、忽略大小写、
   连续数字记为 `#`；整行是页码（`3`、`- 3 -`、`第 3 页 共 9 页`、`Page 3 of 9`、`3 / 9`、
   `iv` 等）时模式统一为页码。同一页边（页眉、页脚分别统计）的同一模式出现在
   **至少 `max(2, min(min_pages, 有文字的页数))` 个不同页**才删除。空白页不计入页数。
   所以单页文档永不清洗，两页文档需要两页都出现。
3. **兜底**：如果清洗会删光全部行（整份资料只有重复的页边文字），放弃清洗、原样返回，
   `applied=False`，避免下游把它误报为 `no_text`。
4. **关闭清洗**：`CleanupOptions(enabled=False)` 时输出与输入等价——`lines` 为全部行、
   `text == original_text`、映射为恒等（`to_original(i) == i`）。

本模块只过滤行、不改写行文本，也不读取印刷页码来改写定位：来源页码始终是物理页序号。
"""

from __future__ import annotations

import re
import unicodedata
from bisect import bisect_right
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from app.services.parsers.pdf import PdfExtraction, PdfLine, PdfPage

__all__ = [
    "CLEANUP_VERSION",
    "CleanupOptions",
    "CleanupResult",
    "LineSpan",
    "RemovalReason",
    "RemovedLine",
    "clean_pages",
]

#: 清洗规则版本。判定规则或默认阈值变化时递增；D11 编排时可并入修订的解析器版本。
CLEANUP_VERSION = "cleanup/1"

_PAGE_NUMBER_KEY = "<page-number>"
_SEPARATOR = "\n"

_WHITESPACE_RE = re.compile(r"\s+")
_DIGITS_RE = re.compile(r"\d+")
_ROMAN = r"(?:x{0,3}(?:ix|iv|v?i{0,3}))"  # 1～39，前言页码足够；限制长度以免误认 mix、civil 等单词
_PAGE_NUMBER_RE = re.compile(
    r"^(?:"
    rf"[-–—~·•\s]*(?:\d+|{_ROMAN})[-–—~·•\s]*"  # 3、- 3 -、— 3 —、iv
    r"|第\s*\d+\s*页(?:\s*[,，/]?\s*共\s*\d+\s*页)?"  # 第 3 页、第3页 共 9 页
    r"|(?:page|pp?\.?)\s*\d+(?:\s*(?:of|/)\s*\d+)?"  # Page 3、Page 3 of 9、p. 3
    r"|\d+\s*/\s*\d+"  # 3 / 9
    r")$"
)


class RemovalReason(StrEnum):
    HEADER = "header"
    FOOTER = "footer"
    PAGE_NUMBER = "page_number"


@dataclass(frozen=True, slots=True)
class CleanupOptions:
    """清洗开关与阈值。默认值见模块说明；`enabled=False` 时其余参数不生效。"""

    enabled: bool = True
    header_ratio: float = 0.10
    footer_ratio: float = 0.10
    edge_lines: int = 2
    min_pages: int = 3

    def __post_init__(self) -> None:
        for name in ("header_ratio", "footer_ratio"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value <= 0.5:
                raise ValueError(f"{name} 必须在 (0, 0.5] 内，收到 {value!r}")
        if isinstance(self.edge_lines, bool) or not isinstance(self.edge_lines, int) or self.edge_lines < 1:
            raise ValueError(f"edge_lines 必须是 ≥ 1 的整数，收到 {self.edge_lines!r}")
        if isinstance(self.min_pages, bool) or not isinstance(self.min_pages, int) or self.min_pages < 2:
            raise ValueError(f"min_pages 必须是 ≥ 2 的整数（单页出现不算重复），收到 {self.min_pages!r}")


@dataclass(frozen=True, slots=True)
class LineSpan:
    """一条保留行在清洗后文本中的位置，以及它的原始出处。

    `start`/`end`：清洗后文本中的半开区间 `[start, end)`，恰为该行文本；
    `original_start`：该行在 `original_text` 中的起始偏移；`page`/`index`：原始物理页与页内行号。
    """

    start: int
    end: int
    original_start: int
    line: PdfLine

    @property
    def page(self) -> int:
        return self.line.page

    @property
    def index(self) -> int:
        return self.line.index


@dataclass(frozen=True, slots=True)
class RemovedLine:
    """被删除的一行：原始行对象（含原始页码）、原因及其在 `original_text` 中的起始偏移。"""

    line: PdfLine
    reason: RemovalReason
    original_start: int


@dataclass(frozen=True, slots=True)
class CleanupResult:
    """清洗结果。`applied` 为 False 表示未做任何删除（关闭清洗或触发兜底）。"""

    lines: tuple[PdfLine, ...]
    removed: tuple[RemovedLine, ...]
    spans: tuple[LineSpan, ...]
    text: str
    original_text: str
    applied: bool

    def locate(self, offset: int) -> LineSpan:
        """清洗后文本位置 → 所在保留行（含原始页与行号）。

        取值 `0 ≤ offset ≤ len(text)`；行间换行符归属前一行，`len(text)` 归属最后一行。
        """
        return self.spans[self._span_index(offset)]

    def to_original(self, offset: int) -> int:
        """清洗后文本位置 → `original_text` 中的对应位置；关闭清洗时为恒等映射。"""
        span = self.locate(offset)
        return span.original_start + (offset - span.start)

    def spans_between(self, start: int, end: int) -> tuple[LineSpan, ...]:
        """清洗后文本半开区间 `[start, end)` 覆盖的保留行；空区间返回 `start` 所在行。"""
        if end < start:
            raise ValueError(f"区间终点 {end} 小于起点 {start}")
        first = self._span_index(start)
        last = first if end == start else self._span_index(end - 1)
        return self.spans[first : last + 1]

    def _span_index(self, offset: int) -> int:
        if not self.spans or not 0 <= offset <= len(self.text):
            raise IndexError(f"offset {offset} 超出清洗后文本范围 [0, {len(self.text)}]")
        return bisect_right(self.spans, offset, key=lambda s: s.start) - 1


def clean_pages(
    source: PdfExtraction | Iterable[PdfPage],
    options: CleanupOptions | None = None,
) -> CleanupResult:
    """删除跨页重复的页眉、页脚与页码行，返回保留行、清洗后文本与位置映射。"""
    options = options or CleanupOptions()
    pages = _checked_pages(source)
    all_lines = tuple(line for page in pages for line in page.lines)

    reasons = _detect(pages, options) if options.enabled else {}
    if len(reasons) == len(all_lines):
        reasons = {}  # 兜底：不删光整份资料
    return _build(all_lines, reasons)


# ---------------------------------------------------------------------------
# 内部实现
# ---------------------------------------------------------------------------


def _checked_pages(source: PdfExtraction | Iterable[PdfPage]) -> tuple[PdfPage, ...]:
    pages = tuple(source.pages if isinstance(source, PdfExtraction) else source)
    last = 0
    for page in pages:
        if not isinstance(page, PdfPage):
            raise TypeError(f"clean_pages 需要 PdfPage 序列，收到 {type(page).__name__}")
        if page.number <= last:
            raise ValueError(f"页序必须按 page.number 严格递增：第 {page.number} 页出现在第 {last} 页之后")
        last = page.number
        for line in page.lines:
            if line.page != page.number:
                raise ValueError(f"行 {line.text!r} 的 page={line.page} 与所在页 page.number={page.number} 不一致")
    return pages


def _detect(pages: tuple[PdfPage, ...], options: CleanupOptions) -> dict[int, RemovalReason]:
    """返回要删除的行（以 `id(line)` 为键）及原因。"""
    text_pages = sum(1 for page in pages if page.lines)
    threshold = max(2, min(options.min_pages, text_pages))

    # (页边, 模式) → 出现的页号集合；以及每个候选行的 (页边, 模式)
    seen: dict[tuple[RemovalReason, str], set[int]] = defaultdict(set)
    candidates: list[tuple[PdfLine, RemovalReason, str]] = []
    for page in pages:
        for line, zone in _edge_candidates(page, options):
            key = _pattern(line.text)
            seen[(zone, key)].add(page.number)
            candidates.append((line, zone, key))

    reasons: dict[int, RemovalReason] = {}
    for line, zone, key in candidates:
        if len(seen[(zone, key)]) >= threshold:
            reasons[id(line)] = RemovalReason.PAGE_NUMBER if key == _PAGE_NUMBER_KEY else zone
    return reasons


def _edge_candidates(page: PdfPage, options: CleanupOptions) -> list[tuple[PdfLine, RemovalReason]]:
    if not page.lines or page.height <= 0:
        return []
    header_floor = page.height * (1 - options.header_ratio)
    footer_ceiling = page.height * options.footer_ratio
    top = sorted(page.lines, key=lambda line: (-line.y1, line.index))[: options.edge_lines]
    bottom = sorted(page.lines, key=lambda line: (line.y0, line.index))[: options.edge_lines]

    result = [(line, RemovalReason.HEADER) for line in top if line.y0 >= header_floor]
    taken = {id(line) for line, _ in result}
    result += [
        (line, RemovalReason.FOOTER) for line in bottom if line.y1 <= footer_ceiling and id(line) not in taken
    ]
    return result


def _pattern(text: str) -> str:
    """把一行归一成跨页比较用的模式；整行是页码时返回统一的页码模式。"""
    normalized = _WHITESPACE_RE.sub(" ", unicodedata.normalize("NFKC", text)).strip().casefold()
    if _PAGE_NUMBER_RE.match(normalized):
        return _PAGE_NUMBER_KEY
    return _DIGITS_RE.sub("#", normalized)


def _build(all_lines: tuple[PdfLine, ...], reasons: dict[int, RemovalReason]) -> CleanupResult:
    kept: list[PdfLine] = []
    spans: list[LineSpan] = []
    removed: list[RemovedLine] = []
    original_offset = 0
    offset = 0
    for line in all_lines:
        reason = reasons.get(id(line))
        if reason is None:
            if kept:
                offset += len(_SEPARATOR)
            spans.append(LineSpan(start=offset, end=offset + len(line.text), original_start=original_offset, line=line))
            kept.append(line)
            offset += len(line.text)
        else:
            removed.append(RemovedLine(line=line, reason=reason, original_start=original_offset))
        original_offset += len(line.text) + len(_SEPARATOR)

    return CleanupResult(
        lines=tuple(kept),
        removed=tuple(removed),
        spans=tuple(spans),
        text=_SEPARATOR.join(line.text for line in kept),
        original_text=_SEPARATOR.join(line.text for line in all_lines),
        applied=bool(removed),
    )
