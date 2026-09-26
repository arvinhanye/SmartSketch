import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, nextTick, ref } from 'vue'
import type { components } from '../../src/contracts/v1/generated/typescript/openapi'
import { HTTP_CLIENT_KEY } from '../../src/frontend/src/api/client'
import { ApiError, createHttpClient, NetworkError, type FetchLike } from '../../src/frontend/src/api/http'
import {
  createKnowledgeDetailApi,
  KNOWLEDGE_DETAIL_API_KEY,
  type KnowledgeDetailApi,
} from '../../src/frontend/src/api/knowledgeDetail'
import KnowledgeDetail from '../../src/frontend/src/components/KnowledgeDetail.vue'
import {
  highlightSegments,
  toKnowledgeDetailView,
  toSourceView,
  useKnowledgeDetail,
} from '../../src/frontend/src/composables/useKnowledgeDetail'
import { useCourseStore } from '../../src/frontend/src/stores/course'

type KnowledgePointDetail = components['schemas']['KnowledgePointDetail']
type SourceRef = components['schemas']['SourceRef']
type ErrorCode = components['schemas']['ErrorCode']

function detail(id: string, overrides: Partial<KnowledgePointDetail> = {}): KnowledgePointDetail {
  return {
    id,
    course_id: 'c1',
    chapter_id: 'ch3',
    name: `知识点 ${id}`,
    aliases: [],
    type: 'concept',
    definition: `${id} 的定义`,
    level: 1,
    confidence: 0.9,
    status: 'approved',
    source: 'ai',
    locked: false,
    revision: 1,
    source_refs: [{ chunk_id: `${id}-chunk`, document_id: 'doc1', page: 3, text: `原文提到 知识点 ${id}。` }],
    prerequisites: [],
    successors: [],
    related: [],
    ...overrides,
  }
}

function apiError(status: number, code: ErrorCode): ApiError {
  return new ApiError(status, { code, message: '服务端原文不应被展示' })
}

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

function fakeApi(get: KnowledgeDetailApi['get'] = async (_cid, kid) => detail(kid)) {
  return { get: vi.fn<KnowledgeDetailApi['get']>(get) }
}

let pinia: Pinia

beforeEach(() => {
  pinia = createPinia()
  setActivePinia(pinia)
  useCourseStore(pinia).selectCourse('c1')
})

afterEach(() => {
  vi.restoreAllMocks()
  delete (window as unknown as Record<string, unknown>).__h06xss
})

function mountDetail(
  api: KnowledgeDetailApi | null,
  props: { kpId: string | null; documentNames?: Record<string, string> } = { kpId: 'k1' },
  provide: Record<symbol, unknown> = {},
) {
  return mount(KnowledgeDetail, {
    props,
    attachTo: document.body,
    global: {
      plugins: [pinia],
      provide: { ...(api ? { [KNOWLEDGE_DETAIL_API_KEY as symbol]: api } : {}), ...provide },
    },
  })
}

// ---------------------------------------------------------------- API 封装

describe('H06 知识点详情 API 封装', () => {
  it('按契约路径 GET 并逐段编码参数，带令牌', async () => {
    const calls: { url: string; init: RequestInit | undefined }[] = []
    const fetch: FetchLike = async (url, init) => {
      calls.push({ url, init })
      return new Response(JSON.stringify(detail('k/1')), { status: 200 })
    }
    const api = createKnowledgeDetailApi(createHttpClient({ fetch, getAccessToken: () => 'tok' }))
    const result = await api.get('c 1', 'k/1')
    expect(result.id).toBe('k/1')
    expect(calls).toHaveLength(1)
    expect(calls[0]!.url).toBe('/api/v1/courses/c%201/kp/k%2F1')
    expect(calls[0]!.init?.method).toBe('GET')
    expect(new Headers(calls[0]!.init?.headers).get('Authorization')).toBe('Bearer tok')
  })
})

// ---------------------------------------------------------------- 视图模型

