import { ref, shallowRef, watch, type Ref } from 'vue'
import { computeLayout, prefersRadial, radialEngine, type DagreEngine, type LayoutEdge, type LayoutNode, type Positions } from '../graph/chapterLayout'

/**
 * 章节分区布局（规格 §4.1）：对**完整已发布图**异步计算一次位置，筛选与局部视图只显示子集，位置不跟着抖动。
 * 源变化时重新计算；期间又变化时丢弃过期结果（`seq` 保护）。`stable` 模式下只改关系不重新计算，见 `GraphLayoutOptions`。
 */
export interface LayoutSource {
  nodes: LayoutNode[]
  edges: LayoutEdge[]
  /** 章节顺序（章节 id，按目录 order） */
  chapterOrder: string[]
}

export interface UseGraphLayout {
  /** 位置；源未到或正在重算时为 null */
  positions: Ref<Positions | null>
  /** 径向布局的位置（只在 `withRadial` 时计算）；与 `positions` 同步更新 */
  radialPositions: Ref<Positions | null>
  /** 层次布局被拉成长条时推荐径向（`withRadial` 且位置已就绪才有值） */
  recommended: Ref<'hierarchical' | 'radial' | null>
  error: Ref<unknown>
  /** `stable` 模式下：位置是按早先的关系算的，现在关系已经变了（可用 `relayout()` 重新排布）；否则恒为 false */
  stale: Ref<boolean>
  /** 按当前的知识点与关系重新计算位置 */
  relayout(): void
}

export interface GraphLayoutOptions {
  /**
   * 位置稳定（UI-GRAPH-STABLE-03，教师图谱页）：只增删关系、或删掉知识点时沿用已有位置，不重新计算——
   * 教师刚连完一条线，节点不应该挪地方，画布也不必整张重建。出现新知识点、知识点换了章节或章节顺序变了才重新计算。
   * 缺省关闭：源一变就重新计算（学生页只读已发布版本，换版本本来就是另一张图）。
   */
  stable?: boolean
}

const edgeKey = (edges: readonly LayoutEdge[]): string => edges.map((e) => `${e.source}>${e.type}>${e.target}`).sort().join('|')

export function useGraphLayout(source: () => LayoutSource | null, engine?: DagreEngine, withRadial = false, options: GraphLayoutOptions = {}): UseGraphLayout {
  const positions = shallowRef<Positions | null>(null)
  const radialPositions = shallowRef<Positions | null>(null)
  const recommended = ref<'hierarchical' | 'radial' | null>(null)
  const error = ref<unknown>(null)
  const stale = ref(false)
  let seq = 0
  /** 当前位置是按哪些知识点（及其章节）、哪个章节顺序、哪些关系算出来的；没有可沿用的位置时为 null */
  let laid: { chapters: Map<string, string | null>; order: string; edges: string } | null = null

  /** 已有位置还能不能接着用：没有新知识点，知识点没换章节，章节顺序没变 */
  function reusable(src: LayoutSource): boolean {
    if (options.stable !== true || laid === null || positions.value === null) return false
    if (src.chapterOrder.join('|') !== laid.order) return false
    return src.nodes.every((node) => laid!.chapters.has(node.id) && laid!.chapters.get(node.id) === (node.chapter ?? null))
  }

  async function compute(src: LayoutSource | null): Promise<void> {
    const mine = ++seq
    positions.value = null
    radialPositions.value = null
    recommended.value = null
    error.value = null
    stale.value = false
    laid = null
    if (src === null) return
    try {
      const result = await computeLayout(src.nodes, src.edges, 'chapter', src.chapterOrder, {}, engine)
      const radial = withRadial ? await computeLayout(src.nodes, src.edges, 'chapter', src.chapterOrder, {}, radialEngine) : null
      if (mine !== seq) return
      // 两份位置与推荐同一时刻生效，页面不会看到只有一半的状态
      radialPositions.value = radial
      recommended.value = withRadial ? (prefersRadial(result) ? 'radial' : 'hierarchical') : null
      laid = { chapters: new Map(src.nodes.map((n) => [n.id, n.chapter ?? null])), order: src.chapterOrder.join('|'), edges: edgeKey(src.edges) }
      positions.value = result
    } catch (cause) {
      if (mine === seq) error.value = cause
    }
  }

  watch(
    source,
    (src) => {
      if (src !== null && reusable(src)) {
        stale.value = edgeKey(src.edges) !== laid!.edges
        return
      }
      void compute(src)
    },
    { immediate: true },
  )

  return { positions, radialPositions, recommended, error, stale, relayout: () => void compute(source()) }
}
