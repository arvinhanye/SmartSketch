"""B12：学习进度与下一步推荐的 wire 契约（specs/learning-path.md §3～§5、§7；ADR-014 修订 1 决定 7、8）。

B12-R1：完整性错误 `details.request_id` 与 `PUT /progress` 的 422 `not_in_published_version`（ADR-017 决定 4、5）。
"""

import copy
import importlib.util
import re
import sys
from pathlib import Path

import jsonschema
import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
SPEC = yaml.safe_load((ROOT / "src/contracts/api.v1.yaml").read_text(encoding="utf-8"))
SCHEMAS = SPEC["components"]["schemas"]
PATHS = SPEC["paths"]
PROGRESS = PATHS["/api/v1/courses/{cid}/progress"]
RECOMMEND = PATHS["/api/v1/courses/{cid}/recommend"]["get"]
GENERATED = ROOT / "src/contracts/v1/generated"


def _rewrite(node):
    if isinstance(node, dict):
        return {
            key: (value.replace("#/components/schemas/", "#/$defs/")
                  if key == "$ref" and isinstance(value, str) else _rewrite(value))
            for key, value in node.items()
        }
    if isinstance(node, list):
        return [_rewrite(item) for item in node]
    return node


DEFS = _rewrite(copy.deepcopy(SCHEMAS))


def is_valid(name: str, instance) -> bool:
    return jsonschema.Draft202012Validator({"$defs": DEFS, "$ref": f"#/$defs/{name}"}).is_valid(instance)


def is_valid_inline(schema: dict, instance) -> bool:
    return jsonschema.Draft202012Validator({"$defs": DEFS, **_rewrite(copy.deepcopy(schema))}).is_valid(instance)


