/**
 * 标签排布（设计规格 §4 第 1 层「标签分级」）。纯函数，不依赖 G6。
 *
 * 缩小时标签不能全部画出来：按优先级从高到低，在屏幕坐标里估算每个标签的占位，
 * 与已放置的标签重叠、或落在工具栏/图例/小地图等浮层下面的就不显示。
 * 节点本身不隐藏；隐藏的标签可经 tooltip、列表、搜索找到。
 *
 * 强制显示只留给「被预览/选中的那个节点」（`forced`）。优先级分数是累加的（章节成员 +950，再加推荐项 +300），
 * 绝不能用分数阈值判断强制，否则章节内的推荐项会意外越线、造成拥挤。
 */
import { LABEL_BASE_PX } from './scale'

/** [x1, y1, x2, y2]，与候选标签使用同一套屏幕坐标 */
export type Box = readonly [number, number, number, number]

export interface LabelCandidate {
  /** 元素 id（调用方自定，如 `kp:abc`） */
  id: string
  /** 节点中心在画布视口里的位置（像素） */
  x: number
  y: number
  /** 标签文字（含推荐序号前缀「1. 」） */
  text: string
  /** 优先级分数，越大越先排 */
  score: number
  /** 被预览/选中的节点：即使与别的标签重叠也显示 */
  forced: boolean
}

export interface LabelPlanInput {
  candidates: readonly LabelCandidate[]
  viewport: { width: number; height: number }
  /** 当前画布缩放 */
  zoom: number
  /** 标签放大系数（`labelScale`） */
  labelK: number
  /** 节点放大系数（`scaleFloors().nodeK`） */
  nodeK: number
  /** 浮层的屏幕包围盒（已含外扩边距） */
  obstacles: readonly Box[]
  /** 量文字宽度：fontPx 为标签在屏幕上的字号。必须用真实字体量，不能按字符数估算 */
  measure: (text: string, fontPx: number) => number
}

/** 视口外多远以内仍参与排布（拖动时标签不会在边缘突然出现） */
const MARGIN = 24
const WRAP_BASE_PX = 112

function overlaps(a: Box, b: Box): boolean {
  return a[0] < b[2] && a[2] > b[0] && a[1] < b[3] && a[3] > b[1]
}

/** 返回允许显示标签的元素 id 集合 */
export function planLabels(input: LabelPlanInput): Set<string> {
  const { viewport, zoom, labelK, nodeK, obstacles, measure } = input
  const shown = new Set<string>()
  if (!(zoom > 0)) return shown
  const fontPx = LABEL_BASE_PX * labelK * zoom
  const wrap = WRAP_BASE_PX * labelK * zoom
  const placed: Box[] = []
  // 分数相同按 id 排，保证结果与输入顺序无关
  const ordered = [...input.candidates].sort((a, b) => b.score - a.score || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0))
  for (const c of ordered) {
    if (c.x < -MARGIN || c.y < -MARGIN || c.x > viewport.width + MARGIN || c.y > viewport.height + MARGIN) continue
    const natural = measure(c.text, fontPx)
    const width = Math.min(natural, wrap) + 10
    const lines = Math.min(2, Math.max(1, Math.ceil(natural / Math.max(wrap, 1))))
    const height = lines * fontPx * 1.3 + 4
    const top = c.y + 18 * nodeK * zoom + 4 * labelK * zoom
    const box: Box = [c.x - width / 2 - 3, top, c.x + width / 2 + 3, top + height + 3]
    // 落在浮层下面的标签看不见：对被预览/选中的节点也一样
    if (obstacles.some((o) => overlaps(box, o))) continue
    if (c.forced || !placed.some((p) => overlaps(box, p))) {
      placed.push(box)
      shown.add(c.id)
    }
  }
  return shown
}
