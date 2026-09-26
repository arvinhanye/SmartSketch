import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick, ref } from 'vue'
import type { components } from '../../src/contracts/v1/generated/typescript/openapi'
import { HTTP_CLIENT_KEY } from '../../src/frontend/src/api/client'
import { ApiError, createHttpClient, NetworkError, TimeoutError, type FetchLike } from '../../src/frontend/src/api/http'
import { createNodeEditApi, NODE_EDIT_API_KEY, type NodeEditApi } from '../../src/frontend/src/api/nodeEdit'
import NodeEditor from '../../src/frontend/src/components/NodeEditor.vue'
import {
  diffForm,
  parseAliases,
  readConflict,
  toForm,
  useNodeEditor,
} from '../../src/frontend/src/composables/useNodeEditor'
import { useCourseStore } from '../../src/frontend/src/stores/course'

type KnowledgePoint = components['schemas']['KnowledgePoint']
type KnowledgePointDetail = components['schemas']['KnowledgePointDetail']
type GraphExchange = components['schemas']['GraphExchange']
type ErrorCode = components['schemas']['ErrorCode']

function kp(id: string, overrides: Partial<KnowledgePointDetail> = {}): KnowledgePointDetail {
  return {
    id,
    course_id: 'c1',
    chapter_id: 'ch1',
    name: `知识点 ${id}`,
    aliases: ['别名一'],
    type: 'concept',
    definition: `${id} 的定义`,
    importance: 0.5,
    level: 1,
    confidence: 0.9,
    status: 'draft',
    source: 'ai',
    locked: false,
    revision: 3,
    source_refs: [{ chunk_id: 'x', document_id: 'd', page: 1 }],
    ...overrides,
  }
}

function saved(base: KnowledgePoint, patch: Partial<KnowledgePoint>): KnowledgePoint {
  return { ...base, ...patch, revision: base.revision + 1, locked: true, source: 'ai' }
}

function apiError(status: number, code: ErrorCode, details?: Record<string, unknown>): ApiError {
  return new ApiError(status, { code, message: '服务端原文不应被展示', details })
}

