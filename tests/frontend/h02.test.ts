import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { createMemoryHistory } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { components } from '../../src/contracts/v1/generated/typescript/openapi'
import App from '../../src/frontend/src/App.vue'
import { COURSES_API_KEY, type CoursesApi } from '../../src/frontend/src/api/courses'
import { ApiError, createHttpClient, NetworkError, type FetchLike } from '../../src/frontend/src/api/http'
import {
  createMaterialsApi,
  MATERIALS_API_KEY,
  TASK_EVENTS_CLIENT_KEY,
  type MaterialsApi,
} from '../../src/frontend/src/api/materials'
import type {
  TaskEventsClient,
  TaskStreamCloseReason,
  TaskStreamHandlers,
  TaskStreamState,
} from '../../src/frontend/src/api/taskEvents'
import {
  taskStatusOf,
  validateMaterialFile,
} from '../../src/frontend/src/composables/useMaterials'
import { COURSE_ROUTE, createAppRouter, MATERIALS_ROUTE } from '../../src/frontend/src/router/index.ts'
import type { CourseRequestScope } from '../../src/frontend/src/stores/course'
import { useCourseStore } from '../../src/frontend/src/stores/course'
import { useSessionStore } from '../../src/frontend/src/stores/session'
import CoursesView from '../../src/frontend/src/views/CoursesView.vue'
import MaterialsView from '../../src/frontend/src/views/MaterialsView.vue'

type Course = components['schemas']['Course']
type Document = components['schemas']['Document']
type Task = components['schemas']['Task']
type TaskStage = components['schemas']['TaskStage']
type ErrorCode = components['schemas']['ErrorCode']

const CID = 'c1'
/** 假上传策略默认返回 `UPLOAD_MAX_BYTES` 的默认值（D-11：50 MiB） */
const DEFAULT_MAX_BYTES = 50 * 1024 * 1024

function course(id: string, overrides: Partial<Course> = {}): Course {
  return {
    id,
    name: `课程 ${id}`,
    description: null,
    status: 'draft',
    my_role: 'teacher',
    teacher_id: 'u_teacher',
    kp_count: 0,
    published_version: null,
    created_at: '2026-09-25T00:00:00Z',
    ...overrides,
  }
}

function doc(id: string, overrides: Partial<Document> = {}): Document {
  return {
    id,
    course_id: CID,
    filename: `${id}.pdf`,
    format: 'pdf',
    size_bytes: 2048,
    parse_status: 'awaiting_review',
    task_id: null,
    uploaded_at: '2026-09-25T00:00:00Z',
    ...overrides,
  }
}

function task(id: string, stage: TaskStage, overrides: Record<string, unknown> = {}): Task {
  return {
    id,
    course_id: CID,
    document_id: `d_${id}`,
    stage,
    progress: stage === 'queued' ? 0 : 0.4,
    cancel_requested: stage === 'cancelled',
    created_at: '2026-09-25T00:00:00Z',
    updated_at: '2026-09-25T00:00:00Z',
    ...overrides,
  } as Task
}

