"""C04（B-QUALITY-01）：把未经教师改写的 AI 草稿转成 K01 predictions，并在没有金标的比赛资料上只按人工判定算准确率。

- 草稿原样来自 `GET /courses/{cid}/graph`（`evaluation/raw/l11/*.json`）；转换不改名称、类型与端点，`run_id` 由草稿字节摘要决定。
- `judge-report` 不需要金标：只算赛题硬指标（实体数、实体与关系人工准确率，全量 ≤100 时全量检查）。
- 判定人以 `claude-assist` 开头的是 Claude 辅助判定：报告必须标为「非人工验收」，不能当作用户签收的结论。
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"evaluation/{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


convert = _load("draft_to_predictions")
evaluate = _load("evaluate_extraction")

DRAFT = {
    "format_version": "1.0", "course_id": "c1", "graph_version": None, "generated_at": "2026-10-03T00:00:00Z",
    "chapters": [], "stats": {},
    "nodes": [
        {"id": "kp_b", "name": "队列", "type": "concept", "definition": "先进先出的线性表。", "source": "ai"},
        {"id": "kp_a", "name": "栈", "type": "concept", "definition": "后进先出的线性表。", "source": "ai"},
        {"id": "kp_m", "name": "教师补充", "type": "example", "definition": "", "source": "manual"},
    ],
    "edges": [
        {"id": "rel_1", "type": "RELATED_TO", "from_id": "kp_a", "to_id": "kp_b", "source": "ai",
         "source_refs": [{"chunk_id": "k1", "section_path": "第3章 > 3.4 比较 > 第1段"}]},
    ],
}


def _predictions(**overrides):
    raw = json.dumps(DRAFT, ensure_ascii=False).encode("utf-8")
    return convert.to_predictions(raw, dataset_id="contest-course1-md", model_id="deepseek-flash",
                                  prompt_versions={"extract_entities": 2, "extract_relations": 2}, **overrides)


def test_conversion_keeps_names_types_endpoints_and_is_valid_k01():
    predictions = _predictions()
    evaluate.validate_predictions(predictions)
    assert predictions["model"] == {"id": "deepseek-flash", "is_fake": False}
    assert [e["id"] for e in predictions["entities"]] == ["kp_b", "kp_a", "kp_m"]
    assert predictions["entities"][1] == {"id": "kp_a", "name": "栈", "type": "concept", "source": "ai",
                                          "definition": "后进先出的线性表。"}
    assert predictions["relations"] == [{"id": "rel_1", "type": "RELATED_TO", "from": "kp_a", "to": "kp_b",
                                         "source": "ai", "section_paths": ["第3章 > 3.4 比较 > 第1段"]}]


def test_run_id_is_derived_from_the_draft_bytes():
    first, second = _predictions(), _predictions()
    assert first["run_id"] == second["run_id"] and first["run_id"].startswith("contest-course1-md-")
    raw = json.dumps({**DRAFT, "generated_at": "x"}, ensure_ascii=False).encode("utf-8")
    other = convert.to_predictions(raw, dataset_id="contest-course1-md", model_id="m", prompt_versions={})
    assert other["run_id"] != first["run_id"]


def test_worksheet_lists_every_ai_item_for_full_check():
    sheet = convert.worksheet(_predictions())
    assert "全量检查" in sheet and "kp_a" in sheet and "kp_b" in sheet and "rel_1" in sheet
    assert "栈 → 队列" in sheet and "第3章 > 3.4 比较 > 第1段" in sheet
    assert "kp_m" not in sheet                                   # 非 AI 条目不参与判定


def _judgments(judge: str, verdicts: dict | None = None):
    predictions = _predictions()
    entities = {"kp_a": "correct", "kp_b": "correct"}
    return predictions, {"run_id": predictions["run_id"], "judge": judge, "seed": 20260926,
                         "entities": entities, "relations": verdicts if verdicts is not None else {"rel_1": "correct"},
                         "notes": {}}


def test_judge_report_without_gold_and_human_judge():
    predictions, judgments = _judgments("ArvinHan")
    report = evaluate.judge_report(predictions, judgments)
    hard = report["hard_indicators"]
    assert hard["entity_accuracy"]["status"] == "judged" and hard["entity_accuracy"]["value"] == 1.0
    assert hard["relation_accuracy"]["sampled"] == 1
    assert report["is_human_judgment"] is True
    assert hard["entity_count"]["value"] == 2               # 只数 AI 条目（未达 20，硬指标照实失败）
    assert hard["verdict"] == evaluate.VERDICT_FAIL


def test_claude_assist_judgments_are_never_reported_as_human_signoff():
    predictions, judgments = _judgments("claude-assist（Opus）")
    report = evaluate.judge_report(predictions, judgments)
    assert report["is_human_judgment"] is False
    assert "辅助判定" in report["note"] and "非人工验收" in report["note"]


def test_judge_report_distinguishes_not_judged_from_incomplete():
    predictions, judgments = _judgments("ArvinHan", verdicts={})
    report = evaluate.judge_report(predictions, judgments)
    assert report["hard_indicators"]["relation_accuracy"]["status"] == "not_judged"     # 一条都没判
    judgments["entities"] = {"kp_a": "correct"}                                       # 漏判 kp_b
    report = evaluate.judge_report(predictions, judgments)
    assert report["hard_indicators"]["entity_accuracy"]["status"] == "incomplete"


def test_cli_converts_a_draft_file(tmp_path, capsys):
    draft = tmp_path / "draft.json"
    draft.write_text(json.dumps(DRAFT, ensure_ascii=False), encoding="utf-8")
    out = tmp_path / "predictions.json"
    sheet = tmp_path / "worksheet.md"
    code = convert.main(["--draft", str(draft), "--dataset-id", "contest-course1-md", "--model-id", "deepseek-flash",
                         "--prompt-version", "extract_entities=2", "--prompt-version", "extract_relations=2",
                         "--out", str(out), "--worksheet", str(sheet)])
    assert code == 0
    assert json.loads(out.read_text(encoding="utf-8"))["prompt_versions"] == {"extract_entities": 2, "extract_relations": 2}
    assert "全量检查" in sheet.read_text(encoding="utf-8")
    with pytest.raises(SystemExit):
        convert.main(["--draft", str(draft), "--dataset-id", "d", "--model-id", "m", "--prompt-version", "bad",
                      "--out", str(out)])
