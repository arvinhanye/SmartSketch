import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, effectScope, h } from 'vue'
import { createMemoryHistory, RouterView, type Router } from 'vue-router'
import type { components } from '../../src/contracts/v1/generated/typescript/openapi'
import { COURSES_API_KEY, type CoursesApi } from '../../src/frontend/src/api/courses'
import { PUBLISHED_GRAPH_API_KEY, type PublishedGraphApi } from '../../src/frontend/src/api/graph'
import { KNOWLEDGE_DETAIL_API_KEY, type KnowledgeDetailApi } from '../../src/frontend/src/api/knowledgeDetail'
import GraphCanvas from '../../src/frontend/src/components/GraphCanvas.vue'
import GraphSearch from '../../src/frontend/src/components/GraphSearch.vue'
import { parseViewQuery, viewQuery } from '../../src/frontend/src/composables/graphViewQuery'
import { defaultFilterState, filterGraph, matchNodes, useGraphFilters } from '../../src/frontend/src/composables/useGraphFilters'
import { shortcutAction, useGraphShortcuts } from '../../src/frontend/src/composables/useGraphShortcuts'
import { readPanelWidth, writePanelWidth } from '../../src/frontend/src/composables/usePanelWidthPreference'
import { toG6Data } from '../../src/frontend/src/graph/adapter'
import { createGraphLifecycle, GRAPH_FACTORY_KEY, READABLE_ZOOM, type CanvasGraph, type CanvasGraphFactory, type GraphCanvasData } from '../../src/frontend/src/graph/lifecycle'
import { searchNodes } from '../../src/frontend/src/graph/search'
import { createAppRouter } from '../../src/frontend/src/router/index.ts'
import { useSessionStore } from '../../src/frontend/src/stores/session'
import CoursesView from '../../src/frontend/src/views/CoursesView.vue'
import StudentGraphView from '../../src/frontend/src/views/StudentGraphView.vue'

/**
 * UI-GRAPH-FIND-01：图谱查找（高亮而不是隐藏、别名、候选、上一个/下一个）、快捷键、视图状态写入地址、面板宽度记忆。
 * 验收条件见 specs/course-knowledge-graph.md「图谱查找、快捷键与视图记忆」。
 */
type KnowledgePoint = components['schemas']['KnowledgePoint']
type KnowledgePointDetail = components['schemas']['KnowledgePointDetail']
type Relation = components['schemas']['Relation']

// ---------------------------------------------------------------- 查找排序（纯函数）

describe('searchNodes：名称与别名、排序', () => {
  const items = [
    { kpId: 'app', name: '队列的应用' },
    { kpId: 'ring', name: '循环队列' },
    { kpId: 'fifo', name: '先进先出表', aliases: ['队列', 'FIFO'] },
    { kpId: 'q', name: '队列' },
    { kpId: 'dq', name: '双端表', aliases: ['双端队列'] },
    { kpId: 's', name: '栈' },
  ]

  it('名称完全一致 > 以关键字开头 > 包含 > 别名完全一致 > 别名包含；同级保持输入顺序', () => {
    expect(searchNodes(items, '队列').map((hit) => hit.kpId)).toEqual(['q', 'app', 'ring', 'fifo', 'dq'])
  })

  it('经别名命中时带上那个别名；按名称命中为 null', () => {
    const hits = searchNodes(items, 'fifo')
    expect(hits).toEqual([{ kpId: 'fifo', name: '先进先出表', alias: 'FIFO' }])
    expect(searchNodes(items, '栈')[0]).toEqual({ kpId: 's', name: '栈', alias: null })
  })

  it('忽略大小写、全半角与首尾空白；空关键字与只有空白返回空数组；不修改输入', () => {
    const frozen = Object.freeze(items.map((item) => Object.freeze({ ...item })))
    expect(searchNodes(frozen, ' ＦＩＦＯ ').map((hit) => hit.kpId)).toEqual(['fifo'])
    expect(searchNodes(frozen, '')).toEqual([])
    expect(searchNodes(frozen, '   ')).toEqual([])
    expect(searchNodes(frozen, '不存在')).toEqual([])
  })
})

