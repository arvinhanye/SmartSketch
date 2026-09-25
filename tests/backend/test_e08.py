"""E08：名称归一与重复候选（``docs/atomic-task-plan.md`` E08；``docs/tasks.md`` 第六批 E08 验收）。

归一键：NFKC → 去格式字符 → 仅 ASCII 字母小写 → 圆括号拆分主名/别名 → 空白规则。
候选：主键相同 ``same_key``；别名命中 ``alias``；名称前缀包含 ``containment``（短键有效字符 ≥ 2、
短/长有效字符比 ≥ 3/5，且不切断拉丁/数字串）。E08 只列候选、不合并。
"""

import ast
import dataclasses
import itertools
import random
from fractions import Fraction
from pathlib import Path

import pytest

from app.services.fusion.normalize import (
    CONTAINMENT_MIN_RATIO,
    CONTAINMENT_MIN_CHARS,
    CandidateReason,
    DuplicateCandidate,
    NameEntry,
    NormalizedName,
    find_duplicate_candidates,
    normalize_name,
)

MODULE = Path(__file__).resolve().parents[2] / "src/backend/app/services/fusion/normalize.py"


def key(name):
    return normalize_name(name).key


def aliases(name):
    return normalize_name(name).aliases


def entries(*names):
    """按出现顺序给 ``e0``、``e1``…… 编号。"""
    return [NameEntry(f"e{i}", name) for i, name in enumerate(names)]


def pairs(*names):
    """返回 ``{(左名, 右名): (原因, 命中键)}``，便于按名称断言。"""
    items = entries(*names)
    by_id = {e.entity_id: e.name for e in items}
    return {
        (by_id[c.left_id], by_id[c.right_id]): (c.reason, c.matched_key)
        for c in find_duplicate_candidates(items)
    }


def reason_of(a, b):
    found = pairs(a, b)
    assert len(found) <= 1
    return next(iter(found.values()))[0] if found else None


# --- 全半角 -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("ＡＢＣ树", "abc树"),
        ("Ｂ＋树", "b+树"),
        ("Ｃ＋＋", "c++"),
        ("第１章", "第1章"),
        ("ｈａｓｈ　ｔａｂｌｅ", "hash table"),
    ],
)
def test_fullwidth_folds_to_halfwidth(raw, expected):
    assert key(raw) == expected


def test_fullwidth_and_halfwidth_names_share_key():
    assert key("Ｂ＋树") == key("B+树") == key("b+ 树")


# --- 空白 -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  二叉树  ", "二叉树"),
        ("二叉　树", "二叉树"),
        ("二 \t叉\n树", "二叉树"),
        ("　栈　", "栈"),
        ("hash   table", "hash table"),
        ("Hash　\tTable", "hash table"),
        ("C 语言", "c语言"),
        ("B + 树", "b+树"),
        ("B+ tree", "b+tree"),
        ("binary  search   tree", "binary search tree"),
        (" 栈 ", "栈"),
    ],
)
def test_whitespace_rules(raw, expected):
    assert key(raw) == expected


def test_space_between_latin_words_is_a_boundary_not_removed():
    assert key("hash table") != key("hashtable")


# --- 大小写 -----------------------------------------------------------------


def test_ascii_latin_case_folds():
    assert key("STACK") == key("Stack") == key("stack") == "stack"
    assert key("ＳＴＡＣＫ") == "stack"


def test_non_ascii_letters_keep_case():
    # 数学符号大小写含义不同：Σ（求和）与 σ（标准差）不能归一到同一个键
    assert key("Σ") != key("σ")
    assert key("Δ算子") == "Δ算子"


# --- 格式字符 ---------------------------------------------------------------


@pytest.mark.parametrize("raw", ["栈​帧", "﻿栈帧", "栈‍帧", "栈帧⁠"])
def test_format_characters_removed(raw):
    assert key(raw) == "栈帧"


