#!/usr/bin/env python3
"""C04（B-QUALITY-01）：把未经教师改写的 AI 草稿转成 K01 ``predictions.json``，并生成人工判定工作表（只用标准库）。

输入是 ``GET /courses/{cid}/graph`` 原样保存的草稿（``evaluation/raw/l11/*.json``，L11-6 / C03-1 导出，发布与编辑之前）。
转换不改名称、类型与端点；``run_id`` = ``<dataset_id>-<草稿字节 sha256 前 12 位>``，草稿变了 ID 就变。
工作表按 ``evaluation/README.md`` §6.2 的抽样规则（与 ``evaluate_extraction.py sample`` 同一函数）列出待判条目，
附定义与证据章节，判定标准见 §6.3；判定结果写进 ``judgments.json`` 后用 ``evaluate_extraction.py judge-report`` 计算。

用法::

    python evaluation/draft_to_predictions.py --draft evaluation/raw/l11/course1-md-draft.json \\
        --dataset-id contest-course1-ds-ch3-md --model-id deepseek-flash \\
        --prompt-version extract_entities=2 --prompt-version extract_relations=2 \\
        --out evaluation/raw/c04/course1-md-predictions.json --worksheet evaluation/raw/c04/course1-md-worksheet.md
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

_spec = importlib.util.spec_from_file_location("evaluate_extraction", Path(__file__).with_name("evaluate_extraction.py"))
evaluate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(evaluate)


def to_predictions(raw: bytes, *, dataset_id: str, model_id: str, prompt_versions: dict[str, int]) -> dict[str, Any]:
    draft = json.loads(raw)
    entities = []
    for node in draft["nodes"]:
        entity = {"id": node["id"], "name": node["name"], "type": node["type"], "source": node["source"]}
        if node.get("definition"):
            entity["definition"] = node["definition"]
        entities.append(entity)
    relations = []
    for edge in draft["edges"]:
        relation = {"id": edge["id"], "type": edge["type"], "from": edge["from_id"], "to": edge["to_id"],
                    "source": edge["source"]}
        sections = [ref["section_path"] for ref in edge.get("source_refs") or [] if ref.get("section_path")]
        pages = [ref["page"] for ref in edge.get("source_refs") or [] if ref.get("page") is not None]
        if sections:
            relation["section_paths"] = sections
        if pages:
            relation["pages"] = pages
        relations.append(relation)
    predictions = {
        "run_id": f"{dataset_id}-{hashlib.sha256(raw).hexdigest()[:12]}",
        "dataset_id": dataset_id,
        "model": {"id": model_id, "is_fake": False},
        "prompt_versions": dict(prompt_versions),
        "source_draft_course_id": draft.get("course_id"),
        "entities": entities,
        "relations": relations,
    }
    evaluate.validate_predictions(predictions)
    return predictions


def worksheet(predictions: dict[str, Any], *, seed: int = evaluate.DEFAULT_SEED) -> str:
    drawn = evaluate.sample(predictions, seed=seed)
    by_id = {e["id"]: e for e in predictions["entities"]}
    rels = {r["id"]: r for r in predictions["relations"]}

    def mode(part: dict[str, Any]) -> str:
        return "全量检查" if part["mode"] == "full" else f"抽样 {len(part['items'])} 条"

    def cell(text: str) -> str:
        return text.replace("|", "\\|").replace("\n", " ")

    lines = [
        f"# 人工判定工作表：{predictions['dataset_id']}",
        "",
        f"- run_id：`{predictions['run_id']}`；模型：`{predictions['model']['id']}`；提示词版本：{predictions['prompt_versions']}",
        f"- 种子 {seed}；实体总体 {drawn['entities']['population']}（{mode(drawn['entities'])}），"
        f"关系总体 {drawn['relations']['population']}（{mode(drawn['relations'])}）",
        "- 判定标准：`evaluation/README.md` §6.3（实体 E1～E5、关系 R1～R6）；判错写明违反的编号。",
        "- 判定值只用 correct / incorrect；结果写进 judgments.json（`judge` 填判定人；Claude 辅助判定一律以 `claude-assist` 开头）。",
        "",
        "## 实体",
        "",
        "| # | ID | 名称 | 类型 | 定义 | 判定 | 依据 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for n, item in enumerate(drawn["entities"]["items"], 1):
        definition = by_id[item["id"]].get("definition", "")
        lines.append(f"| {n} | `{item['id']}` | {cell(item['name'])} | {item['type']} | {cell(definition)} |  |  |")
    lines += ["", "## 关系", "", "| # | ID | 关系 | 类型 | 证据位置 | 判定 | 依据 |", "| --- | --- | --- | --- | --- | --- | --- |"]
    for n, item in enumerate(drawn["relations"]["items"], 1):
        rel = rels[item["id"]]
        where = "；".join(rel.get("section_paths", []) or [f"第 {p} 页" for p in rel.get("pages", [])])
        lines.append(f"| {n} | `{item['id']}` | {cell(item['from_name'])} → {cell(item['to_name'])} | {item['type']} "
                     f"| {cell(where)} |  |  |")
    return "\n".join(lines) + "\n"


def _prompt_versions(values: list[str]) -> dict[str, int]:
    versions: dict[str, int] = {}
    for value in values:
        name, sep, number = value.partition("=")
        if not sep or not name or not number.isdigit():
            raise SystemExit(f"--prompt-version 须写成 用途=版本号，收到 {value!r}")
        versions[name] = int(number)
    return versions


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AI 草稿 → K01 predictions 与人工判定工作表")
    parser.add_argument("--draft", required=True)
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--prompt-version", action="append", default=[], help="用途=版本号，可重复")
    parser.add_argument("--out", required=True)
    parser.add_argument("--worksheet")
    parser.add_argument("--seed", type=int, default=evaluate.DEFAULT_SEED)
    args = parser.parse_args(argv)
    versions = _prompt_versions(args.prompt_version)
    predictions = to_predictions(Path(args.draft).read_bytes(), dataset_id=args.dataset_id, model_id=args.model_id,
                                 prompt_versions=versions)
    Path(args.out).write_text(json.dumps(predictions, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.worksheet:
        Path(args.worksheet).write_text(worksheet(predictions, seed=args.seed), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
