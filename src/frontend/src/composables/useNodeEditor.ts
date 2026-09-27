import { computed, onScopeDispose, reactive, ref, shallowRef, watch, type ComputedRef, type Ref } from 'vue'
import type { components } from '../../../contracts/v1/generated/typescript/openapi'
import { AbortedError, ApiError, NetworkError, TimeoutError } from '../api/http'
import type { KnowledgePoint, KnowledgePointUpdate, NodeEditApi } from '../api/nodeEdit'
import { useCourseStore, type CourseRequestScope } from '../stores/course'

/**
 * 教师节点编辑面板状态（H07）：读草稿节点 → 表单编辑 → 保存（PATCH）/ 解锁 / 删除。
 *
 * - **不假装成功**：不做乐观更新。表单是本地副本，只有服务端确认后才更新 `original`、写回课程图谱并给出成功提示；
 *   任何失败都保留表单里的修改，并说明「未保存」或「无法确认是否已保存」（网络中断、超时）。
 * - 字段错误：提交前本地校验（名称、定义非空；重要度、难度为 0～1；已有值不能清空）；服务端 422
 *   `VALIDATION_ERROR` 的 `details.fields` 按字段落到对应输入框，认不出的字段落为表单级错误。
 * - 修订冲突：409 `REVISION_CONFLICT` 时不覆盖，把 `details.current` 与本地修改逐字段对比列出；
 *   教师选择「采用最新」（丢弃本地修改）或「保留我的修改」（以 `current_revision` 重新提交仍有差异的字段）。
 *   解锁、删除遇冲突时载入最新内容，请教师确认后再操作。`details` 不完整时标记需重新加载。
 * - 锁：保存成功后节点被服务端锁定（`locked = true`，自动流程不再覆盖）；已锁定节点可显式解锁。
 * - 一次只允许一个写请求；切换知识点或课程时中止在途请求并丢弃晚到结果（序号 + 课程作用域）。
 * - 错误只按错误码给固定文案，不回显服务端 message。组件只拿本组合式的返回值，不接触请求与 store。
 */

type KnowledgePointType = components['schemas']['KnowledgePointType']
type KnowledgePointStatus = components['schemas']['KnowledgePointStatus']
type GraphExchange = components['schemas']['GraphExchange']

export const KP_TYPE_OPTIONS: readonly { value: KnowledgePointType; label: string }[] = [
  { value: 'concept', label: '概念' },
  { value: 'theorem', label: '定理' },
  { value: 'formula', label: '公式' },
  { value: 'method', label: '方法' },
  { value: 'example', label: '例题' },
]

export const KP_STATUS_OPTIONS: readonly { value: KnowledgePointStatus; label: string }[] = [
  { value: 'draft', label: '草稿' },
  { value: 'low_confidence', label: '低置信度' },
  { value: 'approved', label: '已通过' },
  { value: 'rejected', label: '已驳回' },
]

export type EditableField = 'name' | 'aliases' | 'type' | 'definition' | 'importance' | 'difficulty' | 'status'

export const FIELD_LABELS: Readonly<Record<EditableField, string>> = {
  name: '名称',
  aliases: '别名',
  type: '类型',
  definition: '定义',
  importance: '重要度',
  difficulty: '难度',
  status: '审核状态',
}

const FIELDS: readonly EditableField[] = ['name', 'aliases', 'type', 'definition', 'importance', 'difficulty', 'status']

/** 表单值：别名按行/逗号/顿号分隔的文本，数值为输入框原文 */
export interface NodeForm {
  name: string
  aliases: string
  type: KnowledgePointType
  definition: string
  importance: string
  difficulty: string
  status: KnowledgePointStatus
}

export interface ConflictDiff {
  field: EditableField
  label: string
  mine: string
  theirs: string
}

export interface RevisionConflictView {
  currentRevision: number
  /** 本地修改过、且与最新内容不同的字段 */
  diffs: ConflictDiff[]
  /** 冲突由哪个操作触发 */
  action: 'save' | 'unlock' | 'delete'
}

