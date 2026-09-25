"""资料解析（D 组）。各格式解析器（D02～D07）输出 `models.ParsedDocument`。"""

from app.services.parsers.models import (
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
]
