#!/usr/bin/env python3
"""K13：抽取消融实验——同一标注集、同一模型、同一计分口径下对比三种抽取配置。

用法（真实模型须在能直连供应商的本机运行，见 ``evaluation/reports/ablation.md``「本机运行步骤」）：

    python3 evaluation/ablation.py run --gold evaluation/fixtures/synthetic.json --out-dir <目录>
    python3 evaluation/ablation.py summarize --gold evaluation/fixtures/synthetic.json --out-dir <目录>

三组配置（``GROUPS``）：

- ``single_stage`` 单阶段：每个块一次调用，用消融专用提示词 ``evaluation/prompts/extract_joint.yaml``
  同时给出实体与关系；关系只能在同一块内、在该块自己抽出的实体之间判断。实体、关系逐条校验复用
  E05/E11 的同一套规则（类型闭集、证据逐字、先修表述、方向、自环、重复），输出不合规同样修复一次。
- ``two_stage`` 两阶段：K02 ``run_live_extraction.run``，E05 块级实体 → 简化融合 → 按小节 E11 关系，
  E06 补漏关闭（与生产缺省一致）。
- ``two_stage_gleaning`` 两阶段 + 补漏：同上，E06 补漏开启 ``--glean-rounds`` 轮（缺省 1）。

三组共用：D03→D08→D09 解析与分块、简化融合（E08 ``normalize_name`` 主键去重，保留首次出现）、
E04 调用策略（重试、熔断、预算）、``evaluate_extraction.score`` 自动比对与固定种子抽样。
单阶段的输出上限缺省为两阶段两类调用上限之和，使三组每块可用的输出量相同。

预算：每组一个运行 ID，单任务预算（``LLM_TASK_TOKEN_BUDGET``）按组计；每日预算按本次三组累计，
后一组开跑前把已用量从日预算里扣掉再交 E04 执行，用尽则后续组记为 ``skipped``。
预算拒绝只停当前组，其余组照跑；鉴权失败或调用记录预写失败会让后续每次调用都失败，因此停止全部
剩余组（记为 ``not_run``）。

输出目录：``<out-dir>/<组>/`` 下 ``predictions.json``（成功时）、``run.json``、``report.json``（自动比对，
有 ``judgments.json`` 时带人工判定）、``sample.json``（待判定条目）；``<out-dir>/ablation.json`` 与
``ablation.md`` 为三组对照。predictions 含资料原文证据，不入库。

口径：``model.is_fake`` 为真时所有结论标「假模型，只验证流程」，**不得当作真实效果**；预测实体为 0 的组
标「空样本」；失败或未运行的组保留行并写明原因，不从表中省略。

退出码：0 全部组成功；2 配置错误；3 有组因预算停止或跳过；4 有组中止或未运行。
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
EVALUATION_DIR = REPO / "evaluation"

try:  # 推荐 ``pip install -e ./src/backend``；未安装时退回仓库内源码路径
    import app  # noqa: F401
except ImportError:  # pragma: no cover - 取决于执行环境
    sys.path.insert(0, str(REPO / "src" / "backend"))

from app.services.ai.client import Message, ModelClient, ModelError, ModelOutputError, ModelRequest, ModelResult  # noqa: E402
from app.services.ai.entities import (  # noqa: E402
    ENTITY_PROMPT_PURPOSE,
    REPAIR_PURPOSE,
    FailureReason,
    _OutputRejected,
)
from app.services.ai.entities import _validate as validate_entities  # noqa: E402
from app.services.ai.fake import FakeModelClient  # noqa: E402
from app.services.ai.prompts import PromptLibrary  # noqa: E402
from app.services.ai.relations import SourceChunk  # noqa: E402
from app.services.ai.relations import _validate as validate_relations  # noqa: E402
from app.services.fusion.normalize import normalize_name  # noqa: E402
from app.services.graph.dag import find_cycle  # noqa: E402


def _load_module(name: str, filename: str):
    module = sys.modules.get(name)
    if module is not None:
        return module
    spec = importlib.util.spec_from_file_location(name, EVALUATION_DIR / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


#: K02 抽取脚本与评测器（``evaluation/`` 不是包，按文件路径导入）
k02 = _load_module("_k13_run_live_extraction", "run_live_extraction.py")
evaluator = _load_module("_k13_evaluate_extraction", "evaluate_extraction.py")

GROUPS = ("single_stage", "two_stage", "two_stage_gleaning")
GROUP_LABELS = {
    "single_stage": "单阶段",
    "two_stage": "两阶段",
    "two_stage_gleaning": "两阶段 + 补漏",
}

JOINT_PROMPT_PURPOSE = "extract_joint"
JOINT_PROMPT_VERSION = 1
JOINT_PROMPTS_DIR = EVALUATION_DIR / "prompts"
DEFAULT_GLEAN_ROUNDS = 1
DEFAULT_JOINT_MAX_OUTPUT_TOKENS = k02.DEFAULT_ENTITY_MAX_OUTPUT_TOKENS + k02.DEFAULT_RELATION_MAX_OUTPUT_TOKENS

EXIT_OK = 0
EXIT_CONFIG = 2
EXIT_BUDGET = 3
EXIT_ABORTED = 4

STATUS_OK = "ok"
STATUS_BUDGET = "budget_exceeded"
STATUS_ABORTED = "aborted"
STATUS_SKIPPED = "skipped"
STATUS_NOT_RUN = "not_run"

SINGLE_STAGE_NOTE = (
    "单阶段：每块一次调用同时抽实体与关系（evaluation/prompts/extract_joint.yaml），关系只在块内、"
    "该块自己抽出的实体之间判断；实体与关系的逐条校验复用 E05/E11。"
)
FAKE_WARNING = "假模型结果只验证流程，不代表任何抽取效果，不得写入结论。"
FUSION_CAVEAT = (
    "三组都用简化融合（只按 E08 规范化名称去重）；完整融合（E08～E10）接入 merging 后，"
    "各组数字与组间差距都可能变化，本结论届时需重跑。"
)
PREDICTIONS = "predictions.json"
RUN_LOG = "run.json"
REPORT = "report.json"
SAMPLE = "sample.json"
JUDGMENTS = "judgments.json"


# ---------------------------------------------------------------- fake 应答


def fake_responder(request: ModelRequest) -> str:
    """``LLM_MODE=fake`` 的确定性应答：单阶段用途在 K02 fake 实体应答上补 ID 与块内关系，其余交 K02。

    关系为相邻两个实体一条 ``RELATED_TO``，证据取第一个实体的证据（块内路径行，必为块文本子串）。
    内容与真实抽取无关，只为让三组流程跑通。
    """
    if request.purpose != JOINT_PROMPT_PURPOSE:
        return k02.fake_responder(request)
    entities = json.loads(k02.fake_responder(replace(request, purpose=ENTITY_PROMPT_PURPOSE)))["entities"]
    for index, entity in enumerate(entities, 1):
        entity["id"] = f"e{index}"
    relations = [
        {"from_id": a["id"], "to_id": b["id"], "type": "RELATED_TO", "evidence": entities[0]["evidence"],
         "confidence": 0.5}
        for a, b in zip(entities, entities[1:])
    ]
    return json.dumps({"entities": entities, "relations": relations}, ensure_ascii=False)


# ---------------------------------------------------------------- 单阶段


def _parse_joint(result: ModelResult) -> tuple[list[Any], list[Any]]:
    if result.finish_reason == "length":
        raise _OutputRejected(FailureReason.TRUNCATED)
    try:
        data = result.json()
    except ModelOutputError:
        raise _OutputRejected(FailureReason.INVALID_JSON) from None
    if (not isinstance(data, dict) or not isinstance(data.get("entities"), list)
            or not isinstance(data.get("relations"), list)):
        raise _OutputRejected(FailureReason.INVALID_STRUCTURE)
    return data["entities"], data["relations"]


def run_single_stage(
    gold: Mapping[str, Any],
    *,
    environ: Mapping[str, str],
    model_client: ModelClient | None = None,
    run_id: str | None = None,
    max_output_tokens: int = DEFAULT_JOINT_MAX_OUTPUT_TOKENS,
    prompts: PromptLibrary | None = None,
    progress: Callable[[str], None] | None = None,
):
    """单阶段抽取（不读写文件），返回与 K02 ``run`` 同形的 ``RunOutcome``。配置错误抛 ``RunConfigError``。"""
    if type(max_output_tokens) is not int or max_output_tokens < 1:
        raise k02.RunConfigError("单阶段输出上限必须是 ≥ 1 的整数")
    settings = k02.load_run_settings(environ)
    runtime = k02.build_runtime(settings, model_client=model_client)
    library = prompts if prompts is not None else PromptLibrary(JOINT_PROMPTS_DIR)
    template = library.get(JOINT_PROMPT_PURPOSE, JOINT_PROMPT_VERSION)

    documents = gold.get("documents") or []
    if not documents or not isinstance(documents[0].get("text"), str):
        raise k02.RunConfigError("金标文件缺少 documents[0].text")
    document = documents[0]
    if document.get("format", "md") not in ("md", "markdown"):
        raise k02.RunConfigError(f"只支持 Markdown 章节，documents[0].format={document.get('format')!r}")
    dataset_id = str(gold.get("dataset_id", ""))
    course_id = str((gold.get("course") or {}).get("id") or "k13-eval-course")
    document_id = str(document.get("id") or "k13-eval-document")
    started = datetime.now(UTC)
    run_id = run_id or f"k13-single-{'fake' if runtime.is_fake else 'live'}-{started.strftime('%Y%m%dT%H%M%SZ')}"

    revision_id, prepared = k02.prepare_chunks(document["text"], course_id=course_id, document_id=document_id)

    entity_dropped: dict[str, int] = {}
    relation_dropped: dict[str, int] = {}
    fusion_dropped: dict[str, int] = {}
    chunk_failures: list[dict[str, Any]] = []
    fused: dict[str, Any] = {}
    merged = 0
    type_conflicts = 0
    relations: dict[tuple[str, str, str], dict[str, Any]] = {}
    status, message, exit_code = "ok", "", k02.EXIT_OK

    try:
        for index, item in enumerate(prepared, 1):
            identity = item.identity
            section = " > ".join(item.chunk.section_titles)
            if progress is not None:
                progress(f"[单阶段 {index}/{len(prepared)}] {section or '（无标题）'}")
            if not item.text.strip():
                continue
            client = runtime.policy.bind(k02.CallAttribution(
                course_id=course_id, task_id=run_id, chunk_id=identity.chunk_id, task_attempt=1, chunk_attempt=1))
            messages = (Message("user", template.render({"chunk_text": item.text}).text),)

            def request(purpose: str, model: str) -> ModelRequest:
                return ModelRequest(purpose=purpose, model=model, messages=messages,
                                    max_output_tokens=max_output_tokens, response_format="json")

            failure_base = {"ordinal": identity.ordinal, "chunk_id": identity.chunk_id, "section": section}
            try:
                result = client.complete(request(JOINT_PROMPT_PURPOSE, runtime.model_id))
                try:
                    raw_entities, raw_relations = _parse_joint(result)
                except _OutputRejected:
                    # 同一模型、同一消息修复一次（与 E05/E11 一致）
                    result = client.complete(request(REPAIR_PURPOSE, result.model_requested))
                    try:
                        raw_entities, raw_relations = _parse_joint(result)
                    except _OutputRejected as rejected:
                        chunk_failures.append({**failure_base, "stage": "joint", "error": rejected.reason.value,
                                               "attempts": 2})
                        continue
            except ModelError as error:
                k02._check_stop(error)
                chunk_failures.append({**failure_base, "stage": "joint", "error": k02._error_code(error)})
                continue

            # ---- 实体：逐条走 E05 校验，保留模型给的块内 ID
            local_to_fused: dict[str, str] = {}
            for raw in raw_entities:
                local_id = raw.get("id") if isinstance(raw, dict) else None
                candidates, dropped = validate_entities([raw], identity, item.text)
                for reason, n in dropped.items():
                    k02._count(entity_dropped, reason.value, n)
                if not candidates:
                    continue
                if not isinstance(local_id, str) or not local_id.strip() or local_id in local_to_fused:
                    k02._count(entity_dropped, "invalid_local_id")
                    continue
                candidate = candidates[0]
                try:
                    key = normalize_name(candidate.name).key
                except ValueError:
                    k02._count(fusion_dropped, "empty_name_key")
                    continue
                existing = fused.get(key)
                if existing is not None:
                    merged += 1
                    if existing.type != candidate.type:
                        type_conflicts += 1
                    existing.chunk_ids.add(identity.chunk_id)
                else:
                    existing = fused[key] = k02.FusedEntity(
                        id=f"p-e{len(fused) + 1:03d}", name=candidate.name, type=candidate.type,
                        definition=candidate.definition, evidence=candidate.evidence, section=section,
                        chunk_ids={identity.chunk_id})
                local_to_fused[local_id] = existing.id

            # ---- 关系：块内 ID 换成融合后 ID，再走 E11 校验（端点、证据、先修表述、方向、重复）
            in_chunk = set(local_to_fused.values())
            entity_types = {e.id: e.type for e in fused.values() if e.id in in_chunk}
            mapped: list[Any] = []
            for raw in raw_relations:
                if isinstance(raw, dict):
                    raw = dict(raw)
                    for end in ("from_id", "to_id"):
                        if isinstance(raw.get(end), str):
                            raw[end] = local_to_fused.get(raw[end], f"unknown:{raw[end]}")
                mapped.append(raw)
            if mapped:
                candidates, dropped = validate_relations(mapped, entity_types, (SourceChunk(identity, item.text),))
                for reason, n in dropped.items():
                    k02._count(relation_dropped, reason.value, n)
                for candidate in candidates:
                    rkey = k02._relation_key(candidate.from_id, candidate.to_id, candidate.type)
                    if rkey in relations:
                        k02._count(relation_dropped, "cross_chunk_duplicate")
                        continue
                    relations[rkey] = {"from": candidate.from_id, "to": candidate.to_id, "type": candidate.type,
                                       "evidence": candidate.evidence, "confidence": candidate.confidence,
                                       "section": section}
    except k02._Stop as stop:
        status, message, exit_code = stop.status, stop.message, stop.exit_code

    entities_out = [
        {"id": e.id, "name": e.name, "type": e.type, "source": "ai", "definition": e.definition,
         "evidence": e.evidence, "section": e.section}
        for e in fused.values()
    ]
    relations_out = [{"id": f"p-r{i:03d}", "source": "ai", **rel} for i, rel in enumerate(relations.values(), 1)]
    prereq_edges = [(r["from"], r["to"]) for r in relations_out if r["type"] == "PREREQUISITE"]
    cycle = find_cycle([e["id"] for e in entities_out], prereq_edges) if prereq_edges else None

    responded = runtime.store.responded_models()
    model: dict[str, Any] = {"id": runtime.model_id, "is_fake": runtime.is_fake}
    if len(responded) == 1:
        model["responded"] = responded[0]
    elif responded:
        model["responded"] = responded
    prompt_versions = {JOINT_PROMPT_PURPOSE: JOINT_PROMPT_VERSION}
    fusion = {"mode": "simplified", "method": "e08_normalize_name_key_first_occurrence", "note": k02.FUSION_NOTE}

    predictions = None
    if exit_code == k02.EXIT_OK:
        predictions = {"run_id": run_id, "dataset_id": dataset_id, "model": model,
                       "prompt_versions": prompt_versions, "fusion": fusion,
                       "entities": entities_out, "relations": relations_out}
    run_log = {
        "run_id": run_id,
        "status": status,
        "message": message,
        "started_at": started.isoformat(timespec="seconds"),
        "finished_at": k02._now(),
        "dataset_id": dataset_id,
        "is_final_benchmark": bool(gold.get("is_final_benchmark", False)),
        "course_id": course_id,
        "document_id": document_id,
        "revision_id": revision_id,
        "mode": runtime.mode,
        "model": model,
        "has_fallback": runtime.has_fallback,
        "prompt_versions": prompt_versions,
        "prompt_sha256": {JOINT_PROMPT_PURPOSE: template.sha256},
        "max_output_tokens": {"joint": max_output_tokens},
        "budgets": {"task": settings.LLM_TASK_TOKEN_BUDGET, "daily": settings.LLM_DAILY_TOKEN_BUDGET,
                    "note": k02.MEMORY_STORE_NOTE},
        "gleaning": {"enabled": False, "max_rounds": 0, "added": 0},
        "stage_mode": "single",
        "stage_note": SINGLE_STAGE_NOTE,
        "chunk_count": len(prepared),
        "section_count": len({tuple(p.chunk.section_titles) for p in prepared}),
        "chunk_failures": chunk_failures,
        "section_failures": [],
        "dropped": {
            "entities": dict(sorted(entity_dropped.items())),
            "gleaning": {},
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
    return k02.RunOutcome(predictions=predictions, run_log=run_log, exit_code=exit_code, message=message)


# ---------------------------------------------------------------- 三组编排


def _group_status(outcome) -> str:
    if outcome.exit_code == k02.EXIT_OK:
        return STATUS_OK
    if outcome.exit_code == k02.EXIT_BUDGET:
        return STATUS_BUDGET
    return STATUS_ABORTED


def run_ablation(
    gold: Mapping[str, Any],
    *,
    environ: Mapping[str, str],
    model_client: ModelClient | None = None,
    groups: Sequence[str] = GROUPS,
    glean_rounds: int = DEFAULT_GLEAN_ROUNDS,
    run_prefix: str | None = None,
    entity_max_output_tokens: int = k02.DEFAULT_ENTITY_MAX_OUTPUT_TOKENS,
    relation_max_output_tokens: int = k02.DEFAULT_RELATION_MAX_OUTPUT_TOKENS,
    joint_max_output_tokens: int = DEFAULT_JOINT_MAX_OUTPUT_TOKENS,
    progress: Callable[[str], None] | None = None,
) -> dict[str, dict[str, Any]]:
    """按顺序跑各组（不读写文件）。返回 ``{组: {"status", "message", "outcome"}}``，未跑的组 ``outcome`` 为 None。

    ``model_client`` 只供测试注入，三组共用同一个客户端；缺省时 fake 模式用本模块 ``fake_responder``，
    live 模式由 K02 ``build_runtime`` 建 HTTP 适配器。配置错误抛 ``RunConfigError``。
    """
    unknown = [g for g in groups if g not in GROUPS]
    if unknown or not groups or len(set(groups)) != len(groups):
        raise k02.RunConfigError(f"--groups 只能取 {', '.join(GROUPS)} 且不重复")
    if "two_stage_gleaning" in groups and not 1 <= glean_rounds <= k02.MAX_ROUNDS_HARD_LIMIT:
        raise k02.RunConfigError(f"--glean-rounds 必须在 1..{k02.MAX_ROUNDS_HARD_LIMIT}")
    settings = k02.load_run_settings(environ)  # 先整体校验一次，避免跑了一组才发现缺密钥
    if model_client is None and settings.LLM_MODE != "live":
        model_client = FakeModelClient(responder=fake_responder)
    daily_budget = settings.LLM_DAILY_TOKEN_BUDGET
    prefix = run_prefix or f"k13-{'live' if settings.LLM_MODE == 'live' and model_client is None else 'fake'}-" \
        f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"

    results: dict[str, dict[str, Any]] = {}
    used = 0
    halted = ""
    for group in groups:
        if halted:
            results[group] = {"status": STATUS_NOT_RUN, "message": halted, "outcome": None}
            continue
        remaining = daily_budget - used
        if remaining <= 0:
            results[group] = {"status": STATUS_SKIPPED, "outcome": None,
                              "message": f"本次各组累计已用 {used} token，达到每日预算 {daily_budget}，未发出请求"}
            continue
        env = {**environ, "LLM_DAILY_TOKEN_BUDGET": str(remaining)}
        run_id = f"{prefix}-{group.replace('_', '-')}"
        if progress is not None:
            progress(f"== {GROUP_LABELS[group]}（{group}）开始，运行 ID {run_id}")
        if group == "single_stage":
            outcome = run_single_stage(gold, environ=env, model_client=model_client, run_id=run_id,
                                       max_output_tokens=joint_max_output_tokens, progress=progress)
        else:
            outcome = k02.run(gold, environ=env, model_client=model_client, run_id=run_id,
                              glean_rounds=glean_rounds if group == "two_stage_gleaning" else 0,
                              entity_max_output_tokens=entity_max_output_tokens,
                              relation_max_output_tokens=relation_max_output_tokens, progress=progress)
        outcome.run_log["ablation_group"] = group
        outcome.run_log["budgets"]["daily_configured"] = daily_budget
        outcome.run_log["budgets"]["daily_used_before_group"] = used
        used += outcome.run_log["model_calls"]["billed_tokens"]
        status = _group_status(outcome)
        results[group] = {"status": status, "message": outcome.message, "outcome": outcome}
        if status == STATUS_ABORTED:
            halted = f"{GROUP_LABELS[group]}组中止（{outcome.message}），后续组未运行"
    return results


# ---------------------------------------------------------------- 汇总


def _metric(block: Mapping[str, Any]) -> dict[str, Any]:
    return {k: block.get(k) for k in ("precision", "recall", "f1", "tp", "fp", "fn")}


def group_row(group: str, status: str, message: str, run_log: Mapping[str, Any] | None,
              report: Mapping[str, Any] | None) -> dict[str, Any]:
    """一组的对照行：状态、规模、成本、版本、自动比对指标与硬指标判定。缺失的部分给 None。"""
    row: dict[str, Any] = {"group": group, "label": GROUP_LABELS[group], "status": status, "message": message}
    if run_log is not None:
        calls = run_log["model_calls"]
        started = datetime.fromisoformat(run_log["started_at"])
        finished = datetime.fromisoformat(run_log["finished_at"])
        row.update(
            run_id=run_log["run_id"],
            is_fake=run_log["model"]["is_fake"],
            model=run_log["model"].get("responded", run_log["model"]["id"]),
            prompt_versions=run_log["prompt_versions"],
            prompt_sha256=run_log["prompt_sha256"],
            max_output_tokens=run_log["max_output_tokens"],
            gleaning_rounds=run_log["gleaning"]["max_rounds"],
            chunks=run_log["chunk_count"],
            chunk_failures=len(run_log["chunk_failures"]),
            section_failures=len(run_log["section_failures"]),
            entities=run_log["counts"]["entities"],
            relations=run_log["counts"]["relations"],
            merged=run_log["fusion"]["merged"],
            gleaning_added=run_log["gleaning"]["added"],
            prerequisite_cycle=run_log["prerequisite_cycle"],
            cost={
                "calls": calls["calls"],
                "by_purpose": calls["by_purpose"],
                "usage_input_tokens": calls["usage_input_tokens"],
                "usage_output_tokens": calls["usage_output_tokens"],
                "billed_tokens": calls["billed_tokens"],
                "calls_without_usage": calls["calls_without_usage"],
                "error_classes": calls["error_classes"],
            },
            seconds=int((finished - started).total_seconds()),
            empty=run_log["counts"]["entities"] == 0,
        )
    if report is not None:
        hard = report["hard_indicators"]
        row["metrics"] = {
            "entities_name_level": _metric(report["entities"]["name_level"]["overall"]),
            "entities_typed": _metric(report["entities"]["typed"]["overall"]),
            "relations": _metric(report["relations"]["overall"]),
            "relations_by_type": {t: _metric(v) for t, v in report["relations"]["by_type"].items()},
        }
        row["hard_indicators"] = {
            "verdict": hard["verdict"],
            "entity_count": hard["entity_count"]["value"],
            "entity_accuracy": hard["entity_accuracy"]["value"],
            "entity_accuracy_status": hard["entity_accuracy"]["status"],
            "relation_accuracy": hard["relation_accuracy"]["value"],
            "relation_accuracy_status": hard["relation_accuracy"]["status"],
        }
    return row


def _fmt(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def render_markdown(summary: Mapping[str, Any]) -> str:
    """把 ``ablation.json`` 渲染成可贴进报告的 Markdown（同输入逐字节相同）。"""
    rows = summary["groups"]
    lines = [f"# K13 消融对照（{summary['dataset_id']}）", ""]
    if summary["any_fake"]:
        lines += [f"> **{FAKE_WARNING}**", ""]
    lines += [f"> {FUSION_CAVEAT}", ""]
    lines += ["| 组 | 状态 | 运行 ID | 模型 | 实体 | 关系 | 实体 P/R/F1（名称级） | 实体 F1（有类型） | "
              "关系 P/R/F1 | 调用 | 计费 token | 失败块/小节 | 硬指标 |",
              "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for row in rows:
        status = row["status"] if not row.get("empty") else f"{row['status']}（空样本）"
        metrics = row.get("metrics")
        if metrics is None:
            ent = typed = rel = "—"
        else:
            e, t, r = metrics["entities_name_level"], metrics["entities_typed"], metrics["relations"]
            ent = f"{_fmt(e['precision'])} / {_fmt(e['recall'])} / {_fmt(e['f1'])}"
            typed = _fmt(t["f1"])
            rel = f"{_fmt(r['precision'])} / {_fmt(r['recall'])} / {_fmt(r['f1'])}"
        cost = row.get("cost") or {}
        failures = (f"{row['chunk_failures']}/{row['section_failures']}" if "chunk_failures" in row else "—")
        verdict = (row.get("hard_indicators") or {}).get("verdict", "—")
        model = row.get("model", "—")
        if row.get("is_fake"):
            model = f"{model}（假）"
        lines.append(" | ".join([
            f"| {row['label']}", status, _fmt(row.get("run_id")), _fmt(model), _fmt(row.get("entities")),
            _fmt(row.get("relations")), ent, typed, rel, _fmt(cost.get("calls")), _fmt(cost.get("billed_tokens")),
            failures, f"{verdict} |"]))
    notes = [row for row in rows if row["message"]]
    if notes:
        lines += ["", "说明："]
        lines += [f"- {row['label']}：{row['message']}" for row in notes]
    lines += ["", f"合计计费 {summary['total_billed_tokens']} token。自动比对口径见 evaluation/README.md；"
              "硬指标的准确率须逐组人工判定（各组目录的 sample.json → judgments.json）后运行 summarize。"]
    return "\n".join(lines) + "\n"


def _read_json(path: Path) -> Any | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def summarize_dir(gold: Mapping[str, Any], out_dir: Path, groups: Iterable[str] = GROUPS) -> dict[str, Any]:
    """读各组目录，重算 report.json / sample.json，写 ablation.json 与 ablation.md，返回汇总。

    组目录缺 run.json 视为未运行；有 ``judgments.json`` 时计入人工判定。
    """
    rows = []
    for group in groups:
        base = out_dir / group
        run_log = _read_json(base / RUN_LOG)
        predictions = _read_json(base / PREDICTIONS)
        status_file = _read_json(base / "status.json") or {}
        if run_log is None:
            rows.append(group_row(group, status_file.get("status", STATUS_NOT_RUN),
                                  status_file.get("message", "未运行"), None, None))
            continue
        report = None
        if predictions is not None:
            judgments = _read_json(base / JUDGMENTS)
            report = evaluator.score(dict(gold), predictions, judgments)
            _write_json(base / REPORT, report)
            _write_json(base / SAMPLE, evaluator.sample(predictions))
        status = status_file.get("status") or (STATUS_OK if run_log["status"] == "ok" else
                                               STATUS_BUDGET if run_log["status"] == "budget_exceeded"
                                               else STATUS_ABORTED)
        rows.append(group_row(group, status, status_file.get("message", run_log.get("message", "")),
                              run_log, report))
    summary = {
        "schema_version": 1,
        "dataset_id": gold.get("dataset_id"),
        "is_final_benchmark": bool(gold.get("is_final_benchmark", False)),
        "any_fake": any(row.get("is_fake") for row in rows),
        "fusion_caveat": FUSION_CAVEAT,
        "total_billed_tokens": sum((row.get("cost") or {}).get("billed_tokens", 0) for row in rows),
        "groups": rows,
    }
    _write_json(out_dir / "ablation.json", summary)
    (out_dir / "ablation.md").write_text(render_markdown(summary), encoding="utf-8", newline="\n")
    return summary


def write_results(results: Mapping[str, Mapping[str, Any]], out_dir: Path) -> None:
    """把 ``run_ablation`` 的结果落到各组目录；失败组只写 run.json，不写 predictions。"""
    for group, result in results.items():
        base = out_dir / group
        base.mkdir(parents=True, exist_ok=True)
        outcome = result["outcome"]
        stale = base / PREDICTIONS
        if stale.exists():
            stale.unlink()  # 本次失败时不留上一次的预测，避免混读
        if outcome is not None:
            if outcome.predictions is not None:
                evaluator.validate_predictions(outcome.predictions)
                _write_json(stale, outcome.predictions)
            _write_json(base / RUN_LOG, outcome.run_log)
        else:
            run_log = base / RUN_LOG
            if run_log.exists():
                run_log.unlink()
        _write_json(base / "status.json", {"status": result["status"], "message": result["message"]})


def exit_code_for(results: Mapping[str, Mapping[str, Any]]) -> int:
    statuses = {r["status"] for r in results.values()}
    if statuses & {STATUS_ABORTED, STATUS_NOT_RUN}:
        return EXIT_ABORTED
    if statuses & {STATUS_BUDGET, STATUS_SKIPPED}:
        return EXIT_BUDGET
    return EXIT_OK


# ---------------------------------------------------------------- CLI


def main(argv: Sequence[str] | None = None, *, environ: Mapping[str, str] | None = None,
         model_client: ModelClient | None = None) -> int:
    parser = argparse.ArgumentParser(description="K13：抽取消融实验（单阶段 / 两阶段 / 两阶段 + 补漏）")
    sub = parser.add_subparsers(dest="command", required=True)
    run_p = sub.add_parser("run", help="依次运行各组并写对照")
    run_p.add_argument("--gold", required=True)
    run_p.add_argument("--out-dir", required=True)
    run_p.add_argument("--groups", default=",".join(GROUPS), help=f"逗号分隔，缺省 {','.join(GROUPS)}")
    run_p.add_argument("--glean-rounds", type=int, default=DEFAULT_GLEAN_ROUNDS)
    run_p.add_argument("--run-prefix", help="缺省为 k13-<live|fake>-<UTC 时间>")
    run_p.add_argument("--entity-max-output-tokens", type=int, default=k02.DEFAULT_ENTITY_MAX_OUTPUT_TOKENS)
    run_p.add_argument("--relation-max-output-tokens", type=int, default=k02.DEFAULT_RELATION_MAX_OUTPUT_TOKENS)
    run_p.add_argument("--joint-max-output-tokens", type=int, default=DEFAULT_JOINT_MAX_OUTPUT_TOKENS)
    sum_p = sub.add_parser("summarize", help="按各组目录（含 judgments.json）重算对照")
    sum_p.add_argument("--gold", required=True)
    sum_p.add_argument("--out-dir", required=True)
    args = parser.parse_args(argv)
    env = os.environ if environ is None else environ

    try:
        gold = json.loads(Path(args.gold).read_text(encoding="utf-8"))
        evaluator.validate_gold(gold)
    except (OSError, json.JSONDecodeError, evaluator.EvaluationInputError) as exc:
        print(f"ablation: 错误：无法读取金标文件 {args.gold}（{type(exc).__name__}）", file=sys.stderr)
        return EXIT_CONFIG
    out_dir = Path(args.out_dir)

    if args.command == "summarize":
        summary = summarize_dir(gold, out_dir)
        print(render_markdown(summary), end="")
        return EXIT_OK

    groups = [g.strip() for g in args.groups.split(",") if g.strip()]
    try:
        results = run_ablation(
            gold, environ=env, model_client=model_client, groups=groups, glean_rounds=args.glean_rounds,
            run_prefix=args.run_prefix, entity_max_output_tokens=args.entity_max_output_tokens,
            relation_max_output_tokens=args.relation_max_output_tokens,
            joint_max_output_tokens=args.joint_max_output_tokens,
            progress=lambda line: print(line, file=sys.stderr, flush=True))
    except k02.RunConfigError as exc:
        print(f"ablation: 配置错误：{exc}", file=sys.stderr)
        return EXIT_CONFIG
    write_results(results, out_dir)
    summary = summarize_dir(gold, out_dir, groups)
    print(render_markdown(summary), end="")
    print(f"\n下一步：逐组打开 {out_dir}/<组>/sample.json 判定，存为同目录 judgments.json，再运行\n"
          f"  python3 evaluation/ablation.py summarize --gold {args.gold} --out-dir {out_dir}")
    code = exit_code_for(results)
    if code != EXIT_OK:
        print("ablation: 有组未成功完成，见上表「说明」", file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
