"""K02：抽取与融合离线评测（``docs/atomic-tasks.json`` K02；``specs/course-knowledge-graph.md`` 验收 7）。

输入：K01 定义的金标数据集、predictions.json、judgments.json；输出：分项指标 JSON 与赛题两项硬指标判定。
验收：空分母为 null；别名/归一化/一对一匹配；有类型与无类型两种口径；RELATED_TO 无向、其余有向；
四类关系与五类实体分组全部列出；恰为 20 个、恰为 70% 视为达标；假模型不充真实效果；
无判定时为「未判定」；固定输入重复结果逐字节一致；固定种子抽样可复现；坏输入非零退出。

``evaluation/`` 不是包，按文件路径导入被测模块；全部用本文件内的小型内联夹具，不依赖 K01 夹具。
"""

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "evaluation" / "evaluate_extraction.py"
SYNTHETIC = REPO / "evaluation" / "fixtures" / "synthetic.json"


def _load_module():
    spec = importlib.util.spec_from_file_location("evaluate_extraction", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("evaluate_extraction", module)
    spec.loader.exec_module(module)
    return module


ev = _load_module()

ENTITY_TYPES = ["concept", "example", "formula", "method", "theorem"]
RELATION_TYPES = ["CONTAINS", "EXAMPLE_OF", "PREREQUISITE", "RELATED_TO"]


# ---------------------------------------------------------------- 夹具构造


def g_ent(eid, name, etype="concept", aliases=()):
    return {"id": eid, "name": name, "aliases": list(aliases), "type": etype,
            "document_id": "doc-1", "evidence": "…"}


def g_rel(rid, frm, to, rtype):
    return {"id": rid, "from": frm, "to": to, "type": rtype, "document_id": "doc-1", "evidence": "…"}


def gold(entities, relations=()):
    return {
        "schema_version": 1,
        "dataset_id": "ds-test",
        "is_final_benchmark": False,
        "license": "自编，仅供测试",
        "course": {"id": "c-1", "name": "数据结构", "chapter": "第 3 章"},
        "documents": [{"id": "doc-1", "filename": "ch3.md", "format": "md", "text": "…"}],
        "gold": {"entities": list(entities), "relations": list(relations)},
    }


def p_ent(eid, name, etype="concept", source="ai"):
    return {"id": eid, "name": name, "type": etype, "source": source}


def p_rel(rid, frm, to, rtype, source="ai"):
    return {"id": rid, "from": frm, "to": to, "type": rtype, "source": source}


def preds(entities, relations=(), *, is_fake=False, run_id="run-1"):
    return {
        "run_id": run_id,
        "dataset_id": "ds-test",
        "model": {"id": "model-x", "is_fake": is_fake},
        "prompt_versions": {"extract_entities": 2, "extract_relations": 2},
        "entities": list(entities),
        "relations": list(relations),
    }


def judgments(entities=None, relations=None, run_id="run-1"):
    return {"run_id": run_id, "judge": "测试员", "seed": 20260926,
            "entities": dict(entities or {}), "relations": dict(relations or {}), "notes": {}}


def many_entities(n, prefix="p-e"):
    return [p_ent(f"{prefix}{i:03d}", f"概念{i}") for i in range(n)]


BASE_GOLD = gold(
    [
        g_ent("g-e1", "栈", aliases=["堆栈"]),
        g_ent("g-e2", "队列"),
        g_ent("g-e3", "递归", "method"),
        g_ent("g-e4", "括号匹配", "example"),
    ],
    [
        g_rel("g-r1", "g-e1", "g-e3", "PREREQUISITE"),
        g_rel("g-r2", "g-e1", "g-e2", "RELATED_TO"),
        g_rel("g-r3", "g-e4", "g-e1", "EXAMPLE_OF"),
    ],
)


def score(g, p, j=None):
    return ev.score(g, p, j)


# ---------------------------------------------------------------- 名称归一化与实体匹配


def test_normalize_name_nfkc_casefold_and_whitespace():
    assert ev.normalize_name("  Ｓｔａｃｋ　栈\t") == "stack栈"
    assert ev.normalize_name("B 树") == ev.normalize_name("b树")


def test_alias_match_counts_as_true_positive():
    result = score(BASE_GOLD, preds([p_ent("p1", "堆栈")]))
    overall = result["entities"]["name_level"]["overall"]
    assert (overall["tp"], overall["fp"], overall["fn"]) == (1, 0, 3)


def test_whitespace_and_fullwidth_normalization_match():
    g = gold([g_ent("g1", "Hash表")])
    result = score(g, preds([p_ent("p1", " ＨＡＳＨ 表 ")]))
    assert result["entities"]["typed"]["overall"]["tp"] == 1


def test_one_to_one_duplicate_is_false_positive():
    result = score(BASE_GOLD, preds([p_ent("p1", "栈"), p_ent("p2", "堆栈")]))
    overall = result["entities"]["name_level"]["overall"]
    assert (overall["tp"], overall["fp"]) == (1, 1)
    assert result["errors"]["entities"]["false_positive"]["duplicate"] == 1


def test_one_to_one_follows_input_order():
    # 第一个预测先占用金标；类型错的先到者占位，后到的正确类型仍算重复。
    result = score(BASE_GOLD, preds([p_ent("p1", "栈", "theorem"), p_ent("p2", "栈", "concept")]))
    typed = result["entities"]["typed"]["overall"]
    assert typed["tp"] == 0
    assert result["errors"]["entities"]["false_positive"]["type_mismatch"] == 1
    assert result["errors"]["entities"]["false_positive"]["duplicate"] == 1


def test_typed_vs_untyped_matching():
    result = score(BASE_GOLD, preds([p_ent("p1", "递归", "concept")]))
    name_level = result["entities"]["name_level"]["overall"]
    typed = result["entities"]["typed"]["overall"]
    assert name_level["tp"] == 1
    assert (typed["tp"], typed["fp"], typed["fn"]) == (0, 1, 4)
    assert result["errors"]["entities"]["false_positive"]["type_mismatch"] == 1
    assert result["errors"]["entities"]["false_negative"]["type_mismatch"] == 1


# ---------------------------------------------------------------- 关系匹配


ENTS = [p_ent("p1", "栈"), p_ent("p2", "队列"), p_ent("p3", "递归", "method"), p_ent("p4", "括号匹配", "example")]


def rel_result(rels):
    return score(BASE_GOLD, preds(ENTS, rels))


def test_related_to_is_undirected():
    result = rel_result([p_rel("r1", "p2", "p1", "RELATED_TO")])
    assert result["relations"]["by_type"]["RELATED_TO"]["tp"] == 1


def test_prerequisite_reversed_is_error():
    result = rel_result([p_rel("r1", "p3", "p1", "PREREQUISITE")])
    assert result["relations"]["by_type"]["PREREQUISITE"]["tp"] == 0
    assert result["relations"]["by_type"]["PREREQUISITE"]["fp"] == 1
    assert result["errors"]["relations"]["false_positive"]["reversed_direction"] == 1
    assert result["errors"]["relations"]["false_negative"]["reversed_direction"] == 1


def test_wrong_relation_type_is_error():
    result = rel_result([p_rel("r1", "p1", "p3", "RELATED_TO")])
    assert result["relations"]["overall"]["tp"] == 0
    assert result["errors"]["relations"]["false_positive"]["wrong_relation_type"] == 1
    assert result["errors"]["relations"]["false_negative"]["wrong_relation_type"] == 1


def test_correct_relations_all_match():
    result = rel_result([
        p_rel("r1", "p1", "p3", "PREREQUISITE"),
        p_rel("r2", "p1", "p2", "RELATED_TO"),
        p_rel("r3", "p4", "p1", "EXAMPLE_OF"),
    ])
    overall = result["relations"]["overall"]
    assert (overall["tp"], overall["fp"], overall["fn"]) == (3, 0, 0)
    assert overall["precision"] == overall["recall"] == overall["f1"] == 1.0


def test_duplicate_relation_is_false_positive():
    result = rel_result([p_rel("r1", "p1", "p2", "RELATED_TO"), p_rel("r2", "p2", "p1", "RELATED_TO")])
    assert result["relations"]["overall"]["tp"] == 1
    assert result["errors"]["relations"]["false_positive"]["duplicate"] == 1


def test_unmapped_endpoint_is_false_positive():
    ents = ENTS + [p_ent("p9", "不存在的概念")]
    result = score(BASE_GOLD, preds(ents, [p_rel("r1", "p9", "p3", "PREREQUISITE")]))
    overall = result["relations"]["overall"]
    assert (overall["tp"], overall["fp"]) == (0, 1)
    assert result["errors"]["relations"]["false_positive"]["unmapped_endpoint"] == 1


def test_missed_gold_relation_with_unextracted_endpoint():
    result = score(BASE_GOLD, preds([p_ent("p1", "栈")]))
    fn = result["errors"]["relations"]["false_negative"]
    assert fn["endpoint_not_extracted"] == 3


# ---------------------------------------------------------------- 指标与分组


def test_empty_denominators_are_null():
    result = score(gold([]), preds([]))
    overall = result["entities"]["typed"]["overall"]
    assert overall == {"tp": 0, "fp": 0, "fn": 0, "precision": None, "recall": None, "f1": None}
    assert result["relations"]["overall"]["precision"] is None
    assert result["hard_indicators"]["entity_accuracy"]["value"] is None


def test_precision_null_when_no_predictions_but_recall_zero():
    result = score(BASE_GOLD, preds([]))
    overall = result["entities"]["typed"]["overall"]
    assert overall["precision"] is None
    assert overall["recall"] == 0.0
    # README：precision 或 recall 为 null 时 F1 为 null
    assert overall["f1"] is None


def test_f1_zero_when_precision_and_recall_both_zero():
    result = score(BASE_GOLD, preds([p_ent("x1", "完全无关的名字")]))
    overall = result["entities"]["typed"]["overall"]
    assert (overall["precision"], overall["recall"], overall["f1"]) == (0.0, 0.0, 0.0)


def test_metrics_only_count_ai_source_items():
    # README：各指标只统计 source = "ai"；其他来源不参与任何指标，只报告数量
    g = BASE_GOLD["gold"]["entities"][0]
    manual = p_ent("m1", g["name"], g["type"], source="manual")
    result = score(BASE_GOLD, preds([manual], [p_rel("mr1", "m1", "m1", "RELATED_TO", source="manual")]))
    overall = result["entities"]["typed"]["overall"]
    assert (overall["tp"], overall["fp"]) == (0, 0)
    assert result["relations"]["overall"]["fp"] == 0
    assert result["counts"]["non_ai_entities"] == 1
    assert result["counts"]["non_ai_relations"] == 1


def test_rounding_to_four_decimals():
    g = gold([g_ent("g1", "甲"), g_ent("g2", "乙"), g_ent("g3", "丙")])
    result = score(g, preds([p_ent("p1", "甲")]))
    assert result["entities"]["typed"]["overall"]["recall"] == 0.3333
    assert result["entities"]["typed"]["overall"]["f1"] == 0.5


def test_per_type_grouping_includes_empty_types():
    result = score(gold([]), preds([]))
    assert sorted(result["entities"]["typed"]["by_type"]) == ENTITY_TYPES
    assert sorted(result["entities"]["name_level"]["by_type"]) == ENTITY_TYPES
    assert sorted(result["relations"]["by_type"]) == RELATION_TYPES
    for bucket in result["relations"]["by_type"].values():
        assert bucket["precision"] is None and bucket["recall"] is None


# ---------------------------------------------------------------- 硬指标


def test_exactly_20_ai_entities_passes_and_19_fails():
    ok = score(gold([]), preds(many_entities(20)))["hard_indicators"]["entity_count"]
    assert (ok["value"], ok["passed"]) == (20, True)
    short = score(gold([]), preds(many_entities(19)))["hard_indicators"]["entity_count"]
    assert (short["value"], short["passed"], short["gap"]) == (19, False, 1)


def test_entity_count_only_counts_ai_source():
    ents = many_entities(19) + [p_ent("p-m", "教师补充", source="teacher")]
    hi = score(gold([]), preds(ents))["hard_indicators"]["entity_count"]
    assert (hi["value"], hi["passed"]) == (19, False)


def _judged(n_correct, n_total, kind="entities"):
    ids = [f"p-e{i:03d}" for i in range(n_total)]
    verdicts = {i: ("correct" if k < n_correct else "incorrect") for k, i in enumerate(ids)}
    return verdicts


def test_exactly_seven_tenths_passes():
    p = preds(many_entities(10))
    j = judgments(entities=_judged(7, 10), relations={})
    hi = score(gold([]), p, j)["hard_indicators"]["entity_accuracy"]
    assert (hi["correct"], hi["judged"], hi["value"], hi["passed"]) == (7, 10, 0.7, True)


def test_sixty_nine_percent_fails():
    p = preds(many_entities(100))
    j = judgments(entities=_judged(69, 100))
    hi = score(gold([]), p, j)["hard_indicators"]["entity_accuracy"]
    assert (hi["value"], hi["passed"]) == (0.69, False)
    assert hi["gap"] == 0.01


def test_relation_accuracy_computed_separately():
    ents = many_entities(20)
    rels = [p_rel(f"p-r{i}", "p-e000", f"p-e{i + 1:03d}", "RELATED_TO") for i in range(10)]
    j = judgments(entities=_judged(20, 20), relations={f"p-r{i}": ("correct" if i < 6 else "incorrect") for i in range(10)})
    hi = score(gold([]), preds(ents, rels), j)["hard_indicators"]
    assert hi["entity_accuracy"]["passed"] is True
    assert hi["relation_accuracy"]["passed"] is False
    assert hi["verdict"] == "未达标"
    assert hi["passed"] is False


def test_all_three_pass_gives_pass_verdict():
    ents = many_entities(20)
    rels = [p_rel(f"p-r{i}", "p-e000", f"p-e{i + 1:03d}", "RELATED_TO") for i in range(10)]
    j = judgments(entities=_judged(14, 20), relations={f"p-r{i}": ("correct" if i < 7 else "incorrect") for i in range(10)})
    hi = score(gold([]), preds(ents, rels), j)["hard_indicators"]
    assert hi["verdict"] == "达标"
    assert hi["passed"] is True


def test_fake_model_never_passes():
    ents = many_entities(20)
    rels = [p_rel("p-r0", "p-e000", "p-e001", "RELATED_TO")]
    j = judgments(entities=_judged(20, 20), relations={"p-r0": "correct"})
    hi = score(gold([]), preds(ents, rels, is_fake=True), j)["hard_indicators"]
    assert hi["verdict"] == "不可用于判定（假模型）"
    assert hi["passed"] is not True


def test_fake_model_without_judgments_is_still_fake_verdict():
    hi = score(gold([]), preds(many_entities(25), is_fake=True))["hard_indicators"]
    assert hi["verdict"] == "不可用于判定（假模型）"


def test_missing_judgments_is_undetermined():
    hi = score(gold([]), preds(many_entities(25)))["hard_indicators"]
    assert hi["entity_accuracy"]["value"] is None
    assert hi["relation_accuracy"]["value"] is None
    assert hi["entity_accuracy"]["passed"] is None
    assert hi["verdict"] == "未判定"
    assert hi["passed"] is None


def test_entity_count_short_without_judgments_is_already_fail():
    # README：实体数 < 20 即「未达标」，不因尚未人工判定而写「未判定」
    hi = score(gold([]), preds(many_entities(19)))["hard_indicators"]
    assert hi["verdict"] == "未达标"
    assert hi["passed"] is False


def test_sampled_item_without_judgment_is_incomplete():
    # README：抽样项中有任一项缺少判定时写「判定不完整」，不得给出达标结论
    j = judgments(entities=_judged(19, 19))  # 20 个全量检查，只判了 19 个
    rels = [p_rel("p-r0", "p-e000", "p-e001", "RELATED_TO")]
    j["relations"] = {"p-r0": "correct"}
    hi = score(gold([]), preds(many_entities(20), rels), j)["hard_indicators"]
    assert hi["entity_accuracy"]["status"] == "incomplete"
    assert hi["entity_accuracy"]["missing"] == 1
    assert hi["entity_accuracy"]["passed"] is None
    assert hi["verdict"] == "判定不完整"
    assert hi["passed"] is None


def test_accuracy_uses_only_the_fixed_seed_sample():
    # 总体 150 > 100：只统计按 judgments.seed 抽中的 100 项，样本外的判定不计
    p = preds(many_entities(150))
    drawn = [i["id"] for i in ev.sample(p, seed=7)["entities"]["items"]]
    verdicts = {i: "correct" for i in drawn}
    verdicts.update({e["id"]: "incorrect" for e in p["entities"] if e["id"] not in verdicts})
    j = judgments(entities=verdicts)
    j["seed"] = 7
    hi = score(gold([]), p, j)["hard_indicators"]["entity_accuracy"]
    assert (hi["status"], hi["judged"], hi["correct"], hi["passed"]) == ("judged", 100, 100, True)


def test_judgments_without_relation_verdicts_is_undetermined():
    j = judgments(entities=_judged(20, 20))
    hi = score(gold([]), preds(many_entities(20)), j)["hard_indicators"]
    assert hi["relation_accuracy"]["value"] is None
    assert hi["verdict"] == "未判定"


# ---------------------------------------------------------------- 确定性


def test_repeat_runs_are_byte_identical():
    rels = [p_rel("r1", "p1", "p3", "PREREQUISITE"), p_rel("r2", "p3", "p1", "PREREQUISITE")]
    a = ev.dumps(score(copy.deepcopy(BASE_GOLD), preds(ENTS, rels)))
    b = ev.dumps(score(copy.deepcopy(BASE_GOLD), preds(ENTS, rels)))
    assert a == b
    assert a.endswith("\n")
    assert json.loads(a)["relations"]["overall"]["tp"] == 1


def test_cli_score_repeat_output_identical(tmp_path):
    g_path, p_path = tmp_path / "g.json", tmp_path / "p.json"
    g_path.write_text(json.dumps(BASE_GOLD, ensure_ascii=False), encoding="utf-8")
    p_path.write_text(json.dumps(preds(ENTS)), encoding="utf-8")
    outs = []
    for k in range(2):
        out = tmp_path / f"r{k}.json"
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "score", "--gold", str(g_path), "--predictions", str(p_path), "--out", str(out)],
            capture_output=True, text=True,
        )
        assert proc.returncode == 0, proc.stderr
        outs.append(out.read_bytes())
    assert outs[0] == outs[1]


