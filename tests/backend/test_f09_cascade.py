"""F09 级联删除与删除影响预览（ADR-092），通过服务层与假 store 验证。

覆盖的是**决定对错的那部分逻辑**：孤儿安全的闭包收敛规则。真实 Cypher（``CONTAINS`` 遍历、
批量删除与关系身份清理）在 ``tests/integration/test_f09_cascade.py`` 上对着真 Neo4j 跑；
这里用假 store 精确构造多父节点等边界，不连接任何数据库。

验收（``docs/tasks.md`` WIN/F09 级联条目）：

* 只沿 ``CONTAINS`` 递归；``PREREQUISITE`` 不产生级联（删前置知识不删依赖它的知识点）；
* 只有「原有 ``CONTAINS`` 父节点全部在待删集合里」的节点才被删，共享节点保留并给出原因；
* 预览与实际删除共用同一计划，报告里的数量就是实际删除的数量；
* 根节点不存在 → 404；``expected_revision`` 不符 → 409 且草稿不变；
* 预览是只读的：不写节点、不加草稿修订号。
"""

from __future__ import annotations

import copy
import uuid

import jsonschema
import pytest
import yaml
from pathlib import Path

from app.repositories import graph_edit, sqlite
from app.repositories.neo4j import GraphScope
from app.services.graph.delete_node_cascade import (
    delete_node_cascade,
    preview_deletion,
)

ROOT = Path(__file__).resolve().parents[2]
_SPEC = yaml.safe_load((ROOT / "src/contracts/api.v1.yaml").read_text(encoding="utf-8"))


def _rewrite(node):
    if isinstance(node, dict):
        return {k: (v.replace("#/components/schemas/", "#/$defs/") if k == "$ref" and isinstance(v, str)
                    else _rewrite(v)) for k, v in node.items()}
    if isinstance(node, list):
        return [_rewrite(item) for item in node]
    return node


_DEFS = _rewrite(copy.deepcopy(_SPEC["components"]["schemas"]))


def assert_schema(name: str, instance: object) -> None:
    schema = {"$ref": f"#/$defs/{name}", "$defs": _DEFS}
    jsonschema.validate(instance, schema)


# --- 假 store：只实现级联用到的仓储函数，按调用顺序分发 --------------------------------

class FakeTx:
    """按仓储函数标识分发到一个内存草稿图；记录每条语句的调用。"""

    def __init__(self, graph: "FakeGraph") -> None:
        self.graph = graph
        self.parameters: list[dict] = []

    def run(self, query: str, parameters=None):
        self.parameters.append(dict(parameters or {}))
        g = self.graph
        if query.startswith("\nMATCH (root:KnowledgePoint"):     # _TX_CONTAINS_REACHABLE
            return g.reachable()
        if query.startswith("\nUNWIND $kp_ids AS id\nMATCH (p:"):  # _TX_CONTAINS_PARENTS
            return g.parents()
        if query.startswith("\nUNWIND $kp_ids AS id\nMATCH (n:") and "RETURN n {" in query:
            return g.nodes_rows()                                # _TX_NODES_ANY_VISIBILITY
        if "DETACH DELETE n" in query and "CALL (rel_ids)" in query:
            return g.delete()                                    # _TX_DELETE_NODES_DRAFT
        if "count(DISTINCT r.rel_id) AS relations" in query:
            ids = list((parameters or {}).get("kp_ids") or [])
            if "NOT b.kp_id IN $kp_ids" in query:
                return [{"relations": g.external_relation_count(ids)}]   # _TX_COUNT_EXTERNAL_DRAFT_RELATIONS
            return [{"relations": g.internal_relation_count(ids)}]       # _TX_COUNT_INTERNAL_DRAFT_RELATIONS
        raise AssertionError(f"未预期的语句: {query[:80]!r}")


