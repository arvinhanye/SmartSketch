import { onScopeDispose, ref, shallowRef, watch, type Ref } from 'vue'
import { AbortedError, ApiError, NetworkError, TimeoutError } from '../api/http'
import type { KnowledgeDetailApi, KnowledgePointDetail, KnowledgePointRef, SourceRef } from '../api/knowledgeDetail'
import { useCourseStore } from '../stores/course'

/**
 * 知识点详情与来源浏览状态（H06，ADR-051）。
 *
 * - 输入是画布回传的知识点 ID（H04 `nodeClick`）；输出是只含展示所需字段的视图模型，
 *   组件不接触后端原始 `KnowledgePointDetail`。
 * - 来源只展示能定位的：`document_id`、`chunk_id` 非空，且页码为正整数或章节路径非空（契约 `SourceRef`
 *   的 anyOf，ADR-003）。不满足的丢弃并计数，不补页码、不补章节、不补原文。
 * - 迟到请求隔离：每次选择递增序号并中止上一次请求；响应只在序号、课程作用域都仍有效时写入，
 *   所以快速切换、A→B→A、切课、卸载后的旧响应都被丢弃。响应的 `id`/`course_id` 与请求不符也不展示。
 * - 错误只按状态码/错误码给固定文案，不回显服务端 message；`COURSE_FORBIDDEN` 交给调用方处理。
 * - 所有文本由组件以文本插值渲染（不用 `v-html`），高亮只切分字符串，不拼 HTML。
 */

type KnowledgePointType = KnowledgePointDetail['type']

const TYPE_LABEL: Record<KnowledgePointType, string> = {
  concept: '概念',
  theorem: '定理',
  formula: '公式',
  method: '方法',
  example: '示例',
}

export interface SourceLocation {
  documentId: string
  chunkId: string
  /** 页码（从 1 起）；来源无分页时不带 */
  page?: number
  /** 章节路径；来源无章节信息时不带 */
  sectionPath?: string
}

export interface SourceView extends SourceLocation {
  /** 列表内唯一键 */
  key: string
  /** 如「第 3 页 · 第3章 > 3.1 栈」；只由真实字段拼成 */
  locationLabel: string
  /** 原文片段；已发布版本或无证据区间时没有 */
  excerpt?: string
}

export interface RelatedView {
  id: string
  name: string
}

export interface KnowledgeDetailView {
  id: string
  name: string
  typeLabel: string
  definition: string
  aliases: string[]
  level: number
  prerequisites: RelatedView[]
  successors: RelatedView[]
  related: RelatedView[]
  sources: SourceView[]
  /** 因无法定位而未展示的来源条数 */
  droppedSources: number
  /** 原文片段中需高亮的词：名称与别名 */
  highlightTerms: string[]
}

function nonEmpty(value: unknown): value is string {
  return typeof value === 'string' && value.trim() !== ''
}

function validPage(value: unknown): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value >= 1
}

/** 把一条来源转成视图；无法定位或身份不完整时返回 null（不伪造位置） */
export function toSourceView(source: SourceRef, index = 0): SourceView | null {
  if (typeof source !== 'object' || source === null) return null
  const raw = source as unknown as Record<string, unknown>
  if (!nonEmpty(raw.document_id) || !nonEmpty(raw.chunk_id)) return null
  const page = validPage(raw.page) ? raw.page : undefined
  const sectionPath = nonEmpty(raw.section_path) ? raw.section_path : undefined
  if (page === undefined && sectionPath === undefined) return null

  const parts: string[] = []
  if (page !== undefined) parts.push(`第 ${page} 页`)
  if (sectionPath !== undefined) parts.push(sectionPath)
  const view: SourceView = {
    key: `${index}:${raw.chunk_id}`,
    documentId: raw.document_id,
    chunkId: raw.chunk_id,
    locationLabel: parts.join(' · '),
  }
  if (page !== undefined) view.page = page
  if (sectionPath !== undefined) view.sectionPath = sectionPath
  if (nonEmpty(raw.text)) view.excerpt = raw.text
  return view
}

function toRelated(items: KnowledgePointRef[] | undefined): RelatedView[] {
  if (!Array.isArray(items)) return []
  return items.filter((item) => nonEmpty(item?.id) && nonEmpty(item?.name)).map((item) => ({ id: item.id, name: item.name }))
}

/** 纯函数：不修改输入，输出不引用输入的数组 */
export function toKnowledgeDetailView(detail: KnowledgePointDetail): KnowledgeDetailView {
  const rawSources = Array.isArray(detail.source_refs) ? detail.source_refs : []
  const sources: SourceView[] = []
  rawSources.forEach((source, index) => {
    const view = toSourceView(source, index)
    if (view !== null) sources.push(view)
  })
  const aliases = (Array.isArray(detail.aliases) ? detail.aliases : []).filter(
    (alias) => nonEmpty(alias) && alias !== detail.name,
  )
  return {
    id: detail.id,
    name: detail.name,
    typeLabel: TYPE_LABEL[detail.type] ?? '知识点',
    definition: detail.definition,
    aliases,
    level: detail.level,
    prerequisites: toRelated(detail.prerequisites),
    successors: toRelated(detail.successors),
    related: toRelated(detail.related),
    sources,
    droppedSources: rawSources.length - sources.length,
    highlightTerms: [detail.name, ...aliases].filter(nonEmpty),
  }
}

export interface TextSegment {
  text: string
  mark: boolean
}

/**
 * 按字面量切分文本以高亮词语：同一位置取最长的词，不解释正则或 HTML。
 * 返回的片段由组件逐段以文本渲染。
 */
