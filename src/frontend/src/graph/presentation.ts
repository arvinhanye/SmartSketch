import type { NodeBadgeStyleProps } from '@antv/g6'
import type { G6EdgeData, G6EdgeStyle, G6NodeData } from './adapter'
import { GRAPH_COLORS } from './theme'
import { NO_FLOORS, type ScaleFloors } from './scale'

/**
 * 展示数据（UI-GRAPH-PILOT-01）：G6 的样式回调只能读元素自己的 `data`，所以把"当前缩放档位、
 * 标签是否显示、掌握角标"这些随视口变化的量写进 `data`，由 `buildGraphOptions` 的回调读取。
 * 纯函数，不修改输入，不依赖 G6。
 */

export interface ViewState {
  /** 标签放大系数（缩小时让标签在屏幕上保持约 13px） */
  labelK: number
  /** 节点、线、箭头的屏幕下限 */
  floors: ScaleFloors
  /** 允许显示标签的节点元素 id；null 表示尚未排布（全部显示） */
  labelShown: ReadonlySet<string> | null
}

export const INITIAL_VIEW: Readonly<ViewState> = Object.freeze({ labelK: 1, floors: NO_FLOORS, labelShown: null })

export type MasteryKind = 'mastered' | 'learning' | 'unknown'

export function masteryOfStates(states: readonly string[] | undefined): MasteryKind {
  if (states?.includes('mastered')) return 'mastered'
  if (states?.includes('learning')) return 'learning'
  return 'unknown'
}

export function decorateNodeData(
  id: string,
  data: G6NodeData,
  states: readonly string[] | undefined,
  view: ViewState,
): G6NodeData {
  return {
    ...data,
    k: view.labelK,
    nk: view.floors.nodeK,
    lw: view.floors.lwMin,
    labelOn: view.labelShown === null ? true : view.labelShown.has(id),
    mastery: masteryOfStates(states),
  }
}

export function decorateEdge(
  edge: { data: G6EdgeData; style: G6EdgeStyle; states?: readonly string[] },
  cross: boolean,
  view: ViewState,
): { data: G6EdgeData; style: G6EdgeStyle } {
  const active = edge.states?.includes('active') ?? false
  const emph = active || (edge.states?.includes('scoped') ?? false)
  const lwMin = view.floors.lwMin
  return {
    data: { ...edge.data, lw: lwMin, ak: view.floors.arrowK, cross, emph, showLabel: active },
    style: {
      ...edge.style,
      lineDash: [...edge.style.lineDash],
      lineWidth: Math.max(cross && !emph ? 1 : edge.style.lineWidth, lwMin),
      labelText: active ? edge.style.labelText : '',
    },
  }
}

export function chapterOfNodes(
  nodes: ReadonlyArray<{ id: string; data: { chapterId: string | null } }>,
): Map<string, string | null> {
  return new Map(nodes.map((n) => [n.id, n.data.chapterId]))
}

/** 掌握角标：已掌握 ✓、学习中 ◐；未学习没有角标（详情、预览卡、列表用文字「未学习」） */
export function badgesFor(mastery: MasteryKind | undefined, nodeK: number): NodeBadgeStyleProps[] {
  if (mastery === 'mastered') {
    return [{ text: '✓', placement: 'right-top', fill: '#FFFFFF', backgroundFill: GRAPH_COLORS.ok, fontSize: 11 * nodeK, fontWeight: 700, padding: [1 * nodeK, 4 * nodeK] }]
  }
  if (mastery === 'learning') {
    return [{ text: '◐', placement: 'right-top', fill: '#FFFFFF', backgroundFill: GRAPH_COLORS.warn, fontSize: 11 * nodeK, padding: [1 * nodeK, 4 * nodeK] }]
  }
  return []
}

/** 节点标签：推荐项前加序号「1. 」（L14），其余为名称 */
export function nodeLabel(data: Pick<G6NodeData, 'name' | 'pathOrder'>): string {
  return data.pathOrder === undefined ? data.name : `${data.pathOrder}. ${data.name}`
}

/** 掌握状态的文字（预览卡、tooltip、列表）：颜色与角标之外必须有文字；与 `useLearning.MASTERY_LABELS` 一致（有测试守着） */
export const MASTERY_TEXT: Readonly<Record<MasteryKind, string>> = Object.freeze({
  mastered: '已掌握',
  learning: '学习中',
  unknown: '未学习',
})