class FakeGraph:
    """内存草稿图：``nodes`` 为 kp_id → 属性，``edges`` 为 (from, to, type)。"""

    def __init__(self) -> None:
        self.nodes: dict[str, dict] = {}
        self.edges: list[tuple[str, str, str]] = []
        self.calls: list[str] = []

    # 构造
    def add(self, kp_id: str, name: str, revision: int = 1, visible: bool = True) -> "FakeGraph":
        self.nodes[kp_id] = {
            "kp_id": kp_id, "name": name, "revision": revision, "locked": False,
            "contrib_manual": visible, "contrib_tasks": [],
        }
        return self

    def contains(self, parent: str, child: str) -> "FakeGraph":
        self.edges.append((parent, child, "CONTAINS"))
        return self

    def prerequisite(self, before: str, after: str) -> "FakeGraph":
        self.edges.append((before, after, "PREREQUISITE"))
        return self

    # 仓储语句的实现（与 Cypher 语义一致）；edges 每项是 (parent, child, kind)
    def _children(self, parent: str) -> list[str]:
        return [child for frm, child, kind in self.edges if kind == "CONTAINS" and frm == parent]

    def _contains_parents(self, kp_id: str) -> list[str]:
        return [frm for frm, child, kind in self.edges if kind == "CONTAINS" and child == kp_id]

    def reachable(self) -> list[dict]:
        """沿 CONTAINS 的闭包 + 到根的最短深度。"""
        self.calls.append("reachable")
        out: list[dict] = []
        seen = {self.root}
        frontier = [(self.root, 0)]
        while frontier:
            node, depth = frontier.pop(0)
            for child in self._children(node):
                if child not in seen:
                    seen.add(child)
                    out.append({"kp_id": child, "depth": depth + 1})
                    frontier.append((child, depth + 1))
        return out

    def parents(self) -> list[dict]:
        self.calls.append("parents")
        out: list[dict] = []
        for kp_id, props in self.nodes.items():
            for parent in self._contains_parents(kp_id):
                if parent in self.nodes:
                    out.append({"kp_id": kp_id, "parent_id": parent, "parent_name": self.nodes[parent]["name"]})
        return out

    def nodes_rows(self) -> list[dict]:
        self.calls.append("nodes")
        return [{"p": dict(props)} for props in self.nodes.values()]

    def internal_relation_count(self, kp_ids: list[str]) -> int:
        """两端都在集合里的关系条数（去重）。"""
        self.calls.append("count_internal_relations")
        doomed = set(kp_ids)
        kinds = ("CONTAINS", "PREREQUISITE", "RELATED_TO", "EXAMPLE_OF")
        return sum(1 for frm, to, kind in self.edges if kind in kinds and frm in doomed and to in doomed)

    def external_relation_count(self, kp_ids: list[str]) -> int:
        """一端在集合里、另一端在集合外的关系条数（去重）。"""
        self.calls.append("count_external_relations")
        doomed = set(kp_ids)
        kinds = ("CONTAINS", "PREREQUISITE", "RELATED_TO", "EXAMPLE_OF")
        return sum(1 for frm, to, kind in self.edges
                   if kind in kinds and ((frm in doomed) != (to in doomed)))

    def delete(self) -> list[dict]:
        self.calls.append("delete")
        doomed = {kp_id for kp_id, props in self.nodes.items() if props.get("_doomed")}
        for kp_id in doomed:
            self.nodes.pop(kp_id, None)
        self.edges = [e for e in self.edges if e[0] not in doomed and e[1] not in doomed]
        return [{"deleted": len(doomed)}]

    # 计划阶段标记待删集合，删除语句据此生效（模拟同一事务内的读—写）
    root: str = ""


class FakeStore:
    """只暴露 ``transaction``；服务层的读与写都走这一个入口。"""

    def __init__(self, graph: FakeGraph) -> None:
        self.graph = graph
        self.transactions = 0

    def transaction(self, scope: GraphScope, work):
        assert scope.version_id == "draft"
        self.transactions += 1
        return work(FakeTx(self.graph))


# --- 夹具 -----------------------------------------------------------------------------

SECRET = "f09-cascade-test-signing-key-0123456789ab"
VALID_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA"


@pytest.fixture
def ctx(tmp_path):
    """一个真实的 SQLite（迁移过）+ 假图 store 组成的 EditContext。"""
    from app.repositories.accounts import insert_account
    from app.repositories.courses import add_member, create_course
    from app.services.graph.edit_node import EditContext

    url = f"sqlite:///{tmp_path / 'cascade.sqlite3'}"
    sqlite.migrate(url)
    teacher = insert_account(url, account_id=uuid.uuid4().hex, username="f09c-teacher",
                             password_hash=VALID_HASH, role="teacher")
    course = create_course(url, name="级联删除测试课", description=None, creator_id=teacher.id)
    add_member(url, course_id=course.id, user_id=teacher.id, role="teacher", added_by=teacher.id)

    graph = FakeGraph()
    graph.root = "root"
    store = FakeStore(graph)
    context = EditContext(sqlite_url=url, store=store, reader=None, lock_seconds=30, wait_seconds=1.0,
                          actor_id=teacher.id)
    return context, graph, url, course.id


def draft_revision(url: str, course_id: str) -> int:
    with sqlite.connect(url) as database:
        return int(database.execute("SELECT draft_revision FROM courses WHERE id = ?",
                                    (course_id,)).fetchone()[0])


