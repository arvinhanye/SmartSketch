# 问答链路与画布键盘停靠点（UI-QA-01）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让学生问答的每条回答自带状态、出处和复制入口，输入区固定且对话自动跟随最新内容；让图谱画布不再占据键盘 Tab 顺序。

**Architecture:** 纯函数/组合式逻辑（`chatSources`、`useCopyFeedback`、`useFollowLatest`、`graph/a11y`）先写测试再实现；新增展示组件 `AnswerCard` 承载单条回答的状态与操作，`ChatView` 只做装配与“当前回答”状态；样式由 `PageSheet`/`PageHeader` + `.light-surface` 统一，删除 `ui.css` 里借 `--ss-*` 名字重映射成浅色的问答段。

**Tech Stack:** Vue 3 + TypeScript + Vite、Vitest + @vue/test-utils（jsdom）、AntV G6（只动容器上的 canvas 属性）。

**Spec:** `specs/grounded-qa.md`「问答页前端呈现」F1–F7；`specs/course-knowledge-graph.md`「图谱画布键盘约定」。

## Global Constraints

- 不改后端、`src/contracts/`、接口、数据与权限；`status`（`answered`/`not_covered`/`error`/`aborted`/`streaming`）与撤回语义不变。
- 不新增依赖；图标用内联 SVG（`AppIcon`，新增 `copy`、`info`）。
- 保留 `data-test`：`chat-kp`、`chat-kp-toggle`、`chat-send`、`chat-stop`、`model-config-required`、`model-config-link`，以及 `.source-list__item`、`aside[aria-label="引用原文"]`、`article.source`（含「出处 [n]」）、`SourceViewer` 钩子。
- 状态必须“文字 + 图标”；动效只用于生成中三点，`prefers-reduced-motion` 下静止；新样式带 `.light-surface` 作用域，颜色用 `--gw-*`。
- 桌面优先：390 宽只要求无横向溢出；先写失败测试再实现；既有断言只在结构变化处更新并写明原因，不放宽。
- 提交、推送、开 PR 只在用户明确指示后做（本计划不含提交步骤）。
- 命令在仓库根执行：`npm --prefix src/frontend run test -- --run <test files>`。

---

### Task 1: 画布不进入 Tab 顺序

**Files:**
- Create: `src/frontend/src/graph/a11y.ts`
- Modify: `src/frontend/src/graph/lifecycle.ts`（`createGraphLifecycle` 开头挂监听，`destroy()` 里摘除）
- Test: `tests/frontend/graph-tab-stops.test.ts`

**Interfaces:**
- Produces: `keepCanvasOutOfTabOrder(container: HTMLElement): () => void`（立即把容器内所有 `canvas` 设为 `tabindex="-1"`，之后新增或被改回的 canvas 同样处理；返回停止函数）。

- [ ] **Step 1: 写失败测试**

```ts
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { keepCanvasOutOfTabOrder } from '../../src/frontend/src/graph/a11y'
import { createGraphLifecycle, type CanvasGraphFactory } from '../../src/frontend/src/graph/lifecycle'
import { FakeEnhancedGraph } from './fakeEnhancedGraph'

const tick = () => new Promise<void>((resolve) => setTimeout(resolve, 0))
function canvas(tab = '1'): HTMLCanvasElement {
  const el = document.createElement('canvas')
  el.setAttribute('tabindex', tab)
  return el
}

describe('画布不进入 Tab 顺序', () => {
  it('已有的 canvas 立即改为 tabindex=-1', () => {
    const box = document.createElement('div')
    box.append(canvas(), canvas())
    const stop = keepCanvasOutOfTabOrder(box)
    expect([...box.querySelectorAll('canvas')].map((c) => c.getAttribute('tabindex'))).toEqual(['-1', '-1'])
    stop()
  })
  it('之后加入的 canvas、被改回的 tabindex 也改为 -1', async () => {
    const box = document.createElement('div')
    const stop = keepCanvasOutOfTabOrder(box)
    const later = canvas()
    box.append(later)
    await tick()
    expect(later.getAttribute('tabindex')).toBe('-1')
    later.setAttribute('tabindex', '1')
    await tick()
    expect(later.getAttribute('tabindex')).toBe('-1')
    stop()
  })
  it('停止后不再干预', async () => {
    const box = document.createElement('div')
    keepCanvasOutOfTabOrder(box)()
    const later = canvas()
    box.append(later)
    await tick()
    expect(later.getAttribute('tabindex')).toBe('1')
  })
})

describe('生命周期接入', () => {
  beforeEach(() => {
    vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} })
    vi.stubGlobal('requestAnimationFrame', () => 1)
    vi.stubGlobal('cancelAnimationFrame', () => undefined)
  })
  afterEach(() => vi.unstubAllGlobals())
  it('图谱创建的 canvas 不进入 Tab 顺序，销毁后停止监听', async () => {
    const factory: CanvasGraphFactory = (init) => new FakeEnhancedGraph({}, init)
    const el = document.createElement('div')
    Object.defineProperty(el, 'clientWidth', { configurable: true, value: 800 })
    Object.defineProperty(el, 'clientHeight', { configurable: true, value: 600 })
    const life = createGraphLifecycle(el, { data: { nodes: [], edges: [] }, factory })
    const drawn = canvas()
    el.append(drawn)
    await tick()
    expect(drawn.getAttribute('tabindex')).toBe('-1')
    life.destroy()
    const after = canvas()
    el.append(after)
    await tick()
    expect(after.getAttribute('tabindex')).toBe('1')
  })
})
```

