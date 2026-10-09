import { describe, expect, it } from 'vitest'
import {
  ARROW_MIN_PX,
  labelScale,
  LINE_MIN_PX,
  NODE_BASE_PX,
  NODE_MIN_PX,
  READABLE_ZOOM,
  sameFloors,
  scaleFloors,
} from '../../src/frontend/src/graph/scale'

describe('屏幕尺寸下限 scaleFloors', () => {
  it('总览缩放 0.2：节点 ≥14px、线宽 ≥1px、箭头 ≥6px（修改前是 7.2px / 0.3px / 1.8px）', () => {
    const f = scaleFloors(0.2, true)
    expect(NODE_BASE_PX * f.nodeK * 0.2).toBeGreaterThanOrEqual(NODE_MIN_PX)
    expect(f.lwMin * 0.2).toBeGreaterThanOrEqual(LINE_MIN_PX)
    expect(9 * f.arrowK * 0.2).toBeGreaterThanOrEqual(ARROW_MIN_PX)
    expect(f).toEqual({ nodeK: 2, lwMin: 5, arrowK: 3.5 })
  })

  it('缩放 ≥ 约 0.4 时节点不放大，尺寸与原设计一致', () => {
    expect(scaleFloors(0.4, true).nodeK).toBe(1)
    expect(scaleFloors(0.9, true).nodeK).toBe(1)
    expect(scaleFloors(1, true)).toEqual({ nodeK: 1, lwMin: 1, arrowK: 1 })
    expect(scaleFloors(2, true).arrowK).toBe(1)
  })

  it('线宽下限随缩放反比，按 0.5 档量化', () => {
    expect(scaleFloors(0.5, true).lwMin).toBe(2)
    expect(scaleFloors(0.34, true).lwMin).toBe(3)
    expect(scaleFloors(0.28, true).lwMin).toBe(3.5)
  })

  it('关闭或缩放无效时不设下限（回到修改前的行为）', () => {
    expect(scaleFloors(0.2, false)).toEqual({ nodeK: 1, lwMin: 0, arrowK: 1 })
    expect(scaleFloors(0, true)).toEqual({ nodeK: 1, lwMin: 0, arrowK: 1 })
    expect(scaleFloors(Number.NaN, true)).toEqual({ nodeK: 1, lwMin: 0, arrowK: 1 })
    expect(scaleFloors(-1, true)).toEqual({ nodeK: 1, lwMin: 0, arrowK: 1 })
  })

  it('返回新对象，调用方改写不会污染共享常量', () => {
    const a = scaleFloors(0.2, false)
    a.nodeK = 99
    expect(scaleFloors(0.2, false).nodeK).toBe(1)
  })

  it('档位量化：缩放略有变化时系数不变，避免每帧重绘', () => {
    expect(sameFloors(scaleFloors(0.2, true), scaleFloors(0.205, true))).toBe(true)
    expect(sameFloors(scaleFloors(0.3, true), scaleFloors(0.305, true))).toBe(true)
    expect(sameFloors(scaleFloors(0.9, true), scaleFloors(0.95, true))).toBe(true)
    // 缩放变化足够大时系数才会变，此时才需要重绘
    expect(sameFloors(scaleFloors(0.2, true), scaleFloors(0.3, true))).toBe(false)
  })
})

describe('标签放大系数 labelScale', () => {
  it('缩放 ≥ 可读缩放时为 1', () => {
    expect(READABLE_ZOOM).toBe(0.9)
    expect(labelScale(1)).toBe(1)
    expect(labelScale(0.9)).toBe(1)
    expect(labelScale(2.5)).toBe(1)
  })

  it('缩小时让标签在屏幕上保持约 13px：系数 × 缩放 ≈ 1', () => {
    for (const zoom of [0.85, 0.6, 0.5, 0.34, 0.27, 0.2]) {
      const k = labelScale(zoom)
      expect(k * zoom).toBeGreaterThan(0.7)
      expect(k * zoom).toBeLessThan(1.4)
    }
  })

  it('按 0.5 步量化，上限 5', () => {
    expect(labelScale(0.5)).toBe(2)
    expect(labelScale(0.268)).toBe(3.5)
    expect(labelScale(0.2)).toBe(5)
    expect(labelScale(0.05)).toBe(5)
  })

  it('无效缩放返回 1', () => {
    expect(labelScale(0)).toBe(1)
    expect(labelScale(Number.NaN)).toBe(1)
  })
})