export type NodeEditorStatus = 'idle' | 'loading' | 'ready' | 'not_found' | 'deleted' | 'error'

export interface UseNodeEditorOptions {
  api: NodeEditApi
  /** 当前编辑的知识点；null 表示未选择 */
  kpId: Ref<string | null>
  /** 服务端确认保存或解锁后 */
  onSaved?: (kp: KnowledgePoint) => void
  /** 服务端确认删除后 */
  onDeleted?: (kpId: string) => void
  /** 节点已被删除或数据异常：页面应重新加载图谱 */
  onRefreshNeeded?: () => void
  /** `COURSE_FORBIDDEN`：当前课程已清空，调用方负责回课程列表 */
  onCourseForbidden?: () => void
}

// ---------------------------------------------------------------- 纯函数

/** 别名文本 → 去空白、去空项、去重后的列表（与后端 F08 的规范化一致） */
export function parseAliases(text: string): string[] {
  const out: string[] = []
  for (const part of text.split(/[\n,，、;；]/)) {
    const alias = part.trim()
    if (alias !== '' && !out.includes(alias)) out.push(alias)
  }
  return out
}

function numberText(value: number | undefined): string {
  return value === undefined ? '' : String(value)
}

export function toForm(kp: KnowledgePoint): NodeForm {
  return {
    name: kp.name,
    aliases: (kp.aliases ?? []).join('\n'),
    type: kp.type,
    definition: kp.definition,
    importance: numberText(kp.importance),
    difficulty: numberText(kp.difficulty),
    status: kp.status,
  }
}

type Parsed = { ok: true; value: number | undefined } | { ok: false; message: string }

function parseScore(text: string, previous: number | undefined): Parsed {
  const trimmed = text.trim()
  if (trimmed === '') {
    return previous === undefined ? { ok: true, value: undefined } : { ok: false, message: '已有值不能清空，请填写 0～1 之间的数。' }
  }
  const value = Number(trimmed)
  if (!Number.isFinite(value) || value < 0 || value > 1) return { ok: false, message: '请填写 0～1 之间的数。' }
  return { ok: true, value }
}

function sameList(a: readonly string[], b: readonly string[]): boolean {
  return a.length === b.length && a.every((x, i) => x === b[i])
}

export interface FormDiff {
  /** 与 `original` 不同、可提交的字段 */
  changes: Omit<KnowledgePointUpdate, 'expected_revision'>
  /** 本地校验错误（字段 → 文案） */
  errors: Partial<Record<EditableField, string>>
}

/** 对比表单与服务端版本：只提交改过的字段；名称、定义去首尾空白后比较 */
export function diffForm(original: KnowledgePoint, form: NodeForm): FormDiff {
  const changes: Record<string, unknown> = {}
  const errors: Partial<Record<EditableField, string>> = {}

  const name = form.name.trim()
  if (name === '') errors.name = '名称不能为空。'
  else if (name !== original.name) changes.name = name

  const definition = form.definition.trim()
  if (definition === '') errors.definition = '定义不能为空。'
  else if (definition !== original.definition) changes.definition = definition

  const aliases = parseAliases(form.aliases)
  if (!sameList(aliases, original.aliases ?? [])) changes.aliases = aliases

  if (form.type !== original.type) changes.type = form.type
  if (form.status !== original.status) changes.status = form.status

  for (const key of ['importance', 'difficulty'] as const) {
    const parsed = parseScore(form[key], original[key])
    if (!parsed.ok) errors[key] = parsed.message
    else if (parsed.value !== undefined && parsed.value !== original[key]) changes[key] = parsed.value
  }
  return { changes: changes as FormDiff['changes'], errors }
}

function display(field: EditableField, value: unknown): string {
  if (value === undefined || value === null) return '（空）'
  if (Array.isArray(value)) return value.length ? value.join('、') : '（无）'
  if (field === 'type') return KP_TYPE_OPTIONS.find((o) => o.value === value)?.label ?? String(value)
  if (field === 'status') return KP_STATUS_OPTIONS.find((o) => o.value === value)?.label ?? String(value)
  return String(value)
}