- [ ] **Step 2: 运行确认失败**：`npm --prefix src/frontend run test -- --run ../../tests/frontend/graph-tab-stops.test.ts`，期望因找不到 `graph/a11y` 失败。

- [ ] **Step 3: 实现 `graph/a11y.ts`**

```ts
/**
 * G6 会把每层 canvas 设成 `tabindex="1"`：4 层 canvas 成了页面最先的 4 个 Tab 停靠点，没有名称也没有焦点环。
 * 画布是指针交互层（键盘等价路径是搜索、章节菜单、列表与详情，见 `specs/course-knowledge-graph.md`），
 * 所以把容器里的 canvas 一律移出 Tab 顺序；G6 重建画布或重设属性时同样处理。返回停止函数。
 */
export function keepCanvasOutOfTabOrder(container: HTMLElement): () => void {
  const apply = (): void => {
    for (const canvas of container.querySelectorAll('canvas')) {
      if (canvas.getAttribute('tabindex') !== '-1') canvas.setAttribute('tabindex', '-1')
    }
  }
  apply()
  if (typeof MutationObserver === 'undefined') return () => undefined
  const observer = new MutationObserver(apply)
  observer.observe(container, { childList: true, subtree: true, attributes: true, attributeFilter: ['tabindex'] })
  return () => observer.disconnect()
}
```

在 `lifecycle.ts`：顶部 `import { keepCanvasOutOfTabOrder } from './a11y'`；`createGraphLifecycle` 内 `const alive = ...` 之前加 `const stopTabStops = keepCanvasOutOfTabOrder(container)`；`destroy()` 中 `stopObserving()` 之后加 `stopTabStops()`。

- [ ] **Step 4: 运行确认通过**，并跑 `graph-lifecycle-enhance`、`graph-canvas-enhanced`、`h04` 相关测试确认无回归。

---

### Task 2: 出处与复制的纯逻辑 `chatSources`

**Files:**
- Create: `src/frontend/src/composables/chatSources.ts`
- Test: `tests/frontend/chat-sources.test.ts`

**Interfaces:**
- Produces: `citationLine(c: Citation): string`；`sourcesPanel(entry: { status; citations } | null): { citations: readonly Citation[]; hint: string }`；`copyText(answer: string, citations: readonly Citation[]): string`；`STATUS_LABELS: Record<ChatEntry['status'], string>`。

- [ ] **Step 1: 写失败测试**

