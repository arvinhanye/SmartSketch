import { describe, expect, it } from 'vitest'
import { advanceGraphMotion, type MotionBody } from '../../src/frontend/src/components/authGraphMotion'

function body(overrides: Partial<MotionBody> = {}): MotionBody {
  return {
    x: 100, y: 100, vx: 20, vy: 0,
    angle: 0, angularVelocity: 10,
    scale: 1, baseScale: 1, pulse: 0.08, pulseSpeed: 1, phase: 0,
    radius: 20,
    ...overrides,
  }
}

describe('认证页装饰图运动', () => {
  it('位置、大小和角度随时间变化，并在绘图区边界反弹', () => {
    const graph = body({ x: 175, vx: 40 })

    advanceGraphMotion([graph], 0.5, 1, { width: 200, height: 200 })

    expect(graph.x).toBeLessThanOrEqual(200 - graph.radius * graph.scale)
    expect(graph.vx).toBeLessThan(0)
    expect(graph.scale).not.toBe(1)
    expect(graph.angle).toBeGreaterThan(0)
  })

  it('两组图谱接触并相向移动时交换法向速度', () => {
    const left = body({ x: 90, vx: 20 })
    const right = body({ x: 117, vx: -20 })

    advanceGraphMotion([left, right], 0.02, 0, { width: 300, height: 200 })

    expect(left.vx).toBeLessThan(0)
    expect(right.vx).toBeGreaterThan(0)
    expect(right.x).toBeGreaterThan(left.x)
  })

  it('旋转保持在可读角度内并在端点改变方向', () => {
    const graph = body({ angle: 21, angularVelocity: 10 })

    advanceGraphMotion([graph], 0.5, 0, { width: 300, height: 200 })

    expect(graph.angle).toBeLessThanOrEqual(22)
    expect(graph.angularVelocity).toBeLessThan(0)
  })
})