// ---------------------------------------------------------------- 筛选层：高亮模式

function kp(id: string, over: Partial<KnowledgePoint> = {}): KnowledgePoint {
  return {
    id, course_id: 'c1', name: `知识点${id}`, type: 'concept', definition: `${id} 的定义`, level: 1, confidence: 0.9,
    status: 'approved', source: 'ai', locked: false, revision: 1, chapter_id: 'ch1', ...over,
  }
}
function rel(id: string, from: string, to: string): Relation {
  return { id, course_id: 'c1', type: 'PREREQUISITE', from_id: from, to_id: to, confidence: 0.9, status: 'approved', source: 'ai', source_refs: [] } as unknown as Relation
}
// a→b→c→d 先修链，e 孤立；两章。c 有别名「链表」，d、e 是「方法」
const nodes = [kp('a'), kp('b'), kp('c', { aliases: ['链表'] }), kp('d', { chapter_id: 'ch2', type: 'method' }), kp('e', { chapter_id: 'ch2', type: 'method' })]
const edges = [rel('r1', 'a', 'b'), rel('r2', 'b', 'c'), rel('r3', 'c', 'd')]

function adapted(): GraphCanvasData {
  const out = toG6Data({ format_version: '1.0', course_id: 'c1', graph_version: 3, generated_at: '2026-09-26T00:00:00Z', nodes, edges } as never)
  return { nodes: out.nodes, edges: out.edges }
}

describe('useGraphFilters：search 选项', () => {
  it('缺省（filter）沿用 H05：关键字隐藏不匹配的知识点', () => {
    const scope = effectScope()
    const filters = scope.run(() => useGraphFilters(adapted))!
    filters.state.value = { ...filters.state.value, query: '知识点b' }
    expect(filters.visible.value!.nodes.map((n) => n.data.kpId)).toEqual(['b'])
    scope.stop()
  })

  it('highlight：关键字不隐藏任何知识点与关系，命中在 matches 里；别名可命中', () => {
    const scope = effectScope()
    const filters = scope.run(() => useGraphFilters(adapted, { search: 'highlight' }))!
    filters.state.value = { ...filters.state.value, query: '链表' }
    expect(filters.visible.value!.nodes).toHaveLength(5)
    expect(filters.visible.value!.edges).toHaveLength(3)
    expect(filters.matches.value).toEqual([{ kpId: 'c', name: '知识点c', alias: '链表' }])
    filters.state.value = { ...filters.state.value, query: '  ' }
    expect(filters.matches.value).toEqual([])
    scope.stop()
  })

  it('被类型筛选隐藏的知识点不参与匹配；filterGraph 纯函数语义不变', () => {
    const onlyConcepts = { ...defaultFilterState(), nodeTypes: ['concept'] } as ReturnType<typeof defaultFilterState>
    expect(matchNodes(adapted(), onlyConcepts, '知识点').map((hit) => hit.kpId)).toEqual(['a', 'b', 'c'])
    expect(filterGraph(adapted(), { ...defaultFilterState(), query: '知识点d' }, null).nodes.map((n) => n.data.kpId)).toEqual(['d'])
  })
})

// ---------------------------------------------------------------- 快捷键

function press(key: string, init: KeyboardEventInit = {}, target: EventTarget = document.body): KeyboardEvent {
  const event = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true, ...init })
  target.dispatchEvent(event)
  return event
}

