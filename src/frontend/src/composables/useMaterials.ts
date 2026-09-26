import { computed, onScopeDispose, ref, watch, type Ref } from 'vue'
import type { components } from '../../../contracts/v1/generated/typescript/openapi'
import type { CoursesApi } from '../api/courses'
import { AbortedError, ApiError, InvalidResponseError, NetworkError, TimeoutError } from '../api/http'
import type { DocumentFormat, MaterialDocument, MaterialsApi, UploadAccepted } from '../api/materials'
import type { TaskEventsClient, TaskStage, TaskStreamState, TaskSubscription } from '../api/taskEvents'
import { useCourseStore, type CourseRequestScope } from '../stores/course'

/**
 * 资料上传与处理进度（H02）。
 *
 * - 页面只对课程内教师开放（`specs/identity-access.md`：`listDocuments` / `uploadDocument` / 任务操作
 *   均为课程教师）；先读课程 `my_role` 作界面引导，授权仍以后端 403 为准。
 * - 上传前本地校验扩展名与大小（PDF/DOCX/TXT/Markdown）。大小上限取自 `getUploadPolicy`（ADR-022，
 *   即服务端 `UPLOAD_MAX_BYTES`）；取不到时跳过本地大小校验、提示以服务器为准。
 *   服务端 413/415 仍按 `errors.v1.md` 提示，413 的 `details.limit_bytes` 同时刷新本地上限。
 * - 上传成功后按 `task_id` 经 C12 `TaskEventsClient` 订阅进度，作用域取自课程 store。
 * - 「取消中」只看服务端 `cancel_requested = true` 且非终态，「已取消」只看 `stage = cancelled`；
 *   409 `TASK_NOT_CANCELLABLE` 以 `details.stage` 刷新界面，不假装取消成功（`specs/task-processing.md` §4）。
 * - 失败/取消后的重试 = 用本次会话保留的同一文件重新上传，生成新任务（I3：不复活旧任务；契约无再处理端点）。
 * - 列表中仍在处理的资料按 `Document.task_id` 续订进度（ADR-021），刷新页面后仍可看进度与取消。
 * - 失败/已取消的资料可删除（ADR-021）：先确认再请求；409 `DOCUMENT_NOT_DELETABLE` 以 `details.stage` 刷新。
 * - 离开页面（路由离开、卸载、切课）关闭全部订阅并中止在途请求；迟到回调一律丢弃。
 * - 错误只按状态码/错误码给固定文案，不回显服务端 message。
 */

type ErrorBody = components['schemas']['Error']

// ---------------------------------------------------------------- 文件校验

/** 与后端 `file_storage._EXTENSIONS` 一致（大小写不敏感） */
export const MATERIAL_EXTENSIONS = ['.pdf', '.docx', '.txt', '.md', '.markdown'] as const
export const SUPPORTED_FORMATS_TEXT = 'PDF、DOCX、TXT、Markdown（.md / .markdown）'
/** `<input accept>`：扩展名 + 契约 `uploadDocument` 声明的媒体类型 */
export const MATERIAL_ACCEPT = [
  ...MATERIAL_EXTENSIONS,
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'text/plain',
  'text/markdown',
].join(',')

const FORMAT_BY_EXTENSION: Record<(typeof MATERIAL_EXTENSIONS)[number], DocumentFormat> = {
  '.pdf': 'pdf',
  '.docx': 'docx',
  '.txt': 'txt',
  '.md': 'markdown',
  '.markdown': 'markdown',
}
const FORMAT_LABEL: Record<DocumentFormat, string> = { pdf: 'PDF', docx: 'DOCX', txt: 'TXT', markdown: 'Markdown' }

function extensionOf(name: string): string {
  const dot = name.lastIndexOf('.')
  // 与后端 Path.suffix 一致：「.md」这类只有点前缀的名字没有扩展名
  return dot <= 0 ? '' : name.slice(dot).toLowerCase()
}

function formatOf(name: string): DocumentFormat | null {
  const ext = extensionOf(name)
  return (FORMAT_BY_EXTENSION as Record<string, DocumentFormat | undefined>)[ext] ?? null
}

