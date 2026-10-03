import { describe, expect, it } from 'vitest'
import { buildLearningPath } from '../../src/frontend/src/graph/learningPath'

// L14（R11）：掌握标记 → 推荐更新 → 看懂学习路径。
// 路径是前端对已发布图的纯计算：只看未被拒的 PREREQUISITE 边；推荐顺序以服务端为准，前端不重排。

// 确定性 DAG：A→C、B→C、C→D、C→E、E→F，G 孤立；另有一条 RELATED_TO 与一条被拒的先修边
const NODES = ['A', 'B', 'C', 'D', 'E', 'F', 'G'].map((id) => ({ id, name: `知识点${id}` }))
const EDGES = [
  { id: 'ac', type: 'PREREQUISITE', from_id: 'A', to_id: 'C' },
  { id: 'bc', type: 'PREREQUISITE', from_id: 'B', to_id: 'C' },
  { id: 'cd', type: 'PREREQUISITE', from_id: 'C', to_id: 'D' },
  { id: 'ce', type: 'PREREQUISITE', from_id: 'C', to_id: 'E' },
  { id: 'ef', type: 'PREREQUISITE', from_id: 'E', to_id: 'F' },
  { id: 'gd', type: 'RELATED_TO', from_id: 'G', to_id: 'D' },
  { id: 'gf', type: 'PREREQUISITE', from_id: 'G', to_id: 'F', status: 'rejected' },
]

function mastery(...ids: string[]): Map<string, string> {
  return new Map(ids.map((id) => [id, 'mastered']))
}

function recs(...ids: string[]) {
  return ids.map((kp_id) => ({ kp_id }))
}

function role(path: ReturnType<typeof buildLearningPath>, id: string) {
  return path.roles.get(id) ?? 'dimmed'
}

describe('L14-1 学习路径纯函数', () => {
  it('无前置：焦点 A 是下一步；C 还需要 B，不算解锁', () => {
    const path = buildLearningPath(NODES, EDGES, mastery(), recs('A', 'B', 'G'), null)
    expect(path.focus).toBe('A')
    expect(role(path, 'A')).toBe('next')
    expect(role(path, 'C')).toBe('dimmed')
    expect(path.narrative).toEqual({ mastered: [], missing: [], next: ['知识点A'], unlocks: [] })
    expect([...path.edges]).toEqual([])
  })

  it('多前置必须全部满足：A 已掌握、焦点 B 时 C 才是解锁', () => {
    const path = buildLearningPath(NODES, EDGES, mastery('A'), recs('B', 'G'), 'B')
    expect(role(path, 'B')).toBe('next')
    expect(role(path, 'C')).toBe('unlocks')
    // A 不是 B 的前置，但它是 C 的另一个前置：已掌握的 A 加上 B 才解锁 C，所以 A 也在路径上
    expect(role(path, 'A')).toBe('mastered')
    expect([...path.edges].sort()).toEqual(['ac', 'bc'])
    expect(path.narrative).toEqual({ mastered: ['知识点A'], missing: [], next: ['知识点B'], unlocks: ['知识点C'] })
  })

  it('分支：A、B 已掌握、焦点 C 时解锁 D 与 E；F 要先学 E', () => {
    const path = buildLearningPath(NODES, EDGES, mastery('A', 'B'), recs('C', 'G'), null)
    expect(role(path, 'A')).toBe('mastered')
    expect(role(path, 'B')).toBe('mastered')
    expect(role(path, 'C')).toBe('next')
    expect(role(path, 'D')).toBe('unlocks')
    expect(role(path, 'E')).toBe('unlocks')
    expect(role(path, 'F')).toBe('dimmed')
    expect(role(path, 'G')).toBe('dimmed')
    expect([...path.edges].sort()).toEqual(['ac', 'bc', 'cd', 'ce'])
    expect(path.narrative).toEqual({
      mastered: ['知识点A', '知识点B'], missing: [], next: ['知识点C'], unlocks: ['知识点D', '知识点E'],
    })
  })

  it('全部掌握或没有推荐：没有焦点，所有节点淡化，叙述为空', () => {
    const path = buildLearningPath(NODES, EDGES, mastery('A', 'B', 'C', 'D', 'E', 'F', 'G'), [], null)
    expect(path.focus).toBe(null)
    expect(NODES.every((node) => role(path, node.id) === 'dimmed')).toBe(true)
    expect(path.narrative).toEqual({ mastered: [], missing: [], next: [], unlocks: [] })
    expect(path.edges.size).toBe(0)
    expect(path.order.size).toBe(0)
  })

  it('取消掌握后重新计算：未掌握的 A 成为缺失前置；A 未掌握时焦点 B 不再解锁 C', () => {
    const before = buildLearningPath(NODES, EDGES, mastery('A', 'B'), recs('C'), 'C')
    expect(role(before, 'D')).toBe('unlocks')
    const after = buildLearningPath(NODES, EDGES, mastery('B'), recs('C'), 'C')
    expect(role(after, 'A')).toBe('prereqMissing')
    expect(role(after, 'D')).toBe('unlocks')
    // 后继解锁只要求「已掌握 ∪ {焦点}」覆盖其全部前置；C 的前置缺失不影响 D 的判定，但叙述要说明缺口
    expect(after.narrative.missing).toEqual(['知识点A'])
    // 焦点 B、A 未掌握：C 不再解锁
    const other = buildLearningPath(NODES, EDGES, mastery(), recs('B'), 'B')
    expect(role(other, 'C')).toBe('dimmed')
  })

  it('RELATED_TO 与被拒的先修边不参与计算', () => {
    const path = buildLearningPath(NODES, EDGES, mastery('E'), recs('G'), 'G')
    // gd 是相关、gf 被拒：G 没有后继可解锁
    expect(role(path, 'D')).toBe('dimmed')
    expect(role(path, 'F')).toBe('dimmed')
    expect(path.edges.size).toBe(0)
  })

  it('推荐序号从 1 开始并保持服务端顺序；焦点不在推荐里时退回第一个推荐项', () => {
    const path = buildLearningPath(NODES, EDGES, mastery(), recs('G', 'B', 'A'), 'F')
    expect([...path.order]).toEqual([['G', 1], ['B', 2], ['A', 3]])
    expect(path.focus).toBe('G')
  })

  it('不修改输入；未知节点的掌握记录与指向未知节点的边被忽略', () => {
    const edges = [...EDGES, { id: 'cx', type: 'PREREQUISITE', from_id: 'C', to_id: 'X' }]
    const m = mastery('A', 'B', 'X')
    const snapshot = JSON.stringify({ edges, m: [...m] })
    const path = buildLearningPath(NODES, edges, m, recs('C'), null)
    expect(path.roles.has('X')).toBe(false)
    expect(path.edges.has('cx')).toBe(false)
    expect(JSON.stringify({ edges, m: [...m] })).toBe(snapshot)
  })
})