```ts
import { describe, expect, it } from 'vitest'
import { copyText, citationLine, sourcesPanel, STATUS_LABELS } from '../../src/frontend/src/composables/chatSources'
import type { Citation } from '../../src/frontend/src/composables/useChat'

const c1: Citation = { index: 1, chunk_id: 'k1', document_id: 'd1', page: 46, section_path: '第3章 > 3.2 栈', text: 'x', document_name: 'ch3.md' }
const c2: Citation = { index: 2, chunk_id: 'k2', document_id: 'd2', text: 'y', section_path: '第3章 > 3.3 队列' }

describe('chatSources', () => {
  it('出处一行写法与图谱来源一致，缺文件名写「资料不可用」', () => {
    expect(citationLine(c1)).toBe('ch3.md · 第 46 页 · 第3章 > 3.2 栈')
    expect(citationLine(c2)).toBe('资料不可用 · 第3章 > 3.3 队列')
  })
  it('只有已回答的回答有出处；其余状态给出原因而不是别的回答的出处', () => {
    expect(sourcesPanel({ status: 'answered', citations: [c1] })).toEqual({ citations: [c1], hint: '' })
    expect(sourcesPanel(null).hint).toBe('点回答中的编号查看对应原文。')
    expect(sourcesPanel({ status: 'not_covered', citations: [] })).toEqual({ citations: [], hint: '这条回答没有出处：课程资料未覆盖这个问题。' })
    expect(sourcesPanel({ status: 'error', citations: [] }).hint).toBe('这条回答没有出处：本次回答未完成。')
    expect(sourcesPanel({ status: 'aborted', citations: [] }).hint).toBe('这条回答没有出处：已停止。')
    expect(sourcesPanel({ status: 'streaming', citations: [] }).hint).toBe('回答生成中，完成后在这里显示出处。')
  })
  it('复制文本是正文、空行、「出处：」和每条一行', () => {
    expect(copyText('栈后进先出[1][2]。', [c1, c2])).toBe(
      '栈后进先出[1][2]。\n\n出处：\n[1] ch3.md · 第 46 页 · 第3章 > 3.2 栈\n[2] 资料不可用 · 第3章 > 3.3 队列',
    )
    expect(copyText('只有正文', [])).toBe('只有正文')
  })
  it('状态标签文字', () => {
    expect(STATUS_LABELS).toEqual({ streaming: '生成中', answered: '已回答', not_covered: '资料未覆盖', error: '未完成', aborted: '已停止' })
  })
})
```

- [ ] **Step 2: 运行确认失败**（模块不存在）。

- [ ] **Step 3: 实现**

```ts
import type { ChatEntry, Citation } from './useChat'
import { formatSourceLine } from './sourceLabel'

export const STATUS_LABELS: Record<ChatEntry['status'], string> = {
  streaming: '生成中',
  answered: '已回答',
  not_covered: '资料未覆盖',
  error: '未完成',
  aborted: '已停止',
}

/** 「文件名 · 第 N 页 · 章节」，面板、列表与复制共用 */
export function citationLine(citation: Citation): string {
  return formatSourceLine({ documentName: citation.document_name, page: citation.page, sectionPath: citation.section_path })
}

const NO_SOURCE: Partial<Record<ChatEntry['status'], string>> = {
  not_covered: '这条回答没有出处：课程资料未覆盖这个问题。',
  error: '这条回答没有出处：本次回答未完成。',
  aborted: '这条回答没有出处：已停止。',
  streaming: '回答生成中，完成后在这里显示出处。',
}

/** 右侧「出处」面板只显示当前回答自己的出处；没有出处时写明原因，不借用别的回答的出处 */
export function sourcesPanel(entry: { status: ChatEntry['status']; citations: readonly Citation[] } | null): { citations: readonly Citation[]; hint: string } {
  if (entry === null) return { citations: [], hint: '点回答中的编号查看对应原文。' }
  if (entry.status === 'answered') {
    return { citations: entry.citations, hint: entry.citations.length === 0 ? '点回答中的编号查看对应原文。' : '' }
  }
  return { citations: [], hint: NO_SOURCE[entry.status] ?? '' }
}

/** 复制内容：正文 + 空行 + 「出处：」+ 每条一行；没有出处时只有正文 */
export function copyText(answer: string, citations: readonly Citation[]): string {
  if (citations.length === 0) return answer
  return `${answer}\n\n出处：\n${citations.map((c) => `[${c.index}] ${citationLine(c)}`).join('\n')}`
}
```

- [ ] **Step 4: 运行确认通过。**

---

### Task 3: 复制反馈 `useCopyFeedback`

**Files:**
- Create: `src/frontend/src/composables/useCopyFeedback.ts`
- Test: `tests/frontend/use-copy-feedback.test.ts`

**Interfaces:**
- Produces: `useCopyFeedback(options?: { write?: (text: string) => Promise<void>; successMs?: number }): { state: Ref<{ id: number; ok: boolean } | null>; copy(id: number, text: string): Promise<void> }`。成功：`state={id,ok:true}`，`successMs`（默认 3000）后清空；失败：`state={id,ok:false}` 保留到下一次 `copy`。

- [ ] **Step 1: 写失败测试**

```ts
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { mount } from '@vue/test-utils'
import { useCopyFeedback } from '../../src/frontend/src/composables/useCopyFeedback'

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
    const { api } = setup({})
    await api.copy(2, 'b')
    expect(api.state.value).toEqual({ id: 2, ok: false })
  })
})
```

- [ ] **Step 2: 运行确认失败。**