def generated_models():
    path = GENERATED / "python/models.py"
    spec = importlib.util.spec_from_file_location("b12_generated_models", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module   # Pydantic 按模块命名空间解析前向引用
    spec.loader.exec_module(module)
    return module


def _without(payload: dict, field: str) -> dict:
    return {k: v for k, v in payload.items() if k != field}


def _json_schema(response: dict) -> dict:
    return response["content"]["application/json"]["schema"]


TS = "2026-09-25T08:00:00Z"

# ── 进度（§5，决定 8）─────────────────────────────────────────────────────────

OWN_ONLY = {"kp_id": "kp_a", "status": "mastered", "own_status": "mastered", "inherited_from": [], "updated_at": TS}
NO_ROW = {"kp_id": "kp_c", "status": "unknown", "own_status": None, "inherited_from": [], "updated_at": None}
# LP-17：A 已掌握、B 无行，A 并入 B
LP17_B = {"kp_id": "kp_b", "status": "mastered", "own_status": None,
          "inherited_from": [{"kp_id": "kp_a", "status": "mastered"}], "updated_at": None}
# LP-18 后者：B 的 unknown 写于合并之前，A 仍参与取最高
LP18_B_BEFORE = {"kp_id": "kp_b", "status": "mastered", "own_status": "unknown",
                 "inherited_from": [{"kp_id": "kp_a", "status": "mastered"}], "updated_at": TS}
# LP-18 前者/同值写入之后：A 被覆盖，不再列出
LP18_B_AFTER = {"kp_id": "kp_b", "status": "unknown", "own_status": "unknown", "inherited_from": [], "updated_at": TS}
LEARNING_FROM_SOURCE = {"kp_id": "kp_d", "status": "learning", "own_status": "unknown",
                        "inherited_from": [{"kp_id": "kp_e", "status": "learning"}, {"kp_id": "kp_f", "status": "unknown"}],
                        "updated_at": TS}
CHAIN_C = {"kp_id": "kp_c", "status": "mastered", "own_status": "learning",
           "inherited_from": [{"kp_id": "kp_a", "status": "mastered"}, {"kp_id": "kp_b", "status": "learning"}],
           "updated_at": TS}

VALID_ENTRIES = [OWN_ONLY, NO_ROW, LP17_B, LP18_B_BEFORE, LP18_B_AFTER, LEARNING_FROM_SOURCE, CHAIN_C]


@pytest.mark.parametrize("entry", VALID_ENTRIES)
def test_progress_entry_accepts_effective_own_and_inherited_states(entry):
    assert is_valid("ProgressEntry", entry)


def test_progress_entry_requires_all_decision_8_fields():
    assert set(SCHEMAS["ProgressEntry"]["required"]) == {"kp_id", "status", "own_status", "inherited_from", "updated_at"}


@pytest.mark.parametrize("field", ["kp_id", "status", "own_status", "inherited_from", "updated_at"])
def test_progress_entry_missing_field_is_rejected(field):
    assert not is_valid("ProgressEntry", _without(LP17_B, field))


@pytest.mark.parametrize("entry", [
    NO_ROW | {"updated_at": TS},                                            # 无自身行却有自身更新时间
    OWN_ONLY | {"updated_at": None},                                        # 有自身行却无更新时间
    OWN_ONLY | {"status": "unknown"},                                       # 有效值低于自身记录
    LP17_B | {"status": "learning"},                                        # 有效值低于继承来源
    OWN_ONLY | {"own_status": "learning"},                                  # mastered 既不来自自身也不来自来源
    LEARNING_FROM_SOURCE | {"inherited_from": [{"kp_id": "kp_f", "status": "unknown"}]},  # learning 无出处
    NO_ROW | {"status": "learning"},
    LP17_B | {"inherited_from": [{"kp_id": "kp_a", "status": "skipped"}]},  # 不设第四种状态（§2）
    OWN_ONLY | {"status": "skipped", "own_status": "skipped"},
    LP17_B | {"inherited_from": [{"kp_id": "kp_a", "status": "mastered", "write_seq": 7}]},  # 内部序号不上 wire
    LP17_B | {"inherited_from": [{"kp_id": "", "status": "mastered"}]},
    LP17_B | {"inherited_from": [{"kp_id": "kp_a"}]},
    OWN_ONLY | {"user_id": "u_1"},
    OWN_ONLY | {"kp_id": ""},
])
def test_progress_entry_invariants(entry):
    assert not is_valid("ProgressEntry", entry)


def test_progress_response_binds_version_and_lists_every_node():
    body = {"graph_version": 2, "entries": [OWN_ONLY, LP17_B, NO_ROW]}
    assert is_valid("ProgressResponse", body)
    for bad in (
        {"graph_version": 2, "entries": []},                 # V=∅ 是完整性故障，不是正常空列表
        _without(body, "graph_version"),
        body | {"graph_version": 0},
        _without(body, "entries"),
        body | {"state": "no_graph"},
        [OWN_ONLY, LP17_B],                                  # 旧形状：裸数组，无法回传 graph_version
    ):
        assert not is_valid("ProgressResponse", bad), bad
    description = SCHEMAS["ProgressResponse"]["description"]
    assert "每个节点" in description and "graph_version" in description


def test_progress_entry_description_pins_semantics():
    text = yaml.safe_dump(SCHEMAS["ProgressEntry"], allow_unicode=True)
    for needle in ("UTF-8 字节序", "未被覆盖", "自身", "同一投影"):
        assert needle in text, needle


@pytest.mark.parametrize("method", ["get", "put"])
def test_progress_operations_return_progress_response(method):
    op = PROGRESS[method]
    assert _json_schema(op["responses"]["200"]) == {"$ref": "#/components/schemas/ProgressResponse"}
    assert {"401", "403", "404", "500"} <= set(op["responses"])
    assert "GRAPH_NOT_PUBLISHED" in op["responses"]["404"]["description"]
    assert _json_schema(op["responses"]["500"]) == {"$ref": "#/components/schemas/LearningIntegrityError"}
    assert "每个节点" in op["description"]


def test_progress_put_request_is_non_empty_batch_without_user_id():
    op = PROGRESS["put"]
    body_schema = op["requestBody"]["content"]["application/json"]["schema"]
    assert "422" in op["responses"]
    assert is_valid_inline(body_schema, [{"kp_id": "kp_a", "status": "mastered"}, {"kp_id": "kp_b", "status": "unknown"}])
    for bad in (
        [],
        [{"kp_id": "kp_a"}],
        [{"kp_id": "", "status": "mastered"}],
        [{"kp_id": "kp_a", "status": "skipped"}],
        [{"kp_id": "kp_a", "status": "mastered", "user_id": "u_other"}],   # 身份只取自认证
    ):
        assert not is_valid_inline(body_schema, bad), bad
    description = op["description"]
    for needle in ("整批拒绝", "零写入", "重复", "同值写入", "graph_version"):
        assert needle in description, needle


# ── 推荐（§3、§4，决定 7）─────────────────────────────────────────────────────

WEIGHTS = {"unlock": 0.35, "importance": 0.25, "chapter_order": 0.20, "ease": 0.20}
FACTORS = {"unlock": 0.5, "importance": 1.0, "chapter_order": 1.0, "ease": 0.5}
WEIGHTED = {k: WEIGHTS[k] * FACTORS[k] for k in WEIGHTS}
SCORE = ((WEIGHTED["unlock"] + WEIGHTED["importance"]) + WEIGHTED["chapter_order"]) + WEIGHTED["ease"]
FACTS = {"primary_factor": "importance", "chapter_id": "ch_1", "chapter_name": "第一章 线性表", "chapter_rank": 0,
         "importance": 1.0, "centrality": 1.0, "difficulty": 0.5}
REC = {"kp_id": "kp_a", "name": "栈", "graph_version": 3, "score": SCORE, "factors": FACTORS, "weighted": WEIGHTED,
       "unlock_count": 1, "reason": "重要度与中心度最高（重要度 1.0000，中心度 1.0000）", "reason_facts": FACTS}
LIST = {"state": "recommendations", "graph_version": 3, "total_eligible": 4, "recommendations": [REC]}
ALL_MASTERED = {"state": "all_mastered", "graph_version": 3, "total_eligible": 0, "recommendations": []}


@pytest.mark.parametrize("payload", [
    LIST, ALL_MASTERED,
    LIST | {"recommendations": [REC] * 50, "total_eligible": 120},        # 截断后仍报告完整 total_eligible
    LIST | {"recommendations": [REC | {"unlock_count": 0, "factors": FACTORS | {"unlock": 0.0},
                                       "weighted": WEIGHTED | {"unlock": 0.0}}]},   # LP-3：u=0
    LIST | {"recommendations": [REC | {"reason_facts": FACTS | {"chapter_id": None, "chapter_name": None,
                                                                 "chapter_rank": None}}]},  # 无章节
])
def test_recommend_response_valid(payload):
    assert is_valid("RecommendResponse", payload)


@pytest.mark.parametrize("payload", [
    {},
    ALL_MASTERED | {"state": "no_graph"},                    # 不增加 no_graph（LP-11）
    LIST | {"state": "no_graph"},
    ALL_MASTERED | {"recommendations": [REC]},               # 全部掌握却有推荐
    ALL_MASTERED | {"total_eligible": 1},
    LIST | {"recommendations": []},                          # 空列表不能冒充全部掌握
    LIST | {"total_eligible": 0},
    LIST | {"recommendations": [REC] * 51},                  # 上限 50
    _without(LIST, "graph_version"),
    _without(ALL_MASTERED, "graph_version"),
    _without(LIST, "total_eligible"),
    _without(LIST, "state"),
    LIST | {"graph_version": 0},
    LIST | {"path": None},                                   # 目标路径不属于 B12（§7，O01/O02）
    {"code": "GRAPH_NOT_PUBLISHED", "message": "课程尚未发布"},  # 未发布是 404，不是 200 空态
])
def test_recommend_response_rejects(payload):
    assert not is_valid("RecommendResponse", payload)


def test_recommend_state_is_a_closed_two_way_discriminator():
    response = SCHEMAS["RecommendResponse"]
    assert response["discriminator"]["propertyName"] == "state"
    assert set(response["discriminator"]["mapping"]) == {"recommendations", "all_mastered"}

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key in ("const", "enum"):
                    assert "no_graph" not in (value if isinstance(value, list) else [value])
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)
    walk(SPEC)


