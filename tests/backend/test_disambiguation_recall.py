"""Hybrid retrieval narrows candidates; it never decides semantic identity."""
from dataclasses import replace
import pytest
from app.services.ai.embeddings import EmbeddedVector


def cards():
    from app.services.fusion.recall import RecallCard
    return [RecallCard("a", "c", "散列表", "按键查询的结构", ("哈希表",)),
            RecallCard("b", "c", "哈希表", "存储键值的结构"),
            RecallCard("c", "c", "键索引", "按键查询的索引"),
            RecallCard("d", "c", "Dictionary", "Associative structure")]


def vectors():
    return {k: EmbeddedVector(v, "m", 2, "real/m/2", k) for k, v in
            dict(a=(1., 0.), b=(0.8, 0.2), c=(0., 1.), d=(1., 0.)).items()}


def test_recall_unions_alias_terms_and_semantics_without_merge_labels():
    from app.services.fusion.recall import recall_candidates
    result = recall_candidates(cards(), top_k=3, max_pairs=20, vectors=vectors())
    found = {(p.left_id, p.right_id): p for p in result.pairs}
    assert "name" in found["a", "b"].channels
    assert "lexical" in found["a", "c"].channels
    assert "vector" in found["a", "d"].channels
    assert not hasattr(found["a", "d"], "verdict")


def test_budget_reports_truncation_and_order_is_deterministic():
    from app.services.fusion.recall import recall_candidates
    a = recall_candidates(cards(), top_k=3, max_pairs=1, vectors=vectors())
    b = recall_candidates(list(reversed(cards())), top_k=3, max_pairs=1, vectors=vectors())
    assert a == b and a.truncated_pairs > 0 and len(a.pairs) == 1


def test_missing_vector_channel_is_explicit_not_synthetic_similarity():
    from app.services.fusion.recall import recall_candidates
    result = recall_candidates(cards(), top_k=3, max_pairs=20)
    assert result.missing_channels == ("vector",)
    assert all("vector" not in p.channels for p in result.pairs)


@pytest.mark.parametrize("mode", ["course", "space", "fake", "missing", "duplicate"])
def test_recall_rejects_invalid_scope_or_vector_corpus(mode):
    from app.services.fusion.recall import recall_candidates
    items, vec = cards(), vectors()
    if mode == "course": items[1] = replace(items[1], course_id="other")
    if mode == "space": vec["b"] = replace(vec["b"], space="real/other/2")
    if mode == "fake": vec = {k: replace(v, space="fake/2") for k, v in vec.items()}
    if mode == "missing": del vec["b"]
    if mode == "duplicate": items.append(items[0])
    with pytest.raises(ValueError):
        recall_candidates(items, top_k=3, max_pairs=20, vectors=vec)