describe('H06 来源视图模型', () => {
  const base = { chunk_id: 'ch', document_id: 'd' }

  it('页码与章节都可定位时都保留', () => {
    const view = toSourceView({ ...base, page: 4, section_path: '第3章 > 3.1 栈', text: '片段' })
    expect(view).toMatchObject({ documentId: 'd', chunkId: 'ch', page: 4, sectionPath: '第3章 > 3.1 栈', excerpt: '片段' })
    expect(view?.locationLabel).toBe('第 4 页 · 第3章 > 3.1 栈')
  })

  it('只有章节时不编造页码', () => {
    const view = toSourceView({ ...base, section_path: '第2章' })
    expect(view?.page).toBeUndefined()
    expect(view?.locationLabel).toBe('第2章')
    expect(view?.locationLabel).not.toContain('页')
  })

  it('只有页码时不编造章节，无原文片段时不补文字', () => {
    const view = toSourceView({ ...base, page: 1 })
    expect(view?.sectionPath).toBeUndefined()
    expect(view?.excerpt).toBeUndefined()
    expect(view?.locationLabel).toBe('第 1 页')
  })

  it.each<[string, Partial<SourceRef> & Record<string, unknown>]>([
    ['页码为 0 且无章节', { page: 0 }],
    ['页码为小数', { page: 2.5 }],
    ['页码为字符串', { page: '3' }],
    ['章节为空串', { section_path: '' }],
    ['章节只有空白', { section_path: '   ' }],
    ['页码为 null', { page: null }],
    ['两者都没有', {}],
  ])('无法定位（%s）时丢弃', (_, extra) => {
    expect(toSourceView({ ...base, ...extra } as SourceRef)).toBeNull()
  })

  it.each<[string, Record<string, unknown>]>([
    ['缺 document_id', { chunk_id: 'ch', page: 1 }],
    ['document_id 为空', { chunk_id: 'ch', document_id: '', page: 1 }],
    ['缺 chunk_id', { document_id: 'd', page: 1 }],
  ])('来源身份不完整（%s）时丢弃', (_, raw) => {
    expect(toSourceView(raw as unknown as SourceRef)).toBeNull()
  })

  it('无效页码但章节有效时只保留章节', () => {
    const view = toSourceView({ ...base, page: -1, section_path: '第1章' } as SourceRef)
    expect(view?.page).toBeUndefined()
    expect(view?.locationLabel).toBe('第1章')
  })

  it('详情视图统计被丢弃的来源，不修改输入', () => {
    const raw = detail('k1', {
      source_refs: [
        { chunk_id: 'a', document_id: 'd', page: 2 },
        { chunk_id: 'b', document_id: 'd', page: 0 } as SourceRef,
      ],
    })
    const frozen = JSON.parse(JSON.stringify(raw)) as KnowledgePointDetail
    const view = toKnowledgeDetailView(raw)
    expect(view.sources.map((s) => s.chunkId)).toEqual(['a'])
    expect(view.droppedSources).toBe(1)
    expect(raw).toEqual(frozen)
  })

  it('同一来源重复出现时键仍唯一', () => {
    const src = { chunk_id: 'a', document_id: 'd', page: 2 }
    const view = toKnowledgeDetailView(detail('k1', { source_refs: [src, { ...src }] }))
    const keys = view.sources.map((s) => s.key)
    expect(new Set(keys).size).toBe(keys.length)
  })

  it('高亮切分按最长词、不解释正则与 HTML', () => {
    expect(highlightSegments('用 C++ 实现栈，栈顶', ['栈', 'C++', '栈顶'])).toEqual([
      { text: '用 ', mark: false },
      { text: 'C++', mark: true },
      { text: ' 实现', mark: false },
      { text: '栈', mark: true },
      { text: '，', mark: false },
      { text: '栈顶', mark: true },
    ])
    expect(highlightSegments('<b>x</b>', ['.*'])).toEqual([{ text: '<b>x</b>', mark: false }])
    expect(highlightSegments('abc', ['', '  '])).toEqual([{ text: 'abc', mark: false }])
  })
})

// ---------------------------------------------------------------- composable：迟到请求

