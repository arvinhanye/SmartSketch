#!/usr/bin/env python3
"""C04 人工签收：在工作表副本的「判定」列填 ✓ / ✗，转成 judgments JSON 并算人工硬指标。

原工作表与 predictions 不改。``init`` 从原工作表复制出 ``*-worksheet-user.md``（多一行「判定人」）；用户在副本里
逐行填「判定」（✓ 对、✗ 错）与「依据」（判 ✗ 写违反的编号，如 E3、R5）；``convert`` 校验后写
``*-judgments-user.json`` 与 ``*-report-user.json``。

以下情况一律拒绝、不写任何结果：有行未填；标记不是 ✓ / ✗；判 ✗ 没写依据；判定人为空或以 ``claude-assist`` 开头；
副本里「判定」「依据」以外的列被改动，或行被增删。

用法::

    python evaluation/c04_signoff.py init               # 生成两课副本（已存在则跳过，不覆盖）
    python evaluation/c04_signoff.py convert            # 校验副本 → judgments JSON + 报告
    python evaluation/c04_signoff.py convert --course course2
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any

_spec = importlib.util.spec_from_file_location("evaluate_extraction", Path(__file__).with_name("evaluate_extraction.py"))
evaluate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(evaluate)

DEFAULT_DIR = Path(__file__).resolve().parent / "raw" / "c04-signoff"
COURSES = {"course1": "course1-pdf-h2-thinking-off", "course2": "course2-pdf-h2-thinking-off"}
JUDGE_PREFIX = "- 判定人："
HINT = ("- 填法：每行「判定」填 ✓（对）或 ✗（错）；判 ✗ 时「依据」写违反的编号（如 E3、R5）。"
        "只改「判定」「依据」两列，单元格里不要用 `|`。填完运行 `python evaluation/c04_signoff.py convert`。")
MARKS = {"✓": "correct", "✔": "correct", "√": "correct", "✗": "incorrect", "✘": "incorrect", "×": "incorrect"}
SECTIONS = {"## 实体": "entities", "## 关系": "relations"}
LABELS = {"entities": "实体", "relations": "关系"}
RULE_CODE = re.compile(r"[ER][1-6]")
ROW = re.compile(r"^\|\s*(\d+)\s*\|\s*`([^`]+)`\s*\|")


class SignoffError(Exception):
    """副本不能转成判定：消息逐条列出原因。"""


class Result:
    """转换结果；不用 dataclass，因为本模块常按文件路径加载、不在 sys.modules 中。"""

    def __init__(self, judgments: dict[str, Any], warnings: list[str]):
        self.judgments, self.warnings = judgments, warnings


def user_sheet(original: str) -> str:
    """在原工作表的说明区末尾加「判定人」与填法两行，表格逐行保持原样。"""
    lines = original.splitlines()
    at = next(i for i, line in enumerate(lines) if line.startswith("## "))
    while at > 0 and not lines[at - 1].strip():
        at -= 1
    return "\n".join(lines[:at] + [HINT, JUDGE_PREFIX] + lines[at:]) + "\n"


def _cells(line: str) -> list[str]:
    """按未转义的 | 切分表格行（名称里的 ``\\|`` 保留在单元格内）。"""
    return [cell.strip() for cell in re.split(r"(?<!\\)\|", line.strip())[1:-1]]


def _rows(sheet: str) -> dict[str, dict[int, tuple[str, list[str]]]]:
    """{kind: {行号: (ID, 全部单元格)}}。"""
    rows: dict[str, dict[int, tuple[str, list[str]]]] = {"entities": {}, "relations": {}}
    kind = None
    for line in sheet.splitlines():
        if line.startswith("## "):
            kind = SECTIONS.get(line.strip())
            continue
        match = ROW.match(line)
        if kind and match:
            rows[kind][int(match.group(1))] = (match.group(2), _cells(line))
    return rows


def _judge(sheet: str) -> str:
    for line in sheet.splitlines():
        if line.startswith(JUDGE_PREFIX):
            return line[len(JUDGE_PREFIX):].strip()
    return ""


def to_judgments(sheet: str, original: str, predictions: dict[str, Any],
                 seed: int = evaluate.DEFAULT_SEED) -> Result:
    errors: list[str] = []
    warnings: list[str] = []
    judge = _judge(sheet)
    if not judge:
        errors.append("判定人为空：在「- 判定人：」后填你的名字")
    elif judge.lower().startswith(evaluate.ASSIST_JUDGE_PREFIX):
        errors.append(f"判定人不能以 {evaluate.ASSIST_JUDGE_PREFIX} 开头（那是 Claude 辅助判定的标记）")

    filled, expected = _rows(sheet), _rows(original)
    judgments: dict[str, Any] = {"run_id": predictions["run_id"], "judge": judge, "seed": seed,
                                 "entities": {}, "relations": {}, "notes": {}}
    unfilled: list[str] = []
    for kind, label in LABELS.items():
        want, got = expected[kind], filled[kind]
        if set(want) != set(got):
            missing = sorted(set(want) - set(got))
            extra = sorted(set(got) - set(want))
            errors.append(f"{label}行与原工作表不一致：缺 {missing or '无'}，多 {extra or '无'}")
        for n in sorted(set(want) & set(got)):
            item_id, cells = got[n]
            if want[n][0] != item_id or cells[:5] != want[n][1][:5]:
                errors.append(f"{label} #{n}：「判定」「依据」以外的列被改动")
                continue
            mark, note = (cells[5:7] + ["", ""])[:2]
            if not mark:
                unfilled.append(f"{label} #{n}")
                continue
            verdict = MARKS.get(mark)
            if verdict is None:
                errors.append(f"{label} #{n}：判定「{mark}」不认识，只能填 ✓ 或 ✗")
                continue
            if verdict == "incorrect" and not note:
                errors.append(f"{label} #{n}：判 ✗ 必须在「依据」写违反的编号（如 E3、R5）")
                continue
            if verdict == "incorrect" and not RULE_CODE.search(note):
                warnings.append(f"{label} #{n}：依据里没有 E1～E5 / R1～R6 编号，建议补上")
            judgments[kind][item_id] = verdict
            if note:
                judgments["notes"][item_id] = note
    if unfilled:
        shown = "、".join(unfilled[:10]) + ("……" if len(unfilled) > 10 else "")
        errors.append(f"未填 {len(unfilled)} 条：{shown}")
    if errors:
        raise SignoffError("\n".join(errors))
    evaluate.validate_judgments(judgments, predictions)
    return Result(judgments, warnings)


def _paths(directory: Path, stem: str) -> dict[str, Path]:
    return {name: directory / f"{stem}-{name}" for name in (
        "predictions.json", "worksheet.md", "worksheet-user.md", "judgments-user.json", "report-user.json")}


def _init(paths: dict[str, Path]) -> None:
    target = paths["worksheet-user.md"]
    if target.exists():
        print(f"已存在，保留不动：{target}")
        return
    target.write_text(user_sheet(paths["worksheet.md"].read_text(encoding="utf-8")), encoding="utf-8")
    print(f"已生成：{target}")


def _convert(paths: dict[str, Path], course: str) -> bool:
    sheet = paths["worksheet-user.md"]
    if not sheet.exists():
        print(f"{course}：没有副本 {sheet.name}，先运行 init", file=sys.stderr)
        return False
    predictions = json.loads(paths["predictions.json"].read_text(encoding="utf-8"))
    try:
        result = to_judgments(sheet.read_text(encoding="utf-8"),
                              paths["worksheet.md"].read_text(encoding="utf-8"), predictions)
    except SignoffError as error:
        print(f"{course}：不能转换，未写任何文件。\n{error}", file=sys.stderr)
        return False
    report = evaluate.judge_report(predictions, result.judgments)
    paths["judgments-user.json"].write_text(evaluate.dumps(result.judgments), encoding="utf-8")
    paths["report-user.json"].write_text(evaluate.dumps(report), encoding="utf-8")
    hard = report["hard_indicators"]
    ent, rel = hard["entity_accuracy"], hard["relation_accuracy"]
    for warning in result.warnings:
        print(f"{course}：提示：{warning}")
    print(f"{course}：判定人 {report['judge']}（人工判定：{'是' if report['is_human_judgment'] else '否'}）；"
          f"实体 {ent['correct']}/{ent['judged']}（{ent['value']:.2%}），关系 {rel['correct']}/{rel['judged']}"
          f"（{rel['value']:.2%}），阈值 70%；结论：{hard['verdict']}")
    print(f"  已写 {paths['judgments-user.json'].name}、{paths['report-user.json'].name}")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="C04 人工签收：工作表 ✓ / ✗ → judgments JSON + 报告")
    parser.add_argument("command", choices=("init", "convert"))
    parser.add_argument("--course", choices=sorted(COURSES), action="append",
                        help="只处理指定课程，可重复；缺省两门都处理")
    parser.add_argument("--dir", default=str(DEFAULT_DIR), help="签收目录（缺省 evaluation/raw/c04-signoff）")
    args = parser.parse_args(argv)
    directory = Path(args.dir)
    ok = True
    for course in args.course or sorted(COURSES):
        paths = _paths(directory, COURSES[course])
        if args.command == "init":
            _init(paths)
        else:
            ok = _convert(paths, course) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