# --- 括号：主名与别名 -------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "main", "alias"),
    [
        ("栈（Stack）", "栈", ("stack",)),
        ("栈(Stack)", "栈", ("stack",)),
        ("先进先出(FIFO)", "先进先出", ("fifo",)),
        ("先进先出（ＦＩＦＯ）", "先进先出", ("fifo",)),
        ("栈 ( Stack )", "栈", ("stack",)),
        ("Stack (LIFO)", "stack", ("lifo",)),
        ("栈（Stack，堆栈）", "栈", ("stack", "堆栈")),
        ("栈（Stack、堆栈）", "栈", ("stack", "堆栈")),
        ("栈（Stack; 堆栈）", "栈", ("stack", "堆栈")),
        ("栈(Stack)(LIFO)", "栈", ("lifo", "stack")),
        ("栈（又称堆栈）", "栈", ("堆栈",)),
        ("队列（英文：Queue）", "队列", ("queue",)),
        ("散列表（简称 哈希表）", "散列表", ("哈希表",)),
        ("二叉 搜索树（Binary Search Tree）", "二叉搜索树", ("binary search tree",)),
    ],
)
def test_trailing_parentheses_are_aliases(raw, main, alias):
    n = normalize_name(raw)
    assert n.key == main
    assert n.aliases == alias


def test_aliases_sorted_deduped_and_exclude_main_key():
    assert aliases("栈（STACK，stack，Stack）") == ("stack",)
    assert aliases("栈（栈）") == ()
    assert aliases("栈（ 栈 ，Stack）") == ("stack",)
    assert aliases("栈（B，A）") == ("a", "b")


def test_empty_groups_and_empty_alias_items_ignored():
    assert normalize_name("栈()") == NormalizedName("栈", ())
    assert normalize_name("栈（ ， ）") == NormalizedName("栈", ())
    assert normalize_name("栈（又称）") == NormalizedName("栈", ("又称",))


def test_marker_only_stripped_when_something_remains():
    # 「又称」后没有内容时不当标记，原样作别名（总比丢失信息好）
    assert aliases("栈（又称）") == ("又称",)
    assert aliases("栈（亦称LIFO结构）") == ("lifo结构",)


def test_label_markers_require_colon():
    assert aliases("队列（英文：Queue）") == ("queue",)
    assert aliases("队列（英文名: Queue）") == ("queue",)
    assert aliases("队列（英文Queue）") == ("英文queue",)
    # 「即」不是标记：「即时编译」是合法别名，不能被切成「时编译」
    assert aliases("JIT（即时编译）") == ("即时编译",)


def test_middle_group_is_annotation_dropped_not_alias():
    n = normalize_name("图（Graph）的遍历")
    assert n == NormalizedName("图的遍历", ())
    assert key("（注）图的遍历") == "图的遍历"


def test_group_glued_to_latin_or_digit_is_literal_formula():
    assert normalize_name("O(n)") == NormalizedName("o(n)", ())
    assert normalize_name("f（x）") == NormalizedName("f(x)", ())
    assert normalize_name("O(n log n)复杂度") == NormalizedName("o(n log n)复杂度", ())
    assert normalize_name("x2(t)") == NormalizedName("x2(t)", ())


def test_glued_group_with_non_ascii_content_is_alias_not_formula():
    assert normalize_name("JIT（即时编译）") == NormalizedName("jit", ("即时编译",))
    assert normalize_name("CPU(中央处理器)") == NormalizedName("cpu", ("中央处理器",))
    # 已知代价：紧贴且全 ASCII 的组按公式保留
    assert normalize_name("Stack(LIFO)") == NormalizedName("stack(lifo)", ())
    assert normalize_name("Stack (LIFO)") == NormalizedName("stack", ("lifo",))


def test_nested_parentheses_keep_inner_literal():
    n = normalize_name("栈（Stack (LIFO)）")
    assert n.key == "栈"
    assert n.aliases == ("stack(lifo)",)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("栈（Stack", "栈(stack"), ("栈)", "栈)"), ("栈（a）)", "栈(a))"), (")栈(", ")栈(")],
)
def test_unbalanced_parentheses_are_literal(raw, expected):
    assert normalize_name(raw) == NormalizedName(expected, ())


def test_name_entirely_in_parentheses_uses_first_group_as_main():
    assert normalize_name("（栈）") == NormalizedName("栈", ())
    assert normalize_name("(Stack)(栈)") == NormalizedName("stack", ("栈",))
    assert normalize_name("( )(栈)") == NormalizedName("栈", ())


def test_keys_property_lists_main_then_aliases():
    assert normalize_name("栈（Stack）").keys == ("栈", "stack")


@pytest.mark.parametrize("raw", ["二叉树", "hash table", "c++", "b+树", "o(n)"])
def test_normalizing_a_key_is_idempotent(raw):
    once = key(raw)
    assert key(once) == once


def test_normalize_is_deterministic():
    names = ["栈（Stack）", "ＡＢＣ", "图（Graph）的遍历", "O(n)", "  hash　table "]
    first = [normalize_name(n) for n in names]
    assert [normalize_name(n) for n in names] == first