interface ConflictDetails {
  currentRevision: number
  current: Partial<KnowledgePoint> & Pick<KnowledgePoint, 'name' | 'type' | 'definition' | 'status' | 'locked'>
}

/** 读 409 `REVISION_CONFLICT` 的 `details`；形状不完整返回 null */
export function readConflict(details: Record<string, unknown> | undefined): ConflictDetails | null {
  const revision = details?.current_revision
  const current = details?.current
  if (typeof revision !== 'number' || !Number.isInteger(revision) || revision < 1) return null
  if (typeof current !== 'object' || current === null) return null
  const c = current as Record<string, unknown>
  if (typeof c.name !== 'string' || typeof c.definition !== 'string' || typeof c.type !== 'string') return null
  if (typeof c.status !== 'string' || typeof c.locked !== 'boolean') return null
  if (c.aliases !== undefined && !(Array.isArray(c.aliases) && c.aliases.every((a) => typeof a === 'string'))) return null
  for (const key of ['importance', 'difficulty']) {
    if (c[key] !== undefined && typeof c[key] !== 'number') return null
  }
  return { currentRevision: revision, current: c as ConflictDetails['current'] }
}

/** 冲突时把服务端最新内容并入本地已知的节点（`details.current` 不含章节与来源） */
function mergeCurrent(original: KnowledgePoint, conflict: ConflictDetails): KnowledgePoint {
  const { current } = conflict
  const merged: KnowledgePoint = {
    ...original,
    name: current.name,
    aliases: current.aliases ?? [],
    type: current.type,
    definition: current.definition,
    status: current.status,
    locked: current.locked,
    revision: conflict.currentRevision,
  }
  for (const key of ['importance', 'difficulty'] as const) {
    if (current[key] === undefined) delete merged[key]
    else merged[key] = current[key]
  }
  return merged
}

/** 服务端 422 的 `details.fields` → 字段错误；返回认不出的项数 */
function mapServerFields(details: Record<string, unknown> | undefined): {
  errors: Partial<Record<EditableField, string>>
  unknown: number
} {
  const errors: Partial<Record<EditableField, string>> = {}
  let unknown = 0
  const fields = details?.fields
  if (!Array.isArray(fields)) return { errors, unknown: 1 }
  for (const item of fields) {
    const field = typeof item?.field === 'string' ? item.field : ''
    const reason = typeof item?.reason === 'string' ? item.reason : ''
    const head = field.split('.')[0] as EditableField
    if (!FIELDS.includes(head)) {
      unknown += 1
      continue
    }
    if (errors[head] !== undefined) continue
    if (reason === 'blank' || reason === 'missing') errors[head] = `${FIELD_LABELS[head]}不能为空。`
    else if (reason.startsWith('greater_than') || reason.startsWith('less_than')) errors[head] = '请填写 0～1 之间的数。'
    else errors[head] = `${FIELD_LABELS[head]}不符合要求。`
  }
  return { errors, unknown }
}

// ---------------------------------------------------------------- 状态

const LOAD_NETWORK_MESSAGE = '无法连接服务器，请检查网络后重试。'
const NOT_FOUND_MESSAGE = '该知识点不存在或已被删除。'
const INVALID_MESSAGE = '服务端返回的数据异常，无法确认结果，请重新加载节点。'
const STALE_MESSAGE = '节点已被他人修改，且无法取得最新内容，请重新加载节点。'

const ACTION_VERB: Record<'save' | 'unlock' | 'delete', string> = { save: '保存', unlock: '解锁', delete: '删除' }

const ACTION_FAILED: Record<'save' | 'unlock' | 'delete', string> = {
  save: '未保存',
  unlock: '未解锁',
  delete: '未删除',
}

