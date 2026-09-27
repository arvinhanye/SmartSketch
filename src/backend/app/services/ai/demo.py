"""ADR-079 演示模型：``LLM_MODE=demo`` 与 ``EMBEDDING_MODE=demo`` 的确定性、无网络客户端。

目的是在没有付费模型时让**真实服务链路**（worker 抽取、审核发布、问答）跑出合理结果，用于演示与端到端
验收（K05/K06）。它不是模型，也不代表抽取或问答质量：规则只看字面，结果一律当作「演示数据」。

``DemoModelClient`` 基于 E02 ``FakeModelClient`` 的 responder 机制（同样的截断、usage 模拟与流式切片），
按 ``ModelRequest.purpose`` 分派，从请求消息里取出资料原文，用规则产出**对应解析器/校验器能原样接受**的输出：

- ``extract_entities`` / ``repair``（E05）：按资料块中的章节路径行、定义句（「X 是/指/称为/用……」）、
  「特点是 P」「称为 X」、加粗术语、``术语：说明`` 列表项、表格首列与先修句式抽知识点；``evidence`` 一律是
  块内逐字连续的原文（章节路径行或所在句），``definition`` 取所在句。输出总长不超过声明的输出上限。
- ``extract_entities_gleaning``（E06）：同一规则减去已抽取列表，通常为空数组（没有遗漏可补）。
- ``extract_relations``（E11）：章节路径的上下级给 ``CONTAINS``（章 → 节、节标题 → 本节定义的知识点）；
  只有句中含 E11 ``PREREQUISITE_CUES`` 先修表述并匹配「学习 X 之前需要先掌握 Y」「X 建立在 Y 的基础上」
  「掌握 Y 后才能学习 X」「Y 是 X 的基础/前提」时给 ``PREREQUISITE``（Y → X），并在本次输出内做环检测，
  会成环的边直接舍弃；「X 是 Y 的例子」给 ``EXAMPLE_OF``；同句提到两个知识点且有对比/关联词给 ``RELATED_TO``。
  出现先后、同级顺序**不**判前置（与提示词和 E11 校验一致）。
- ``answer_with_context``（J05）：从编号资料块中挑与问题字词重叠最多的 1～3 句，逐句以 ``[n]`` 结尾；
  没有重叠时只输出 ``<<INSUFFICIENT_EVIDENCE>>`` 哨兵。
- ``rewrite_query``（J03）：原样返回当前问题。
- ``judge_duplicate`` / ``summarize_definition``（E10）：名称规范化后相同才判同义；合并定义取左侧定义。

``DemoEmbeddingClient``：字符 1-gram + 2-gram 的有符号哈希词袋（亚线性词频，每个 gram 分散到 32 个哈希维，
使向量接近稠密、经得起 Neo4j 向量索引的标量量化），L2 归一化，维度取请求的 ``dimensions``。字面重叠的中文问题与文本块余弦相似度明显高于无关文本；它所在的向量空间是保留模型 ID
``DEMO_EMBEDDING_MODEL`` 的独立空间，不与 ``fake`` 向量混用（``app.config.embedding_space_identity``）。

本模块不记日志、不读配置以外的任何东西；同一请求 → 同一结果（跨进程，只用 ``hashlib``）。
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, Final

from app.config import DEMO_EMBEDDING_MODEL
from app.services.ai.client import EmbeddingRequest, EmbeddingResult, ModelRequest, Usage
from app.services.ai.entities import (
    DEFINITION_MAX_CHARS,
    ENTITY_PROMPT_PURPOSE,
    EVIDENCE_MAX_CHARS,
    NAME_MAX_CHARS,
    REPAIR_PURPOSE,
)
from app.services.ai.fake import FakeModelClient
from app.services.ai.gleaning import GLEANING_PROMPT_PURPOSE
from app.services.ai.relations import PREREQUISITE_CUES, RELATION_PROMPT_PURPOSE
from app.services.fusion.judge import JUDGE_PURPOSE, SUMMARY_PURPOSE
from app.services.qa.citations import SENTINEL
from app.services.qa.generate import ANSWER_CALL_PURPOSE
from app.services.qa.rewrite import REWRITE_CALL_PURPOSE

__all__ = [
    "DEMO_EMBEDDING_MODEL",
    "DEMO_MODEL_ID",
    "DemoEmbeddingClient",
    "DemoModelClient",
    "demo_respond",
    "demo_vector",
]

#: 演示模式请求与 ``model_calls`` 里的模型 ID（不沿用 ``LLM_*_MODEL``）。
DEMO_MODEL_ID: Final = "smartsketch-demo-rules-v1"

# ---------------------------------------------------------------- 提示词中的定位标记（随模板版本固定）

_CHUNK_MARK: Final = "\n资料块：\n"
_KNOWN_MARK: Final = "已抽取知识点（JSON 数组，每项含 name 与 type）：\n"
_TABLE_MARK: Final = "实体表（JSON，每项含 id、name、type）：\n"
_SOURCES_MARK: Final = "来源资料（每段以 [块 ID] 开头）：\n"
_CONTEXT_OPEN: Final = "<<课程资料>>\n"
_CONTEXT_CLOSE: Final = "\n<<课程资料结束>>"
_QUESTION_OPEN: Final = "<<学生问题>>\n"
_QUESTION_CLOSE: Final = "\n<<学生问题结束>>"
_CURRENT_QUESTION: Final = "当前问题："

_CHUNK_HEAD = re.compile(r"(?m)^\[[^\[\]\n]+\]\n")
_BLOCK_HEAD = re.compile(r"(?m)^<<资料 ([1-9][0-9]*)>>.*$")

# ---------------------------------------------------------------- 资料文本的切分

_PATH_SEPARATOR: Final = " > "
_LOCATOR_PART = re.compile(r"第\s*\d+\s*[段页行]")
_NUMBERING = re.compile(
    r"^(?:第\s*[0-9一二三四五六七八九十百零〇]+\s*[章节篇部讲课单元]|[0-9]+(?:\.[0-9]+)*[.、．]?"
    r"|[一二三四五六七八九十]+[、.．])\s*"
)
_SENTENCE_END = re.compile(r"(?<=[。！？!?；;])")
_BULLET = re.compile(r"^\s*(?:[-*+•]|[0-9]+[.)、])\s+")
_TERM_ITEM = re.compile(r"^(?P<name>[^：:，,。；;]{1,16})[：:]\s*(?P<rest>\S.*)$")
_BOLD = re.compile(r"\*\*([^*\n]{1,30})\*\*")
_TABLE_SEPARATOR = re.compile(r"^\s*\|?\s*:?-{3,}")

_BAD_NAME_PREFIXES: Final = (
    "本", "这", "该", "此", "它", "其", "每", "对", "如", "若", "当", "在", "由", "从", "将", "我", "你",
    "他", "学习", "如果", "因为", "所以", "但是", "而且", "例如", "比如", "一", "另",
)
_EXAMPLE_SENTENCE = re.compile(
    r"^(?P<x>[^，,。；;：:]{1,16}?)是(?P<y>[^，,。；;：:]{1,16}?)的(?:一个|一种|典型)?(?:例子|实例|示例|应用实例|典型应用)"
)
_PROPERTY_SENTENCE = re.compile(r"^(?P<s>[^，,。；;：:]{1,16}?)的(?:特点|性质|特性)是(?P<p>[^，,。；;、]{2,16})")
_SUBJECT_SENTENCE = re.compile(
    r"^(?P<s>[^，,。；;：:（(]{1,16}?)(?:是指|是一种|是一类|是|指的是|指|称为|定义为|表示|用|把|通过|采用|只允许|只能|反复|选定|利用)"
)
_PROPERTY_ANYWHERE = re.compile(r"特点是(?P<p>[^，,。；;、\s]{2,12})")
_CALLED = re.compile(r"称为(?P<n>[^，,。；;、\s]{1,12})")

_PREREQUISITE_PATTERNS: Final = (
    # (正则, from 组, to 组)：from 是先修知识点
    (re.compile(r"学习(?P<to>[^，,。；;]+?)(?:之前|以前|前)[，,]?(?:需要|必须|应该|应当|要|应)?先?"
                r"(?:掌握|学习|了解|理解|学会)(?P<from>[^，,。；;]+?)(?:[。；;，,！!]|$)"), "from", "to"),
    (re.compile(r"^(?P<to>[^，,。；;]+?)(?:建立在|依赖于)(?P<from>[^，,。；;]+?)(?:的基础之上|的基础上|基础上|之上)?"
                r"(?:[。；;，,！!]|$)"), "from", "to"),
    (re.compile(r"掌握(?:了)?(?P<from>[^，,。；;]+?)(?:之)?后[，,]?才(?:能|可以)(?:学习|理解|掌握)?(?P<to>[^，,。；;]+?)"
                r"(?:[。；;，,！!]|$)"), "from", "to"),
    (re.compile(r"^(?P<from>[^，,。；;]+?)是(?:学习)?(?P<to>[^，,。；;]+?)的(?:先修|前置|前提|基础)"), "from", "to"),
)
_CUES_FOLDED: Final = tuple(unicodedata.normalize("NFKC", cue).casefold() for cue in PREREQUISITE_CUES)
_RELATED_CUES: Final = ("相比", "对比", "区别", "不同", "类似", "相似", "联系", "对应", "与", "和", "及")

_METHOD_SUFFIX = re.compile(r"(?:算法|方法|排序|查找|搜索|遍历|操作|步骤|策略|技巧|入栈|出栈|入队|出队|插入|删除)$")
_THEOREM_SUFFIX = re.compile(r"(?:定理|定律|引理|推论|性质|原理|结论)$")
_FORMULA_SUFFIX = re.compile(r"(?:公式|方程|复杂度|表达式)$")


def _fold(text: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text)).casefold()


def _has_word(text: str) -> bool:
    return any(unicodedata.category(ch)[0] in "LN" for ch in text) and not text.strip().isdigit()


def _clean_name(raw: str) -> str | None:
    name = _BOLD.sub(r"\1", raw).replace("*", "").strip(" \t「」“”\"'《》()（）")
    if not name or len(name) > NAME_MAX_CHARS or not _has_word(name):
        return None
    if any(ch in name for ch in "，,。；;：:!！?？|`[]【】<>"):
        return None
    if name.startswith(_BAD_NAME_PREFIXES):
        return None
    return name


def _type_of(name: str, default: str = "concept") -> str:
    if _METHOD_SUFFIX.search(name):
        return "method"
    if _THEOREM_SUFFIX.search(name):
        return "theorem"
    if _FORMULA_SUFFIX.search(name):
        return "formula"
    return default


def _is_path_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped or len(stripped) > 300:
        return False
    if _LOCATOR_PART.fullmatch(stripped):
        return True
    return _PATH_SEPARATOR in stripped and all(part.strip() for part in stripped.split(_PATH_SEPARATOR))


def _headings(path_line: str) -> list[tuple[str, str]]:
    """章节路径行 → ``[(原标题, 知识点名)]``，去掉段/页定位与编号前缀。"""
    out: list[tuple[str, str]] = []
    for part in path_line.strip().split(_PATH_SEPARATOR):
        part = part.strip()
        if not part or _LOCATOR_PART.fullmatch(part):
            continue
        name = _clean_name(_NUMBERING.sub("", part))
        if name is not None:
            out.append((part, name))
    return out


def _sentences(line: str) -> list[str]:
    return [piece.strip() for piece in _SENTENCE_END.split(line) if piece.strip()]


@dataclass
class _Segment:
    path_line: str | None
    lines: list[str]


def _segments(text: str) -> list[_Segment]:
    """按章节路径行切段；围栏代码块内的行丢弃（代码不是知识点定义句）。"""
    segments = [_Segment(None, [])]
    fence = False
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith(("```", "~~~")):
            fence = not fence
            continue
        if fence:
            continue
        if _is_path_line(line):
            segments.append(_Segment(stripped, []))
            continue
        segments[-1].lines.append(line)
    return [segment for segment in segments if segment.path_line or segment.lines]


# ---------------------------------------------------------------- 实体规则


@dataclass
class _Item:
    name: str
    type: str
    definition: str
    evidence: str
    confidence: float
    heading: bool
    segment: int

    def as_json(self) -> dict[str, Any]:
        return {"name": self.name, "type": self.type, "definition": self.definition,
                "evidence": self.evidence, "confidence": self.confidence}


def _definition(text: str) -> str:
    text = _BOLD.sub(r"\1", text).strip()
    return text[:DEFINITION_MAX_CHARS]


def _entity_items(text: str) -> list[_Item]:
    items: list[_Item] = []
    seen: set[str] = set()

    def add(raw_name: str | None, type_: str, definition: str, evidence: str, confidence: float,
            *, heading: bool = False, segment: int = 0) -> None:
        name = _clean_name(raw_name) if raw_name is not None else None
        evidence = evidence.strip()
        definition = _definition(definition)
        if name is None or not definition or not evidence or len(evidence) > EVIDENCE_MAX_CHARS:
            return
        if evidence not in text:
            return
        key = _fold(name)
        if key in seen:
            return
        seen.add(key)
        items.append(_Item(name, type_, definition, evidence, confidence, heading, segment))

    segments = _segments(text)
    subject_definitions: dict[str, str] = {}
    for segment in segments:
        for line in segment.lines:
            for sentence in _sentences(line):
                match = _SUBJECT_SENTENCE.match(sentence)
                if match:
                    subject_definitions.setdefault(_fold(match.group("s")), sentence)

    for index, segment in enumerate(segments):
        if segment.path_line:
            for original, name in _headings(segment.path_line):
                definition = subject_definitions.get(_fold(name)) or f"课程资料中「{original}」一节的主题。"
                add(name, _type_of(name), definition, segment.path_line, 0.5, heading=True, segment=index)
        header: list[str] | None = None
        for line in segment.lines:
            stripped = line.strip()
            if not stripped:
                header = None
                continue
            if stripped.startswith("|"):
                cells = [cell.strip() for cell in stripped.strip("|").split("|")]
                if _TABLE_SEPARATOR.match(stripped):
                    continue
                if header is None:
                    header = cells
                    continue
                if cells and cells[0]:
                    described = "；".join(f"{h}：{v}" for h, v in zip(header[1:], cells[1:], strict=False) if v)
                    default = "method" if header and re.search(r"操作|方法|算法|步骤", header[0]) else "concept"
                    add(cells[0], _type_of(cells[0], default),
                        f"{cells[0]}：{described}" if described else cells[0], stripped, 0.6, segment=index)
                continue
            header = None
            bullet = _BULLET.match(stripped)
            if bullet:
                content = stripped[bullet.end():].strip()
                term = _TERM_ITEM.match(content)
                if term:
                    add(term.group("name"), _type_of(_clean_name(term.group("name")) or ""), content, content, 0.6,
                        segment=index)
                    continue
                stripped = content
            for sentence in _sentences(stripped):
                for bold in _BOLD.finditer(sentence):
                    add(bold.group(1), _type_of(bold.group(1)), sentence, sentence, 0.7, segment=index)
                plain = _BOLD.sub(r"\1", sentence)
                if plain != sentence:
                    continue  # 加粗句的其余规则需要去掉标记后的原文作证据，不能保证逐字，跳过
                for pattern, from_group, to_group in _PREREQUISITE_PATTERNS:
                    found = pattern.search(sentence)
                    if found and _has_cue(sentence):
                        for group in (to_group, from_group):
                            add(found.group(group), _type_of(found.group(group)), sentence, sentence, 0.6,
                                segment=index)
                        break
                example = _EXAMPLE_SENTENCE.match(sentence)
                if example:
                    add(example.group("x"), "example", sentence, sentence, 0.7, segment=index)
                    add(example.group("y"), _type_of(example.group("y")), sentence, sentence, 0.5, segment=index)
                    continue
                prop = _PROPERTY_SENTENCE.match(sentence)
                if prop:
                    add(prop.group("s"), _type_of(prop.group("s")), sentence, sentence, 0.7, segment=index)
                    add(prop.group("p"), "theorem", sentence, sentence, 0.7, segment=index)
                    continue
                subject = _SUBJECT_SENTENCE.match(sentence)
                if subject:
                    add(subject.group("s"), _type_of(subject.group("s")), sentence, sentence, 0.8, segment=index)
                for called in _CALLED.finditer(sentence):
                    add(called.group("n"), _type_of(called.group("n")), sentence, sentence, 0.7, segment=index)
                for feature in _PROPERTY_ANYWHERE.finditer(sentence):
                    add(feature.group("p"), "theorem", sentence, sentence, 0.7, segment=index)
    return items


def _fit(key: str, rows: Iterable[dict[str, Any]], limit: int) -> str:
    """``{"<key>": [...]}``，按顺序放入条目直到总字符数将超过 ``limit``（fake 口径：一字符一 token）。"""
    kept: list[dict[str, Any]] = []
    for row in rows:
        candidate = json.dumps({key: [*kept, row]}, ensure_ascii=False)
        if len(candidate) > limit:
            break
        kept.append(row)
    return json.dumps({key: kept}, ensure_ascii=False)


def _chunk_text(prompt: str) -> str | None:
    head, found, rest = prompt.partition(_CHUNK_MARK)
    return rest if found else None


def _entities_reply(request: ModelRequest, prompt: str) -> str:
    text = _chunk_text(prompt)
    rows = [item.as_json() for item in _entity_items(text)] if text is not None else []
    return _fit("entities", rows, request.max_output_tokens)


def _gleaning_reply(request: ModelRequest, prompt: str) -> str:
    text = _chunk_text(prompt)
    known: set[str] = set()
    start = prompt.find(_KNOWN_MARK)
    if start >= 0:
        try:
            listed, _ = json.JSONDecoder().raw_decode(prompt, start + len(_KNOWN_MARK))
        except ValueError:
            listed = []
        if isinstance(listed, list):
            known = {_fold(row["name"]) for row in listed if isinstance(row, dict) and isinstance(row.get("name"), str)}
    rows = ([item.as_json() for item in _entity_items(text) if _fold(item.name) not in known]
            if text is not None else [])
    return _fit("entities", rows, request.max_output_tokens)


# ---------------------------------------------------------------- 关系规则


def _has_cue(sentence: str) -> bool:
    folded = unicodedata.normalize("NFKC", sentence).casefold()
    return any(cue in folded for cue in _CUES_FOLDED)


def _reaches(graph: dict[str, set[str]], start: str, goal: str) -> bool:
    stack, seen = [start], set()
    while stack:
        node = stack.pop()
        if node == goal:
            return True
        if node in seen:
            continue
        seen.add(node)
        stack.extend(graph.get(node, ()))
    return False


def _relations(table: list[dict[str, Any]], chunks: list[str], limit: int) -> str:
    ids: dict[str, str] = {}
    types: dict[str, str] = {}
    names: dict[str, str] = {}
    for row in table:
        if isinstance(row, dict) and all(isinstance(row.get(k), str) for k in ("id", "name", "type")):
            ids.setdefault(_fold(row["name"]), row["id"])
            types[row["id"]] = row["type"]
            names[row["id"]] = row["name"]
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    linked: set[frozenset[str]] = set()
    prerequisites: dict[str, set[str]] = {}

    def entity(fragment: str) -> str | None:
        exact = ids.get(_fold(fragment))
        if exact is not None:
            return exact
        folded = _fold(fragment)
        hits = [(len(key), -folded.find(key), entity_id) for key, entity_id in ids.items() if key and key in folded]
        return max(hits)[2] if hits else None

    def emit(from_id: str | None, to_id: str | None, type_: str, evidence: str, confidence: float) -> None:
        if from_id is None or to_id is None or from_id == to_id or len(evidence) > EVIDENCE_MAX_CHARS:
            return
        key = (from_id, to_id, type_) if type_ != "RELATED_TO" else (*sorted((from_id, to_id)), type_)
        if key in seen:  # type: ignore[comparison-overlap]
            return
        if type_ == "PREREQUISITE":
            if _reaches(prerequisites, to_id, from_id):
                return  # 会成环：舍弃这条（DAG 约束，宁缺勿错）
            prerequisites.setdefault(from_id, set()).add(to_id)
        seen.add(key)  # type: ignore[arg-type]
        linked.add(frozenset((from_id, to_id)))
        rows.append({"from_id": from_id, "to_id": to_id, "type": type_, "evidence": evidence,
                     "confidence": confidence})

    for text in chunks:
        segments = _segments(text)
        items = _entity_items(text)
        for index, segment in enumerate(segments):
            heading_ids: list[str] = []
            if segment.path_line:
                heading_ids = [i for i in (ids.get(_fold(name)) for _, name in _headings(segment.path_line)) if i]
                for outer, inner in zip(heading_ids, heading_ids[1:], strict=False):
                    emit(outer, inner, "CONTAINS", segment.path_line, 0.7)
            for line in segment.lines:
                for sentence in _sentences(line.strip()):
                    for pattern, from_group, to_group in _PREREQUISITE_PATTERNS:
                        found = pattern.search(sentence)
                        if found and _has_cue(sentence):
                            emit(entity(found.group(from_group)), entity(found.group(to_group)),
                                 "PREREQUISITE", sentence, 0.8)
                            break
                    example = _EXAMPLE_SENTENCE.match(sentence)
                    if example:
                        emit(entity(example.group("x")), entity(example.group("y")), "EXAMPLE_OF", sentence, 0.7)
            if heading_ids:
                for item in items:
                    if item.segment != index or item.heading or item.type == "example":
                        continue
                    child = ids.get(_fold(item.name))
                    emit(heading_ids[-1], child, "CONTAINS", segment.path_line or "", 0.6)
            for line in segment.lines:
                for sentence in _sentences(line.strip()):
                    if not any(cue in sentence for cue in _RELATED_CUES):
                        continue
                    present = sorted(((sentence.find(names[i]), names[i], i) for i in names if names[i] in sentence))
                    present = [p for p in present if not any(p[1] != q[1] and p[1] in q[1] for q in present)]
                    if len(present) >= 2 and frozenset((present[0][2], present[1][2])) not in linked:
                        emit(present[0][2], present[1][2], "RELATED_TO", sentence, 0.5)
    return _fit("relations", rows, limit)


def _relations_reply(request: ModelRequest, prompt: str) -> str:
    start = prompt.find(_TABLE_MARK)
    sources_at = prompt.find(_SOURCES_MARK)
    if start < 0 or sources_at < 0:
        return json.dumps({"relations": []})
    try:
        table, _ = json.JSONDecoder().raw_decode(prompt, start + len(_TABLE_MARK))
    except ValueError:
        return json.dumps({"relations": []})
    body = prompt[sources_at + len(_SOURCES_MARK):]
    chunks = [piece for piece in _CHUNK_HEAD.split(body) if piece.strip()]
    return _relations(table if isinstance(table, list) else [], chunks, request.max_output_tokens)


# ---------------------------------------------------------------- 问答


_QUESTION_STOP_PHRASES: Final = (
    "为什么", "是什么", "什么是", "什么", "怎么样", "怎么", "怎样", "如何", "哪些", "哪个", "是否", "有没有",
    "请问", "请", "介绍一下", "介绍", "一下", "解释", "说明", "讲讲", "谈谈", "吗", "呢", "吧", "啊",
)
_QUESTION_STOP_CHARS: Final = set("的是了和与及或在中有个")
_ANSWER_UNSAFE = re.compile(r"[\[\]【】［］`<>«＜]|\.(?=\s|$)")


def _question_terms(question: str) -> list[str]:
    text = unicodedata.normalize("NFKC", question).casefold()
    for phrase in _QUESTION_STOP_PHRASES:
        text = text.replace(phrase, " ")
    terms: list[str] = []
    current = ""
    for ch in text:
        if unicodedata.category(ch)[0] in "LN" and ch not in _QUESTION_STOP_CHARS:
            current += ch
        else:
            if current:
                terms.append(current)
            current = ""
    if current:
        terms.append(current)
    return list(dict.fromkeys(terms))


def _sentence_score(sentence: str, terms: list[str]) -> int:
    folded = unicodedata.normalize("NFKC", sentence).casefold()
    score = 0
    for term in terms:
        if term in folded:
            score += 2 * len(term) + (3 if folded.startswith(term) else 0)
        elif len(term) >= 2:
            score += sum(1 for i in range(len(term) - 1) if term[i:i + 2] in folded)
    return score


def _answer_sentences(block: str) -> list[str]:
    out: list[str] = []
    for segment in _segments(block):
        for line in segment.lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("|"):
                continue
            bullet = _BULLET.match(stripped)
            if bullet:
                stripped = stripped[bullet.end():]
            stripped = stripped.lstrip("#").strip().replace("**", "")
            for sentence in _sentences(stripped):
                body = sentence.rstrip("。！？!?；;，,：: ")
                if len(body) < 4 or len(body) > 200 or not _has_word(body) or _ANSWER_UNSAFE.search(body):
                    continue
                out.append(body)
    return out


def _answer_reply(request: ModelRequest, prompt: str) -> str:
    q_start = prompt.find(_QUESTION_OPEN)
    q_end = prompt.find(_QUESTION_CLOSE, q_start + 1)
    c_start = prompt.find(_CONTEXT_OPEN)
    c_end = prompt.find(_CONTEXT_CLOSE, c_start + 1)
    if min(q_start, q_end, c_start, c_end) < 0:
        return SENTINEL
    terms = _question_terms(prompt[q_start + len(_QUESTION_OPEN):q_end])
    context = prompt[c_start + len(_CONTEXT_OPEN):c_end]
    heads = list(_BLOCK_HEAD.finditer(context))
    ranked: list[tuple[int, int, int, str]] = []
    for position, head in enumerate(heads):
        end = heads[position + 1].start() if position + 1 < len(heads) else len(context)
        index = int(head.group(1))
        for order, sentence in enumerate(_answer_sentences(context[head.end():end])):
            score = _sentence_score(sentence, terms)
            if score >= 2:
                ranked.append((score, position, order, f"{sentence}[{index}]。"))
    if not ranked:
        return SENTINEL
    best = max(score for score, *_ in ranked)
    chosen = sorted(ranked, key=lambda row: (-row[0], row[1], row[2]))
    chosen = [row for row in chosen if row[0] * 2 >= best][:3]
    answer = ""
    for _, _, _, text in sorted(chosen, key=lambda row: (row[1], row[2])):
        if text in answer or len(answer) + len(text) > request.max_output_tokens:
            continue
        answer += text
    return answer or SENTINEL


def _rewrite_reply(prompt: str) -> str:
    at = prompt.rfind(_CURRENT_QUESTION)
    if at < 0:
        return ""
    return prompt[at + len(_CURRENT_QUESTION):].strip().split("\n", 1)[0].strip()


# ---------------------------------------------------------------- E10 同义裁决与定义合并


def _json_after(prompt: str, label: str) -> Any:
    at = prompt.find(label)
    if at < 0:
        return None
    try:
        value, _ = json.JSONDecoder().raw_decode(prompt, at + len(label))
    except ValueError:
        return None
    return value


def _line_after(prompt: str, label: str) -> str:
    at = prompt.find(label)
    return prompt[at + len(label):].split("\n", 1)[0].strip() if at >= 0 else ""


def _source_ids(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [row["source_id"] for row in value if isinstance(row, dict) and isinstance(row.get("source_id"), str)]


def _judge_reply(prompt: str) -> str:
    same = bool(_line_after(prompt, "知识点 A：")) and _fold(_line_after(prompt, "知识点 A：")) == _fold(
        _line_after(prompt, "知识点 B："))
    ids = list(dict.fromkeys(_source_ids(_json_after(prompt, "来源 A：")) + _source_ids(_json_after(prompt, "来源 B："))))
    reason = "两侧名称规范化后相同，来源原文描述同一知识点（演示规则）" if same else "名称不同，演示规则不判为同义"
    return json.dumps({"same": same, "reason": reason, "source_ids": ids}, ensure_ascii=False)


def _summary_reply(prompt: str) -> str:
    definitions = _json_after(prompt, "原文定义：\n")
    definition = ""
    if isinstance(definitions, list):
        texts = [row.get("definition") for row in definitions if isinstance(row, dict)]
        definition = next((text for text in texts if isinstance(text, str) and text.strip()), "")
    ids = list(dict.fromkeys(_source_ids(_json_after(prompt, "原文来源：\n"))))
    return json.dumps({"definition": definition[:DEFINITION_MAX_CHARS], "source_ids": ids}, ensure_ascii=False)


# ---------------------------------------------------------------- 分派


def demo_respond(request: ModelRequest) -> str:
    """按 ``purpose`` 产出规则输出；无法识别的用途退回 E02 fake 缺省输出的形状（不猜）。"""
    prompt = "\n".join(message.content for message in request.messages)
    purpose = request.purpose
    if purpose == REPAIR_PURPOSE:  # 修复调用沿用原消息：按消息内容判断原用途
        if _TABLE_MARK in prompt:
            purpose = RELATION_PROMPT_PURPOSE
        elif _KNOWN_MARK in prompt:
            purpose = GLEANING_PROMPT_PURPOSE
        else:
            purpose = ENTITY_PROMPT_PURPOSE
    handlers: dict[str, Callable[[], str]] = {
        ENTITY_PROMPT_PURPOSE: lambda: _entities_reply(request, prompt),
        GLEANING_PROMPT_PURPOSE: lambda: _gleaning_reply(request, prompt),
        RELATION_PROMPT_PURPOSE: lambda: _relations_reply(request, prompt),
        ANSWER_CALL_PURPOSE: lambda: _answer_reply(request, prompt),
        REWRITE_CALL_PURPOSE: lambda: _rewrite_reply(prompt),
        JUDGE_PURPOSE: lambda: _judge_reply(prompt),
        SUMMARY_PURPOSE: lambda: _summary_reply(prompt),
    }
    handler = handlers.get(purpose)
    if handler is None:
        from app.services.ai.fake import default_text

        return default_text(request)
    return handler()


class DemoModelClient(FakeModelClient):
    """E02 fake 的截断、usage 与流式行为 + ``demo_respond`` 规则输出（仍可 ``script`` 注入故障）。"""

    def __init__(self, *, stream_chunk_chars: int = 8) -> None:
        super().__init__(responder=demo_respond, stream_chunk_chars=stream_chunk_chars)


# ---------------------------------------------------------------- 向量

_EMBEDDING_STOP_CHARS: Final = set("的是了在和与及或一个这那么什怎样吗呢第段")
_STOP_WEIGHT: Final = 0.3
#: 每个 n-gram 分散到的维数（稀疏随机投影）。只落一维的纯哈希词袋过于稀疏，Neo4j 5.26 向量索引缺省的
#: 标量量化会把它的相似度压扁（实测无关问题也有 0.6+）；分散后向量接近稠密，量化后仍保序。
_SPREAD: Final = 128


def _units(text: str) -> list[str]:
    folded = unicodedata.normalize("NFKC", text).casefold()
    for phrase in _QUESTION_STOP_PHRASES:  # 疑问套话不携带主题，去掉后问题向量更贴近主题词
        folded = folded.replace(phrase, " ")
    return [ch for ch in folded if unicodedata.category(ch)[0] in "LN"]


def demo_vector(text: str, dimensions: int) -> tuple[float, ...]:
    """字符 1-gram + 2-gram 有符号哈希词袋，权重 ``1 + ln(tf)``（虚词字降权、疑问套话去掉），每个 gram
    以 ±权重分散到 ``_SPREAD`` 个哈希维上，最后 L2 归一化。"""
    if type(dimensions) is not int or dimensions < 1:
        raise ValueError("dimensions must be an int >= 1")
    units = _units(text)
    grams = Counter(units)
    grams.update(units[i] + units[i + 1] for i in range(len(units) - 1))
    values = [0.0] * dimensions
    for gram, count in grams.items():
        weight = 1.0 + math.log(count)
        if all(ch in _EMBEDDING_STOP_CHARS for ch in gram):
            weight *= _STOP_WEIGHT
        digest = hashlib.shake_256(gram.encode("utf-8")).digest(4 * _SPREAD)
        for offset in range(0, len(digest), 4):
            code = int.from_bytes(digest[offset:offset + 4], "big")
            values[(code >> 1) % dimensions] += weight if code & 1 else -weight
    norm = math.sqrt(sum(value * value for value in values))
    if norm == 0:
        return tuple(1.0 if i == 0 else 0.0 for i in range(dimensions))
    return tuple(value / norm for value in values)


class DemoEmbeddingClient:
    """确定性演示向量；usage 按字符数模拟（向量调用不计入预算，与 fake 相同）。"""

    def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        if not isinstance(request, EmbeddingRequest):
            raise TypeError("request must be an EmbeddingRequest")
        return EmbeddingResult(
            vectors=tuple(demo_vector(text, request.dimensions) for text in request.texts),
            model_requested=request.model,
            model_responded=request.model,
            usage=Usage(sum(len(text) for text in request.texts), 0),
        )
