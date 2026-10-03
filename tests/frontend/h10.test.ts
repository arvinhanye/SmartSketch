import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent, h } from 'vue'
import { createMemoryHistory, RouterView } from 'vue-router'
import { REVIEW_API_KEY, type ReviewApi } from '../../src/frontend/src/api/review'
import { createAppRouter } from '../../src/frontend/src/router'
import { useSessionStore } from '../../src/frontend/src/stores/session'
import ReviewView from '../../src/frontend/src/views/ReviewView.vue'
import type { components } from '../../src/contracts/v1/generated/typescript/openapi'
import { COURSES_API_KEY, type CoursesApi } from '../../src/frontend/src/api/courses'
import { ApiError, createHttpClient, TimeoutError, type FetchLike } from '../../src/frontend/src/api/http'
import { createVersionsApi, VERSIONS_API_KEY, type VersionsApi } from '../../src/frontend/src/api/versions'
import VersionPanel from '../../src/frontend/src/components/VersionPanel.vue'

type Course = components['schemas']['Course']
type GraphVersion = components['schemas']['GraphVersion']
type PublishResult = components['schemas']['PublishResult']

function course(cid: string, status: Course['status'] = 'revising', publishedVersion: number | null = 2): Course {
  return { id: cid, name: `课程 ${cid}`, status, my_role: 'teacher', published_version: publishedVersion,
    created_at: '2026-09-01T00:00:00Z' } as Course
}
function published(version: number): GraphVersion {
  return { version, kind: 'publish', published_at: '2026-09-25T00:00:00Z' }
}
function result(version: number, unchanged = false): PublishResult {
  return { version, unchanged, published_at: '2026-09-27T00:00:00Z',
    excluded: { low_confidence_nodes: 0, low_confidence_edges: 0, cascaded_edges: 0 } }
}
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => { resolve = done })
  return { promise, resolve }
}
function fixture(options: { get?: CoursesApi['get']; list?: VersionsApi['list']; publish?: VersionsApi['publish']; rollback?: VersionsApi['rollback'] } = {}) {
  const get = vi.fn<CoursesApi['get']>(options.get ?? (async (cid) => course(cid)))
  const list = vi.fn<VersionsApi['list']>(options.list ?? (async () => [published(1), published(2)]))
  const publish = vi.fn<VersionsApi['publish']>(options.publish ?? (async () => result(3)))
  const rollback = vi.fn<VersionsApi['rollback']>(options.rollback ?? (async () => result(3)))
  const courses: CoursesApi = { get, list: vi.fn(), create: vi.fn() }
  const versions: VersionsApi = { list, publish, rollback }
  const wrapper = mount(VersionPanel, { props: { courseId: 'c1' }, global: { provide: {
    [COURSES_API_KEY as symbol]: courses, [VERSIONS_API_KEY as symbol]: versions,
  } } })
  return { wrapper, get, list, publish, rollback }
}

describe('H10 version API', () => {
  it('uses the contract paths for list, publish and rollback', async () => {
    const calls: Array<{ url: string; method: string }> = []
    const fetch: FetchLike = async (url, init) => {
      calls.push({ url, method: init?.method ?? 'GET' })
      return new Response(JSON.stringify({}), { status: 200, headers: { 'Content-Type': 'application/json' } })
    }
    const api = createVersionsApi(createHttpClient({ fetch, getAccessToken: () => 'tok' }))
    await api.list('c/1')
    await api.publish('c/1')
    await api.rollback('c/1', 2)
    expect(calls).toEqual([
      { url: '/api/v1/courses/c%2F1/versions', method: 'GET' },
      { url: '/api/v1/courses/c%2F1/publish', method: 'POST' },
      { url: '/api/v1/courses/c%2F1/versions/2/rollback', method: 'POST' },
    ])
  })
})