- [ ] **Step 3: 实现**

```ts
import { onBeforeUnmount, ref } from 'vue'

export interface CopyFeedbackOptions {
  write?: (text: string) => Promise<void>
  successMs?: number
}

/** 复制并给出可见反馈：成功提示数秒后消失，失败提示保留到下一次操作（失败时用户需要手动复制） */
export function useCopyFeedback({ write, successMs = 3000 }: CopyFeedbackOptions = {}) {
  const state = ref<{ id: number; ok: boolean } | null>(null)
  let timer: ReturnType<typeof setTimeout> | null = null
  const clear = () => {
    if (timer !== null) clearTimeout(timer)
    timer = null
  }
  async function copy(id: number, text: string): Promise<void> {
    clear()
    try {
      if (write !== undefined) await write(text)
      else if (typeof navigator !== 'undefined' && navigator.clipboard) await navigator.clipboard.writeText(text)
      else throw new Error('clipboard unavailable')
      state.value = { id, ok: true }
      timer = setTimeout(() => {
        state.value = null
        timer = null
      }, successMs)
    } catch {
      state.value = { id, ok: false }
    }
  }
  onBeforeUnmount(clear)
  return { state, copy }
}
```

- [ ] **Step 4: 运行确认通过。**

---

### Task 4: 跟随最新 `useFollowLatest`

**Files:**
- Create: `src/frontend/src/composables/useFollowLatest.ts`
- Test: `tests/frontend/use-follow-latest.test.ts`

**Interfaces:**
- Produces: `useFollowLatest(options?: { reducedMotion?: () => boolean }): { behind: Ref<boolean>; contentChanged(): void; scrollToLatest(): void }`。页面滚动在 `window`；“在底部”指 `scrollHeight - (scrollY + innerHeight) <= 120`。`contentChanged()`：在底部则 `window.scrollTo({ top: scrollHeight, behavior: 'auto' })`，否则 `behind = true`。`scrollToLatest()`：`behavior` 为 `smooth`（减少动效时 `auto`），并 `behind = false`。滚动到底部时 `behind` 自动清除。

- [ ] **Step 1: 写失败测试**

```ts
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { mount } from '@vue/test-utils'
import { useFollowLatest } from '../../src/frontend/src/composables/useFollowLatest'

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
  vi.stubGlobal('scrollTo', scrollTo)
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
    const { api, wrapper } = setup()
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
```

- [ ] **Step 2: 运行确认失败。**

- [ ] **Step 3: 实现**

```ts
import { onBeforeUnmount, onMounted, ref } from 'vue'

const NEAR_BOTTOM_PX = 120

export interface FollowLatestOptions {
  /** 减少动效时「回到最新」不用平滑滚动；缺省读取系统设置 */
  reducedMotion?: () => boolean
}

function systemReduced(): boolean {
  return typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches
}

/**
 * 对话页的滚动跟随（页面整体滚动在 window）：用户在底部时新内容自动滚到最新；
 * 用户上翻阅读时不强拉，只置 `behind` 让页面显示「回到最新」。
 */
export function useFollowLatest({ reducedMotion = systemReduced }: FollowLatestOptions = {}) {
  const behind = ref(false)
  let following = true
  const bottomGap = () => document.documentElement.scrollHeight - (window.scrollY + window.innerHeight)
  const onScroll = () => {
    following = bottomGap() <= NEAR_BOTTOM_PX
    if (following) behind.value = false
  }
  const toBottom = (behavior: ScrollBehavior) => window.scrollTo({ top: document.documentElement.scrollHeight, behavior })

  function contentChanged(): void {
    if (following) toBottom('auto')
    else behind.value = true
  }
  function scrollToLatest(): void {
    following = true
    behind.value = false
    toBottom(reducedMotion() ? 'auto' : 'smooth')
  }
  onMounted(() => window.addEventListener('scroll', onScroll, { passive: true }))
  onBeforeUnmount(() => window.removeEventListener('scroll', onScroll))
  return { behind, contentChanged, scrollToLatest }
}
```

- [ ] **Step 4: 运行确认通过。**

---

### Task 5: 单条回答卡 `AnswerCard` + 图标

**Files:**
- Modify: `src/frontend/src/components/AppIcon.vue`（新增 `copy`、`info`）
- Create: `src/frontend/src/components/chat/AnswerCard.vue`
- Test: `tests/frontend/answer-card.test.ts`

