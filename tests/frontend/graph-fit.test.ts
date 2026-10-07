import { describe, expect, it } from 'vitest'
import { bottomPad, computeFit, DEFAULT_PADS } from '../../src/frontend/src/graph/fit'

const base = {
  viewport: { width: 884, height: 732 },
  pads: DEFAULT_PADS,
  nodeRadius: 24,
  bottomExtra: 20,
}

describe('范围适应 computeFit', () => {
  it('没有节点时返回 null', () => {
    expect(computeFit({ ...base, points: [] })).toBeNull()
  })

  it('一组节点整体放得进可用区域：包围盒缩放后不超过可用宽高', () => {
    const points: Array<[number, number]> = [[0, 0], [600, 0], [0, 500], [600, 500]]
    const fit = computeFit({ ...base, points })!
    const availW = 884 - 56 - 96
    const availH = 732 - 104 - 96
    const boxW = (600 + 48) * fit.zoom
    const boxH = (500 + 48 + 20) * fit.zoom
    expect(boxW).toBeLessThanOrEqual(availW + 0.001)
    expect(boxH).toBeLessThanOrEqual(availH + 0.001)
    // 至少有一个方向恰好贴满
    expect(Math.max(boxW / availW, boxH / availH)).toBeCloseTo(1, 5)
  })

  it('目标位置是可用区域的中心，而不是视口中心（避开搜索栏、右侧工具、底部折叠条）', () => {
    const fit = computeFit({ ...base, points: [[0, 0], [100, 100]] })!
    expect(fit.target).toEqual([56 + (884 - 56 - 96) / 2, 104 + (732 - 104 - 96) / 2])
    expect(fit.target[0]).not.toBe(884 / 2)
  })

  it('包围盒中心含节点半径与底部标签余量', () => {
    const fit = computeFit({ ...base, points: [[100, 100], [300, 200]] })!
    expect(fit.center[0]).toBeCloseTo((76 + 324) / 2)
    expect(fit.center[1]).toBeCloseTo((76 + (200 + 24 + 20)) / 2)
  })

  it('缩放被限制在 [minZoom, maxZoom]：很大的范围不会缩到 0.2 以下，单个点不会放大到 1.2 以上', () => {
    expect(computeFit({ ...base, points: [[0, 0], [90000, 90000]] })!.zoom).toBe(0.2)
    expect(computeFit({ ...base, points: [[5, 5]] })!.zoom).toBe(1.2)
    expect(computeFit({ ...base, points: [[5, 5]], maxZoom: 2 })!.zoom).toBe(2)
    expect(computeFit({ ...base, points: [[0, 0], [90000, 0]], minZoom: 0.05 })!.zoom).toBeLessThan(0.2)
  })

  it('视口比边距还小时仍给出有限的结果', () => {
    const fit = computeFit({ ...base, viewport: { width: 50, height: 50 }, points: [[0, 0], [300, 300]] })!
    expect(Number.isFinite(fit.zoom)).toBe(true)
    expect(fit.zoom).toBeGreaterThanOrEqual(0.2)
  })

  it('不修改输入', () => {
    const points: Array<readonly [number, number]> = [[1, 2], [3, 4]]
    const snapshot = JSON.stringify(points)
    computeFit({ ...base, points })
    expect(JSON.stringify(points)).toBe(snapshot)
  })
})

describe('底部边距 bottomPad', () => {
  it('没有障碍物时是默认边距', () => {
    expect(bottomPad([], 732)).toBe(96)
  })

  it('避开视口下半部分的硬障碍（小地图），上半部分的不计', () => {
    const minimap = [600, 580, 880, 726] as const // 顶边在 580 > 732 × 0.55
    expect(bottomPad([minimap], 732)).toBe(732 - 580 + 6)
    const toolbar = [10, 10, 300, 60] as const
    expect(bottomPad([toolbar], 732)).toBe(96)
  })

  it('障碍物不高时不会比默认边距更小', () => {
    expect(bottomPad([[0, 700, 100, 730]], 732)).toBe(96)
  })
})
