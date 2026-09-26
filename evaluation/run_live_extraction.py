#!/usr/bin/env python3
"""K02：在执行者本机用真实模型抽取基准章节，生成供 ``evaluate_extraction.py`` 计分的 predictions.json。

用法：
    python3 evaluation/run_live_extraction.py --gold evaluation/fixtures/synthetic.json \\
        --out predictions.json [--run-log run.json]

背景：开发云环境的网络策略拦截 ``api.deepseek.com``，真实模型评测只能在能直连供应商的本机运行
（ADR-027 主用模型 DeepSeek V4.1 Flash ``deepseek-flash``；ADR-028 已确认本章评测的付费调用）。
格式口径以 ``evaluation/README.md`` 第 4 节为准。

流程（与生产路径共用同一批服务，只有融合是简化版）：

1. 取 ``gold.documents[0].text``（Markdown）。
2. 按 D11 ``parse_task`` 的路径解析与分块：D03 ``parse_markdown`` → D08 ``chunk_blocks`` →
   D09 ``assign_chunk_identities``。课程、资料 ID 取金标文件里的值，内容哈希按正文现算，
   修订 ID 由 D09 从三元组派生；这些 ID 只在本次运行内有意义，不写任何数据库。
3. 按环境变量建模型客户端（``app.config.load_settings``）：
   - ``LLM_MODE=live``：E03 ``CompatibleModelClient``（配置了备用四项时同时建备用），外包 E04
     ``ModelCallPolicy``，重试、熔断、任务/日预算取环境变量。``LLM_API_KEY`` 为空即拒绝运行；
     密钥不打印、不写入任何文件。
   - ``LLM_MODE=fake``：E02 ``FakeModelClient`` 配本脚本的确定性应答 ``fake_responder``，同样外包
     E04 策略。只用于测试脚本流程，输出 ``model.is_fake = true``，**结果不能证明达标**。
   调用记录写本进程内存（``MemoryCallStore``，计费规则同 ``model_calls``），不读写应用 SQLite；
   因此日预算只统计本次运行，看不到当天其他用量。
4. 逐块 E05 ``EntityExtractor`` 抽实体。E06 补漏（gleaning）默认关闭，与生产缺省一致；
   ``--glean-rounds N`` 可开启 N 轮。
5. **简化融合**：真实融合（E08～E10，由 E12 编排）在此不可用。按 E08 ``normalize_name`` 的主键去重，
   保留首次出现的名称与类型；别名、包含、向量候选与模型裁决一概不做。输出中注明为简化融合。
6. 按章节路径把块分组（``--section-depth``，缺省用完整路径），每组以融合后在该组块中出现过的实体
   组成 ``SectionEntity`` 表，调 E11 ``RelationExtractor.extract``。跨组合并时按（起点、终点、类型）
   去重，``RELATED_TO`` 视为无向。
7. 写 predictions.json（README 格式，``source`` 一律 ``"ai"``）与运行日志，并打印 ``sample``、
   ``score`` 两步命令。

失败处理：单块或单组失败（调用错误、修复后仍不合规）记录后继续；预算拒绝（``BudgetExceededError``）
立即停止，不写 predictions.json，只写运行日志；鉴权失败与调用记录预写失败同样停止（后续每块都会失败）。

退出码：0 完成；2 配置错误（含 live 缺密钥）；3 预算拒绝；4 其他中止（鉴权失败等）。
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]

try:  # 推荐 ``pip install -e ./src/backend``；未安装时退回仓库内源码路径
    import app  # noqa: F401
except ImportError:  # pragma: no cover - 取决于执行环境
    sys.path.insert(0, str(REPO / "src" / "backend"))

from app.config import Settings, SettingsError, load_settings  # noqa: E402
from app.repositories.model_calls import EMBEDDING_PURPOSE, BudgetRejected, CallOutcome, CallRecord  # noqa: E402
from app.services.ai.client import ModelAuthError, ModelCallError, ModelClient, ModelError, ModelRequest  # noqa: E402
from app.services.ai.compatible import CompatibleModelClient  # noqa: E402
from app.services.ai.entities import (  # noqa: E402
    ENTITY_PROMPT_PURPOSE,
    ENTITY_PROMPT_VERSION,
    EntityCandidate,
    EntityExtractor,
)
from app.services.ai.fake import FakeModelClient  # noqa: E402
from app.services.ai.gleaning import (  # noqa: E402
    GLEANING_PROMPT_PURPOSE,
    GLEANING_PROMPT_VERSION,
    MAX_ROUNDS_HARD_LIMIT,
    EntityGleaner,
    StopReason,
)
from app.services.ai.policy import (  # noqa: E402
    BudgetExceededError,
    CallAttribution,
    CallRecordError,
    ModelCallPolicy,
)
from app.services.ai.relations import (  # noqa: E402
    RELATION_PROMPT_PURPOSE,
    RELATION_PROMPT_VERSION,
    RelationExtractor,
    SectionEntity,
    SourceChunk,
)
from app.services.chunk_identity import (  # noqa: E402
    ChunkIdentity,
    assign_chunk_identities,
    revision_id_for,
    revision_parser_version,
)
from app.services.chunking import (  # noqa: E402
    DEFAULT_OVERLAP_CHARS,
    DEFAULT_TARGET_CHARS,
    SemanticChunk,
    chunk_blocks,
    chunking_version,
)
from app.services.fusion.normalize import normalize_name  # noqa: E402
from app.services.graph.dag import find_cycle  # noqa: E402
from app.services.parsers.markdown import parse_markdown  # noqa: E402
from app.services.parsers.models import RevisionKey  # noqa: E402

EXIT_OK = 0
EXIT_CONFIG = 2
EXIT_BUDGET = 3
EXIT_ABORTED = 4

#: 每次抽取调用声明的输出上限（token）。规格未给值，按单块实体表与单节关系表的量级暂定。
DEFAULT_ENTITY_MAX_OUTPUT_TOKENS = 4096
DEFAULT_RELATION_MAX_OUTPUT_TOKENS = 4096
FAKE_MODEL_ID = "fake-extraction"
DEFAULT_SEED = 20260926

FUSION_NOTE = (
    "简化融合：只按 E08 normalize_name 主键去重，保留首次出现的名称与类型；未做别名/包含/向量候选"
    "与 E10 模型裁决。真实融合（E08～E10）由 E12 编排，本结果只是初步数字，不是验收 7 的最终判定"
    "（验收 7 须经 E12 完整流程处理到 awaiting_review 后导出）。"
)
MEMORY_STORE_NOTE = "调用记录只在本进程内存中计量；日预算只统计本次运行，未读取应用数据库中的当日用量。"


class RunConfigError(Exception):
    """配置不可用（live 缺密钥、变量不合法等）。消息只含变量名，不含取值。"""


class _Stop(Exception):
    def __init__(self, status: str, message: str, exit_code: int) -> None:
        super().__init__(message)
        self.status = status
        self.message = message
        self.exit_code = exit_code


# ---------------------------------------------------------------- 调用记录（内存）


class MemoryCallStore:
    """E04 ``CallStore`` 的进程内实现：预算检查与计费规则同 ``SqliteCallStore``（ADR-011 修订 3）。

    行只含 ID、计数与分类，不含提示词、输出或密钥。
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._rows: dict[str, dict[str, Any]] = {}

    def __repr__(self) -> str:
        return f"MemoryCallStore(rows={len(self._rows)})"

    @staticmethod
    def _billed(row: Mapping[str, Any]) -> int:
        if row["usage_input"] is not None and row["usage_output"] is not None:
            return row["usage_input"] + row["usage_output"]
        if row["status"] == "error" and row["rejected_before_generation"]:
            return 0
        return row["input_tokens_est"] + row["max_output_tokens"]

    def _used(self, task_id: str | None) -> int:
        return sum(
            self._billed(row)
            for row in self._rows.values()
            if row["purpose"] != EMBEDDING_PURPOSE and (task_id is None or row["task_id"] == task_id)
        )

    def prewrite(self, record: CallRecord, *, task_budget: int, daily_budget: int) -> None:
        with self._lock:
            if record.call_id in self._rows:
                return
            if record.purpose != EMBEDDING_PURPOSE:
                if record.task_id is not None:
                    used = self._used(record.task_id)
                    if used >= task_budget:
                        raise BudgetRejected("task", used, task_budget)
                used = self._used(None)
                if used >= daily_budget:
                    raise BudgetRejected("daily", used, daily_budget)
            self._rows[record.call_id] = {
                "status": "sent",
                "task_id": record.task_id,
                "purpose": record.purpose,
                "provider_role": record.provider_role,
                "model_requested": record.model_requested,
                "model_responded": None,
                "input_tokens_est": record.input_tokens_est,
                "max_output_tokens": record.max_output_tokens,
                "usage_input": None,
                "usage_output": None,
                "error_class": None,
                "rejected_before_generation": False,
            }

    def finish(self, outcome: CallOutcome) -> None:
        with self._lock:
            row = self._rows.get(outcome.call_id)
            if row is None:
                return
            row.update(
                status=outcome.status,
                model_responded=outcome.model_responded,
                usage_input=outcome.usage_input,
                usage_output=outcome.usage_output,
                error_class=outcome.error_class,
                rejected_before_generation=outcome.rejected_before_generation,
            )

    def responded_models(self) -> list[str]:
        with self._lock:
            return sorted({r["model_responded"] for r in self._rows.values() if r["model_responded"]})

    def summary(self) -> dict[str, Any]:
        with self._lock:
            rows = list(self._rows.values())
        by_purpose: dict[str, int] = {}
        by_status: dict[str, int] = {}
        errors: dict[str, int] = {}
        for row in rows:
            by_purpose[row["purpose"]] = by_purpose.get(row["purpose"], 0) + 1
            by_status[row["status"]] = by_status.get(row["status"], 0) + 1
            if row["error_class"]:
                errors[row["error_class"]] = errors.get(row["error_class"], 0) + 1
        with_usage = [r for r in rows if r["usage_input"] is not None]
        return {
            "calls": len(rows),
            "by_purpose": dict(sorted(by_purpose.items())),
            "by_status": dict(sorted(by_status.items())),
            "error_classes": dict(sorted(errors.items())),
            "by_provider_role": {
                role: sum(1 for r in rows if r["provider_role"] == role)
                for role in sorted({r["provider_role"] for r in rows})
            },
            "usage_input_tokens": sum(r["usage_input"] for r in with_usage),
            "usage_output_tokens": sum(r["usage_output"] for r in with_usage),
            "calls_without_usage": len(rows) - len(with_usage),
            "billed_tokens": sum(self._billed(r) for r in rows),
            "responded_models": sorted({r["model_responded"] for r in rows if r["model_responded"]}),
        }


