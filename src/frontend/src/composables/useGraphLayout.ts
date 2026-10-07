import { ref, shallowRef, watch, type Ref } from 'vue'
import { computeLayout, type DagreEngine, type LayoutEdge, type LayoutNode, type Positions } from '../graph/chapterLayout'

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
  error: Ref<unknown>
}

export function useGraphLayout(source: () => LayoutSource | null, engine?: DagreEngine): UseGraphLayout {
  const positions = shallowRef<Positions | null>(null)
  const error = ref<unknown>(null)
  let seq = 0

  watch(
    source,
    async (src) => {
      const mine = ++seq
      positions.value = null
      error.value = null
      if (src === null) return
      try {
        const result = await computeLayout(src.nodes, src.edges, 'chapter', src.chapterOrder, {}, engine)
        if (mine === seq) positions.value = result
      } catch (cause) {
        if (mine === seq) error.value = cause
      }
    },
    { immediate: true },
  )

  return { positions, error }
}
