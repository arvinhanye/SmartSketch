#!/usr/bin/env python3
"""契约静态校验：结构、$ref 完整性与契约不变量。

由 scripts/verify/contracts.sh 调用。

**缺依赖时失败，不跳过。** 这是 codex 审查 R02 的修复：原先缺 PyYAML 就
`return`，verify.sh 随后打印「passed」并 exit 0——没解析任何 YAML，也没校验
引用与枚举，损坏的已冻结契约仍能越过门禁。本机三个 python3 里有两个没有
PyYAML，这不是边角情形。

仅在显式传入 `--allow-scaffold` 时降级，且必须打印未完成验收标记。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

SPEC = Path("src/contracts/api.v1.yaml")
EVENTS = Path("src/contracts/events.v1.md")
ARCH = Path("docs/architecture.md")
KG_SPEC = Path("specs/course-knowledge-graph.md")
TOOLCHAIN = Path("src/contracts/toolchain.txt")

# ── 契约不变量（来自 ADR，改这里前先改 ADR）────────────────────────
RELATION_TYPES = ["CONTAINS", "PREREQUISITE", "RELATED_TO", "EXAMPLE_OF"]   # ADR-008
TASK_STAGES = ["queued", "parsing", "extracting", "merging",                # ADR-005/006
               "persisting", "awaiting_review", "completed", "failed", "cancelled"]
TERMINAL_STAGES = {"completed", "failed", "cancelled"}
NON_ERROR_STATES = ["NOT_COVERED", "TASK_FAILED"]   # 领域状态，不得混进 ErrorCode
API_PREFIX = "/api/v1"                              # ADR-004 第 8 条
UNVERSIONED_PATHS = {"/health"}                     # 运维端点，不带版本前缀

# ADR-008 命名基线：契约文档里不得出现这些同义别名。
# 只扫描契约类文档——ADR 与任务板要能引用旧名来说明「改成什么」，扫进去会误报。
NAMING_DRIFT_DOCS = [
    Path("AGENTS.md"),
    Path("docs/architecture.md"),
    Path("specs/course-knowledge-graph.md"),
    Path("specs/learning-path.md"),
    Path("specs/teacher-review-publish.md"),
    Path("specs/grounded-qa.md"),           # A09 合入后加回（ADR-016 修订 1）
    Path("src/contracts/api.v1.yaml"),
    Path("src/contracts/events.v1.md"),
    Path("src/contracts/errors.v1.md"),
    Path("src/contracts/README.md"),
]
BANNED_ALIASES = [
    (r"\bRELATED\b", "用 RELATED_TO"),
    (r"\bAPPLIES_TO\b", "用 EXAMPLE_OF"),
    (r"\bSourceChunk\b", "用 Chunk"),
]

REQUIRED_MODULES = [
    ("yaml", "pyyaml", "解析 api.v1.yaml"),
    ("openapi_spec_validator", "openapi-spec-validator", "OpenAPI 3.1 形式校验"),
    ("jsonschema", "jsonschema", "运行契约正负例"),
]

failures: list[str] = []


def fail(msg: str) -> None:
    failures.append(msg)


def require(cond: bool, msg: str) -> None:
    if not cond:
        fail(msg)


def collect_refs(node, out: list[str]) -> None:
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


def check_missing_deps() -> list[tuple[str, str, str]]:
    missing = []
    for module, pkg, why in REQUIRED_MODULES:
        try:
            __import__(module)
        except ImportError:
            missing.append((module, pkg, why))
    return missing


# ── 各项不变量 ────────────────────────────────────────────────────

def check_paths(spec) -> None:
    """ADR-004 第 8 条：REST 路径前缀统一为 /api/v1。"""
    for path in spec.get("paths", {}):
        if path in UNVERSIONED_PATHS:
            continue
        require(path.startswith(API_PREFIX + "/"),
                f"路径 {path} 缺少 {API_PREFIX} 前缀（ADR-004 第 8 条）")


def check_enums(schemas) -> None:
    require(schemas.get("RelationType", {}).get("enum") == RELATION_TYPES,
            f"RelationType 必须恰好是 {RELATION_TYPES}（ADR-008）")

    stages = schemas.get("TaskStage", {}).get("enum", [])
    require(stages == TASK_STAGES,
            f"TaskStage 必须恰好是 {TASK_STAGES}（ADR-005/ADR-006），实际 {stages}")

    error_codes = schemas.get("ErrorCode", {}).get("enum", [])
    leaked = [s for s in NON_ERROR_STATES if s in error_codes]
    require(not leaked, f"{leaked} 是领域状态不是错误码——见 errors.v1.md")
    require("COURSE_FORBIDDEN" in error_codes, "ErrorCode 缺 COURSE_FORBIDDEN（课程隔离）")
    require("not_covered" in schemas.get("ChatStatus", {}).get("enum", []),
            "ChatStatus 缺 not_covered（ADR-003）")


def _locator_anyof_ok(schema: dict) -> bool:
    """页码或章节至少有一个：anyOf: [{required:[page]},{required:[section_path]}]。"""
    branches = schema.get("anyOf")
    if not isinstance(branches, list):
        return False
    required_sets = {tuple(b.get("required", [])) for b in branches if isinstance(b, dict)}
    return {("page",), ("section_path",)} <= required_sets


def _no_nullable_locator(name: str, schema: dict) -> None:
    for field in ("page", "section_path"):
        spec_field = schema.get("properties", {}).get(field, {})
        ftype = spec_field.get("type")
        require(not (isinstance(ftype, list) and "null" in ftype),
                f"{name}.{field} 不得接受 null——可定位是硬约束（ADR-003，审查 R03）")


def check_citation_constraints(schemas) -> None:
    """R03：来源要求必须是结构约束，不能只写在 description 里。"""
    for name in ("SourceRef", "Citation"):
        schema = schemas.get(name)
        if not isinstance(schema, dict):
            fail(f"缺少 schema {name}")
            continue
        require(_locator_anyof_ok(schema),
                f"{name} 必须用 anyOf 要求 page 或 section_path 至少给一个（ADR-003，审查 R03）")
        require(schema.get("properties", {}).get("page", {}).get("minimum") == 1,
                f"{name}.page 必须 minimum: 1（页码从 1 起，0 不是定位）")
        require(schema.get("properties", {}).get("section_path", {}).get("minLength") == 1,
                f"{name}.section_path 必须 minLength: 1（空串不是定位）")
        _no_nullable_locator(name, schema)

    answered = schemas.get("ChatAnswered", {})
    require(answered.get("properties", {}).get("citations", {}).get("minItems", 0) >= 1,
            "ChatAnswered.citations 必须 minItems ≥ 1——"
            "否则 {\"status\":\"answered\",\"citations\":[]} 是合格响应（ADR-003，审查 R03）")

    not_covered = schemas.get("ChatNotCovered", {})
    require(not_covered.get("properties", {}).get("citations", {}).get("maxItems") == 0,
            "ChatNotCovered.citations 必须 maxItems: 0")
    require("reason" in not_covered.get("required", []),
            "ChatNotCovered 必须要求 reason——AGENTS.md §4 要求可机读的未覆盖原因")

    chat_response = schemas.get("ChatResponse", {})
    require("oneOf" in chat_response and chat_response.get("discriminator", {}).get("propertyName") == "status",
            "ChatResponse 必须按 status 分支（oneOf + discriminator），不能是一个宽松对象")


def check_chat_events(schemas) -> None:
    """R04：每种问答事件独立载荷，required 非空，done 携带最终正文。"""
    chat_event = schemas.get("ChatEvent", {})
    branches = chat_event.get("oneOf")
    require(isinstance(branches, list) and len(branches) >= 4,
            "ChatEvent 必须是按事件类型分支的 oneOf（审查 R04）")
    require(chat_event.get("discriminator", {}).get("propertyName") == "event",
            "ChatEvent 必须用 discriminator: event 区分事件类型")

    for name in ("ChatMetaEvent", "ChatDeltaEvent", "ChatDoneEvent", "ChatErrorEvent"):
        schema = schemas.get(name)
        if not isinstance(schema, dict):
            fail(f"缺少 schema {name}（审查 R04）")
            continue
        required = schema.get("required", [])
        require(bool(required), f"{name}.required 不得为空——空载荷 {{}} 必须被拒绝（审查 R04）")
        require("event" in required, f"{name} 必须要求 event 字段，事件要自描述")

    require("final" in schemas.get("ChatDoneEvent", {}).get("required", []),
            "ChatDoneEvent 必须要求 final——最终正文/引用/状态由它统一替换（审查 R04）")
    require("answer" not in schemas.get("ChatDoneEvent", {}).get("properties", {}),
            "ChatDoneEvent 不应有裸 answer 字段；最终正文在 final 里（审查 R04）")


def check_naming_drift() -> None:
    """ADR-008：契约文档不得引入同义别名。"""
    import re
    for path in NAMING_DRIFT_DOCS:
        if not path.exists():
            fail(f"命名漂移扫描缺少文件：{path}")
            continue
        text = path.read_text(encoding="utf-8")
        for pattern, hint in BANNED_ALIASES:
            for match in re.finditer(pattern, text):
                line = text.count("\n", 0, match.start()) + 1
                line_text = text.splitlines()[line - 1]
                if path == Path("docs/architecture.md") and "S2 图 6.3" in line_text and "不得使用" in line_text:
                    continue  # 仅豁免现有架构表中对 S2 旧别名的明确禁止说明
                fail(f"命名漂移（ADR-008）：{path}:{line} 出现 '{match.group()}'，{hint}")


def check_state_machine_consistency(schemas) -> None:
    """R05：状态机在契约、架构、规格、时序文档里必须一致。"""
    docs = {
        "src/contracts/events.v1.md": EVENTS,
        "docs/architecture.md": ARCH,
        "specs/course-knowledge-graph.md": KG_SPEC,
    }
    for label, path in docs.items():
        if not path.exists():
            fail(f"缺少文件：{label}")
            continue
        text = path.read_text(encoding="utf-8")
        missing = [s for s in TASK_STAGES if s not in text]
        require(not missing, f"{label} 的状态机缺 {missing}（审查 R05：规格与架构曾各写一份）")

    # 终态集合必须在时序文档里写明
    if EVENTS.exists():
        text = EVENTS.read_text(encoding="utf-8")
        require("终态集合" in text or "终态：" in text,
                "events.v1.md 必须写明终态集合，否则各方各自推断")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-scaffold", action="store_true",
        help="骨架模式：缺依赖时降级为部分校验并打印未完成验收标记，而不是失败")
    args = parser.parse_args(argv)

    missing = check_missing_deps()
    if missing:
        lines = [f"  - {pkg}（{why}）" for _, pkg, why in missing]
        pkgs = " ".join(pkg for _, pkg, _ in missing)
        if not args.allow_scaffold:
            print("FAIL contracts: 契约校验缺少依赖，门禁失败：", file=sys.stderr)
            print("\n".join(lines), file=sys.stderr)
            print(f"  安装：pip3 install {pkgs}", file=sys.stderr)
            print(f"  版本锁见 {TOOLCHAIN}", file=sys.stderr)
            print("  仅骨架阶段可用 --allow-scaffold 降级（会打印未完成验收标记）。", file=sys.stderr)
            return 1
        print("SKIP contracts: INCOMPLETE 契约校验未执行：缺依赖 " + pkgs)
        print("  本次结果不构成契约验收。安装依赖后重跑，去掉 --allow-scaffold。")
        return 0

    import yaml
    from openapi_spec_validator import validate

    if not SPEC.exists():
        print(f"FAIL contracts: 契约校验失败：{SPEC} 不存在", file=sys.stderr)
        return 1

    try:
        spec = yaml.safe_load(SPEC.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        print(f"FAIL contracts: 契约校验失败：{SPEC} 不是合法 YAML：{exc}", file=sys.stderr)
        return 1
    if (not isinstance(spec, dict)
            or not isinstance(spec.get("components"), dict)
            or not isinstance(spec.get("paths"), dict)):
        print(f"FAIL contracts: 契约校验失败：{SPEC} 的 paths 与 components 必须是对象", file=sys.stderr)
        return 1

    schemas = spec.get("components", {}).get("schemas", {})
    if not isinstance(schemas, dict) or any(not isinstance(item, dict) for item in schemas.values()):
        print(f"FAIL contracts: 契约校验失败：{SPEC} 的 components.schemas 必须是对象映射", file=sys.stderr)
        return 1

    refs: list[str] = []
    try:
        collect_refs(spec, refs)
        broken = sorted({r for r in refs if not resolve(spec, r)})
        if broken:
            fail(f"无法解析的 $ref：{broken}")

        check_paths(spec)
        check_enums(schemas)
        check_citation_constraints(schemas)
        check_chat_events(schemas)
        check_state_machine_consistency(schemas)
        check_naming_drift()
    except Exception as exc:  # noqa: BLE001 - malformed nested YAML must fail closed
        fail(f"契约结构校验异常：{type(exc).__name__}: {exc}")

    try:
        validate(spec)
    except Exception as exc:                      # noqa: BLE001 - validator 抛多种类型
        fail(f"OpenAPI 形式校验不通过：{exc}")

    if failures:
        print(f"FAIL contracts: 契约校验失败（{len(failures)} 项）：", file=sys.stderr)
        for item in failures:
            print(f"  ✗ {item}", file=sys.stderr)
        return 1

    print(f"PASS contracts: 契约校验通过：OpenAPI {spec['openapi']}，"
          f"{len(spec['paths'])} 条路径 / {len(schemas)} 个 schema / {len(refs)} 处 $ref")
    print(f"  ✓ 不变量：关系类型 4 类、状态机 {len(TASK_STAGES)} 态（终态 {len(TERMINAL_STAGES)}）、"
          "来源可定位、问答事件分类型载荷")
    print(f"  ✓ 命名基线：{len(NAMING_DRIFT_DOCS)} 份契约文档无同义别名（ADR-008）")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
