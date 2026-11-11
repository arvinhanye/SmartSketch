import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { createMemoryHistory } from 'vue-router'
import { COURSES_API_KEY, type Course, type CoursesApi } from '../../src/frontend/src/api/courses'
import { PROGRESS_API_KEY, type ProgressApi, type ProgressResponse } from '../../src/frontend/src/api/progress'
import { RECOMMEND_API_KEY, type RecommendApi, type RecommendResponse } from '../../src/frontend/src/api/recommend'
import { lastActivity, resumeReason, summarizeProgress } from '../../src/frontend/src/composables/resumeLearning'
import { createAppRouter } from '../../src/frontend/src/router'
import { useSessionStore } from '../../src/frontend/src/stores/session'
import CoursesView from '../../src/frontend/src/views/CoursesView.vue'

// UI-PINE-01：学生课程列表页顶部的「继续学习」主卡（设计预览 v3）。
// 选最近有学习记录的已发布课程；读它的进度与下一步推荐；读取失败时主卡不出现，不影响课程列表。

const base: Course = { id: 'c1', name: '数据结构', description: null, status: 'published', my_role: 'student', teacher_id: 't1', kp_count: 3, published_version: 1, created_at: '2026-10-01T00:00:00Z' }
const courseA: Course = { ...base, id: 'cA', name: '栈与队列' }
const courseB: Course = { ...base, id: 'cB', name: '进程与线程' }
const draft: Course = { ...base, id: 'cD', name: '未发布课程', status: 'draft', published_version: null }

function progress(entries: Array<[string, 'mastered' | 'learning' | 'unknown', string | null]>, version = 1): ProgressResponse {
  return {
    graph_version: version,
    entries: entries.map(([kp_id, status, updated_at]) => ({ kp_id, status, own_status: updated_at === null ? null : status, inherited_from: [], updated_at })),
  } as ProgressResponse
}
function recommend(name: string, unlock: number, kp = 'k9', version = 1): RecommendResponse {
  return {
    state: 'recommendations',
    graph_version: version,
    total_eligible: 4,
    recommendations: [{ kp_id: kp, name, graph_version: version, score: 1, unlock_count: unlock, reason: '服务端理由', factors: {}, weighted: {}, reason_facts: {} }],
  } as unknown as RecommendResponse
}

describe('继续学习：纯函数', () => {
  it('最近学习时间取自身行 updated_at 的最大值；没有自身行时为 null', () => {
    expect(lastActivity(progress([['a', 'mastered', '2026-11-01T10:00:00Z'], ['b', 'learning', '2026-11-02T09:00:00Z'], ['c', 'unknown', null]]))).toBe('2026-11-02T09:00:00Z')
    expect(lastActivity(progress([['a', 'unknown', null]]))).toBeNull()
  })
  it('进度统计按 status（含继承）计数', () => {
    expect(summarizeProgress(progress([['a', 'mastered', null], ['b', 'learning', null], ['c', 'unknown', null], ['d', 'mastered', null]]))).toEqual({ mastered: 2, learning: 1, total: 4 })
  })
  it('理由是一句短语：能解锁就说解锁几个，否则说明前置已掌握；全部掌握另有一句', () => {
    expect(resumeReason(recommend('后缀表达式求值', 2))).toBe('学完可解锁 2 个知识点')
    expect(resumeReason(recommend('循环队列', 0))).toBe('前置知识已掌握')
    expect(resumeReason({ state: 'all_mastered', graph_version: 1, recommendations: [] } as unknown as RecommendResponse)).toBe('本课程知识点已全部掌握')
  })
})

const Page = defineComponent({ render: () => h('p', '页面') })
beforeEach(() => sessionStorage.clear())
afterEach(() => vi.restoreAllMocks())