# ---------------------------------------------------------------- fake 应答


_PATH_LINE = re.compile(r"^(?P<path>\S.*) > 第\d+段$", re.MULTILINE)
_NUMBERING = re.compile(r"^(?:第\s*\d+\s*章|\d+(?:\.\d+)*)\s*")
_ENTITY_ROW = re.compile(r'^(\{"id": .*\}),?$', re.MULTILINE)


def fake_responder(request: ModelRequest) -> str:
    """``LLM_MODE=fake`` 的确定性应答：只为让流程跑通，内容与真实抽取无关。

    - 实体：块内每个章节路径行（「… > 第N段」）中除章以外的各级标题，去掉编号后作为 ``concept``，
      证据为该路径行本身（块文本的连续子串）。同一小节下的块会反复给出上级标题（如「栈」），
      用来检验跨块合并。
    - 关系：实体表中相邻两项给一条 ``RELATED_TO``，证据为来源块的第一条路径行。
    - 补漏：空数组。其他用途（如修复）：同时含空 ``entities`` 与 ``relations``。
    """
    text = "\n".join(message.content for message in request.messages)
    if request.purpose == ENTITY_PROMPT_PURPOSE:
        items: list[dict[str, Any]] = []
        names: set[str] = set()
        for match in _PATH_LINE.finditer(text):
            for title in match.group("path").split(" > ")[1:]:
                name = _NUMBERING.sub("", title).strip()
                if name and name not in names:
                    names.add(name)
                    items.append({"name": name, "type": "concept", "definition": f"（fake）{title}",
                                  "evidence": match.group(0), "confidence": 0.5})
        return json.dumps({"entities": items}, ensure_ascii=False)
    if request.purpose == RELATION_PROMPT_PURPOSE:
        rows = [json.loads(line) for line in _ENTITY_ROW.findall(text)]
        first = _PATH_LINE.search(text)
        relations = []
        if first is not None:
            relations = [
                {"from_id": a["id"], "to_id": b["id"], "type": "RELATED_TO", "evidence": first.group(0),
                 "confidence": 0.5}
                for a, b in zip(rows, rows[1:])
            ]
        return json.dumps({"relations": relations}, ensure_ascii=False)
    if request.purpose == GLEANING_PROMPT_PURPOSE:
        return json.dumps({"entities": []})
    return json.dumps({"entities": [], "relations": []})


