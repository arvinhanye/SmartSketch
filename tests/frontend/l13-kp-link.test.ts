import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import type { components } from '../../src/contracts/v1/generated/typescript/openapi'
import { CHAT_STREAM_CLIENT_KEY, type ChatStreamClient } from '../../src/frontend/src/api/chatStream'
import { COURSES_API_KEY } from '../../src/frontend/src/api/courses'
import { PUBLISHED_GRAPH_API_KEY, type PublishedGraphApi } from '../../src/frontend/src/api/graph'
import { PROGRESS_API_KEY } from '../../src/frontend/src/api/progress'
import { RECOMMEND_API_KEY } from '../../src/frontend/src/api/recommend'
import { KNOWLEDGE_DETAIL_API_KEY } from '../../src/frontend/src/api/knowledgeDetail'
import { kpLinkOutcome } from '../../src/frontend/src/composables/kpLink'
import { GRAPH_FACTORY_KEY, type CanvasGraph, type CanvasGraphFactory } from '../../src/frontend/src/graph/lifecycle'
import { CHAT_ROUTE, COURSE_ROUTE, createAppRouter, SETTINGS_ROUTE, STUDENT_GRAPH_ROUTE } from '../../src/frontend/src/router/index.ts'
import { useRuntimeStore } from '../../src/frontend/src/stores/runtime'
import { useSessionStore } from '../../src/frontend/src/stores/session'
import ChatView from '../../src/frontend/src/views/ChatView.vue'
import CoursesView from '../../src/frontend/src/views/CoursesView.vue'
import StudentGraphView from '../../src/frontend/src/views/StudentGraphView.vue'

// L13-4（R08）：问答知识点按钮跳转课程图谱，图谱消费 kp 参数并选中目标，而不只是改变 URL。
// 课程与 graph_version 保持一致；目标已不存在、旧版本时明确提示；不跨课找同 ID 节点。

type KnowledgePoint = components['schemas']['KnowledgePoint']
type GraphExchange = components['schemas']['GraphExchange']

describe('L13-4 kp 链接的处理结果（纯函数）', () => {
  const graph = { course_id: 'c1', graph_version: 3, nodes: [{ id: 'a', name: '栈' }] }

  it('节点在当前图、版本一致：选中，无提示', () => {
    expect(kpLinkOutcome({ kp: 'a', v: '3' }, 'c1', graph)).toEqual({ select: 'a', notice: null })
    expect(kpLinkOutcome({ kp: 'a' }, 'c1', graph)).toEqual({ select: 'a', notice: null })
  })

  it('节点仍在但版本不同：选中并提示回答所依据的版本', () => {
    expect(kpLinkOutcome({ kp: 'a', v: '2' }, 'c1', graph)).toEqual({
      select: 'a', notice: '回答基于第 2 版图谱，当前为第 3 版；知识点内容可能已有变化。' })
  })

  it('节点不在当前图：不选中，提示不在当前发布版本中', () => {
    expect(kpLinkOutcome({ kp: 'gone', v: '3' }, 'c1', graph)).toEqual({
      select: null, notice: '该知识点不在当前发布版本中（可能已被删除或合并）。' })
  })

  it('图尚未加载、图属于别的课程或没有 kp：不处理（不跨课找同 ID 节点）', () => {
    expect(kpLinkOutcome({ kp: 'a' }, 'c1', null)).toBe(null)
    expect(kpLinkOutcome({ kp: 'a' }, 'c2', graph)).toBe(null)
    expect(kpLinkOutcome({}, 'c1', graph)).toBe(null)
    expect(kpLinkOutcome({ kp: ['a', 'b'] as unknown as string }, 'c1', graph)).toBe(null)
  })
})

// ---------------------------------------------------------------- 学生图谱页直达

function kp(id: string, cid = 'c1'): KnowledgePoint {
  return { id, course_id: cid, name: `知识点 ${id}`, type: 'concept', definition: `${id} 的定义`, level: 1,
    confidence: 0.9, status: 'approved', source: 'ai', locked: false, revision: 1, chapter_id: 'ch1' }
}

function exchange(cid: string, version: number, nodes: KnowledgePoint[]): GraphExchange {
  return { format_version: '1.0', course_id: cid, graph_version: version, generated_at: '2026-10-03T00:00:00Z',
    chapters: [{ id: 'ch1', title: '第一章', order: 1 }], nodes, edges: [] } as GraphExchange
}

function canvasFactory(focused: string[]): CanvasGraphFactory {
  return (() => ({
    destroyed: false, render: () => Promise.resolve(), setData: () => {}, setSize: () => {},
    fitView: () => Promise.resolve(), on() { return this }, destroy: () => {},
    focusElement: (id: string) => { focused.push(id); return Promise.resolve() },
  }) as unknown as CanvasGraph) as CanvasGraphFactory
}

let pinia: Pinia
beforeEach(() => {
  pinia = createPinia()
  setActivePinia(pinia)
})