def test_all_mastered_is_not_an_error_and_not_published_is_not_a_state():
    assert not is_valid("Error", ALL_MASTERED)
    assert not is_valid("LearningIntegrityError", ALL_MASTERED)
    responses = RECOMMEND["responses"]
    assert "GRAPH_NOT_PUBLISHED" in responses["404"]["description"]
    assert "all_mastered" in responses["200"]["description"]
    assert _json_schema(responses["200"]) == {"$ref": "#/components/schemas/RecommendResponse"}


@pytest.mark.parametrize("field", ["kp_id", "name", "graph_version", "score", "factors", "weighted",
                                   "unlock_count", "reason", "reason_facts"])
def test_recommendation_missing_field_is_rejected(field):
    assert not is_valid("Recommendation", _without(REC, field))


@pytest.mark.parametrize("rec", [
    REC | {"factors": FACTORS | {"unlock": 1.2}},
    REC | {"factors": FACTORS | {"ease": -0.1}},
    REC | {"factors": _without(FACTORS, "chapter_order")},
    REC | {"factors": FACTORS | {"centrality": 1.0}},
    REC | {"weighted": WEIGHTED | {"importance": -0.01}},
    REC | {"weighted": _without(WEIGHTED, "ease")},
    REC | {"score": -0.1},
    REC | {"unlock_count": -1},
    REC | {"unlock_count": 0},                                               # u>0 却称无可解锁后继
    REC | {"unlock_count": 2, "factors": FACTORS | {"unlock": 0.0}},         # 有可解锁后继却 u=0
    REC | {"reason": ""},
    REC | {"graph_version": 0},
    REC | {"reason_facts": FACTS | {"primary_factor": "centrality"}},
    REC | {"reason_facts": FACTS | {"chapter_id": None}},                    # 无章节却有秩
    REC | {"reason_facts": FACTS | {"chapter_rank": None}},                  # 有章节却无秩
    REC | {"reason_facts": FACTS | {"difficulty": 1.5}},
    REC | {"reason_facts": _without(FACTS, "centrality")},
    REC | {"generated_by": "llm"},
])
def test_recommendation_invariants(rec):
    assert not is_valid("Recommendation", rec)


