"""E01: versioned prompt loader — lookup by purpose + version, strict rendering, template digest."""

import hashlib
import re
from pathlib import Path

import pytest

from app.services.ai.prompts import (
    PromptLibrary,
    PromptNotFoundError,
    PromptTemplateError,
    PromptVariableError,
    PromptVersionError,
    RenderedPrompt,
)

REPO_PROMPTS = Path(__file__).parents[2] / "prompts"

# 8 类清单：S2 §6.7 表 6.8，经分支 prompts/MANIFEST.md 照录，atomic-task-plan 的 E/J/O 任务沿用同名文件。
EIGHT_PURPOSES = {
    "extract_entities",
    "extract_entities_gleaning",
    "extract_relations",
    "judge_duplicate",
    "summarize_definition",
    "rewrite_query",
    "answer_with_context",
    "gen_study_material",
}
NOT_YET_CREATED = {"gen_study_material"}  # 待 O01 准入，由 O06 建文件


def repo_template_files() -> list[Path]:
    # 分支骨架 TEMPLATE.yaml 若随 A10 批 3 导入，它只是字段说明，不是可装载的提示词。
    return sorted(p for p in REPO_PROMPTS.glob("*.yaml") if p.name != "TEMPLATE.yaml")


def write(root: Path, name: str, text: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{name}.yaml"
    path.write_text(text, encoding="utf-8")
    return path


GOOD = """\
# 注释行允许出现在字段之前
id: demo
version: 2
purpose: 演示用途
evaluation: evaluation/evaluate_qa.py
variables:
  - question
  - context
template: |
  资料：
  {{context}}

  问题：{{question}}
  JSON 示例：{"answer": "…", "refs": [{"n": 1}]}
"""


@pytest.fixture
def lib(tmp_path: Path) -> PromptLibrary:
    write(tmp_path, "demo", GOOD)
    return PromptLibrary(tmp_path)


# ---------- 成功路径 ----------


def test_render_substitutes_every_placeholder_and_returns_digest(lib: PromptLibrary):
    rendered = lib.render("demo", 2, {"question": "什么是栈？", "context": "[1] 栈是后进先出的线性表。"})

    assert isinstance(rendered, RenderedPrompt)
    assert rendered.purpose == "demo"
    assert rendered.version == 2
    assert rendered.text == (
        "资料：\n[1] 栈是后进先出的线性表。\n\n问题：什么是栈？\n"
        'JSON 示例：{"answer": "…", "refs": [{"n": 1}]}\n'
    )
    body = lib.get("demo", 2).template
    assert rendered.template_sha256 == hashlib.sha256(body.encode("utf-8")).hexdigest()
    assert re.fullmatch(r"[0-9a-f]{64}", rendered.template_sha256)


def test_template_metadata_is_exposed(lib: PromptLibrary):
    template = lib.get("demo", 2)

    assert template.purpose == "demo"
    assert template.version == 2
    assert template.variables == ("question", "context")
    assert template.evaluation == "evaluation/evaluate_qa.py"
    assert template.template.startswith("资料：\n{{context}}\n")
    assert template.template.endswith("}]}\n")


def test_digest_depends_only_on_template_body(tmp_path: Path):
    write(tmp_path / "a", "demo", GOOD)
    write(tmp_path / "b", "demo", GOOD.replace("演示用途", "别的说明").replace("# 注释行允许出现在字段之前\n", ""))
    write(tmp_path / "c", "demo", GOOD.replace("问题：", "提问："))

    digest = {k: PromptLibrary(tmp_path / k).get("demo", 2).sha256 for k in "abc"}
    assert digest["a"] == digest["b"]
    assert digest["a"] != digest["c"]


def test_crlf_file_has_same_digest_as_lf(tmp_path: Path):
    (tmp_path / "lf").mkdir()
    (tmp_path / "crlf").mkdir()
    (tmp_path / "lf" / "demo.yaml").write_bytes(GOOD.encode("utf-8"))
    (tmp_path / "crlf" / "demo.yaml").write_bytes(GOOD.replace("\n", "\r\n").encode("utf-8"))

    assert PromptLibrary(tmp_path / "lf").get("demo", 2).sha256 == PromptLibrary(tmp_path / "crlf").get("demo", 2).sha256


def test_rendered_repr_does_not_leak_prompt_text(lib: PromptLibrary):
    rendered = lib.render("demo", 2, {"question": "机密问题", "context": "课程原文"})

    assert "机密问题" not in repr(rendered)
    assert "课程原文" not in repr(rendered)
    assert rendered.template_sha256 in repr(rendered)


# ---------- 边界 ----------


def test_values_with_braces_and_placeholders_are_inserted_verbatim(lib: PromptLibrary):
    tricky = "{{context}} {question} {0} }}{{ ${x} %s"
    rendered = lib.render("demo", 2, {"question": tricky, "context": "{\"a\": {\"b\": 1}}"})

    assert f"问题：{tricky}\n" in rendered.text
    assert '{"a": {"b": 1}}' in rendered.text
    assert rendered.text.count("{{context}}") == 1  # 值里的占位符不被二次展开


def test_non_ascii_empty_and_multiline_values(lib: PromptLibrary):
    rendered = lib.render("demo", 2, {"question": "", "context": "第一行\n第二行 ∑ 😀 \\n"})

    assert "问题：\n" in rendered.text
    assert "第一行\n第二行 ∑ 😀 \\n\n" in rendered.text


def test_repeated_placeholder_and_no_variable_template(tmp_path: Path):
    write(tmp_path, "twice", GOOD.replace("id: demo", "id: twice").replace("问题：{{question}}", "{{question}}/{{question}}"))
    write(
        tmp_path,
        "plain",
        "id: plain\nversion: 1\npurpose: 无变量\nevaluation: evaluation/evaluate_qa.py\nvariables: []\ntemplate: |\n  固定文本\n",
    )
    lib = PromptLibrary(tmp_path)

    assert "甲/甲\n" in lib.render("twice", 2, {"question": "甲", "context": ""}).text
    assert lib.render("plain", 1, {}).text == "固定文本\n"


def test_block_literal_keeps_inner_indent_and_clips_trailing_blank_lines(tmp_path: Path):
    write(
        tmp_path,
        "indent",
        "id: indent\nversion: 1\npurpose: 缩进\nevaluation: evaluation/evaluate_qa.py\nvariables: []\n"
        "template: |\n  第一行\n    缩进四格\n\n  末行 # 不是注释\n\n\n",
    )

    assert PromptLibrary(tmp_path).get("indent", 1).template == "第一行\n  缩进四格\n\n末行 # 不是注释\n"


def test_templates_are_cached_per_library(lib: PromptLibrary, tmp_path: Path):
    first = lib.get("demo", 2)
    (tmp_path / "demo.yaml").write_text(GOOD.replace("问题：", "改了："), encoding="utf-8")

    assert lib.get("demo", 2) is first


# ---------- 失败路径：变量 ----------


def test_missing_variable_is_an_error_naming_the_variable(lib: PromptLibrary):
    with pytest.raises(PromptVariableError, match="missing.*context"):
        lib.render("demo", 2, {"question": "什么是栈？"})


def test_unexpected_variable_is_an_error(lib: PromptLibrary):
    with pytest.raises(PromptVariableError, match="unexpected.*history"):
        lib.render("demo", 2, {"question": "q", "context": "c", "history": "h"})


@pytest.mark.parametrize("value", [None, 1, b"bytes", ["x"]])
def test_non_string_value_is_an_error(lib: PromptLibrary, value: object):
    with pytest.raises(PromptVariableError, match="context"):
        lib.render("demo", 2, {"question": "q", "context": value})  # type: ignore[dict-item]


def test_variable_error_does_not_echo_values(lib: PromptLibrary):
    with pytest.raises(PromptVariableError) as info:
        lib.render("demo", 2, {"question": "学生的私密问题", "context": "c", "extra": "课程原文"})

    assert "学生的私密问题" not in str(info.value)
    assert "课程原文" not in str(info.value)


# ---------- 失败路径：用途与版本 ----------


def test_unknown_purpose_is_an_error(lib: PromptLibrary):
    with pytest.raises(PromptNotFoundError, match="nope"):
        lib.get("nope", 1)


@pytest.mark.parametrize("purpose", ["../demo", "Demo", "demo.yaml", "", "de mo", "demo/x"])
def test_invalid_purpose_names_are_rejected_without_touching_paths(lib: PromptLibrary, purpose: str):
    with pytest.raises(PromptNotFoundError):
        lib.get(purpose, 2)


@pytest.mark.parametrize("version", [1, 3, 0, -2])
def test_unknown_version_is_an_error_listing_the_available_one(lib: PromptLibrary, version: int):
    with pytest.raises(PromptVersionError, match=r"available: 2"):
        lib.get("demo", version)


@pytest.mark.parametrize("version", ["2", 2.0, True, None])
def test_version_must_be_an_int(lib: PromptLibrary, version: object):
    with pytest.raises(PromptVersionError):
        lib.get("demo", version)  # type: ignore[arg-type]


def test_render_checks_version_before_variables(lib: PromptLibrary):
    with pytest.raises(PromptVersionError):
        lib.render("demo", 1, {})


# ---------- 失败路径：模板文件 ----------


def _variant(old: str, new: str) -> str:
    assert old in GOOD
    return GOOD.replace(old, new)


@pytest.mark.parametrize(
    ("text", "message"),
    [
        (_variant("id: demo", "id: other"), "id"),
        (_variant("version: 2", "version: 0"), "version"),
        (_variant("version: 2", "version: 1.0"), "version"),
        (_variant("version: 2", "version: v2"), "version"),
        (_variant("evaluation: evaluation/evaluate_qa.py", "evals: evaluation/evaluate_qa.py"), "evals"),
        (_variant("evaluation: evaluation/evaluate_qa.py", "evaluation: evals/qa.py"), "evaluation"),
        (_variant("evaluation: evaluation/evaluate_qa.py\n", ""), "evaluation"),
        (_variant("purpose: 演示用途\n", ""), "purpose"),
        (_variant("purpose: 演示用途", "purpose: 演示用途\npurpose: 重复"), "duplicate"),
        (_variant("purpose: 演示用途", "purpose: 演示用途\nmodel: LLM_EXTRACTION_MODEL"), "unknown"),
        (_variant("purpose: 演示用途", "purpose: 带: 冒号"), "purpose"),
        (_variant("purpose: 演示用途", "purpose: \"引号\""), "purpose"),
        (_variant("  - context\n", ""), "context"),
        (_variant("  - context\n", "  - context\n  - unused\n"), "unused"),
        (_variant("  - context\n", "  - context\n  - context\n"), "duplicate"),
        (_variant("  - context\n", "  - Context\n"), "variable"),
        (_variant("{{context}}", "{{ context }}"), "placeholder"),
        (_variant("{{context}}", "{{context}"), "placeholder"),
        (_variant("template: |", "template: >"), "template"),
        (_variant("  资料：\n", "资料：\n"), "indent"),
        (_variant("  资料：\n", "    资料：\n"), "indent"),
        (_variant("  资料：\n", "  资料：\n\t制表符\n"), "indent"),
        (GOOD + "extra: 1\n", "indent"),
        (GOOD.split("template: |")[0] + "template: |\n\n", "empty"),
        (GOOD.split("template: |")[0], "template"),
        (_variant("version: 2", "version 2"), "line"),
    ],
)
def test_malformed_template_file_is_rejected(tmp_path: Path, text: str, message: str):
    write(tmp_path, "demo", text)

    with pytest.raises(PromptTemplateError, match=message):
        PromptLibrary(tmp_path).get("demo", 2)


def test_template_error_names_the_file(tmp_path: Path):
    write(tmp_path, "demo", _variant("version: 2", "version: x"))

    with pytest.raises(PromptTemplateError, match=r"demo\.yaml"):
        PromptLibrary(tmp_path).get("demo", 2)


def test_non_utf8_file_is_rejected(tmp_path: Path):
    tmp_path.joinpath("demo.yaml").write_bytes(GOOD.encode("gbk"))

    with pytest.raises(PromptTemplateError, match="UTF-8"):
        PromptLibrary(tmp_path).get("demo", 2)


def test_missing_root_directory_is_reported_as_not_found(tmp_path: Path):
    with pytest.raises(PromptNotFoundError):
        PromptLibrary(tmp_path / "absent").get("demo", 2)


# ---------- 仓库资产：8 类清单与 MANIFEST ----------


def _manifest_rows() -> dict[str, list[str]]:
    rows: dict[str, list[str]] = {}
    for line in (REPO_PROMPTS / "MANIFEST.md").read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 7 and re.fullmatch(r"`[a-z_]+`", cells[0]):
            rows[cells[0].strip("`")] = cells
    return rows


def test_manifest_lists_exactly_the_eight_purposes():
    assert set(_manifest_rows()) == EIGHT_PURPOSES


def test_manifest_header_uses_evaluation_not_evals():
    text = (REPO_PROMPTS / "MANIFEST.md").read_text(encoding="utf-8")
    header = next(line for line in text.splitlines() if line.startswith("| 用途"))

    assert "evaluation" in header
    assert "evals" not in header


def test_every_template_file_is_in_manifest_and_loads_with_default_root():
    files = {p.stem for p in repo_template_files()}
    assert files == EIGHT_PURPOSES - NOT_YET_CREATED

    lib = PromptLibrary()  # 默认根目录即仓库 prompts/
    rows = _manifest_rows()
    for purpose in sorted(files):
        _, version, variables, evaluation, digest, *_ = rows[purpose]
        template = lib.get(purpose, int(version))
        assert template.sha256 == digest.strip("`"), f"{purpose}: MANIFEST 摘要与文件不符，改模板须升版本并更新摘要"
        assert tuple(re.findall(r"`([a-z_]+)`", variables)) == template.variables, purpose
        assert evaluation.strip("`") == template.evaluation, purpose
        assert template.evaluation in {"evaluation/evaluate_extraction.py", "evaluation/evaluate_qa.py"}


def test_not_yet_created_purpose_is_unknown_to_the_loader():
    for purpose in NOT_YET_CREATED:
        with pytest.raises(PromptNotFoundError):
            PromptLibrary().get(purpose, 1)


def test_repo_templates_never_use_evals_spelling_and_hold_no_secrets():
    for path in repo_template_files():
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"\bevals\b", text), path.name
        assert not re.search(r"(?i)(api[_-]?key|sk-[a-z0-9]{8,}|bearer\s)", text), path.name


def test_answer_prompt_carries_sentinel_and_citation_contract():
    template = PromptLibrary().get("answer_with_context", 1)

    assert "<<INSUFFICIENT_EVIDENCE>>" in template.template  # ADR-015 决定 3
    assert "[n]" in template.template  # ADR-015 决定 2
    assert "history" not in template.variables  # ADR-015 决定 6：生成提示不含历史


def test_course_material_prompts_declare_injection_guard():
    lib = PromptLibrary()
    for path in repo_template_files():
        template = lib.get(path.stem, int(_manifest_rows()[path.stem][1]))
        assert "只当作数据" in template.template, path.name
