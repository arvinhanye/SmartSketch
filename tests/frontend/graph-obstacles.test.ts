import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, ref } from 'vue'
import { createObstacleRegistry, GRAPH_OBSTACLES_KEY, useGraphObstacle } from '../../src/frontend/src/graph/obstacles'

function rect(el: HTMLElement, left: number, top: number, width: number, height: number): void {
  el.getBoundingClientRect = () =>
    ({ left, top, width, height, right: left + width, bottom: top + height, x: left, y: top, toJSON: () => ({}) }) as DOMRect
}

class FakeResizeObserver {
  static instances: FakeResizeObserver[] = []
  observed = new Set<Element>()
  constructor(readonly callback: () => void) {
    FakeResizeObserver.instances.push(this)
  }
  observe(el: Element): void {
    this.observed.add(el)
  }
  unobserve(el: Element): void {
    this.observed.delete(el)
  }
  disconnect(): void {}
}

beforeEach(() => {
  FakeResizeObserver.instances = []
  vi.stubGlobal('ResizeObserver', FakeResizeObserver)
})
afterEach(() => vi.unstubAllGlobals())

describe('createObstacleRegistry', () => {
  it('包围盒相对画布左上角，四周外扩 6px，硬/软障碍分开', () => {
    const registry = createObstacleRegistry()
    const base = document.createElement('div')
    rect(base, 100, 50, 800, 600)
    const bar = document.createElement('div')
    rect(bar, 120, 60, 280, 40)
    const legend = document.createElement('div')
    rect(legend, 110, 400, 200, 100)
    registry.register(bar)
    registry.register(legend, 'soft')
    expect(registry.boxes(base)).toEqual({
      hard: [[14, 4, 306, 56]],
      soft: [[4, 344, 216, 456]],
    })
  })
  it('尺寸为 0（隐藏）的元素被忽略；注销后不再计入', () => {
    const registry = createObstacleRegistry()
    const base = document.createElement('div')
    rect(base, 0, 0, 800, 600)
    const hidden = document.createElement('div')
    rect(hidden, 10, 10, 0, 0)
    const shown = document.createElement('div')
    rect(shown, 10, 10, 50, 20)
    registry.register(hidden)
    const off = registry.register(shown)
    expect(registry.boxes(base).hard).toHaveLength(1)
    off()
    expect(registry.boxes(base).hard).toHaveLength(0)
  })
  it('登记、注销和元素尺寸变化时通知订阅者；取消订阅后不再通知', () => {
    const registry = createObstacleRegistry()
    const listener = vi.fn()
    const stop = registry.onChange(listener)
    const el = document.createElement('div')
    const off = registry.register(el)
    expect(listener).toHaveBeenCalledTimes(1)
    FakeResizeObserver.instances[0]!.callback()
    expect(listener).toHaveBeenCalledTimes(2)
    off()
    expect(listener).toHaveBeenCalledTimes(3)
    off() // 重复注销不再通知
    expect(listener).toHaveBeenCalledTimes(3)
    stop()
    registry.register(el)
    expect(listener).toHaveBeenCalledTimes(3)
  })
})

describe('useGraphObstacle', () => {
  const Overlay = defineComponent({
    setup() {
      const el = ref<HTMLElement | null>(null)
      useGraphObstacle(el, 'soft')
      return () => h('div', { ref: el }, '浮层')
    },
  })

  it('挂载时登记、卸载时注销', () => {
    const registry = createObstacleRegistry()
    const listener = vi.fn()
    registry.onChange(listener)
    const wrapper = mount(Overlay, { global: { provide: { [GRAPH_OBSTACLES_KEY as symbol]: registry } } })
    expect(listener).toHaveBeenCalledTimes(1)
    const base = document.createElement('div')
    rect(base, 0, 0, 100, 100)
    rect(wrapper.element as HTMLElement, 10, 10, 20, 20)
    expect(registry.boxes(base).soft).toHaveLength(1)
    wrapper.unmount()
    expect(registry.boxes(base).soft).toHaveLength(0)
  })
  it('没有注册表时什么都不做', () => {
    expect(() => mount(Overlay).unmount()).not.toThrow()
  })
})