**Interfaces:**
- Consumes: `ChatEntry`、`Citation`（`useChat`）；`STATUS_LABELS`、`citationLine`（Task 2）。
- Produces: `<AnswerCard :entry :active :current-version :course-id :graph-link-available :kp-label :copy-state :sending @citation @show-sources @copy @retry @open-kp />`，其中 `kpLabel: (id: string) => string`，`copyState: { ok: boolean } | null`。DOM 钩子：根 `li`-内容为 `div.answer[data-status]`，状态标签 `data-test="answer-status"`（`data-status`），「查看 N 处出处」`data-test="answer-sources-toggle"`（`aria-pressed=active`），复制 `data-test="chat-copy"`、反馈 `data-test="chat-copy-status"`，下一步 `data-test="chat-nc-next"`，原因 `data-test="answer-error-reason"`，涉及的知识点沿用 `chat-kp`/`chat-kp-toggle`。

- [ ] **Step 1: 写失败测试**（`mount(AnswerCard, { props, global: { plugins: [router] } })`，router 含 `STUDENT_GRAPH_ROUTE`）

```ts
import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it } from 'vitest'
import AnswerCard from '../../src/frontend/src/components/chat/AnswerCard.vue'
import type { ChatEntry } from '../../src/frontend/src/composables/useChat'
import { STUDENT_GRAPH_ROUTE } from '../../src/frontend/src/router/index.ts'

const cite = { index: 1, chunk_id: 'k', document_id: 'd', page: 2, text: '原文', document_name: 'a.md' }
const base: ChatEntry = { id: 1, question: '问', answer: '正文[1]', status: 'answered', citations: [cite], relatedKpIds: [] }
const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/g/:cid', name: STUDENT_GRAPH_ROUTE, component: { render: () => null } }] })
function card(entry: Partial<ChatEntry>, props: Record<string, unknown> = {}) {
  return mount(AnswerCard, {
    props: { entry: { ...base, ...entry }, active: false, currentVersion: 1, courseId: 'c1', graphLinkAvailable: true, kpLabel: (id: string) => id, copyState: null, sending: false, ...props },
    global: { plugins: [router] },
  })
}

describe('AnswerCard', () => {
  it.each([
    ['streaming', '生成中'], ['answered', '已回答'], ['not_covered', '资料未覆盖'], ['error', '未完成'], ['aborted', '已停止'],
  ] as const)('%s 状态标签文字与 data-status', (status, text) => {
    const w = card({ status })
    const tag = w.get('[data-test="answer-status"]')
    expect(tag.text()).toContain(text)
    expect(tag.attributes('data-status')).toBe(status)
    expect(tag.find('svg').exists() || status === 'streaming').toBe(true)
  })
  it('已回答：有「查看 1 处出处」和复制按钮；点击分别发出事件', async () => {
    const w = card({})
    await w.get('[data-test="answer-sources-toggle"]').trigger('click')
    await w.get('[data-test="chat-copy"]').trigger('click')
    expect(w.get('[data-test="answer-sources-toggle"]').text()).toContain('1 处出处')
    expect(w.emitted('show-sources')).toHaveLength(1)
    expect(w.emitted('copy')).toHaveLength(1)
  })
  it('资料未覆盖：给下一步，没有出处与复制按钮', () => {
    const w = card({ status: 'not_covered', citations: [], answer: '课程资料不足。', relatedKpIds: ['kp_a'] })
    expect(w.get('[data-test="chat-nc-next"]').text()).toContain('换个问法')
    expect(w.find('[data-test="answer-sources-toggle"]').exists()).toBe(false)
    expect(w.find('[data-test="chat-copy"]').exists()).toBe(false)
    expect(w.find('[data-test="answer-error-reason"]').exists()).toBe(false)
  })
  it('未完成：原因只出现一次，有重试；重试在发送中禁用', async () => {
    const w = card({ status: 'error', citations: [], answer: '问答暂时失败，请稍后重试。' })
    expect(w.text().split('问答暂时失败').length - 1).toBe(1)
    expect(w.get('[data-test="answer-error-reason"]').attributes('role')).toBe('alert')
    expect(w.find('[data-test="chat-nc-next"]').exists()).toBe(false)
    await w.get('[data-test="answer-retry"]').trigger('click')
    expect(w.emitted('retry')).toHaveLength(1)
    const busy = card({ status: 'error', citations: [], answer: 'x' }, { sending: true })
    expect(busy.get('[data-test="answer-retry"]').attributes('disabled')).toBeDefined()
  })
  it('复制反馈：成功与失败文字，role=status', () => {
    expect(card({}, { copyState: { ok: true } }).get('[data-test="chat-copy-status"]').text()).toBe('已复制回答和出处。')
    const failed = card({}, { copyState: { ok: false } }).get('[data-test="chat-copy-status"]')
    expect(failed.text()).toContain('复制失败')
    expect(failed.attributes('role')).toBe('status')
  })
  it('版本不同时显示「基于第 N 版」', () => {
    expect(card({ graphVersion: 1 }, { currentVersion: 3 }).text()).toContain('基于第 1 版')
  })
})
```

