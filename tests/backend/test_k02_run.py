"""K02 本机真实模型抽取脚本（``evaluation/run_live_extraction.py``）的离线测试。

脚本在执行者本机用真实模型把基准章节抽取成 predictions.json，交 ``evaluate_extraction.py`` 计分。
本文件只用 E02 fake 客户端（含脚本化步骤），**不联网**。覆盖：输出通过 ``validate_predictions`` 且
``score`` 可对金标运行；fake 模式 ``model.is_fake`` 为真；跨块同名实体被简化融合合并；关系只引用已输出
的实体 ID；单块失败被记录且运行继续；预算拒绝即停止且不写 predictions；live 模式缺密钥拒绝运行；
密钥不出现在输出、日志与终端里。

``evaluation/`` 不是包，按文件路径导入被测模块（与 ``test_k02.py`` 一致）。
"""

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from app.services.ai.client import ModelInvalidRequestError
from app.services.ai.fake import BAD_JSON_TEXT, FakeModelClient
from app.services.fusion.normalize import normalize_name

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "evaluation" / "run_live_extraction.py"
EVALUATOR = REPO / "evaluation" / "evaluate_extraction.py"
SYNTHETIC = REPO / "evaluation" / "fixtures" / "synthetic.json"

SECRET = "sk-test-DO-NOT-LEAK-7f3a9c"

FAKE_ENV = {"LLM_MODE": "fake"}


def _import(name: str, path: Path):
    if not path.exists():
        pytest.fail(f"{path.relative_to(REPO)} 不存在")
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def run_mod():
    return _import("run_live_extraction", SCRIPT)


@pytest.fixture(scope="module")
def ev():
    return _import("evaluate_extraction_for_run", EVALUATOR)


