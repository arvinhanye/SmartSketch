"""L14-3（R11）：推荐理由句不把缺失属性的中性值 0.5 说成测量值。

抽取与教师编辑目前都不填 importance / difficulty，服务端按中性值 0.5 参与排序（ADR-014 修订 1 决定 5）；
理由句在属性缺失时写「未标注」，明确存在的值（包括恰为 0.5）照常写数值。
"""

from app.services.learning.ranking import RecommendWeights
from test_i04 import kp, rank


def test_ease_primary_with_missing_difficulty_says_unlabelled():
    (a,) = rank(["A"], [], set(), attrs=[kp("A")], weights=RecommendWeights(0, 0, 0, 1))
    assert a.reason_facts.primary_factor == "ease"
    assert a.reason_facts.difficulty == 0.5
    assert a.reason == "该点的主要推荐依据是易学度（难度未标注，按中性值 0.5 计，易学度 0.5000）"


def test_importance_primary_with_missing_importance_says_unlabelled():
    (a,) = rank(["A", "B"], [("A", "B")], set(), attrs=[kp("A"), kp("B")], weights=RecommendWeights(0, 1, 0, 0))
    assert a.reason_facts.primary_factor == "importance"
    assert a.reason == "该点的主要推荐依据是重要度（重要度未标注，按中性值 0.5 计，中心度 1.0000）"


def test_explicit_neutral_value_is_still_a_number():
    (a,) = rank(["A"], [], set(), attrs=[kp("A", difficulty=0.5)], weights=RecommendWeights(0, 0, 0, 1))
    assert a.reason == "该点的主要推荐依据是易学度（难度 0.5000，易学度 0.5000）"


def test_wire_marks_missing_attributes_without_guessing_neutral_values():
    from app.services.learning.recommend import _item
    (missing,) = rank(["A"], [], set(), attrs=[kp("A")], weights=RecommendWeights(0, 0, 0, 1))
    (explicit,) = rank(["A"], [], set(), attrs=[kp("A", importance=0.5, difficulty=0.5)], weights=RecommendWeights(0, 0, 0, 1))
    assert _item(missing, 1)["reason_facts"]["importance_defaulted"] is True
    assert _item(missing, 1)["reason_facts"]["difficulty_defaulted"] is True
    assert _item(explicit, 1)["reason_facts"]["importance_defaulted"] is False
    assert _item(explicit, 1)["reason_facts"]["difficulty_defaulted"] is False


def test_qa_output_cap_is_2048_without_changing_rewrite_cap():
    from app.services.qa.generate import ANSWER_MAX_OUTPUT_TOKENS
    from app.services.qa.rewrite import REWRITE_MAX_OUTPUT_TOKENS
    assert ANSWER_MAX_OUTPUT_TOKENS == 2048
    assert REWRITE_MAX_OUTPUT_TOKENS == 300
