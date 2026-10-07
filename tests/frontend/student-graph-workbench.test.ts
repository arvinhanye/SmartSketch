import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { createMemoryHistory, RouterView } from 'vue-router'
import type { components } from '../../src/contracts/v1/generated/typescript/openapi'
import { COURSES_API_KEY, type CoursesApi } from '../../src/frontend/src/api/courses'
import { PUBLISHED_GRAPH_API_KEY, type PublishedGraphApi } from '../../src/frontend/src/api/graph'
import { KNOWLEDGE_DETAIL_API_KEY, type KnowledgeDetailApi } from '../../src/frontend/src/api/knowledgeDetail'
import GraphCanvas from '../../src/frontend/src/components/GraphCanvas.vue'
import { GRAPH_FACTORY_KEY, type CanvasGraph, type CanvasGraphFactory, type GraphCanvasData } from '../../src/frontend/src/graph/lifecycle'
import { createAppRouter } from '../../src/frontend/src/router/index.ts'
import { useSessionStore } from '../../src/frontend/src/stores/session'
import CoursesView from '../../src/frontend/src/views/CoursesView.vue'
import StudentGraphView from '../../src/frontend/src/views/StudentGraphView.vue'

type KnowledgePoint = components['schemas']['KnowledgePoint']
type KnowledgePointDetail = components['schemas']['KnowledgePointDetail']
type Relation = components['schemas']['Relation']

// ---------------------------------------------------------------- 夹具：a→b→c→d 先修链，e 孤立；两章

function kp(id: string, over: Partial<KnowledgePoint> = {}): KnowledgePoint {
  return {
    id, course_id: 'c1', name: `知识点${id}`, type: 'concept', definition: `${id} 的定义`, level: 1, confidence: 0.9,
    status: 'approved', source: 'ai', locked: false, revision: 1, chapter_id: 'ch1', ...over,
  }
}
function rel(id: string, from: string, to: string): Relation {
  return { id, course_id: 'c1', type: 'PREREQUISITE', from_id: from, to_id: to, confidence: 0.9, status: 'approved', source: 'ai', source_refs: [] } as unknown as Relation
}
const nodes = [kp('a'), kp('b'), kp('c'), kp('d', { chapter_id: 'ch2', type: 'method' }), kp('e', { chapter_id: 'ch2', type: 'method' })]
const edges = [rel('r1', 'a', 'b'), rel('r2', 'b', 'c'), rel('r3', 'c', 'd')]

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

/** jsdom 不排版：把工作区容器量成指定宽度（≥960 并置，否则覆盖） */
function mockWorkspaceWidth(width: number): void {
  vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockImplementation(function (this: HTMLElement) {
    return this.classList.contains('graph-workspace') ? width : 0
  })
}

let pinia: Pinia
beforeEach(() => {
  // 宽屏（≥1280）图例默认展开
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1440 })
  sessionStorage.clear()
  pinia = createPinia()
  setActivePinia(pinia)
})
afterEach(() => vi.restoreAllMocks())

async function mountPage(path = '/courses/c1/graph') {
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
  const getPublished = vi.fn<PublishedGraphApi['getPublished']>(async (cid, version) => ({
    format_version: '1.0', course_id: cid, graph_version: version, generated_at: '2026-09-26T00:00:00Z',
    chapters: [{ id: 'ch1', title: '第一章 线性表', order: 1 }, { id: 'ch2', title: '第二章 栈', order: 2 }],
    nodes, edges,
  }))
  const wrapper = mount(defineComponent({ render: () => h(RouterView) }), {
    attachTo: document.body,
    global: {
      plugins: [pinia, router],
      provide: {
        [COURSES_API_KEY as symbol]: {
          list: async () => [], create: vi.fn(),
          get: vi.fn<CoursesApi['get']>(async (cid) => ({ id: cid, name: '数据结构', status: 'published', my_role: 'student', published_version: 3, created_at: '2026-09-01T00:00:00Z' })),
        },
        [PUBLISHED_GRAPH_API_KEY as symbol]: { getPublished },
        [KNOWLEDGE_DETAIL_API_KEY as symbol]: {
          get: vi.fn<KnowledgeDetailApi['get']>(async (cid, kid) => ({ ...kp(kid), course_id: cid, source_refs: [], prerequisites: [], successors: [], related: [] }) as unknown as KnowledgePointDetail),
        },
        [GRAPH_FACTORY_KEY as symbol]: factory,
      },
    },
  })
  await flushPromises()
  return wrapper
}