# ---------------------------------------------------------------- 配置与客户端


def load_run_settings(environ: Mapping[str, str]) -> Settings:
    """读环境变量；live 缺密钥或变量不合法时抛 ``RunConfigError``（只报变量名）。"""
    if environ.get("LLM_MODE", "fake") == "live" and not environ.get("LLM_API_KEY", "").strip():
        raise RunConfigError("LLM_MODE=live 时必须设置 LLM_API_KEY（只放本机环境变量，不写入任何文件）")
    try:
        return load_settings(environ)
    except SettingsError as exc:
        raise RunConfigError(str(exc)) from None


@dataclass
class Runtime:
    """一次运行的模型栈：适配器 → E04 策略（绑定到本次运行）→ 抽取服务。"""

    mode: str
    model_id: str
    is_fake: bool
    primary: ModelClient = field(repr=False)
    policy: ModelCallPolicy = field(repr=False)
    store: MemoryCallStore = field(repr=False)
    has_fallback: bool = False

    def __repr__(self) -> str:
        return (f"Runtime(mode={self.mode!r}, model_id={self.model_id!r}, is_fake={self.is_fake}, "
                f"has_fallback={self.has_fallback})")


def build_runtime(settings: Settings, *, model_client: ModelClient | None = None) -> Runtime:
    """按 ``LLM_MODE`` 建客户端并外包 E04 策略。``model_client`` 只供测试注入（替代 HTTP 适配器）。"""
    fallback: ModelClient | None = None
    if model_client is not None:
        primary = model_client
    elif settings.LLM_MODE == "live":
        primary = CompatibleModelClient.from_settings(settings, role="primary")
        if settings.LLM_FALLBACK_BASE_URL.strip():
            fallback = CompatibleModelClient.from_settings(settings, role="fallback")
    else:
        primary = FakeModelClient(responder=fake_responder)
    model_id = settings.LLM_EXTRACTION_MODEL.strip() or FAKE_MODEL_ID
    store = MemoryCallStore()
    policy = ModelCallPolicy.from_settings(settings, primary=primary, fallback=fallback, store=store)
    # 只有真正的 HTTP 适配器才算真实模型；注入的 fake 一律按假模型标注
    is_fake = not isinstance(primary, CompatibleModelClient)
    return Runtime(mode=settings.LLM_MODE, model_id=model_id, is_fake=is_fake, primary=primary,
                   policy=policy, store=store, has_fallback=fallback is not None)