describe('快捷键', () => {
  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('/ 搜索，F 适应，+ 与 = 放大，- 缩小；其他键不处理', () => {
    const action = (key: string, init: KeyboardEventInit = {}) => {
      let seen: ReturnType<typeof shortcutAction> = null
      const listener = (event: Event) => {
        seen = shortcutAction(event as KeyboardEvent)
      }
      window.addEventListener('keydown', listener)
      press(key, init)
      window.removeEventListener('keydown', listener)
      return seen
    }
    expect(action('/')).toBe('search')
    expect(action('f')).toBe('fit')
    expect(action('F')).toBe('fit')
    expect(action('+')).toBe('zoomIn')
    expect(action('=')).toBe('zoomIn')
    expect(action('-')).toBe('zoomOut')
    expect(action('a')).toBe(null)
    expect(action('f', { ctrlKey: true })).toBe(null)
    expect(action('f', { metaKey: true })).toBe(null)
    expect(action('-', { altKey: true })).toBe(null)
  })

  it('焦点在输入框、文本域、下拉框或可编辑区域内不触发；处理过的按键阻止默认行为，未处理的不阻止', () => {
    const calls: string[] = []
    let ready = true
    const Host = defineComponent({
      setup() {
        useGraphShortcuts({ search: () => void calls.push('search'), fit: () => (ready ? void calls.push('fit') : false) })
        return () => h('div', [h('input'), h('textarea'), h('select'), h('div', { contenteditable: 'true' })])
      },
    })
    const w = mount(Host, { attachTo: document.body })

    expect(press('/').defaultPrevented).toBe(true)
    expect(press('f').defaultPrevented).toBe(true)
    expect(calls).toEqual(['search', 'fit'])

    for (const selector of ['input', 'textarea', 'select', '[contenteditable]']) {
      const event = press('/', {}, w.get(selector).element)
      expect(event.defaultPrevented).toBe(false)
      press('f', {}, w.get(selector).element)
    }
    expect(calls).toEqual(['search', 'fit'])

    ready = false
    expect(press('f').defaultPrevented).toBe(false)
    expect(press('+').defaultPrevented).toBe(false)

    w.unmount()
    press('/')
    expect(calls).toEqual(['search', 'fit'])
  })
})

// ---------------------------------------------------------------- 地址参数与宽度偏好（纯函数）

describe('视图状态 ↔ 地址参数', () => {
  it('缺省值不写；写出的参数能原样读回', () => {
    const empty = { kp: null, q: '', ch: null, hiddenRelations: [], hiddenTypes: [], cards: false }
    expect(viewQuery(empty)).toEqual({})
    const state = { kp: 'c', q: '链表', ch: 'ch2', hiddenRelations: ['RELATED_TO', 'CONTAINS'], hiddenTypes: ['example'], cards: true } as never
    expect(viewQuery(state)).toEqual({ kp: 'c', q: '链表', ch: 'ch2', rel: 'CONTAINS,RELATED_TO', type: 'example', view: 'cards' })
    expect(parseViewQuery(viewQuery(state))).toEqual({ ...(state as object), hiddenRelations: ['CONTAINS', 'RELATED_TO'] })
  })

  it('不认识的值忽略，不抛错', () => {
    expect(parseViewQuery({ kp: ['a', 'b'], q: 3, ch: '', rel: 'NOPE,PREREQUISITE', type: 'x', view: 'grid' })).toEqual({
      kp: null, q: '', ch: null, hiddenRelations: ['PREREQUISITE'], hiddenTypes: [], cards: false,
    })
  })
})

describe('面板宽度偏好', () => {
  beforeEach(() => window.localStorage.clear())
  afterEach(() => vi.restoreAllMocks())

  it('读写一个数字；没存过、存的不是正数时返回 null', () => {
    expect(readPanelWidth('student-graph')).toBe(null)
    writePanelWidth('student-graph', 31.456)
    expect(readPanelWidth('student-graph')).toBe(31.46)
    expect(readPanelWidth('teacher-graph')).toBe(null)
    window.localStorage.setItem('smartsketch.panel-width.teacher-graph', 'abc')
    expect(readPanelWidth('teacher-graph')).toBe(null)
    writePanelWidth('teacher-graph', Number.NaN)
    expect(readPanelWidth('teacher-graph')).toBe(null)
  })

  it('存储抛异常时不报错', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    expect(readPanelWidth('student-graph')).toBe(null)
    expect(() => writePanelWidth('student-graph', 30)).not.toThrow()
  })
})

// ---------------------------------------------------------------- 搜索框组件