# --- 非法输入 ---------------------------------------------------------------


@pytest.mark.parametrize("bad", [None, 1, 1.5, True, b"stack", ["栈"], object()])
def test_non_string_name_rejected(bad):
    with pytest.raises(TypeError):
        normalize_name(bad)


@pytest.mark.parametrize("bad", ["", "   ", "　", "\t\n", "()", "（ ）", "​", "(​)"])
def test_empty_name_rejected(bad):
    with pytest.raises(ValueError):
        normalize_name(bad)


@pytest.mark.parametrize("bad_id", [None, 3, b"e1"])
def test_entry_id_must_be_string(bad_id):
    with pytest.raises(TypeError):
        NameEntry(bad_id, "栈")


@pytest.mark.parametrize("bad_id", ["", "  ", "　"])
def test_entry_id_must_be_non_blank(bad_id):
    with pytest.raises(ValueError):
        NameEntry(bad_id, "栈")


@pytest.mark.parametrize("bad", [None, 7, b"x"])
def test_entry_name_must_be_string(bad):
    with pytest.raises(TypeError):
        NameEntry("e1", bad)


@pytest.mark.parametrize("bad", [7, b"x", ["定义"]])
def test_entry_definition_must_be_string_or_none(bad):
    with pytest.raises(TypeError):
        NameEntry("e1", "栈", bad)


def test_entry_accepts_definition():
    assert NameEntry("e1", "栈", "后进先出的线性表").definition == "后进先出的线性表"
    assert NameEntry("e1", "栈").definition is None


def test_blank_name_in_batch_rejected():
    with pytest.raises(ValueError):
        find_duplicate_candidates([NameEntry("a", "栈"), NameEntry("b", "（ ）")])


def test_duplicate_entity_ids_rejected():
    with pytest.raises(ValueError):
        find_duplicate_candidates([NameEntry("a", "栈"), NameEntry("a", "队列")])


@pytest.mark.parametrize("bad", ["栈", [("a", "栈")], [NameEntry("a", "栈"), "队列"], [None]])
def test_non_entry_items_rejected(bad):
    with pytest.raises(TypeError):
        find_duplicate_candidates(bad)


# --- 同键候选 ---------------------------------------------------------------


def test_same_key_candidates():
    assert pairs("栈", "栈（Stack）") == {("栈", "栈（Stack）"): (CandidateReason.SAME_KEY, "栈")}
    assert reason_of("二叉树", "二叉　树 ") is CandidateReason.SAME_KEY
    assert reason_of("Ｂ＋树", "B+树") is CandidateReason.SAME_KEY
    assert reason_of("HASH TABLE", "hash  table") is CandidateReason.SAME_KEY
    assert reason_of("栈（Stack）", "栈（堆栈）") is CandidateReason.SAME_KEY


def test_same_key_group_of_three_yields_all_pairs():
    found = find_duplicate_candidates(entries("栈", "栈 ", "（栈）"))
    assert [(c.left_id, c.right_id) for c in found] == [("e0", "e1"), ("e0", "e2"), ("e1", "e2")]
    assert {c.reason for c in found} == {CandidateReason.SAME_KEY}
    assert {c.matched_key for c in found} == {"栈"}


def test_definition_does_not_affect_candidates():
    a = NameEntry("a", "栈", "后进先出的线性表")
    b = NameEntry("b", "栈", "完全不同的定义")
    c = NameEntry("c", "队列", "后进先出的线性表")
    found = find_duplicate_candidates([a, b, c])
    assert [(x.left_id, x.right_id, x.reason) for x in found] == [("a", "b", CandidateReason.SAME_KEY)]


# --- 别名候选 ---------------------------------------------------------------


def test_alias_matches_other_main_key():
    assert pairs("先进先出(FIFO)", "FIFO") == {
        ("先进先出(FIFO)", "FIFO"): (CandidateReason.ALIAS, "fifo")
    }
    assert reason_of("栈（Stack）", "STACK") is CandidateReason.ALIAS


def test_shared_alias_is_alias_candidate():
    assert pairs("堆栈（Stack）", "栈(stack)") == {
        ("堆栈（Stack）", "栈(stack)"): (CandidateReason.ALIAS, "stack")
    }


def test_alias_matched_key_is_smallest_shared_key():
    found = pairs("栈（Stack，LIFO）", "堆栈（LIFO，Stack）")
    assert list(found.values()) == [(CandidateReason.ALIAS, "lifo")]


