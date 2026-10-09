/**
 * 缩放相关的纯函数（设计规格 §3.4「屏幕尺寸下限」与 §4 标签分级）。
 *
 * 缩小时标签靠放大字号保持约 13px，但节点、线和箭头原先会缩成 7px 的点和 0.3px 的发丝，与标签严重失衡。
 * 这里给它们设屏幕下限（不是缩小标签，也不是降透明度）：节点直径 ≥14px、线宽 ≥1px、箭头 ≥6px。
 * 放大系数按档位量化（节点 0.25 步、线宽 0.5 步），避免滚轮缩放时每一帧都重绘。
 */

/** 可读缩放：整图适配后低于它就放大到它并聚焦入口节点（13px 标签在 0.9 下约 11.7px；原 0.7 时只有约 9px） */
export const READABLE_ZOOM = 0.9

export const NODE_BASE_PX = 36
export const NODE_MIN_PX = 14
export const LINE_MIN_PX = 1
export const ARROW_BASE_PX = 9
export const ARROW_MIN_PX = 6
export const LABEL_BASE_PX = 13

export interface ScaleFloors {
  /** 节点放大系数（≥1） */
  nodeK: number
  /** 线宽下限，画布像素（0 表示不设下限） */
  lwMin: number
  /** 箭头放大系数（≥1） */
  arrowK: number
}

export const NO_FLOORS: Readonly<ScaleFloors> = Object.freeze({ nodeK: 1, lwMin: 0, arrowK: 1 })

const quantize = (value: number, step: number): number => Math.round(value / step) * step

/** 按当前缩放算屏幕下限；关闭（enabled=false）或缩放无效时不设下限 */
export function scaleFloors(zoom: number, enabled: boolean): ScaleFloors {
  if (!enabled || !(zoom > 0)) return { ...NO_FLOORS }
  return {
    nodeK: Math.max(1, quantize(NODE_MIN_PX / (NODE_BASE_PX * zoom), 0.25)),
    lwMin: Math.max(0, quantize(LINE_MIN_PX / zoom, 0.5)),
    arrowK: Math.max(1, quantize(ARROW_MIN_PX / (ARROW_BASE_PX * zoom), 0.5)),
  }
}

/**
 * 标签放大系数：缩放 ≥ 可读缩放时为 1；缩小时放大字号，让标签在屏幕上保持约 13px。
 * 按 0.5 步量化，上限 5（缩放 0.2）。
 */
export function labelScale(zoom: number): number {
  if (!(zoom > 0) || zoom >= READABLE_ZOOM) return 1
  return Math.min(5, Math.max(1, Math.round((1 / zoom) * 2) / 2))
}

export function sameFloors(a: ScaleFloors, b: ScaleFloors): boolean {
  return a.nodeK === b.nodeK && a.lwMin === b.lwMin && a.arrowK === b.arrowK
}