describe('GraphSearch：候选、定位与键盘', () => {
  const options = Array.from({ length: 10 }, (_, i) => ({ kpId: `k${i}`, name: `知识点${i}`, meta: '第一章 · 概念', alias: i === 1 ? '别名一' : null }))
  const mountBox = (props: Record<string, unknown> = {}) =>
    mount(GraphSearch, { attachTo: document.body, props: { modelValue: '知识点', options, cursor: -1, ...props } })
  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('没有关键字时显示 / 提示，不显示计数与候选', () => {
    const w = mountBox({ modelValue: '', options: [] })
    expect(w.find('.gw-search__kbd').exists()).toBe(true)
    expect(w.find('[data-test="gw-search-count"]').exists()).toBe(false)
    expect(w.find('[data-test="gw-search-list"]').exists()).toBe(false)
    w.unmount()
  })

  it('输入后展开候选（最多 8 条并说明还有几个），经别名命中的注明别名；计数随定位位置变化', async () => {
    const w = mountBox()
    expect(w.get('[data-test="gw-search-count"]').text()).toBe('共 10 个')
    await w.get('input').setValue('知识点')
    expect(w.emitted('update:modelValue')!.at(-1)).toEqual(['知识点'])
    expect(w.findAll('[data-test="gw-search-option"]')).toHaveLength(8)
    expect(w.get('[data-test="gw-search-list"]').text()).toContain('还有 2 个')
    expect(w.findAll('[data-test="gw-search-option"]')[1]!.text()).toContain('别名：别名一')
    expect(w.get('input').attributes('aria-expanded')).toBe('true')
    await w.setProps({ cursor: 2 })
    expect(w.get('[data-test="gw-search-count"]').text()).toBe('3 / 10')
    await w.setProps({ options: [] })
    expect(w.get('[data-test="gw-search-count"]').text()).toBe('无匹配')
    expect(w.get('[data-test="gw-search-next"]').attributes('disabled')).toBeDefined()
    w.unmount()
  })

  it('回车定位下一个，Shift+回车上一个，按钮同理；定位后收起候选', async () => {
    const w = mountBox()
    await w.get('input').setValue('知识点')
    await w.get('form').trigger('submit')
    expect(w.emitted('step')).toEqual([[1]])
    expect(w.find('[data-test="gw-search-list"]').exists()).toBe(false)
    await w.get('input').trigger('keydown', { key: 'Enter', shiftKey: true })
    await w.get('[data-test="gw-search-next"]').trigger('click')
    await w.get('[data-test="gw-search-prev"]').trigger('click')
    expect(w.emitted('step')).toEqual([[1], [-1], [1], [-1]])
    expect(w.emitted('pick')).toBeUndefined()
    w.unmount()
  })

  it('↑/↓ 在候选里循环移动并标出当前项，回车选定它；点击候选同样选定', async () => {
    const w = mountBox()
    const input = w.get('input')
    await input.setValue('知识点')
    await input.trigger('keydown', { key: 'ArrowDown' })
    await input.trigger('keydown', { key: 'ArrowDown' })
    const second = w.findAll('[data-test="gw-search-option"]')[1]!
    expect(second.attributes('aria-selected')).toBe('true')
    expect(input.attributes('aria-activedescendant')).toBe(second.attributes('id'))
    await input.trigger('keydown', { key: 'ArrowUp' })
    await input.trigger('keydown', { key: 'ArrowUp' })
    expect(w.findAll('[data-test="gw-search-option"]')[7]!.attributes('aria-selected')).toBe('true')
    await w.get('form').trigger('submit')
    expect(w.emitted('pick')).toEqual([['k7']])
    expect(w.emitted('step')).toBeUndefined()

    await input.setValue('知识点')
    await w.findAll('[data-test="gw-search-option"]')[3]!.trigger('click')
    expect(w.emitted('pick')).toEqual([['k7'], ['k3']])
    w.unmount()
  })

  it('Esc 只收起候选并且不再冒泡；候选已收起时 Esc 照常冒泡', async () => {
    const w = mountBox()
    const seen: string[] = []
    const listener = (event: KeyboardEvent) => seen.push(event.key)
    window.addEventListener('keydown', listener)
    await w.get('input').setValue('知识点')
    await w.get('input').trigger('keydown', { key: 'Escape' })
    expect(w.find('[data-test="gw-search-list"]').exists()).toBe(false)
    expect(seen).toEqual([])
    await w.get('input').trigger('keydown', { key: 'Escape' })
    expect(seen).toEqual(['Escape'])
    window.removeEventListener('keydown', listener)
    w.unmount()
  })
})