def test_literal_formula_group_does_not_create_alias():
    assert reason_of("O(n)", "n") is None


def test_middle_group_does_not_create_alias():
    # 「图（Graph）的遍历」里的 Graph 只注释「图」，不是整个名称的别名
    assert reason_of("图（Graph）的遍历", "Graph") is None


# --- 包含候选 ---------------------------------------------------------------


def test_containment_positive_examples():
    assert pairs("快速排序", "快速排序算法") == {
        ("快速排序", "快速排序算法"): (CandidateReason.CONTAINMENT, "快速排序")
    }
    assert reason_of("动态规划法", "动态规划") is CandidateReason.CONTAINMENT
    assert reason_of("最短路径", "最短路径问题") is CandidateReason.CONTAINMENT
    assert reason_of("Dijkstra", "Dijkstra算法") is CandidateReason.CONTAINMENT
    assert reason_of("KMP", "ＫＭＰ算法") is CandidateReason.CONTAINMENT


def test_containment_thresholds_are_inclusive():
    assert CONTAINMENT_MIN_CHARS == 2
    assert CONTAINMENT_MIN_RATIO == Fraction(3, 5)
    # 3/5 恰等于比例门槛：列为候选
    assert reason_of("二叉树", "二叉树遍历") is CandidateReason.CONTAINMENT
    # 2 个有效字符恰等于最短门槛、2/3 ≥ 3/5：列为候选
    assert reason_of("散列", "散列法") is CandidateReason.CONTAINMENT
    # 2/4 < 3/5：不列
    assert reason_of("排序", "排序算法") is None
    # 3/6 < 3/5：不列
    assert reason_of("二叉树", "二叉树的遍历") is None


def test_significant_chars_ignore_punctuation_and_spaces():
    # 「c++」只有 1 个有效字符（c），低于最短门槛
    assert reason_of("C++", "C++模板") is None
    # 「b+树」有 2 个有效字符（b、树），「b+树索引」有 4 个：2/4 < 3/5
    assert reason_of("B+树", "B+树索引") is None
    assert reason_of("B+树", "B+树法") is CandidateReason.CONTAINMENT


def test_only_prefix_containment_counts():
    # 前加修饰语通常得到下位概念（平衡二叉树 ⊂ 二叉树），不是重复
    assert reason_of("二叉树", "平衡二叉树") is None
    assert reason_of("链表", "单链表") is None
    assert reason_of("排序", "堆排序") is None
    assert reason_of("最短路径", "单源最短路径") is None
    assert reason_of("binary tree", "balanced binary tree") is None
    # 中间出现也不算
    assert reason_of("二叉树", "平衡二叉树法") is None


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("栈", "栈帧"),
        ("树", "二叉树"),
        ("图", "图灵机"),
        ("C", "C++"),
        ("C", "C语言"),
        ("C++", "C++模板"),
        ("二叉树", "平衡二叉树"),
        ("链表", "单链表"),
        ("排序", "堆排序"),
        ("Java", "JavaScript"),
        ("tree", "street"),
        ("hash table", "hash tables"),
        ("Σ", "σ"),
        ("排序", "快速排序"),
        ("排序", "归并排序"),
        ("k2", "k23"),
    ],
)
def test_false_merge_counterexamples_stay_independent(a, b):
    assert reason_of(a, b) is None


def test_single_character_names_do_not_flood():
    names = ["图", "树", "栈", "堆", "图灵机", "二叉树", "栈帧", "堆排序", "图的遍历", "树的高度"]
    assert find_duplicate_candidates(entries(*names)) == ()


def test_generic_short_name_does_not_pair_with_every_longer_name():
    # 后缀包含（X排序）不算；唯一的前缀包含「排序算法」比例 2/4 < 3/5
    assert pairs("排序", "快速排序", "归并排序", "冒泡排序", "堆排序", "排序算法") == {}


def test_containment_needs_latin_word_boundary():
    assert reason_of("binary tree", "binary trees") is None
    assert reason_of("Java", "JavaScript") is None
    assert reason_of("k2", "k23") is None
    assert reason_of("red black", "red black tree") is CandidateReason.CONTAINMENT
    assert reason_of("Dijkstra", "Dijkstra算法") is CandidateReason.CONTAINMENT


# --- 原因优先级 -------------------------------------------------------------


def test_reason_precedence_alias_over_containment():
    found = pairs("快速排序(QS)", "快速排序算法（QS）")
    assert list(found.values()) == [(CandidateReason.ALIAS, "qs")]


