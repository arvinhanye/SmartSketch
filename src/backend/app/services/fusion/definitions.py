"""Choose complete source-derived definitions independently of stable graph IDs."""
import re
from collections.abc import Mapping, Sequence

from app.services.ai.entities import DEFINITION_MAX_CHARS


def _membership(text: str, names: Sequence[str]) -> bool:
    # Only classify a *whole* generic curriculum-membership sentence as weak.
    # A definition containing further clauses or formulas is never discarded.
    for name in names:
        if not text.startswith(name):
            continue
        if re.fullmatch(
            r'(?:属于|归属于|是)(?:(?:本章|本节|本课程)(?:中|的)?)?'
            r'(?:一个|一种|一类)?(?:概念|知识点|数据结构|操作|算法|方法|公式|示例|例子|内容)'
            r'(?:类|知识点)?[。.]?', text[len(name):]):
            return True
    return False


def merged_definition(nodes: Sequence[Mapping], canonical: Mapping) -> str:
    """Preserve original sentences, never invent or truncate a qualifier."""
    texts = list(dict.fromkeys(str(n.get('definition', '')).strip() for n in nodes))
    texts = [s for s in texts if s]
    names = [n.get('name', '') for n in nodes if n.get('name')]
    substantive = [s for s in texts if not _membership(s, names)]
    choices = substantive or texts
    if not choices:
        return canonical.get('definition', '')
    # Prefer a complete substantive description; ties preserve the current one.
    choices.sort(key=lambda s: (-len(s), s != canonical.get('definition'), s))
    result = choices[0]
    for text in choices[1:]:
        if text in result:
            continue
        combined = result + '\n' + text
        if len(combined) <= DEFINITION_MAX_CHARS:
            result = combined
    return result