function apiError(status: number, code: ErrorCode, details?: Record<string, unknown>): ApiError {
  return new ApiError(status, { code, message: '服务端原文不应被展示', details })
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

function fakeCoursesApi(overrides: Partial<CoursesApi> = {}) {
  return {
    list: vi.fn<CoursesApi['list']>(overrides.list ?? (async () => [course(CID)])),
    create: vi.fn<CoursesApi['create']>(overrides.create ?? (async (body) => course('c_new', { name: body.name }))),
    get: vi.fn<CoursesApi['get']>(overrides.get ?? (async (cid) => course(cid))),
  }
}

function fakeMaterialsApi(overrides: Partial<MaterialsApi> = {}) {
  let seq = 0
  return {
    list: vi.fn<MaterialsApi['list']>(overrides.list ?? (async () => [])),
    upload: vi.fn<MaterialsApi['upload']>(
      overrides.upload ??
        (async () => {
          seq += 1
          return { task_id: `t${seq}`, document_id: `d_t${seq}` }
        }),
    ),
    cancelTask: vi.fn<MaterialsApi['cancelTask']>(overrides.cancelTask ?? (async (tid) => task(tid, 'cancelled'))),
    deleteDocument: vi.fn<MaterialsApi['deleteDocument']>(overrides.deleteDocument ?? (async () => undefined)),
    uploadPolicy: vi.fn<MaterialsApi['uploadPolicy']>(
      overrides.uploadPolicy ?? (async () => ({ max_bytes: DEFAULT_MAX_BYTES })),
    ),
  }
}

/** 假任务流客户端：记录每次订阅，测试手动推送事件、状态与关闭原因 */
function fakeTaskEvents() {
  interface Sub {
    taskId: string
    scope: CourseRequestScope
    handlers: TaskStreamHandlers
    close: ReturnType<typeof vi.fn<() => void>>
    closed: boolean
  }
  const subs: Sub[] = []
  const client: TaskEventsClient = {
    subscribe: vi.fn((taskId: string, scope: CourseRequestScope, handlers: TaskStreamHandlers) => {
      const sub: Sub = {
        taskId,
        scope,
        handlers,
        closed: false,
        close: vi.fn(() => {
          if (sub.closed) return
          sub.closed = true
          handlers.onClose?.({ kind: 'unsubscribed' })
        }),
      }
      subs.push(sub)
      return {
        close: () => sub.close(),
        get closed() {
          return sub.closed
        },
      }
    }),
  }
  function last(taskId?: string): Sub {
    const found = taskId === undefined ? subs.at(-1) : subs.filter((s) => s.taskId === taskId).at(-1)
    if (!found) throw new Error('没有订阅')
    return found
  }
  function stage(taskId: string, stageName: TaskStage, progress: number, cancelRequested = false) {
    const final = stageName === 'awaiting_review'
    last(taskId).handlers.onUpdate({
      source: 'stream',
      event: 'stage',
      final,
      data: { task_id: taskId, stage: stageName, progress, cancel_requested: cancelRequested } as never,
    })
    if (final) finish(taskId, stageName)
  }
  function finish(taskId: string, stageName: TaskStage) {
    const sub = last(taskId)
    sub.closed = true
    sub.handlers.onClose?.({ kind: 'finished', stage: stageName })
  }
  function cancelled(taskId: string, progress = 0.4) {
    last(taskId).handlers.onUpdate({
      source: 'stream',
      event: 'cancelled',
      final: true,
      data: { task_id: taskId, stage: 'cancelled', progress, cancel_requested: true },
    })
    finish(taskId, 'cancelled')
  }
  function failed(taskId: string, code: ErrorCode) {
    last(taskId).handlers.onUpdate({
      source: 'stream',
      event: 'error',
      final: true,
      data: { task_id: taskId, stage: 'failed', progress: 0.3, error: { code, message: '服务端原文不应被展示' } },
    })
    finish(taskId, 'failed')
  }
  function state(taskId: string, value: TaskStreamState) {
    last(taskId).handlers.onState?.(value)
  }
  function close(taskId: string, reason: TaskStreamCloseReason) {
    const sub = last(taskId)
    sub.closed = true
    sub.handlers.onClose?.(reason)
  }
  return { client, subs, last, stage, cancelled, failed, state, close }
}

function file(name: string, size = 16, type = ''): File {
  const f = new File(['x'.repeat(Math.min(size, 16))], name, { type })
  if (size !== f.size) Object.defineProperty(f, 'size', { value: size })
  return f
}

async function chooseFile(wrapper: VueWrapper, f: File) {
  const input = wrapper.get('[data-test="material-file-input"]')
  Object.defineProperty(input.element, 'files', { value: [f], configurable: true })
  await input.trigger('change')
  await flushPromises()
}

async function submitUpload(wrapper: VueWrapper) {
  await wrapper.get('[data-test="material-upload-form"]').trigger('submit')
  await flushPromises()
}

let pinia: Pinia

beforeEach(() => {
  sessionStorage.clear()
  pinia = createPinia()
  setActivePinia(pinia)
})

afterEach(() => {
  vi.restoreAllMocks()
})

async function mountPage({
  materials = fakeMaterialsApi(),
  courses = fakeCoursesApi(),
  events = fakeTaskEvents(),
  path = `/courses/${CID}/materials`,
  accountRole = 'teacher' as const as 'teacher' | 'student',
}: {
  materials?: ReturnType<typeof fakeMaterialsApi>
  courses?: ReturnType<typeof fakeCoursesApi>
  events?: ReturnType<typeof fakeTaskEvents>
  path?: string
  accountRole?: 'teacher' | 'student'
} = {}) {
  const session = useSessionStore(pinia)
  session.signIn({
    access_token: 'tok',
    token_type: 'bearer',
    expires_in: 3600,
    user: { id: `u_${accountRole}`, username: accountRole, role: accountRole },
  })
  const router = createAppRouter({
    history: createMemoryHistory(),
    getAccountRole: () => session.role,
    coursesComponent: CoursesView,
    materialsComponent: MaterialsView,
  })
  await router.push(path)
  await router.isReady()
  const wrapper = mount(App, {
    global: {
      plugins: [pinia, router],
      provide: {
        [COURSES_API_KEY as symbol]: courses,
        [MATERIALS_API_KEY as symbol]: materials,
        [TASK_EVENTS_CLIENT_KEY as symbol]: events.client,
      },
    },
  })
  await flushPromises()
  return { wrapper, router, materials, courses, events, store: useCourseStore(pinia) }
}

function row(wrapper: VueWrapper, documentId: string) {
  return wrapper.get(`[data-test="material-row"][data-document-id="${documentId}"]`)
}

// ---------------------------------------------------------------- API 封装

describe('H02 资料 API 封装', () => {
  function recordingFetch(response: () => Response) {
    const calls: { url: string; init: RequestInit | undefined }[] = []
    const fetch: FetchLike = async (url, init) => {
      calls.push({ url, init })
      return response()
    }
    return { calls, fetch }
  }
  const json = (body: unknown, status = 200) =>
    new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

  it('list 走契约 GET /api/v1/courses/{cid}/documents', async () => {
    const { calls, fetch } = recordingFetch(() => json([doc('d1')]))
    const api = createMaterialsApi(createHttpClient({ fetch, getAccessToken: () => 'tok' }))
    await expect(api.list('c/1')).resolves.toEqual([doc('d1')])
    expect(calls[0]!.url).toBe('/api/v1/courses/c%2F1/documents')
    expect(calls[0]!.init?.method).toBe('GET')
  })

  it('upload 以 multipart 字段 file 上传，不设 JSON Content-Type', async () => {
    const { calls, fetch } = recordingFetch(() => json({ task_id: 't1', document_id: 'd1' }, 202))
    const api = createMaterialsApi(createHttpClient({ fetch }))
    const f = file('讲义.pdf', 16, 'application/pdf')
    await expect(api.upload(CID, f)).resolves.toEqual({ task_id: 't1', document_id: 'd1' })
    expect(calls[0]!.url).toBe('/api/v1/courses/c1/documents')
    expect(calls[0]!.init?.method).toBe('POST')
    const body = calls[0]!.init?.body
    expect(body).toBeInstanceOf(FormData)
    expect((body as FormData).get('file')).toBeInstanceOf(File)
    expect(((body as FormData).get('file') as File).name).toBe('讲义.pdf')
    expect(new Headers(calls[0]!.init?.headers).get('Content-Type')).toBeNull()
  })

  it('deleteDocument 走契约 DELETE /api/v1/courses/{cid}/documents/{did}，204 无响应体', async () => {
    const { calls, fetch } = recordingFetch(() => new Response(null, { status: 204 }))
    const api = createMaterialsApi(createHttpClient({ fetch }))
    await expect(api.deleteDocument(CID, 'd/1')).resolves.toBeUndefined()
    expect(calls[0]!.url).toBe('/api/v1/courses/c1/documents/d%2F1')
    expect(calls[0]!.init?.method).toBe('DELETE')
  })

  it('cancelTask 走 POST /api/v1/tasks/{tid}/cancel', async () => {
    const { calls, fetch } = recordingFetch(() => json(task('t1', 'cancelled')))
    const api = createMaterialsApi(createHttpClient({ fetch }))
    await api.cancelTask('t1')
    expect(calls[0]!.url).toBe('/api/v1/tasks/t1/cancel')
    expect(calls[0]!.init?.method).toBe('POST')
  })

  it('uploadPolicy 走契约 GET /api/v1/courses/{cid}/upload-policy（ADR-022）', async () => {
    const { calls, fetch } = recordingFetch(() => json({ max_bytes: 1234 }))
    const api = createMaterialsApi(createHttpClient({ fetch }))
    await expect(api.uploadPolicy('c/1')).resolves.toEqual({ max_bytes: 1234 })
    expect(calls[0]!.url).toBe('/api/v1/courses/c%2F1/upload-policy')
    expect(calls[0]!.init?.method).toBe('GET')
  })
})

// ---------------------------------------------------------------- 纯函数

describe('H02 文件校验与状态文案', () => {
  it.each(['a.pdf', 'b.DOCX', 'c.txt', 'd.md', 'e.Markdown'])('接受 %s', (name) => {
    expect(validateMaterialFile(file(name), DEFAULT_MAX_BYTES)).toBeNull()
  })

  it.each(['a.doc', 'b.pptx', 'c.pdf.exe', 'README', '.md.zip'])('拒绝非法格式 %s 并列出支持格式', (name) => {
    const message = validateMaterialFile(file(name), DEFAULT_MAX_BYTES)
    expect(message).toMatch(/PDF.*DOCX.*TXT.*Markdown/)
  })

  it('拒绝空文件与超过上限的文件，恰好等于上限可接受', () => {
    expect(validateMaterialFile(file('a.pdf', 0), DEFAULT_MAX_BYTES)).toMatch(/空/)
    expect(validateMaterialFile(file('a.pdf', DEFAULT_MAX_BYTES), DEFAULT_MAX_BYTES)).toBeNull()
    expect(validateMaterialFile(file('a.pdf', DEFAULT_MAX_BYTES + 1), DEFAULT_MAX_BYTES)).toMatch(/50 MiB/)
  })

  it('上限取传入值而非固定 50 MiB（ADR-022）', () => {
    expect(validateMaterialFile(file('a.pdf', 2048), 2048)).toBeNull()
    expect(validateMaterialFile(file('a.pdf', 2049), 2048)).toMatch(/2 KiB/)
    expect(validateMaterialFile(file('a.pdf', DEFAULT_MAX_BYTES + 1), 100 * 1024 * 1024)).toBeNull()
  })

  it('上限未知（策略未取到）时跳过本地大小校验，但仍拒绝空文件与非法格式', () => {
    expect(validateMaterialFile(file('a.pdf', DEFAULT_MAX_BYTES * 10), null)).toBeNull()
    expect(validateMaterialFile(file('a.pdf', 0), null)).toMatch(/空/)
    expect(validateMaterialFile(file('a.doc'), null)).toMatch(/PDF.*DOCX/)
  })

  it('取消中与已取消是两种状态', () => {
    const cancelling = taskStatusOf({ stage: 'extracting', cancelRequested: true })
    const cancelled = taskStatusOf({ stage: 'cancelled', cancelRequested: true })
    expect(cancelling.kind).toBe('cancelling')
    expect(cancelling.label).toBe('取消中')
    expect(cancelled.kind).toBe('cancelled')
    expect(cancelled.label).toBe('已取消')
    // 失败时标志可能仍为 true（TASK-7）：按失败显示，不显示取消中
    expect(taskStatusOf({ stage: 'failed', cancelRequested: true }).kind).toBe('failed')
    expect(taskStatusOf({ stage: 'extracting', cancelRequested: false }).label).toBe('抽取中')
    expect(taskStatusOf({ stage: 'awaiting_review', cancelRequested: false }).label).toBe('待审核')
  })
})

// ---------------------------------------------------------------- 页面四态与访问

describe('H02 页面状态与访问', () => {
  it('加载态：请求未完成时 aria-busy 并显示 role=status', async () => {
    const pending = deferred<Document[]>()
    const { wrapper } = await mountPage({ materials: fakeMaterialsApi({ list: () => pending.promise }) })
    expect(wrapper.get('[data-test="materials-loading"]').attributes('role')).toBe('status')
    expect(wrapper.get('[data-test="materials-page"]').attributes('aria-busy')).toBe('true')
    pending.resolve([doc('d1')])
    await flushPromises()
    expect(wrapper.find('[data-test="materials-loading"]').exists()).toBe(false)
    expect(wrapper.findAll('[data-test="material-row"]')).toHaveLength(1)
  })

  it('空态：没有资料时提示上传', async () => {
    const { wrapper } = await mountPage()
    expect(wrapper.get('[data-test="materials-empty"]').text()).toContain('尚未上传')
  })

  it('错误态：网络失败显示 role=alert 与重试，重试成功后显示资料', async () => {
    let attempt = 0
    const materials = fakeMaterialsApi({
      list: async () => {
        attempt += 1
        if (attempt === 1) throw new NetworkError(new TypeError('offline'))
        return [doc('d1')]
      },
    })
    const { wrapper } = await mountPage({ materials })
    const alert = wrapper.get('[data-test="materials-error"]')
    expect(alert.attributes('role')).toBe('alert')
    expect(alert.text()).toContain('网络')
    expect(alert.text()).not.toContain('服务端原文')
    await wrapper.get('[data-test="materials-retry"]').trigger('click')
    await flushPromises()
    expect(materials.list).toHaveBeenCalledTimes(2)
    expect(wrapper.findAll('[data-test="material-row"]')).toHaveLength(1)
  })

  it('列表显示文件名、格式与由 parse_status 得出的状态', async () => {
    const materials = fakeMaterialsApi({
      list: async () => [
        doc('d1', { filename: '第一章.pdf', parse_status: 'awaiting_review' }),
        doc('d2', { filename: 'notes.md', format: 'markdown', parse_status: 'failed' }),
        doc('d3', { filename: 'x.txt', format: 'txt', parse_status: 'cancelled' }),
      ],
    })
    const { wrapper } = await mountPage({ materials })
    expect(row(wrapper, 'd1').text()).toContain('第一章.pdf')
    expect(row(wrapper, 'd1').get('[data-test="material-status"]').text()).toBe('待审核')
    expect(row(wrapper, 'd2').text()).toContain('Markdown')
    expect(row(wrapper, 'd2').get('[data-test="material-status"]').text()).toBe('处理失败')
    expect(row(wrapper, 'd3').get('[data-test="material-status"]').text()).toBe('已取消')
    // 列表来的资料没有本次会话的文件，失败/取消后引导重新选择文件上传
    expect(row(wrapper, 'd2').text()).toContain('重新选择文件上传')
    expect(row(wrapper, 'd2').find('[data-test="task-retry"]').exists()).toBe(false)
  })

  it('课程内角色为学生：显示仅教师可用，不请求资料列表，也不显示上传表单', async () => {
    const courses = fakeCoursesApi({ get: async (cid) => course(cid, { my_role: 'student', status: 'published' }) })
    const { wrapper, materials } = await mountPage({ courses, accountRole: 'student' })
    expect(wrapper.get('[data-test="materials-forbidden"]').attributes('role')).toBe('alert')
    expect(wrapper.get('[data-test="materials-forbidden"]').text()).toContain('仅课程教师')
    expect(materials.list).not.toHaveBeenCalled()
    expect(wrapper.find('[data-test="material-upload-form"]').exists()).toBe(false)
  })

  it('资料列表返回 403 ROLE_FORBIDDEN 时显示无权限', async () => {
    const materials = fakeMaterialsApi({ list: async () => Promise.reject(apiError(403, 'ROLE_FORBIDDEN')) })
    const { wrapper } = await mountPage({ materials })
    expect(wrapper.get('[data-test="materials-forbidden"]').text()).toContain('仅课程教师')
  })

  it('非成员 COURSE_FORBIDDEN：显示无权访问并给出返回课程列表的链接', async () => {
    const courses = fakeCoursesApi({ get: async () => Promise.reject(apiError(403, 'COURSE_FORBIDDEN')) })
    const { wrapper, materials } = await mountPage({ courses })
    expect(wrapper.get('[data-test="materials-forbidden"]').text()).toContain('无权访问')
    expect(materials.list).not.toHaveBeenCalled()
  })

  it('上传控件有可见 label，并以 accept 提示支持的格式', async () => {
    const { wrapper } = await mountPage()
    const input = wrapper.get('[data-test="material-file-input"]')
    const id = input.attributes('id')
    expect(id).toBeTruthy()
    expect(wrapper.get(`label[for="${id}"]`).text()).toContain('选择资料')
    expect(input.attributes('accept')).toContain('.pdf')
    expect(input.attributes('accept')).toContain('.md')
    expect(wrapper.get('[data-test="upload-hint"]').text()).toMatch(/PDF.*DOCX.*TXT.*Markdown.*50 MiB/)
  })
})

// ---------------------------------------------------------------- 上传

describe('H02 上传', () => {
  it('非法格式：本地提示并高亮，不发请求', async () => {
    const { wrapper, materials } = await mountPage()
    await chooseFile(wrapper, file('slides.pptx'))
    const alert = wrapper.get('[data-test="upload-error"]')
    expect(alert.attributes('role')).toBe('alert')
    expect(alert.text()).toMatch(/PDF.*DOCX.*TXT.*Markdown/)
    expect(wrapper.get('[data-test="material-file-input"]').attributes('aria-invalid')).toBe('true')
    await submitUpload(wrapper)
    expect(materials.upload).not.toHaveBeenCalled()
  })

  it('超过 50 MiB：本地提示，不发请求', async () => {
    const { wrapper, materials } = await mountPage()
    await chooseFile(wrapper, file('big.pdf', DEFAULT_MAX_BYTES + 1))
    expect(wrapper.get('[data-test="upload-error"]').text()).toContain('50 MiB')
    await submitUpload(wrapper)
    expect(materials.upload).not.toHaveBeenCalled()
  })

  it('服务端 415 UNSUPPORTED_FORMAT：提示支持格式，不提供重试', async () => {
    const materials = fakeMaterialsApi({
      upload: async () => Promise.reject(apiError(415, 'UNSUPPORTED_FORMAT', { reason: 'content_mismatch' })),
    })
    const { wrapper } = await mountPage({ materials })
    await chooseFile(wrapper, file('fake.pdf'))
    await submitUpload(wrapper)
    const alert = wrapper.get('[data-test="upload-error"]')
    expect(alert.text()).toMatch(/PDF.*DOCX.*TXT.*Markdown/)
    expect(alert.text()).not.toContain('服务端原文')
    expect(wrapper.find('[data-test="upload-retry"]').exists()).toBe(false)
  })

  it('服务端 413 FILE_TOO_LARGE：按 details.limit_bytes 提示上限', async () => {
    const materials = fakeMaterialsApi({
      upload: async () => Promise.reject(apiError(413, 'FILE_TOO_LARGE', { limit_bytes: 10 * 1024 * 1024 })),
    })
    const { wrapper } = await mountPage({ materials })
    await chooseFile(wrapper, file('a.pdf'))
    await submitUpload(wrapper)
    expect(wrapper.get('[data-test="upload-error"]').text()).toContain('10 MiB')
  })
})

// ---------------------------------------------------------------- 上传上限（ADR-022）

describe('H02 上传上限取自服务端 UPLOAD_MAX_BYTES（ADR-022）', () => {
  it('按课程读取上传策略，提示与本地校验都用服务端上限', async () => {
    const materials = fakeMaterialsApi({ uploadPolicy: async () => ({ max_bytes: 2048 }) })
    const { wrapper } = await mountPage({ materials })
    expect(materials.uploadPolicy).toHaveBeenCalledWith(CID, expect.anything())
    expect(wrapper.get('[data-test="upload-hint"]').text()).toContain('2 KiB')
    expect(wrapper.get('[data-test="upload-hint"]').text()).not.toContain('50 MiB')
    await chooseFile(wrapper, file('a.pdf', 2049))
    expect(wrapper.get('[data-test="upload-error"]').text()).toContain('2 KiB')
    await submitUpload(wrapper)
    expect(materials.upload).not.toHaveBeenCalled()
  })

  it('服务端上限大于 50 MiB 时，不再按 50 MiB 在本地拦截', async () => {
    const materials = fakeMaterialsApi({ uploadPolicy: async () => ({ max_bytes: 100 * 1024 * 1024 }) })
    const { wrapper } = await mountPage({ materials })
    expect(wrapper.get('[data-test="upload-hint"]').text()).toContain('100 MiB')
    await chooseFile(wrapper, file('big.pdf', 60 * 1024 * 1024))
    expect(wrapper.find('[data-test="upload-error"]').exists()).toBe(false)
    await submitUpload(wrapper)
    expect(materials.upload).toHaveBeenCalledTimes(1)
  })

  it('策略读取失败：页面照常可用，提示以服务器为准，不做本地大小拦截', async () => {
    const materials = fakeMaterialsApi({ uploadPolicy: async () => Promise.reject(new NetworkError(new TypeError('offline'))) })
    const { wrapper } = await mountPage({ materials })
    expect(wrapper.find('[data-test="materials-error"]').exists()).toBe(false)
    const hint = wrapper.get('[data-test="upload-hint"]').text()
    expect(hint).toContain('以服务器为准')
    expect(hint).not.toContain('MiB')
    await chooseFile(wrapper, file('big.pdf', 60 * 1024 * 1024))
    expect(wrapper.find('[data-test="upload-error"]').exists()).toBe(false)
    await submitUpload(wrapper)
    expect(materials.upload).toHaveBeenCalledTimes(1)
  })

  it('413 带 limit_bytes 时刷新本地上限，之后超限文件在本地拦截', async () => {
    const materials = fakeMaterialsApi({
      uploadPolicy: async () => Promise.reject(new NetworkError(new TypeError('offline'))),
      upload: async () => Promise.reject(apiError(413, 'FILE_TOO_LARGE', { limit_bytes: 1024 * 1024 })),
    })
    const { wrapper } = await mountPage({ materials })
    await chooseFile(wrapper, file('a.pdf', 2 * 1024 * 1024))
    await submitUpload(wrapper)
    expect(materials.upload).toHaveBeenCalledTimes(1)
    expect(wrapper.get('[data-test="upload-hint"]').text()).toContain('1 MiB')
    await chooseFile(wrapper, file('b.pdf', 2 * 1024 * 1024))
    expect(wrapper.get('[data-test="upload-error"]').text()).toContain('1 MiB')
    await submitUpload(wrapper)
    expect(materials.upload).toHaveBeenCalledTimes(1)
  })

  it('非课程教师不读取上传策略', async () => {
    const courses = fakeCoursesApi({ get: async (cid) => course(cid, { my_role: 'student' }) })
    const { materials } = await mountPage({ courses })
    expect(materials.uploadPolicy).not.toHaveBeenCalled()
  })

  it('上传失败（网络）可重试：重试用同一文件，成功后开始订阅进度', async () => {
    let attempt = 0
    const materials = fakeMaterialsApi({
      upload: async () => {
        attempt += 1
        if (attempt === 1) throw new NetworkError(new TypeError('offline'))
        return { task_id: 't9', document_id: 'd_t9' }
      },
    })
    const { wrapper, events } = await mountPage({ materials })
    const f = file('讲义.pdf')
    await chooseFile(wrapper, f)
    await submitUpload(wrapper)
    expect(wrapper.get('[data-test="upload-error"]').text()).toContain('网络')
    await wrapper.get('[data-test="upload-retry"]').trigger('click')
    await flushPromises()
    expect(materials.upload).toHaveBeenCalledTimes(2)
    expect(materials.upload.mock.calls[1]![1]).toBe(f)
    expect(wrapper.find('[data-test="upload-error"]').exists()).toBe(false)
    expect(events.client.subscribe).toHaveBeenCalledTimes(1)
    expect(events.last().taskId).toBe('t9')
  })

  it('上传中防重入：连续提交只上传一次，按钮禁用', async () => {
    const pending = deferred<{ task_id: string; document_id: string }>()
    const materials = fakeMaterialsApi({ upload: () => pending.promise })
    const { wrapper } = await mountPage({ materials })
    await chooseFile(wrapper, file('a.pdf'))
    const form = wrapper.get('[data-test="material-upload-form"]')
    await form.trigger('submit')
    await form.trigger('submit')
    await flushPromises()
    expect(materials.upload).toHaveBeenCalledTimes(1)
    expect(wrapper.get('[data-test="upload-submit"]').attributes('disabled')).toBeDefined()
    pending.resolve({ task_id: 't1', document_id: 'd_t1' })
    await flushPromises()
  })

  it('上传成功：刷新列表，按 task_id 与当前课程作用域订阅，阶段事件更新进度条', async () => {
    let listed: Document[] = []
    const materials = fakeMaterialsApi({ list: async () => listed })
    const { wrapper, events } = await mountPage({ materials })
    await chooseFile(wrapper, file('第一章.pdf'))
    listed = [doc('d_t1', { filename: '第一章.pdf', parse_status: 'queued' })]
    await submitUpload(wrapper)
    expect(materials.upload.mock.calls[0]![0]).toBe(CID)
    expect(materials.list).toHaveBeenCalledTimes(2)
    const sub = events.last()
    expect(sub.taskId).toBe('t1')
    expect(sub.scope.courseId).toBe(CID)
    expect(wrapper.get('[data-test="upload-success"]').attributes('role')).toBe('status')

    events.stage('t1', 'extracting', 0.42)
    await flushPromises()
    const r = row(wrapper, 'd_t1')
    expect(r.get('[data-test="material-status"]').text()).toBe('抽取中')
    const bar = r.get('[data-test="material-progress"]')
    expect(bar.attributes('role')).toBe('progressbar')
    expect(bar.attributes('aria-valuenow')).toBe('42')
    expect(bar.attributes('aria-label')).toContain('第一章.pdf')

    events.stage('t1', 'awaiting_review', 0.95)
    await flushPromises()
    expect(row(wrapper, 'd_t1').get('[data-test="material-status"]').text()).toBe('待审核')
    expect(row(wrapper, 'd_t1').find('[data-test="task-cancel"]').exists()).toBe(false)
  })

  it('列表刷新前任务行也可见（以上传的文件名占位）', async () => {
    const { wrapper, events } = await mountPage()
    await chooseFile(wrapper, file('第二章.docx'))
    await submitUpload(wrapper)
    events.stage('t1', 'parsing', 0.1)
    await flushPromises()
    expect(row(wrapper, 'd_t1').text()).toContain('第二章.docx')
    expect(row(wrapper, 'd_t1').get('[data-test="material-status"]').text()).toBe('解析中')
  })
})

// ---------------------------------------------------------------- 取消

async function uploaded(options: Parameters<typeof mountPage>[0] = {}) {
  const ctx = await mountPage(options)
  await chooseFile(ctx.wrapper, file('第一章.pdf'))
  await submitUpload(ctx.wrapper)
  return ctx
}

describe('H02 取消', () => {
  it('处理中取消：响应 cancel_requested=true 显示「取消中」，收到 cancelled 事件后显示「已取消」', async () => {
    const materials = fakeMaterialsApi({
      cancelTask: async (tid) => task(tid, 'extracting', { cancel_requested: true, document_id: 'd_t1' }),
    })
    const { wrapper, events } = await uploaded({ materials })
    events.stage('t1', 'extracting', 0.4)
    await flushPromises()
    await row(wrapper, 'd_t1').get('[data-test="task-cancel"]').trigger('click')
    await flushPromises()
    expect(materials.cancelTask).toHaveBeenCalledWith('t1', expect.anything())
    expect(row(wrapper, 'd_t1').get('[data-test="material-status"]').text()).toBe('取消中')
    expect(row(wrapper, 'd_t1').find('[data-test="task-cancel"]').exists()).toBe(false)

    events.cancelled('t1')
    await flushPromises()
    expect(row(wrapper, 'd_t1').get('[data-test="material-status"]').text()).toBe('已取消')
    expect(row(wrapper, 'd_t1').text()).not.toContain('取消中')
  })

  it('SSE 推来 cancel_requested=true（如另一标签页取消）也显示「取消中」', async () => {
    const { wrapper, events } = await uploaded()
    events.stage('t1', 'merging', 0.7, true)
    await flushPromises()
    expect(row(wrapper, 'd_t1').get('[data-test="material-status"]').text()).toBe('取消中')
  })

  it('排队中取消：响应 stage=cancelled 直接显示「已取消」', async () => {
    const materials = fakeMaterialsApi({ cancelTask: async (tid) => task(tid, 'cancelled', { document_id: 'd_t1' }) })
    const { wrapper, events } = await uploaded({ materials })
    events.stage('t1', 'queued', 0)
    await flushPromises()
    await row(wrapper, 'd_t1').get('[data-test="task-cancel"]').trigger('click')
    await flushPromises()
    expect(row(wrapper, 'd_t1').get('[data-test="material-status"]').text()).toBe('已取消')
  })

  it('提交取消期间按钮禁用，重复点击只发一次', async () => {
    const pending = deferred<Task>()
    const materials = fakeMaterialsApi({ cancelTask: () => pending.promise })
    const { wrapper, events } = await uploaded({ materials })
    events.stage('t1', 'parsing', 0.1)
    await flushPromises()
    const button = row(wrapper, 'd_t1').get('[data-test="task-cancel"]')
    await button.trigger('click')
    await button.trigger('click')
    expect(materials.cancelTask).toHaveBeenCalledTimes(1)
    expect(button.attributes('disabled')).toBeDefined()
    // 提交中不是「取消中」：取消中只以服务端 cancel_requested 为准
    expect(row(wrapper, 'd_t1').get('[data-test="material-status"]').text()).toBe('解析中')
    pending.resolve(task('t1', 'parsing', { cancel_requested: true, document_id: 'd_t1' }))
    await flushPromises()
    expect(row(wrapper, 'd_t1').get('[data-test="material-status"]').text()).toBe('取消中')
  })

  it('409 persisting：以 details.stage 刷新为「入库中」并提示不可取消，不假装取消成功', async () => {
    const materials = fakeMaterialsApi({
      cancelTask: async () =>
        Promise.reject(
          apiError(409, 'TASK_NOT_CANCELLABLE', { stage: 'persisting', reason: 'persisting_uninterruptible' }),
        ),
    })
    const { wrapper, events } = await uploaded({ materials })
    events.stage('t1', 'merging', 0.7)
    await flushPromises()
    await row(wrapper, 'd_t1').get('[data-test="task-cancel"]').trigger('click')
    await flushPromises()
    const r = row(wrapper, 'd_t1')
    expect(r.get('[data-test="material-status"]').text()).toBe('入库中')
    expect(r.get('[data-test="cancel-error"]').attributes('role')).toBe('alert')
    expect(r.get('[data-test="cancel-error"]').text()).toContain('正在入库')
    expect(r.text()).not.toContain('取消中')
    expect(r.text()).not.toContain('已取消')
    expect(r.find('[data-test="task-cancel"]').exists()).toBe(false)
  })

  it('409 already_terminal：以实际终态刷新', async () => {
    const materials = fakeMaterialsApi({
      cancelTask: async () =>
        Promise.reject(apiError(409, 'TASK_NOT_CANCELLABLE', { stage: 'cancelled', reason: 'already_terminal' })),
    })
    const { wrapper, events } = await uploaded({ materials })
    events.stage('t1', 'extracting', 0.4)
    await flushPromises()
    await row(wrapper, 'd_t1').get('[data-test="task-cancel"]').trigger('click')
    await flushPromises()
    expect(row(wrapper, 'd_t1').get('[data-test="material-status"]').text()).toBe('已取消')
  })

  it('取消请求网络失败：提示可再次取消，状态不变', async () => {
    const materials = fakeMaterialsApi({
      cancelTask: async () => Promise.reject(new NetworkError(new TypeError('offline'))),
    })
    const { wrapper, events } = await uploaded({ materials })
    events.stage('t1', 'extracting', 0.4)
    await flushPromises()
    await row(wrapper, 'd_t1').get('[data-test="task-cancel"]').trigger('click')
    await flushPromises()
    const r = row(wrapper, 'd_t1')
    expect(r.get('[data-test="cancel-error"]').text()).toContain('网络')
    expect(r.get('[data-test="material-status"]').text()).toBe('抽取中')
    expect(r.find('[data-test="task-cancel"]').exists()).toBe(true)
  })

  it('入库中不显示取消按钮', async () => {
    const { wrapper, events } = await uploaded()
    events.stage('t1', 'persisting', 0.85)
    await flushPromises()
    expect(row(wrapper, 'd_t1').find('[data-test="task-cancel"]').exists()).toBe(false)
  })
})

// ---------------------------------------------------------------- 失败与重试

describe('H02 任务失败与重试', () => {
  it('任务失败：按错误码显示固定文案（不回显服务端 message），可用同一文件重新上传', async () => {
    const { wrapper, events, materials } = await uploaded()
    events.failed('t1', 'DOCUMENT_UNREADABLE')
    await flushPromises()
    const r = row(wrapper, 'd_t1')
    expect(r.get('[data-test="material-status"]').text()).toBe('处理失败')
    expect(r.get('[data-test="task-error"]').text()).toContain('无法解析')
    expect(r.text()).not.toContain('服务端原文')

    await r.get('[data-test="task-retry"]').trigger('click')
    await flushPromises()
    expect(materials.upload).toHaveBeenCalledTimes(2)
    expect((materials.upload.mock.calls[1]![1] as File).name).toBe('第一章.pdf')
    // 再处理一律新建任务（task-processing I3）：订阅新 task_id
    expect(events.last().taskId).toBe('t2')
  })

  it('已取消的任务也可重新上传', async () => {
    const { wrapper, events, materials } = await uploaded()
    events.cancelled('t1')
    await flushPromises()
    await row(wrapper, 'd_t1').get('[data-test="task-retry"]').trigger('click')
    await flushPromises()
    expect(materials.upload).toHaveBeenCalledTimes(2)
  })

  it('进度流降级轮询与重连中给出提示', async () => {
    const { wrapper, events } = await uploaded()
    events.state('t1', 'reconnecting')
    await flushPromises()
    expect(row(wrapper, 'd_t1').get('[data-test="stream-status"]').text()).toContain('重连')
    events.state('t1', 'polling')
    await flushPromises()
    expect(row(wrapper, 'd_t1').get('[data-test="stream-status"]').text()).toContain('定时刷新')
  })

  it('轮询快照同样更新状态', async () => {
    const { wrapper, events } = await uploaded()
    events.last('t1').handlers.onUpdate({
      source: 'poll',
      final: false,
      task: task('t1', 'merging', { progress: 0.75, document_id: 'd_t1' }),
    })
    await flushPromises()
    expect(row(wrapper, 'd_t1').get('[data-test="material-status"]').text()).toBe('融合中')
  })

  it('进度流不可恢复中断：提示并可重新连接', async () => {
    const { wrapper, events } = await uploaded()
    events.stage('t1', 'extracting', 0.4)
    events.close('t1', { kind: 'fatal', error: apiError(404, 'NOT_FOUND') })
    await flushPromises()
    const r = row(wrapper, 'd_t1')
    expect(r.get('[data-test="stream-status"]').text()).toContain('中断')
    await r.get('[data-test="stream-reconnect"]').trigger('click')
    await flushPromises()
    expect(events.client.subscribe).toHaveBeenCalledTimes(2)
    expect(events.last().taskId).toBe('t1')
    expect(row(wrapper, 'd_t1').find('[data-test="stream-reconnect"]').exists()).toBe(false)
  })
})

// ---------------------------------------------------------------- 离开页面

describe('H02 离开页面关闭流', () => {
  it('路由离开（同一课程的课程页）时关闭全部订阅', async () => {
    const { wrapper, events, router } = await uploaded()
    await chooseFile(wrapper, file('第二章.pdf'))
    await submitUpload(wrapper)
    expect(events.subs).toHaveLength(2)
    await router.push(`/courses/${CID}`)
    await flushPromises()
    expect(events.subs.every((s) => s.close.mock.calls.length === 1)).toBe(true)
  })

  it('卸载时关闭订阅，迟到事件不再报错', async () => {
    const { wrapper, events } = await uploaded()
    const sub = events.last()
    wrapper.unmount()
    expect(sub.close).toHaveBeenCalledTimes(1)
    expect(() =>
      sub.handlers.onUpdate({
        source: 'stream',
        event: 'stage',
        final: false,
        data: { task_id: 't1', stage: 'parsing', progress: 0.1, cancel_requested: false },
      }),
    ).not.toThrow()
  })

  // 回同一课程的课程页不会使课程作用域失效，必须由页面自己中止
  it.each(['/teacher', `/courses/${CID}`])('离开页面（到 %s）时中止在途上传', async (target) => {
    let uploadSignal: AbortSignal | undefined
    const materials = fakeMaterialsApi({
      upload: (_cid, _file, control) => {
        uploadSignal = control?.signal
        return new Promise(() => undefined)
      },
    })
    const { wrapper, router } = await mountPage({ materials })
    await chooseFile(wrapper, file('a.pdf'))
    await submitUpload(wrapper)
    await router.push(target)
    await flushPromises()
    expect(uploadSignal?.aborted).toBe(true)
  })

  it('切换到另一课程的资料页：关闭旧课程订阅并按新课程重新加载', async () => {
    const { wrapper, events, router, materials } = await uploaded()
    const old = events.last()
    await router.push('/courses/c2/materials')
    await flushPromises()
    expect(old.close).toHaveBeenCalled()
    expect(materials.list.mock.calls.at(-1)![0]).toBe('c2')
    expect(wrapper.findAll('[data-test="material-row"]')).toHaveLength(0)
  })
})

// ---------------------------------------------------------------- 路由接入

describe('H02 路由接入', () => {
  it('注入资料页后注册 /courses/:cid/materials', async () => {
    const { router } = await mountPage()
    expect(router.currentRoute.value.name).toBe(MATERIALS_ROUTE)
    expect(router.currentRoute.value.params.cid).toBe(CID)
  })

  it('未注入资料页时不注册资料路由', () => {
    const router = createAppRouter({
      history: createMemoryHistory(),
      getAccountRole: () => 'teacher',
      coursesComponent: CoursesView,
    })
    expect(router.hasRoute(MATERIALS_ROUTE)).toBe(false)
  })

  it('课程页只对课程内教师显示资料管理入口', async () => {
    const teacher = await mountPage({ path: `/courses/${CID}` })
    expect(teacher.router.currentRoute.value.name).toBe(COURSE_ROUTE)
    const link = teacher.wrapper.get('[data-test="materials-link"]')
    expect(link.attributes('href')).toBe(`/courses/${CID}/materials`)
    teacher.wrapper.unmount()

    setActivePinia((pinia = createPinia()))
    const student = await mountPage({
      path: `/courses/${CID}`,
      accountRole: 'student',
      courses: fakeCoursesApi({ get: async (cid) => course(cid, { my_role: 'student' }) }),
    })
    expect(student.wrapper.find('[data-test="materials-link"]').exists()).toBe(false)
  })

  it('未注入资料 API 时给出明确错误', () => {
    expect(() =>
      mount(MaterialsView, { global: { plugins: [pinia] } }),
    ).toThrow(/MATERIALS_API_KEY|COURSES_API_KEY|TASK_EVENTS_CLIENT_KEY/)
  })
})

// ---------------------------------------------------------------- ADR-021：刷新后续看进度、删除资料

describe('H02 刷新后续看处理中的资料（Document.task_id）', () => {
  it('列表中处理中的资料按 task_id 订阅进度，并可取消', async () => {
    const materials = fakeMaterialsApi({
      list: async () => [doc('d9', { parse_status: 'extracting', task_id: 't9' })],
    })
    const { wrapper, events } = await mountPage({ materials })

    expect(events.last().taskId).toBe('t9')
    events.stage('t9', 'merging', 0.6)
    await flushPromises()
    const r = row(wrapper, 'd9')
    expect(r.get('[data-test="material-status"]').text()).toBe('融合中')
    expect(r.get('[data-test="material-progress"]').attributes('aria-valuenow')).toBe('60')

    await r.get('[data-test="task-cancel"]').trigger('click')
    await flushPromises()
    expect(materials.cancelTask).toHaveBeenCalledWith('t9', expect.anything())
  })

  it('已结束或待审核的资料不订阅；没有 task_id 的资料也不订阅', async () => {
    const materials = fakeMaterialsApi({
      list: async () => [
        doc('d1', { parse_status: 'awaiting_review', task_id: 't1' }),
        doc('d2', { parse_status: 'failed', task_id: 't2' }),
        doc('d3', { parse_status: 'queued', task_id: null }),
      ],
    })
    const { events } = await mountPage({ materials })

    expect(events.subs).toHaveLength(0)
  })

  it('离开页面时关闭按 task_id 续订的流', async () => {
    const materials = fakeMaterialsApi({ list: async () => [doc('d9', { parse_status: 'parsing', task_id: 't9' })] })
    const { router, events } = await mountPage({ materials })

    await router.push({ name: COURSE_ROUTE, params: { cid: CID } })
    await flushPromises()
    expect(events.last('t9').close).toHaveBeenCalled()
  })
})

describe('H02 删除资料（ADR-021）', () => {
  async function withDocs(docs: Document[], overrides: Partial<MaterialsApi> = {}) {
    const materials = fakeMaterialsApi({ list: async () => docs, ...overrides })
    return mountPage({ materials })
  }

  it('失败与已取消的资料可删除：先确认，确认后调用接口并移除该行', async () => {
    const { wrapper, materials } = await withDocs([
      doc('d1', { parse_status: 'failed', task_id: 't1' }),
      doc('d2', { parse_status: 'cancelled', task_id: 't2' }),
    ])

    const r = row(wrapper, 'd1')
    await r.get('[data-test="material-delete"]').trigger('click')
    await flushPromises()
    expect(materials.deleteDocument).not.toHaveBeenCalled()
    await row(wrapper, 'd1').get('[data-test="material-delete-confirm"]').trigger('click')
    await flushPromises()

    expect(materials.deleteDocument).toHaveBeenCalledTimes(1)
    expect(materials.deleteDocument).toHaveBeenCalledWith(CID, 'd1', expect.anything())
    expect(wrapper.find('[data-test="material-row"][data-document-id="d1"]').exists()).toBe(false)
    expect(row(wrapper, 'd2').find('[data-test="material-delete"]').exists()).toBe(true)
  })

  it('可以取消删除确认', async () => {
    const { wrapper, materials } = await withDocs([doc('d1', { parse_status: 'failed', task_id: 't1' })])
    await row(wrapper, 'd1').get('[data-test="material-delete"]').trigger('click')
    await flushPromises()
    await row(wrapper, 'd1').get('[data-test="material-delete-cancel"]').trigger('click')
    await flushPromises()

    expect(materials.deleteDocument).not.toHaveBeenCalled()
    expect(row(wrapper, 'd1').find('[data-test="material-delete"]').exists()).toBe(true)
  })

  it.each(['queued', 'extracting', 'persisting', 'awaiting_review', 'completed'] as const)(
    '%s 的资料不显示删除按钮',
    async (stage) => {
      const { wrapper } = await withDocs([doc('d1', { parse_status: stage, task_id: null })])
      expect(row(wrapper, 'd1').find('[data-test="material-delete"]').exists()).toBe(false)
    },
  )

  it('删除中重复确认只发一次请求', async () => {
    const pending = deferred<undefined>()
    const { wrapper, materials } = await withDocs([doc('d1', { parse_status: 'failed', task_id: 't1' })], {
      deleteDocument: () => pending.promise,
    })
    await row(wrapper, 'd1').get('[data-test="material-delete"]').trigger('click')
    await flushPromises()
    const confirm = row(wrapper, 'd1').get('[data-test="material-delete-confirm"]')
    // 不等待重渲染连续点击：按钮禁用前两次点击都会到达
    void confirm.trigger('click')
    void confirm.trigger('click')
    await flushPromises()
    expect(materials.deleteDocument).toHaveBeenCalledTimes(1)
    expect(confirm.attributes('disabled')).toBeDefined()
    pending.resolve(undefined)
    await flushPromises()
    expect(wrapper.find('[data-test="material-row"][data-document-id="d1"]').exists()).toBe(false)
  })

  it('409 contributed（更早的任务已进入图谱）：提示并隐藏删除入口，行仍显示最新任务状态', async () => {
    const { wrapper } = await withDocs([doc('d1', { parse_status: 'failed', task_id: 't1' })], {
      deleteDocument: async () => {
        throw apiError(409, 'DOCUMENT_NOT_DELETABLE', { stage: 'completed', reason: 'contributed' })
      },
    })
    await row(wrapper, 'd1').get('[data-test="material-delete"]').trigger('click')
    await flushPromises()
    await row(wrapper, 'd1').get('[data-test="material-delete-confirm"]').trigger('click')
    await flushPromises()

    const r = row(wrapper, 'd1')
    expect(r.get('[data-test="material-status"]').text()).toBe('处理失败')
    expect(r.get('[data-test="delete-error"]').text()).toContain('已进入图谱')
    expect(r.find('[data-test="material-delete"]').exists()).toBe(false)
    expect(r.text()).not.toContain('服务端原文')
  })

  it('409 processing（列表已过时）：按 details.stage 刷新为处理中，不再显示删除', async () => {
    const { wrapper } = await withDocs([doc('d1', { parse_status: 'cancelled', task_id: 't1' })], {
      deleteDocument: async () => {
        throw apiError(409, 'DOCUMENT_NOT_DELETABLE', { stage: 'parsing', reason: 'processing' })
      },
    })
    await row(wrapper, 'd1').get('[data-test="material-delete"]').trigger('click')
    await flushPromises()
    await row(wrapper, 'd1').get('[data-test="material-delete-confirm"]').trigger('click')
    await flushPromises()

    const r = row(wrapper, 'd1')
    expect(r.get('[data-test="material-status"]').text()).toBe('解析中')
    expect(r.get('[data-test="delete-error"]').text()).toContain('仍在处理')
    expect(r.find('[data-test="material-delete"]').exists()).toBe(false)
  })

  it('409 cleanup_pending：提示稍后再试，保留删除入口', async () => {
    const { wrapper } = await withDocs([doc('d1', { parse_status: 'failed', task_id: 't1' })], {
      deleteDocument: async () => {
        throw apiError(409, 'DOCUMENT_NOT_DELETABLE', { stage: 'failed', reason: 'cleanup_pending' })
      },
    })
    await row(wrapper, 'd1').get('[data-test="material-delete"]').trigger('click')
    await flushPromises()
    await row(wrapper, 'd1').get('[data-test="material-delete-confirm"]').trigger('click')
    await flushPromises()

    const r = row(wrapper, 'd1')
    expect(r.get('[data-test="delete-error"]').text()).toContain('稍后')
    expect(r.find('[data-test="material-delete"]').exists()).toBe(true)
  })

  it('404：资料已不存在，直接从列表移除', async () => {
    const { wrapper } = await withDocs([doc('d1', { parse_status: 'failed', task_id: 't1' })], {
      deleteDocument: async () => {
        throw apiError(404, 'NOT_FOUND')
      },
    })
    await row(wrapper, 'd1').get('[data-test="material-delete"]').trigger('click')
    await flushPromises()
    await row(wrapper, 'd1').get('[data-test="material-delete-confirm"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-test="material-row"][data-document-id="d1"]').exists()).toBe(false)
  })

  it('网络失败：提示可重试，保留该行', async () => {
    const { wrapper } = await withDocs([doc('d1', { parse_status: 'failed', task_id: 't1' })], {
      deleteDocument: async () => {
        throw new NetworkError(new TypeError('offline'))
      },
    })
    await row(wrapper, 'd1').get('[data-test="material-delete"]').trigger('click')
    await flushPromises()
    await row(wrapper, 'd1').get('[data-test="material-delete-confirm"]').trigger('click')
    await flushPromises()

    const r = row(wrapper, 'd1')
    expect(r.get('[data-test="delete-error"]').text()).toContain('网络')
    expect(r.find('[data-test="material-delete"]').exists()).toBe(true)
  })

  it('本次会话上传后失败的资料删除后，文件缓存与跟踪一并清除', async () => {
    const { wrapper, events, materials } = await mountPage()
    await chooseFile(wrapper, file('第一章.pdf', 16, 'application/pdf'))
    await submitUpload(wrapper)
    events.failed('t1', 'DOCUMENT_UNREADABLE')
    await flushPromises()

    await row(wrapper, 'd_t1').get('[data-test="material-delete"]').trigger('click')
    await flushPromises()
    await row(wrapper, 'd_t1').get('[data-test="material-delete-confirm"]').trigger('click')
    await flushPromises()

    expect(materials.deleteDocument).toHaveBeenCalledWith(CID, 'd_t1', expect.anything())
    expect(wrapper.find('[data-test="material-row"][data-document-id="d_t1"]').exists()).toBe(false)
  })
})