describe('H10 version panel', () => {
  it('shows the committed student-visible version during draft revision and sorts history', async () => {
    const { wrapper } = fixture({ list: async () => [published(1), published(2)] })
    await flushPromises()
    expect(wrapper.get('[data-test="vp-current"]').text()).toContain('v2')
    expect(wrapper.get('[data-test="vp-revising"]').text()).toContain('草稿修订中')
    // 修订状态下仍说明学生当前看到的版本
    expect(wrapper.get('[data-test="vp-current"]').text()).toContain('学生当前看到')
    expect(wrapper.findAll('[data-test="vp-version"]').map((item) => item.text())).toEqual([
      expect.stringContaining('v2'), expect.stringContaining('v1'),
    ])
  })

  it('collapses version history by default without dropping the version state', async () => {
    const { wrapper, list } = fixture({ list: async () => [published(1), published(2)] })
    await flushPromises()
    const details = wrapper.get('details')
    expect(details.attributes('open')).toBeUndefined()
    // 折叠只影响展示：历史数据仍在，展开后可见
    expect(wrapper.get('[data-test="vp-version"]').isVisible()).toBe(false)
    await wrapper.get('summary').trigger('click')
    await flushPromises()
    expect(wrapper.get('details').attributes('open')).toBeDefined()
    expect(wrapper.findAll('[data-test="vp-version"]').map((item) => item.text())).toEqual([
      expect.stringContaining('v2'), expect.stringContaining('v1'),
    ])
    expect(list).toHaveBeenCalledTimes(1)
  })

  it('formats the published time in Chinese with an explicit timezone and never shows Invalid Date', async () => {
    const { wrapper } = fixture({
      list: async () => [
        { version: 2, kind: 'rollback', source_version: 1, published_at: '2026-09-25T00:00:00Z' },
        { version: 1, kind: 'publish', published_at: '' },
      ],
    })
    await flushPromises()
    await wrapper.get('summary').trigger('click')
    await flushPromises()
    const text = wrapper.text()
    expect(text).toContain('回滚自 v1')
    // 固定 Asia/Shanghai：UTC 零点显示为当地 08:00，并带出时区说明
    expect(text).toContain('2026年9月25日')
    expect(text).toContain('UTC+8')
    expect(text).toContain('发布时间未知')
    expect(text).not.toContain('Invalid Date')
    expect(text).not.toContain('2026-09-25T00:00:00Z')
  })

  it('keeps the rollback confirmation visible even when the history section is collapsed', async () => {
    const { wrapper } = fixture()
    await flushPromises()
    await wrapper.get('[data-test="vp-rollback"][data-version="1"]').trigger('click')
    // 触发回滚按钮需要展开历史；确认区不随折叠一起隐藏
    expect(wrapper.get('[data-test="vp-confirm"]').text()).toContain('v1')
    expect(wrapper.get('details').attributes('open')).toBeUndefined()
    expect(wrapper.get('[data-test="vp-confirm-rollback"]').isVisible()).toBe(true)
  })

  it('treats a never-published course whose published_version is omitted as having no current version', async () => {
    // 后端 Course 使用 response_model_exclude_none：从未发布时字段缺省而非 null（2026-09-27 联调发现）
    const { id, name, status, my_role, created_at } = course('c1', 'draft', null)
    const { wrapper } = fixture({ get: async () => ({ id, name, status, my_role, created_at }) as Course, list: async () => [] })
    await flushPromises()
    expect(wrapper.text()).not.toContain('不一致')
    expect(wrapper.find('[data-test="vp-publish"]').exists()).toBe(true)
  })

  it('does not query version history for a course student', async () => {
    const { wrapper, list, publish } = fixture({ get: async () => ({ ...course('c1'), my_role: 'student' }) })
    await flushPromises()
    expect(wrapper.get('[data-test="vp-not-teacher"]').text()).toContain('教师')
    expect(list).not.toHaveBeenCalled()
    expect(publish).not.toHaveBeenCalled()
  })

  it('hides cached history and write controls if a teacher loses course permission on refresh', async () => {
    let role: Course['my_role'] = 'teacher'
    const { wrapper } = fixture({ get: async () => ({ ...course('c1'), my_role: role }) })
    await flushPromises()
    expect(wrapper.find('[data-test="vp-publish"]').exists()).toBe(true)
    role = 'student'
    await wrapper.get('[data-test="vp-refresh"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-test="vp-not-teacher"]').text()).toContain('教师')
    expect(wrapper.find('[data-test="vp-publish"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="vp-version"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="vp-current"]').exists()).toBe(false)
  })

  it('keeps the old version after a rejected publish and shows a fixed error', async () => {
    const { wrapper, publish } = fixture({ publish: async () => {
      throw new ApiError(409, { code: 'PUBLISH_BLOCKED', message: 'server private text' })
    } })
    await flushPromises()
    await wrapper.get('[data-test="vp-publish"]').trigger('click')
    await flushPromises()
    expect(publish).toHaveBeenCalledTimes(1)
    expect(wrapper.get('[data-test="vp-current"]').text()).toContain('v2')
    expect(wrapper.get('[data-test="vp-error"]').text()).toContain('发布校验未通过')
    expect(wrapper.get('[data-test="vp-error"]').text()).not.toContain('server private text')
  })

  it('displays the rollback target before writing and refreshes only after success', async () => {
    let current = course('c1')
    const { wrapper, rollback } = fixture({
      get: async () => current,
      list: async () => current.published_version === 3
        ? [{ version: 3, kind: 'rollback', source_version: 1, published_at: '2026-09-27T00:00:00Z' }, published(2), published(1)]
        : [published(1), published(2)],
      rollback: async () => { current = course('c1', 'published', 3); return result(3) },
    })
    await flushPromises()
    await wrapper.get('[data-test="vp-rollback"][data-version="1"]').trigger('click')
    expect(wrapper.get('[data-test="vp-confirm"]').text()).toContain('v1')
    expect(wrapper.get('[data-test="vp-current"]').text()).toContain('v2')
    expect(rollback).not.toHaveBeenCalled()
    await wrapper.get('[data-test="vp-confirm-rollback"]').trigger('click')
    await flushPromises()
    expect(rollback).toHaveBeenCalledWith('c1', 1, expect.anything())
    expect(wrapper.get('[data-test="vp-current"]').text()).toContain('v3')
    expect(wrapper.find('[data-test="vp-confirm"]').exists()).toBe(false)
  })

  it('does not advance the visible version until course detail refresh confirms publish', async () => {
    const fresh = deferred<Course>()
    let reads = 0
    const { wrapper } = fixture({
      get: async () => ++reads === 1 ? course('c1') : fresh.promise,
      list: async () => reads === 1 ? [published(1), published(2)] : [published(1), published(2), published(3)],
      publish: async () => result(3),
    })
    await flushPromises()
    await wrapper.get('[data-test="vp-publish"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-test="vp-current"]').text()).toContain('v2')
    expect(wrapper.get('[data-test="vp-publish"]').attributes('disabled')).toBeDefined()
    fresh.resolve(course('c1', 'published', 3))
    await flushPromises()
    expect(wrapper.get('[data-test="vp-current"]').text()).toContain('v3')
  })

  it('marks a successful write as unconfirmed if refresh still reports the old pointer', async () => {
    const { wrapper } = fixture({ publish: async () => result(3) })
    await flushPromises()
    await wrapper.get('[data-test="vp-publish"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-test="vp-current"]').text()).toContain('v2')
    expect(wrapper.get('[data-test="vp-error"]').text()).toContain('状态刷新')
    expect(wrapper.get('[data-test="vp-publish"]').attributes('disabled')).toBeDefined()
  })

  it('does not confirm a new pointer absent from the refreshed version history', async () => {
    let reads = 0
    const { wrapper } = fixture({ get: async () => ++reads === 1 ? course('c1') : course('c1', 'published', 3),
      list: async () => [published(1), published(2)], publish: async () => result(3) })
    await flushPromises()
    await wrapper.get('[data-test="vp-publish"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-test="vp-current"]').text()).toContain('v2')
    expect(wrapper.find('[data-test="vp-notice"]').exists()).toBe(false)
    expect(wrapper.get('[data-test="vp-error"]').text()).toContain('状态刷新未确认')
    expect(wrapper.get('[data-test="vp-publish"]').attributes('disabled')).toBeDefined()
  })

  it('pauses another write after a timeout until the course pointer is rechecked', async () => {
    const { wrapper, publish } = fixture({ publish: async () => { throw new TimeoutError(30_000) } })
    await flushPromises()
    await wrapper.get('[data-test="vp-publish"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-test="vp-current"]').text()).toContain('v2')
    expect(wrapper.get('[data-test="vp-error"]').text()).toContain('结果未确认')
    expect(wrapper.get('[data-test="vp-publish"]').attributes('disabled')).toBeDefined()
    await wrapper.get('[data-test="vp-refresh"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-test="vp-publish"]').attributes('disabled')).toBeUndefined()
    expect(publish).toHaveBeenCalledTimes(1)
  })

  it('ignores a late old-course response after switching courses', async () => {
    const old = deferred<Course>()
    const { wrapper } = fixture({ get: (cid) => cid === 'c1' ? old.promise : Promise.resolve(course('c2', 'published', 5)),
      list: async (cid) => cid === 'c1' ? [published(1), published(2)] : [published(5)] })
    await wrapper.setProps({ courseId: 'c2' })
    await flushPromises()
    old.resolve(course('c1'))
    await flushPromises()
    expect(wrapper.get('[data-test="vp-current"]').text()).toContain('v5')
    expect(wrapper.get('[data-test="vp-current"]').text()).not.toContain('v2')
  })
})