export function formatBytes(bytes: number): string {
  const mib = bytes / (1024 * 1024)
  if (mib >= 1) return `${Number.isInteger(mib) ? mib : mib.toFixed(1)} MiB`
  const kib = bytes / 1024
  if (kib >= 1) return `${Number.isInteger(kib) ? kib : kib.toFixed(1)} KiB`
  return `${bytes} B`
}

const UNSUPPORTED_MESSAGE = `不支持该文件格式，仅支持 ${SUPPORTED_FORMATS_TEXT}。`

/**
 * 本地校验；通过返回 null，否则返回提示文案。
 * `maxBytes` 为服务端上传上限（ADR-022）；`null` 表示未知，此时不做大小校验，交服务端 413 判定。
 */
export function validateMaterialFile(file: File, maxBytes: number | null): string | null {
  if (formatOf(file.name) === null) return UNSUPPORTED_MESSAGE
  if (file.size === 0) return '文件为空，请选择有内容的资料。'
  if (maxBytes !== null && file.size > maxBytes) {
    return `文件大小 ${formatBytes(file.size)} 超过 ${formatBytes(maxBytes)} 上限，请压缩或拆分后上传。`
  }
  return null
}

// ---------------------------------------------------------------- 状态文案

export type TaskStatusKind = 'processing' | 'cancelling' | 'awaiting_review' | 'completed' | 'failed' | 'cancelled'

export interface TaskStatus {
  kind: TaskStatusKind
  label: string
}

const STAGE_LABEL: Record<TaskStage, string> = {
  queued: '排队中',
  parsing: '解析中',
  extracting: '抽取中',
  merging: '融合中',
  persisting: '入库中',
  awaiting_review: '待审核',
  completed: '已完成审核',
  failed: '处理失败',
  cancelled: '已取消',
}

const ACTIVE_STAGES: ReadonlySet<TaskStage> = new Set(['queued', 'parsing', 'extracting', 'merging', 'persisting'])
/** 可发起取消的阶段；`persisting` 不可中断（`specs/task-processing.md` §1） */
const CANCELLABLE_STAGES: ReadonlySet<TaskStage> = new Set(['queued', 'parsing', 'extracting', 'merging'])
const ALL_STAGES: ReadonlySet<string> = new Set(Object.keys(STAGE_LABEL))

/** 「取消中」与「已取消」分开：前者是非终态上的标志位，后者是终态 */
export function taskStatusOf({ stage, cancelRequested }: { stage: TaskStage; cancelRequested: boolean }): TaskStatus {
  const label = STAGE_LABEL[stage]
  switch (stage) {
    case 'cancelled':
    case 'failed':
    case 'completed':
    case 'awaiting_review':
      return { kind: stage, label }
    default:
      return cancelRequested ? { kind: 'cancelling', label: '取消中' } : { kind: 'processing', label }
  }
}

const TASK_ERROR_MESSAGE: Partial<Record<ErrorBody['code'], string>> = {
  DOCUMENT_UNREADABLE: '文件无法解析（可能已损坏、加密或没有可提取的文本）。',
  LLM_UNAVAILABLE: '模型服务暂不可用，抽取未完成。',
  EXTRACTION_INCOMPLETE: '抽取失败的片段过多，任务未完成。',
  STORAGE_UNAVAILABLE: '存储暂不可用，写入失败。',
  CYCLE_DETECTED: '自动生成的前置关系成环且无法降级。',
  TASK_ATTEMPTS_EXHAUSTED: '处理多次中断，已停止重试。',
  BUDGET_EXCEEDED: '模型调用预算已用尽。',
  INTERNAL_ERROR: '处理过程中发生内部错误。',
}

function taskErrorMessage(error: ErrorBody | null): string {
  return (error && TASK_ERROR_MESSAGE[error.code]) ?? '处理失败。'
}

const NETWORK_MESSAGE = '无法连接服务器，请检查网络后重试。'