describe('H06 迟到请求隔离', () => {
  function harness(api: KnowledgeDetailApi, initial: string | null = 'k1', onCourseForbidden = vi.fn()) {
    const kpId = ref<string | null>(initial)
    let state!: ReturnType<typeof useKnowledgeDetail>
    const Host = defineComponent({
      setup() {
        state = useKnowledgeDetail({ api, kpId, onCourseForbidden })
        return () => h('div')
      },
    })
    const wrapper = mount(Host, { global: { plugins: [pinia] } })
    return { wrapper, kpId, state: () => state, onCourseForbidden }
  }

  it('快速切换节点时旧响应不覆盖新选择，旧请求被中止', async () => {
    const pending = new Map<string, ReturnType<typeof deferred<KnowledgePointDetail>>>()
    const signals = new Map<string, AbortSignal | undefined>()
    const api = fakeApi((_cid, kid, control) => {
      const d = deferred<KnowledgePointDetail>()
      pending.set(kid, d)
      signals.set(kid, control?.signal)
      return d.promise
    })
    const { kpId, state } = harness(api)
    await flushPromises()
    kpId.value = 'k2'
    await flushPromises()
    expect(signals.get('k1')?.aborted).toBe(true)
    expect(signals.get('k2')?.aborted).toBe(false)

    pending.get('k2')!.resolve(detail('k2'))
    await flushPromises()
    pending.get('k1')!.resolve(detail('k1'))
    await flushPromises()
    expect(state().status.value).toBe('ready')
    expect(state().detail.value?.id).toBe('k2')
  })

  it('旧响应先到时仍保持加载，不闪现旧节点', async () => {
    const pending = new Map<string, ReturnType<typeof deferred<KnowledgePointDetail>>>()
    const api = fakeApi((_cid, kid) => {
      const d = deferred<KnowledgePointDetail>()
      pending.set(kid, d)
      return d.promise
    })
    const { kpId, state } = harness(api)
    await flushPromises()
    kpId.value = 'k2'
    await flushPromises()
    pending.get('k1')!.resolve(detail('k1'))
    await flushPromises()
    expect(state().status.value).toBe('loading')
    expect(state().detail.value).toBeNull()
    pending.get('k2')!.resolve(detail('k2'))
    await flushPromises()
    expect(state().detail.value?.id).toBe('k2')
  })

  it('旧请求的迟到失败不改写新选择的状态', async () => {
    const pending = new Map<string, ReturnType<typeof deferred<KnowledgePointDetail>>>()
    const api = fakeApi((_cid, kid) => {
      const d = deferred<KnowledgePointDetail>()
      pending.set(kid, d)
      return d.promise
    })
    const { kpId, state } = harness(api)
    await flushPromises()
    kpId.value = 'k2'
    await flushPromises()
    pending.get('k2')!.resolve(detail('k2'))
    await flushPromises()
    pending.get('k1')!.reject(new NetworkError(new Error('late')))
    await flushPromises()
    expect(state().status.value).toBe('ready')
    expect(state().error.value).toBeNull()
  })

  it('A→B→A 时第一次 A 的迟到响应被丢弃', async () => {
    const calls: { kid: string; d: ReturnType<typeof deferred<KnowledgePointDetail>> }[] = []
    const api = fakeApi((_cid, kid) => {
      const d = deferred<KnowledgePointDetail>()
      calls.push({ kid, d })
      return d.promise
    })
    const { kpId, state } = harness(api)
    await flushPromises()
    kpId.value = 'k2'
    await flushPromises()
    kpId.value = 'k1'
    await flushPromises()
    expect(calls.map((c) => c.kid)).toEqual(['k1', 'k2', 'k1'])
    calls[0]!.d.resolve(detail('k1', { definition: '过期定义' }))
    await flushPromises()
    expect(state().detail.value).toBeNull()
    calls[2]!.d.resolve(detail('k1', { definition: '最新定义' }))
    await flushPromises()
    expect(state().detail.value?.definition).toBe('最新定义')
  })

  it('切课后旧课程的响应被丢弃，请求被中止', async () => {
    const d = deferred<KnowledgePointDetail>()
    let signal: AbortSignal | undefined
    const api = fakeApi((_cid, _kid, control) => {
      signal = control?.signal
      return d.promise
    })
    const { state } = harness(api)
    await flushPromises()
    useCourseStore(pinia).selectCourse('c2')
    await flushPromises()
    expect(signal?.aborted).toBe(true)
    d.resolve(detail('k1'))
    await flushPromises()
    expect(state().detail.value).toBeNull()
  })

  it('响应的课程或知识点与请求不符时不展示', async () => {
    const api = fakeApi(async (_cid, kid) => detail(kid, { course_id: 'c_other' }))
    const { state } = harness(api)
    await flushPromises()
    expect(state().detail.value).toBeNull()
    expect(state().status.value).toBe('error')

    const api2 = fakeApi(async () => detail('k_other'))
    const h2 = harness(api2)
    await flushPromises()
    expect(h2.state().detail.value).toBeNull()
    expect(h2.state().status.value).toBe('error')
  })

  it('卸载后中止在途请求，迟到响应不写入', async () => {
    const d = deferred<KnowledgePointDetail>()
    let signal: AbortSignal | undefined
    const api = fakeApi((_cid, _kid, control) => {
      signal = control?.signal
      return d.promise
    })
    const { wrapper, state } = harness(api)
    await flushPromises()
    wrapper.unmount()
    expect(signal?.aborted).toBe(true)
    d.resolve(detail('k1'))
    await flushPromises()
    expect(state().detail.value).toBeNull()
  })

  it('取消选择回到空态并中止请求', async () => {
    let signal: AbortSignal | undefined
    const api = fakeApi((_cid, _kid, control) => {
      signal = control?.signal
      return new Promise(() => undefined)
    })
    const { kpId, state } = harness(api)
    await flushPromises()
    kpId.value = null
    await flushPromises()
    expect(signal?.aborted).toBe(true)
    expect(state().status.value).toBe('idle')
  })

  it('未选课程时不发请求', async () => {
    useCourseStore(pinia).selectCourse(null)
    const api = fakeApi()
    const { state } = harness(api)
    await flushPromises()
    expect(api.get).not.toHaveBeenCalled()
    expect(state().status.value).toBe('idle')
  })

  it('COURSE_FORBIDDEN 交给调用方', async () => {
    const api = fakeApi(async () => {
      throw apiError(403, 'COURSE_FORBIDDEN')
    })
    const { onCourseForbidden, state } = harness(api)
    await flushPromises()
    expect(onCourseForbidden).toHaveBeenCalledTimes(1)
    expect(state().detail.value).toBeNull()
  })
})