export function useNodeEditor({ api, kpId, onSaved, onDeleted, onRefreshNeeded, onCourseForbidden }: UseNodeEditorOptions) {
  const store = useCourseStore()

  const status = ref<NodeEditorStatus>('idle')
  const original = shallowRef<KnowledgePoint | null>(null)
  const form = reactive<NodeForm>({
    name: '',
    aliases: '',
    type: 'concept',
    definition: '',
    importance: '',
    difficulty: '',
    status: 'draft',
  })
  const loadError = ref<string | null>(null)
  const loadRetryable = ref(false)
  /** 表单级错误（写操作失败） */
  const error = ref<string | null>(null)
  /** 服务端确认后的成功提示 */
  const notice = ref<string | null>(null)
  /** 服务端 422 落到字段上的错误；编辑对应字段后清除 */
  const serverErrors = ref<Partial<Record<EditableField, string>>>({})
  /** 用户尝试提交后才显示本地校验错误 */
  const submitted = ref(false)
  const saving = ref(false)
  const conflict = shallowRef<RevisionConflictView | null>(null)
  /** 需重新加载（冲突细节缺失、结果无法确认） */
  const stale = ref(false)

  let seq = 0
  let controller: AbortController | null = null
  let disposed = false
  /** 冲突时的服务端最新内容：选择「采用最新」或「保留我的修改」时并入 */
  let pendingCurrent: ConflictDetails | null = null

  // ------------------------------------------------------------ 派生
  const diff: ComputedRef<FormDiff | null> = computed(() => (original.value ? diffForm(original.value, form) : null))
  const dirty = computed(() => diff.value !== null && Object.keys(diff.value.changes).length > 0)
  const fieldErrors: ComputedRef<Partial<Record<EditableField, string>>> = computed(() => ({
    ...(submitted.value ? diff.value?.errors : {}),
    ...serverErrors.value,
  }))
  const locked = computed(() => original.value?.locked === true)
  /** 保存冲突未处理前不能再次保存（须先选择采用最新或保留我的修改） */
  const saveBlocked = computed(() => conflict.value?.action === 'save')
  const canSave = computed(() => status.value === 'ready' && !saving.value && dirty.value && !saveBlocked.value)

  // 编辑某字段后清掉该字段的服务端错误
  for (const key of FIELDS) {
    watch(
      () => form[key],
      () => {
        if (serverErrors.value[key] === undefined) return
        const next = { ...serverErrors.value }
        delete next[key]
        serverErrors.value = next
      },
    )
  }

  // ------------------------------------------------------------ 基础
  function cancel(): void {
    seq += 1
    controller?.abort()
    controller = null
    saving.value = false
  }

  function clearMessages(): void {
    error.value = null
    notice.value = null
    serverErrors.value = {}
    conflict.value = null
    pendingCurrent = null
  }

  function adopt(kp: KnowledgePoint, resetForm: boolean): void {
    original.value = kp
    if (resetForm) Object.assign(form, toForm(kp))
  }

  /**
   * 换到新的服务端基准（冲突时的最新内容），只保留教师改过的字段：
   * 没改过的字段跟随最新内容，避免「保留我的修改」时把他人的修改改回去。
   */
  function rebase(kp: KnowledgePoint): void {
    const changed = new Set(Object.keys(diff.value?.changes ?? {}))
    const next = toForm(kp)
    original.value = kp
    for (const key of FIELDS) {
      if (!changed.has(key)) (form as Record<EditableField, string>)[key] = next[key]
    }
  }

  function reset(next: NodeEditorStatus): void {
    status.value = next
    original.value = null
    loadError.value = null
    loadRetryable.value = false
    submitted.value = false
    stale.value = false
    clearMessages()
  }

  /** 开启一次请求：课程作用域 + 自有中止器；返回 null 表示不能发请求 */
  function begin(): { scope: CourseRequestScope; own: AbortController; token: number; done: () => void } | null {
    if (disposed || store.courseId === null) return null
    cancel()
    const token = seq
    const scope = store.beginRequest()
    const own = new AbortController()
    controller = own
    const onScopeAbort = () => own.abort(scope.signal.reason)
    if (scope.signal.aborted) own.abort(scope.signal.reason)
    else scope.signal.addEventListener('abort', onScopeAbort, { once: true })
    return {
      scope,
      own,
      token,
      done: () => {
        scope.signal.removeEventListener('abort', onScopeAbort)
        if (controller === own) controller = null
      },
    }
  }

  function isCurrent(token: number, scope: CourseRequestScope): boolean {
    return !disposed && token === seq && scope.isCurrent()
  }

  // ------------------------------------------------------------ 加载
  async function load(kid: string | null): Promise<void> {
    cancel()
    if (disposed || kid === null || store.courseId === null) {
      reset('idle')
      return
    }
    const req = begin()
    if (req === null) return
    const { scope, own, token, done } = req
    reset('loading')
    try {
      const result = await api.get(scope.courseId, kid, { signal: own.signal })
      if (!isCurrent(token, scope)) return
      if (result?.id !== kid || result.course_id !== scope.courseId) {
        status.value = 'error'
        loadError.value = '知识点数据异常，请稍后重试。'
        loadRetryable.value = true
        return
      }
      store.commit(scope, () => {
        adopt(result, true)
        status.value = 'ready'
      })
    } catch (cause) {
      if (!isCurrent(token, scope) || cause instanceof AbortedError) return
      status.value = 'error'
      loadRetryable.value = false
      if (cause instanceof ApiError) {
        if (cause.code === 'COURSE_FORBIDDEN') return forbidden()
        if (cause.code === 'NOT_FOUND') {
          status.value = 'not_found'
          loadError.value = NOT_FOUND_MESSAGE
          return
        }
        if (cause.status === 401) {
          loadError.value = '登录已失效，请重新登录。'
          return
        }
        loadError.value = '知识点加载失败，请稍后重试。'
        loadRetryable.value = cause.status >= 500
        return
      }
      loadRetryable.value = true
      loadError.value =
        cause instanceof NetworkError || cause instanceof TimeoutError ? LOAD_NETWORK_MESSAGE : '知识点数据异常，请稍后重试。'
    } finally {
      done()
    }
  }

  function forbidden(): void {
    status.value = 'error'
    loadError.value = '无权访问该课程。'
    store.selectCourse(null)
    onCourseForbidden?.()
  }

  // ------------------------------------------------------------ 写回课程图谱
  function syncGraph(scope: CourseRequestScope, update: (graph: GraphExchange) => GraphExchange): void {
    const graph = store.graph
    if (graph === null || graph.course_id !== scope.courseId) return
    store.setGraph(scope, update(graph))
  }

  function replaceNode(scope: CourseRequestScope, kp: KnowledgePoint): void {
    syncGraph(scope, (g) =>
      g.nodes.some((n) => n.id === kp.id)
        ? { ...g, nodes: g.nodes.map((n) => (n.id === kp.id ? { ...n, ...kp } : n)) }
        : g,
    )
  }

  function removeNode(scope: CourseRequestScope, kid: string): void {
    syncGraph(scope, (g) => ({
      ...g,
      nodes: g.nodes.filter((n) => n.id !== kid),
      edges: g.edges.filter((e) => e.from_id !== kid && e.to_id !== kid),
    }))
  }

  // ------------------------------------------------------------ 写操作错误
  function writeError(cause: unknown, action: 'save' | 'unlock' | 'delete'): void {
    const failed = ACTION_FAILED[action]
    if (cause instanceof ApiError) {
      switch (cause.code) {
        case 'REVISION_CONFLICT': {
          const details = readConflict(cause.details)
          if (details === null || original.value === null) {
            stale.value = true
            error.value = `${STALE_MESSAGE}（${failed}）`
            return
          }
          if (action === 'save') {
            pendingCurrent = details
            const diffs: ConflictDiff[] = []
            const mine = diff.value?.changes ?? {}
            const theirs = mergeCurrent(original.value, details)
            for (const field of FIELDS) {
              if (!(field in mine)) continue
              const a = (mine as Record<string, unknown>)[field]
              const b = field === 'aliases' ? theirs.aliases ?? [] : theirs[field]
              if (display(field, a) === display(field, b)) continue
              diffs.push({ field, label: FIELD_LABELS[field], mine: display(field, a), theirs: display(field, b) })
            }
            conflict.value = { currentRevision: details.currentRevision, diffs, action }
            error.value = '保存前该知识点已被他人修改，你的修改未保存。请对比后选择采用最新内容或保留你的修改。'
            return
          }
          // 解锁、删除：载入最新内容（保留表单中尚未保存的修改），请教师确认后再操作
          rebase(mergeCurrent(original.value, details))
          conflict.value = { currentRevision: details.currentRevision, diffs: [], action }
          error.value = `该知识点已被他人修改，${failed}。已载入最新内容，请确认后再${ACTION_VERB[action]}。`
          return
        }
        case 'VALIDATION_ERROR': {
          const { errors, unknown } = mapServerFields(cause.details)
          serverErrors.value = errors
          error.value =
            unknown > 0 || Object.keys(errors).length === 0
              ? `提交内容不符合要求，${failed}。`
              : `请修正标出的字段，${failed}。`
          return
        }
        case 'NOT_FOUND':
          status.value = action === 'delete' ? 'deleted' : 'not_found'
          error.value = action === 'delete' ? '该知识点已不存在（可能已被他人删除）。' : `${NOT_FOUND_MESSAGE}${failed}。`
          onRefreshNeeded?.()
          return
        case 'COURSE_BUSY':
          error.value = `课程正在进行其他写入或发布，${failed}，请稍后重试。`
          return
        case 'ROLE_FORBIDDEN':
          error.value = `无权编辑：只有本课程的教师可以修改图谱，${failed}。`
          return
        case 'UNAUTHENTICATED':
          error.value = `登录已失效，${failed}，请重新登录。`
          return
      }
      error.value = `操作失败，${failed}，请稍后重试。`
      return
    }
    if (cause instanceof NetworkError || cause instanceof TimeoutError) {
      stale.value = true
      error.value = `无法连接服务器，不能确认是否已${ACTION_VERB[action]}。请重新加载节点核对后再操作。`
      return
    }
    stale.value = true
    error.value = INVALID_MESSAGE
  }

  /** 公共写流程：只在服务端确认后调用 `apply` */
  async function write<T>(
    action: 'save' | 'unlock' | 'delete',
    send: (scope: CourseRequestScope, kid: string, revision: number, signal: AbortSignal) => Promise<T>,
    apply: (scope: CourseRequestScope, kid: string, result: T) => boolean,
  ): Promise<boolean> {
    const kid = kpId.value
    const base = original.value
    if (saving.value || status.value !== 'ready' || kid === null || base === null) return false
    const req = begin()
    if (req === null) return false
    const { scope, own, token, done } = req
    clearMessages()
    saving.value = true
    try {
      const result = await send(scope, kid, base.revision, own.signal)
      if (!isCurrent(token, scope)) return false
      let ok = false
      store.commit(scope, () => {
        ok = apply(scope, kid, result)
      })
      return ok
    } catch (cause) {
      if (!isCurrent(token, scope) || cause instanceof AbortedError) return false
      if (cause instanceof ApiError && cause.code === 'COURSE_FORBIDDEN') {
        forbidden()
        return false
      }
      writeError(cause, action)
      return false
    } finally {
      if (token === seq) saving.value = false
      done()
    }
  }

  /** 校验服务端返回的节点；不符时不采用、不提示成功 */
  function confirmed(scope: CourseRequestScope, kid: string, kp: KnowledgePoint | undefined): kp is KnowledgePoint {
    if (kp?.id === kid && kp.course_id === scope.courseId && typeof kp.revision === 'number') return true
    stale.value = true
    error.value = INVALID_MESSAGE
    return false
  }

  async function save(): Promise<boolean> {
    submitted.value = true
    const current = diff.value
    if (current === null || status.value !== 'ready') return false
    if (Object.keys(current.errors).length > 0) {
      error.value = '请修正标出的字段，未保存。'
      notice.value = null
      return false
    }
    if (saveBlocked.value) return false
    if (Object.keys(current.changes).length === 0) {
      error.value = null
      notice.value = '没有需要保存的修改。'
      return false
    }
    const changes = current.changes
    return write(
      'save',
      (scope, kid, revision, signal) =>
        api.update(scope.courseId, kid, { ...changes, expected_revision: revision } as KnowledgePointUpdate, { signal }),
      (scope, kid, kp) => {
        if (!confirmed(scope, kid, kp)) return false
        adopt(kp, true)
        submitted.value = false
        replaceNode(scope, kp)
        notice.value = kp.locked ? '已保存。该知识点已锁定，后续自动抽取不会覆盖。' : '已保存。'
        onSaved?.(kp)
        return true
      },
    )
  }

  async function unlock(): Promise<boolean> {
    if (!locked.value) return false
    return write(
      'unlock',
      (scope, kid, revision, signal) => api.unlock(scope.courseId, kid, revision, { signal }),
      (scope, kid, kp) => {
        if (!confirmed(scope, kid, kp)) return false
        // 解锁不改内容：保留表单里尚未保存的修改
        rebase(kp)
        replaceNode(scope, kp)
        notice.value = kp.locked ? null : '已解锁。后续自动抽取可以更新该知识点。'
        if (kp.locked) error.value = '服务端仍显示该知识点已锁定，请重新加载核对。'
        onSaved?.(kp)
        return !kp.locked
      },
    )
  }

  async function remove(): Promise<boolean> {
    return write(
      'delete',
      async (scope, kid, revision, signal) => {
        await api.remove(scope.courseId, kid, revision, { signal })
      },
      (scope, kid) => {
        status.value = 'deleted'
        original.value = null
        removeNode(scope, kid)
        notice.value = '已删除该知识点及其相连关系。'
        onDeleted?.(kid)
        return true
      },
    )
  }

  // ------------------------------------------------------------ 冲突处理
  /** 采用服务端最新内容，丢弃本地修改 */
  function acceptTheirs(): void {
    const base = original.value
    if (pendingCurrent === null || base === null) return
    adopt(mergeCurrent(base, pendingCurrent), true)
    clearMessages()
    submitted.value = false
    notice.value = '已载入最新内容，你的修改已丢弃。'
  }

  /** 以最新修订号为基准，重新提交仍与最新内容不同的本地修改 */
  async function keepMine(): Promise<boolean> {
    const base = original.value
    if (pendingCurrent === null || base === null) return false
    rebase(mergeCurrent(base, pendingCurrent))
    clearMessages()
    if (!dirty.value) {
      notice.value = '最新内容已与你的修改一致，无需再保存。'
      return true
    }
    return save()
  }

  /** 关闭解锁/删除冲突提示（最新内容已载入） */
  function dismissConflict(): void {
    if (conflict.value?.action === 'save') return
    conflict.value = null
  }

  /** 放弃本地修改，回到最近一次确认的服务端内容 */
  function discard(): void {
    if (original.value === null) return
    Object.assign(form, toForm(original.value))
    clearMessages()
    submitted.value = false
  }

  function reload(): void {
    void load(kpId.value)
  }

  // ------------------------------------------------------------ 切换
  watch(
    [kpId, () => store.courseId] as const,
    ([kid, cid], [prevKid, prevCid]) => {
      if (cid !== prevCid && kid === prevKid) {
        cancel()
        reset('idle')
        return
      }
      void load(kid)
    },
  )
  void load(kpId.value)

  onScopeDispose(() => {
    disposed = true
    cancel()
  })

  return {
    status: status as Readonly<Ref<NodeEditorStatus>>,
    original: original as Readonly<Ref<KnowledgePoint | null>>,
    form,
    dirty,
    locked,
    canSave,
    fieldErrors,
    loadError: loadError as Readonly<Ref<string | null>>,
    loadRetryable: loadRetryable as Readonly<Ref<boolean>>,
    error: error as Readonly<Ref<string | null>>,
    notice: notice as Readonly<Ref<string | null>>,
    saving: saving as Readonly<Ref<boolean>>,
    conflict: conflict as Readonly<Ref<RevisionConflictView | null>>,
    stale: stale as Readonly<Ref<boolean>>,
    save,
    unlock,
    remove,
    acceptTheirs,
    keepMine,
    dismissConflict,
    discard,
    reload,
  }
}

export type NodeEditor = ReturnType<typeof useNodeEditor>