// ---------------------------------------------------------------- 学生图谱页

const factory = (() => ({
  render: () => Promise.resolve(),
  setData: () => {},
  setSize: () => {},
  fitView: () => Promise.resolve(),
  on() {
    return this
  },
  destroy: () => {},
})) as unknown as CanvasGraphFactory

let pinia: Pinia
beforeEach(() => {
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1440 })
  sessionStorage.clear()
  window.localStorage.clear()
  pinia = createPinia()
  setActivePinia(pinia)
})
afterEach(() => {
  vi.restoreAllMocks()
  document.body.innerHTML = ''
})

async function mountPage(path = '/courses/c1/graph'): Promise<{ w: VueWrapper; router: Router }> {
  const session = useSessionStore(pinia)
  session.signIn({ access_token: 'tok', token_type: 'bearer', expires_in: 3600, user: { id: 'u1', username: 'student', role: 'student' } })
  const router = createAppRouter({
    history: createMemoryHistory(),
    getAccountRole: () => session.role,
    coursesComponent: CoursesView,
    studentGraphComponent: StudentGraphView,
  })
  await router.push(path)
  await router.isReady()
  const w = mount(defineComponent({ render: () => h(RouterView) }), {
    attachTo: document.body,
    global: {
      plugins: [pinia, router],
      provide: {
        [COURSES_API_KEY as symbol]: {
          list: async () => [], create: vi.fn(),
          get: vi.fn<CoursesApi['get']>(async (cid) => ({ id: cid, name: '数据结构', status: 'published', my_role: 'student', published_version: 3, created_at: '2026-09-01T00:00:00Z' })),
        },
        [PUBLISHED_GRAPH_API_KEY as symbol]: {
          getPublished: vi.fn<PublishedGraphApi['getPublished']>(async (cid, version) => ({
            format_version: '1.0', course_id: cid, graph_version: version, generated_at: '2026-09-26T00:00:00Z',
            chapters: [{ id: 'ch1', title: '第一章 线性表', order: 1 }, { id: 'ch2', title: '第二章 栈', order: 2 }],
            nodes, edges,
          })),
        },
        [KNOWLEDGE_DETAIL_API_KEY as symbol]: {
          get: vi.fn<KnowledgeDetailApi['get']>(async (cid, kid) => ({ ...kp(kid), course_id: cid, source_refs: [], prerequisites: [], successors: [], related: [] }) as unknown as KnowledgePointDetail),
        },
        [GRAPH_FACTORY_KEY as symbol]: factory,
      },
    },
  })
  await flushPromises()
  return { w, router }
}

const canvasGraph = (w: VueWrapper) => w.findComponent(GraphCanvas).props('graph') as GraphCanvasData
const statesOf = (w: VueWrapper, kpId: string) => canvasGraph(w).nodes.find((n) => n.data.kpId === kpId)?.states ?? []
const shownIds = (w: VueWrapper) => canvasGraph(w).nodes.map((n) => n.data.kpId).sort()
const query = (router: Router) => router.currentRoute.value.query
async function typeQuery(w: VueWrapper, text: string): Promise<void> {
  await w.get('input[type="search"]').setValue(text)
  await flushPromises()
}
async function submit(w: VueWrapper): Promise<void> {
  await w.get('form[role="search"]').trigger('submit')
  await flushPromises()
}