const canvasProps = (w: VueWrapper) => w.findComponent(GraphCanvas).props() as { graph: GraphCanvasData | null; scope: readonly string[] | null; positions: unknown }
const emitCanvas = (w: VueWrapper, event: 'nodeClick' | 'blankClick', ...args: string[]) => w.findComponent(GraphCanvas).vm.$emit(event, ...args)
const statesOf = (w: VueWrapper, kpId: string) => canvasProps(w).graph?.nodes.find((n) => n.data.kpId === kpId)?.states ?? []
const shownIds = (w: VueWrapper) => canvasProps(w).graph!.nodes.map((n) => n.data.kpId).sort()

describe('学生图谱页：预览与详情（规格 §7）', () => {
  it('单击节点只进入预览：预览卡出现、节点高亮，侧栏不打开详情', async () => {
    const w = await mountPage()
    emitCanvas(w, 'nodeClick', 'b')
    await flushPromises()
    expect(w.get('[data-test="gw-preview"]').text()).toContain('知识点b')
    expect(w.find('[data-test="knowledge-detail"]').exists()).toBe(false)
    expect(statesOf(w, 'b')).toContain('selected')
    expect(statesOf(w, 'a')).toContain('neighbor')
    expect(statesOf(w, 'e')).toContain('dimmed')
    w.unmount()
  })

  it('再次单击同一节点才打开详情，预览卡消失', async () => {
    const w = await mountPage()
    emitCanvas(w, 'nodeClick', 'b')
    emitCanvas(w, 'nodeClick', 'b')
    await flushPromises()
    expect(w.find('[data-test="gw-preview"]').exists()).toBe(false)
    expect(w.get('[data-test="kd-title"]').text()).toBe('知识点b')
    expect(w.get('[data-test="sg-version"]').text()).toContain('v3') // 详情态下版本号仍然可见（端到端用例依赖它）
    w.unmount()
  })

  it('详情已打开时单击另一个节点：只预览新节点，详情保持不变；画布上只有新节点带选中外环', async () => {
    const w = await mountPage()
    emitCanvas(w, 'nodeClick', 'b')
    emitCanvas(w, 'nodeClick', 'b')
    await flushPromises()
    emitCanvas(w, 'nodeClick', 'c')
    await flushPromises()
    expect(w.get('[data-test="gw-preview"]').text()).toContain('知识点c')
    expect(w.get('[data-test="kd-title"]').text()).toBe('知识点b')
    expect(statesOf(w, 'c')).toContain('selected')
    expect(statesOf(w, 'b')).not.toContain('selected')
    w.unmount()
  })

  it('点空白处、Esc、预览卡 ✕ 都取消预览，详情不受影响', async () => {
    mockWorkspaceWidth(1200) // 并置模式：Esc 直接取消预览（覆盖抽屉打开时 Esc 先关抽屉，见下方面板用例）
    const w = await mountPage()
    emitCanvas(w, 'nodeClick', 'b')
    emitCanvas(w, 'nodeClick', 'b')
    emitCanvas(w, 'nodeClick', 'c')
    await flushPromises()
    emitCanvas(w, 'blankClick')
    await flushPromises()
    expect(w.find('[data-test="gw-preview"]').exists()).toBe(false)
    expect(w.get('[data-test="kd-title"]').text()).toBe('知识点b')

    emitCanvas(w, 'nodeClick', 'c')
    await flushPromises()
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await flushPromises()
    expect(w.find('[data-test="gw-preview"]').exists()).toBe(false)

    emitCanvas(w, 'nodeClick', 'c')
    await flushPromises()
    await w.get('[data-test="gw-preview-close"]').trigger('click')
    expect(w.find('[data-test="gw-preview"]').exists()).toBe(false)
    expect(w.get('[data-test="kd-title"]').text()).toBe('知识点b')
    w.unmount()
  })

  it('预览卡「查看详情」打开详情；卡上有先修与解锁数量和掌握状态文字', async () => {
    const w = await mountPage()
    emitCanvas(w, 'nodeClick', 'b')
    await flushPromises()
    const card = w.get('[data-test="gw-preview"]').text()
    expect(card).toContain('先修 1 项')
    expect(card).toContain('学完可解锁 1 项')
    expect(card).toContain('未学习')
    await w.get('[data-test="gw-preview-open"]').trigger('click')
    await flushPromises()
    expect(w.get('[data-test="kd-title"]').text()).toBe('知识点b')
    w.unmount()
  })

  it('搜索回车：定位并进入预览（不是直接打开详情）；没有匹配时给出提示', async () => {
    const w = await mountPage()
    const input = w.get('input[type="search"]')
    await input.setValue('知识点c')
    await w.get('form[role="search"]').trigger('submit')
    await flushPromises()
    expect(w.get('[data-test="gw-preview"]').text()).toContain('知识点c')
    expect(w.find('[data-test="knowledge-detail"]').exists()).toBe(false)

    await input.setValue('不存在')
    await w.get('form[role="search"]').trigger('submit')
    await flushPromises()
    expect(w.get('[data-test="sg-search-notice"]').text()).toContain('未找到匹配的知识点')
    w.unmount()
  })

  it('问答链接 ?kp= 是显式选择：直接打开详情', async () => {
    const w = await mountPage('/courses/c1/graph?kp=c&v=3')
    expect(w.get('[data-test="kd-title"]').text()).toBe('知识点c')
    expect(w.find('[data-test="gw-preview"]').exists()).toBe(false)
    w.unmount()
  })
})

