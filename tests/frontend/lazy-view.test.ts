import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import { describe, expect, it, vi } from 'vitest'

const settle = async () => { for (let i = 0; i < 6; i += 1) await flushPromises() }
import { lazyView } from '../../src/frontend/src/router/lazyView'

// 异步组件要放进宿主里渲染（和路由里的用法一致）
const host = (view: ReturnType<typeof lazyView>) => defineComponent({ render: () => h(view) })
// 真实的动态 import 返回 ES 模块命名空间对象；Vue 靠 __esModule / Symbol.toStringTag 识别并取 default
const esm = <T,>(component: T) => ({ __esModule: true as const, default: component })
const Page = defineComponent({ render: () => h('main', { 'data-test': 'page' }, '页面内容') })

describe('路由页面按需加载', () => {
  it('加载成功后渲染页面', async () => {
    const wrapper = mount(host(lazyView(async () => esm(Page))))
    await settle()
    expect(wrapper.find('[data-test="page"]').exists()).toBe(true)
  })

  it('偶发失败时自动重试，重试成功就正常渲染', async () => {
    const load = vi.fn<() => Promise<ReturnType<typeof esm<typeof Page>>>>()
    load.mockRejectedValueOnce(new Error('chunk 404')).mockResolvedValue(esm(Page))
    const wrapper = mount(host(lazyView(load)))
    await settle()
    expect(load).toHaveBeenCalledTimes(2)
    expect(wrapper.find('[data-test="page"]').exists()).toBe(true)
  })

  it('一直失败：重试次数用尽后显示可读的错误提示，而不是白屏', async () => {
    const load = vi.fn(async () => Promise.reject(new Error('chunk 404')))
    const wrapper = mount(host(lazyView(load, 2)))
    await settle()
    expect(load).toHaveBeenCalledTimes(3)
    expect(wrapper.get('[role="alert"]').text()).toContain('页面加载失败')
    expect(wrapper.find('[data-test="page"]').exists()).toBe(false)
  })
})
