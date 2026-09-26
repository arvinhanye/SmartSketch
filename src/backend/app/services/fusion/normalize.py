"""E08：名称归一与重复候选——实体名称 → 确定性归一键与重复候选对。

纯函数：不调用模型、不做 I/O、不记录日志、不修改输入。E08 **只列候选，不合并**：同键、别名、
包含三类候选一律交给 E09（向量候选分层）与 E10（重复裁决）决定是否同义。

课程隔离：本模块不认识课程。调用方必须只传入**同一课程**、且已按草稿可见性（ADR-011 修订 1，
F02 的 V 过滤）筛过的实体集合；跨课程混传会产生跨课程候选，这是调用方的错误。

归一键（``normalize_name``）按以下顺序处理：

1. **类型**：只接受 ``str``，否则 ``TypeError``。
2. **全半角**：Unicode NFKC。全角字母数字、全角空格（U+3000）、全角括号（）、全角逗号/分号/冒号都
   折成半角；``、``（U+3001）不受 NFKC 影响，按原样作别名分隔符。
3. **格式字符**：删除 Unicode 类别 ``Cf`` 的字符（零宽空格、零宽连接符、BOM、字连接符等）。
4. **大小写**：只把 ASCII ``A``–``Z`` 转成小写。希腊、西里尔等字母保留大小写（数学里 Σ 求和与
   σ 标准差、Δ 与 δ 含义不同，不能归一到同一个键）。
5. **圆括号**：只识别圆括号（NFKC 后的 ``(``、``)``）。先找出顶层括号组；括号不配对（多出 ``)`` 或
   未闭合的 ``(``）时整个名称不拆分，括号作普通字符留在键里。配对时逐组分类：

   - **公式组**：``(`` 紧贴在 ASCII 字母或数字之后、且组内全是 ASCII 字符（如 ``O(n)``、``f(x)``、
     ``x2(t)``），括号与内容原样留在键里，不产生别名。组内含非 ASCII 字符的不算公式
     （「JIT（即时编译）」「CPU（中央处理器）」仍按别名处理）；代价是紧贴且全 ASCII 的
     「Stack(LIFO)」也按公式保留，需写成「Stack (LIFO)」或「栈（LIFO）」才拆出别名；
   - **别名组**：名称末尾连续的括号组（组间只允许空白），内容是整个名称的别名/缩写，从主名中去掉；
   - **注释组**：其余括号组（开头或中间，如「图（Graph）的遍历」），内容只注释相邻的词，不是整个
     名称的别名，从主名中去掉且不产生别名。

   嵌套括号只看顶层；组内的内层括号作普通字符留在别名里。
6. **别名切分**：别名组内容按 ``,``、``;``、``、`` 切成多项。每项先做第 7 步空白处理，再去掉前缀
   标记：「又称、也称、亦称、简称、俗称、或称」可直接跟内容（可再跟一个 ``:``）；「英文全称、英文缩写、
   英文名、英文、全称、缩写」必须跟 ``:`` 才算标记。去掉标记后为空则保留原文。「即」不是标记
   （「即时编译」是合法别名）。
7. **空白**：按 Unicode 空白拆成片段后重新拼接；只有两侧都是 ASCII 字母或数字时保留一个半角空格
   （拉丁单词边界，「hash table」≠「hashtable」），其余空白一律删除（「二叉 树」=「二叉树」、
   「C 语言」=「c语言」、「B + 树」=「b+树」）。首尾空白自然去掉。
8. **结果**：主名为空而存在别名项时（名称整个在括号里，如「（栈）」），按出现顺序取第一项作主键、
   其余作别名；两者都为空则 ``ValueError``。别名去重、去掉与主键相同的项、按码点升序。

重复候选（``find_duplicate_candidates``），每一对只报一次，原因按优先级取最强的一个：

1. ``same_key``：两者主键完全相同。**只有**主键相同才是同键候选。
2. ``alias``：主键不同，但一方的主键或别名与另一方的主键或别名相同（至少一侧用到别名，包括
   双方共享同一别名）。``matched_key`` 取共享键中码点最小者。
3. ``containment``：主键不同、无共享别名，且较短主键是较长主键的**前缀**，并同时满足：

   - 较短主键的有效字符数 ≥ ``CONTAINMENT_MIN_CHARS``（2）。有效字符 = Unicode 字母或数字
     （类别 L*、N*），标点、符号与空格不计。单字名（「栈」「树」「图」「C」「C++」）因此永不参与
     包含候选，避免「栈/栈帧」「图/图灵机」「C/C++」这类单字包含泛滥；
   - 有效字符比 较短/较长 ≥ ``CONTAINMENT_MIN_RATIO``（3/5，含等号）。挡住「排序/排序算法」
     「二叉树/二叉树的遍历」这类短通名被长名称包含的情况；
   - 前缀不切断拉丁/数字串：较短键末字符与较长键下一字符都是 ASCII 字母或数字时不算
     （「Java/JavaScript」「hash table/hash tables」「k2/k23」）。

   只认前缀、不认后缀或中间包含，理由：中文与英文的名词短语都是中心语在后，前加修饰语通常得到
   下位概念（「平衡二叉树」「单链表」「堆排序」「单源最短路径」都不是其短名的重复），而在后面补
   「算法/法/问题」等通常仍指同一概念（「快速排序/快速排序算法」「Dijkstra/Dijkstra算法」）。
   其余语义相近但名称不包含的重复交给 E09 向量候选。``matched_key`` 为较短主键。

定义不参与归一与候选：定义相似度属于 E09/E10 的语义判断，E08 只看名称，避免同定义不同名的误报。

输出：``DuplicateCandidate`` 元组，``left_id < right_id``（码点序，等同 UTF-8 字节序），按
``(left_id, right_id)`` 升序，无重复、无自配对，与输入顺序无关。复杂度 O(n²) 对，面向单课程规模。
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from fractions import Fraction
from typing import Final

__all__ = [
    "CONTAINMENT_MIN_CHARS",
    "CONTAINMENT_MIN_RATIO",
    "CandidateReason",
    "DuplicateCandidate",
    "NameEntry",
    "NormalizedName",
    "find_duplicate_candidates",
    "normalize_name",
]

#: 包含候选中较短主键的最少有效字符数（含）。
CONTAINMENT_MIN_CHARS: Final = 2
#: 包含候选的有效字符比下限 较短/较长（含等号）。
CONTAINMENT_MIN_RATIO: Final = Fraction(3, 5)

_WORD_CHARS: Final = frozenset("abcdefghijklmnopqrstuvwxyz0123456789")
_ASCII_LOWER: Final = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")
_ALIAS_SEPARATORS: Final = (",", ";", "、")
#: 可直接跟内容的前缀标记（冒号可有可无）。
_VERB_MARKERS: Final = ("又称", "也称", "亦称", "简称", "俗称", "或称")
#: 必须跟冒号才算标记的前缀；按长度降序，先匹配长的。
_LABEL_MARKERS: Final = ("英文全称", "英文缩写", "英文名", "英文", "全称", "缩写")


class CandidateReason(StrEnum):
    """候选原因，按优先级从高到低排列；一对只取最强的一个。"""

    SAME_KEY = "same_key"
    ALIAS = "alias"
    CONTAINMENT = "containment"


@dataclass(frozen=True, slots=True)
class NormalizedName:
    """一个名称的归一结果。``key`` 为主键；``aliases`` 为括号别名的键，去重、不含主键、码点升序。"""

    key: str
    aliases: tuple[str, ...] = ()

    @property
    def keys(self) -> tuple[str, ...]:
        """主键在前、别名在后。"""
        return (self.key, *self.aliases)


@dataclass(frozen=True, slots=True)
class NameEntry:
    """一个待归一的实体。``entity_id`` 由调用方给定、在一次调用内唯一；``definition`` 只随行，不参与计算。"""

    entity_id: str
    name: str
    definition: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.entity_id, str):
            raise TypeError(f"entity_id must be str, got {type(self.entity_id).__name__}")
        if not self.entity_id.strip():
            raise ValueError("entity_id must be non-blank")
        if not isinstance(self.name, str):
            raise TypeError(f"name must be str, got {type(self.name).__name__}")
        if self.definition is not None and not isinstance(self.definition, str):
            raise TypeError(f"definition must be str or None, got {type(self.definition).__name__}")


@dataclass(frozen=True, slots=True)
class DuplicateCandidate:
    """一对重复候选。``left_id < right_id``；``matched_key`` 是命中的归一键（见模块说明）。"""

    left_id: str
    right_id: str
    reason: CandidateReason
    matched_key: str

    def __post_init__(self) -> None:
        if not isinstance(self.reason, CandidateReason):
            raise TypeError("reason must be CandidateReason")
        if not self.left_id < self.right_id:
            raise ValueError("left_id must sort strictly before right_id")


def _is_word(ch: str) -> bool:
    return ch in _WORD_CHARS


def _squash(text: str) -> str:
    """空白规则：两侧都是 ASCII 字母/数字时留一个空格，否则删除。"""
    out = ""
    for piece in text.split():
        if out and _is_word(out[-1]) and _is_word(piece[0]):
            out += " "
        out += piece
    return out


def _strip_marker(item: str) -> str:
    for marker in _VERB_MARKERS:
        if item.startswith(marker):
            rest = item[len(marker) :]
            if rest.startswith(":"):
                rest = rest[1:]
            if rest:
                return rest
    for marker in _LABEL_MARKERS:
        if item.startswith(marker + ":"):
            rest = item[len(marker) + 1 :]
            if rest:
                return rest
    return item


def _top_level_groups(text: str) -> list[tuple[int, int]] | None:
    """顶层括号组的 ``(开括号下标, 闭括号下标)``；不配对时返回 ``None``。"""
    groups: list[tuple[int, int]] = []
    depth = 0
    start = 0
    for index, ch in enumerate(text):
        if ch == "(":
            if depth == 0:
                start = index
            depth += 1
        elif ch == ")":
            if depth == 0:
                return None
            depth -= 1
            if depth == 0:
                groups.append((start, index))
    return None if depth else groups


def _split_parentheses(text: str) -> tuple[str, list[str]]:
    """拆成（主名原文，别名组内容列表）。公式组留在主名；注释组丢弃。"""
    groups = _top_level_groups(text)
    if not groups:
        return text, []
    literal = [
        start > 0 and _is_word(text[start - 1]) and text[start + 1 : end].isascii() for start, end in groups
    ]

    trailing: set[int] = set()
    tail = len(text)
    for index in range(len(groups) - 1, -1, -1):
        start, end = groups[index]
        if literal[index] or text[end + 1 : tail].strip():
            break
        trailing.add(index)
        tail = start

    main_parts: list[str] = []
    alias_raws: list[str] = []
    cursor = 0
    for index, (start, end) in enumerate(groups):
        if literal[index]:
            continue
        main_parts.append(text[cursor:start])
        cursor = end + 1
        if index in trailing:
            alias_raws.append(text[start + 1 : end])
    main_parts.append(text[cursor:])
    return "".join(main_parts), alias_raws


def _alias_items(raw: str) -> list[str]:
    for separator in _ALIAS_SEPARATORS[1:]:
        raw = raw.replace(separator, _ALIAS_SEPARATORS[0])
    items = []
    for part in raw.split(_ALIAS_SEPARATORS[0]):
        item = _squash(part)
        if item:
            items.append(_strip_marker(item))
    return items


def normalize_name(name: str) -> NormalizedName:
    """把一个实体名称归一为确定性主键与别名键（规则见模块说明）。"""
    if not isinstance(name, str):
        raise TypeError(f"name must be str, got {type(name).__name__}")
    text = unicodedata.normalize("NFKC", name)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Cf")
    text = text.translate(_ASCII_LOWER)

    main_raw, alias_raws = _split_parentheses(text)
    main = _squash(main_raw)
    items = [item for raw in alias_raws for item in _alias_items(raw)]
    if not main:
        if not items:
            raise ValueError("name is empty after normalization")
        main, items = items[0], items[1:]
    return NormalizedName(main, tuple(sorted(set(items) - {main})))


def _significant_chars(key: str) -> int:
    return sum(1 for ch in key if unicodedata.category(ch)[0] in "LN")


def _prefix_containment(a: str, b: str) -> str | None:
    short, long = (a, b) if len(a) < len(b) else (b, a)
    if len(short) == len(long) or not long.startswith(short):
        return None
    if _is_word(short[-1]) and _is_word(long[len(short)]):
        return None
    short_chars = _significant_chars(short)
    if short_chars < CONTAINMENT_MIN_CHARS:
        return None
    if Fraction(short_chars, _significant_chars(long)) < CONTAINMENT_MIN_RATIO:
        return None
    return short


def _classify(a: NormalizedName, b: NormalizedName) -> tuple[CandidateReason, str] | None:
    if a.key == b.key:
        return CandidateReason.SAME_KEY, a.key
    shared = set(a.keys) & set(b.keys)
    if shared:
        return CandidateReason.ALIAS, min(shared)
    contained = _prefix_containment(a.key, b.key)
    if contained is not None:
        return CandidateReason.CONTAINMENT, contained
    return None


def find_duplicate_candidates(entries: Iterable[NameEntry]) -> tuple[DuplicateCandidate, ...]:
    """列出单课程实体集合中的重复候选对（只列候选，不合并）。

    ``entries`` 中每项必须是 ``NameEntry``（否则 ``TypeError``），``entity_id`` 不得重复、名称归一后
    不得为空（否则 ``ValueError``）。
    """
    normalized: list[tuple[str, NormalizedName]] = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, NameEntry):
            raise TypeError(f"entries must contain NameEntry, got {type(entry).__name__}")
        if entry.entity_id in seen:
            raise ValueError("duplicate entity_id")
        seen.add(entry.entity_id)
        normalized.append((entry.entity_id, normalize_name(entry.name)))
    normalized.sort(key=lambda item: item[0])

    candidates: list[DuplicateCandidate] = []
    for i, (left_id, left) in enumerate(normalized):
        for right_id, right in normalized[i + 1 :]:
            found = _classify(left, right)
            if found is not None:
                candidates.append(DuplicateCandidate(left_id, right_id, *found))
    return tuple(candidates)