# ---------------------------------------------------------------- 解析与分块


@dataclass(frozen=True)
class PreparedChunk:
    identity: ChunkIdentity
    chunk: SemanticChunk

    @property
    def text(self) -> str:
        return self.chunk.text


def prepare_chunks(
    text: str, *, course_id: str, document_id: str,
    target_chars: int = DEFAULT_TARGET_CHARS, overlap_chars: int = DEFAULT_OVERLAP_CHARS,
) -> tuple[str, list[PreparedChunk]]:
    """D03 → D08 → D09，与 D11 ``run_parse_stage`` 同一路径。返回（修订 ID，块列表）。"""
    data = text.encode("utf-8")
    document = parse_markdown(data)
    chunks = chunk_blocks(document.blocks, target_chars=target_chars, overlap_chars=overlap_chars)
    key = RevisionKey(
        document_id=document_id,
        content_hash="sha256:" + hashlib.sha256(data).hexdigest(),
        parser_version=revision_parser_version(
            document.parser_version, chunking_version(target_chars, overlap_chars)),
    )
    identities = assign_chunk_identities(course_id, key, chunks)
    return revision_id_for(key), [PreparedChunk(i, c) for i, c in zip(identities, chunks)]


# ---------------------------------------------------------------- 主流程


@dataclass
class FusedEntity:
    id: str
    name: str
    type: str
    definition: str
    evidence: str
    section: str
    chunk_ids: set[str]


@dataclass
class RunOutcome:
    predictions: dict[str, Any] | None
    run_log: dict[str, Any]
    exit_code: int
    message: str = ""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _count(bucket: dict[str, int], key: str, amount: int = 1) -> None:
    bucket[key] = bucket.get(key, 0) + amount


def _error_code(error: BaseException) -> str:
    error_class = getattr(error, "error_class", None)
    if error_class is not None:
        return str(error_class.value)
    code = getattr(error, "code", None)
    return f"{type(error).__name__}:{code}" if code else type(error).__name__