describe('学生图谱页：搜索高亮而不是隐藏', () => {
  it('输入关键字后画布节点与关系数量不变：命中带 match，其余标准淡化；清空后恢复', async () => {
    const { w } = await mountPage()
    await typeQuery(w, '知识点b')
    expect(shownIds(w)).toEqual(['a', 'b', 'c', 'd', 'e'])
    expect(canvasGraph(w).edges).toHaveLength(3)
    expect(statesOf(w, 'b')).toContain('match')
    expect(statesOf(w, 'b')).not.toContain('dimmed')
    for (const id of ['a', 'c', 'd', 'e']) expect(statesOf(w, id)).toContain('dimmed')
    await typeQuery(w, '')
    for (const id of ['a', 'b', 'c', 'd', 'e']) {
      expect(statesOf(w, id)).not.toContain('dimmed')
      expect(statesOf(w, id)).not.toContain('match')
    }
    w.unmount()
  })

  it('别名可命中，候选里注明别名与章节、类型', async () => {
    const { w } = await mountPage()
    await typeQuery(w, '链表')
    expect(statesOf(w, 'c')).toContain('match')
    const option = w.get('[data-test="gw-search-option"]').text()
    expect(option).toContain('知识点c')
    expect(option).toContain('别名：链表')
    expect(option).toContain('第一章 线性表 · 概念')
    w.unmount()
  })

  it('没有任何命中时不淡化；回车给出提示且不改变当前预览', async () => {
    const { w } = await mountPage()
    w.findComponent(GraphCanvas).vm.$emit('nodeClick', 'b')
    await flushPromises()
    await typeQuery(w, '不存在')
    expect(statesOf(w, 'b')).toContain('selected')
    await submit(w)
    expect(w.get('[data-test="sg-search-notice"]').text()).toContain('未找到匹配的知识点')
    expect(w.get('[data-test="gw-preview"]').text()).toContain('知识点b')
    w.findComponent(GraphCanvas).vm.$emit('blankClick')
    await flushPromises()
    for (const id of ['a', 'b', 'c', 'd', 'e']) expect(statesOf(w, id)).not.toContain('dimmed')
    w.unmount()
  })

  it('回车依次预览下一个命中，Shift+回车上一个，首尾循环；计数显示位置', async () => {
    const { w } = await mountPage()
    await typeQuery(w, '知识点')
    expect(w.get('[data-test="gw-search-count"]').text()).toBe('共 5 个')
    const preview = () => w.get('[data-test="gw-preview"]').text()
    await submit(w)
    expect(preview()).toContain('知识点a')
    expect(w.get('[data-test="gw-search-count"]').text()).toBe('1 / 5')
    await submit(w)
    expect(preview()).toContain('知识点b')
    await w.get('input[type="search"]').trigger('keydown', { key: 'Enter', shiftKey: true })
    await w.get('input[type="search"]').trigger('keydown', { key: 'Enter', shiftKey: true })
    await flushPromises()
    expect(preview()).toContain('知识点e')
    expect(w.get('[data-test="gw-search-count"]').text()).toBe('5 / 5')
    await submit(w)
    expect(preview()).toContain('知识点a')
    // 预览时命中仍带 match，淡化由预览决定（a 的邻居 b 不淡化）
    expect(statesOf(w, 'b')).toEqual(expect.arrayContaining(['neighbor', 'match']))
    expect(w.find('[data-test="knowledge-detail"]').exists()).toBe(false)
    w.unmount()
  })

  it('点候选项直接预览它', async () => {
    const { w } = await mountPage()
    await typeQuery(w, '知识点')
    await w.findAll('[data-test="gw-search-option"]')[2]!.trigger('click')
    await flushPromises()
    expect(w.get('[data-test="gw-preview"]').text()).toContain('知识点c')
    expect(w.get('[data-test="gw-search-count"]').text()).toBe('3 / 5')
    w.unmount()
  })

  it('被类型筛选隐藏的知识点不在命中里；列表视图只列命中的卡片', async () => {
    const { w } = await mountPage('/courses/c1/graph?type=method')
    await typeQuery(w, '知识点')
    expect(w.get('[data-test="gw-search-count"]').text()).toBe('共 3 个')
    await typeQuery(w, '知识点b')
    await w.get('[data-test="sg-mode-cards"]').trigger('click')
    await flushPromises()
    expect(w.findAll('[data-test="kc-card"]')).toHaveLength(1)
    w.unmount()
  })
})

