/**
 * 画布主题（暖纸墨色）。
 *
 * G6 在 canvas/WebGL 上绘制，不继承 CSS，所以画布颜色必须在**建图时**从 `:root` 的 CSS 变量读一次，
 * 再作为普通值传进 G6；不能在每个节点/边的渲染回调里重复调用 `getComputedStyle`。
 *
 * 这里只放颜色：关系类型、掌握状态、审核状态、选中与推荐仍各自一种颜色，保持原有可区分性。
 * 边（关系类型）的颜色另有唯一来源 `adapter.ts` 的 `RELATION_STYLES`（图例与画布共用）；
 * `--graph-edge-*` 镜像那四个值，改色时两处一起改。
 * 变量缺失（非浏览器环境、测试替身）时退回下列字面量，与 `styles.css` 的 `:root` 保持一致。
 */
import type { RelationType } from './adapter'

export interface GraphTheme {
  /** 画布底色 */
  canvas: string
  /** 默认节点（未带状态时） */
  node: { fill: string; stroke: string; label: string }
  /** 关系类型 → 边颜色，键与 `RelationType` 一致 */
  relation: Record<RelationType, string>
  /** 元素状态 → 颜色；键与 `CanvasElementState` 一致 */
  state: {
    rejectedStroke: string
    lowConfidenceStroke: string
    masteredFill: string
    masteredStroke: string
    learningFill: string
    learningStroke: string
    notStartedFill: string
    notStartedStroke: string
    recommendedStroke: string
    recommendedHalo: string
    selectedStroke: string
    selectedHalo: string
  }
}

/** 与 `:root` 默认值一致的兜底色（非浏览器环境或变量未定义时使用） */
export const FALLBACK_GRAPH_THEME: GraphTheme = Object.freeze({
  canvas: '#fffdfa',
  node: { fill: '#fffdfa', stroke: '#c9bfb1', label: '#23201c' },
  relation: {
    CONTAINS: '#8a8175',
    PREREQUISITE: '#9c4a34',
    RELATED_TO: '#3f6157',
    EXAMPLE_OF: '#b1791f',
  },
  state: {
    rejectedStroke: '#c9bfb1',
    lowConfidenceStroke: '#8a6a1f',
    masteredFill: '#eef3ef',
    masteredStroke: '#3f6157',
    learningFill: '#fdf7e8',
    learningStroke: '#b1791f',
    notStartedFill: '#fffdfa',
    notStartedStroke: '#c9bfb1',
    recommendedStroke: '#6b4a3a',
    recommendedHalo: '#9c4a34',
    selectedStroke: '#7f3a27',
    selectedHalo: '#9c4a34',
  },
})

/** 画布主题需要读取的 CSS 变量名（顺序即 `toGraphTheme` 的取值顺序） */
export const GRAPH_THEME_VARIABLES = [
  '--color-surface',
  '--color-border-strong',
  '--color-text',
  '--graph-edge-contains',
  '--graph-edge-prerequisite',
  '--graph-edge-related',
  '--graph-edge-example',
  '--graph-state-rejected',
  '--graph-state-low-confidence',
  '--graph-state-mastered-fill',
  '--graph-state-mastered-stroke',
  '--graph-state-learning-fill',
  '--graph-state-learning-stroke',
  '--graph-state-not-started-fill',
  '--graph-state-not-started-stroke',
  '--graph-state-recommended',
  '--graph-state-recommended-halo',
  '--graph-state-selected',
  '--graph-state-selected-halo',
] as const

/** 从一次读到的变量表组装主题；空值一律退回兜底色 */
export function toGraphTheme(values: ReadonlyMap<string, string>): GraphTheme {
  const read = (name: string, fallback: string): string => values.get(name)?.trim() || fallback
  return {
    canvas: read('--color-surface', FALLBACK_GRAPH_THEME.canvas),
    node: {
      fill: read('--color-surface', FALLBACK_GRAPH_THEME.node.fill),
      stroke: read('--color-border-strong', FALLBACK_GRAPH_THEME.node.stroke),
      label: read('--color-text', FALLBACK_GRAPH_THEME.node.label),
    },
    relation: {
      CONTAINS: read('--graph-edge-contains', FALLBACK_GRAPH_THEME.relation.CONTAINS),
      PREREQUISITE: read('--graph-edge-prerequisite', FALLBACK_GRAPH_THEME.relation.PREREQUISITE),
      RELATED_TO: read('--graph-edge-related', FALLBACK_GRAPH_THEME.relation.RELATED_TO),
      EXAMPLE_OF: read('--graph-edge-example', FALLBACK_GRAPH_THEME.relation.EXAMPLE_OF),
    },
    state: {
      rejectedStroke: read('--graph-state-rejected', FALLBACK_GRAPH_THEME.state.rejectedStroke),
      lowConfidenceStroke: read('--graph-state-low-confidence', FALLBACK_GRAPH_THEME.state.lowConfidenceStroke),
      masteredFill: read('--graph-state-mastered-fill', FALLBACK_GRAPH_THEME.state.masteredFill),
      masteredStroke: read('--graph-state-mastered-stroke', FALLBACK_GRAPH_THEME.state.masteredStroke),
      learningFill: read('--graph-state-learning-fill', FALLBACK_GRAPH_THEME.state.learningFill),
      learningStroke: read('--graph-state-learning-stroke', FALLBACK_GRAPH_THEME.state.learningStroke),
      notStartedFill: read('--graph-state-not-started-fill', FALLBACK_GRAPH_THEME.state.notStartedFill),
      notStartedStroke: read('--graph-state-not-started-stroke', FALLBACK_GRAPH_THEME.state.notStartedStroke),
      recommendedStroke: read('--graph-state-recommended', FALLBACK_GRAPH_THEME.state.recommendedStroke),
      recommendedHalo: read('--graph-state-recommended-halo', FALLBACK_GRAPH_THEME.state.recommendedHalo),
      selectedStroke: read('--graph-state-selected', FALLBACK_GRAPH_THEME.state.selectedStroke),
      selectedHalo: read('--graph-state-selected-halo', FALLBACK_GRAPH_THEME.state.selectedHalo),
    },
  }
}

/**
 * 读取元素上生效的主题变量。**只在建图/重建时调用一次**，不要放进渲染循环。
 * 传入 `null`（未挂载、测试环境）时返回兜底主题。
 */
export function readGraphTheme(element: Element | null): GraphTheme {
  if (element === null || typeof getComputedStyle !== 'function') return FALLBACK_GRAPH_THEME
  const computed = getComputedStyle(element)
  const values = new Map<string, string>()
  for (const name of GRAPH_THEME_VARIABLES) values.set(name, computed.getPropertyValue(name))
  return toGraphTheme(values)
}