// ---------------------------------------------------------------- L14-2 画布：路径高亮、序号与淡化

import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { createMemoryHistory, RouterView } from 'vue-router'
import type { components } from '../../src/contracts/v1/generated/typescript/openapi'
import { COURSES_API_KEY } from '../../src/frontend/src/api/courses'
import { PUBLISHED_GRAPH_API_KEY } from '../../src/frontend/src/api/graph'
import { KNOWLEDGE_DETAIL_API_KEY } from '../../src/frontend/src/api/knowledgeDetail'
import { PROGRESS_API_KEY, type ProgressApi, type ProgressEntry } from '../../src/frontend/src/api/progress'
import { RECOMMEND_API_KEY, type Recommendation, type RecommendApi } from '../../src/frontend/src/api/recommend'
import GraphCanvas from '../../src/frontend/src/components/GraphCanvas.vue'
import { applyLearningStates } from '../../src/frontend/src/composables/useLearning'
import { toG6Data } from '../../src/frontend/src/graph/adapter'
import { pathInputFromCanvas } from '../../src/frontend/src/graph/learningPath'
import {
  buildGraphOptions,
  GRAPH_FACTORY_KEY,
  nodeLabel,
  type CanvasGraph,
  type CanvasGraphFactory,
  type GraphCanvasData,
} from '../../src/frontend/src/graph/lifecycle'
import { createAppRouter } from '../../src/frontend/src/router/index.ts'
import { useSessionStore } from '../../src/frontend/src/stores/session'
import CoursesView from '../../src/frontend/src/views/CoursesView.vue'
import StudentGraphView from '../../src/frontend/src/views/StudentGraphView.vue'

type KnowledgePoint = components['schemas']['KnowledgePoint']
type GraphExchange = components['schemas']['GraphExchange']

