import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { mount } from '@vue/test-utils'
import { useFollowLatest } from '../../src/frontend/src/composables/useFollowLatest'

// UI-QA-01 F5：用户在底部才自动跟随；上翻阅读时不强拉，给「回到最新」。
let scrollTo: ReturnType<typeof vi.fn>
function page(scrollY: number, height = 2000, inner = 900) {
  Object.defineProperty(document.documentElement, 'scrollHeight', { configurable: true, value: height })
  Object.defineProperty(window, 'innerHeight', { configurable: true, value: inner })
  Object.defineProperty(window, 'scrollY', { configurable: true, value: scrollY })
  window.dispatchEvent(new Event('scroll'))
}
function setup(options?: Parameters<typeof useFollowLatest>[0]) {
  let api!: ReturnType<typeof useFollowLatest>
  const wrapper = mount(defineComponent({ setup() { api = useFollowLatest(options); return () => h('div') } }))
  return { api, wrapper }
}
beforeEach(() => {
  scrollTo = vi.fn()
  window.scrollTo = scrollTo as never
})
afterEach(() => vi.unstubAllGlobals())

describe('useFollowLatest', () => {
  it('用户在底部时新内容自动滚到最新，不出现「回到最新」', () => {
    const { api, wrapper } = setup()
    page(1100)
    api.contentChanged()
    expect(scrollTo).toHaveBeenCalledWith({ top: 2000, behavior: 'auto' })
    expect(api.behind.value).toBe(false)
    wrapper.unmount()
  })
  it('用户上翻阅读时不强拉，出现「回到最新」', () => {
    const { api, wrapper } = setup()
    page(0)
    api.contentChanged()
    expect(scrollTo).not.toHaveBeenCalled()
    expect(api.behind.value).toBe(true)
    wrapper.unmount()
  })
  it('回到最新：平滑滚动并隐藏提示；减少动效时不用平滑滚动', () => {
    const { api, wrapper } = setup({ reducedMotion: () => false })
    page(0)
    api.contentChanged()
    api.scrollToLatest()
    expect(scrollTo).toHaveBeenLastCalledWith({ top: 2000, behavior: 'smooth' })
    expect(api.behind.value).toBe(false)
    wrapper.unmount()
    const reduced = setup({ reducedMotion: () => true })
    page(0)
    reduced.api.scrollToLatest()
    expect(scrollTo).toHaveBeenLastCalledWith({ top: 2000, behavior: 'auto' })
    reduced.wrapper.unmount()
  })
  it('自己滚回底部后提示自动消失', () => {
    const { api, wrapper } = setup()
    page(0)
    api.contentChanged()
    expect(api.behind.value).toBe(true)
    page(1100)
    expect(api.behind.value).toBe(false)
    wrapper.unmount()
  })
})
