import { computed, ref, type ComputedRef, type Ref } from 'vue'
import { kpIdFromElementId } from '../graph/adapter'
import type { GraphCanvasData } from '../graph/lifecycle'

/**
 * 只看相邻（局部视图，规格 §4 第 3 层）：用户主动开启，只显示某知识点及 1 或 2 跳邻居，其余**隐藏**（不是淡化）。
 * 与类型/关系筛选叠加时按交集显示；隐藏状态在页面顶部提示条里可见、可恢复。
 */
export interface LocalView {
  /** 中心知识点（契约 ID） */
  id: string
  hops: 1 | 2
}

/** 中心点及 `hops` 跳以内的邻居（不分关系方向），只在传入的图里找 */
export function localKpIds(graph: GraphCanvasData, view: LocalView): Set<string> {
  const kpOf = new Map(graph.nodes.map((n) => [n.id, n.data.kpId]))
  const reach = new Set<string>([view.id])
  let frontier = [view.id]
  for (let hop = 0; hop < view.hops; hop += 1) {
    const next: string[] = []
    for (const e of graph.edges) {
      const a = kpOf.get(e.source) ?? kpIdFromElementId(e.source)
      const b = kpOf.get(e.target) ?? kpIdFromElementId(e.target)
      for (const [from, to] of [[a, b], [b, a]] as const) {
        if (frontier.includes(from) && !reach.has(to)) {
          reach.add(to)
          next.push(to)
        }
      }
    }
    frontier = next
  }
  return reach
}

/** 只保留在 `ids` 里的节点，以及两端都保留的边；不修改输入 */
export function restrictGraph(graph: GraphCanvasData, ids: ReadonlySet<string>): GraphCanvasData {
  const nodes = graph.nodes.filter((n) => ids.has(n.data.kpId))
  const present = new Set(nodes.map((n) => n.id))
  return { nodes, edges: graph.edges.filter((e) => present.has(e.source) && present.has(e.target)) }
}

export interface UseLocalView {
  view: Ref<LocalView | null>
  /** 开启/关闭某知识点的局部视图（再次对同一知识点调用即关闭） */
  toggle(kpId: string): void
  setHops(hops: 1 | 2): void
  clear(): void
  /** 局部视图可见的知识点；未开启为 null */
  ids: ComputedRef<Set<string> | null>
  /** 应用局部视图；未开启时原样返回 */
  apply(graph: GraphCanvasData | null): GraphCanvasData | null
}

/** `source` 是已按筛选得到的可见图：局部范围在它里面找，所以与筛选叠加时取交集 */
export function useLocalView(source: () => GraphCanvasData | null): UseLocalView {
  const view = ref<LocalView | null>(null)
  const ids = computed(() => {
    const g = source()
    return view.value === null || g === null ? null : localKpIds(g, view.value)
  })
  return {
    view,
    toggle(kpId) {
      view.value = view.value?.id === kpId ? null : { id: kpId, hops: 1 }
    },
    setHops(hops) {
      if (view.value !== null) view.value = { ...view.value, hops }
    },
    clear() {
      view.value = null
    },
    ids,
    apply(graph) {
      return graph === null || ids.value === null ? graph : restrictGraph(graph, ids.value)
    },
  }
}
