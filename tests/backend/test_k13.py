"""K13 抽取消融实验（``evaluation/ablation.py``）的离线测试。

只用 E02 fake 客户端，**不联网**。覆盖：三组在同一标注集上跑通并各自通过 ``validate_predictions``；
fake 结果一律标「假模型」且不给达标判定；单阶段复用 E05/E11 校验（块内 ID 映射、悬空端点、先修表述、
修复一次、修复仍失败记失败块并继续）；预算拒绝只停当前组、日预算按组累计、鉴权失败停止剩余组；
空样本与失败组在对照表中明确；live 缺密钥拒绝运行；密钥不出现在任何输出里；summarize 读入人工判定；
消融提示词的规则与生产两阶段提示词逐行一致。

``evaluation/`` 不是包，按文件路径导入被测模块（与 ``test_k02_run.py`` 一致）。
"""

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from app.services.ai.client import ModelAuthError
from app.services.ai.fake import BAD_JSON_TEXT, FakeModelClient

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "evaluation" / "ablation.py"
SYNTHETIC = REPO / "evaluation" / "fixtures" / "synthetic.json"
JOINT_PROMPT = REPO / "evaluation" / "prompts" / "extract_joint.yaml"

SECRET = "sk-test-DO-NOT-LEAK-k13-51c2"
FAKE_ENV = {"LLM_MODE": "fake"}