function conflictError(currentRevision: number, current: Record<string, unknown>): ApiError {
  return apiError(409, 'REVISION_CONFLICT', {
    kp_id: 'k1',
    expected_revision: 3,
    current_revision: currentRevision,
    current,
  })
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

function fakeApi(overrides: Partial<NodeEditApi> = {}) {
  return {
    get: vi.fn<NodeEditApi['get']>(overrides.get ?? (async (_cid, kid) => kp(kid))),
    update: vi.fn<NodeEditApi['update']>(
      overrides.update ?? (async (_cid, kid, body) => saved(kp(kid), body as Partial<KnowledgePoint>)),
    ),
    unlock: vi.fn<NodeEditApi['unlock']>(
      overrides.unlock ?? (async (_cid, kid) => ({ ...kp(kid, { locked: true }), locked: false, revision: 4 })),
    ),
    remove: vi.fn<NodeEditApi['remove']>(overrides.remove ?? (async () => undefined)),
  }
}

function graph(): GraphExchange {
  return {
    format_version: '1.0',
    course_id: 'c1',
    graph_version: null,
    generated_at: '2026-09-26T00:00:00Z',
    nodes: [kp('k1'), kp('k2')].map(({ source_refs: _s, ...n }) => n),
    edges: [
      { id: 'r1', course_id: 'c1', type: 'PREREQUISITE', from_id: 'k1', to_id: 'k2', confidence: 1, status: 'draft', source: 'ai', source_refs: [] },
    ],
  } as GraphExchange
}

let pinia: Pinia

beforeEach(() => {
  pinia = createPinia()
  setActivePinia(pinia)
  const store = useCourseStore(pinia)
  store.selectCourse('c1')
  store.setGraph(store.beginRequest(), graph())
})

afterEach(() => {
  vi.restoreAllMocks()
  delete (window as unknown as Record<string, unknown>).__h07xss
})

function setup(api: ReturnType<typeof fakeApi>, initial: string | null = 'k1', hooks: Record<string, () => void> = {}) {
  const kpId = ref<string | null>(initial)
  const scope = effectScope()
  const onSaved = vi.fn()
  const onDeleted = vi.fn()
  const onRefreshNeeded = vi.fn()
  const onCourseForbidden = vi.fn()
  const editor = scope.run(() =>
    useNodeEditor({ api, kpId, onSaved, onDeleted, onRefreshNeeded, onCourseForbidden, ...hooks }),
  )!
  return { editor, kpId, scope, onSaved, onDeleted, onRefreshNeeded, onCourseForbidden }
}

function mountEditor(api: NodeEditApi | null, kpId: string | null = 'k1', provide: Record<symbol, unknown> = {}) {
  return mount(NodeEditor, {
    props: { kpId },
    attachTo: document.body,
    global: {
      plugins: [pinia],
      provide: { ...(api ? { [NODE_EDIT_API_KEY as symbol]: api } : {}), ...provide },
    },
  })
}

// ---------------------------------------------------------------- API 封装

describe('H07 节点编辑 API 封装', () => {
  function recorder(status = 200, body: unknown = kp('k/1')) {
    const calls: { url: string; init: RequestInit | undefined }[] = []
    const fetch: FetchLike = async (url, init) => {
      calls.push({ url, init })
      return status === 204 ? new Response(null, { status }) : new Response(JSON.stringify(body), { status })
    }
    return { calls, api: createNodeEditApi(createHttpClient({ fetch, getAccessToken: () => 'tok' })) }
  }

  it('PATCH 带 expected_revision 与改动字段，路径逐段编码', async () => {
    const { calls, api } = recorder()
    await api.update('c 1', 'k/1', { expected_revision: 3, name: '新名' })
    expect(calls[0]!.url).toBe('/api/v1/courses/c%201/kp/k%2F1')
    expect(calls[0]!.init?.method).toBe('PATCH')
    expect(JSON.parse(String(calls[0]!.init?.body))).toEqual({ expected_revision: 3, name: '新名' })
    expect(new Headers(calls[0]!.init?.headers).get('Authorization')).toBe('Bearer tok')
  })

  it('解锁 POST /unlock，请求体只有 expected_revision', async () => {
    const { calls, api } = recorder()
    await api.unlock('c1', 'k1', 7)
    expect(calls[0]!.url).toBe('/api/v1/courses/c1/kp/k1/unlock')
    expect(calls[0]!.init?.method).toBe('POST')
    expect(JSON.parse(String(calls[0]!.init?.body))).toEqual({ expected_revision: 7 })
  })

  it('删除 DELETE 带 expected_revision 查询参数，204 无响应体', async () => {
    const { calls, api } = recorder(204)
    await expect(api.remove('c1', 'k1', 5)).resolves.toBeUndefined()
    expect(calls[0]!.url).toBe('/api/v1/courses/c1/kp/k1?expected_revision=5')
    expect(calls[0]!.init?.method).toBe('DELETE')
  })

  it('读取 GET 详情', async () => {
    const { calls, api } = recorder()
    await api.get('c1', 'k1')
    expect(calls[0]!.init?.method).toBe('GET')
    expect(calls[0]!.url).toBe('/api/v1/courses/c1/kp/k1')
  })
})

// ---------------------------------------------------------------- 纯函数

describe('H07 表单与差异', () => {
  it('别名按行、逗号、顿号分隔，去空白、去空项、去重', () => {
    expect(parseAliases(' 栈 \n\n堆栈，LIFO、栈, ;  ')).toEqual(['栈', '堆栈', 'LIFO'])
  })

  it('未改动时无差异；只提交改过的字段', () => {
    const base = kp('k1')
    expect(diffForm(base, toForm(base))).toEqual({ changes: {}, errors: {} })
    const form = { ...toForm(base), name: '  新名  ', difficulty: '0.3' }
    expect(diffForm(base, form)).toEqual({ changes: { name: '新名', difficulty: 0.3 }, errors: {} })
  })

  it('仅首尾空白或别名重复不算修改', () => {
    const base = kp('k1')
    const form = { ...toForm(base), name: ` ${base.name} `, aliases: '别名一\n别名一' }
    expect(diffForm(base, form).changes).toEqual({})
  })

  it('名称、定义为空白时报字段错误', () => {
    const base = kp('k1')
    const { errors, changes } = diffForm(base, { ...toForm(base), name: '   ', definition: '' })
    expect(errors.name).toBe('名称不能为空。')
    expect(errors.definition).toBe('定义不能为空。')
    expect(changes).toEqual({})
  })

  it('重要度、难度须为 0～1；已有值不能清空；原本无值可留空', () => {
    const base = kp('k1') // importance 0.5，无 difficulty
    for (const bad of ['1.5', '-0.1', 'abc', 'NaN', 'Infinity']) {
      expect(diffForm(base, { ...toForm(base), importance: bad }).errors.importance).toBe('请填写 0～1 之间的数。')
    }
    expect(diffForm(base, { ...toForm(base), importance: '' }).errors.importance).toContain('不能清空')
    expect(diffForm(base, { ...toForm(base), difficulty: '' })).toEqual({ changes: {}, errors: {} })
    expect(diffForm(base, { ...toForm(base), importance: '0', difficulty: '1' }).changes).toEqual({ importance: 0, difficulty: 1 })
  })

  it('冲突详情形状不完整时返回 null', () => {
    const current = { name: 'n', definition: 'd', type: 'concept', status: 'draft', locked: true }
    expect(readConflict({ current_revision: 5, current })).not.toBeNull()
    expect(readConflict(undefined)).toBeNull()
    expect(readConflict({ current_revision: 0, current })).toBeNull()
    expect(readConflict({ current_revision: 5 })).toBeNull()
    expect(readConflict({ current_revision: 5, current: { ...current, locked: 'yes' } })).toBeNull()
    expect(readConflict({ current_revision: 5, current: { ...current, aliases: [1] } })).toBeNull()
    expect(readConflict({ current_revision: 5, current: { ...current, importance: '0.3' } })).toBeNull()
  })
})

// ---------------------------------------------------------------- 组合式

describe('H07 加载', () => {
  it('载入节点到表单；切换知识点重新载入', async () => {
    const api = fakeApi()
    const { editor, kpId } = setup(api)
    expect(editor.status.value).toBe('loading')
    await flushPromises()
    expect(editor.status.value).toBe('ready')
    expect(editor.form.name).toBe('知识点 k1')
    expect(editor.form.aliases).toBe('别名一')
    expect(editor.form.importance).toBe('0.5')
    expect(editor.dirty.value).toBe(false)
    kpId.value = 'k2'
    await flushPromises()
    expect(editor.form.name).toBe('知识点 k2')
    expect(api.get).toHaveBeenLastCalledWith('c1', 'k2', expect.objectContaining({ signal: expect.any(AbortSignal) }))
  })

  it('未选择时为空态', async () => {
    const { editor } = setup(fakeApi(), null)
    await flushPromises()
    expect(editor.status.value).toBe('idle')
  })

  it('旧请求晚到不覆盖新选择', async () => {
    const first = deferred<KnowledgePointDetail>()
    const api = fakeApi({ get: async (_c, kid) => (kid === 'k1' ? first.promise : kp(kid)) })
    const { editor, kpId } = setup(api)
    kpId.value = 'k2'
    await flushPromises()
    first.resolve(kp('k1'))
    await flushPromises()
    expect(editor.original.value?.id).toBe('k2')
    expect(editor.form.name).toBe('知识点 k2')
  })

  it('响应 id 或课程不符按数据异常处理，不进入可编辑态', async () => {
    const { editor } = setup(fakeApi({ get: async () => kp('other') }))
    await flushPromises()
    expect(editor.status.value).toBe('error')
    expect(editor.loadRetryable.value).toBe(true)
    const { editor: e2 } = setup(fakeApi({ get: async (_c, kid) => kp(kid, { course_id: 'c2' }) }))
    await flushPromises()
    expect(e2.status.value).toBe('error')
  })

  it('404 为不存在；网络错误可重试', async () => {
    const { editor } = setup(fakeApi({ get: async () => Promise.reject(apiError(404, 'NOT_FOUND')) }))
    await flushPromises()
    expect(editor.status.value).toBe('not_found')
    const { editor: e2 } = setup(fakeApi({ get: async () => Promise.reject(new NetworkError(new TypeError('x'))) }))
    await flushPromises()
    expect(e2.status.value).toBe('error')
    expect(e2.loadRetryable.value).toBe(true)
  })

  it('课程变了而选择没变：回到空态', async () => {
    const { editor } = setup(fakeApi())
    await flushPromises()
    useCourseStore().selectCourse('c2')
    await flushPromises()
    expect(editor.status.value).toBe('idle')
    expect(editor.original.value).toBeNull()
  })
})

describe('H07 保存', () => {
  it('只提交改动字段与读到的修订号；成功后更新表单、锁定并写回图谱', async () => {
    const api = fakeApi()
    const { editor, onSaved } = setup(api)
    await flushPromises()
    editor.form.name = '新名称'
    editor.form.aliases = '甲、乙'
    expect(editor.dirty.value).toBe(true)
    expect(editor.canSave.value).toBe(true)
    await expect(editor.save()).resolves.toBe(true)
    expect(api.update).toHaveBeenCalledWith(
      'c1',
      'k1',
      { name: '新名称', aliases: ['甲', '乙'], expected_revision: 3 },
      expect.anything(),
    )
    expect(editor.original.value?.revision).toBe(4)
    expect(editor.locked.value).toBe(true)
    expect(editor.dirty.value).toBe(false)
    expect(editor.notice.value).toContain('已保存')
    expect(editor.notice.value).toContain('锁定')
    expect(onSaved).toHaveBeenCalledTimes(1)
    const node = useCourseStore().graph!.nodes.find((n) => n.id === 'k1')!
    expect(node.name).toBe('新名称')
    expect(node.locked).toBe(true)
    expect(node.revision).toBe(4)
  })

  it('本地字段错误不发请求，保存后才显示错误', async () => {
    const api = fakeApi()
    const { editor } = setup(api)
    await flushPromises()
    editor.form.name = ' '
    expect(editor.fieldErrors.value.name).toBeUndefined()
    await expect(editor.save()).resolves.toBe(false)
    expect(api.update).not.toHaveBeenCalled()
    expect(editor.fieldErrors.value.name).toBe('名称不能为空。')
    expect(editor.error.value).toContain('未保存')
    expect(editor.notice.value).toBeNull()
  })

  it('没有修改时不发请求', async () => {
    const api = fakeApi()
    const { editor } = setup(api)
    await flushPromises()
    expect(editor.canSave.value).toBe(false)
    await expect(editor.save()).resolves.toBe(false)
    expect(api.update).not.toHaveBeenCalled()
  })

  it('服务端 422 字段错误落到对应字段；编辑该字段后清除', async () => {
    const api = fakeApi({
      update: async () =>
        Promise.reject(
          apiError(422, 'VALIDATION_ERROR', {
            fields: [
              { in: 'body', field: 'aliases.1', reason: 'blank' },
              { in: 'body', field: 'importance', reason: 'less_than_equal' },
            ],
          }),
        ),
    })
    const { editor, onSaved } = setup(api)
    await flushPromises()
    editor.form.aliases = '甲\n乙'
    editor.form.importance = '0.9'
    await expect(editor.save()).resolves.toBe(false)
    expect(editor.fieldErrors.value.aliases).toBe('别名不能为空。')
    expect(editor.fieldErrors.value.importance).toBe('请填写 0～1 之间的数。')
    expect(editor.error.value).toBe('请修正标出的字段，未保存。')
    expect(editor.notice.value).toBeNull()
    expect(editor.form.aliases).toBe('甲\n乙')
    expect(editor.original.value?.revision).toBe(3)
    expect(onSaved).not.toHaveBeenCalled()
    editor.form.aliases = '甲'
    await nextTick()
    expect(editor.fieldErrors.value.aliases).toBeUndefined()
    expect(editor.fieldErrors.value.importance).toBeDefined()
  })

  it('422 认不出的字段给表单级错误', async () => {
    const api = fakeApi({
      update: async () => Promise.reject(apiError(422, 'VALIDATION_ERROR', { fields: [{ in: 'body', field: '', reason: 'no_changes' }] })),
    })
    const { editor } = setup(api)
    await flushPromises()
    editor.form.name = '新'
    await editor.save()
    expect(editor.error.value).toBe('提交内容不符合要求，未保存。')
  })

  it.each([
    ['COURSE_BUSY', 409, '课程正在进行其他写入或发布'],
    ['ROLE_FORBIDDEN', 403, '无权编辑'],
    ['INTERNAL_ERROR', 500, '操作失败'],
  ] as const)('%s：失败不假装成功，保留修改', async (code, status, text) => {
    const api = fakeApi({ update: async () => Promise.reject(apiError(status, code)) })
    const { editor, onSaved } = setup(api)
    await flushPromises()
    editor.form.definition = '新定义'
    await expect(editor.save()).resolves.toBe(false)
    expect(editor.error.value).toContain(text)
    expect(editor.error.value).toContain('未保存')
    expect(editor.error.value).not.toContain('服务端原文')
    expect(editor.notice.value).toBeNull()
    expect(editor.form.definition).toBe('新定义')
    expect(editor.dirty.value).toBe(true)
    expect(editor.locked.value).toBe(false)
    expect(onSaved).not.toHaveBeenCalled()
    expect(useCourseStore().graph!.nodes.find((n) => n.id === 'k1')!.definition).toBe('k1 的定义')
  })

  it.each([
    ['网络中断', () => new NetworkError(new TypeError('x'))],
    ['超时', () => new TimeoutError(30000)],
  ])('%s：说明无法确认是否已保存并提供重新加载', async (_name, make) => {
    const api = fakeApi({ update: async () => Promise.reject(make()) })
    const { editor } = setup(api)
    await flushPromises()
    editor.form.name = '新'
    await editor.save()
    expect(editor.error.value).toContain('不能确认是否已保存')
    expect(editor.stale.value).toBe(true)
    expect(editor.notice.value).toBeNull()
    expect(editor.form.name).toBe('新')
  })

  it('成功响应与请求不符时不当作成功', async () => {
    const api = fakeApi({ update: async () => kp('other') })
    const { editor, onSaved } = setup(api)
    await flushPromises()
    editor.form.name = '新'
    await expect(editor.save()).resolves.toBe(false)
    expect(editor.notice.value).toBeNull()
    expect(editor.error.value).toContain('无法确认结果')
    expect(editor.stale.value).toBe(true)
    expect(onSaved).not.toHaveBeenCalled()
    expect(useCourseStore().graph!.nodes.find((n) => n.id === 'k1')!.name).toBe('知识点 k1')
  })

  it('节点已被删除：进入不存在态并请求刷新图谱', async () => {
    const api = fakeApi({ update: async () => Promise.reject(apiError(404, 'NOT_FOUND')) })
    const { editor, onRefreshNeeded } = setup(api)
    await flushPromises()
    editor.form.name = '新'
    await editor.save()
    expect(editor.status.value).toBe('not_found')
    expect(editor.error.value).toContain('未保存')
    expect(onRefreshNeeded).toHaveBeenCalledTimes(1)
  })

  it('保存中不接受第二次写请求；切换知识点丢弃晚到的保存结果', async () => {
    const pending = deferred<KnowledgePoint>()
    const api = fakeApi({ update: () => pending.promise })
    const { editor, kpId, onSaved } = setup(api)
    await flushPromises()
    editor.form.name = '新'
    const first = editor.save()
    expect(editor.saving.value).toBe(true)
    expect(editor.canSave.value).toBe(false)
    await expect(editor.unlock()).resolves.toBe(false)
    await expect(editor.remove()).resolves.toBe(false)
    expect(api.update).toHaveBeenCalledTimes(1)
    expect(api.remove).not.toHaveBeenCalled()
    kpId.value = 'k2'
    await flushPromises()
    pending.resolve(saved(kp('k1'), { name: '新' }))
    await expect(first).resolves.toBe(false)
    expect(editor.original.value?.id).toBe('k2')
    expect(editor.notice.value).toBeNull()
    expect(onSaved).not.toHaveBeenCalled()
  })

  it('COURSE_FORBIDDEN：清空课程并通知页面', async () => {
    const api = fakeApi({ update: async () => Promise.reject(apiError(403, 'COURSE_FORBIDDEN')) })
    const { editor, onCourseForbidden } = setup(api)
    await flushPromises()
    editor.form.name = '新'
    await editor.save()
    expect(onCourseForbidden).toHaveBeenCalledTimes(1)
    expect(useCourseStore().courseId).toBeNull()
  })
})

describe('H07 修订冲突', () => {
  const theirs = {
    name: '他人改的名',
    aliases: ['别名一'],
    type: 'theorem',
    definition: 'k1 的定义',
    status: 'approved',
    locked: true,
    importance: 0.5,
  }

  async function conflicted(update?: NodeEditApi['update']) {
    let calls = 0
    const api = fakeApi({
      update: async (cid, kid, body, control) => {
        calls += 1
        if (calls === 1) throw conflictError(5, theirs)
        return update ? update(cid, kid, body, control) : saved({ ...kp(kid), ...theirs, revision: 5 } as KnowledgePoint, body as Partial<KnowledgePoint>)
      },
    })
    const ctx = setup(api)
    await flushPromises()
    ctx.editor.form.name = '我改的名'
    ctx.editor.form.definition = '我改的定义'
    await expect(ctx.editor.save()).resolves.toBe(false)
    return { ...ctx, api }
  }

  it('不覆盖；列出我的修改与最新内容的差异，并阻止直接再次保存', async () => {
    const { editor, onSaved } = await conflicted()
    expect(editor.conflict.value).toEqual({
      currentRevision: 5,
      action: 'save',
      diffs: [
        { field: 'name', label: '名称', mine: '我改的名', theirs: '他人改的名' },
        { field: 'definition', label: '定义', mine: '我改的定义', theirs: 'k1 的定义' },
      ],
    })
    expect(editor.error.value).toContain('未保存')
    expect(editor.notice.value).toBeNull()
    expect(editor.form.name).toBe('我改的名')
    expect(editor.original.value?.revision).toBe(3)
    expect(editor.canSave.value).toBe(false)
    await expect(editor.save()).resolves.toBe(false)
    expect(onSaved).not.toHaveBeenCalled()
  })

  it('采用最新内容：丢弃本地修改，修订号更新为当前值', async () => {
    const { editor, api } = await conflicted()
    editor.acceptTheirs()
    expect(editor.conflict.value).toBeNull()
    expect(editor.form.name).toBe('他人改的名')
    expect(editor.form.type).toBe('theorem')
    expect(editor.form.definition).toBe('k1 的定义')
    expect(editor.original.value?.revision).toBe(5)
    expect(editor.locked.value).toBe(true)
    expect(editor.original.value?.chapter_id).toBe('ch1')
    expect(editor.dirty.value).toBe(false)
    expect(api.update).toHaveBeenCalledTimes(1)
  })

  it('保留我的修改：以 current_revision 只重新提交仍有差异的字段', async () => {
    const { editor, api, onSaved } = await conflicted()
    await expect(editor.keepMine()).resolves.toBe(true)
    expect(api.update).toHaveBeenCalledTimes(2)
    expect(api.update.mock.calls[1]![2]).toEqual({ name: '我改的名', definition: '我改的定义', expected_revision: 5 })
    expect(editor.original.value?.revision).toBe(6)
    expect(editor.form.type).toBe('theorem') // 未改的字段不回退他人的修改
    expect(editor.conflict.value).toBeNull()
    expect(onSaved).toHaveBeenCalledTimes(1)
  })

  it('我的修改已与最新一致时不再提交', async () => {
    let calls = 0
    const api = fakeApi({
      update: async () => {
        calls += 1
        throw conflictError(5, { ...theirs, name: '同名' })
      },
    })
    const { editor } = setup(api)
    await flushPromises()
    editor.form.name = '同名'
    await editor.save()
    expect(editor.conflict.value?.diffs).toEqual([])
    await expect(editor.keepMine()).resolves.toBe(true)
    expect(calls).toBe(1)
    expect(editor.dirty.value).toBe(false)
  })

  it('冲突详情缺失：不猜测，提示重新加载', async () => {
    const api = fakeApi({ update: async () => Promise.reject(apiError(409, 'REVISION_CONFLICT', { current_revision: 5 })) })
    const { editor } = setup(api)
    await flushPromises()
    editor.form.name = '新'
    await editor.save()
    expect(editor.conflict.value).toBeNull()
    expect(editor.stale.value).toBe(true)
    expect(editor.error.value).toContain('重新加载')
    expect(editor.form.name).toBe('新')
    editor.reload()
    await flushPromises()
    expect(editor.stale.value).toBe(false)
    expect(api.get).toHaveBeenCalledTimes(2)
  })
})

describe('H07 锁与解锁', () => {
  it('解锁带读到的修订号；成功后未锁定并写回图谱', async () => {
    const api = fakeApi({ get: async (_c, kid) => kp(kid, { locked: true }) })
    const { editor, onSaved } = setup(api)
    await flushPromises()
    expect(editor.locked.value).toBe(true)
    await expect(editor.unlock()).resolves.toBe(true)
    expect(api.unlock).toHaveBeenCalledWith('c1', 'k1', 3, expect.anything())
    expect(editor.locked.value).toBe(false)
    expect(editor.original.value?.revision).toBe(4)
    expect(editor.notice.value).toContain('已解锁')
    expect(onSaved).toHaveBeenCalledTimes(1)
    expect(useCourseStore().graph!.nodes.find((n) => n.id === 'k1')!.locked).toBe(false)
  })

  it('未锁定时不发解锁请求', async () => {
    const api = fakeApi()
    const { editor } = setup(api)
    await flushPromises()
    await expect(editor.unlock()).resolves.toBe(false)
    expect(api.unlock).not.toHaveBeenCalled()
  })

  it('解锁保留表单中未保存的修改', async () => {
    const api = fakeApi({ get: async (_c, kid) => kp(kid, { locked: true }) })
    const { editor } = setup(api)
    await flushPromises()
    editor.form.definition = '未保存'
    await editor.unlock()
    expect(editor.form.definition).toBe('未保存')
    expect(editor.dirty.value).toBe(true)
  })

  it('解锁冲突：仍锁定，载入最新内容，提示确认后再解锁', async () => {
    const api = fakeApi({
      get: async (_c, kid) => kp(kid, { locked: true }),
      unlock: vi
        .fn<NodeEditApi['unlock']>()
        .mockRejectedValueOnce(conflictError(6, { name: '最新', definition: 'd', type: 'concept', status: 'draft', locked: true }))
        .mockResolvedValue({ ...kp('k1'), name: '最新', definition: 'd', locked: false, revision: 7 }),
    })
    const { editor, onSaved } = setup(api)
    await flushPromises()
    await expect(editor.unlock()).resolves.toBe(false)
    expect(editor.locked.value).toBe(true)
    expect(editor.original.value?.revision).toBe(6)
    expect(editor.form.name).toBe('最新')
    expect(editor.error.value).toContain('未解锁')
    expect(editor.notice.value).toBeNull()
    expect(onSaved).not.toHaveBeenCalled()
    await expect(editor.unlock()).resolves.toBe(true)
    expect(api.unlock).toHaveBeenLastCalledWith('c1', 'k1', 6, expect.anything())
  })

  it('解锁响应与请求不符时不当作成功', async () => {
    const api = fakeApi({
      get: async (_c, kid) => kp(kid, { locked: true }),
      unlock: async () => ({ ...kp('other'), locked: false, revision: 4 }),
    })
    const { editor, onSaved } = setup(api)
    await flushPromises()
    await expect(editor.unlock()).resolves.toBe(false)
    expect(editor.locked.value).toBe(true)
    expect(editor.notice.value).toBeNull()
    expect(editor.stale.value).toBe(true)
    expect(onSaved).not.toHaveBeenCalled()
  })

  it('服务端仍返回锁定：不提示已解锁', async () => {
    const api = fakeApi({
      get: async (_c, kid) => kp(kid, { locked: true }),
      unlock: async (_c, kid) => kp(kid, { locked: true, revision: 4 }),
    })
    const { editor } = setup(api)
    await flushPromises()
    await expect(editor.unlock()).resolves.toBe(false)
    expect(editor.notice.value).toBeNull()
    expect(editor.error.value).toContain('仍显示')
  })
})

describe('H07 删除', () => {
  it('带修订号删除；成功后从图谱移除节点与相连关系', async () => {
    const api = fakeApi()
    const { editor, onDeleted } = setup(api)
    await flushPromises()
    await expect(editor.remove()).resolves.toBe(true)
    expect(api.remove).toHaveBeenCalledWith('c1', 'k1', 3, expect.anything())
    expect(editor.status.value).toBe('deleted')
    expect(onDeleted).toHaveBeenCalledWith('k1')
    const g = useCourseStore().graph!
    expect(g.nodes.map((n) => n.id)).toEqual(['k2'])
    expect(g.edges).toEqual([])
  })

  it('删除冲突：不删除，载入最新内容并保持可编辑', async () => {
    const api = fakeApi({
      remove: async () => Promise.reject(conflictError(4, { name: '最新', definition: 'd', type: 'concept', status: 'draft', locked: false })),
    })
    const { editor, onDeleted } = setup(api)
    await flushPromises()
    await expect(editor.remove()).resolves.toBe(false)
    expect(editor.status.value).toBe('ready')
    expect(editor.error.value).toContain('未删除')
    expect(editor.original.value?.revision).toBe(4)
    expect(onDeleted).not.toHaveBeenCalled()
    expect(useCourseStore().graph!.nodes).toHaveLength(2)
  })

  it('删除时节点已不存在：说明已不存在并请求刷新，不提示「已删除」', async () => {
    const api = fakeApi({ remove: async () => Promise.reject(apiError(404, 'NOT_FOUND')) })
    const { editor, onDeleted, onRefreshNeeded } = setup(api)
    await flushPromises()
    await editor.remove()
    expect(editor.status.value).toBe('deleted')
    expect(editor.notice.value).toBeNull()
    expect(editor.error.value).toContain('已不存在')
    expect(onDeleted).not.toHaveBeenCalled()
    expect(onRefreshNeeded).toHaveBeenCalledTimes(1)
  })

  it('删除网络失败：保留节点，说明无法确认', async () => {
    const api = fakeApi({ remove: async () => Promise.reject(new NetworkError(new TypeError('x'))) })
    const { editor, onDeleted } = setup(api)
    await flushPromises()
    await editor.remove()
    expect(editor.status.value).toBe('ready')
    expect(editor.error.value).toContain('不能确认')
    expect(onDeleted).not.toHaveBeenCalled()
    expect(useCourseStore().graph!.nodes).toHaveLength(2)
  })
})

// ---------------------------------------------------------------- 组件

describe('H07 NodeEditor 组件', () => {
  it('空态、加载态、就绪态；标签关联输入框并聚焦标题', async () => {
    const wrapper = mountEditor(fakeApi(), null)
    expect(wrapper.find('[data-test="ne-empty"]').exists()).toBe(true)
    await wrapper.setProps({ kpId: 'k1' })
    expect(wrapper.find('[data-test="ne-loading"]').exists()).toBe(true)
    expect(wrapper.get('[data-test="node-editor"]').attributes('aria-busy')).toBe('true')
    await flushPromises()
    const input = wrapper.get('[data-test="ne-name"]')
    expect((input.element as HTMLInputElement).value).toBe('知识点 k1')
    expect(wrapper.get(`label[for="${input.attributes('id')}"]`).text()).toBe('名称')
    expect(document.activeElement).toBe(wrapper.get('[data-test="ne-title"]').element)
    expect(wrapper.get('[data-test="ne-lock-state"]').text()).toContain('未锁定')
    expect(wrapper.find('[data-test="ne-unlock"]').exists()).toBe(false)
    expect((wrapper.get('[data-test="ne-save"]').element as HTMLButtonElement).disabled).toBe(true)
  })

  it('字段错误：aria-invalid 并以 aria-describedby 关联错误文字', async () => {
    const api = fakeApi()
    const wrapper = mountEditor(api)
    await flushPromises()
    await wrapper.get('[data-test="ne-definition"]').setValue('  ')
    await wrapper.get('[data-test="ne-name"]').setValue('x') // 使保存可用
    await wrapper.get('[data-test="ne-form"]').trigger('submit')
    await flushPromises()
    const field = wrapper.get('[data-test="ne-definition"]')
    expect(field.attributes('aria-invalid')).toBe('true')
    const err = wrapper.get('[data-test="ne-definition-error"]')
    expect(field.attributes('aria-describedby')).toBe(err.attributes('id'))
    expect(err.text()).toBe('定义不能为空。')
    expect(wrapper.get('[data-test="ne-error"]').attributes('role')).toBe('alert')
    expect(api.update).not.toHaveBeenCalled()
  })

  it('保存成功发出 saved，显示锁定与解锁按钮', async () => {
    const wrapper = mountEditor(fakeApi())
    await flushPromises()
    await wrapper.get('[data-test="ne-name"]').setValue('新名')
    expect(wrapper.find('[data-test="ne-dirty"]').exists()).toBe(true)
    await wrapper.get('[data-test="ne-form"]').trigger('submit')
    await flushPromises()
    expect(wrapper.emitted('saved')).toHaveLength(1)
    expect(wrapper.get('[data-test="ne-notice"]').text()).toContain('已保存')
    expect(wrapper.get('[data-test="ne-lock-state"]').text()).toContain('已锁定')
    expect(wrapper.find('[data-test="ne-unlock"]').exists()).toBe(true)
    expect(wrapper.get('[data-test="ne-title"]').text()).toBe('编辑：新名')
  })

  it('保存失败时不显示成功提示，按钮恢复可用', async () => {
    const wrapper = mountEditor(fakeApi({ update: async () => Promise.reject(apiError(409, 'COURSE_BUSY')) }))
    await flushPromises()
    await wrapper.get('[data-test="ne-name"]').setValue('新名')
    await wrapper.get('[data-test="ne-form"]').trigger('submit')
    await flushPromises()
    expect(wrapper.find('[data-test="ne-notice"]').exists()).toBe(false)
    expect(wrapper.get('[data-test="ne-error"]').text()).toContain('未保存')
    expect((wrapper.get('[data-test="ne-save"]').element as HTMLButtonElement).disabled).toBe(false)
    expect(wrapper.emitted('saved')).toBeUndefined()
  })

  it('冲突面板并列展示差异，可采用最新内容', async () => {
    const api = fakeApi({
      update: async () =>
        Promise.reject(conflictError(5, { name: '他人', aliases: [], type: 'concept', definition: 'k1 的定义', status: 'draft', locked: true })),
    })
    const wrapper = mountEditor(api)
    await flushPromises()
    await wrapper.get('[data-test="ne-name"]').setValue('我的')
    await wrapper.get('[data-test="ne-form"]').trigger('submit')
    await flushPromises()
    const row = wrapper.get('[data-test="ne-conflict-name"]')
    expect(row.findAll('td').map((c) => c.text())).toEqual(['我的', '他人'])
    expect(wrapper.get('[data-test="ne-conflict"]').text()).toContain('最新修订 5')
    expect((wrapper.get('[data-test="ne-save"]').element as HTMLButtonElement).disabled).toBe(true)
    await wrapper.get('[data-test="ne-accept-theirs"]').trigger('click')
    expect(wrapper.find('[data-test="ne-conflict"]').exists()).toBe(false)
    expect((wrapper.get('[data-test="ne-name"]').element as HTMLInputElement).value).toBe('他人')
  })

  it('删除需二次确认；取消不发请求，确认后发出 deleted', async () => {
    const api = fakeApi()
    const wrapper = mountEditor(api)
    await flushPromises()
    await wrapper.get('[data-test="ne-delete"]').trigger('click')
    const confirm = wrapper.get('[data-test="ne-delete-confirm"]')
    expect(confirm.text()).toContain('相连的全部关系')
    expect(confirm.attributes('role')).toBe('alertdialog')
    expect(wrapper.find('[data-test="ne-delete"]').exists()).toBe(false)
    await wrapper.get('[data-test="ne-delete-no"]').trigger('click')
    expect(wrapper.find('[data-test="ne-delete-confirm"]').exists()).toBe(false)
    expect(api.remove).not.toHaveBeenCalled()
    await wrapper.get('[data-test="ne-name"]').setValue('改过')
    await wrapper.get('[data-test="ne-delete"]').trigger('click')
    expect(wrapper.get('[data-test="ne-delete-confirm"]').text()).toContain('未保存的修改也会丢失')
    await wrapper.get('[data-test="ne-delete-yes"]').trigger('click')
    await flushPromises()
    expect(api.remove).toHaveBeenCalledTimes(1)
    expect(wrapper.emitted('deleted')).toEqual([['k1']])
    expect(wrapper.get('[data-test="ne-deleted"]').text()).toContain('已删除')
  })

  it('解锁按钮调用解锁接口', async () => {
    const api = fakeApi({ get: async (_c, kid) => kp(kid, { locked: true }) })
    const wrapper = mountEditor(api)
    await flushPromises()
    await wrapper.get('[data-test="ne-unlock"]').trigger('click')
    await flushPromises()
    expect(api.unlock).toHaveBeenCalledTimes(1)
    expect(wrapper.get('[data-test="ne-lock-state"]').text()).toContain('未锁定')
    expect(wrapper.find('[data-test="ne-unlock"]').exists()).toBe(false)
  })

  it('网络失败提供重新加载按钮', async () => {
    const api = fakeApi({ update: async () => Promise.reject(new NetworkError(new TypeError('x'))) })
    const wrapper = mountEditor(api)
    await flushPromises()
    await wrapper.get('[data-test="ne-name"]').setValue('新')
    await wrapper.get('[data-test="ne-form"]').trigger('submit')
    await flushPromises()
    await wrapper.get('[data-test="ne-reload"]').trigger('click')
    await flushPromises()
    expect(api.get).toHaveBeenCalledTimes(2)
    expect((wrapper.get('[data-test="ne-name"]').element as HTMLInputElement).value).toBe('知识点 k1')
  })

  it('加载 404 显示错误且不可重试；Esc 与关闭按钮发出 close', async () => {
    const wrapper = mountEditor(fakeApi({ get: async () => Promise.reject(apiError(404, 'NOT_FOUND')) }))
    await flushPromises()
    expect(wrapper.get('[data-test="ne-load-error"]').text()).toContain('不存在')
    expect(wrapper.find('[data-test="ne-retry"]').exists()).toBe(false)
    await wrapper.get('[data-test="node-editor"]').trigger('keydown', { key: 'Escape' })
    await wrapper.get('[data-test="ne-close"]').trigger('click')
    expect(wrapper.emitted('close')).toHaveLength(2)
  })

  it('服务端文本以插值渲染，不执行 HTML', async () => {
    const evil = '<img src=x onerror="window.__h07xss=1">'
    const wrapper = mountEditor(fakeApi({ get: async (_c, kid) => kp(kid, { name: evil }) }))
    await flushPromises()
    expect(wrapper.get('[data-test="ne-title"]').text()).toBe(`编辑：${evil}`)
    expect(wrapper.find('[data-test="ne-title"] img').exists()).toBe(false)
    expect((window as unknown as Record<string, unknown>).__h07xss).toBeUndefined()
  })

  it('未注入专用 API 时用 HTTP_CLIENT_KEY 的客户端', async () => {
    const fetch: FetchLike = async () => new Response(JSON.stringify(kp('k1')), { status: 200 })
    const wrapper = mountEditor(null, 'k1', { [HTTP_CLIENT_KEY as symbol]: createHttpClient({ fetch }) })
    await flushPromises()
    expect((wrapper.get('[data-test="ne-name"]').element as HTMLInputElement).value).toBe('知识点 k1')
  })
})
