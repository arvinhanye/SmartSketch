"""D01：解析阶段的输出模型与来源定位规则。

纯数据模型，不做任何真实解析、I/O 或持久化。D02～D07 的各格式解析器产出
`ParsedDocument`；D08 分块、D09 块身份、D10 持久化、D11 编排都只消费这里的类型。

定位规则（与 `src/contracts/api.v1.yaml` 的 `SourceRef` 一致：`page` 正整数与
`section_path` 非空至少给出一个，ADR-003）：

1. **PDF**（唯一有页码的格式）：每块必须有 `page ≥ 1`；`section_titles` 可空
   （由 D06 标题判定给出）；`paragraph` 可选；不带行号。
2. **TXT / Markdown / DOCX**（无页码）：`page` 必须为空，不得编造页码。
   每块必须有 `paragraph`：该块在**同一 `section_titles`** 下按文档顺序的序号，从 1 起、
   连续不断档；同一标题路径在文档中重复出现时接续编号，因此「章节路径 + 段落」在文档内唯一。
   `section_path` 取标题路径（`" > "` 连接）；块前没有任何标题时，兜底为 `第N段`。
3. **行号**：TXT 与 Markdown 必须带 `line_start`/`line_end`（解码后源文本的物理行号，
   从 1 起、闭区间），块间按块序号递增且不重叠；DOCX 与 PDF 不带行号。
4. 块序号 `ordinal` 为文档内从 0 起的连续整数，即 D09「`revision_id` + 块序号」之外的
   **解析块**顺序；分块后的块序号由 D08/D09 另行给出。
5. 空文档不构造 `ParsedDocument`：解析器改抛 `DocumentUnreadableError(no_text)`，
   对应任务失败码 `DOCUMENT_UNREADABLE` 的 `reason = no_text`（specs/task-processing.md §6）。

资料修订 `(document_id, 内容哈希, 解析器版本)`（ADR-012 修订 1）由 `RevisionKey` 表示；
解析器只知道自己的 `parser_version`，`document_id` 与原始字节的哈希由 D11 编排时补齐。
`revision_id` 与块 ID 的派生公式归 D09，本模块不定义。命名按 ADR-016 决定 6
使用 `document_id`（规格 V2 中的 `material_id` 为同一概念）。
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum

__all__ = [
    "SECTION_SEPARATOR",
    "BlockKind",
    "DocumentUnreadableError",
    "ParseModelError",
    "ParsedBlock",
    "ParsedDocument",
    "RevisionKey",
    "SourceFormat",
    "SourceLocator",
    "UnreadableReason",
    "normalize_heading",
    "sha256_digest",
]

#: `section_path` 中各级标题的连接符，与 `SourceRef.section_path` 的示例「第3章 > 3.1 栈」一致。
SECTION_SEPARATOR = " > "

_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_WHITESPACE_RE = re.compile(r"\s+")


class ParseModelError(ValueError):
    """解析输出不满足本模块的不变量。出现即说明解析器实现有缺陷，不是用户资料的问题。"""


class SourceFormat(StrEnum):
    TXT = "txt"
    MARKDOWN = "markdown"
    DOCX = "docx"
    PDF = "pdf"

    @property
    def paginated(self) -> bool:
        """是否有可信页码。只有 PDF 有；DOCX 的分页取决于渲染，不当作页码。"""
        return self is SourceFormat.PDF


class BlockKind(StrEnum):
    """解析块的内容形态，供 D08 决定切分方式（如表格、代码尽量不从中间切开）。

    标题不是块：标题只进入后续块的 `section_titles`。
    """

    PARAGRAPH = "paragraph"
    LIST = "list"
    TABLE = "table"
    CODE = "code"


class UnreadableReason(StrEnum):
    """与 `DOCUMENT_UNREADABLE` 错误的 `details.reason` wire 闭集一致（errors.v1.md）。"""

    CORRUPTED = "corrupted"
    ENCRYPTED = "encrypted"
    NO_TEXT = "no_text"


class DocumentUnreadableError(Exception):
    """资料无法解析。解析器以此代替返回空结果；扫描件等无文本层的 PDF 用 `no_text`，不声称有 OCR。"""

    def __init__(self, reason: UnreadableReason | str, detail: str = "") -> None:
        try:
            self.reason = UnreadableReason(reason)
        except ValueError:
            raise ParseModelError(
                f"reason 必须是 {[r.value for r in UnreadableReason]} 之一，收到 {reason!r}"
            ) from None
        self.detail = detail
        super().__init__(f"{self.reason.value}: {detail}" if detail else self.reason.value)


def normalize_heading(title: str) -> str:
    """把原文标题整理成可放进 `section_titles` 的形式。

    合并所有空白（含换行、全角空格）为单个半角空格并去首尾；半角 `>` 替换为全角 `＞`，
    保证 `section_path` 可以按连接符无歧义地拆回各级标题。解析器应先用它处理标题再构造定位。
    """
    return _WHITESPACE_RE.sub(" ", title).strip().replace(">", "＞")


def sha256_digest(data: bytes) -> str:
    """资料原始字节的内容哈希，格式与快照摘要一致：`sha256:<64 位小写十六进制>`。"""
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise ParseModelError("sha256_digest 只接受 bytes（对原始上传字节求哈希，不对解码后的文本）")
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _check_version(value: object) -> None:
    if not isinstance(value, str) or not value or any(ch.isspace() for ch in value):
        raise ParseModelError(f"parser_version 必须是不含空白的非空字符串，收到 {value!r}")


@dataclass(frozen=True, slots=True)
class SourceLocator:
    """一个解析块在原文中的位置。字段语义见模块说明的定位规则。"""

    page: int | None = None
    section_titles: tuple[str, ...] = ()
    paragraph: int | None = None
    line_start: int | None = None
    line_end: int | None = None

    def __post_init__(self) -> None:
        if self.page is not None and not (_is_int(self.page) and self.page >= 1):
            raise ParseModelError(f"page 必须是 ≥ 1 的整数或为空，收到 {self.page!r}")

        titles = self.section_titles
        if isinstance(titles, (str, bytes)) or not isinstance(titles, Iterable):
            raise ParseModelError(f"section_titles 必须是标题序列，收到 {titles!r}")
        titles = tuple(titles)
        for title in titles:
            if not isinstance(title, str) or not title or normalize_heading(title) != title:
                raise ParseModelError(
                    f"section_titles 中的标题必须非空且已经 normalize_heading 规范化，收到 {title!r}"
                )
        object.__setattr__(self, "section_titles", titles)

        if self.paragraph is not None and not (_is_int(self.paragraph) and self.paragraph >= 1):
            raise ParseModelError(f"paragraph 必须是 ≥ 1 的整数或为空，收到 {self.paragraph!r}")

        start, end = self.line_start, self.line_end
        if (start is None) != (end is None):
            raise ParseModelError("line_start 与 line_end 必须同时给出或同时为空")
        if start is not None:
            if not (_is_int(start) and _is_int(end) and 1 <= start <= end):
                raise ParseModelError(
                    f"line_start/line_end 必须是 1 ≤ line_start ≤ line_end 的整数，收到 {start!r}..{end!r}"
                )

        if self.page is None and not titles and self.paragraph is None:
            raise ParseModelError("定位至少需要 page、section_titles、paragraph 之一")

    @property
    def section_path(self) -> str | None:
        """SourceRef 的 `section_path`：有标题取标题路径，无标题时以 `第N段` 兜底，二者皆无为空。"""
        if self.section_titles:
            return SECTION_SEPARATOR.join(self.section_titles)
        if self.paragraph is not None:
            return f"第{self.paragraph}段"
        return None

    def to_source_fields(self) -> dict[str, int | str]:
        """转为 SourceRef 的定位字段；缺失的键直接省略（契约要求不写 null）。"""
        fields: dict[str, int | str] = {}
        if self.page is not None:
            fields["page"] = self.page
        path = self.section_path
        if path is not None:
            fields["section_path"] = path
        return fields


@dataclass(frozen=True, slots=True)
class ParsedBlock:
    """解析器输出的最小单元：一段正文、一个列表、一张表或一个代码块，不可变。"""

    ordinal: int
    text: str
    locator: SourceLocator
    kind: BlockKind = BlockKind.PARAGRAPH

    def __post_init__(self) -> None:
        if not (_is_int(self.ordinal) and self.ordinal >= 0):
            raise ParseModelError(f"ordinal 必须是 ≥ 0 的整数，收到 {self.ordinal!r}")
        if not isinstance(self.text, str) or not self.text.strip():
            raise ParseModelError("text 必须是去掉空白后仍非空的字符串")
        if not isinstance(self.locator, SourceLocator):
            raise ParseModelError(f"locator 必须是 SourceLocator，收到 {type(self.locator).__name__}")
        try:
            object.__setattr__(self, "kind", BlockKind(self.kind))
        except ValueError:
            raise ParseModelError(
                f"kind 必须是 {[k.value for k in BlockKind]} 之一，收到 {self.kind!r}"
            ) from None


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    """一份资料的完整解析结果：块按 `ordinal` 排列，且全部满足该格式的定位规则。"""

    source_format: SourceFormat
    parser_version: str
    blocks: tuple[ParsedBlock, ...] = field(default=())

    def __post_init__(self) -> None:
        try:
            fmt = SourceFormat(self.source_format)
        except ValueError:
            raise ParseModelError(
                f"source_format 必须是 {[f.value for f in SourceFormat]} 之一，收到 {self.source_format!r}"
            ) from None
        object.__setattr__(self, "source_format", fmt)
        _check_version(self.parser_version)

        blocks = tuple(self.blocks)
        if not all(isinstance(b, ParsedBlock) for b in blocks):
            raise ParseModelError("blocks 只能包含 ParsedBlock")
        if not blocks:
            raise ParseModelError(
                "blocks 为空：没有可提取文本时解析器应抛 DocumentUnreadableError(no_text)"
            )
        object.__setattr__(self, "blocks", blocks)

        ordinals = [b.ordinal for b in blocks]
        if ordinals != list(range(len(blocks))):
            raise ParseModelError(f"ordinal 必须按顺序从 0 连续编号，收到 {ordinals}")

        text_lines = fmt in (SourceFormat.TXT, SourceFormat.MARKDOWN)
        next_paragraph: dict[tuple[str, ...], int] = {}
        last_line = 0
        for block in blocks:
            loc = block.locator
            where = f"块 {block.ordinal}"
            if fmt.paginated:
                if loc.page is None:
                    raise ParseModelError(f"{where}：PDF 块必须有 page")
            else:
                if loc.page is not None:
                    raise ParseModelError(f"{where}：{fmt.value} 没有页码，page 必须为空（不得编造）")
                if loc.paragraph is None:
                    raise ParseModelError(f"{where}：{fmt.value} 块必须有 paragraph 作为段落定位")

            if loc.paragraph is not None:
                expected = next_paragraph.get(loc.section_titles, 1)
                if loc.paragraph != expected:
                    raise ParseModelError(
                        f"{where}：paragraph 应为 {expected}（同一章节路径下从 1 起连续编号），"
                        f"收到 {loc.paragraph}"
                    )
                next_paragraph[loc.section_titles] = expected + 1

            if text_lines:
                if loc.line_start is None:
                    raise ParseModelError(f"{where}：{fmt.value} 块必须有 line_start/line_end")
                if loc.line_start <= last_line:
                    raise ParseModelError(
                        f"{where}：line_start={loc.line_start} 与前一块（止于第 {last_line} 行）重叠或倒序"
                    )
                last_line = loc.line_end  # type: ignore[assignment]
            elif loc.line_start is not None:
                raise ParseModelError(f"{where}：{fmt.value} 没有可靠行号，line_start/line_end 必须为空")


@dataclass(frozen=True, slots=True)
class RevisionKey:
    """资料修订的三元组（ADR-012 修订 1）。`revision_id` 的派生公式归 D09。"""

    document_id: str
    content_hash: str
    parser_version: str

    def __post_init__(self) -> None:
        if not isinstance(self.document_id, str) or not self.document_id.strip():
            raise ParseModelError("document_id 必须是非空字符串")
        if not isinstance(self.content_hash, str) or not _HASH_RE.match(self.content_hash):
            raise ParseModelError(
                f"content_hash 必须形如 sha256:<64 位小写十六进制>，收到 {self.content_hash!r}"
            )
        _check_version(self.parser_version)