- [ ] **Step 2: 运行确认失败。**

- [ ] **Step 3: 实现 `AppIcon` 新图标**：

```ts
  copy: '<rect x="8.5" y="8.5" width="11" height="11" rx="2"/><path d="M15.5 8.5V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v7.5a2 2 0 0 0 2 2h2.5"/>',
  info: '<circle cx="12" cy="12" r="8.5"/><path d="M12 11v5M12 8v.2"/>',
```

实现 `AnswerCard.vue`：脚本含 `defineProps`/`defineEmits`、`KP_COLLAPSED = 8` 与本卡自己的 `expanded` 状态（原先在 `ChatView` 里按回答 id 存的 `expandedKps` 随卡内化）；模板结构：

```vue
<div class="answer" :class="`answer--${entry.status}`" :data-status="entry.status" :aria-busy="entry.status === 'streaming'">
  <div class="answer__head">
    <strong class="answer__who">课程助教</strong>
    <span class="answer__status" data-test="answer-status" :data-status="entry.status">
      <AppIcon v-if="STATUS_ICON[entry.status]" :name="STATUS_ICON[entry.status]!" :size="14" />
      <span v-else class="answer__dots" aria-hidden="true"><i /><i /><i /></span>
      {{ STATUS_LABELS[entry.status] }}
    </span>
  </div>
  <!-- 未完成/已停止：原因只写一次，不走 Markdown -->
  <p v-if="entry.status === 'error' || entry.status === 'aborted'" class="answer__reason" data-test="answer-error-reason" :role="entry.status === 'error' ? 'alert' : 'status'">{{ entry.answer }}</p>
  <ChatMarkdown v-else :text="entry.answer" :citations="entry.citations" :final="entry.status === 'answered'" @citation="emit('citation', $event)" />
  <p v-if="entry.status === 'not_covered'" class="answer__next" data-test="chat-nc-next">
    可以换个问法，或到知识图谱里浏览相关知识点。<RouterLink v-if="graphLinkAvailable && courseId" :to="{ name: STUDENT_GRAPH_ROUTE, params: { cid: courseId } }">在图谱中查看</RouterLink>
  </p>
  <!-- 版本提示、涉及的知识点（沿用原逻辑与钩子）、操作行 -->
  <div v-if="entry.status === 'answered'" class="answer__actions">
    <button type="button" class="answer__action" data-test="answer-sources-toggle" :aria-pressed="active ? 'true' : 'false'" @click="emit('show-sources')">查看 {{ entry.citations.length }} 处出处</button>
    <button type="button" class="answer__action" data-test="chat-copy" @click="emit('copy')"><AppIcon name="copy" :size="14" />复制回答</button>
    <span v-if="copyState" class="answer__copy-status" data-test="chat-copy-status" role="status">{{ copyState.ok ? '已复制回答和出处。' : '复制失败，请手动选择文字复制。' }}</span>
  </div>
  <button v-if="entry.status === 'error' || entry.status === 'aborted'" type="button" class="answer__action" data-test="answer-retry" :disabled="sending" @click="emit('retry')">重试</button>
</div>
```

`STATUS_ICON = { answered: 'check', not_covered: 'info', error: 'warn', aborted: 'minus' }`。「涉及的知识点」整段沿用 `ChatView` 现有模板（`chat-kp` 链接或 `open-kp` 按钮、`chat-kp-toggle`），`answered`/`not_covered` 才显示。

- [ ] **Step 4: 运行确认通过。**

---

### Task 6: `ChatView` 装配（当前回答、复制、跟随最新、固定输入区）与样式

