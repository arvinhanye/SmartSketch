import { ref, shallowRef, watch, type Ref } from 'vue'
import { computeLayout, prefersRadial, radialEngine, type DagreEngine, type LayoutEdge, type LayoutNode, type Positions } from '../graph/chapterLayout'

/**
 * 章节分区布局（规格 §4.1）：对**完整已发布图**异步计算一次位置，筛选与局部视图只显示子集，位置不跟着抖动。
 * 源变化时重新计算；期间又变化时丢弃过期结果（`seq` 保护）。
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
}

export function useGraphLayout(source: () => LayoutSource | null, engine?: DagreEngine, withRadial = false): UseGraphLayout {
  const positions = shallowRef<Positions | null>(null)
  const radialPositions = shallowRef<Positions | null>(null)
  const recommended = ref<'hierarchical' | 'radial' | null>(null)
  const error = ref<unknown>(null)
  let seq = 0

  watch(
    source,
    async (src) => {
      const mine = ++seq
      positions.value = null
      radialPositions.value = null
      recommended.value = null
      error.value = null
      if (src === null) return
      try {
        const result = await computeLayout(src.nodes, src.edges, 'chapter', src.chapterOrder, {}, engine)
        const radial = withRadial ? await computeLayout(src.nodes, src.edges, 'chapter', src.chapterOrder, {}, radialEngine) : null
        if (mine !== seq) return
        // 两份位置与推荐同一时刻生效，页面不会看到只有一半的状态
        radialPositions.value = radial
        recommended.value = withRadial ? (prefersRadial(result) ? 'radial' : 'hierarchical') : null
        positions.value = result
      } catch (cause) {
        if (mine === seq) error.value = cause
      }
    },
    { immediate: true },
  )

  return { positions, radialPositions, recommended, error }
}