describe('学生图谱页：快捷键', () => {
  it('/ 聚焦搜索框；焦点已在搜索框里时 / 只是输入字符', async () => {
    const { w } = await mountPage()
    const input = w.get('input[type="search"]').element as HTMLInputElement
    expect(document.activeElement).not.toBe(input)
    expect(press('/').defaultPrevented).toBe(true)
    expect(document.activeElement).toBe(input)
    expect(press('/', {}, input).defaultPrevented).toBe(false)
    w.unmount()
  })

  it('F、+、- 调用画布的适应与缩放；列表视图下不处理', async () => {
    const { w } = await mountPage()
    // 组件对外暴露的方法放在 `exposed` 上：换成替身后页面经模板引用调到的就是它
    const exposed = w.findComponent(GraphCanvas).vm.$.exposed as { fitTo: (ids?: readonly string[]) => void; zoomBy: (ratio: number) => void }
    expect(typeof exposed.zoomBy).toBe('function')
    const fitTo = vi.fn()
    const zoomBy = vi.fn()
    exposed.fitTo = fitTo
    exposed.zoomBy = zoomBy
    expect(press('f').defaultPrevented).toBe(true)
    press('+')
    press('-')
    expect(fitTo).toHaveBeenCalledTimes(1)
    expect(zoomBy.mock.calls).toEqual([[1.25], [0.8]])

    await w.get('[data-test="sg-mode-cards"]').trigger('click')
    await flushPromises()
    expect(press('f').defaultPrevented).toBe(false)
    expect(fitTo).toHaveBeenCalledTimes(1)
    w.unmount()
  })
})

describe('学生图谱页：视图状态写入地址并可恢复', () => {
  it('打开详情、搜索、隐藏关系与类型、定位章节、切到列表都写进地址；恢复缺省后参数消失', async () => {
    const { w, router } = await mountPage()
    expect(query(router)).toEqual({})
    w.findComponent(GraphCanvas).vm.$emit('nodeClick', 'b')
    await flushPromises()
    // 预览不算“打开详情”
    expect(query(router)).toEqual({})
    await w.get('[data-test="gw-preview-open"]').trigger('click')
    await flushPromises()
    expect(query(router)).toEqual({ kp: 'b' })

    await typeQuery(w, '链表')
    await w.get('[data-test="gw-chapter-button"]').trigger('click')
    await w.get('[data-test="gw-chapter-ch2"]').trigger('click')
    await flushPromises()
    expect(query(router)).toEqual({ kp: 'b', q: '链表', ch: 'ch2' })

    await w.get('[data-test="sg-mode-cards"]').trigger('click')
    await flushPromises()
    expect(query(router).view).toBe('cards')
    await w.get('[data-test="sg-mode-graph"]').trigger('click')
    await typeQuery(w, '')
    await w.get('[data-test="gw-chapter-chip"] button').trigger('click')
    await flushPromises()
    expect(query(router)).toEqual({ kp: 'b' })
    w.unmount()
  })

  it('由地址恢复：详情、关键字、章节、隐藏的类型与关系、列表视图', async () => {
    const { w, router } = await mountPage('/courses/c1/graph?kp=c&q=%E7%9F%A5%E8%AF%86%E7%82%B9&ch=ch2&type=method&rel=PREREQUISITE&view=cards')
    expect(w.get('[data-test="kd-title"]').text()).toBe('知识点c')
    expect((w.get('input[type="search"]').element as HTMLInputElement).value).toBe('知识点')
    expect(w.get('[data-test="gw-chapter-chip"]').text()).toContain('第二章 栈')
    expect(w.get('[data-test="sg-mode-cards"]').attributes('aria-pressed')).toBe('true')
    // 「方法」被隐藏：只剩三个概念
    expect(w.findAll('[data-test="kc-card"]')).toHaveLength(3)
    await w.get('[data-test="sg-mode-graph"]').trigger('click')
    await flushPromises()
    expect(shownIds(w)).toEqual(['a', 'b', 'c'])
    expect(canvasGraph(w).edges).toHaveLength(0)
    expect(query(router)).toEqual({ kp: 'c', q: '知识点', ch: 'ch2', type: 'method', rel: 'PREREQUISITE' })
    w.unmount()
  })

  it('地址里的知识点、章节不存在或值不认识时忽略：页面照常，章节不定位', async () => {
    const { w, router } = await mountPage('/courses/c1/graph?ch=nope&type=bogus&rel=NOPE&view=grid')
    expect(shownIds(w)).toEqual(['a', 'b', 'c', 'd', 'e'])
    expect(w.find('[data-test="gw-chapter-chip"]').exists()).toBe(false)
    expect(w.find('[data-test="sg-error"]').exists()).toBe(false)
    expect(query(router)).toEqual({})
    w.unmount()
  })

  it('问答链接的版本提示只出现一次：自己改选知识点后地址里的 v 被移除', async () => {
    const { w, router } = await mountPage('/courses/c1/graph?kp=c&v=2')
    expect(w.get('[data-test="sg-link-notice"]').text()).toContain('回答基于第 2 版图谱')
    expect(query(router)).toEqual({ kp: 'c', v: '2' })
    w.findComponent(GraphCanvas).vm.$emit('nodeClick', 'a')
    await flushPromises()
    await w.get('[data-test="gw-preview-open"]').trigger('click')
    await flushPromises()
    expect(w.get('[data-test="kd-title"]').text()).toBe('知识点a')
    expect(query(router)).toEqual({ kp: 'a' })
    w.unmount()
  })

  it('写地址用 replace：不增加历史记录', async () => {
    const { w, router } = await mountPage()
    const push = vi.spyOn(router, 'push')
    const replace = vi.spyOn(router, 'replace')
    await typeQuery(w, '知识点')
    expect(replace).toHaveBeenCalled()
    expect(push).not.toHaveBeenCalled()
    w.unmount()
  })
})

