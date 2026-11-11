import { computed, type Ref } from 'vue'
import type { MasteryStatus } from '../api/progress'
import { kpIdFromElementId, nodeElementId } from '../graph/adapter'
import { applyFocusStates } from '../graph/focusStates'
import type { GraphCanvasData } from '../graph/lifecycle'
import type { Chapter } from './useGraphFilters'
import { useGraphLayout } from './useGraphLayout'
import { MASTERY_LABELS } from './useLearning'
import type { UseLocalView } from './useLocalView'

interface StudentGraphPresentationOptions {
  graph: Readonly<Ref<GraphCanvasData | null>>
  chapters: Readonly<Ref<readonly Chapter[]>>
  learningGraph: Readonly<Ref<GraphCanvasData | null>>
  localView: Pick<UseLocalView, 'apply'>
  highlightId: Readonly<Ref<string | null>>
  previewId: Readonly<Ref<string | null>>
  chapterId: Readonly<Ref<string | null>>
  chapterKpIds: Readonly<Ref<string[]>>
  statusOf(kpId: string): MasteryStatus
}

/** Derived canvas data, chapter positions, node preview and mastery summary. */
export function useStudentGraphPresentation({
  graph, chapters, learningGraph, localView, highlightId, previewId, chapterId, chapterKpIds, statusOf,
}: StudentGraphPresentationOptions) {
  // ---------------------------------------------------------------- 画布数据：学习状态 → 局部视图 → 聚焦状态
  /** 预览/选中由 `highlightId` 决定；筛选层与学习路径带来的 `selected` 要去掉，否则预览与详情会同时出现两个外环 */
  function withoutSelected(g: GraphCanvasData): GraphCanvasData {
    return {
      nodes: g.nodes.map((n) => (n.states?.includes('selected') ? { ...n, states: n.states.filter((s) => s !== 'selected') } : n)),
      edges: g.edges,
    }
  }
  const canvasGraph = computed<GraphCanvasData | null>(() => {
    const base = localView.apply(learningGraph.value)
    if (base === null) return null
    const hl = highlightId.value
    const scope = chapterId.value === null ? null : new Set(chapterKpIds.value.map(nodeElementId))
    return applyFocusStates(withoutSelected(base), {
      selectedId: hl === null ? null : nodeElementId(hl),
      matchedIds: new Set(),
      chapterIds: scope,
      fade: 'standard',
    })
  })

  // ---------------------------------------------------------------- 章节分区布局（对完整已发布图算一次，筛选只显示子集）
  const layoutSource = computed(() => {
    const g = graph.value
    if (g === null) return null
    return {
      nodes: g.nodes.map((n) => ({ id: n.data.kpId, chapter: n.data.chapterId })),
      edges: g.edges.map((e) => ({
        id: e.data.relationId,
        source: kpIdFromElementId(e.source),
        target: kpIdFromElementId(e.target),
        type: e.data.type,
      })),
      chapterOrder: [...chapters.value].sort((a, b) => a.order - b.order || (a.id < b.id ? -1 : 1)).map((c) => c.id),
    }
  })
  const { positions } = useGraphLayout(() => layoutSource.value)

  // ---------------------------------------------------------------- 预览卡
  const preview = computed(() => {
    const id = previewId.value
    const g = graph.value
    const node = id === null || g === null ? undefined : g.nodes.find((n) => n.data.kpId === id)
    if (id === null || g === null || node === undefined) return null
    const el = nodeElementId(id)
    const status = statusOf(id)
    const mastery: 'mastered' | 'learning' | 'unknown' = status === 'mastered' ? 'mastered' : status === 'learning' ? 'learning' : 'unknown'
    return {
      id,
      name: node.data.name,
      type: node.data.type,
      chapter: chapters.value.find((c) => c.id === node.data.chapterId)?.title ?? '未分章',
      mastery,
      masteryText: MASTERY_LABELS[status],
      prerequisites: g.edges.filter((e) => e.data.type === 'PREREQUISITE' && e.target === el).length,
      unlocks: g.edges.filter((e) => e.data.type === 'PREREQUISITE' && e.source === el).length,
    }
  })

  // ---------------------------------------------------------------- 进度（左面板概览）
  const progress = computed(() => {
    const total = graph.value?.nodes.length ?? 0
    let done = 0
    let learning = 0
    for (const node of graph.value?.nodes ?? []) {
      const s = statusOf(node.data.kpId)
      if (s === 'mastered') done += 1
      else if (s === 'learning') learning += 1
    }
    return { total, done, learning, percent: total === 0 ? 0 : Math.round((done / total) * 100) }
  })

  return { canvasGraph, positions, preview, progress }
}