# ---------------------------------------------------------------- 抽样


def test_same_seed_same_sample_different_seed_differs():
    p = preds(many_entities(150))
    a = ev.sample(p, seed=20260926)
    b = ev.sample(p, seed=20260926)
    c = ev.sample(p, seed=1)
    assert a == b
    assert a["entities"]["mode"] == "sampled"
    assert len(a["entities"]["items"]) == 100
    assert [i["id"] for i in a["entities"]["items"]] != [i["id"] for i in c["entities"]["items"]]


def test_sample_independent_of_input_order():
    ents = many_entities(150)
    a = ev.sample(preds(ents), seed=7)
    b = ev.sample(preds(list(reversed(ents))), seed=7)
    assert a == b


def test_population_at_most_100_is_full_check():
    ents = many_entities(100)
    rels = [p_rel("p-r1", "p-e000", "p-e001", "PREREQUISITE")]
    s = ev.sample(preds(ents, rels), seed=20260926)
    assert s["entities"]["mode"] == "full"
    assert s["entities"]["population"] == 100
    assert [i["id"] for i in s["entities"]["items"]] == sorted(e["id"] for e in ents)
    rel_item = s["relations"]["items"][0]
    assert rel_item["from_name"] == "概念0" and rel_item["to_name"] == "概念1"
    assert rel_item["type"] == "PREREQUISITE"