describe('学生图谱页：面板宽度记忆', () => {
  it('调整后的宽度记在本浏览器，重新进入页面保留', async () => {
    vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockImplementation(function (this: HTMLElement) {
      return this.classList.contains('graph-workspace') ? 1600 : 0
    })
    const first = await mountPage()
    const divider = first.w.get('[role="separator"]')
    expect(divider.attributes('aria-valuenow')).toBe('25')
    await divider.trigger('keydown', { key: 'ArrowRight' })
    await divider.trigger('keydown', { key: 'ArrowRight' })
    expect(divider.attributes('aria-valuenow')).toBe('29')
    first.w.unmount()

    const second = await mountPage()
    expect(second.w.get('[role="separator"]').attributes('aria-valuenow')).toBe('29')
    second.w.unmount()
  })
})

// ---------------------------------------------------------------- 搜索定位时放大到可读缩放

describe('画布生命周期：focus 的 readable 选项', () => {
  async function build(zoom: number) {
    const calls: string[] = []
    let current = zoom
    const graph = {
      destroyed: false,
      render: () => Promise.resolve(),
      setData: () => {},
      setSize: () => {},
      fitView: () => Promise.resolve(),
      on() {
        return this
      },
      destroy: () => {},
      getZoom: () => current,
      zoomTo: (next: number) => {
        calls.push(`zoomTo:${next}`)
        current = next
        return Promise.resolve()
      },
      focusElement: (id: string) => {
        calls.push(`focus:${id}`)
        return Promise.resolve()
      },
    } as unknown as CanvasGraph
    const container = document.createElement('div')
    Object.defineProperty(container, 'clientWidth', { value: 800 })
    Object.defineProperty(container, 'clientHeight', { value: 600 })
    const lifecycle = createGraphLifecycle(container, { data: adapted(), factory: () => graph })
    await vi.waitFor(() => expect(lifecycle.status).toBe('ready'))
    calls.length = 0
    // 首屏已放大到可读缩放；模拟用户之后把图缩小（如适应画布）
    current = zoom
    return { lifecycle, calls }
  }

  it('缩放低于可读值时先放大再居中；不带选项时只居中（既有行为）', async () => {
    const { lifecycle, calls } = await build(0.2)
    lifecycle.focus('c')
    await vi.waitFor(() => expect(calls).toEqual(['focus:kp:c']))
    lifecycle.focus('b', { readable: true })
    await vi.waitFor(() => expect(calls).toEqual(['focus:kp:c', `zoomTo:${READABLE_ZOOM}`, 'focus:kp:b']))
    lifecycle.destroy()
  })

  it('已经够大时不改缩放', async () => {
    const { lifecycle, calls } = await build(1.4)
    lifecycle.focus('b', { readable: true })
    await vi.waitFor(() => expect(calls).toEqual(['focus:kp:b']))
    lifecycle.destroy()
  })
})
