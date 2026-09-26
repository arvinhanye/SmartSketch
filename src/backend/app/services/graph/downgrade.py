"""ADR-009 自动候选成环降级（F13）：纯函数，无 I/O。

输入是「当前可见草稿 + 本任务候选」中参与环检测的 ``PREREQUISITE`` 边（调用方已排除 ``rejected``），
每条带置信度与是否可降级（``source = ai`` 且未经教师确认）。算法（specs/course-knowledge-graph.md
「降级算法」第 2～5 步）：

1. F05 ``find_cycle`` 找一个环（确定性：只取决于边集合）；
2. 在环上的可降级边里选置信度最低者，并列取 ``rel_id`` 字典序最小者；
3. 该边移出参与集合，记为降级（附触发它的闭合环路）；
4. 重复直到无环。环上没有可降级边 → ``UnresolvableCycleError``（DAG-10，任务以 ``CYCLE_DETECTED`` 失败）。

每轮只降级一条，不承诺全局最少。同一顶点对最多一条 ``PREREQUISITE``（``rel_id`` 由端点派生）；若调用方
传入同一顶点对的多条边，环上取 ``rel_id`` 最小者代表该步，其余在后续轮次中处理。
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from app.repositories.graph_relations import PrerequisiteEdge
from app.services.graph.dag import find_cycle

__all__ = ["Downgrade", "UnresolvableCycleError", "plan_downgrades"]


@dataclass(frozen=True)
class Downgrade:
    rel_id: str
    from_id: str
    to_id: str
    cycle: tuple[str, ...]


class UnresolvableCycleError(Exception):
    code = "CYCLE_DETECTED"

    def __init__(self, cycle: tuple[str, ...]) -> None:
        super().__init__(self.code)
        self.cycle = cycle


def plan_downgrades(nodes: Iterable[str], edges: Sequence[PrerequisiteEdge]) -> tuple[Downgrade, ...]:
    known = set(nodes)
    active = {edge.rel_id: edge for edge in edges}
    if len(active) != len(edges):
        raise ValueError("duplicate rel_id in edges")
    plan: list[Downgrade] = []
    while True:
        by_pair: dict[tuple[str, str], PrerequisiteEdge] = {}
        for edge in sorted(active.values(), key=lambda e: e.rel_id):
            by_pair.setdefault((edge.from_id, edge.to_id), edge)
        cycle = find_cycle(known, by_pair)
        if cycle is None:
            return tuple(plan)
        on_cycle = [by_pair[(cycle[i], cycle[i + 1])] for i in range(len(cycle) - 1)]
        choices = [edge for edge in on_cycle if edge.downgradable]
        if not choices:
            raise UnresolvableCycleError(cycle)
        victim = min(choices, key=lambda edge: (edge.confidence, edge.rel_id))
        plan.append(Downgrade(victim.rel_id, victim.from_id, victim.to_id, cycle))
        del active[victim.rel_id]