def _check_stop(error: BaseException) -> None:
    """预算拒绝、调用记录失败、鉴权失败：后续每次调用都会同样失败，停止运行。"""
    if isinstance(error, BudgetExceededError):
        scope = "单任务" if error.scope == "task" else "每日"
        raise _Stop("budget_exceeded",
                    f"{scope}预算已用尽（LLM_{'TASK' if error.scope == 'task' else 'DAILY'}_TOKEN_BUDGET），"
                    "未再发出请求；运行已停止，未写 predictions.json", EXIT_BUDGET) from None
    if isinstance(error, CallRecordError):
        raise _Stop("aborted", "调用记录预写失败，未发出请求；运行已停止", EXIT_ABORTED) from None
    if isinstance(error, ModelAuthError):
        raise _Stop("aborted", f"供应商鉴权失败（HTTP {error.status_code}）：请检查 LLM_API_KEY 与 LLM_BASE_URL；"
                    "运行已停止", EXIT_ABORTED) from None


def _section_key(chunk: SemanticChunk, depth: int) -> tuple[str, ...]:
    titles = tuple(chunk.section_titles)
    return titles[:depth] if depth > 0 else titles


def _relation_key(frm: str, to: str, rtype: str) -> tuple[str, str, str]:
    if rtype == "RELATED_TO" and to < frm:
        frm, to = to, frm
    return frm, to, rtype