def test_score_may_exceed_one_by_weight_tolerance():
    """权重和允许 1 ± 1e-9（§1）；全满分量时 score 与加权分量可略大于 1，契约不得据此拒绝。"""
    w = 1.0 + 5e-10
    rec = REC | {"factors": {k: 1.0 for k in FACTORS},
                 "weighted": {"unlock": w, "importance": 0.0, "chapter_order": 0.0, "ease": 0.0},
                 "score": w, "unlock_count": 1}
    assert is_valid("Recommendation", rec)


# ── 未舍入 double，按 u→i→c→e 求和逐位等于评分（§3）───────────────────────────

ORDER = ["unlock", "importance", "chapter_order", "ease"]


@pytest.mark.parametrize("name", ["RecommendFactors", "RecommendWeightedFactors"])
def test_factor_property_order_is_u_i_c_e_and_unrounded_double(name):
    schema = SCHEMAS[name]
    assert list(schema["properties"]) == ORDER
    assert schema["required"] == ORDER
    assert schema.get("additionalProperties") is False
    for prop in schema["properties"].values():
        assert prop["type"] == "number" and prop["format"] == "double"
        assert "multipleOf" not in prop
    assert "u→i→c→e" in schema["description"]


def test_score_description_requires_bitwise_ordered_sum_and_display_only_rounding():
    score = SCHEMAS["Recommendation"]["properties"]["score"]
    assert score["format"] == "double" and "multipleOf" not in score and "maximum" not in score
    for needle in ("u→i→c→e", "逐位", "未舍入", "展示"):
        assert needle in score["description"], needle


