import { mount } from '@vue/test-utils'
import { effectScope, nextTick, ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import ToastNotice from '../../src/frontend/src/components/ToastNotice.vue'
import { useAutoDismiss } from '../../src/frontend/src/composables/useAutoDismiss'

// 用户反馈：快速点击审核队列时，页面顶部的提示行一出一没，把下面的内容顶得上下跳动。
// 提示改为固定在右下角的弹窗：不占文档流，不会引起布局位移。
const here = dirname(fileURLToPath(import.meta.url))
const read = (p: string) => readFileSync(resolve(here, '../../src/frontend/src', p), 'utf8')

describe('ToastNotice 组件', () => {
  it('成功/信息提示用 role=status，错误提示用 role=alert，并带 data-tone', () => {
    const toast = (wrapper: ReturnType<typeof mount>) => wrapper.get('.ui-toast')
    expect(toast(mount(ToastNotice, { props: { tone: 'success', text: '已通过' } })).attributes('role')).toBe('status')
    expect(toast(mount(ToastNotice, { props: { tone: 'info', text: '已刷新' } })).attributes('role')).toBe('status')
    const error = mount(ToastNotice, { props: { tone: 'error', text: '网络中断' } })
    expect(toast(error).attributes('role')).toBe('alert')
    expect(toast(error).attributes('data-tone')).toBe('error')
    expect(error.text()).toContain('网络中断')
  })

  it('attrs（如 data-test）落在弹窗上，且弹窗不是组件根元素（不会被「直接子元素」通用规则命中）', () => {
    const wrapper = mount(ToastNotice, { props: { tone: 'success', text: '已通过' }, attrs: { 'data-test': 'rv-notice' } })
    expect(wrapper.classes()).toContain('ui-toast-host')
    expect(wrapper.attributes('data-test')).toBeUndefined()
    expect(wrapper.get('.ui-toast').attributes('data-test')).toBe('rv-notice')
  })

  it('有可访问名称的关闭按钮，点击发出 dismiss', async () => {
    const wrapper = mount(ToastNotice, { props: { tone: 'info', text: '提示' } })
    const close = wrapper.get('button')
    expect(close.attributes('aria-label')).toBe('关闭提示')
    expect(close.attributes('type')).toBe('button')
    await close.trigger('click')
    expect(wrapper.emitted('dismiss')).toHaveLength(1)
  })
})

describe('useAutoDismiss', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  function setup(keep?: (v: { tone: string }) => boolean) {
    const notice = ref<{ tone: string; text: string } | null>(null)
    const dismiss = vi.fn(() => { notice.value = null })
    const scope = effectScope()
    scope.run(() => useAutoDismiss(notice, dismiss, { ms: 4000, keep }))
    return { notice, dismiss, scope }
  }

  it('成功提示 4 秒后自动消失', async () => {
    const { notice, dismiss } = setup((v) => v.tone === 'error')
    notice.value = { tone: 'success', text: '已通过' }
    await nextTick()
    vi.advanceTimersByTime(3999)
    expect(dismiss).not.toHaveBeenCalled()
    vi.advanceTimersByTime(2)
    expect(dismiss).toHaveBeenCalledTimes(1)
  })

  it('错误提示不自动消失，由用户关闭', async () => {
    const { notice, dismiss } = setup((v) => v.tone === 'error')
    notice.value = { tone: 'error', text: '网络中断' }
    await nextTick()
    vi.advanceTimersByTime(60_000)
    expect(dismiss).not.toHaveBeenCalled()
  })

  it('快速连续出现新提示时重新计时，不会被上一条的计时器提前关掉', async () => {
    const { notice, dismiss } = setup()
    notice.value = { tone: 'success', text: '第一条' }
    await nextTick()
    vi.advanceTimersByTime(3000)
    notice.value = { tone: 'success', text: '第二条' }
    await nextTick()
    vi.advanceTimersByTime(3000) // 距第一条 6s，但距第二条只有 3s
    expect(dismiss).not.toHaveBeenCalled()
    vi.advanceTimersByTime(1100)
    expect(dismiss).toHaveBeenCalledTimes(1)
  })

  it('作用域销毁后不再触发', async () => {
    const { notice, dismiss, scope } = setup()
    notice.value = { tone: 'success', text: '已通过' }
    await nextTick()
    scope.stop()
    vi.advanceTimersByTime(10_000)
    expect(dismiss).not.toHaveBeenCalled()
  })
})

describe('审核页与样式守护', () => {
  it('审核页的提示用弹窗组件，不再是文档流里的 <p>', () => {
    const view = read('views/ReviewView.vue')
    expect(view).toContain('<ToastNotice')
    expect(view).not.toMatch(/<p\s[^>]*data-test="rv-notice"/)
    expect(view).toMatch(/data-test="rv-notice"/)
  })

  it('弹窗固定在视口右下角，不占文档流', () => {
    const css = read('styles/ui.css')
    const rule = /div\.ui-toast\.ui-toast\.ui-toast \{([^}]*)\}/.exec(css)?.[1] ?? ''
    expect(rule).toContain('position: fixed')
    expect(rule).toMatch(/right:\s*\d+px/)
    expect(rule).toMatch(/bottom:\s*\d+px/)
    expect(rule).toMatch(/z-index:\s*\d+/)
    // 文字与底色显式写死，不被页面里 [role=alert] 的红字、.ui-sheet__inner > [role=status] 的灰底盖掉
    expect(rule).toMatch(/background:\s*#1d2029/)
    expect(rule).toMatch(/color:\s*#f2f3f7/)
  })

  it('关闭按钮的样式带元素名，不会被页面里的通用按钮样式盖成白底带边框', () => {
    const css = read('styles/ui.css')
    expect(css).toMatch(/div\.ui-toast button\.ui-toast__close \{[^}]*background: transparent/)
    expect(css).toMatch(/div\.ui-toast button\.ui-toast__close:hover:not\(:disabled\)/)
  })

  it('顶栏与功能栏固定：页面向下滚动时不会消失', () => {
    const css = read('styles/graph-workspace.css')
    const rail = /\n\.app-rail \{([^}]*)\}/.exec(css)?.[1] ?? ''
    expect(rail).toContain('position: sticky')
    expect(rail).toMatch(/top:\s*56px/)
    expect(rail).toMatch(/height:\s*calc\(100dvh - 56px\)/)
    const top = /\n\.app-topbar \{([^}]*)\}/.exec(css)?.[1] ?? ''
    expect(top).toContain('position: sticky')
    expect(top).toMatch(/top:\s*0/)
    expect(top).toMatch(/background:\s*var\(--ss-bg\)/)
    expect(top).toMatch(/z-index:\s*\d+/)
  })
})
