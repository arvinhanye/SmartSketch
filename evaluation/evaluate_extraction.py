#!/usr/bin/env python3
"""K02：知识抽取与融合离线评测（只用标准库，不调用任何模型或网络）。

输入格式由 K01 定义（``evaluation/README.md``）：金标数据集、predictions.json、judgments.json。

子命令：
    score  --gold G --predictions P [--judgments J] [--out report.json]
        计算实体（名称级 / 有类型）与关系的 tp/fp/fn/P/R/F1，按类型分组，统计错误类型，
        并判定赛题两项硬指标（specs/course-knowledge-graph.md 验收 7）。
    sample --predictions P [--seed N] [--size N]
        固定种子抽样 ``source == "ai"`` 的实体与关系，输出供人工判定的条目与 judgments 模板。

口径要点：
- 名称归一化：NFKC → casefold → 去除全部空白；预测名等于金标名或任一别名即命中。
- 一对一匹配：按预测输入顺序遍历，每个金标最多被匹配一次；后来命中已占用金标的预测记为重复（FP）。
  有类型口径沿用同一组配对，类型也相同才算 TP，因此类型错误的先到者也会占用金标。
- 关系端点经名称级配对映射到金标 ID；未映射的端点使该关系成为 FP。RELATED_TO 无向，其余三类有向。
- 分母为 0 时指标为 null；小数保留 4 位；输出键排序，相同输入逐字节一致。
- 硬指标：AI 实体数 ≥ 20；实体、关系人工判定准确率各 ≥ 70%（Fraction 精确比较，恰为 7/10 达标）。
  无判定为「未判定」；``model.is_fake`` 为真时一律「不可用于判定（假模型）」。
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import unicodedata
from fractions import Fraction
from typing import Any

ENTITY_TYPES = ("concept", "theorem", "formula", "method", "example")
RELATION_TYPES = ("CONTAINS", "PREREQUISITE", "RELATED_TO", "EXAMPLE_OF")
UNDIRECTED_TYPES = frozenset({"RELATED_TO"})
JUDGMENT_VALUES = ("correct", "incorrect")

DEFAULT_SEED = 20260926
DEFAULT_SAMPLE_SIZE = 100
ENTITY_COUNT_THRESHOLD = 20
ACCURACY_THRESHOLD = Fraction(7, 10)

VERDICT_PASS = "达标"
VERDICT_FAIL = "未达标"
VERDICT_UNDETERMINED = "未判定"
VERDICT_INCOMPLETE = "判定不完整"
VERDICT_FAKE = "不可用于判定（假模型）"

ENTITY_FP_REASONS = ("duplicate", "no_gold_match", "type_mismatch")
ENTITY_FN_REASONS = ("not_extracted", "type_mismatch")
RELATION_FP_REASONS = ("duplicate", "no_gold_match", "reversed_direction", "unmapped_endpoint", "wrong_relation_type")
RELATION_FN_REASONS = ("endpoint_not_extracted", "not_predicted", "reversed_direction", "wrong_relation_type")

DECIMALS = 4


class EvaluationInputError(ValueError):
    """输入文件结构不合法（未知类型、重复 ID、悬空端点、数据集不一致等）。"""


# ---------------------------------------------------------------- 归一化与校验


def normalize_name(name: str) -> str:
    """NFKC → casefold → 去除全部空白字符。"""
    folded = unicodedata.normalize("NFKC", name).casefold()
    return "".join(ch for ch in folded if not ch.isspace())


def _require(cond: bool, message: str) -> None:
    if not cond:
        raise EvaluationInputError(message)


def _require_str(obj: dict, key: str, where: str) -> str:
    value = obj.get(key) if isinstance(obj, dict) else None
    _require(isinstance(value, str) and value.strip() != "", f"{where} 缺少非空字符串字段 {key!r}")
    return value


def _require_list(obj: dict, key: str, where: str) -> list:
    value = obj.get(key) if isinstance(obj, dict) else None
    _require(isinstance(value, list), f"{where} 字段 {key!r} 必须是数组")
    return value


def _check_entities(entities: list, where: str, *, gold: bool) -> dict[str, dict]:
    by_id: dict[str, dict] = {}
    for idx, ent in enumerate(entities):
        loc = f"{where}.entities[{idx}]"
        _require(isinstance(ent, dict), f"{loc} 必须是对象")
        eid = _require_str(ent, "id", loc)
        _require(eid not in by_id, f"{where} 实体 ID 重复：{eid!r}")
        name = _require_str(ent, "name", loc)
        _require(normalize_name(name) != "", f"{loc} 名称归一化后为空")
        etype = ent.get("type")
        _require(etype in ENTITY_TYPES, f"{loc} 未知实体类型 {etype!r}（允许：{', '.join(ENTITY_TYPES)}）")
        if gold:
            aliases = ent.get("aliases", [])
            _require(isinstance(aliases, list) and all(isinstance(a, str) for a in aliases),
                     f"{loc} 字段 'aliases' 必须是字符串数组")
        else:
            _require_str(ent, "source", loc)
        by_id[eid] = ent
    return by_id


def _check_relations(relations: list, entity_ids: dict[str, dict], where: str) -> dict[str, dict]:
    by_id: dict[str, dict] = {}
    for idx, rel in enumerate(relations):
        loc = f"{where}.relations[{idx}]"
        _require(isinstance(rel, dict), f"{loc} 必须是对象")
        rid = _require_str(rel, "id", loc)
        _require(rid not in by_id, f"{where} 关系 ID 重复：{rid!r}")
        rtype = rel.get("type")
        _require(rtype in RELATION_TYPES, f"{loc} 未知关系类型 {rtype!r}（允许：{', '.join(RELATION_TYPES)}）")
        for end in ("from", "to"):
            ref = _require_str(rel, end, loc)
            _require(ref in entity_ids, f"{loc} 端点 {end}={ref!r} 不存在于实体列表（悬空端点）")
        by_id[rid] = rel
    return by_id


def validate_gold(data: Any) -> None:
    _require(isinstance(data, dict), "金标文件顶层必须是对象")
    _require_str(data, "dataset_id", "gold")
    body = data.get("gold")
    _require(isinstance(body, dict), "金标文件缺少对象字段 'gold'")
    ents = _check_entities(_require_list(body, "entities", "gold"), "gold", gold=True)
    _check_relations(_require_list(body, "relations", "gold"), ents, "gold")


def validate_predictions(data: Any) -> None:
    _require(isinstance(data, dict), "predictions 顶层必须是对象")
    _require_str(data, "run_id", "predictions")
    _require_str(data, "dataset_id", "predictions")
    model = data.get("model")
    _require(isinstance(model, dict) and isinstance(model.get("is_fake"), bool),
             "predictions.model 必须是对象且含布尔字段 'is_fake'")
    ents = _check_entities(_require_list(data, "entities", "predictions"), "predictions", gold=False)
    _check_relations(_require_list(data, "relations", "predictions"), ents, "predictions")


def validate_judgments(data: Any, predictions: dict) -> None:
    _require(isinstance(data, dict), "judgments 顶层必须是对象")
    run_id = _require_str(data, "run_id", "judgments")
    _require(run_id == predictions["run_id"],
             f"judgments.run_id={run_id!r} 与 predictions.run_id={predictions['run_id']!r} 不一致")
    known = {
        "entities": {e["id"] for e in predictions["entities"]},
        "relations": {r["id"] for r in predictions["relations"]},
    }
    for kind in ("entities", "relations"):
        verdicts = data.get(kind, {})
        _require(isinstance(verdicts, dict), f"judgments.{kind} 必须是对象")
        for item_id, verdict in verdicts.items():
            _require(item_id in known[kind], f"judgments.{kind} 中的 {item_id!r} 不在 predictions 中")
            _require(verdict in JUDGMENT_VALUES,
                     f"judgments.{kind}[{item_id!r}]={verdict!r} 不合法（允许：{', '.join(JUDGMENT_VALUES)}）")


# ---------------------------------------------------------------- 指标


def _ratio(num: int, den: int) -> float | None:
    return None if den == 0 else round(float(Fraction(num, den)), DECIMALS)


def _prf(tp: int, fp: int, fn: int) -> dict:
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": _ratio(tp, tp + fp),
        "recall": _ratio(tp, tp + fn),
        # README：precision 或 recall 为 null 时 F1 为 null；两者均为 0 时为 0
        "f1": None if tp + fp == 0 or tp + fn == 0 else _ratio(2 * tp, 2 * tp + fp + fn),
    }


class _Tally:
    def __init__(self, types: tuple[str, ...]):
        self.counts = {t: {"tp": 0, "fp": 0, "fn": 0} for t in types}

    def add(self, kind: str, rtype: str) -> None:
        self.counts[rtype][kind] += 1

    def report(self) -> dict:
        total = {k: sum(c[k] for c in self.counts.values()) for k in ("tp", "fp", "fn")}
        return {
            "overall": _prf(total["tp"], total["fp"], total["fn"]),
            "by_type": {t: _prf(c["tp"], c["fp"], c["fn"]) for t, c in self.counts.items()},
        }


# ---------------------------------------------------------------- 实体匹配


def _match_entities(gold_entities: list[dict], pred_entities: list[dict]) -> tuple[dict, dict, list]:
    """名称级一对一配对。返回（预测→金标映射、各变体计数、逐条明细）。"""
    index: dict[str, list[dict]] = {}
    for g in gold_entities:
        keys = {normalize_name(g["name"])} | {normalize_name(a) for a in g.get("aliases", []) if normalize_name(a)}
        for key in sorted(keys):
            index.setdefault(key, []).append(g)

    assigned: dict[str, str] = {}  # pred id → gold id
    taken: dict[str, dict] = {}  # gold id → pred
    name_level, typed = _Tally(ENTITY_TYPES), _Tally(ENTITY_TYPES)
    fp_reasons = dict.fromkeys(ENTITY_FP_REASONS, 0)
    fn_reasons = dict.fromkeys(ENTITY_FN_REASONS, 0)
    details = []

    for p in pred_entities:
        cands = index.get(normalize_name(p["name"]), [])
        free = [g for g in cands if g["id"] not in taken]
        # 同名多个金标时优先类型一致的，其余按金标顺序。
        free.sort(key=lambda g: g["type"] != p["type"])
        if free:
            g = free[0]
            assigned[p["id"]] = g["id"]
            taken[g["id"]] = p
            name_level.add("tp", g["type"])
            if g["type"] == p["type"]:
                typed.add("tp", g["type"])
                outcome = "correct"
            else:
                typed.add("fp", p["type"])
                fp_reasons["type_mismatch"] += 1
                outcome = "type_mismatch"
            details.append({"id": p["id"], "gold_id": g["id"], "outcome": outcome})
            continue
        reason = "duplicate" if cands else "no_gold_match"
        name_level.add("fp", p["type"])
        typed.add("fp", p["type"])
        fp_reasons[reason] += 1
        details.append({"id": p["id"], "gold_id": cands[0]["id"] if cands else None, "outcome": reason})

    for g in gold_entities:
        p = taken.get(g["id"])
        if p is None:
            name_level.add("fn", g["type"])
            typed.add("fn", g["type"])
            fn_reasons["not_extracted"] += 1
        elif p["type"] != g["type"]:
            typed.add("fn", g["type"])
            fn_reasons["type_mismatch"] += 1

    tallies = {"name_level": name_level.report(), "typed": typed.report()}
    errors = {"false_positive": fp_reasons, "false_negative": fn_reasons}
    return assigned, {"metrics": tallies, "errors": errors}, details


# ---------------------------------------------------------------- 关系匹配


def _rel_key(frm: str, to: str, rtype: str) -> tuple:
    if rtype in UNDIRECTED_TYPES:
        a, b = sorted((frm, to))
        return (a, b, rtype)
    return (frm, to, rtype)


def _match_relations(gold_relations: list[dict], pred_relations: list[dict], assigned: dict[str, str],
                     matched_gold_entities: set[str]) -> tuple[dict, dict, list]:
    by_key: dict[tuple, list[dict]] = {}
    pair_types: dict[frozenset, set[str]] = {}
    for g in gold_relations:
        by_key.setdefault(_rel_key(g["from"], g["to"], g["type"]), []).append(g)
        pair_types.setdefault(frozenset((g["from"], g["to"])), set()).add(g["type"])

    taken: set[str] = set()
    tally = _Tally(RELATION_TYPES)
    fp_reasons = dict.fromkeys(RELATION_FP_REASONS, 0)
    fn_reasons = dict.fromkeys(RELATION_FN_REASONS, 0)
    mapped_preds: list[tuple[str, str, str]] = []
    details = []

    for p in pred_relations:
        frm, to = assigned.get(p["from"]), assigned.get(p["to"])
        gold_id = None
        if frm is None or to is None:
            outcome = "unmapped_endpoint"
        else:
            mapped_preds.append((frm, to, p["type"]))
            cands = by_key.get(_rel_key(frm, to, p["type"]), [])
            free = [g for g in cands if g["id"] not in taken]
            if free:
                gold_id, outcome = free[0]["id"], "correct"
                taken.add(gold_id)
            elif cands:
                gold_id, outcome = cands[0]["id"], "duplicate"
            elif p["type"] not in UNDIRECTED_TYPES and (to, frm, p["type"]) in by_key:
                gold_id, outcome = by_key[(to, frm, p["type"])][0]["id"], "reversed_direction"
            elif pair_types.get(frozenset((frm, to)), set()) - {p["type"]}:
                outcome = "wrong_relation_type"
            else:
                outcome = "no_gold_match"
        if outcome == "correct":
            tally.add("tp", p["type"])
        else:
            tally.add("fp", p["type"])
            fp_reasons[outcome] += 1
        details.append({"id": p["id"], "gold_id": gold_id, "outcome": outcome})

    for g in gold_relations:
        if g["id"] in taken:
            continue
        tally.add("fn", g["type"])
        if g["from"] not in matched_gold_entities or g["to"] not in matched_gold_entities:
            reason = "endpoint_not_extracted"
        elif g["type"] not in UNDIRECTED_TYPES and (g["to"], g["from"], g["type"]) in mapped_preds:
            reason = "reversed_direction"
        elif any(frozenset((f, t)) == frozenset((g["from"], g["to"])) and rt != g["type"]
                 for f, t, rt in mapped_preds):
            reason = "wrong_relation_type"
        else:
            reason = "not_predicted"
        fn_reasons[reason] += 1

    return tally.report(), {"false_positive": fp_reasons, "false_negative": fn_reasons}, details


# ---------------------------------------------------------------- 硬指标


def _accuracy(verdicts: dict | None, sampled_ids: list[str]) -> dict:
    """人工判定准确率，只统计按固定种子抽中的条目（README「抽样」）。

    ``status``：``not_judged``（无判定或总体为空）、``incomplete``（抽中项有缺判）、``judged``。
    """
    base = {"threshold": float(ACCURACY_THRESHOLD), "threshold_fraction": str(ACCURACY_THRESHOLD),
            "sampled": len(sampled_ids)}
    empty = {"correct": 0, "judged": 0, "missing": len(sampled_ids), "value": None, "passed": None, "gap": None}
    if not verdicts or not sampled_ids:
        return {**base, **empty, "status": "not_judged"}
    missing = [i for i in sampled_ids if i not in verdicts]
    if missing:
        return {**base, **empty, "missing": len(missing), "status": "incomplete"}
    judged = len(sampled_ids)
    correct = sum(1 for i in sampled_ids if verdicts[i] == "correct")
    frac = Fraction(correct, judged)
    passed = frac >= ACCURACY_THRESHOLD
    gap = 0.0 if passed else round(float(ACCURACY_THRESHOLD - frac), DECIMALS)
    return {**base, "status": "judged", "correct": correct, "judged": judged, "missing": 0,
            "value": round(float(frac), DECIMALS), "passed": passed, "gap": gap}


def _hard_indicators(predictions: dict, judgments: dict | None) -> dict:
    ai_count = sum(1 for e in predictions["entities"] if e["source"] == "ai")
    count = {
        "value": ai_count,
        "threshold": ENTITY_COUNT_THRESHOLD,
        "passed": ai_count >= ENTITY_COUNT_THRESHOLD,
        "gap": max(0, ENTITY_COUNT_THRESHOLD - ai_count),
    }
    seed = judgments.get("seed", DEFAULT_SEED) if judgments else DEFAULT_SEED
    drawn = sample(predictions, seed=seed)
    ent_acc = _accuracy(judgments.get("entities") if judgments else None,
                        [i["id"] for i in drawn["entities"]["items"]])
    rel_acc = _accuracy(judgments.get("relations") if judgments else None,
                        [i["id"] for i in drawn["relations"]["items"]])
    is_fake = predictions["model"]["is_fake"]
    if is_fake:
        verdict, passed = VERDICT_FAKE, None
    elif not count["passed"] or ent_acc["passed"] is False or rel_acc["passed"] is False:
        # README：实体数 < 20 或任一准确率 < 70% 即「未达标」，不等其余判定
        verdict, passed = VERDICT_FAIL, False
    elif "incomplete" in (ent_acc["status"], rel_acc["status"]):
        verdict, passed = VERDICT_INCOMPLETE, None
    elif ent_acc["passed"] is None or rel_acc["passed"] is None:
        verdict, passed = VERDICT_UNDETERMINED, None
    else:
        passed = count["passed"] and ent_acc["passed"] and rel_acc["passed"]
        verdict = VERDICT_PASS if passed else VERDICT_FAIL
    return {
        "entity_count": count,
        "entity_accuracy": ent_acc,
        "relation_accuracy": rel_acc,
        "is_fake_model": is_fake,
        "passed": passed,
        "verdict": verdict,
    }


# ---------------------------------------------------------------- 入口函数


def score(gold: dict, predictions: dict, judgments: dict | None = None) -> dict:
    """计算完整评测结果（纯函数，不读写文件）。"""
    validate_gold(gold)
    validate_predictions(predictions)
    _require(gold["dataset_id"] == predictions["dataset_id"],
             f"dataset_id 不一致：gold={gold['dataset_id']!r}，predictions={predictions['dataset_id']!r}")
    if judgments is not None:
        validate_judgments(judgments, predictions)

    g_ents, g_rels = gold["gold"]["entities"], gold["gold"]["relations"]
    # README：各指标只统计 source = "ai" 的条目；其他来源只报告数量
    ai_ents = [e for e in predictions["entities"] if e["source"] == "ai"]
    ai_rels = [r for r in predictions["relations"] if r["source"] == "ai"]
    assigned, ent_result, ent_details = _match_entities(g_ents, ai_ents)
    rel_metrics, rel_errors, rel_details = _match_relations(
        g_rels, ai_rels, assigned, set(assigned.values()))

    return {
        "schema_version": 1,
        "dataset_id": gold["dataset_id"],
        "is_final_benchmark": bool(gold.get("is_final_benchmark", False)),
        "run_id": predictions["run_id"],
        "model": predictions["model"],
        "prompt_versions": predictions.get("prompt_versions", {}),
        "judge": judgments.get("judge") if judgments else None,
        "counts": {
            "gold_entities": len(g_ents),
            "gold_relations": len(g_rels),
            "predicted_entities": len(predictions["entities"]),
            "predicted_relations": len(predictions["relations"]),
            "non_ai_entities": len(predictions["entities"]) - len(ai_ents),
            "non_ai_relations": len(predictions["relations"]) - len(ai_rels),
        },
        "entities": ent_result["metrics"],
        "relations": rel_metrics,
        "errors": {"entities": ent_result["errors"], "relations": rel_errors},
        "details": {"entities": ent_details, "relations": rel_details},
        "hard_indicators": _hard_indicators(predictions, judgments),
    }


def sample(predictions: dict, seed: int = DEFAULT_SEED, size: int = DEFAULT_SAMPLE_SIZE) -> dict:
    """固定种子抽样 source == "ai" 的实体与关系；总体 ≤ size 时全量检查。"""
    validate_predictions(predictions)
    _require(isinstance(size, int) and size >= 1, f"抽样量必须是正整数，收到 {size!r}")
    names = {e["id"]: e["name"] for e in predictions["entities"]}

    def draw(items: list[dict], render) -> dict:
        population = sorted((i for i in items if i["source"] == "ai"), key=lambda i: i["id"])
        if len(population) <= size:
            chosen, mode = population, "full"
        else:
            # 每类各用一个独立的 Random(seed)，实体与关系的抽样互不影响。
            chosen, mode = random.Random(seed).sample(population, size), "sampled"
        return {
            "population": len(population),
            "mode": mode,
            "items": [render(i) for i in sorted(chosen, key=lambda i: i["id"])],
        }

    entities = draw(predictions["entities"], lambda e: {"id": e["id"], "name": e["name"], "type": e["type"]})
    relations = draw(predictions["relations"], lambda r: {
        "id": r["id"], "type": r["type"], "from": r["from"], "from_name": names[r["from"]],
        "to": r["to"], "to_name": names[r["to"]]})
    return {
        "run_id": predictions["run_id"],
        "dataset_id": predictions["dataset_id"],
        "model": predictions["model"],
        "seed": seed,
        "size": size,
        "entities": entities,
        "relations": relations,
        "judgments_template": {
            "run_id": predictions["run_id"],
            "judge": "",
            "seed": seed,
            "entities": {i["id"]: None for i in entities["items"]},
            "relations": {i["id"]: None for i in relations["items"]},
            "notes": {},
        },
    }


def dumps(result: dict) -> str:
    """确定性序列化：键排序、UTF-8 原文、两空格缩进、末尾换行。"""
    return json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


# ---------------------------------------------------------------- CLI


def _load(path: str, label: str) -> Any:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except OSError as exc:
        raise EvaluationInputError(f"无法读取{label}文件 {path}：{exc.strerror}") from exc
    except json.JSONDecodeError as exc:
        raise EvaluationInputError(f"{label}文件 {path} 不是合法 JSON：第 {exc.lineno} 行 {exc.msg}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="K02 知识抽取与融合离线评测（不调用模型）")
    sub = parser.add_subparsers(dest="command", required=True)
    p_score = sub.add_parser("score", help="计算指标与硬指标判定")
    p_score.add_argument("--gold", required=True)
    p_score.add_argument("--predictions", required=True)
    p_score.add_argument("--judgments")
    p_score.add_argument("--out", help="输出 JSON 路径；缺省写到标准输出")
    p_sample = sub.add_parser("sample", help="固定种子抽样供人工判定")
    p_sample.add_argument("--predictions", required=True)
    p_sample.add_argument("--seed", type=int, default=DEFAULT_SEED)
    p_sample.add_argument("--size", type=int, default=DEFAULT_SAMPLE_SIZE)
    args = parser.parse_args(argv)

    try:
        if args.command == "score":
            gold = _load(args.gold, "金标")
            preds = _load(args.predictions, "预测")
            judg = _load(args.judgments, "判定") if args.judgments else None
            text = dumps(score(gold, preds, judg))
            if args.out:
                with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
                    fh.write(text)
            else:
                sys.stdout.write(text)
        else:
            sys.stdout.write(dumps(sample(_load(args.predictions, "预测"), seed=args.seed, size=args.size)))
    except EvaluationInputError as exc:
        print(f"evaluate_extraction: 错误：{exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