def test_recommendation_example_sums_bitwise_in_fixed_order():
    example = SCHEMAS["Recommendation"]["example"]
    assert is_valid("Recommendation", example)
    w = example["weighted"]
    u, i, c, e = (w[k] for k in ORDER)
    assert example["score"] == ((u + i) + c) + e
    # 示例须能区分求和顺序，否则上式对任何顺序都成立，起不到回归作用
    assert ((e + c) + i) + u != example["score"]
    for key in ORDER:
        assert w[key] == WEIGHTS[key] * example["factors"][key]
    assert example["score"] == SCORE


# ── 已提交版完整性故障（§1、§4，LP-11、LP-12）─────────────────────────────────

def test_integrity_error_carries_only_a_request_id():
    ok = {"code": "INTERNAL_ERROR", "message": "课程图谱数据异常，请联系教师",
          "details": {"request_id": "01J8Z3K4M5N6P7Q8R9S0T1V2W3"}}
    assert is_valid("LearningIntegrityError", ok)
    rid = ok["details"]["request_id"]
    for bad in (
        _without(ok, "details"),
        ok | {"details": {}},
        ok | {"details": {"request_id": ""}},
        ok | {"details": {"diagnostic_id": rid}},                                   # ADR-017 决定 4：旧字段名不再接受
        ok | {"details": {"request_id": rid, "diagnostic_id": rid}},                # 闭合对象：不并存旧名
        ok | {"details": {"request_id": rid, "cycle": ["kp_1", "kp_2", "kp_1"]}},   # 不外露环路
        ok | {"details": {"request_id": rid, "kp_id": "kp_1"}},                     # 不外露节点 ID
        ok | {"code": "GRAPH_NOT_PUBLISHED"},
        ok | {"code": "CYCLE_DETECTED"},                                            # 教师草稿的 409 不用于学生读路径
    ):
        assert not is_valid("LearningIntegrityError", bad), bad


def test_integrity_request_id_matches_chat_request_id():
    """ADR-017 决定 4：与问答的 `details.request_id` 同名同型，作为全平台日志关联编号。"""
    details = SCHEMAS["LearningIntegrityDetails"]
    assert details["required"] == ["request_id"]
    assert details["additionalProperties"] is False
    assert set(details["properties"]) == {"request_id"}
    assert details["properties"]["request_id"] == SCHEMAS["ChatErrorDetails"]["properties"]["request_id"]
    assert "ADR-017" in details["description"] and "request_id" in details["description"]
    error_description = SCHEMAS["LearningIntegrityError"]["description"]
    assert "request_id" in error_description and "专用码待定" not in error_description
    assert "ProgressOutsideGraphError" in error_description


def test_diagnostic_id_is_gone_from_source_and_generated():
    assert "diagnostic_id" not in (ROOT / "src/contracts/api.v1.yaml").read_text(encoding="utf-8")
    for rel in ("openapi.json", "python/models.py", "typescript/openapi.d.ts"):
        assert "diagnostic_id" not in (GENERATED / rel).read_text(encoding="utf-8"), rel


def test_integrity_500_covers_empty_committed_graph_on_every_learning_read():
    for op in (PROGRESS["get"], PROGRESS["put"], RECOMMEND):
        description = op["responses"]["500"]["description"]
        assert "V=∅" in description and "request_id" in description
        assert "诊断 ID" not in description
    assert "no_graph" in SCHEMAS["LearningIntegrityError"]["description"]


# ── PUT /progress 目标不在当前发布版（ADR-017 决定 5）─────────────────────────

NOT_PUBLISHED = {
    "code": "VALIDATION_ERROR",
    "message": "部分知识点不在当前发布的课程图谱中，请刷新后重试",
    "details": {
        "fields": [
            {"in": "body", "field": "[0].kp_id", "reason": "not_in_published_version"},
            {"in": "body", "field": "[12].kp_id", "reason": "not_in_published_version"},
        ],
        "graph_version": 4,
    },
}
_ITEM = NOT_PUBLISHED["details"]["fields"][0]