def run(
    gold: Mapping[str, Any],
    *,
    environ: Mapping[str, str],
    model_client: ModelClient | None = None,
    run_id: str | None = None,
    glean_rounds: int = 0,
    section_depth: int = 0,
    entity_max_output_tokens: int = DEFAULT_ENTITY_MAX_OUTPUT_TOKENS,
    relation_max_output_tokens: int = DEFAULT_RELATION_MAX_OUTPUT_TOKENS,
    progress: Callable[[str], None] | None = None,
) -> RunOutcome:
    """执行一次抽取（不读写文件）。配置错误抛 ``RunConfigError``；其余情况返回 ``RunOutcome``。"""
    if not 0 <= glean_rounds <= MAX_ROUNDS_HARD_LIMIT:
        raise RunConfigError(f"--glean-rounds 必须在 0..{MAX_ROUNDS_HARD_LIMIT}")
    if section_depth < 0:
        raise RunConfigError("--section-depth 必须 ≥ 0")
    settings = load_run_settings(environ)
    runtime = build_runtime(settings, model_client=model_client)

    documents = gold.get("documents") or []
    if not documents or not isinstance(documents[0].get("text"), str):
        raise RunConfigError("金标文件缺少 documents[0].text")
    document = documents[0]
    if document.get("format", "md") not in ("md", "markdown"):
        raise RunConfigError(f"只支持 Markdown 章节，documents[0].format={document.get('format')!r}")
    dataset_id = str(gold.get("dataset_id", ""))
    course_id = str((gold.get("course") or {}).get("id") or "k02-eval-course")
    document_id = str(document.get("id") or "k02-eval-document")
    started = datetime.now(UTC)
    run_id = run_id or f"k02-{'fake' if runtime.is_fake else 'live'}-{started.strftime('%Y%m%dT%H%M%SZ')}"

    revision_id, prepared = prepare_chunks(document["text"], course_id=course_id, document_id=document_id)

    entity_dropped: dict[str, int] = {}
    gleaning_dropped: dict[str, int] = {}
    relation_dropped: dict[str, int] = {}
    fusion_dropped: dict[str, int] = {}
    chunk_failures: list[dict[str, Any]] = []
    section_failures: list[dict[str, Any]] = []
    fused: dict[str, FusedEntity] = {}
    merged = 0
    type_conflicts = 0
    gleaning_added = 0
    relations: dict[tuple[str, str, str], dict[str, Any]] = {}
    sections: dict[tuple[str, ...], list[PreparedChunk]] = {}
    status, message, exit_code = "ok", "", EXIT_OK
    prompt_sha: dict[str, str] = {}

    def bound(chunk_id: str | None) -> ModelClient:
        return runtime.policy.bind(CallAttribution(
            course_id=course_id, task_id=run_id, chunk_id=chunk_id, task_attempt=1,
            chunk_attempt=1 if chunk_id else None))

    try:
        # ---- 实体：逐块 E05（可选 E06）
        for index, item in enumerate(prepared, 1):
            identity = item.identity
            if progress is not None:
                progress(f"[实体 {index}/{len(prepared)}] {' > '.join(item.chunk.section_titles) or '（无标题）'}")
            sections.setdefault(_section_key(item.chunk, section_depth), []).append(item)
            client = bound(identity.chunk_id)
            extractor = EntityExtractor(client, model=runtime.model_id, max_output_tokens=entity_max_output_tokens)
            prompt_sha[ENTITY_PROMPT_PURPOSE] = extractor.prompt().sha256
            failure_base = {"ordinal": identity.ordinal, "chunk_id": identity.chunk_id,
                            "section": " > ".join(item.chunk.section_titles)}
            try:
                extraction = extractor.extract(identity, item.text)
            except ModelError as error:
                _check_stop(error)
                chunk_failures.append({**failure_base, "stage": "entities", "error": _error_code(error)})
                continue
            if not extraction.ok:
                assert extraction.failure is not None
                chunk_failures.append({**failure_base, "stage": "entities",
                                       "error": extraction.failure.reason.value,
                                       "attempts": extraction.failure.attempts})
                continue
            for reason, n in extraction.dropped.items():
                _count(entity_dropped, reason.value, n)
            candidates: list[EntityCandidate] = list(extraction.candidates)

            if glean_rounds:
                gleaner = EntityGleaner(client, model=runtime.model_id, max_output_tokens=entity_max_output_tokens,
                                        enabled=True, max_rounds=glean_rounds)
                prompt_sha[GLEANING_PROMPT_PURPOSE] = gleaner.prompt().sha256
                try:
                    gleaned = gleaner.glean(identity, item.text, candidates)
                except ModelError as error:
                    _check_stop(error)
                    chunk_failures.append({**failure_base, "stage": "gleaning", "error": _error_code(error),
                                           "kept_first_pass": True})
                else:
                    if gleaned.stop_reason is StopReason.BUDGET_EXCEEDED:
                        _check_stop(BudgetExceededError("task"))
                    for reason, n in gleaned.dropped.items():
                        _count(gleaning_dropped, reason.value, n)
                    if gleaned.duplicates:
                        _count(gleaning_dropped, "duplicate", gleaned.duplicates)
                    if gleaned.ok:
                        candidates.extend(gleaned.added)
                        gleaning_added += len(gleaned.added)
                    else:
                        chunk_failures.append({**failure_base, "stage": "gleaning",
                                               "error": gleaned.stop_reason.value, "kept_first_pass": True})

            # ---- 简化融合：E08 主键去重，保留首次出现
            for candidate in candidates:
                try:
                    key = normalize_name(candidate.name).key
                except ValueError:
                    _count(fusion_dropped, "empty_name_key")
                    continue
                existing = fused.get(key)
                if existing is not None:
                    merged += 1
                    if existing.type != candidate.type:
                        type_conflicts += 1
                    existing.chunk_ids.add(identity.chunk_id)
                    continue
                fused[key] = FusedEntity(
                    id=f"p-e{len(fused) + 1:03d}", name=candidate.name, type=candidate.type,
                    definition=candidate.definition, evidence=candidate.evidence,
                    section=" > ".join(item.chunk.section_titles), chunk_ids={identity.chunk_id})

        # ---- 关系：按章节路径分组调 E11
        ordered_entities = list(fused.values())
        for index, (key, members) in enumerate(sections.items(), 1):
            if progress is not None:
                progress(f"[关系 {index}/{len(sections)}] {' > '.join(key) or '（无标题）'}")
            chunk_ids = {m.identity.chunk_id for m in members}
            table = [SectionEntity(entity_id=e.id, course_id=course_id, name=e.name, type=e.type)
                     for e in ordered_entities if e.chunk_ids & chunk_ids]
            extractor = RelationExtractor(bound(None), model=runtime.model_id,
                                          max_output_tokens=relation_max_output_tokens)
            prompt_sha[RELATION_PROMPT_PURPOSE] = extractor.prompt().sha256
            section_name = " > ".join(key)
            try:
                result = extractor.extract(course_id, table, [SourceChunk(m.identity, m.text) for m in members])
            except ModelError as error:
                _check_stop(error)
                section_failures.append({"section": section_name, "entities": len(table),
                                         "error": _error_code(error)})
                continue
            if not result.ok:
                assert result.failure is not None
                section_failures.append({"section": section_name, "entities": len(table),
                                         "error": result.failure.reason.value,
                                         "attempts": result.failure.attempts})
                continue
            for reason, n in result.dropped.items():
                _count(relation_dropped, reason.value, n)
            for candidate in result.candidates:
                rkey = _relation_key(candidate.from_id, candidate.to_id, candidate.type)
                if rkey in relations:
                    _count(relation_dropped, "cross_section_duplicate")
                    continue
                relations[rkey] = {"from": candidate.from_id, "to": candidate.to_id, "type": candidate.type,
                                   "evidence": candidate.evidence, "confidence": candidate.confidence,
                                   "section": section_name}
    except _Stop as stop:
        status, message, exit_code = stop.status, stop.message, stop.exit_code

    entities_out = [
        {"id": e.id, "name": e.name, "type": e.type, "source": "ai", "definition": e.definition,
         "evidence": e.evidence, "section": e.section}
        for e in fused.values()
    ]
    relations_out = [
        {"id": f"p-r{i:03d}", "source": "ai", **rel} for i, rel in enumerate(relations.values(), start=1)
    ]
    prereq_edges = [(r["from"], r["to"]) for r in relations_out if r["type"] == "PREREQUISITE"]
    cycle = find_cycle([e["id"] for e in entities_out], prereq_edges) if prereq_edges else None

    responded = runtime.store.responded_models()
    model: dict[str, Any] = {"id": runtime.model_id, "is_fake": runtime.is_fake}
    if len(responded) == 1:
        model["responded"] = responded[0]
    elif responded:
        model["responded"] = responded
    prompt_versions = {ENTITY_PROMPT_PURPOSE: ENTITY_PROMPT_VERSION, RELATION_PROMPT_PURPOSE: RELATION_PROMPT_VERSION}
    if glean_rounds:
        prompt_versions[GLEANING_PROMPT_PURPOSE] = GLEANING_PROMPT_VERSION
    fusion = {"mode": "simplified", "method": "e08_normalize_name_key_first_occurrence", "note": FUSION_NOTE}

    predictions = None
    if exit_code == EXIT_OK:
        predictions = {
            "run_id": run_id,
            "dataset_id": dataset_id,
            "model": model,
            "prompt_versions": prompt_versions,
            "fusion": fusion,
            "entities": entities_out,
            "relations": relations_out,
        }

    run_log = {
        "run_id": run_id,
        "status": status,
        "message": message,
        "started_at": started.isoformat(timespec="seconds"),
        "finished_at": _now(),
        "dataset_id": dataset_id,
        "is_final_benchmark": bool(gold.get("is_final_benchmark", False)),
        "course_id": course_id,
        "document_id": document_id,
        "revision_id": revision_id,
        "mode": runtime.mode,
        "model": model,
        "has_fallback": runtime.has_fallback,
        "prompt_versions": prompt_versions,
        "prompt_sha256": dict(sorted(prompt_sha.items())),
        "max_output_tokens": {"entities": entity_max_output_tokens, "relations": relation_max_output_tokens},
        "budgets": {"task": settings.LLM_TASK_TOKEN_BUDGET, "daily": settings.LLM_DAILY_TOKEN_BUDGET,
                    "note": MEMORY_STORE_NOTE},
        "gleaning": {"enabled": bool(glean_rounds), "max_rounds": glean_rounds, "added": gleaning_added},
        "section_depth": section_depth,
        "chunk_count": len(prepared),
        "section_count": len(sections),
        "chunk_failures": chunk_failures,
        "section_failures": section_failures,
        "dropped": {
            "entities": dict(sorted(entity_dropped.items())),
            "gleaning": dict(sorted(gleaning_dropped.items())),
            "fusion": dict(sorted(fusion_dropped.items())),
            "relations": dict(sorted(relation_dropped.items())),
        },
        "fusion": {**fusion, "merged": merged, "type_conflicts_kept_first": type_conflicts},
        "counts": {"entities": len(entities_out), "relations": len(relations_out),
                   "relations_by_type": {t: sum(1 for r in relations_out if r["type"] == t)
                                         for t in ("CONTAINS", "PREREQUISITE", "RELATED_TO", "EXAMPLE_OF")}},
        "prerequisite_cycle": list(cycle) if cycle else None,
        "model_calls": runtime.store.summary(),
    }
    return RunOutcome(predictions=predictions, run_log=run_log, exit_code=exit_code, message=message)