// ---------------------------------------------------------------- 组件

describe('H06 知识点详情组件', () => {
  it('未选节点时显示空态提示，不发请求', async () => {
    const api = fakeApi()
    const wrapper = mountDetail(api, { kpId: null })
    await flushPromises()
    expect(api.get).not.toHaveBeenCalled()
    expect(wrapper.get('[data-test="kd-empty"]').text()).toContain('点击图谱中的知识点')
  })

  it('加载态有 role=status 与 aria-busy', async () => {
    const api = fakeApi(() => new Promise(() => undefined))
    const wrapper = mountDetail(api)
    await flushPromises()
    const loading = wrapper.get('[data-test="kd-loading"]')
    expect(loading.attributes('role')).toBe('status')
    expect(wrapper.get('[data-test="knowledge-detail"]').attributes('aria-busy')).toBe('true')
  })

  it('展示名称、类型、别名、定义与关系，区域有可访问名称', async () => {
    const api = fakeApi(async (_cid, kid) =>
      detail(kid, {
        name: '栈',
        aliases: ['堆栈'],
        type: 'concept',
        definition: '后进先出的线性表',
        prerequisites: [{ id: 'k0', name: '线性表' }],
        successors: [{ id: 'k2', name: '表达式求值' }],
        related: [],
      }),
    )
    const wrapper = mountDetail(api)
    await flushPromises()
    const root = wrapper.get('[data-test="knowledge-detail"]')
    expect(root.attributes('aria-busy')).toBe('false')
    const labelledBy = root.attributes('aria-labelledby')
    expect(labelledBy).toBeTruthy()
    expect(wrapper.get(`#${labelledBy}`).text()).toBe('栈')
    expect(wrapper.get('[data-test="kd-type"]').text()).toBe('概念')
    expect(wrapper.get('[data-test="kd-aliases"]').text()).toContain('堆栈')
    expect(wrapper.get('[data-test="kd-definition"]').text()).toBe('后进先出的线性表')
    expect(wrapper.get('[data-test="kd-prerequisites"]').text()).toContain('线性表')
    expect(wrapper.get('[data-test="kd-successors"]').text()).toContain('表达式求值')
    expect(wrapper.get('[data-test="kd-related"]').text()).toContain('无')
  })

  it('就绪后焦点移到标题，便于屏幕阅读器播报', async () => {
    const wrapper = mountDetail(fakeApi())
    await flushPromises()
    await nextTick()
    expect(document.activeElement).toBe(wrapper.get('[data-test="kd-title"]').element)
  })

  it('点击关联知识点请求切换选择', async () => {
    const api = fakeApi(async (_cid, kid) => detail(kid, { prerequisites: [{ id: 'k0', name: '线性表' }] }))
    const wrapper = mountDetail(api)
    await flushPromises()
    await wrapper.get('[data-test="kd-prerequisites"] button').trigger('click')
    expect(wrapper.emitted('selectKnowledgePoint')).toEqual([['k0']])
  })

  it('点击来源定位页码或章节，并标记当前来源', async () => {
    const api = fakeApi(async (_cid, kid) =>
      detail(kid, {
        source_refs: [
          { chunk_id: 'c-a', document_id: 'doc1', page: 7, text: '片段 A' },
          { chunk_id: 'c-b', document_id: 'doc2', section_path: '第3章 > 3.2 队列' },
        ],
      }),
    )
    const wrapper = mountDetail(api, { kpId: 'k1', documentNames: { doc1: '数据结构讲义.pdf' } })
    await flushPromises()
    const buttons = wrapper.findAll('[data-test="kd-source-locate"]')
    expect(buttons).toHaveLength(2)
    expect(buttons[0]!.text()).toContain('数据结构讲义.pdf')
    expect(buttons[0]!.text()).toContain('第 7 页')
    expect(buttons[1]!.text()).toContain('第3章 > 3.2 队列')
    expect(buttons[1]!.text()).not.toContain('页')
    expect(buttons[0]!.attributes('aria-pressed')).toBe('false')

    await buttons[0]!.trigger('click')
    await buttons[1]!.trigger('click')
    expect(wrapper.emitted('locateSource')).toEqual([
      [{ documentId: 'doc1', chunkId: 'c-a', page: 7 }],
      [{ documentId: 'doc2', chunkId: 'c-b', sectionPath: '第3章 > 3.2 队列' }],
    ])
    expect(buttons[0]!.attributes('aria-pressed')).toBe('false')
    expect(buttons[1]!.attributes('aria-pressed')).toBe('true')
  })

  it('未知资料名不伪造标题，只显示资料编号', async () => {
    const wrapper = mountDetail(fakeApi(), { kpId: 'k1', documentNames: {} })
    await flushPromises()
    const text = wrapper.get('[data-test="kd-source-locate"]').text()
    expect(text).toContain('doc1')
    expect(text).not.toContain('.pdf')
  })

  it('无法定位的来源不显示也不补页码，并说明被略去的条数', async () => {
    const api = fakeApi(async (_cid, kid) =>
      detail(kid, {
        source_refs: [
          { chunk_id: 'ok', document_id: 'doc1', section_path: '第1章' },
          { chunk_id: 'bad1', document_id: 'doc1', page: 0 } as SourceRef,
          { chunk_id: 'bad2', document_id: 'doc1', section_path: ' ' } as SourceRef,
        ],
      }),
    )
    const wrapper = mountDetail(api)
    await flushPromises()
    expect(wrapper.findAll('[data-test="kd-source-locate"]')).toHaveLength(1)
    expect(wrapper.get('[data-test="kd-sources-dropped"]').text()).toContain('2')
    expect(wrapper.text()).not.toContain('第 0 页')
  })

  it('全部来源无法定位时明确提示，不给定位按钮', async () => {
    const api = fakeApi(async (_cid, kid) =>
      detail(kid, { source_refs: [{ chunk_id: 'bad', document_id: 'doc1' } as SourceRef] }),
    )
    const wrapper = mountDetail(api)
    await flushPromises()
    expect(wrapper.find('[data-test="kd-source-locate"]').exists()).toBe(false)
    expect(wrapper.get('[data-test="kd-sources-none"]').text()).toContain('无法定位')
  })

  it('原文片段按知识点名称高亮', async () => {
    const api = fakeApi(async (_cid, kid) =>
      detail(kid, {
        name: '栈',
        source_refs: [{ chunk_id: 'c', document_id: 'd', page: 1, text: '栈是一种线性表' }],
      }),
    )
    const wrapper = mountDetail(api)
    await flushPromises()
    const marks = wrapper.findAll('[data-test="kd-source-excerpt"] mark')
    expect(marks.map((m) => m.text())).toEqual(['栈'])
    expect(wrapper.get('[data-test="kd-source-excerpt"]').text()).toBe('栈是一种线性表')
  })

  it('XSS 文本按纯文本显示，不执行、不生成元素', async () => {
    const payload = '<img src=x onerror="window.__h06xss=1"><script>window.__h06xss=2</script>'
    const api = fakeApi(async (_cid, kid) =>
      detail(kid, {
        name: `<b>名</b>${payload}`,
        aliases: [payload],
        definition: payload,
        prerequisites: [{ id: 'k0', name: payload }],
        source_refs: [{ chunk_id: 'c', document_id: 'd', page: 1, section_path: payload, text: `前${payload}后` }],
      }),
    )
    const wrapper = mountDetail(api, { kpId: 'k1', documentNames: { d: payload } })
    await flushPromises()
    await new Promise((r) => setTimeout(r, 0))
    const root = wrapper.get('[data-test="knowledge-detail"]').element
    expect(root.querySelector('img, script, b')).toBeNull()
    expect(wrapper.get('[data-test="kd-definition"]').text()).toBe(payload)
    expect(wrapper.get('[data-test="kd-title"]').text()).toContain('<b>名</b>')
    expect((window as unknown as Record<string, unknown>).__h06xss).toBeUndefined()
  })

  it('404 显示不存在，不回显服务端文案，也不给重试', async () => {
    const api = fakeApi(async () => {
      throw apiError(404, 'NOT_FOUND')
    })
    const wrapper = mountDetail(api)
    await flushPromises()
    const alert = wrapper.get('[data-test="kd-error"]')
    expect(alert.attributes('role')).toBe('alert')
    expect(alert.text()).toContain('不存在')
    expect(wrapper.text()).not.toContain('服务端原文')
    expect(wrapper.find('[data-test="kd-retry"]').exists()).toBe(false)
  })

  it('图谱未发布时提示未发布', async () => {
    const api = fakeApi(async () => {
      throw apiError(404, 'GRAPH_NOT_PUBLISHED')
    })
    const wrapper = mountDetail(api)
    await flushPromises()
    expect(wrapper.get('[data-test="kd-error"]').text()).toContain('尚未发布')
  })

  it('网络失败显示错误态，重试后恢复', async () => {
    let attempt = 0
    const api = fakeApi(async (_cid, kid) => {
      attempt += 1
      if (attempt === 1) throw new NetworkError(new Error('offline'))
      return detail(kid)
    })
    const wrapper = mountDetail(api)
    await flushPromises()
    expect(wrapper.get('[data-test="kd-error"]').text()).toContain('无法连接服务器')
    await wrapper.get('[data-test="kd-retry"]').trigger('click')
    await flushPromises()
    expect(api.get).toHaveBeenCalledTimes(2)
    expect(wrapper.find('[data-test="kd-error"]').exists()).toBe(false)
    expect(wrapper.get('[data-test="kd-definition"]').text()).toBe('k1 的定义')
  })

  it('403 课程无权限时向页面发出 courseForbidden', async () => {
    const api = fakeApi(async () => {
      throw apiError(403, 'COURSE_FORBIDDEN')
    })
    const wrapper = mountDetail(api)
    await flushPromises()
    expect(wrapper.emitted('courseForbidden')).toHaveLength(1)
  })

  it('关闭按钮与 Esc 发出 close', async () => {
    const wrapper = mountDetail(fakeApi())
    await flushPromises()
    const close = wrapper.get('[data-test="kd-close"]')
    expect(close.attributes('aria-label')).toBe('关闭知识点详情')
    await close.trigger('click')
    await wrapper.get('[data-test="knowledge-detail"]').trigger('keydown', { key: 'Escape' })
    expect(wrapper.emitted('close')).toHaveLength(2)
  })

  it('切换节点时组件只显示最新节点', async () => {
    const pending = new Map<string, ReturnType<typeof deferred<KnowledgePointDetail>>>()
    const api = fakeApi((_cid, kid) => {
      const d = deferred<KnowledgePointDetail>()
      pending.set(kid, d)
      return d.promise
    })
    const wrapper = mountDetail(api)
    await flushPromises()
    await wrapper.setProps({ kpId: 'k2' })
    await flushPromises()
    pending.get('k2')!.resolve(detail('k2', { name: '新节点' }))
    await flushPromises()
    pending.get('k1')!.resolve(detail('k1', { name: '旧节点' }))
    await flushPromises()
    expect(wrapper.get('[data-test="kd-title"]').text()).toBe('新节点')
    expect(wrapper.text()).not.toContain('旧节点')
  })

  it('切换节点时清除已定位的来源', async () => {
    const wrapper = mountDetail(fakeApi())
    await flushPromises()
    await wrapper.get('[data-test="kd-source-locate"]').trigger('click')
    await wrapper.setProps({ kpId: 'k2' })
    await flushPromises()
    expect(wrapper.get('[data-test="kd-source-locate"]').attributes('aria-pressed')).toBe('false')
  })

  it('未注入专用 API 时用共享 HTTP 客户端', async () => {
    const fetch: FetchLike = async () => new Response(JSON.stringify(detail('k1', { name: '经客户端' })), { status: 200 })
    const wrapper = mountDetail(null, { kpId: 'k1' }, { [HTTP_CLIENT_KEY as symbol]: createHttpClient({ fetch }) })
    await flushPromises()
    expect(wrapper.get('[data-test="kd-title"]').text()).toBe('经客户端')
  })
})