export function highlightSegments(text: string, terms: readonly string[]): TextSegment[] {
  const words = [...new Set(terms.filter(nonEmpty))].sort((a, b) => b.length - a.length)
  const segments: TextSegment[] = []
  let plain = ''
  let i = 0
  while (i < text.length) {
    const hit = words.find((word) => text.startsWith(word, i))
    if (hit === undefined) {
      plain += text[i]
      i += 1
      continue
    }
    if (plain) segments.push({ text: plain, mark: false })
    plain = ''
    segments.push({ text: hit, mark: true })
    i += hit.length
  }
  if (plain || segments.length === 0) segments.push({ text: plain, mark: false })
  return segments
}

// ---------------------------------------------------------------- 状态

export type KnowledgeDetailStatus = 'idle' | 'loading' | 'ready' | 'not_found' | 'error'

const NETWORK_MESSAGE = '无法连接服务器，请检查网络后重试。'
const NOT_FOUND_MESSAGE = '该知识点不存在或已被删除。'
const NOT_PUBLISHED_MESSAGE = '课程图谱尚未发布，暂无法查看知识点详情。'
const SESSION_EXPIRED_MESSAGE = '登录已失效，请重新登录。'
const FORBIDDEN_MESSAGE = '无权访问该课程。'
const INVALID_MESSAGE = '知识点详情数据异常，请稍后重试。'
const GENERIC_MESSAGE = '知识点详情加载失败，请稍后重试。'

export interface UseKnowledgeDetailOptions {
  api: KnowledgeDetailApi
  /** 当前选中的知识点 ID（画布 `nodeClick`）；null 表示未选择 */
  kpId: Ref<string | null>
  /** 返回 `COURSE_FORBIDDEN`：调用方负责回课程列表 */
  onCourseForbidden?: () => void
}

export function useKnowledgeDetail({ api, kpId, onCourseForbidden }: UseKnowledgeDetailOptions) {
  const store = useCourseStore()
  const status = ref<KnowledgeDetailStatus>('idle')
  const detail = shallowRef<KnowledgeDetailView | null>(null)
  const error = ref<string | null>(null)
  /** 是否可重试（网络、超时、服务端临时故障） */
  const retryable = ref(false)
  const activeSourceKey = ref<string | null>(null)

  let seq = 0
  let controller: AbortController | null = null
  let disposed = false

  function cancel(): void {
    seq += 1
    controller?.abort()
    controller = null
  }

  function reset(next: KnowledgeDetailStatus): void {
    status.value = next
    detail.value = null
    error.value = null
    retryable.value = false
    activeSourceKey.value = null
  }

  function fail(next: 'not_found' | 'error', message: string, canRetry: boolean): void {
    status.value = next
    detail.value = null
    error.value = message
    retryable.value = canRetry
  }

  async function load(kid: string | null): Promise<void> {
    cancel()
    const token = seq
    if (disposed || kid === null || store.courseId === null) {
      reset('idle')
      return
    }
    const scope = store.beginRequest()
    const own = new AbortController()
    controller = own
    const onScopeAbort = () => own.abort(scope.signal.reason)
    if (scope.signal.aborted) own.abort(scope.signal.reason)
    else scope.signal.addEventListener('abort', onScopeAbort, { once: true })
    const current = () => !disposed && token === seq && scope.isCurrent()

    reset('loading')
    try {
      const result = await api.get(scope.courseId, kid, { signal: own.signal })
      if (!current()) return
      // 课程隔离：不展示与请求不符的课程或知识点
      if (result?.id !== kid || result.course_id !== scope.courseId) {
        fail('error', INVALID_MESSAGE, true)
        return
      }
      store.commit(scope, () => {
        detail.value = toKnowledgeDetailView(result)
        status.value = 'ready'
      })
    } catch (cause) {
      if (!current() || cause instanceof AbortedError) return
      if (cause instanceof ApiError) {
        if (cause.code === 'COURSE_FORBIDDEN') {
          fail('error', FORBIDDEN_MESSAGE, false)
          onCourseForbidden?.()
          return
        }
        if (cause.code === 'NOT_FOUND') return fail('not_found', NOT_FOUND_MESSAGE, false)
        if (cause.code === 'GRAPH_NOT_PUBLISHED') return fail('not_found', NOT_PUBLISHED_MESSAGE, false)
        if (cause.status === 401) return fail('error', SESSION_EXPIRED_MESSAGE, false)
        return fail('error', GENERIC_MESSAGE, cause.status >= 500)
      }
      if (cause instanceof NetworkError || cause instanceof TimeoutError) return fail('error', NETWORK_MESSAGE, true)
      fail('error', INVALID_MESSAGE, true)
    } finally {
      scope.signal.removeEventListener('abort', onScopeAbort)
      if (controller === own) controller = null
    }
  }

  // 课程变了而选择没变：旧选择属于旧课程，回到空态，等页面给出新选择
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

  function retry(): void {
    void load(kpId.value)
  }

  /** 定位到某条来源：记为当前来源并返回位置，由页面跳到原文 */
  function locate(source: SourceView): SourceLocation {
    activeSourceKey.value = source.key
    const location: SourceLocation = { documentId: source.documentId, chunkId: source.chunkId }
    if (source.page !== undefined) location.page = source.page
    if (source.sectionPath !== undefined) location.sectionPath = source.sectionPath
    return location
  }

  onScopeDispose(() => {
    disposed = true
    cancel()
  })

  return { status, detail, error, retryable, activeSourceKey, retry, locate }
}