# ---------------------------------------------------------------- CLI


def _load_evaluator():
    path = Path(__file__).resolve().with_name("evaluate_extraction.py")
    spec = importlib.util.spec_from_file_location("_k02_evaluate_extraction", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    model_client: ModelClient | None = None,
) -> int:
    parser = argparse.ArgumentParser(description="K02：本机用真实模型抽取基准章节，生成 predictions.json")
    parser.add_argument("--gold", required=True, help="金标数据集（取 documents[0].text）")
    parser.add_argument("--out", required=True, help="predictions.json 输出路径")
    parser.add_argument("--run-log", help="运行日志 JSON 输出路径")
    parser.add_argument("--run-id", help="缺省为 k02-<live|fake>-<UTC 时间>")
    parser.add_argument("--glean-rounds", type=int, default=0,
                        help=f"E06 补漏轮数，0 为关闭（缺省，与生产缺省一致），最多 {MAX_ROUNDS_HARD_LIMIT}")
    parser.add_argument("--section-depth", type=int, default=0,
                        help="关系抽取按章节路径前 N 级分组；0（缺省）为完整路径")
    parser.add_argument("--entity-max-output-tokens", type=int, default=DEFAULT_ENTITY_MAX_OUTPUT_TOKENS)
    parser.add_argument("--relation-max-output-tokens", type=int, default=DEFAULT_RELATION_MAX_OUTPUT_TOKENS)
    args = parser.parse_args(argv)
    env = os.environ if environ is None else environ

    try:
        gold = json.loads(Path(args.gold).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"run_live_extraction: 错误：无法读取金标文件 {args.gold}（{type(exc).__name__}）", file=sys.stderr)
        return EXIT_CONFIG
    try:
        outcome = run(
            gold, environ=env, model_client=model_client, run_id=args.run_id,
            glean_rounds=args.glean_rounds, section_depth=args.section_depth,
            entity_max_output_tokens=args.entity_max_output_tokens,
            relation_max_output_tokens=args.relation_max_output_tokens,
            progress=lambda line: print(line, file=sys.stderr, flush=True),
        )
    except RunConfigError as exc:
        print(f"run_live_extraction: 配置错误：{exc}", file=sys.stderr)
        return EXIT_CONFIG

    out = Path(args.out)
    if outcome.predictions is not None:
        _load_evaluator().validate_predictions(outcome.predictions)  # 写出前按 README 格式自检
        _write_json(out, outcome.predictions)
    if args.run_log:
        _write_json(Path(args.run_log), outcome.run_log)

    log = outcome.run_log
    calls = log["model_calls"]
    print(f"运行 {log['run_id']}：模式 {log['mode']}，模型 {log['model']['id']}"
          f"（响应模型：{', '.join(calls['responded_models']) or '无'}）")
    print(f"块 {log['chunk_count']}，失败块 {len(log['chunk_failures'])}；小节 {log['section_count']}，"
          f"失败小节 {len(log['section_failures'])}")
    print(f"实体 {log['counts']['entities']}（简化融合合并 {log['fusion']['merged']}），"
          f"关系 {log['counts']['relations']}")
    print(f"模型调用 {calls['calls']} 次，usage 输入 {calls['usage_input_tokens']} / 输出 "
          f"{calls['usage_output_tokens']} token，计费 {calls['billed_tokens']} token")
    if log["model"]["is_fake"]:
        print("注意：fake 模型结果只验证流程，不能证明达标。")
    if outcome.exit_code != EXIT_OK:
        print(f"run_live_extraction: 已停止：{outcome.message}", file=sys.stderr)
        return outcome.exit_code

    base = out.parent
    print("注意：以上为简化融合结果，只是初步数字，不是验收 7 的最终判定（须经 E12 完整流程）。")
    print("下一步：")
    print(f"  python3 evaluation/evaluate_extraction.py sample --predictions {out} "
          f"--seed {DEFAULT_SEED} --size 100 > {base / 'sample.json'}")
    print(f"  python3 evaluation/evaluate_extraction.py score --gold {args.gold} --predictions {out} "
          f"--out {base / 'report.json'}")
    print(f"  判定后：python3 evaluation/evaluate_extraction.py score --gold {args.gold} --predictions {out} "
          f"--judgments {base / 'judgments.json'} --out {base / 'report.json'}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