def _details(**changes) -> dict:
    return NOT_PUBLISHED | {"details": NOT_PUBLISHED["details"] | changes}


def test_progress_put_422_uses_progress_validation_error():
    response = PROGRESS["put"]["responses"]["422"]
    assert _json_schema(response) == {"$ref": "#/components/schemas/ProgressValidationError"}
    for needle in ("not_in_published_version", "graph_version", "草稿独有", "已删除", "他课",
                   "发布指针", "重复", "零写入", "ADR-017"):
        assert needle in response["description"], needle
    assert "待定" not in response["description"]
    for needle in ("not_in_published_version", "ADR-017"):
        assert needle in PROGRESS["put"]["description"], needle


@pytest.mark.parametrize("payload", [
    NOT_PUBLISHED,
    _details(fields=[_ITEM]),
    _details(graph_version=1),
])
def test_progress_not_in_published_version_is_accepted(payload):
    assert is_valid("ProgressValidationError", payload)


@pytest.mark.parametrize("payload", [
    # 请求体 schema 校验与同批重复仍是 B12 已定的普通 VALIDATION_ERROR，不被本修订收窄
    {"code": "VALIDATION_ERROR", "message": "m", "details": {"fields": [{"in": "body", "field": "0.status", "reason": "enum"}]}},
    {"code": "VALIDATION_ERROR", "message": "m", "details": {"fields": [{"in": "body", "field": "", "reason": "json_invalid"}]}},
    {"code": "VALIDATION_ERROR", "message": "m"},
], ids=["schema-enum", "json-invalid", "no-details"])
def test_progress_generic_validation_errors_stay_open(payload):
    assert is_valid("ProgressValidationError", payload)


@pytest.mark.parametrize("payload", [
    NOT_PUBLISHED | {"details": _without(NOT_PUBLISHED["details"], "graph_version")},
    _details(graph_version=0),
    _details(graph_version="4"),
    _details(course_id="c_other"),                                                  # details 闭合
    _details(fields=[_ITEM | {"input": "kp_x"}]),                                   # 不回显输入
    _details(fields=[_ITEM | {"reason": "not_found"}]),                             # reason 闭合
    _details(fields=[_ITEM | {"reason": "missing"}]),
    _details(fields=[_ITEM, {"in": "body", "field": "[1].status", "reason": "enum"}]),  # 不与其他 reason 混排
    _details(fields=[_ITEM | {"in": "query"}]),
    _details(fields=[_ITEM | {"field": "[0].status"}]),
    _details(fields=[_ITEM | {"field": "[-1].kp_id"}]),
    _details(fields=[_ITEM | {"field": "[01].kp_id"}]),
    _details(fields=[]),
    NOT_PUBLISHED | {"code": "NOT_FOUND"},                                          # 不用 404
    NOT_PUBLISHED | {"code": "PUBLISH_IN_PROGRESS"},                                # 不用 409
    # 缺 graph_version 时仍由 reason 触发专用结构
    {"code": "VALIDATION_ERROR", "message": "m", "details": {"fields": [_ITEM]}},
    # 带 graph_version 而 reason 取别的值
    {"code": "VALIDATION_ERROR", "message": "m",
     "details": {"fields": [{"in": "body", "field": "[0].kp_id", "reason": "string_too_short"}], "graph_version": 4}},
], ids=["no-graph-version", "graph-version-0", "graph-version-str", "extra-details", "extra-item-field",
        "reason-not-found", "reason-missing", "mixed-reasons", "in-query", "field-status", "field-negative",
        "field-leading-zero", "empty-fields", "code-404", "code-409", "reason-without-version",
        "version-with-other-reason"])
def test_progress_not_in_published_version_rejects(payload):
    assert not is_valid("ProgressValidationError", payload)


