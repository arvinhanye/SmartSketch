/**
 * 范围适应（设计规格 §4.2）。纯函数，不依赖 G6。
 *
 * 把一组节点整体放进视口：先按包围盒算缩放，再算出「包围盒中心应落在视口哪个位置」——
 * 中心取在「未被搜索栏、右侧工具、底部折叠条和小地图占用的区域」的中心。
 * 章节跳转展示的是整章范围而不是一个点；局部视图、类型筛选下的「适应画布」也只按可见节点计算。
 */
import type { Box } from './labelPlan'

export interface FitPads {
  left: number
  right: number
  top: number
  bottom: number
}

export interface FitInput {
  /** 节点中心（画布坐标） */
  points: ReadonlyArray<readonly [number, number]>
  viewport: { width: number; height: number }
  pads: FitPads
  /** 节点半径（含放大系数） */
  nodeRadius: number
  /** 包围盒底部额外留给标签的高度 */
  bottomExtra: number
  minZoom?: number
  maxZoom?: number
}

export interface FitResult {
  zoom: number
  /** 包围盒中心（画布坐标） */
  center: [number, number]
  /** 适应后该中心应落在的视口位置（像素） */
  target: [number, number]
}

export const DEFAULT_PADS: Readonly<FitPads> = Object.freeze({ left: 56, right: 96, top: 104, bottom: 96 })

export function computeFit(input: FitInput): FitResult | null {
  const { points, viewport, pads, nodeRadius, bottomExtra } = input
  if (points.length === 0) return null
  const minZoom = input.minZoom ?? 0.2
  const maxZoom = input.maxZoom ?? 1.2
  const xs = points.map((p) => p[0])
  const ys = points.map((p) => p[1])
  const minX = Math.min(...xs) - nodeRadius
  const maxX = Math.max(...xs) + nodeRadius
  const minY = Math.min(...ys) - nodeRadius
  const maxY = Math.max(...ys) + nodeRadius + bottomExtra
  const availW = Math.max(viewport.width - pads.left - pads.right, 100)
  const availH = Math.max(viewport.height - pads.top - pads.bottom, 100)
  const raw = Math.min(availW / Math.max(maxX - minX, 1), availH / Math.max(maxY - minY, 1))
  return {
    zoom: Math.min(maxZoom, Math.max(minZoom, raw)),
    center: [(minX + maxX) / 2, (minY + maxY) / 2],
    target: [pads.left + availW / 2, pads.top + availH / 2],
  }
}

/**
 * 底部边距：至少 `base`，并避开处于视口下半部分的浮层（如小地图）。
 * 传入的应是「硬障碍」；可展开的图例这类「软障碍」由调用方过滤掉，否则总览会因此缩小。
 */
export function bottomPad(hardObstacles: readonly Box[], viewportHeight: number, base = DEFAULT_PADS.bottom): number {
  let pad = base
  for (const box of hardObstacles) {
    if (box[1] > viewportHeight * 0.55) pad = Math.max(pad, viewportHeight - box[1] + 6)
  }
  return pad
}