describe('学生图谱页：只看相邻（局部视图）', () => {
  it('开启 1 跳隐藏其余节点并给出提示条；2 跳扩大范围；恢复全部回到整图；清除预览不取消局部视图', async () => {
    const w = await mountPage()
    emitCanvas(w, 'nodeClick', 'b')
    await flushPromises()
    await w.get('[data-test="gw-preview-local"]').trigger('click')
    await flushPromises()
    expect(shownIds(w)).toEqual(['a', 'b', 'c'])
    expect(w.get('[data-test="gw-local-bar"]').text()).toContain('只看「知识点b」的相邻知识，已隐藏 2 个')

    await w.get('[data-test="gw-local-2"]').trigger('click')
    await flushPromises()
    expect(shownIds(w)).toEqual(['a', 'b', 'c', 'd'])
    expect(w.get('[data-test="gw-local-bar"]').text()).toContain('已隐藏 1 个')

    emitCanvas(w, 'blankClick')
    await flushPromises()
    expect(w.find('[data-test="gw-local-bar"]').exists()).toBe(true)

    await w.get('[data-test="gw-local-restore"]').trigger('click')
    await flushPromises()
    expect(shownIds(w)).toEqual(['a', 'b', 'c', 'd', 'e'])
    expect(w.find('[data-test="gw-local-bar"]').exists()).toBe(false)
    w.unmount()
  })

  it('与类型筛选叠加取交集，底部计数同步', async () => {
    const w = await mountPage()
    emitCanvas(w, 'nodeClick', 'c')
    await flushPromises()
    await w.get('[data-test="gw-preview-local"]').trigger('click')
    await w.get('[data-test="legend-type-method"]').trigger('click') // 隐藏方法类（d、e）
    await flushPromises()
    expect(shownIds(w)).toEqual(['b', 'c'])
    expect(w.get('.gw-count').text()).toContain('显示 2 / 5')
    w.unmount()
  })
})

describe('学生图谱页：图例即筛选', () => {
  it('图例带计数；隐藏类型后画布与列表同步，「恢复全部」同时恢复关系与类型', async () => {
    const w = await mountPage()
    const legend = w.get('[data-test="relation-legend"]')
    expect(legend.get('[data-test="legend-type-concept"]').text()).toContain('3')
    expect(legend.get('[data-test="legend-type-method"]').text()).toContain('2')
    expect(legend.get('[data-test="legend-rel-PREREQUISITE"]').text()).toContain('3')

    await legend.get('[data-test="legend-type-method"]').trigger('click')
    await legend.get('[data-test="legend-rel-PREREQUISITE"]').trigger('click')
    await flushPromises()
    expect(shownIds(w)).toEqual(['a', 'b', 'c'])
    expect(canvasProps(w).graph!.edges).toHaveLength(0)
    expect(legend.get('[data-test="legend-type-method"]').attributes('aria-label')).toContain('已隐藏')
    expect(legend.text()).toContain('已隐藏 2 类')

    await legend.get('[data-test="legend-restore"]').trigger('click')
    await flushPromises()
    expect(shownIds(w)).toEqual(['a', 'b', 'c', 'd', 'e'])
    expect(canvasProps(w).graph!.edges).toHaveLength(3)
    w.unmount()
  })
})