function kpOf(id: string): KnowledgePoint {
  return { id, course_id: 'c1', name: `知识点${id}`, type: 'concept', definition: `${id} 的定义`, level: 1,
    confidence: 0.9, status: 'approved', source: 'ai', locked: false, revision: 1, chapter_id: 'ch1' }
}

function exchangeOf(): GraphExchange {
  const edges = EDGES.map((edge) => ({
    id: edge.id, course_id: 'c1', type: edge.type, from_id: edge.from_id, to_id: edge.to_id,
    confidence: 0.9, status: edge.status ?? 'approved', source: 'ai', revision: 1,
  }))
  return { format_version: '1.0', course_id: 'c1', graph_version: 3, generated_at: '2026-10-03T00:00:00Z',
    chapters: [{ id: 'ch1', title: '第一章', order: 1 }], nodes: NODES.map((n) => kpOf(n.id)), edges } as unknown as GraphExchange
}

function canvasData(): GraphCanvasData {
  const adapted = toG6Data(exchangeOf())
  return { nodes: adapted.nodes, edges: adapted.edges }
}

function entries(...mastered: string[]): Map<string, ProgressEntry> {
  return new Map(mastered.map((id) => [id, { kp_id: id, status: 'mastered', own_status: 'mastered', inherited_from: [], updated_at: 'x' }]))
}

function statesOf(graph: GraphCanvasData) {
  return {
    node: new Map(graph.nodes.map((n) => [n.data.kpId, n.states ?? []])),
    edge: new Map(graph.edges.map((e) => [e.data.relationId, e.states ?? []])),
  }
}

describe('L14-2 画布路径状态', () => {
  it('画布数据可转成路径输入（kpId 与 relation id，保留类型与状态）', () => {
    const input = pathInputFromCanvas(canvasData())
    expect(input.nodes.find((n) => n.id === 'A')).toEqual({ id: 'A', name: '知识点A' })
    expect(input.edges.find((e) => e.id === 'gf')).toEqual({ id: 'gf', type: 'PREREQUISITE', from_id: 'G', to_id: 'F', status: 'rejected' })
  })

  it('推荐项带序号标签；缺失前置、解锁、淡化与高亮边各有状态', () => {
    const graph = canvasData()
    const m = entries('B')
    const input = pathInputFromCanvas(graph)
    const path = buildLearningPath(input.nodes, input.edges, new Map([['B', 'mastered']]), recs('C', 'G'), null)
    const result = applyLearningStates(graph, m, new Set(['C', 'G']), path)
    const c = result.nodes.find((n) => n.data.kpId === 'C')!
    expect(c.data.pathOrder).toBe(1)
    expect(nodeLabel(c.data)).toBe('1. 知识点C')
    expect(nodeLabel(result.nodes.find((n) => n.data.kpId === 'G')!.data)).toBe('2. 知识点G')
    expect(nodeLabel(result.nodes.find((n) => n.data.kpId === 'A')!.data)).toBe('知识点A')
    const { node, edge } = statesOf(result)
    expect(node.get('C')).toEqual(['notStarted', 'recommended'])
    expect(node.get('A')).toEqual(['notStarted', 'pathPrereq'])
    expect(node.get('B')).toEqual(['mastered'])
    expect(node.get('D')).toEqual(['notStarted', 'pathUnlock'])
    expect(node.get('F')).toEqual(['notStarted', 'dimmed'])
    // 第二个推荐项 G 不在当前焦点的路径上：仍保留推荐色，同时淡化
    expect(node.get('G')).toEqual(['notStarted', 'recommended', 'dimmed'])
    expect(edge.get('ac')).toEqual(['pathEdge'])
    expect(edge.get('cd')).toEqual(['pathEdge'])
    expect(edge.get('ef')).toEqual(['dimmed'])
    // 输入不被修改
    expect(graph.nodes.find((n) => n.data.kpId === 'C')!.data.pathOrder).toBeUndefined()
  })

  it('选中的节点不淡化；没有焦点（全部掌握）时不叠加任何路径状态', () => {
    const graph = canvasData()
    graph.nodes = graph.nodes.map((n) => (n.data.kpId === 'F' ? { ...n, states: ['selected'] } : n))
    const input = pathInputFromCanvas(graph)
    const path = buildLearningPath(input.nodes, input.edges, new Map(), recs('A'), null)
    expect(statesOf(applyLearningStates(graph, new Map(), new Set(['A']), path)).node.get('F')).toEqual(['notStarted', 'selected'])
    const none = buildLearningPath(input.nodes, input.edges, new Map(), [], null)
    const { node, edge } = statesOf(applyLearningStates(graph, new Map(), new Set(), none))
    expect(node.get('D')).toEqual(['notStarted'])
    expect(edge.get('cd')).toEqual([])
  })

  it('状态样式只在 buildGraphOptions 定义：节点 pathPrereq/pathUnlock/dimmed，边 pathEdge/dimmed', () => {
    const el = document.createElement('div')
    const options = buildGraphOptions({ container: el, width: 1, height: 1, data: canvasData() }) as unknown as {
      node: { state: Record<string, unknown>; style: { labelText: (d: unknown) => string } }
      edge: { state: Record<string, unknown> }
    }
    expect(Object.keys(options.node.state)).toEqual(expect.arrayContaining(['pathPrereq', 'pathUnlock', 'dimmed']))
    expect(Object.keys(options.edge.state)).toEqual(expect.arrayContaining(['pathEdge', 'dimmed']))
    expect(options.node.style.labelText({ data: { name: '栈', pathOrder: 2 } })).toBe('2. 栈')
  })
})