function isNetworkFailure(cause: unknown): boolean {
  return cause instanceof NetworkError || cause instanceof TimeoutError
}

interface UploadFailure {
  message: string
  /** 同一文件可直接重试（网络、超时、服务端临时故障） */
  retryable: boolean
  /** 文件本身不合格，高亮上传控件 */
  fileInvalid: boolean
}

/** 413 `FILE_TOO_LARGE` 的 `details.limit_bytes`；缺失或不合法为 null */
function limitBytesOf(cause: unknown): number | null {
  if (!(cause instanceof ApiError) || cause.code !== 'FILE_TOO_LARGE') return null
  const limit = cause.details?.limit_bytes
  return typeof limit === 'number' && Number.isInteger(limit) && limit > 0 ? limit : null
}

function uploadFailure(cause: unknown, maxBytes: number | null): UploadFailure {
  if (isNetworkFailure(cause)) return { message: NETWORK_MESSAGE, retryable: true, fileInvalid: false }
  if (cause instanceof ApiError) {
    if (cause.code === 'UNSUPPORTED_FORMAT') {
      return {
        message: `文件格式不受支持或内容与扩展名不符，仅支持 ${SUPPORTED_FORMATS_TEXT}。`,
        retryable: false,
        fileInvalid: true,
      }
    }
    if (cause.code === 'FILE_TOO_LARGE') {
      const limit = limitBytesOf(cause) ?? maxBytes
      const text = limit === null ? '服务器上限' : `服务器上限 ${formatBytes(limit)}`
      return { message: `文件超过${text}，请压缩或拆分后上传。`, retryable: false, fileInvalid: true }
    }
    if (cause.code === 'VALIDATION_ERROR') {
      return { message: '文件名不符合要求（可能为空或过长），请重命名后上传。', retryable: false, fileInvalid: true }
    }
    if (cause.status === 401) return { message: '登录已失效，请重新登录。', retryable: false, fileInvalid: false }
    if (cause.status === 403) return { message: '当前账号无权向该课程上传资料。', retryable: false, fileInvalid: false }
    if (cause.code === 'STORAGE_UNAVAILABLE') {
      return { message: '存储暂不可用，请稍后重试。', retryable: true, fileInvalid: false }
    }
  }
  return { message: '上传失败，请稍后重试。', retryable: true, fileInvalid: false }
}

const CANCEL_REASON_MESSAGE: Record<string, string> = {
  persisting_uninterruptible: '资料正在入库，无法中断，将继续处理到待审核。',
  processing_finished: '处理已结束，无法取消；如需丢弃内容，请在审核中驳回。',
  already_terminal: '任务已结束，无法取消。',
}

const DELETE_REASON_MESSAGE: Record<string, string> = {
  processing: '资料仍在处理中，不能删除。',
  contributed: '资料已进入图谱（待审核或已完成），不能删除。',
  cleanup_pending: '资料的图谱清理尚未完成，请稍后再删除。',
}

function deleteErrorMessage(cause: unknown): string {
  if (isNetworkFailure(cause)) return '无法连接服务器，删除未提交，请检查网络后重试。'
  if (cause instanceof ApiError) {
    if (cause.status === 401) return '登录已失效，请重新登录。'
    if (cause.status === 403) return '当前账号无权删除该资料。'
  }
  return '删除失败，请稍后重试。'
}

function cancelErrorMessage(cause: unknown): string {
  if (isNetworkFailure(cause)) return '无法连接服务器，取消未提交，请检查网络后重试。'
  if (cause instanceof ApiError) {
    if (cause.status === 401) return '登录已失效，请重新登录。'
    if (cause.status === 403) return '当前账号无权取消该任务。'
    if (cause.status === 404) return '任务不存在或已无权访问。'
  }
  return '取消失败，请稍后重试。'
}

// ---------------------------------------------------------------- 视图模型

export type PageStatus = 'loading' | 'ready' | 'error' | 'forbidden'
/** C12 的连接状态，外加 `broken`：不可恢复地中断，可手动重新连接 */
export type StreamStatus = TaskStreamState | 'broken'