def test_not_in_published_version_details_are_closed_and_minimal():
    details = SCHEMAS["ProgressNotInPublishedVersionDetails"]
    assert details["additionalProperties"] is False
    assert set(details["required"]) == {"fields", "graph_version"} == set(details["properties"])
    item = SCHEMAS["ProgressNotInPublishedVersionField"]
    assert item["additionalProperties"] is False
    assert set(item["required"]) == {"in", "field", "reason"} == set(item["properties"])
    assert item["properties"]["in"]["const"] == "body"
    assert item["properties"]["reason"]["const"] == "not_in_published_version"
    assert "ADR-017" in SCHEMAS["ProgressValidationError"]["description"]


# ── 接口参数（决定 7；§7 目标路径不属于 B12）──────────────────────────────────

def test_recommend_limit_and_no_target_path():
    params = {p["name"]: p for p in RECOMMEND.get("parameters", [])}
    assert "target" not in params
    assert params["limit"]["schema"] == {"type": "integer", "minimum": 1, "maximum": 50, "default": 10}
    assert {"401", "403", "404", "422", "500"} <= set(RECOMMEND["responses"])
    assert "limit" in RECOMMEND["responses"]["422"]["description"]
    for branch in SCHEMAS["RecommendResponse"]["discriminator"]["mapping"].values():
        assert "path" not in SCHEMAS[branch.rsplit("/", 1)[1]]["properties"]
    assert "#/components/schemas/LearningPath" not in yaml.safe_dump(PATHS)


# ── 生成物（ADR-004：改真源后重新生成）────────────────────────────────────────

def test_generated_pydantic_models_enforce_shape():
    models = generated_models()
    models.ProgressEntry.model_validate(LP17_B)
    # 注意：datamodel-codegen 0.26.3 对 OpenAPI 3.1 的「必填且可空」字段生成 `= None` 默认值
    # （既有 GraphExchange.graph_version 同样如此），缺字段不会被 Pydantic 拒绝；必填性以真源、
    # openapi.json 与 TS 生成物为准，见 docs/handoffs/claude-b12.md 风险。
    assert {"own_status", "inherited_from", "updated_at"} <= set(models.ProgressEntry.model_fields)
    for bad in (LP17_B | {"own_status": "skipped"}, LP17_B | {"write_seq": 3},
                LP17_B | {"inherited_from": [{"kp_id": "kp_a", "status": "mastered", "commit_seq": 1}]}):
        with pytest.raises(Exception):
            models.ProgressEntry.model_validate(bad)
    models.ProgressResponse.model_validate({"graph_version": 2, "entries": [LP17_B]})
    models.RecommendResponse.model_validate(LIST)
    models.RecommendResponse.model_validate(ALL_MASTERED)
    for bad in (ALL_MASTERED | {"state": "no_graph"}, LIST | {"recommendations": []}):
        with pytest.raises(Exception):
            models.RecommendResponse.model_validate(bad)
    models.LearningIntegrityError.model_validate(
        {"code": "INTERNAL_ERROR", "message": "m", "details": {"request_id": "r1"}})
    for bad_details in ({"request_id": "r1", "cycle": []}, {"diagnostic_id": "d1"}):
        with pytest.raises(Exception):
            models.LearningIntegrityError.model_validate({"code": "INTERNAL_ERROR", "message": "m", "details": bad_details})
    models.ProgressNotInPublishedVersionDetails.model_validate(NOT_PUBLISHED["details"])
    for bad_details in (_without(NOT_PUBLISHED["details"], "graph_version"),
                        NOT_PUBLISHED["details"] | {"course_id": "c1"},
                        NOT_PUBLISHED["details"] | {"fields": [_ITEM | {"reason": "missing"}]},
                        NOT_PUBLISHED["details"] | {"fields": [_ITEM | {"field": "[0].status"}]}):
        with pytest.raises(Exception):
            models.ProgressNotInPublishedVersionDetails.model_validate(bad_details)