describe('学生图谱页：章节跳转与章节聚焦', () => {
  it('选择章节后外框成员为本章节点，其他章节淡化，出现可取消的「已定位」标签并收起图例；取消后恢复', async () => {
    const w = await mountPage()
    await w.get('[data-test="gw-chapter-button"]').trigger('click')
    expect(w.get('[data-test="gw-chapter-ch2"]').text()).toContain('共 2 个，已掌握 0')
    await w.get('[data-test="gw-chapter-ch2"]').trigger('click')
    await flushPromises()
    expect(w.get('[data-test="gw-chapter-chip"]').text()).toContain('已定位：第二章 栈')
    expect(canvasProps(w).scope).toEqual(['d', 'e'])
    expect(statesOf(w, 'd')).toContain('match')
    expect(statesOf(w, 'a')).toContain('dimmed')
    expect(w.find('[data-test="legend-type-concept"]').exists()).toBe(false) // 图例自动收起

    await w.get('.gw-chip-on__x').trigger('click')
    await flushPromises()
    expect(w.find('[data-test="gw-chapter-chip"]').exists()).toBe(false)
    expect(canvasProps(w).scope).toBeNull()
    expect(statesOf(w, 'a')).not.toContain('dimmed')
    expect(w.find('[data-test="legend-type-concept"]').exists()).toBe(true) // 自动收起的图例自动恢复
    w.unmount()
  })
})

describe('学生图谱页：左面板按容器宽度并置或覆盖', () => {
  it('容器宽度 ≥960 并置，可收起；不足时是覆盖抽屉（关闭时 inert），选中知识点时抽屉同时打开', async () => {
    mockWorkspaceWidth(1200)
    const docked = await mountPage()
    expect(docked.get('.graph-workspace').classes()).toContain('is-docked')
    expect(docked.get('[data-test="gw-panel"]').attributes('role')).toBe('complementary')
    await docked.get('[data-test="gw-panel-close"]').trigger('click')
    expect(docked.get('.graph-workspace').classes()).toContain('is-collapsed')
    expect(docked.get('[data-test="gw-panel"]').attributes('inert')).toBeDefined()
    await docked.get('[data-test="gw-panel-open"]').trigger('click')
    expect(docked.get('.graph-workspace').classes()).not.toContain('is-collapsed')
    docked.unmount()
    vi.restoreAllMocks()

    const overlay = await mountPage() // jsdom 宽度为 0 → 覆盖模式
    expect(overlay.get('.graph-workspace').classes()).toContain('is-overlay')
    expect(overlay.get('[data-test="gw-panel"]').attributes('role')).toBe('dialog')
    expect(overlay.get('[data-test="gw-panel"]').attributes('inert')).toBeDefined()
    emitCanvas(overlay, 'nodeClick', 'b')
    emitCanvas(overlay, 'nodeClick', 'b')
    await flushPromises()
    expect(overlay.get('[data-test="gw-panel"]').attributes('inert')).toBeUndefined()
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await flushPromises()
    expect(overlay.get('[data-test="gw-panel"]').attributes('inert')).toBeDefined()
    overlay.unmount()
  })
})

describe('学生图谱页：状态与可访问性', () => {
  it('无障碍：画布区描述规模；图例按钮名称写明显示/隐藏状态；工具栏有名称', async () => {
    const w = await mountPage()
    expect(w.get('.graph-canvas__stage').attributes('aria-label')).toBe('课程知识图谱：5 个知识点，3 条关系')
    expect(w.get('[data-test="legend-rel-PREREQUISITE"]').attributes('aria-label')).toBe('前置：显示中，点击隐藏')
    expect(w.get('[role="toolbar"]').attributes('aria-label')).toBe('画布工具')
    expect(w.get('[data-test="sg-mode-graph"]').attributes('aria-label')).toBe('图谱视图')
    w.unmount()
  })
})

// User-approved acceptance follow-up: a single return-to-course action in student details.
describe('学生详情唯一返回入口', () => {
  it('详情没有重复关闭叉；返回课程清除选中并回到课程说明', async () => {
    mockWorkspaceWidth(1200)
    const w = await mountPage('/courses/c1/graph?kp=c&v=3')
    expect(w.get('[data-test="kd-title"]').text()).toBe('知识点c')
    expect(w.find('[data-test="kd-close"]').exists()).toBe(false)
    await w.get('[data-test="gw-back"]').trigger('click')
    await flushPromises()
    expect(w.find('[data-test="knowledge-detail"]').exists()).toBe(false)
    expect(w.get('[data-test="gw-panel"]').attributes('aria-label')).toBe('课程说明')
    w.unmount()
  })
})