# --- 闭包与孤儿安全 -------------------------------------------------------------------

def test_cascade_follows_contains_and_keeps_shared_child(ctx):
    """删「栈」带走它的子树，但保留仍挂在「链队列」下的「采」。"""
    context, graph, _, cid = ctx
    graph.add("root", "栈").add("n1", "顺序栈").add("n2", "链栈").add("shared", "采")
    graph.contains("root", "n1").contains("root", "n2")
    graph.contains("n1", "shared").contains("n2", "shared")   # shared 有两个父节点，都在子树内
    graph.contains("q", "shared")                              # 但还有一个父节点在子树外
    graph.add("q", "链队列")

    impact = preview_deletion(context, cid, "root")
    ids = [node.kp_id for node in impact.nodes]
    assert ids == ["root", "n1", "n2"], ids
    assert "shared" not in ids
    assert [node.kp_id for node in impact.retained] == ["shared"]
    assert impact.retained[0].retained_parents == ("链队列",)


def test_cascade_deletes_child_when_all_parents_are_doomed(ctx):
    """父节点全在待删集合里时，子节点跟着删（这是「后续节点」的常规情形）。"""
    context, graph, _, cid = ctx
    graph.add("root", "栈").add("n1", "顺序栈").add("leaf", "栈顶")
    graph.contains("root", "n1").contains("n1", "leaf")

    impact = preview_deletion(context, cid, "root")
    assert [n.kp_id for n in impact.nodes] == ["root", "n1", "leaf"]
    assert [n.depth for n in impact.nodes] == [0, 1, 2]
    assert impact.retained == ()


def test_prerequisite_does_not_cascade(ctx):
    """删前置知识不连带删除依赖它的知识点：PREREQUISITE 不是归属关系。"""
    context, graph, _, cid = ctx
    graph.add("root", "递归").add("after", "二叉树遍历")
    graph.prerequisite("root", "after")

    impact = preview_deletion(context, cid, "root")
    assert [n.kp_id for n in impact.nodes] == ["root"]
    assert impact.retained == ()


def test_node_with_parent_outside_subtree_is_never_cascaded(ctx):
    """自身是别处根节点的子节点时，不因为「可达」就被牵连。"""
    context, graph, _, cid = ctx
    graph.add("root", "栈").add("other", "队列").add("shared", "循环队列")
    graph.contains("root", "shared")
    graph.contains("other", "shared")

    impact = preview_deletion(context, cid, "root")
    assert [n.kp_id for n in impact.nodes] == ["root"]
    assert [n.kp_id for n in impact.retained] == ["shared"]
    assert impact.retained[0].retained_parents == ("队列",)


# --- 报告与预览的一致性 ---------------------------------------------------------------

def test_preview_reports_the_same_set_the_delete_removes(ctx):
    """预览集 = 实际删除集：共用同一个计划函数，不会出现「说删 3 个实际删 30 个」。"""
    context, graph, _, cid = ctx
    graph.add("root", "栈").add("n1", "顺序栈").add("leaf", "栈顶").add("keep", "采")
    graph.contains("root", "n1").contains("n1", "leaf").contains("other", "keep")
    graph.add("other", "链队列")

    preview = preview_deletion(context, cid, "root")
    expected = [n.kp_id for n in preview.nodes]

    for kp_id in expected:
        graph.nodes[kp_id]["_doomed"] = True
    impact = delete_node_cascade(context, cid, "root")

    assert [n.kp_id for n in impact.nodes] == expected
    assert "keep" in graph.nodes and "root" not in graph.nodes and "leaf" not in graph.nodes


def test_relation_count_counts_edges_incident_to_deleted_nodes(ctx):
    """与保留节点相连的关系也在删除范围内（否则会留下悬空边），报告里要算进去。"""
    context, graph, _, cid = ctx
    graph.add("root", "栈").add("n1", "顺序栈").add("keep", "采").add("other", "链队列")
    graph.contains("root", "n1").contains("root", "keep").contains("other", "keep")

    impact = preview_deletion(context, cid, "root")
    # root-n1、root-keep 会被删；other-keep 两端都保留，不算
    assert impact.relation_count == 2


def test_relation_count_does_not_double_count_internal_edges(ctx):
    """两端都在待删集合里的关系只算一次（逐节点汇总会重复计，必须扣掉）。"""
    context, graph, _, cid = ctx
    graph.add("root", "栈").add("n1", "顺序栈").add("n2", "链栈").add("out", "采").add("other", "链队列")
    graph.contains("root", "n1").contains("root", "n2").contains("n1", "n2")
    graph.contains("n1", "out").contains("other", "out")   # out 保留，只有 n1-out 会被删

    impact = preview_deletion(context, cid, "root")
    written = {e for e in graph.edges if e[0] in {"root", "n1", "n2"} or e[1] in {"root", "n1", "n2"}}
    # root-n1、root-n2、n1-n2、n1-out = 4（n1-n2 不能算两次）
    assert impact.relation_count == 4, (impact.relation_count, written)