def test_sample_default_seed_and_only_ai_items():
    ents = many_entities(3) + [p_ent("p-t", "教师节点", source="teacher")]
    s = ev.sample(preds(ents))
    assert s["seed"] == 20260926
    assert "p-t" not in [i["id"] for i in s["entities"]["items"]]


def test_cli_sample_runs(tmp_path):
    p_path = tmp_path / "p.json"
    p_path.write_text(json.dumps(preds(many_entities(120))), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "sample", "--predictions", str(p_path), "--seed", "3", "--size", "10"],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert data["seed"] == 3 and len(data["entities"]["items"]) == 10


# ---------------------------------------------------------------- 坏输入


def _bad_cases():
    unknown_ent_type = preds([p_ent("p1", "栈", "lemma")])
    unknown_rel_type = preds(ENTS, [p_rel("r1", "p1", "p2", "DEPENDS_ON")])
    dup_id = preds([p_ent("p1", "栈"), p_ent("p1", "队列")])
    dangling = preds(ENTS, [p_rel("r1", "p1", "p404", "PREREQUISITE")])
    mismatch = preds(ENTS)
    mismatch["dataset_id"] = "other"
    return {
        "unknown entity type": (BASE_GOLD, unknown_ent_type, None),
        "unknown relation type": (BASE_GOLD, unknown_rel_type, None),
        "duplicate id": (BASE_GOLD, dup_id, None),
        "dangling endpoint": (BASE_GOLD, dangling, None),
        "dataset mismatch": (BASE_GOLD, mismatch, None),
        "gold dangling": (gold([g_ent("g1", "栈")], [g_rel("gr", "g1", "g9", "CONTAINS")]), preds([]), None),
        "gold duplicate id": (gold([g_ent("g1", "栈"), g_ent("g1", "队列")]), preds([]), None),
        "judgment unknown id": (BASE_GOLD, preds(ENTS), judgments(entities={"nope": "correct"})),
        "judgment bad value": (BASE_GOLD, preds(ENTS), judgments(entities={"p1": "maybe"})),
        "judgment run mismatch": (BASE_GOLD, preds(ENTS), judgments(run_id="run-2")),
    }


