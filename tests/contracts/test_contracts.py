#!/usr/bin/env python3
"""契约门禁的负向测试。

对应 codex 审查 R02～R05 的验收条件：坏输入必须让门禁非 0 退出，正常契约通过。
门禁本身沉默地放行过一次（缺 PyYAML 时 exit 0），所以门禁需要自己的测试。

用法：
    python3 tests/contracts/test_contracts.py     # 独立运行，无需 pytest
    pytest tests/contracts/test_contracts.py      # 装了 pytest 也能直接跑
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SHIM = Path(__file__).resolve().parent / "_shim"
GATE = "scripts/check_contracts.py"

# 门禁读到的全部文件：构造临时工作区时要一并复制
WORKSPACE_FILES = [
    "scripts/check_contracts.py",
    "src/contracts/api.v1.yaml",
    "src/contracts/events.v1.md",
    "src/contracts/errors.v1.md",
    "src/contracts/README.md",
    "src/contracts/toolchain.txt",
    "docs/architecture.md",
    "specs/course-knowledge-graph.md",
    "specs/grounded-qa.md",
    "specs/learning-path.md",
    "specs/teacher-review-publish.md",
    "AGENTS.md",
]


def _run(cwd: Path, argv: list[str], env_extra: dict[str, str] | None = None) -> int:
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run([sys.executable, *argv], cwd=cwd, env=env,
                          capture_output=True, text=True)
    return proc.returncode


def _workspace() -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="contract-gate-"))
    for rel in WORKSPACE_FILES:
        dest = tmp / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / rel, dest)
    return tmp


def _gate_with(mutate_yaml=None, mutate_text=None) -> int:
    """在临时工作区上施加一处破坏，返回门禁退出码。"""
    import yaml
    tmp = _workspace()
    try:
        spec_path = tmp / "src/contracts/api.v1.yaml"
        if mutate_yaml is not None:
            spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
            mutate_yaml(spec)
            spec_path.write_text(yaml.safe_dump(spec, allow_unicode=True, sort_keys=False),
                                 encoding="utf-8")
        if mutate_text is not None:
            mutate_text(tmp)
        return _run(tmp, [GATE])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ── R02：缺依赖 / 坏 YAML / 坏 $ref ──────────────────────────────

def test_clean_contract_passes():
    assert _run(REPO, [GATE]) == 0, "正常契约应当通过"


def test_unmutated_workspace_passes():
    # 测试的测试：若临时工作区本身就构造得不对，下面所有「必须失败」的用例都会
    # 假阳性通过。先证明未被破坏的工作区是绿的。
    assert _gate_with() == 0, "未施加破坏的临时工作区应当通过——否则负向用例无意义"


def test_missing_dependency_fails():
    assert _run(REPO, [GATE], {"PYTHONPATH": str(SHIM), "BLOCK_MODULES": "yaml"}) != 0, \
        "缺 PyYAML 必须失败——这正是 R02 报告的静默放行"


def test_missing_dependency_scaffold_mode_is_marked():
    rc = _run(REPO, [GATE, "--allow-scaffold"],
              {"PYTHONPATH": str(SHIM), "BLOCK_MODULES": "yaml"})
    assert rc == 0, "显式降级模式可以退出 0"


def test_broken_yaml_fails():
    def break_it(tmp: Path):
        p = tmp / "src/contracts/api.v1.yaml"
        p.write_text(p.read_text(encoding="utf-8") + "\n  : : bad yaml : :\n", encoding="utf-8")
    assert _gate_with(mutate_text=break_it) != 0, "坏 YAML 必须失败"


def test_broken_ref_fails():
    def break_it(spec):
        spec["components"]["schemas"]["Citation"]["properties"]["chunk_id"] = \
            {"$ref": "#/components/schemas/DoesNotExist"}
    assert _gate_with(mutate_yaml=break_it) != 0, "无法解析的 $ref 必须失败"


# ── R01：路径前缀 / 枚举 ────────────────────────────────────────

def test_unversioned_path_fails():
    def break_it(spec):
        spec["paths"]["/api/courses"] = spec["paths"]["/api/v1/courses"]
    assert _gate_with(mutate_yaml=break_it) != 0, "缺 /api/v1 前缀必须失败"


def test_relation_alias_fails():
    def break_it(spec):
        spec["components"]["schemas"]["RelationType"]["enum"].append("RELATED")
    assert _gate_with(mutate_yaml=break_it) != 0, "关系类型别名必须失败（ADR-008）"


def test_task_stage_missing_persisting_fails():
    def break_it(spec):
        spec["components"]["schemas"]["TaskStage"]["enum"].remove("persisting")
    assert _gate_with(mutate_yaml=break_it) != 0, "状态机缺 persisting 必须失败"


def test_domain_state_as_error_code_fails():
    def break_it(spec):
        spec["components"]["schemas"]["ErrorCode"]["enum"].append("NOT_COVERED")
    assert _gate_with(mutate_yaml=break_it) != 0, "领域状态混进错误码必须失败"


# ── R03：来源引用的结构约束 ─────────────────────────────────────

def test_answered_without_min_citations_fails():
    def break_it(spec):
        spec["components"]["schemas"]["ChatAnswered"]["properties"]["citations"].pop("minItems")
    assert _gate_with(mutate_yaml=break_it) != 0, "answered 不要求引用必须失败"


def test_citation_without_locator_constraint_fails():
    def break_it(spec):
        spec["components"]["schemas"]["Citation"].pop("anyOf")
    assert _gate_with(mutate_yaml=break_it) != 0, "引用不强制可定位必须失败"


def test_nullable_page_fails():
    def break_it(spec):
        spec["components"]["schemas"]["SourceRef"]["properties"]["page"] = \
            {"type": ["integer", "null"]}
    assert _gate_with(mutate_yaml=break_it) != 0, "page 可为 null 必须失败"


def test_not_covered_without_reason_fails():
    def break_it(spec):
        spec["components"]["schemas"]["ChatNotCovered"]["required"].remove("reason")
    assert _gate_with(mutate_yaml=break_it) != 0, "not_covered 不给机读原因必须失败"


# ── R04：问答事件载荷 ───────────────────────────────────────────

def test_loose_chat_event_fails():
    def break_it(spec):
        spec["components"]["schemas"]["ChatEvent"] = {
            "type": "object",
            "properties": {"delta": {"type": "string"}},
        }
    assert _gate_with(mutate_yaml=break_it) != 0, "宽松 ChatEvent 必须失败（{} 会通过）"


def test_done_event_without_final_fails():
    def break_it(spec):
        spec["components"]["schemas"]["ChatDoneEvent"]["required"] = ["event"]
    assert _gate_with(mutate_yaml=break_it) != 0, "done 不带最终正文必须失败"


def test_naming_alias_in_contract_doc_fails():
    def break_it(tmp: Path):
        p = tmp / "docs/architecture.md"
        p.write_text(p.read_text(encoding="utf-8") + "\n- 关系类型 RELATED 表示相关。\n",
                     encoding="utf-8")
    assert _gate_with(mutate_text=break_it) != 0, "契约文档出现同义别名必须失败（ADR-008）"


# ── R05：状态机跨文件一致 ───────────────────────────────────────

def test_spec_missing_stage_fails():
    def break_it(tmp: Path):
        p = tmp / "specs/course-knowledge-graph.md"
        p.write_text(p.read_text(encoding="utf-8").replace(" → persisting", ""), encoding="utf-8")
    assert _gate_with(mutate_text=break_it) != 0, "规格漏掉 persisting 必须失败（R05）"


def test_architecture_missing_cancelled_fails():
    def break_it(tmp: Path):
        p = tmp / "docs/architecture.md"
        p.write_text(p.read_text(encoding="utf-8").replace("cancelled", "已取消"), encoding="utf-8")
    assert _gate_with(mutate_text=break_it) != 0, "架构漏掉 cancelled 必须失败（R05）"


# ── 实例级正负例：schema 真的拦得住报告里的两个例子吗 ──────────────

def _instance_cases():
    return [
        ("ChatResponse", {"status": "answered", "answer": "结论", "citations": []}, False,
         "R03 报告原例：answered 但没有引用"),
        ("ChatResponse", {"status": "answered", "answer": "栈是后进先出[1]。", "citations": [
            {"index": 1, "chunk_id": "c_77", "document_id": "d_03", "text": "栈是…"}]}, False,
         "R03 报告原例：引用无页码也无章节"),
        ("ChatResponse", {"status": "answered", "answer": "栈是后进先出[1]。", "citations": [
            {"index": 1, "chunk_id": "c_77", "document_id": "d_03", "page": 52,
             "text": "栈是…"}]}, True, "带页码的真实引用"),
        ("ChatResponse", {"status": "answered", "answer": "栈是后进先出[1]。", "citations": [
            {"index": 1, "chunk_id": "c_77", "document_id": "d_03",
             "section_path": "第3章 > 3.1 栈", "text": "栈是…"}]}, True, "只带章节路径"),
        ("ChatResponse", {"status": "not_covered", "answer": "课程资料未覆盖该问题。",
                          "citations": [], "reason": "no_retrieval_hit"}, True,
         "未覆盖终态带机读原因"),
        ("ChatResponse", {"status": "not_covered", "answer": "未覆盖", "citations": []}, False,
         "未覆盖但没给机读原因"),
        ("ChatEvent", {}, False, "R04 报告原例：空事件 {}"),
        ("ChatEvent", {"event": "done", "status": "not_covered", "answer": "未覆盖",
                       "citations": []}, False, "R04 报告原例：done 用文档里并不存在的 answer 字段"),
        ("ChatEvent", {"event": "done", "final": {
            "status": "not_covered", "answer": "生成的回答无法与课程资料对应，已撤回。",
            "citations": [], "reason": "all_citations_invalidated"}}, True,
         "引用全部失效时降级为未覆盖终态"),
        ("ChatEvent", {"event": "delta", "delta": ""}, False, "空 delta"),
        ("ChatEvent", {"event": "meta", "status": "answered", "retrieved": 6}, True, "meta"),
    ]


def test_instance_level_cases():
    import yaml
    from jsonschema import Draft202012Validator
    spec = yaml.safe_load((REPO / "src/contracts/api.v1.yaml").read_text(encoding="utf-8"))
    schemas = spec["components"]["schemas"]
    bad = []
    for name, doc, should_pass, label in _instance_cases():
        validator = Draft202012Validator(
            {"$ref": f"#/components/schemas/{name}", "components": {"schemas": schemas}})
        accepted = not list(validator.iter_errors(doc))
        if accepted != should_pass:
            bad.append(f"{label}：实际{'接受' if accepted else '拒绝'}，"
                       f"期望{'接受' if should_pass else '拒绝'}")
    assert not bad, "实例级用例不符预期：\n  " + "\n  ".join(bad)


def main() -> int:
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ✓ {name}")
        except AssertionError as exc:
            failed += 1
            print(f"  ✗ {name}: {exc}")
        except Exception as exc:                     # noqa: BLE001
            failed += 1
            print(f"  ✗ {name}: 未预期的异常 {exc!r}")
    print(f"\n{len(tests) - failed}/{len(tests)} 通过")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