@pytest.fixture(scope="module")
def gold():
    return json.loads(SYNTHETIC.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def fake_run(run_mod, gold):
    """fake 模式在真实夹具上跑一遍（模块内共享，只读）。"""
    return run_mod.run(copy.deepcopy(gold), environ=dict(FAKE_ENV))


def _run_main(run_mod, tmp_path, environ, *, model_client=None, extra=()):
    out = tmp_path / "predictions.json"
    log = tmp_path / "run.json"
    argv = ["--gold", str(SYNTHETIC), "--out", str(out), "--run-log", str(log), *extra]
    code = run_mod.main(argv, environ=environ, model_client=model_client)
    return code, out, log


# ---------------------------------------------------------------- 输出格式与计分


def test_output_validates_and_scores(run_mod, ev, gold, fake_run):
    preds = fake_run.predictions
    ev.validate_predictions(preds)
    assert preds["dataset_id"] == gold["dataset_id"]
    assert preds["entities"] and preds["relations"]
    assert all(item["source"] == "ai" for item in preds["entities"] + preds["relations"])
    assert preds["prompt_versions"]["extract_entities"] == 2
    assert preds["prompt_versions"]["extract_relations"] == 2
    report = ev.score(gold, preds)
    assert report["hard_indicators"]["verdict"] == ev.VERDICT_FAKE
    assert report["counts"]["predicted_entities"] == len(preds["entities"])


def test_fake_mode_marks_is_fake(fake_run):
    model = fake_run.predictions["model"]
    assert model["is_fake"] is True
    assert isinstance(model["id"], str) and model["id"]
    assert fake_run.run_log["model"]["is_fake"] is True


def test_output_records_simplified_fusion(fake_run):
    assert fake_run.predictions["fusion"]["mode"] == "simplified"
    assert "E12" in fake_run.run_log["fusion"]["note"]
    assert fake_run.run_log["chunk_count"] == 16


def test_main_writes_files_and_prints_next_steps(run_mod, ev, tmp_path, capsys):
    code, out, log = _run_main(run_mod, tmp_path, dict(FAKE_ENV))
    assert code == 0
    preds = json.loads(out.read_text(encoding="utf-8"))
    ev.validate_predictions(preds)
    run_log = json.loads(log.read_text(encoding="utf-8"))
    for key in ("started_at", "finished_at", "chunk_count", "chunk_failures", "section_failures",
                "dropped", "model_calls", "fusion"):
        assert key in run_log
    printed = capsys.readouterr().out
    assert "evaluate_extraction.py sample" in printed
    assert "evaluate_extraction.py score" in printed
    assert str(out) in printed


# ---------------------------------------------------------------- 简化融合与关系


def test_duplicate_names_across_chunks_are_merged(fake_run):
    ents = fake_run.predictions["entities"]
    keys = [normalize_name(e["name"]).key for e in ents]
    assert len(keys) == len(set(keys))
    # fake 应答对「3.2 栈」下的每个块都给出「栈」，合并后只剩一个
    assert keys.count(normalize_name("栈").key) == 1
    assert fake_run.run_log["fusion"]["merged"] > 0


def test_merge_keeps_first_type(run_mod, gold):
    first = {"entities": [{"name": "栈", "type": "concept", "definition": "d", "evidence": "栈"}]}
    later = {"entities": [{"name": " 栈 ", "type": "method", "definition": "d", "evidence": "栈"}]}
    client = FakeModelClient()
    client.script(json.dumps(first, ensure_ascii=False), purpose="extract_entities")
    client.script(*[json.dumps(later, ensure_ascii=False)] * 15, purpose="extract_entities")
    client.script(*['{"relations": []}'] * 40, purpose="extract_relations")
    outcome = run_mod.run(copy.deepcopy(gold), environ=dict(FAKE_ENV), model_client=client)
    ents = outcome.predictions["entities"]
    assert [(e["name"], e["type"]) for e in ents] == [("栈", "concept")]


def test_relations_reference_only_emitted_entities(fake_run):
    preds = fake_run.predictions
    ids = {e["id"] for e in preds["entities"]}
    seen = set()
    for rel in preds["relations"]:
        assert rel["from"] in ids and rel["to"] in ids
        assert rel["from"] != rel["to"]
        key = (rel["from"], rel["to"], rel["type"])
        if rel["type"] == "RELATED_TO":
            key = (*sorted((rel["from"], rel["to"])), rel["type"])
        assert key not in seen
        seen.add(key)


# ---------------------------------------------------------------- 失败路径


def test_chunk_failure_is_recorded_and_run_continues(run_mod, ev, gold):
    client = FakeModelClient(responder=run_mod.fake_responder)
    # 第 1 块：调用错误（参数类 4xx，不重试）；第 2 块：两次坏 JSON（修复后仍不合规）
    client.script(ModelInvalidRequestError("fake-extraction"), purpose="extract_entities")
    client.script(BAD_JSON_TEXT, purpose="extract_entities")
    client.script(BAD_JSON_TEXT, purpose="repair")
    outcome = run_mod.run(copy.deepcopy(gold), environ=dict(FAKE_ENV), model_client=client)
    failures = outcome.run_log["chunk_failures"]
    assert len(failures) == 2
    assert failures[0]["ordinal"] == 0 and failures[0]["error"] == "invalid_request"
    assert failures[1]["ordinal"] == 1 and failures[1]["error"] == "invalid_json"
    assert outcome.exit_code == 0
    assert outcome.predictions["entities"]
    ev.validate_predictions(outcome.predictions)


def test_budget_refusal_stops_run(run_mod, gold, tmp_path, capsys):
    env = {**FAKE_ENV, "LLM_TASK_TOKEN_BUDGET": "1"}
    code, out, log = _run_main(run_mod, tmp_path, env)
    assert code == run_mod.EXIT_BUDGET
    assert not out.exists()
    run_log = json.loads(log.read_text(encoding="utf-8"))
    assert run_log["status"] == "budget_exceeded"
    assert "预算" in capsys.readouterr().err


def test_live_mode_without_key_refuses(run_mod, tmp_path, capsys):
    env = {"LLM_MODE": "live", "LLM_BASE_URL": "https://api.deepseek.com",
           "LLM_EXTRACTION_MODEL": "deepseek-flash", "LLM_CHAT_MODEL": "deepseek-flash",
           "LLM_API_KEY": "  "}
    code, out, log = _run_main(run_mod, tmp_path, env)
    assert code == run_mod.EXIT_CONFIG
    assert not out.exists() and not log.exists()
    assert "LLM_API_KEY" in capsys.readouterr().err


def test_live_mode_builds_compatible_client_under_policy(run_mod):
    from app.services.ai.compatible import CompatibleModelClient
    from app.services.ai.policy import ModelCallPolicy

    env = {"LLM_MODE": "live", "LLM_BASE_URL": "https://api.deepseek.com",
           "LLM_EXTRACTION_MODEL": "deepseek-flash", "LLM_CHAT_MODEL": "deepseek-flash",
           "LLM_API_KEY": SECRET, "LLM_TASK_TOKEN_BUDGET": "1234"}
    settings = run_mod.load_run_settings(env)
    runtime = run_mod.build_runtime(settings)
    assert isinstance(runtime.primary, CompatibleModelClient)
    assert isinstance(runtime.policy, ModelCallPolicy)
    assert runtime.policy.task_token_budget == 1234
    assert runtime.is_fake is False
    assert runtime.model_id == "deepseek-flash"
    assert SECRET not in repr(runtime)


def test_key_never_appears_in_output_or_log(run_mod, tmp_path, capsys):
    env = {"LLM_MODE": "live", "LLM_BASE_URL": "https://api.deepseek.com",
           "LLM_EXTRACTION_MODEL": "deepseek-flash", "LLM_CHAT_MODEL": "deepseek-flash",
           "LLM_API_KEY": SECRET}
    # 注入 fake 客户端代替 HTTP 适配器：不联网，但走 live 的配置与策略路径
    client = FakeModelClient(responder=run_mod.fake_responder)
    code, out, log = _run_main(run_mod, tmp_path, env, model_client=client)
    assert code == 0
    captured = capsys.readouterr()
    for text in (out.read_text(encoding="utf-8"), log.read_text(encoding="utf-8"),
                 captured.out, captured.err):
        assert SECRET not in text
    # 注入的是 fake 客户端，结果必须标为假模型
    assert json.loads(out.read_text(encoding="utf-8"))["model"]["is_fake"] is True


def test_gleaning_is_optional_and_recorded(run_mod, gold):
    outcome = run_mod.run(copy.deepcopy(gold), environ=dict(FAKE_ENV), glean_rounds=1)
    assert outcome.predictions["prompt_versions"]["extract_entities_gleaning"] == 2
    assert outcome.run_log["gleaning"]["enabled"] is True
    assert outcome.run_log["model_calls"]["by_purpose"]["extract_entities_gleaning"] == 16


def test_progress_reports_each_chunk_and_section(run_mod, gold):
    # 本机运行耗时数分钟，逐块、逐小节报告进度，避免用户误以为卡住
    lines: list[str] = []
    outcome = run_mod.run(copy.deepcopy(gold), environ=dict(FAKE_ENV), progress=lines.append)
    log = outcome.run_log
    entity_lines = [line for line in lines if line.startswith("[实体 ")]
    relation_lines = [line for line in lines if line.startswith("[关系 ")]
    assert len(entity_lines) == log["chunk_count"]
    assert len(relation_lines) == log["section_count"]
    assert entity_lines[0].startswith(f"[实体 1/{log['chunk_count']}]")
    assert all("sk-" not in line for line in lines)