export interface MaterialRow {
  documentId: string
  filename: string
  formatLabel: string
  sizeLabel: string | null
  status: TaskStatus
  /** 本次会话跟踪的任务才有实时进度（0–100） */
  progressPercent: number | null
  canCancel: boolean
  cancelPending: boolean
  cancelError: string | null
  errorMessage: string | null
  /** 本次会话保留了该文件，可一键重新上传 */
  canRetry: boolean
  /** 失败/取消但没有文件可重试：引导重新选择文件 */
  needsReselect: boolean
  streamNotice: string | null
  canReconnect: boolean
  /** 失败/已取消的资料可删除（ADR-021） */
  canDelete: boolean
  confirmingDelete: boolean
  deletePending: boolean
  deleteError: string | null
}

interface DeleteState {
  confirming: boolean
  pending: boolean
  error: string | null
  /** 409 后不再提供删除入口（清理未完成除外） */
  blocked: boolean
}

interface TrackedTask {
  taskId: string
  documentId: string
  filename: string
  stage: TaskStage
  progress: number
  cancelRequested: boolean
  error: ErrorBody | null
  stream: StreamStatus
  cancelPending: boolean
  cancelError: string | null
}

const STREAM_NOTICE: Partial<Record<StreamStatus, string>> = {
  reconnecting: '实时连接中断，正在重连…',
  polling: '实时连接不可用，已改为定时刷新进度。',
  broken: '进度连接已中断，状态可能不是最新。',
}

/** 一次「打开某课程资料页」的生命周期；离开或切课即作废 */
interface PageSession {
  courseId: string
  scope: CourseRequestScope
  controller: AbortController
  subs: Map<string, TaskSubscription>
  uploading: boolean
  disposed: boolean
}

export interface UseMaterialsOptions {
  materialsApi: MaterialsApi
  coursesApi: CoursesApi
  taskEvents: TaskEventsClient
  /** 当前路由中的课程 ID；`null` 表示已离开资料页 */
  courseId: Ref<string | null>
}