def test_delete_removes_incident_edges_and_keeps_retained_subgraph(ctx):
    """实际删除后：待删节点消失、与它们相连的边消失、保留节点之间的边还在。"""
    context, graph, _, cid = ctx
    graph.add("root", "栈").add("n1", "顺序栈").add("keep", "采").add("other", "链队列")
    graph.contains("root", "n1").contains("root", "keep").contains("other", "keep")

    preview = preview_deletion(context, cid, "root")
    for kp_id in (n.kp_id for n in preview.nodes):
        graph.nodes[kp_id]["_doomed"] = True
    impact = delete_node_cascade(context, cid, "root")

    assert [n.kp_id for n in impact.nodes] == ["root", "n1"]
    assert set(graph.nodes) == {"keep", "other"}
    assert ("other", "keep", "CONTAINS") in graph.edges      # 保留子图的关系没被动
    assert not any("root" in (frm, to) or "n1" in (frm, to) for frm, to, _ in graph.edges)


def test_preview_is_readonly(ctx):
    """预览不加草稿修订号、不改动任何节点。"""
    context, graph, url, cid = ctx
    graph.add("root", "栈").add("n1", "顺序栈")
    graph.contains("root", "n1")
    before_revision = draft_revision(url, cid)
    before_nodes = copy.deepcopy(graph.nodes)

    preview_deletion(context, cid, "root")

    assert draft_revision(url, cid) == before_revision
    assert graph.nodes == before_nodes


# --- 错误路径 -------------------------------------------------------------------------

def test_missing_root_is_not_found(ctx):
    context, graph, url, cid = ctx
    from app.services.access import AccessDenied

    before = draft_revision(url, cid)
    with pytest.raises(AccessDenied):
        preview_deletion(context, cid, "nope")
    assert draft_revision(url, cid) == before


def test_stale_expected_revision_conflicts_without_writing(ctx):
    context, graph, url, cid = ctx
    graph.add("root", "栈", revision=3).add("n1", "顺序栈")
    graph.contains("root", "n1")
    from app.services.graph.edit_node import RevisionConflict

    with pytest.raises(RevisionConflict):
        delete_node_cascade(context, cid, "root", expected_revision=2)
    assert "root" in graph.nodes and "n1" in graph.nodes


def test_empty_kp_id_is_not_found(ctx):
    context, _, _, cid = ctx
    from app.services.access import AccessDenied

    with pytest.raises(AccessDenied):
        preview_deletion(context, cid, "   ")


# --- 契约一致性 -----------------------------------------------------------------------

def test_report_matches_the_contract_schema(ctx):
    """服务层返回的报告能通过契约 ``KnowledgePointDeletion`` 的校验。"""
    context, graph, _, cid = ctx
    graph.add("root", "栈").add("n1", "顺序栈").add("keep", "采").add("other", "链队列")
    graph.contains("root", "n1").contains("root", "keep").contains("other", "keep")

    impact = preview_deletion(context, cid, "root")
    payload = {
        "root_id": impact.root_id,
        "root_name": impact.root_name,
        "cascade": impact.cascade,
        "deleted_count": impact.deleted_count,
        "relation_count": impact.relation_count,
        "nodes": [{"id": n.kp_id, "name": n.name, "depth": n.depth} for n in impact.nodes],
        "retained": [{"id": n.kp_id, "name": n.name, "depth": n.depth,
                      "retained_parents": list(n.retained_parents)} for n in impact.retained],
    }
    assert_schema("KnowledgePointDeletion", payload)
    assert payload["deleted_count"] == len(payload["nodes"])
    assert payload["retained"][0]["retained_parents"] == ["链队列"]


def test_depth_is_shortest_contains_distance(ctx):
    """同一节点经两条路径可达时取最短距离，报告的 depth 才可解释。"""
    context, graph, _, cid = ctx
    graph.add("root", "栈").add("a", "A").add("b", "B").add("c", "C")
    graph.contains("root", "a").contains("a", "b").contains("b", "c").contains("root", "c")

    impact = preview_deletion(context, cid, "root")
    depth = {n.kp_id: n.depth for n in impact.nodes}
    assert depth["c"] == 1, depth
    assert depth["b"] == 2, depth
