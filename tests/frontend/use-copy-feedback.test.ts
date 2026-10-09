import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { mount } from '@vue/test-utils'
import { useCopyFeedback } from '../../src/frontend/src/composables/useCopyFeedback'

// UI-QA-01 F4：复制反馈——成功提示数秒后消失，失败提示保留到下一次操作。
function setup(options: Parameters<typeof useCopyFeedback>[0]) {
  let api!: ReturnType<typeof useCopyFeedback>
  const wrapper = mount(defineComponent({ setup() { api = useCopyFeedback(options); return () => h('div') } }))
  return { api, wrapper }
}
beforeEach(() => vi.useFakeTimers())
afterEach(() => vi.useRealTimers())

describe('useCopyFeedback', () => {
  it('成功：写入文本、显示成功，数秒后清空', async () => {
    const write = vi.fn(async () => undefined)
    const { api } = setup({ write, successMs: 3000 })
    await api.copy(7, '正文')
    expect(write).toHaveBeenCalledWith('正文')
    expect(api.state.value).toEqual({ id: 7, ok: true })
    vi.advanceTimersByTime(3000)
    expect(api.state.value).toBeNull()
  })
  it('失败：显示失败并保留，直到下一次复制', async () => {
    const write = vi.fn().mockRejectedValueOnce(new Error('denied')).mockResolvedValueOnce(undefined)
    const { api } = setup({ write })
    await api.copy(1, 'a')
    expect(api.state.value).toEqual({ id: 1, ok: false })
    vi.advanceTimersByTime(60_000)
    expect(api.state.value).toEqual({ id: 1, ok: false })
    await api.copy(1, 'a')
    expect(api.state.value).toEqual({ id: 1, ok: true })
  })
  it('没有剪贴板接口时按失败处理', async () => {
    vi.stubGlobal('navigator', {})
    const { api } = setup({})
    await api.copy(2, 'b')
    expect(api.state.value).toEqual({ id: 2, ok: false })
    vi.unstubAllGlobals()
  })
})