// ---------------------------------------------------------------- 学生图谱页：点推荐项切换路径焦点

function rec(kpId: string, extra: Partial<Recommendation['reason_facts']> = {}): Recommendation {
  return {
    kp_id: kpId, name: `知识点${kpId}`, graph_version: 3, score: 0.6,
    factors: { unlock: 0.5, importance: 0.5, chapter_order: 1, ease: 0.5 },
    weighted: { unlock: 0.175, importance: 0.125, chapter_order: 0.2, ease: 0.1 },
    unlock_count: 1, reason: `完成 ${kpId} 可解锁后继`,
    reason_facts: { primary_factor: 'unlock', chapter_id: 'ch1', chapter_name: '第一章', chapter_rank: 0,
      importance: 0.5, centrality: 0.3, difficulty: 0.5, ...extra },
  }
}

function fakeCanvas(): CanvasGraphFactory {
  return (() => ({
    destroyed: false, render: () => Promise.resolve(), setData: () => {}, setSize: () => {},
    fitView: () => Promise.resolve(), on() { return this }, destroy: () => {},
  }) as unknown as CanvasGraph) as CanvasGraphFactory
}

async function mountStudent(mastered: string[], recommended: string[]) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const session = useSessionStore(pinia)
  session.signIn({ access_token: 't', token_type: 'bearer', expires_in: 3600, user: { id: 'u_s', username: 's', role: 'student' } })
  const router = createAppRouter({ history: createMemoryHistory(), getAccountRole: () => session.role,
    coursesComponent: CoursesView, studentGraphComponent: StudentGraphView })
  await router.push('/courses/c1/graph')
  await router.isReady()
  const progress: ProgressApi = {
    get: vi.fn(async () => ({ graph_version: 3, entries: NODES.map((n) => ({
      kp_id: n.id, status: mastered.includes(n.id) ? 'mastered' : 'unknown',
      own_status: mastered.includes(n.id) ? 'mastered' : 'unknown', inherited_from: [], updated_at: 'x' })) })),
    update: vi.fn(),
  } as unknown as ProgressApi
  const recommend: RecommendApi = {
    get: vi.fn(async () => ({ state: 'recommendations', graph_version: 3, total_eligible: recommended.length,
      recommendations: recommended.map((id) => rec(id)) })),
  } as unknown as RecommendApi
  const course = { id: 'c1', name: '课', status: 'published', my_role: 'student', published_version: 3, created_at: 'x' }
  const wrapper = mount(defineComponent({ render: () => h(RouterView) }), {
    attachTo: document.body,
    global: {
      plugins: [pinia, router],
      provide: {
        [COURSES_API_KEY as symbol]: { list: async () => [], create: vi.fn(), get: async () => course },
        [PUBLISHED_GRAPH_API_KEY as symbol]: { getPublished: async () => exchangeOf() },
        [KNOWLEDGE_DETAIL_API_KEY as symbol]: { get: async (_c: string, k: string) => ({ ...kpOf(k), source_refs: [], prerequisites: [], successors: [], related: [] }) },
        [GRAPH_FACTORY_KEY as symbol]: fakeCanvas(),
        [PROGRESS_API_KEY as symbol]: progress,
        [RECOMMEND_API_KEY as symbol]: recommend,
      },
    },
  })
  await flushPromises()
  return wrapper
}