**Files:**
- Modify: `src/frontend/src/views/ChatView.vue`（根改为 `PageSheet` + `PageHeader`；用 `AnswerCard`；当前回答；复制；跟随最新；删除旧 `latestCitations`、`expandedKps`、旧 scoped 样式）
- Modify: `src/frontend/src/components/ChatMarkdown.vue`（scoped 样式改用 `--gw-*`）
- Modify: `src/frontend/src/styles/ui.css`（删除 `.ui-chat-workspace` 全部规则：约 222–252、263–264、283–286 行及末尾 `.ui-chat-workspace` 三行；新增 `.light-surface .chat-*` 问答样式）
- Test: `tests/frontend/chat-ui-qa.test.ts`（新）；`tests/frontend/redesign-chat.test.ts`、`l12.test.ts`、`l10.test.ts`、`l13-kp-link.test.ts`、`chat-send-lock.test.ts` 须仍通过

**Interfaces:**
- Consumes: Task 2–5 全部产出。
- Produces（ChatView 内部）：`activeEntryId: Ref<number | null>`（`null` = 最后一条）；`activeEntry`；`panel = sourcesPanel(activeEntry)`；点编号 → `activeEntryId = entry.id; selectedCitation = citation`；提新问题（`entries.length` 增加）→ `activeEntryId = null`、`selectedCitation = null`；`watch(activeEntry?.id)` 清空 `selectedCitation`；`follow.contentChanged()` 在 `entries` 长度、最后一条 `answer.length`/`status` 变化后（`nextTick`）调用；`<button data-test="chat-jump-latest" v-if="follow.behind.value">回到最新</button>`。

- [ ] **Step 1: 写失败测试 `chat-ui-qa.test.ts`**（用 `redesign-chat.test.ts` 的 mount 方式，客户端按序返回多条结果）：
  1. 先答一条有出处的，再提一个 `not_covered`：`aside[aria-label="引用原文"]` 内没有 `.source-list__item`，文字含「这条回答没有出处」；点第一条回答的 `answer-sources-toggle` 后，面板出现该回答的 `.source-list__item`；再提新问题后回到最后一条（面板再次无出处）。
  2. 点正文里第 1 条回答的 `.citation` 按钮：面板切到那条回答并展开 `article.source`（含「出处 [1]」）。
  3. 状态标签：三条结果（answered / not_covered / error）各一个 `[data-test=answer-status]`，文字依次「已回答」「资料未覆盖」「未完成」。
  4. 失败卡：原因文字只出现一次，且有 `answer-retry`；点重试以原问题再发一次。
  5. 复制：`navigator.clipboard.writeText` 被替换为 `vi.fn`，点 `chat-copy` 后调用参数逐字等于 `正文\n\n出处：\n[1] ...`，`chat-copy-status` 文字「已复制回答和出处。」；`writeText` 拒绝时显示「复制失败」。
  6. 输入区：`form.compose` 有 `data-test="chat-compose"`（固定在底部由样式实现，测试只断言存在且在最后一条回答之后）；初始没有 `chat-jump-latest`。
  7. 页头：`h2#chat-title` 文字「课程问答」，页内「返回课程」链接指向课程页，`仅依据已发布资料回答` 仍可见。

- [ ] **Step 2: 运行确认失败**（新增断言失败，旧测试仍通过）。

- [ ] **Step 3: 实现 `ChatView`**。脚本要点：

```ts
import AnswerCard from '../components/chat/AnswerCard.vue'
import PageHeader from '../components/PageHeader.vue'
import PageSheet from '../components/PageSheet.vue'
import { citationLine, copyText, sourcesPanel } from '../composables/chatSources'
import { useCopyFeedback } from '../composables/useCopyFeedback'
import { useFollowLatest } from '../composables/useFollowLatest'

const activeEntryId = ref<number | null>(null)
const activeEntry = computed(() => entries.value.find((e) => e.id === activeEntryId.value) ?? entries.value.at(-1) ?? null)
const panel = computed(() => sourcesPanel(activeEntry.value))
watch(() => activeEntry.value?.id, () => { selectedCitation.value = null })
watch(() => entries.value.length, () => { activeEntryId.value = null })   // 新问题回到最后一条
function pickCitation(entry: ChatEntry, citation: Citation): void { activeEntryId.value = entry.id; selectedCitation.value = citation }
function showSources(entry: ChatEntry): void { activeEntryId.value = entry.id; selectedCitation.value = null }
const copyFeedback = useCopyFeedback()
function copyAnswer(entry: ChatEntry): void { void copyFeedback.copy(entry.id, copyText(entry.answer, entry.citations)) }
const follow = useFollowLatest()
watch(
  () => [entries.value.length, entries.value.at(-1)?.answer.length, entries.value.at(-1)?.status],
  () => { void nextTick(follow.contentChanged) },
)
```