def test_generated_typescript_keeps_nullable_fields_required():
    ts = (GENERATED / "typescript/openapi.d.ts").read_text(encoding="utf-8")
    block = re.search(r"^        ProgressEntry: \{(.*?)^        \}", ts, re.M | re.S)
    assert block, "ProgressEntry 类型缺失"
    body = block.group(1)
    assert re.search(r"^\s+own_status: .*\| null;", body, re.M)
    assert re.search(r"^\s+updated_at: string \| null;", body, re.M)
    assert re.search(r"^\s+inherited_from: ", body, re.M)
    assert "own_status?" not in body and "updated_at?" not in body
    assert '"all_mastered"' in ts and '"no_graph"' not in ts
    block = re.search(r"^        LearningIntegrityDetails: \{(.*?)^        \}", ts, re.M | re.S)
    assert block and re.search(r"^\s+request_id: string;", block.group(1), re.M)
    block = re.search(r"^        ProgressNotInPublishedVersionField: \{(.*?)^        \}", ts, re.M | re.S)
    assert block, "ProgressNotInPublishedVersionField 类型缺失"
    assert re.search(r'^\s+in: "body";', block.group(1), re.M)
    assert re.search(r'^\s+reason: "not_in_published_version";', block.group(1), re.M)


def test_generated_openapi_json_matches_source_for_b12_schemas():
    import json
    generated = json.loads((GENERATED / "openapi.json").read_text(encoding="utf-8"))["components"]["schemas"]
    for name in ("MasteryStatus", "ProgressUpdate", "ProgressInheritedSource", "ProgressEntry", "ProgressResponse",
                 "RecommendFactors", "RecommendWeightedFactors", "RecommendReasonFacts", "Recommendation",
                 "RecommendListResponse", "RecommendAllMasteredResponse", "RecommendResponse",
                 "LearningIntegrityError", "LearningIntegrityDetails", "ProgressValidationError",
                 "ProgressNotInPublishedVersionDetails", "ProgressNotInPublishedVersionField"):
        assert generated[name] == SCHEMAS[name], name


# ── 规格状态标注 ───────────────────────────────────────────────────────────────

def test_learning_path_spec_marks_b12_gap_as_landed():
    text = (ROOT / "specs/learning-path.md").read_text(encoding="utf-8")
    section = text.split("## 7. 接口与已签收事项", 1)[1]
    assert "B12 已落实" in section and "tests/contracts/test_b12.py" in section


def test_learning_path_spec_records_b12_r1():
    text = (ROOT / "specs/learning-path.md").read_text(encoding="utf-8")
    section5 = text.split("## 5. 进度跨版本投影与写入", 1)[1].split("## 6.", 1)[0]
    for needle in ("422", "VALIDATION_ERROR", "not_in_published_version", "[<i>].kp_id", "graph_version", "ADR-017"):
        assert needle in section5, needle
    lp12 = next(line for line in text.splitlines() if line.startswith("| LP-12 "))
    for needle in ("投影到当前发布版节点集", "ProgressOutsideGraphError", "INTERNAL_ERROR", "ADR-017"):
        assert needle in lp12, needle
    section7 = text.split("## 7. 接口与已签收事项", 1)[1]
    assert "B12-R1 已落实" in section7 and "request_id" in section7


# ── 错误码文档（errors.v1.md 实现约束：details 结构须在该文件登记）───────────────

def test_errors_doc_registers_request_id_and_not_in_published_version():
    doc = (ROOT / "src/contracts/errors.v1.md").read_text(encoding="utf-8")
    assert "diagnostic_id" not in doc
    http_rows = [line for line in doc.splitlines() if line.startswith("| `INTERNAL_ERROR` | 500 |")]
    assert len(http_rows) == 1 and "request_id" in http_rows[0] and "ADR-017" in http_rows[0]
    validation = doc.split("`VALIDATION_ERROR` 的 `details`", 1)[1].split("### 图谱编辑", 1)[0]
    for needle in ("not_in_published_version", "graph_version", "[<i>].kp_id", "PUT /progress", "ADR-017"):
        assert needle in validation, needle