function pageStates(wrapper: VueWrapper) {
  return statesOf(wrapper.findComponent(GraphCanvas).props('graph') as GraphCanvasData)
}

describe('L14-2 学生图谱页路径焦点', () => {
  it('默认解释第一个推荐项；点击第二个推荐项后路径改为它', async () => {
    const wrapper = await mountStudent(['A', 'B'], ['C', 'G'])
    expect(pageStates(wrapper).node.get('D')).toContain('pathUnlock')
    expect(pageStates(wrapper).node.get('G')).toContain('dimmed')
    await wrapper.get('[data-test="rc-select-G"]').trigger('click')
    await flushPromises()
    expect(pageStates(wrapper).node.get('G')).not.toContain('dimmed')
    expect(pageStates(wrapper).node.get('D')).toContain('dimmed')
    wrapper.unmount()
  })
})

// ---------------------------------------------------------------- L14-3 推荐解释

import Recommendations from '../../src/frontend/src/components/Recommendations.vue'
import { pathLine, reasonFactRows } from '../../src/frontend/src/composables/useLearning'

describe('L14-3 推荐解释：先修事实优先，缺省值不冒充测量', () => {
  it('路径行：已掌握 → 还需先学 → 下一步 → 之后解锁；空段省略；没有下一步时为空', () => {
    expect(pathLine({ mastered: ['A', 'B'], missing: [], next: ['C'], unlocks: ['D', 'E'] }))
      .toBe('已掌握：A、B → 下一步：C → 之后解锁：D、E')
    expect(pathLine({ mastered: [], missing: ['A'], next: ['C'], unlocks: [] })).toBe('还需先学：A → 下一步：C')
    expect(pathLine({ mastered: [], missing: [], next: [], unlocks: [] })).toBe('')
  })

  it('重要度、难度为中性值 0.5 时写「未标注」，其他值照常显示', () => {
    const rows = new Map(reasonFactRows(rec('C')).map((row) => [row.key, row]))
    expect(rows.get('importance')!.value).toBe('未标注（按中性值 0.5 排序）')
    expect(rows.get('importance')!.labelledDefault).toBe(true)
    expect(rows.get('difficulty')!.value).toBe('未标注（按中性值 0.5 排序）')
    const marked = new Map(reasonFactRows(rec('C', { importance: 0.8, difficulty: 0.3 })).map((row) => [row.key, row]))
    expect(marked.get('importance')!.value).toBe('0.8000')
    expect(marked.get('importance')!.labelledDefault).toBe(false)
    expect(marked.get('difficulty')!.value).toBe('0.3000')
  })

  it('列表：顶部路径行、每项序号、「排序参考」', () => {
    const wrapper = mount(Recommendations, {
      props: {
        state: 'recommendations', items: [rec('C'), rec('G')], totalEligible: 2,
        narrative: { mastered: ['知识点A'], missing: [], next: ['知识点C'], unlocks: ['知识点D'] },
      },
    })
    expect(wrapper.get('[data-test="rc-path-line"]').text()).toBe('已掌握：知识点A → 下一步：知识点C → 之后解锁：知识点D')
    expect(wrapper.findAll('[data-test="rc-order"]').map((el) => el.text())).toEqual(['1.', '2.'])
    expect(wrapper.get('.recommendations__details summary').text()).toBe('排序参考')
    expect(wrapper.find('[data-fact="importance"]').text()).toContain('未标注')
  })

  it('没有路径叙述时不渲染路径行', () => {
    const wrapper = mount(Recommendations, { props: { state: 'recommendations', items: [rec('C')], totalEligible: 1 } })
    expect(wrapper.find('[data-test="rc-path-line"]').exists()).toBe(false)
  })

  it('学生图谱页：路径行随选中的推荐项更新', async () => {
    const wrapper = await mountStudent(['A', 'B'], ['C', 'G'])
    expect(wrapper.get('[data-test="rc-path-line"]').text()).toBe('已掌握：知识点A、知识点B → 下一步：知识点C → 之后解锁：知识点D、知识点E')
    await wrapper.get('[data-test="rc-select-G"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-test="rc-path-line"]').text()).toBe('下一步：知识点G')
    wrapper.unmount()
  })
})