@pytest.fixture(scope="module")
def ab():
    if not SCRIPT.exists():
        pytest.fail(f"{SCRIPT.relative_to(REPO)} 不存在")
    spec = importlib.util.spec_from_file_location("k13_ablation", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["k13_ablation"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gold():
    return json.loads(SYNTHETIC.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def fake_results(ab, gold):
    return ab.run_ablation(copy.deepcopy(gold), environ=dict(FAKE_ENV), run_prefix="k13-test")


def _single_client(ab, joint_replies, *, fallback=True):
    """单阶段用脚本化应答；脚本用完后交 ``fake_responder``。"""
    client = FakeModelClient(responder=ab.fake_responder if fallback else None)
    if joint_replies:
        client.script(*joint_replies, purpose=ab.JOINT_PROMPT_PURPOSE)
    return client


def _chunk_texts(ab, gold):
    k02 = ab.k02
    _, prepared = k02.prepare_chunks(gold["documents"][0]["text"], course_id=gold["course"]["id"],
                                     document_id=gold["documents"][0]["id"])
    return [p.text for p in prepared]


# ---------------------------------------------------------------- 三组同口径


def test_three_groups_run_on_same_dataset(ab, gold, fake_results):
    ev = ab.evaluator
    assert list(fake_results) == list(ab.GROUPS)
    for group, result in fake_results.items():
        assert result["status"] == ab.STATUS_OK, group
        outcome = result["outcome"]
        ev.validate_predictions(outcome.predictions)
        assert outcome.predictions["dataset_id"] == gold["dataset_id"]
        assert outcome.run_log["chunk_count"] == 16
        assert outcome.run_log["ablation_group"] == group
        assert outcome.predictions["fusion"]["mode"] == "simplified"


def test_groups_differ_only_in_stage_configuration(fake_results):
    single = fake_results["single_stage"]["outcome"].run_log
    two = fake_results["two_stage"]["outcome"].run_log
    glean = fake_results["two_stage_gleaning"]["outcome"].run_log
    assert single["prompt_versions"] == {"extract_joint": 1}
    assert two["prompt_versions"] == {"extract_entities": 2, "extract_relations": 2}
    assert glean["prompt_versions"] == {"extract_entities": 2, "extract_relations": 2,
                                        "extract_entities_gleaning": 2}
    assert two["gleaning"]["enabled"] is False
    assert glean["gleaning"] == {"enabled": True, "max_rounds": 1, "added": 0}
    assert set(single["model_calls"]["by_purpose"]) == {"extract_joint"}
    assert "extract_entities_gleaning" in glean["model_calls"]["by_purpose"]
    assert single["max_output_tokens"]["joint"] == (two["max_output_tokens"]["entities"]
                                                    + two["max_output_tokens"]["relations"])


def test_run_ids_are_distinct_per_group(fake_results):
    ids = [r["outcome"].run_log["run_id"] for r in fake_results.values()]
    assert ids == ["k13-test-single-stage", "k13-test-two-stage", "k13-test-two-stage-gleaning"]


def test_fake_results_never_pass_as_real(ab, gold, fake_results, tmp_path):
    ab.write_results(fake_results, tmp_path)
    summary = ab.summarize_dir(gold, tmp_path)
    assert summary["any_fake"] is True
    for row in summary["groups"]:
        assert row["is_fake"] is True
        assert row["hard_indicators"]["verdict"] == ab.evaluator.VERDICT_FAKE
    markdown = (tmp_path / "ablation.md").read_text(encoding="utf-8")
    assert ab.FAKE_WARNING in markdown
    assert "（假）" in markdown
    assert ab.FUSION_CAVEAT in markdown


def test_summary_records_cost_and_versions(ab, gold, fake_results, tmp_path):
    ab.write_results(fake_results, tmp_path)
    summary = ab.summarize_dir(gold, tmp_path)
    total = 0
    for row in summary["groups"]:
        assert row["cost"]["calls"] > 0
        assert row["cost"]["billed_tokens"] > 0
        assert row["prompt_sha256"]
        assert row["model"] == "fake-extraction"
        assert row["metrics"]["entities_name_level"]["f1"] is not None
        total += row["cost"]["billed_tokens"]
    assert summary["total_billed_tokens"] == total
    for group in ab.GROUPS:
        for name in ("predictions.json", "run.json", "report.json", "sample.json", "status.json"):
            assert (tmp_path / group / name).is_file(), (group, name)


def test_markdown_is_deterministic(ab, gold, fake_results, tmp_path):
    ab.write_results(fake_results, tmp_path)
    first = ab.render_markdown(ab.summarize_dir(gold, tmp_path))
    second = ab.render_markdown(ab.summarize_dir(gold, tmp_path))
    assert first == second


# ---------------------------------------------------------------- 单阶段


def test_single_stage_maps_local_ids_and_merges_across_chunks(ab, gold, fake_results):
    preds = fake_results["single_stage"]["outcome"].predictions
    ids = {e["id"] for e in preds["entities"]}
    assert preds["relations"]
    for rel in preds["relations"]:
        assert rel["from"] in ids and rel["to"] in ids
        assert not rel["from"].startswith("e") or rel["from"].startswith("p-e")
    names = [e["name"] for e in preds["entities"]]
    assert names.count("栈") == 1
    assert fake_results["single_stage"]["outcome"].run_log["fusion"]["merged"] > 0


def test_single_stage_relation_evidence_is_in_chunk(ab, gold, fake_results):
    texts = _chunk_texts(ab, gold)
    for rel in fake_results["single_stage"]["outcome"].predictions["relations"]:
        assert any(rel["evidence"] in text for text in texts)


def _joint(entities, relations):
    return json.dumps({"entities": entities, "relations": relations}, ensure_ascii=False)


def test_single_stage_reuses_e11_rules(ab, gold):
    text = _chunk_texts(ab, gold)[0]
    evidence = text[:10]
    entities = [
        {"id": "e1", "name": "甲概念", "type": "concept", "definition": "d", "evidence": evidence},
        {"id": "e2", "name": "乙概念", "type": "concept", "definition": "d", "evidence": evidence},
        {"id": "e2", "name": "重复编号", "type": "concept", "definition": "d", "evidence": evidence},
        {"id": "e3", "name": "证据不在块内", "type": "concept", "definition": "d", "evidence": "不存在的原文"},
    ]
    relations = [
        {"from_id": "e1", "to_id": "e2", "type": "PREREQUISITE", "evidence": evidence},  # 无先修表述
        {"from_id": "e1", "to_id": "e9", "type": "RELATED_TO", "evidence": evidence},    # 悬空
        {"from_id": "e1", "to_id": "e1", "type": "RELATED_TO", "evidence": evidence},    # 自环
        {"from_id": "e1", "to_id": "e2", "type": "CONTAINS", "evidence": evidence},
    ]
    client = FakeModelClient()
    client.script(_joint(entities, relations), purpose=ab.JOINT_PROMPT_PURPOSE)
    client.script(*[_joint([], [])] * 20, purpose=ab.JOINT_PROMPT_PURPOSE)
    outcome = ab.run_single_stage(copy.deepcopy(gold), environ=dict(FAKE_ENV), model_client=client)
    preds = outcome.predictions
    assert [e["name"] for e in preds["entities"]] == ["甲概念", "乙概念"]
    assert [(r["from"], r["to"], r["type"]) for r in preds["relations"]] == [("p-e001", "p-e002", "CONTAINS")]
    dropped = outcome.run_log["dropped"]
    assert dropped["entities"] == {"evidence_not_in_chunk": 1, "invalid_local_id": 1}
    assert dropped["relations"] == {"dangling_endpoint": 1, "prerequisite_without_cue": 1, "self_loop": 1}


def test_single_stage_repairs_once_then_succeeds(ab, gold):
    client = _single_client(ab, [BAD_JSON_TEXT])
    outcome = ab.run_single_stage(copy.deepcopy(gold), environ=dict(FAKE_ENV), model_client=client)
    assert outcome.exit_code == 0
    assert outcome.run_log["chunk_failures"] == []
    assert outcome.run_log["model_calls"]["by_purpose"]["repair"] == 1


def test_single_stage_failed_repair_records_chunk_and_continues(ab, gold):
    client = _single_client(ab, [BAD_JSON_TEXT])
    client.script(BAD_JSON_TEXT, purpose="repair")
    outcome = ab.run_single_stage(copy.deepcopy(gold), environ=dict(FAKE_ENV), model_client=client)
    assert outcome.exit_code == 0
    failures = outcome.run_log["chunk_failures"]
    assert len(failures) == 1
    assert failures[0]["stage"] == "joint"
    assert failures[0]["error"] == "invalid_json"
    assert outcome.predictions["entities"]  # 其余块照常抽取


def test_single_stage_missing_relations_array_is_invalid_structure(ab, gold):
    client = _single_client(ab, ['{"entities": []}'])
    client.script('{"entities": []}', purpose="repair")
    outcome = ab.run_single_stage(copy.deepcopy(gold), environ=dict(FAKE_ENV), model_client=client)
    assert outcome.run_log["chunk_failures"][0]["error"] == "invalid_structure"


def test_joint_prompt_loads_and_mirrors_production_rules(ab):
    template = ab.PromptLibrary(ab.JOINT_PROMPTS_DIR).get(ab.JOINT_PROMPT_PURPOSE, ab.JOINT_PROMPT_VERSION)
    assert template.variables == ("chunk_text",)
    assert template.evaluation == "evaluation/ablation.py"
    body = template.template
    for name in ("extract_entities", "extract_relations"):
        source = (REPO / "prompts" / f"{name}.yaml").read_text(encoding="utf-8")
        rule_lines = [line.strip() for line in source.split("\n") if line.strip().startswith("- ")]
        rule_lines = [line for line in rule_lines if not line.startswith(("- chunk_text", "- entity_table",
                                                                          "- source_chunks"))]
        # 只有两条按单阶段改写：证据来源从「来源资料」改为「资料块」，空结果改为同时给出两个数组
        adapted = ("- evidence 必须从来源资料", "- 没有可确认的关系时输出")
        missing = [line for line in rule_lines if line not in body and not line.startswith(adapted)]
        assert missing == [], (name, missing)
    assert "evidence 必须从资料块中逐字连续摘录" in body
    assert '{"entities": [], "relations": []}' in body


# ---------------------------------------------------------------- 预算、失败组、空样本


def test_task_budget_stops_only_that_group(ab, gold, tmp_path):
    env = {**FAKE_ENV, "LLM_TASK_TOKEN_BUDGET": "5000"}
    (tmp_path / "single_stage").mkdir()
    (tmp_path / "single_stage" / "predictions.json").write_text("{}", encoding="utf-8")  # 上一次的残留
    results = ab.run_ablation(copy.deepcopy(gold), environ=env, run_prefix="k13-budget")
    assert {r["status"] for r in results.values()} == {ab.STATUS_BUDGET}
    ab.write_results(results, tmp_path)
    assert not (tmp_path / "single_stage" / "predictions.json").exists()
    summary = ab.summarize_dir(gold, tmp_path)
    for row in summary["groups"]:
        assert row["status"] == ab.STATUS_BUDGET
        assert "预算" in row["message"]
        assert "metrics" not in row
    assert ab.exit_code_for(results) == ab.EXIT_BUDGET


def test_daily_budget_is_shared_across_groups(ab, gold):
    env = {**FAKE_ENV, "LLM_DAILY_TOKEN_BUDGET": "40000"}
    results = ab.run_ablation(copy.deepcopy(gold), environ=env, run_prefix="k13-daily")
    single = results["single_stage"]
    assert single["status"] == ab.STATUS_OK
    used = single["outcome"].run_log["model_calls"]["billed_tokens"]
    assert used < 40000
    two = results["two_stage"]
    assert two["outcome"].run_log["budgets"]["daily"] == 40000 - used
    assert two["outcome"].run_log["budgets"]["daily_used_before_group"] == used
    assert two["status"] == ab.STATUS_BUDGET
    assert results["two_stage_gleaning"]["status"] == ab.STATUS_SKIPPED
    assert results["two_stage_gleaning"]["outcome"] is None


def test_auth_failure_halts_remaining_groups(ab, gold, tmp_path):
    client = FakeModelClient(responder=ab.fake_responder)
    client.script(ModelAuthError("fake-extraction", status_code=401), purpose=ab.JOINT_PROMPT_PURPOSE)
    results = ab.run_ablation(copy.deepcopy(gold), environ=dict(FAKE_ENV), model_client=client,
                              run_prefix="k13-auth")
    assert results["single_stage"]["status"] == ab.STATUS_ABORTED
    assert results["two_stage"]["status"] == ab.STATUS_NOT_RUN
    assert results["two_stage_gleaning"]["status"] == ab.STATUS_NOT_RUN
    assert ab.exit_code_for(results) == ab.EXIT_ABORTED
    ab.write_results(results, tmp_path)
    markdown = ab.render_markdown(ab.summarize_dir(gold, tmp_path))
    assert "后续组未运行" in markdown
    assert "not_run" in markdown


def test_empty_sample_is_marked(ab, gold, tmp_path):
    client = FakeModelClient(responder=lambda request: json.dumps(
        {"entities": [], "relations": []} if request.purpose == ab.JOINT_PROMPT_PURPOSE else
        ({"relations": []} if request.purpose == "extract_relations" else {"entities": []})))
    results = ab.run_ablation(copy.deepcopy(gold), environ=dict(FAKE_ENV), model_client=client,
                              run_prefix="k13-empty")
    ab.write_results(results, tmp_path)
    summary = ab.summarize_dir(gold, tmp_path)
    assert all(row["empty"] for row in summary["groups"])
    assert ab.render_markdown(summary).count("（空样本）") == 3


def test_unknown_or_duplicate_group_is_config_error(ab, gold):
    for groups in (["bogus"], ["two_stage", "two_stage"], []):
        with pytest.raises(ab.k02.RunConfigError):
            ab.run_ablation(copy.deepcopy(gold), environ=dict(FAKE_ENV), groups=groups)
    with pytest.raises(ab.k02.RunConfigError):
        ab.run_ablation(copy.deepcopy(gold), environ=dict(FAKE_ENV), glean_rounds=0)


# ---------------------------------------------------------------- CLI、密钥、人工判定


def test_live_without_key_is_refused(ab, tmp_path, capsys):
    code = ab.main(["run", "--gold", str(SYNTHETIC), "--out-dir", str(tmp_path)],
                   environ={"LLM_MODE": "live", "LLM_API_KEY": " "})
    assert code == ab.EXIT_CONFIG
    assert "LLM_API_KEY" in capsys.readouterr().err
    assert not any(tmp_path.iterdir())


def test_secret_never_written_or_printed(ab, tmp_path, capsys):
    env = {**FAKE_ENV, "LLM_API_KEY": SECRET}
    code = ab.main(["run", "--gold", str(SYNTHETIC), "--out-dir", str(tmp_path), "--run-prefix", "k13-secret"],
                   environ=env)
    assert code == ab.EXIT_OK
    captured = capsys.readouterr()
    assert SECRET not in captured.out + captured.err
    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert SECRET not in path.read_text(encoding="utf-8"), path


def test_summarize_reads_judgments(ab, gold, fake_results, tmp_path, capsys):
    ab.write_results(fake_results, tmp_path)
    ab.summarize_dir(gold, tmp_path)
    sample = json.loads((tmp_path / "two_stage" / "sample.json").read_text(encoding="utf-8"))
    judgments = sample["judgments_template"]
    judgments["judge"] = "测试"
    for kind in ("entities", "relations"):
        judgments[kind] = {item_id: "correct" for item_id in judgments[kind]}
    (tmp_path / "two_stage" / "judgments.json").write_text(json.dumps(judgments, ensure_ascii=False),
                                                          encoding="utf-8")
    code = ab.main(["summarize", "--gold", str(SYNTHETIC), "--out-dir", str(tmp_path)], environ=dict(FAKE_ENV))
    assert code == ab.EXIT_OK
    summary = json.loads((tmp_path / "ablation.json").read_text(encoding="utf-8"))
    rows = {row["group"]: row for row in summary["groups"]}
    assert rows["two_stage"]["hard_indicators"]["entity_accuracy_status"] == "judged"
    assert rows["two_stage"]["hard_indicators"]["entity_accuracy"] == 1.0
    assert rows["single_stage"]["hard_indicators"]["entity_accuracy_status"] == "not_judged"
    assert rows["two_stage"]["hard_indicators"]["verdict"] == ab.evaluator.VERDICT_FAKE
    assert "两阶段" in capsys.readouterr().out


def test_summarize_marks_groups_never_run(ab, gold, tmp_path):
    summary = ab.summarize_dir(gold, tmp_path)
    assert [row["status"] for row in summary["groups"]] == [ab.STATUS_NOT_RUN] * 3
    assert summary["total_billed_tokens"] == 0