注意：两个 `watch` 的先后——长度变化先把 `activeEntryId` 置空，再触发滚动；`selectedCitation` 在 `activeEntry.id` 变化时清空，但 `pickCitation` 同步写入两者，`watch` 在下一轮才执行会把刚选的引用清掉——因此 `pickCitation` 要在 `nextTick` 之后再赋 `selectedCitation`，或把清空逻辑改成“仅当 `activeEntry.id` 与 `selectedEntryId` 不一致时清空”。实现时用后者：新增 `selectedEntryId`，`selectedCitation` 仅当 `selectedEntryId === activeEntry.id` 才显示。

模板：`PageSheet class="chat"` → `PageHeader id="chat-title" title="课程问答" description="仅依据已发布的课程资料回答，每条回答都标注出处。"`，actions 槽放 `<span class="ui-chip">仅依据已发布资料回答</span>` 与 `RouterLink.ui-btn`「返回课程」；`ol.conversation > li.exchange` 内 `p.question` + `AnswerCard`；`aside.chat__sources`（`aria-label="引用原文"`）显示 `panel.citations` 列表、`panel.hint`、`article.source`；`form.compose[data-test=chat-compose]` 外包 `div.chat__dock`（`position: sticky; bottom: 12px`），其上放 `chat-jump-latest` 按钮。

- [ ] **Step 4: 实现样式**。`ChatView` scoped 样式与 `ChatMarkdown` 样式全部改用 `--gw-*`（`.light-surface` 作用域内可用），并含：`.answer`（卡片）、`.answer--not_covered`（`--gw-warn-bg`/`--gw-warn`，信息色）、`.answer--error`（`--gw-danger-bg`/`--gw-danger`）、`.answer__status` 标签、`.answer__dots` 三点脉冲（`@media (prefers-reduced-motion: reduce)` 下 `animation: none`）、`.chat__dock`（sticky + 浅色底 + 顶部分隔）、「回到最新」按钮（居中，`position: sticky`，在输入区上方）；删除 `ui.css` 中所有 `.ui-chat-workspace` 规则。引用角标颜色 `var(--gw-accent)`，代码块底 `var(--gw-hover)`。

- [ ] **Step 5: 运行 `chat-ui-qa`、`answer-card`、`redesign-chat`、`l10`、`l12`、`l13-kp-link`、`chat-send-lock`、`graph-theme` 及前端全量，确认通过**。若旧测试因结构变化失败，只改结构/文案断言并在交接里写明原因，不放宽业务断言。

---

### Task 7: 验收、文档与交接

**Files:**
- Create: `docs/handoffs/claude-ui-qa-01.md`
- Modify: `docs/tasks.md`（UI-QA-01 状态与验收证据）

- [ ] **Step 1:** 在仓库根运行并记录实际结果：`npm --prefix src/frontend run type-check`、`npm --prefix src/frontend run test -- --run`、`npm --prefix src/frontend run build`、`./scripts/verify.sh`；问答相关 E2E（`scripts/e2e.sh tests/e2e/student.spec.ts`，需 Docker；缺环境则如实记「未执行」）。
- [ ] **Step 2:** 起一次性演示栈（审计时用的脚本，不进仓库），Playwright 在 1440×900、1280×800、768×1024 截“优化后”图并与审计前图对比；390 仅验证无横向溢出；三种回答状态、长对话（输入区固定、回到最新）、Tab 顺序（图谱页第一个停靠点是导航链接）、焦点可见、200% 缩放无溢出、`prefers-reduced-motion` 下三点静止、文字对比度扫描无新增不达标。
- [ ] **Step 3:** 写交接：交付物、验证（测试通过与浏览器验收分开）、与计划的差异、未验证项（真实模型、真实课程、读屏、画布像素对比度）、回滚（逐任务 `git revert`）、下一步（第二批候选）。更新 `docs/tasks.md` 状态与验收证据。

## 自检（对照规格）

- F1 状态标签 → Task 2（`STATUS_LABELS`）、Task 5；F2 当前回答出处 → Task 2、Task 6；F3 下一步与单次原因 → Task 5；F4 复制 → Task 2、3、5、6；F5 固定输入区与跟随最新 → Task 4、6；F6 动效 → Task 6 样式；F7 钩子 → Task 5、6 的保留清单与旧测试；画布键盘约定 → Task 1。
- 与计划外的差异（须在交接说明）：右侧面板保留为“当前回答的出处”并配「查看 N 处出处」，没有再在每条回答下重复铺一排来源条，以保住既有 `.source-list__item` 与 `aside` 钩子并避免重复信息。
