#!/usr/bin/env python3
"""从契约真源 api.v1.yaml 生成 openapi.json 与独立 JSON Schema。

由 scripts/gen-contracts.sh 调用，不单独使用。生成必须**可重复**：
同一份 YAML 生成两次字节一致（ADR-004 第 4 条）。因此这里只做确定性转换——
保持 YAML 的键序、固定缩进、固定换行，不引入时间戳或随机名。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SPEC = Path("src/contracts/api.v1.yaml")

# 需要脱离 OpenAPI 单独校验的格式：SSE 事件载荷与可落盘的图谱交换文件（ADR-004）
STANDALONE = ["TaskEvent", "ChatEvent", "GraphExchange"]

JSON_SCHEMA_DRAFT = "https://json-schema.org/draft/2020-12/schema"


def dump(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def rewrite_refs(node):
    """#/components/schemas/X → #/$defs/X，使 schema 脱离 OpenAPI 也能解析。"""
    if isinstance(node, dict):
        return {
            k: (v.replace("#/components/schemas/", "#/$defs/")
                if k == "$ref" and isinstance(v, str) else rewrite_refs(v))
            for k, v in node.items()
        }
    if isinstance(node, list):
        return [rewrite_refs(item) for item in node]
    return node


def collect_deps(schemas: dict, root: str) -> list[str]:
    """root 传递依赖到的全部 schema 名，按名字排序保证输出稳定。"""
    seen: set[str] = set()
    stack = [root]
    while stack:
        name = stack.pop()
        if name in seen or name not in schemas:
            continue
        seen.add(name)
        refs: list[str] = []
        _collect_ref_names(schemas[name], refs)
        stack.extend(refs)
    return sorted(seen)


def _collect_ref_names(node, out: list[str]) -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "$ref" and isinstance(v, str) and v.startswith("#/components/schemas/"):
                out.append(v.rsplit("/", 1)[-1])
            else:
                _collect_ref_names(v, out)
    elif isinstance(node, list):
        for item in node:
            _collect_ref_names(item, out)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("用法：gen_contracts.py <openapi|schemas> <输出目录>", file=sys.stderr)
        return 2
    stage, outdir = argv[0], Path(argv[1])

    import yaml
    spec = yaml.safe_load(SPEC.read_text(encoding="utf-8"))

    if stage == "openapi":
        dump(outdir / "openapi.json", spec)
        print(f"  · openapi.json（{len(spec['paths'])} 条路径）")
        return 0

    if stage == "schemas":
        schemas = spec["components"]["schemas"]
        missing = [n for n in STANDALONE if n not in schemas]
        if missing:
            print(f"真源缺少需要独立导出的 schema：{missing}", file=sys.stderr)
            return 1
        for name in STANDALONE:
            deps = collect_deps(schemas, name)
            dump(outdir / "schemas" / f"{name}.schema.json", {
                "$schema": JSON_SCHEMA_DRAFT,
                "$id": f"https://smartsketch.local/contracts/v1/{name}.schema.json",
                "title": name,
                "$ref": f"#/$defs/{name}",
                "$defs": {d: rewrite_refs(schemas[d]) for d in deps},
            })
            print(f"  · schemas/{name}.schema.json（含 {len(deps)} 个依赖定义）")
        return 0

    print(f"未知阶段：{stage}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