@pytest.mark.parametrize("case", sorted(_bad_cases()))
def test_malformed_input_raises(case):
    g, p, j = _bad_cases()[case]
    with pytest.raises(ev.EvaluationInputError):
        ev.score(copy.deepcopy(g), copy.deepcopy(p), copy.deepcopy(j))


def test_cli_malformed_input_exits_nonzero(tmp_path):
    g_path, p_path = tmp_path / "g.json", tmp_path / "p.json"
    g_path.write_text(json.dumps(BASE_GOLD, ensure_ascii=False), encoding="utf-8")
    p_path.write_text(json.dumps(preds([p_ent("p1", "栈", "lemma")])), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "score", "--gold", str(g_path), "--predictions", str(p_path)],
        capture_output=True, text=True,
    )
    assert proc.returncode != 0
    assert "lemma" in proc.stderr
    assert proc.stdout == ""


def test_cli_invalid_json_exits_nonzero(tmp_path):
    p_path = tmp_path / "p.json"
    p_path.write_text("{not json", encoding="utf-8")
    proc = subprocess.run([sys.executable, str(SCRIPT), "sample", "--predictions", str(p_path)],
                          capture_output=True, text=True)
    assert proc.returncode != 0
    assert "JSON" in proc.stderr


# ---------------------------------------------------------------- 可选：K01 合成夹具


def test_k01_synthetic_fixture_validates_if_present():
    if not SYNTHETIC.exists():
        pytest.skip("K01 夹具 evaluation/fixtures/synthetic.json 尚未合入")
    g = json.loads(SYNTHETIC.read_text(encoding="utf-8"))
    ents = [p_ent(f"p-{e['id']}", e["name"], e["type"]) for e in g["gold"]["entities"]]
    idmap = {e["id"]: f"p-{e['id']}" for e in g["gold"]["entities"]}
    rels = [p_rel(f"p-{r['id']}", idmap[r["from"]], idmap[r["to"]], r["type"]) for r in g["gold"]["relations"]]
    p = preds(ents, rels, is_fake=True)
    p["dataset_id"] = g["dataset_id"]
    result = ev.score(g, p)
    assert result["entities"]["typed"]["overall"]["fn"] == 0
    assert result["relations"]["overall"]["fn"] == 0
    assert result["hard_indicators"]["verdict"] == "不可用于判定（假模型）"