async function mountView(opts: { role?: 'student' | 'teacher'; courses?: Course[]; progress?: ProgressApi['get']; recommend?: RecommendApi['get'] }) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const role = opts.role ?? 'student'
  const session = useSessionStore()
  session.signIn({ access_token: 'test-token', token_type: 'bearer', expires_in: 3600, user: { id: 'u1', username: 'stu', role } })
  const courses = opts.courses ?? [courseA, courseB]
  const api: CoursesApi = { list: async () => courses, get: async (id) => courses.find((c) => c.id === id)!, create: async (body) => ({ ...base, name: body.name }) }
  const progressApi: ProgressApi = { get: opts.progress ?? (async () => progress([['a', 'unknown', null]])), update: async () => progress([['a', 'unknown', null]]) }
  const recommendApi: RecommendApi = { get: opts.recommend ?? (async () => recommend('后缀表达式求值', 1)) }
  const router = createAppRouter({ history: createMemoryHistory(), getAccountRole: () => session.role, coursesComponent: CoursesView, studentGraphComponent: Page, teacherGraphComponent: Page, materialsComponent: Page, reviewComponent: Page, membersComponent: Page, chatComponent: Page })
  await router.push(role === 'teacher' ? '/teacher' : '/student')
  await router.isReady()
  const wrapper = mount(CoursesView, {
    global: { plugins: [pinia, router], provide: { [COURSES_API_KEY as symbol]: api, [PROGRESS_API_KEY as symbol]: progressApi, [RECOMMEND_API_KEY as symbol]: recommendApi } },
  })
  await flushPromises()
  return { wrapper, router }
}

describe('继续学习主卡', () => {
  it('选最近学过的课程，显示下一步、短理由与掌握数，按钮直达该知识点', async () => {
    const recommendCalls: string[] = []
    const { wrapper } = await mountView({
      progress: async (cid) => (cid === 'cB'
        ? progress([['a', 'mastered', '2026-11-03T08:00:00Z'], ['b', 'learning', '2026-11-03T09:00:00Z'], ['c', 'unknown', null]])
        : progress([['x', 'mastered', '2026-10-20T08:00:00Z'], ['y', 'unknown', null]])),
      recommend: async (cid) => { recommendCalls.push(cid); return recommend('程序与进程', 2, 'k7') },
    })
    const card = wrapper.get('[data-test="resume-card"]')
    expect(card.text()).toContain('进程与线程')
    expect(card.text()).toContain('程序与进程')
    expect(card.text()).toContain('学完可解锁 2 个知识点')
    expect(card.get('[data-test="resume-progress"]').attributes('aria-label')).toBe('3 个知识点中已掌握 1 个，学习中 1 个')
    expect(recommendCalls).toEqual(['cB'])
    const go = card.get('[data-test="resume-go"]')
    expect(go.attributes('href')).toContain('/courses/cB/graph')
    expect(go.attributes('href')).toContain('kp=k7')
    expect(go.attributes('href')).toContain('v=1')
    expect(wrapper.findAll('[data-test="course-card"]')).toHaveLength(2)
  })

  it('从没学过时选第一门已发布课程，主卡写「开始学习」；未发布课程不参与', async () => {
    const { wrapper } = await mountView({ courses: [draft, courseA, courseB] })
    const card = wrapper.get('[data-test="resume-card"]')
    expect(card.text()).toContain('开始学习')
    expect(card.text()).toContain('栈与队列')
  })

  it('全部掌握时不给下一步按钮的知识点，只进入图谱', async () => {
    const { wrapper } = await mountView({ recommend: async () => ({ state: 'all_mastered', graph_version: 1, recommendations: [] }) as unknown as RecommendResponse })
    const card = wrapper.get('[data-test="resume-card"]')
    expect(card.text()).toContain('本课程知识点已全部掌握')
    expect(card.get('[data-test="resume-go"]').attributes('href')).not.toContain('kp=')
  })

  it('进度或推荐读取失败：主卡不出现，课程列表照常显示', async () => {
    const { wrapper } = await mountView({ recommend: async () => { throw new Error('boom') } })
    expect(wrapper.find('[data-test="resume-card"]').exists()).toBe(false)
    expect(wrapper.findAll('[data-test="course-card"]')).toHaveLength(2)
  })

  it('教师首页没有继续学习主卡', async () => {
    const { wrapper } = await mountView({ role: 'teacher', courses: [{ ...courseA, my_role: 'teacher' }] })
    expect(wrapper.find('[data-test="resume-card"]').exists()).toBe(false)
  })
})
