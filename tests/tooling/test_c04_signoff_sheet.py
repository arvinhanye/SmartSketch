"""C04 签收：用户在工作表副本的「判定」列填 ✓ / ✗，脚本转成 judgments JSON 并算人工硬指标。

- 原工作表与 predictions 不改；副本里只认「判定」「依据」两列，其他列被改动就拒绝。
- 未填、非法标记、判 ✗ 没写依据、判定人为空或以 `claude-assist` 开头：一律拒绝，不写半截结果。
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
signoff = _load("c04_signoff")

DRAFT = {
    "format_version": "1.0", "course_id": "c1", "graph_version": None, "generated_at": "2026-10-03T00:00:00Z",
    "chapters": [], "stats": {},
    "nodes": [
        {"id": "kp_a", "name": "栈", "type": "concept", "definition": "后进先出的线性表。", "source": "ai"},
        {"id": "kp_b", "name": "队列", "type": "concept", "definition": "先进先出的线性表。", "source": "ai"},
        {"id": "kp_c", "name": "ls | grep 示例", "type": "example", "definition": "管道。", "source": "ai"},
    ],
    "edges": [
        {"id": "rel_1", "type": "RELATED_TO", "from_id": "kp_a", "to_id": "kp_b", "source": "ai",
         "source_refs": [{"chunk_id": "k1", "section_path": "第3章 > 3.4"}]},
    ],
}


def _predictions():
    raw = json.dumps(DRAFT, ensure_ascii=False).encode("utf-8")
    return convert.to_predictions(raw, dataset_id="contest-course1-md", model_id="deepseek-flash",
                                  prompt_versions={"extract_entities": 2})


def _fill(sheet: str, marks: dict[str, tuple[str, str]], judge: str = "张三") -> str:
    """把 marks（ID → (判定, 依据)）填进副本的空单元格。"""
    out = []
    for line in sheet.splitlines():
        if line.startswith("- 判定人："):
            line = f"- 判定人：{judge}"
        for item_id, (mark, note) in marks.items():
            if f"| `{item_id}` |" in line and line.endswith("|  |  |"):
                line = line[: -len("|  |  |")] + f"| {mark} | {note} |"
        out.append(line)
    return "\n".join(out) + "\n"


@pytest.fixture
def setup():
    predictions = _predictions()
    original = convert.worksheet(predictions)
    return predictions, original, signoff.user_sheet(original)


ALL_OK = {"kp_a": ("✓", ""), "kp_b": ("✓", ""), "kp_c": ("✗", "E2：把命令当名称"), "rel_1": ("✓", "")}


def test_user_sheet_keeps_every_original_row_and_adds_a_judge_line(setup):
    _, original, sheet = setup
    assert "- 判定人：" in sheet and "- 判定人：" not in original
    rows = [line for line in original.splitlines() if line.startswith("| ") and "`" in line]
    assert rows and all(row in sheet.splitlines() for row in rows)


def test_filled_sheet_converts_to_valid_human_judgments(setup):
    predictions, original, sheet = setup
    result = signoff.to_judgments(_fill(sheet, ALL_OK), original, predictions)
    judgments = result.judgments
    assert judgments["judge"] == "张三" and judgments["run_id"] == predictions["run_id"]
    assert judgments["entities"] == {"kp_a": "correct", "kp_b": "correct", "kp_c": "incorrect"}
    assert judgments["relations"] == {"rel_1": "correct"}
    assert judgments["notes"] == {"kp_c": "E2：把命令当名称"}
    report = signoff.evaluate.judge_report(predictions, judgments)
    assert report["is_human_judgment"] is True
    assert report["hard_indicators"]["entity_accuracy"]["correct"] == 2


def test_mark_variants_are_accepted(setup):
    predictions, original, sheet = setup
    marks = {"kp_a": ("√", ""), "kp_b": ("✔", ""), "kp_c": ("×", "E1"), "rel_1": ("✘", "R5")}
    judgments = signoff.to_judgments(_fill(sheet, marks), original, predictions).judgments
    assert judgments["entities"] == {"kp_a": "correct", "kp_b": "correct", "kp_c": "incorrect"}
    assert judgments["relations"] == {"rel_1": "incorrect"}


def test_unfilled_rows_are_rejected_with_their_numbers(setup):
    predictions, original, sheet = setup
    partial = {k: v for k, v in ALL_OK.items() if k != "kp_b"}
    with pytest.raises(signoff.SignoffError) as error:
        signoff.to_judgments(_fill(sheet, partial), original, predictions)
    assert "未填 1 条" in str(error.value) and "实体 #2" in str(error.value)


@pytest.mark.parametrize("judge", ["", "claude-assist（Opus）", "Claude-Assist 复核"])
def test_judge_must_be_a_person(setup, judge):
    predictions, original, sheet = setup
    with pytest.raises(signoff.SignoffError, match="判定人"):
        signoff.to_judgments(_fill(sheet, ALL_OK, judge=judge), original, predictions)


def test_cross_without_basis_and_unknown_marks_are_rejected(setup):
    predictions, original, sheet = setup
    marks = {**ALL_OK, "kp_c": ("✗", ""), "rel_1": ("对", "")}
    with pytest.raises(signoff.SignoffError) as error:
        signoff.to_judgments(_fill(sheet, marks), original, predictions)
    message = str(error.value)
    assert "实体 #3" in message and "依据" in message
    assert "关系 #1" in message and "对" in message


def test_editing_other_columns_is_rejected(setup):
    predictions, original, sheet = setup
    tampered = _fill(sheet, ALL_OK).replace("| 栈 | concept |", "| 栈 | theorem |")
    with pytest.raises(signoff.SignoffError, match="实体 #1.*改动"):
        signoff.to_judgments(tampered, original, predictions)


def test_cross_without_rule_code_only_warns(setup):
    predictions, original, sheet = setup
    marks = {**ALL_OK, "kp_c": ("✗", "名称不对")}
    result = signoff.to_judgments(_fill(sheet, marks), original, predictions)
    assert result.judgments["entities"]["kp_c"] == "incorrect"
    assert any("实体 #3" in warning for warning in result.warnings)


def test_cli_init_then_convert_writes_json_and_report_without_touching_originals(tmp_path, capsys):
    predictions = _predictions()
    stem = "course1-pdf-h2-thinking-off"
    (tmp_path / f"{stem}-predictions.json").write_text(json.dumps(predictions, ensure_ascii=False), encoding="utf-8")
    (tmp_path / f"{stem}-worksheet.md").write_text(convert.worksheet(predictions), encoding="utf-8")
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}

    assert signoff.main(["init", "--dir", str(tmp_path), "--course", "course1"]) == 0
    sheet_path = tmp_path / f"{stem}-worksheet-user.md"
    sheet_path.write_text(_fill(sheet_path.read_text(encoding="utf-8"), ALL_OK), encoding="utf-8")
    assert signoff.main(["init", "--dir", str(tmp_path), "--course", "course1"]) == 0   # 已存在：不覆盖
    assert "✓" in sheet_path.read_text(encoding="utf-8")

    assert signoff.main(["convert", "--dir", str(tmp_path), "--course", "course1"]) == 0
    judgments = json.loads((tmp_path / f"{stem}-judgments-user.json").read_text(encoding="utf-8"))
    report = json.loads((tmp_path / f"{stem}-report-user.json").read_text(encoding="utf-8"))
    assert judgments["judge"] == "张三" and report["is_human_judgment"] is True
    assert "实体 2/3" in capsys.readouterr().out
    assert all((tmp_path / name).read_bytes() == data for name, data in before.items())


def test_cli_convert_fails_and_writes_nothing_when_incomplete(tmp_path):
    predictions = _predictions()
    stem = "course1-pdf-h2-thinking-off"
    (tmp_path / f"{stem}-predictions.json").write_text(json.dumps(predictions, ensure_ascii=False), encoding="utf-8")
    (tmp_path / f"{stem}-worksheet.md").write_text(convert.worksheet(predictions), encoding="utf-8")
    signoff.main(["init", "--dir", str(tmp_path), "--course", "course1"])
    assert signoff.main(["convert", "--dir", str(tmp_path), "--course", "course1"]) == 1
    assert not (tmp_path / f"{stem}-judgments-user.json").exists()
    assert not (tmp_path / f"{stem}-report-user.json").exists()