describe('H10 review-page integration', () => {
  it('shows the version panel beside the review queue for a course teacher', async () => {
    sessionStorage.clear()
    const pinia = createPinia()
    setActivePinia(pinia)
    const session = useSessionStore(pinia)
    session.signIn({ access_token: 'tok', token_type: 'bearer', expires_in: 3600,
      user: { id: 'u1', username: 'teacher', role: 'teacher' } })
    const router = createAppRouter({ history: createMemoryHistory(), getAccountRole: () => session.role,
      coursesComponent: defineComponent({ render: () => h('div') }), reviewComponent: ReviewView })
    await router.push('/courses/c1/review')
    await router.isReady()
    const review: ReviewApi = {
      getQueue: async () => ({ low_confidence_relations: [], suspected_duplicates: [], isolated_nodes: [],
        totals: { low_confidence_relations: 0, suspected_duplicates: 0, isolated_nodes: 0 },
        next_cursors: { low_confidence_relations: null, suspected_duplicates: null, isolated_nodes: null } }),
      resolve: vi.fn(),
    }
    const wrapper = mount(defineComponent({ render: () => h(RouterView) }), { global: { plugins: [pinia, router], provide: {
      [COURSES_API_KEY as symbol]: { get: async () => course('c1'), list: vi.fn(), create: vi.fn() },
      [REVIEW_API_KEY as symbol]: review,
      [VERSIONS_API_KEY as symbol]: { list: async () => [published(1), published(2)], publish: vi.fn(), rollback: vi.fn() },
    } } })
    await flushPromises()
    expect(wrapper.find('[data-test="rv-all-empty"]').exists()).toBe(true)
    expect(wrapper.get('[data-test="version-panel"]').text()).toContain('学生当前看到 v2')
  })

  it('keeps the version history folded and after the review area without duplicating panel state', async () => {
    sessionStorage.clear()
    const pinia = createPinia()
    setActivePinia(pinia)
    const session = useSessionStore(pinia)
    session.signIn({ access_token: 'tok', token_type: 'bearer', expires_in: 3600,
      user: { id: 'u1', username: 'teacher', role: 'teacher' } })
    const router = createAppRouter({ history: createMemoryHistory(), getAccountRole: () => session.role,
      coursesComponent: defineComponent({ render: () => h('div') }), reviewComponent: ReviewView })
    await router.push('/courses/c1/review')
    await router.isReady()
    const review: ReviewApi = {
      getQueue: async () => ({ low_confidence_relations: [], suspected_duplicates: [], isolated_nodes: [],
        totals: { low_confidence_relations: 0, suspected_duplicates: 0, isolated_nodes: 0 },
        next_cursors: { low_confidence_relations: null, suspected_duplicates: null, isolated_nodes: null } }),
      resolve: vi.fn(),
    }
    const list = vi.fn(async () => [published(1), published(2)])
    const wrapper = mount(defineComponent({ render: () => h(RouterView) }), { global: { plugins: [pinia, router], provide: {
      [COURSES_API_KEY as symbol]: { get: async () => course('c1'), list: vi.fn(), create: vi.fn() },
      [REVIEW_API_KEY as symbol]: review,
      [VERSIONS_API_KEY as symbol]: { list, publish: vi.fn(), rollback: vi.fn() },
    } } })
    await flushPromises()
    // 只挂载一个版本面板、只请求一次版本历史：发布栏与历史共用同一份版本状态
    expect(wrapper.findAll('[data-test="version-panel"]')).toHaveLength(1)
    expect(list).toHaveBeenCalledTimes(1)
    // 标题在发布栏之前，版本历史在审核区之后
    const all = Array.from(wrapper.element.querySelectorAll('*'))
    const at = (selector: string) => all.indexOf(wrapper.get(selector).element as Element)
    expect(at('#review-title')).toBeLessThan(at('[data-test="vp-publish"]'))
    expect(at('.review-card')).toBeLessThan(at('.history'))
    // 版本历史仍默认折叠
    expect(wrapper.get('details').attributes('open')).toBeUndefined()
  })

  it('keeps the navigation and title visible while the version request is pending or failing', async () => {
    sessionStorage.clear()
    const pinia = createPinia()
    setActivePinia(pinia)
    const session = useSessionStore(pinia)
    session.signIn({ access_token: 'tok', token_type: 'bearer', expires_in: 3600,
      user: { id: 'u1', username: 'teacher', role: 'teacher' } })
    const router = createAppRouter({ history: createMemoryHistory(), getAccountRole: () => session.role,
      coursesComponent: defineComponent({ render: () => h('div') }), reviewComponent: ReviewView })
    await router.push('/courses/c1/review')
    await router.isReady()
    const review: ReviewApi = {
      getQueue: async () => ({ low_confidence_relations: [], suspected_duplicates: [], isolated_nodes: [],
        totals: { low_confidence_relations: 1, suspected_duplicates: 0, isolated_nodes: 0 },
        next_cursors: { low_confidence_relations: null, suspected_duplicates: null, isolated_nodes: null } }),
      resolve: vi.fn(),
    }
    const gateway = deferred<GraphVersion[]>()
    const wrapper = mount(defineComponent({ render: () => h(RouterView) }), { global: { plugins: [pinia, router], provide: {
      [COURSES_API_KEY as symbol]: { get: async () => course('c1'), list: vi.fn(), create: vi.fn() },
      [REVIEW_API_KEY as symbol]: review,
      [VERSIONS_API_KEY as symbol]: { list: () => gateway.promise, publish: vi.fn(), rollback: vi.fn() },
    } } })
    await flushPromises()
    expect(wrapper.find('[data-test="vp-loading"]').exists()).toBe(true)
    expect(wrapper.get('[data-test="rv-back"]').exists()).toBe(true)
    expect(wrapper.get('#review-title').text()).toBe('审核队列')
    expect(wrapper.find('[data-test="rv-all-empty"]').exists()).toBe(false)
    gateway.resolve([published(1), published(2)])
    await flushPromises()
    expect(wrapper.get('[data-test="vp-current"]').text()).toContain('v2')
    expect(wrapper.get('[data-test="rv-back"]').exists()).toBe(true)
  })
})