def test_reason_precedence_same_key_over_alias():
    found = pairs("栈（Stack）", "栈（Stack，LIFO）")
    assert list(found.values()) == [(CandidateReason.SAME_KEY, "栈")]


def test_candidate_reason_values_are_stable_wire_strings():
    assert [r.value for r in CandidateReason] == ["same_key", "alias", "containment"]


# --- 输出形状 ---------------------------------------------------------------


def test_empty_and_single_inputs():
    assert find_duplicate_candidates([]) == ()
    assert find_duplicate_candidates(iter([])) == ()
    assert find_duplicate_candidates([NameEntry("a", "栈")]) == ()


def test_output_is_tuple_of_candidates_ordered_and_without_self_pairs():
    names = ["快速排序算法", "栈", "FIFO", "快速排序", "栈（Stack）", "先进先出(FIFO)", "STACK"]
    found = find_duplicate_candidates(entries(*names))
    assert isinstance(found, tuple)
    assert all(isinstance(c, DuplicateCandidate) for c in found)
    keys = [(c.left_id, c.right_id) for c in found]
    assert keys == sorted(keys)
    assert len(set(keys)) == len(keys)
    assert all(c.left_id < c.right_id for c in found)
    assert {(c.left_id, c.right_id, c.reason) for c in found} == {
        ("e0", "e3", CandidateReason.CONTAINMENT),
        ("e1", "e4", CandidateReason.SAME_KEY),
        ("e2", "e5", CandidateReason.ALIAS),
        ("e4", "e6", CandidateReason.ALIAS),
    }


def test_ids_ordered_by_code_point():
    items = [NameEntry("中", "栈"), NameEntry("b", "栈"), NameEntry("B", "栈")]
    found = find_duplicate_candidates(items)
    assert [(c.left_id, c.right_id) for c in found] == [("B", "b"), ("B", "中"), ("b", "中")]


def test_result_independent_of_input_order():
    names = [
        "栈", "栈（Stack）", "STACK", "堆栈（stack）", "快速排序", "快速排序算法", "二叉树",
        "平衡二叉树", "先进先出(FIFO)", "FIFO", "队列", "图", "图灵机", "C", "C++", "链表", "单链表",
    ]
    base = entries(*names)
    expected = find_duplicate_candidates(base)
    assert expected
    rng = random.Random(8)
    for _ in range(30):
        shuffled = base[:]
        rng.shuffle(shuffled)
        assert find_duplicate_candidates(shuffled) == expected


def test_every_pair_reported_at_most_once_even_if_multiple_reasons():
    names = ["栈（Stack）", "栈 (stack)", "Stack", "堆栈（Stack）"]
    found = find_duplicate_candidates(entries(*names))
    ids = [(c.left_id, c.right_id) for c in found]
    assert len(ids) == len(set(ids)) == len(list(itertools.combinations(names, 2)))


def test_accepts_any_iterable_including_generator():
    gen = (NameEntry(f"g{i}", n) for i, n in enumerate(["栈", "栈"]))
    assert len(find_duplicate_candidates(gen)) == 1


# --- 值对象 -----------------------------------------------------------------


def test_value_objects_are_frozen():
    n = normalize_name("栈")
    e = NameEntry("a", "栈")
    c = DuplicateCandidate("a", "b", CandidateReason.SAME_KEY, "栈")
    for obj, field in ((n, "key"), (e, "name"), (c, "reason")):
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(obj, field, "x")


def test_candidate_rejects_unordered_or_self_pair():
    with pytest.raises(ValueError):
        DuplicateCandidate("b", "a", CandidateReason.SAME_KEY, "栈")
    with pytest.raises(ValueError):
        DuplicateCandidate("a", "a", CandidateReason.SAME_KEY, "栈")
    with pytest.raises(TypeError):
        DuplicateCandidate("a", "b", "same_key", "栈")


def test_definition_not_in_repr():
    assert "秘密定义" not in repr(NameEntry("a", "栈", "秘密定义"))


# --- 纯函数 -----------------------------------------------------------------


def test_module_imports_only_pure_stdlib():
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    allowed = {"__future__", "collections", "dataclasses", "enum", "fractions", "typing", "unicodedata", "re"}
    assert imported <= allowed, imported - allowed


def test_inputs_not_mutated():
    items = entries("栈", "栈（Stack）")
    snapshot = list(items)
    find_duplicate_candidates(items)
    assert items == snapshot