export function useMaterials({ materialsApi, coursesApi, taskEvents, courseId }: UseMaterialsOptions) {
  const store = useCourseStore()

  const pageStatus = ref<PageStatus>('loading')
  const pageError = ref<string | null>(null)
  const courseName = ref<string | null>(null)
  const documents = ref<MaterialDocument[]>([])
  const tracked = ref<Record<string, TrackedTask>>({})
  // File 不放进响应式对象（代理后不再是 Blob）；按资料 ID 保存本次会话上传的文件，用于重试
  const files = new Map<string, File>()
  const retryable = ref<Record<string, true>>({})
  const deletions = ref<Record<string, DeleteState>>({})
  /** 服务端上传上限（ADR-022）；`null` = 尚未取到或读取失败 */
  const maxBytes = ref<number | null>(null)

  const selectedName = ref<string | null>(null)
  let selectedFile: File | null = null
  const fileInvalid = ref(false)
  /** 上传成功后递增，视图据此重置文件控件 */
  const selectionVersion = ref(0)
  const uploading = ref(false)
  const uploadError = ref<string | null>(null)
  const uploadSuccess = ref<string | null>(null)
  let retryFile: File | null = null
  const canRetryUpload = ref(false)

  let session: PageSession | null = null

  const alive = (s: PageSession) => s === session && !s.disposed

  function dispose(): void {
    const s = session
    if (s === null) return
    session = null
    s.disposed = true
    s.controller.abort()
    for (const sub of [...s.subs.values()]) sub.close()
    s.subs.clear()
  }

  function resetState(): void {
    pageStatus.value = 'loading'
    pageError.value = null
    courseName.value = null
    documents.value = []
    tracked.value = {}
    files.clear()
    retryable.value = {}
    deletions.value = {}
    maxBytes.value = null
    selectedName.value = null
    selectedFile = null
    fileInvalid.value = false
    uploading.value = false
    uploadError.value = null
    uploadSuccess.value = null
    retryFile = null
    canRetryUpload.value = false
  }

  function open(cid: string | null): void {
    dispose()
    resetState()
    if (cid === null) return
    store.selectCourse(cid)
    const scope = store.beginRequest()
    const s: PageSession = {
      courseId: cid,
      scope,
      controller: new AbortController(),
      subs: new Map(),
      uploading: false,
      disposed: false,
    }
    // 课程作用域失效（切课、登出）同样中止本页在途请求
    scope.signal.addEventListener('abort', () => s.controller.abort(), { once: true })
    session = s
    void load(s)
  }

  // ------------------------------------------------------------ 加载

  async function load(s: PageSession): Promise<void> {
    pageStatus.value = 'loading'
    pageError.value = null
    try {
      const detail = await coursesApi.get(s.courseId, { signal: s.controller.signal })
      if (!alive(s)) return
      courseName.value = detail.name
      if (detail.my_role !== 'teacher') {
        pageStatus.value = 'forbidden'
        pageError.value = '仅课程教师可以上传资料和查看处理进度。'
        return
      }
      void loadPolicy(s)
      const list = await materialsApi.list(s.courseId, { signal: s.controller.signal })
      if (!alive(s)) return
      // 资料按 course_id 隔离，不接收别的课程的数据
      documents.value = list.filter((d) => d.course_id === s.courseId)
      pageStatus.value = 'ready'
      adopt(s)
    } catch (cause) {
      if (!alive(s) || cause instanceof AbortedError) return
      if (cause instanceof ApiError && cause.code === 'COURSE_FORBIDDEN') {
        pageStatus.value = 'forbidden'
        pageError.value = '你无权访问该课程（可能已被移出课程）。'
        return
      }
      if (cause instanceof ApiError && cause.status === 403) {
        pageStatus.value = 'forbidden'
        pageError.value = '仅课程教师可以上传资料和查看处理进度。'
        return
      }
      pageStatus.value = 'error'
      if (cause instanceof ApiError && cause.status === 404) pageError.value = '课程不存在。'
      else if (cause instanceof ApiError && cause.status === 401) pageError.value = '登录已失效，请重新登录。'
      else pageError.value = isNetworkFailure(cause) ? NETWORK_MESSAGE : '资料列表加载失败，请稍后重试。'
    }
  }

  /** 上传策略与列表并行读取；失败只影响本地大小预检，不影响页面（ADR-022） */
  async function loadPolicy(s: PageSession): Promise<void> {
    try {
      const policy = await materialsApi.uploadPolicy(s.courseId, { signal: s.controller.signal })
      if (!alive(s)) return
      const limit = policy.max_bytes
      if (Number.isInteger(limit) && limit > 0) maxBytes.value = limit
    } catch {
      // 忽略：保持未知，上传时由服务端 413 判定并回填上限
    }
  }

  function reload(): void {
    if (session !== null) void load(session)
  }

  /** 上传后静默刷新列表；失败时保留现有行（任务行仍以上传文件名占位） */
  async function refreshList(s: PageSession): Promise<void> {
    try {
      const list = await materialsApi.list(s.courseId, { signal: s.controller.signal })
      if (!alive(s)) return
      documents.value = list.filter((d) => d.course_id === s.courseId)
      adopt(s)
    } catch {
      // 忽略：下次进入页面或上传会再刷新
    }
  }

  // ------------------------------------------------------------ 任务跟踪

  function applySnapshot(
    documentId: string,
    data: { stage: TaskStage; progress: number; cancel_requested?: boolean; error?: ErrorBody | null },
  ): void {
    const t = tracked.value[documentId]
    if (!t) return
    t.stage = data.stage
    t.progress = data.progress
    if (data.cancel_requested !== undefined) t.cancelRequested = data.cancel_requested
    t.error = data.stage === 'failed' ? (data.error ?? null) : null
  }

  function subscribe(s: PageSession, documentId: string): void {
    const t = tracked.value[documentId]
    if (!t || !alive(s)) return
    const { taskId } = t
    s.subs.get(taskId)?.close()
    s.subs.delete(taskId)
    t.stream = 'connecting'
    let sub: TaskSubscription | undefined
    sub = taskEvents.subscribe(taskId, s.scope, {
      onUpdate: (update) => {
        if (!alive(s)) return
        const data = update.source === 'stream' ? update.data : update.task
        if (update.source === 'poll' && (update.task.id !== taskId || update.task.course_id !== s.courseId)) return
        applySnapshot(documentId, data)
      },
      onState: (state) => {
        if (!alive(s)) return
        const current = tracked.value[documentId]
        if (current) current.stream = state
      },
      onClose: (reason) => {
        if (!alive(s)) return
        if (sub !== undefined && s.subs.get(taskId) === sub) s.subs.delete(taskId)
        const current = tracked.value[documentId]
        if (!current) return
        current.stream = reason.kind === 'fatal' ? 'broken' : 'closed'
      },
    })
    if (!sub.closed) s.subs.set(taskId, sub)
  }

  function track(s: PageSession, accepted: UploadAccepted, file: File): void {
    files.set(accepted.document_id, file)
    retryable.value[accepted.document_id] = true
    tracked.value[accepted.document_id] = {
      taskId: accepted.task_id,
      documentId: accepted.document_id,
      filename: file.name,
      stage: 'queued',
      progress: 0,
      cancelRequested: false,
      error: null,
      stream: 'connecting',
      cancelPending: false,
      cancelError: null,
    }
    subscribe(s, accepted.document_id)
  }

  /** 列表中仍在处理、尚未跟踪的资料：按 `task_id` 续订进度（ADR-021） */
  function adopt(s: PageSession): void {
    for (const d of documents.value) {
      if (!d.task_id || !ACTIVE_STAGES.has(d.parse_status) || tracked.value[d.id]) continue
      tracked.value[d.id] = {
        taskId: d.task_id,
        documentId: d.id,
        filename: d.filename,
        stage: d.parse_status,
        progress: 0,
        cancelRequested: false,
        error: null,
        stream: 'connecting',
        cancelPending: false,
        cancelError: null,
      }
      subscribe(s, d.id)
    }
  }

  function reconnect(documentId: string): void {
    if (session !== null) subscribe(session, documentId)
  }

  // ------------------------------------------------------------ 上传

  function selectFile(file: File | null): void {
    selectedFile = file
    selectedName.value = file?.name ?? null
    uploadSuccess.value = null
    retryFile = null
    canRetryUpload.value = false
    const problem = file === null ? null : validateMaterialFile(file, maxBytes.value)
    uploadError.value = problem
    fileInvalid.value = problem !== null
  }

  async function uploadFile(file: File): Promise<void> {
    const s = session
    // 防重入用同步标志：两次 submit 可能在按钮禁用前连续到达
    if (s === null || !alive(s) || s.uploading || pageStatus.value !== 'ready') return
    const problem = validateMaterialFile(file, maxBytes.value)
    if (problem !== null) {
      uploadError.value = problem
      fileInvalid.value = true
      return
    }
    s.uploading = true
    uploading.value = true
    uploadError.value = null
    uploadSuccess.value = null
    retryFile = null
    canRetryUpload.value = false
    try {
      const accepted = await materialsApi.upload(s.courseId, file, { signal: s.controller.signal })
      if (!alive(s)) return
      track(s, accepted, file)
      uploadSuccess.value = file.name
      selectedFile = null
      selectedName.value = null
      fileInvalid.value = false
      selectionVersion.value += 1
      void refreshList(s)
    } catch (cause) {
      if (!alive(s) || cause instanceof AbortedError) return
      maxBytes.value = limitBytesOf(cause) ?? maxBytes.value
      const failure = uploadFailure(cause, maxBytes.value)
      uploadError.value = failure.message
      fileInvalid.value = failure.fileInvalid
      retryFile = failure.retryable ? file : null
      canRetryUpload.value = failure.retryable
    } finally {
      s.uploading = false
      if (alive(s)) uploading.value = false
    }
  }

  function submitUpload(): Promise<void> {
    if (selectedFile === null) {
      if (uploadError.value === null) {
        uploadError.value = '请先选择要上传的资料文件。'
        fileInvalid.value = true
      }
      return Promise.resolve()
    }
    if (fileInvalid.value) return Promise.resolve()
    return uploadFile(selectedFile)
  }

  function retryUpload(): Promise<void> {
    return retryFile === null ? Promise.resolve() : uploadFile(retryFile)
  }

  /** 失败或已取消的任务：用同一文件重新上传，生成新资料与新任务 */
  function retryTask(documentId: string): Promise<void> {
    const file = files.get(documentId)
    return file === undefined ? Promise.resolve() : uploadFile(file)
  }

  // ------------------------------------------------------------ 取消

  async function cancel(documentId: string): Promise<void> {
    const s = session
    const t = tracked.value[documentId]
    if (s === null || !alive(s) || !t || t.cancelPending) return
    if (!CANCELLABLE_STAGES.has(t.stage) || t.cancelRequested) return
    t.cancelPending = true
    t.cancelError = null
    try {
      const snapshot = await materialsApi.cancelTask(t.taskId, { signal: s.controller.signal })
      if (!alive(s)) return
      if (snapshot.id !== t.taskId || snapshot.course_id !== s.courseId) {
        t.cancelError = '取消失败，请稍后重试。'
        return
      }
      applySnapshot(documentId, snapshot)
    } catch (cause) {
      if (!alive(s) || cause instanceof AbortedError) return
      if (cause instanceof ApiError && cause.code === 'TASK_NOT_CANCELLABLE') {
        const stage = cause.details?.stage
        const reason = cause.details?.reason
        if (typeof stage === 'string' && ALL_STAGES.has(stage)) {
          t.stage = stage as TaskStage
          if (stage === 'awaiting_review') t.progress = 0.95
          if (stage === 'completed') t.progress = 1
          if (stage !== 'failed') t.error = null
        }
        t.cancelError = (typeof reason === 'string' && CANCEL_REASON_MESSAGE[reason]) || '任务当前不可取消。'
        return
      }
      t.cancelError =
        cause instanceof InvalidResponseError ? '取消失败，请稍后重试。' : cancelErrorMessage(cause)
    } finally {
      t.cancelPending = false
    }
  }

  // ------------------------------------------------------------ 删除（ADR-021）

  function deletionOf(documentId: string): DeleteState {
    const existing = deletions.value[documentId]
    if (existing) return existing
    const created: DeleteState = { confirming: false, pending: false, error: null, blocked: false }
    deletions.value[documentId] = created
    return deletions.value[documentId]!
  }

  function requestDelete(documentId: string): void {
    const d = deletionOf(documentId)
    if (d.pending) return
    d.confirming = true
    d.error = null
  }

  function cancelDelete(documentId: string): void {
    const d = deletions.value[documentId]
    if (d && !d.pending) d.confirming = false
  }

  function forget(s: PageSession, documentId: string): void {
    const t = tracked.value[documentId]
    if (t) {
      s.subs.get(t.taskId)?.close()
      s.subs.delete(t.taskId)
    }
    documents.value = documents.value.filter((d) => d.id !== documentId)
    delete tracked.value[documentId]
    delete retryable.value[documentId]
    delete deletions.value[documentId]
    files.delete(documentId)
  }

  async function confirmDelete(documentId: string): Promise<void> {
    const s = session
    const d = deletions.value[documentId]
    // 防重入用同步标志：两次点击可能在按钮禁用前连续到达
    if (s === null || !alive(s) || !d || !d.confirming || d.pending) return
    d.pending = true
    d.error = null
    try {
      await materialsApi.deleteDocument(s.courseId, documentId, { signal: s.controller.signal })
      if (!alive(s)) return
      forget(s, documentId)
    } catch (cause) {
      if (!alive(s) || cause instanceof AbortedError) return
      if (cause instanceof ApiError && cause.status === 404) {
        forget(s, documentId)
        return
      }
      d.confirming = false
      if (cause instanceof ApiError && cause.code === 'DOCUMENT_NOT_DELETABLE') {
        const stage = cause.details?.stage
        const reason = cause.details?.reason
        // 只有「仍在处理」时阻塞任务就是当前进度所在，刷新阶段；「已进入图谱」来自更早的任务，行仍显示最新任务
        if (reason === 'processing' && typeof stage === 'string' && ALL_STAGES.has(stage)) {
          documents.value = documents.value.map((doc) =>
            doc.id === documentId ? { ...doc, parse_status: stage as TaskStage } : doc,
          )
          const t = tracked.value[documentId]
          if (t) t.stage = stage as TaskStage
        }
        d.blocked = reason !== 'cleanup_pending'
        d.error = (typeof reason === 'string' && DELETE_REASON_MESSAGE[reason]) || '资料当前不能删除。'
        return
      }
      d.error = deleteErrorMessage(cause)
    } finally {
      d.pending = false
    }
  }

  // ------------------------------------------------------------ 行

  function rowOf(
    documentId: string,
    filename: string,
    format: DocumentFormat | null,
    sizeBytes: number | undefined,
    fallbackStage: TaskStage,
  ): MaterialRow {
    const t = tracked.value[documentId]
    const stage = t?.stage ?? fallbackStage
    const status = taskStatusOf({ stage, cancelRequested: t?.cancelRequested ?? false })
    const ended = status.kind === 'failed' || status.kind === 'cancelled'
    const canRetry = ended && retryable.value[documentId] === true
    const stream = t?.stream
    const streamNotice = t && !ended && stream ? (STREAM_NOTICE[stream] ?? null) : null
    const deletion = deletions.value[documentId]
    return {
      documentId,
      filename,
      formatLabel: format === null ? '未知格式' : FORMAT_LABEL[format],
      sizeLabel: sizeBytes === undefined ? null : formatBytes(sizeBytes),
      status,
      progressPercent: t ? Math.round(Math.min(1, Math.max(0, t.progress)) * 100) : null,
      canCancel: !!t && CANCELLABLE_STAGES.has(t.stage) && !t.cancelRequested,
      cancelPending: t?.cancelPending ?? false,
      cancelError: t?.cancelError ?? null,
      errorMessage: status.kind === 'failed' ? taskErrorMessage(t?.error ?? null) : null,
      canRetry,
      needsReselect: ended && !canRetry,
      streamNotice,
      canReconnect: !!t && stream === 'broken' && ACTIVE_STAGES.has(t.stage),
      canDelete: ended && !(deletion?.blocked ?? false),
      confirmingDelete: deletion?.confirming ?? false,
      deletePending: deletion?.pending ?? false,
      deleteError: deletion?.error ?? null,
    }
  }

  const rows = computed<MaterialRow[]>(() => {
    const listed = documents.value.map((d) => rowOf(d.id, d.filename, d.format, d.size_bytes, d.parse_status))
    const seen = new Set(documents.value.map((d) => d.id))
    // 刚上传、列表尚未刷新到的资料：以上传的文件名占位
    const pending = Object.values(tracked.value)
      .filter((t) => !seen.has(t.documentId))
      .map((t) => rowOf(t.documentId, t.filename, formatOf(t.filename), files.get(t.documentId)?.size, t.stage))
    return [...listed, ...pending]
  })

  /** 提示中的上限文案；未知时为 null，视图提示以服务器为准 */
  const limitText = computed(() => (maxBytes.value === null ? null : formatBytes(maxBytes.value)))

  const isEmpty = computed(() => pageStatus.value === 'ready' && rows.value.length === 0)

  watch(courseId, open, { immediate: true })
  onScopeDispose(dispose)

  return {
    pageStatus,
    pageError,
    courseName,
    rows,
    isEmpty,
    limitText,
    reload,
    selectedName,
    fileInvalid,
    selectionVersion,
    uploading,
    uploadError,
    uploadSuccess,
    canRetryUpload,
    selectFile,
    submitUpload,
    retryUpload,
    retryTask,
    cancel,
    reconnect,
    requestDelete,
    cancelDelete,
    confirmDelete,
  }
}