const captured: string[] = []
async function mountGraph(path: string, version = 3, learning = false) {
  captured.length = 0
  const session = useSessionStore(pinia)
  session.signIn({ access_token: 't', token_type: 'bearer', expires_in: 3600, user: { id: 'u_s', username: 's', role: 'student' } })
  const router = createAppRouter({ history: createMemoryHistory(), getAccountRole: () => session.role,
    coursesComponent: CoursesView, studentGraphComponent: StudentGraphView })
  await router.push(path)
  await router.isReady()
  const graph: PublishedGraphApi = { getPublished: vi.fn(async (cid: string) => exchange(cid, version, [kp('a', cid), kp('b', cid)])) }
  const course = { id: 'c1', name: '课', status: 'published', my_role: 'student', published_version: version, created_at: 'x' }
  const wrapper = mount(defineComponent({ render: () => h(RouterView) }), {
    attachTo: document.body,
    global: {
      plugins: [pinia, router],
      provide: {
        [COURSES_API_KEY as symbol]: { list: async () => [], create: vi.fn(), get: async () => course },
        [PUBLISHED_GRAPH_API_KEY as symbol]: graph,
        [KNOWLEDGE_DETAIL_API_KEY as symbol]: { get: async (_cid: string, kid: string) => ({ ...kp(kid), source_refs: [{ chunk_id: 'k', document_id: 'd', page: 1 }], prerequisites: [], successors: [], related: [] }) },
        [GRAPH_FACTORY_KEY as symbol]: canvasFactory(captured),
        ...(learning ? {
          [PROGRESS_API_KEY as symbol]: { get: async () => ({graph_version:version, entries:['a','b'].map(kp_id=>({kp_id,status:'unknown',own_status:'unknown',inherited_from:[],updated_at:null}))}) },
          [RECOMMEND_API_KEY as symbol]: { get: async () => ({graph_version:version,state:'recommendations',total_eligible:1,recommendations:[{kp_id:'a',name:'知识点 a',graph_version:version,score:0.6,unlock_count:0,reason:'fixture',factors:{unlock:0,importance:0.5,chapter_order:1,ease:0.5},weighted:{unlock:0,importance:0.125,chapter_order:0.2,ease:0.1},reason_facts:{primary_factor:'chapter_order',chapter_id:'ch1',chapter_name:'章',chapter_rank:0,importance:0.5,centrality:0,difficulty:0.5}}]}) }
        } : {}),
      },
    },
  })
  await flushPromises()
  return { wrapper, router }
}

describe('L13-4 学生图谱页消费 kp 参数', () => {
  it('直达 ?kp=b&v=3：选中该知识点并打开详情', async () => {
    const { wrapper } = await mountGraph('/courses/c1/graph?kp=b&v=3')
    expect(wrapper.get('[data-test="kd-title"]').text()).toBe('知识点 b')
    expect(wrapper.find('[data-test="sg-link-notice"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('目标不在当前版本：提示且不打开详情', async () => {
    const { wrapper } = await mountGraph('/courses/c1/graph?kp=gone&v=3')
    expect(wrapper.get('[data-test="sg-link-notice"]').text()).toContain('不在当前发布版本中')
    expect(wrapper.find('[data-test="kd-title"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('回答基于旧版本：仍选中，并提示版本差异', async () => {
    const { wrapper } = await mountGraph('/courses/c1/graph?kp=a&v=1')
    expect(wrapper.get('[data-test="kd-title"]').text()).toBe('知识点 a')
    expect(wrapper.get('[data-test="sg-link-notice"]').text()).toContain('第 1 版')
    wrapper.unmount()
  })
})

// ---------------------------------------------------------------- 问答页按钮

describe('L13-4 问答知识点按钮链接到图谱', () => {
  it('链接带课程、kp 与回答的图谱版本', async () => {
    useRuntimeStore().apply({ runtime_mode: 'personal', configured: true })
    const client: ChatStreamClient = {
      async send() {
        return { kind: 'done', final: { status: 'answered', answer: '栈后进先出[1]。', graph_version: 3, request_id: 'r',
          related_kp_ids: ['a'], citations: [{ index: 1, chunk_id: 'k', document_id: 'd', page: 1, text: '栈' }] } } as never
      },
    }
    const stub = { render: () => null }
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/courses/:cid', name: COURSE_ROUTE, component: stub },
        { path: '/courses/:cid/chat', name: CHAT_ROUTE, component: ChatView },
        { path: '/courses/:cid/graph', name: STUDENT_GRAPH_ROUTE, component: stub },
        { path: '/settings/model', name: SETTINGS_ROUTE, component: stub },
      ],
    })
    await router.push('/courses/c1/chat')
    await router.isReady()
    const wrapper = mount(ChatView, { global: { plugins: [pinia, router], provide: { [CHAT_STREAM_CLIENT_KEY as symbol]: client } } })
    await wrapper.get('textarea').setValue('什么是栈？')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    const chip = wrapper.get('[data-test="chat-kp"]')
    expect(chip.element.tagName).toBe('A')
    expect(chip.attributes('href')).toBe('/courses/c1/graph?kp=a&v=3')
    wrapper.unmount()
  })
})

describe('offline QA viewport probes', () => {
  it('QA direct link without learning preserves requested focus b', async () => {
    vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(800)
    vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(600)
    const {wrapper}=await mountGraph('/courses/c1/graph?kp=b&v=3')
    await flushPromises()
    expect(wrapper.get('[data-test="kd-title"]').text()).toBe('知识点 b')
    expect(captured.at(-1)).toBe('kp:b')
    wrapper.unmount(); vi.restoreAllMocks()
  })
  it('QA direct link with learning preserves requested focus b', async () => {
    vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(800)
    vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(600)
    const {wrapper}=await mountGraph('/courses/c1/graph?kp=b&v=3',3,true)
    await flushPromises()
    expect(wrapper.get('[data-test="kd-title"]').text()).toBe('知识点 b')
    expect(captured.at(-1)).toBe('kp:b')
    wrapper.unmount(); vi.restoreAllMocks()
  })
})
