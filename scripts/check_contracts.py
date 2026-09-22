#!/usr/bin/env python3
"""契约校验：结构、$ref 完整性与 ADR-004 不变量。

由 scripts/verify.sh 调用。openapi-spec-validator 可选：缺失时跳过形式校验，
其余检查仍然执行，因此本脚本不依赖重量级环境即可给出有效信号。
"""
from __future__ import annotations

import sys
from pathlib import Path

SPEC = Path("src/contracts/api.v1.yaml")

# ADR-004 与 ADR-003 固化下来的契约不变量
RELATION_TYPES = ["CONTAINS", "PREREQUISITE", "RELATED_TO", "EXAMPLE_OF"]
REQUIRED_STAGES = ["queued", "parsing", "extracting", "merging",
                   "persisting", "awaiting_review", "completed", "failed", "cancelled"]
# 领域状态，不得混入错误码（errors.v1.md「不是错误的两个状态」）
NON_ERROR_STATES = ["NOT_COVERED", "TASK_FAILED"]


def fail(msg: str) -> None:
    print(f"Contract check failed: {msg}", file=sys.stderr)
    sys.exit(1)


def collect_refs(node, out):
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str):
                out.append(value)
            else:
                collect_refs(value, out)
    elif isinstance(node, list):
        for item in node:
            collect_refs(item, out)


def resolve(spec, ref: str) -> bool:
    if not ref.startswith("#/"):
        return False
    node = spec
    for part in ref[2:].split("/"):
        if not isinstance(node, dict) or part not in node:
            return False
        node = node[part]
    return True


def main() -> None:
    try:
        import yaml
    except ImportError:
        print("SKIP contract checks: PyYAML not installed (pip3 install pyyaml)")
        return

    if not SPEC.exists():
        fail(f"{SPEC} is missing")

    try:
        spec = yaml.safe_load(SPEC.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        fail(f"{SPEC} is not valid YAML: {exc}")

    refs: list[str] = []
    collect_refs(spec, refs)
    broken = [r for r in refs if not resolve(spec, r)]
    if broken:
        fail(f"unresolved $ref in {SPEC}: {sorted(set(broken))}")

    schemas = spec.get("components", {}).get("schemas", {})

    if schemas.get("RelationType", {}).get("enum") != RELATION_TYPES:
        fail(f"RelationType must be exactly {RELATION_TYPES} (ADR-004)")

    stages = schemas.get("TaskStage", {}).get("enum", [])
    missing = [s for s in REQUIRED_STAGES if s not in stages]
    if missing:
        fail(f"TaskStage misses {missing} (ADR-004)")

    error_codes = schemas.get("ErrorCode", {}).get("enum", [])
    leaked = [s for s in NON_ERROR_STATES if s in error_codes]
    if leaked:
        fail(f"{leaked} are domain states, not error codes — see errors.v1.md")
    if "COURSE_FORBIDDEN" not in error_codes:
        fail("ErrorCode misses COURSE_FORBIDDEN (course isolation)")

    if "not_covered" not in schemas.get("ChatStatus", {}).get("enum", []):
        fail("ChatStatus misses not_covered (ADR-003)")

    try:
        from openapi_spec_validator import validate
    except ImportError:
        print(f"OK contract checks: {len(spec['paths'])} paths, {len(schemas)} schemas, "
              f"{len(refs)} refs resolved "
              "(formal OpenAPI validation skipped: pip3 install openapi-spec-validator)")
        return

    try:
        validate(spec)
    except Exception as exc:  # noqa: BLE001 - validator raises several types
        fail(f"OpenAPI validation error: {exc}")

    print(f"OK contract checks: OpenAPI {spec['openapi']} valid, "
          f"{len(spec['paths'])} paths, {len(schemas)} schemas, {len(refs)} refs resolved")


if __name__ == "__main__":
    main()
