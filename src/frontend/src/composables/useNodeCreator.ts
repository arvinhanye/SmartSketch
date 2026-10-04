import { onScopeDispose, reactive, ref, type Ref } from 'vue'
import type { components } from '../../../contracts/v1/generated/typescript/openapi'
import { AbortedError, ApiError, NetworkError, TimeoutError } from '../api/http'
import type { KnowledgeDetailApi, SourceRef } from '../api/knowledgeDetail'
import { toSourceView, type SourceView } from './useKnowledgeDetail'
import type { KnowledgePoint, KnowledgePointCreate, NodeEditApi } from '../api/nodeEdit'
import { useCourseStore } from '../stores/course'

type GraphExchange = components['schemas']['GraphExchange']
type KnowledgePointType = components['schemas']['KnowledgePointType']

/**
 * 教师新建知识点（L11，ADR-035：新建必带来源）。没有列出课程文本块的接口，所以来源取自当前选中知识点的
 * 来源——教师在图上或下拉框选中一个相关知识点，以它引用的文本块作为新知识点的依据。
 * 结果按课程作用域提交：切课后晚到的响应被丢弃；错误只给固定文案，不回显服务端 message。
 */

export interface PickerOption {
  value: string
  label: string
}

/** 教师图谱页的节点下拉框：画布之外的可访问选择方式（键盘与自动化） */
export function nodePickerOptions(graph: Pick<GraphExchange, 'nodes'> | null): PickerOption[] {
  if (graph === null) return []
  return graph.nodes
    .filter((node) => typeof node.name === 'string' && node.name.trim() !== '')
    .map((node) => ({ value: node.id, label: node.name }))
    .sort((a, b) => a.label.localeCompare(b.label, 'zh-Hans-CN'))
}

export interface CreatorSource {
  chunkId: string
  label: string
  excerpt: string
}

export const KNOWLEDGE_POINT_TYPES: Array<{ value: KnowledgePointType; label: string }> = [
  { value: 'concept', label: '概念' },
  { value: 'theorem', label: '定理' },
  { value: 'formula', label: '公式' },
  { value: 'method', label: '方法' },
  { value: 'example', label: '示例' },
]

function failureText(cause: unknown): string {
  if (cause instanceof ApiError) {
    if (cause.code === 'VALIDATION_ERROR') {
      const fields = Array.isArray(cause.details?.fields) ? (cause.details!.fields as Array<{ field?: unknown }>) : []
      if (fields.some((f) => typeof f.field === 'string' && f.field.startsWith('sources'))) {
        return '所选来源无效（文本块不属于本课程或所在资料尚未处理完成），请换一个知识点的来源。'
      }
      return '请检查填写的内容。'
    }
    if (cause.code === 'COURSE_BUSY') return '课程正在写入，请稍后重试。'
    if (cause.code === 'COURSE_FORBIDDEN' || cause.code === 'ROLE_FORBIDDEN') return '只有本课程的教师可以新建知识点。'
    if (cause.status === 401) return '登录已失效，请重新登录。'
    return '新建失败，请稍后重试。'
  }
  if (cause instanceof NetworkError || cause instanceof TimeoutError) return '无法连接服务器，请检查网络后重试。'
  return '新建失败，请稍后重试。'
}

export interface UseNodeCreatorOptions {
  api: Pick<NodeEditApi, 'create'>
  detailApi: KnowledgeDetailApi
  /** 提供来源的知识点（页面当前选中项） */
  sourceKpId: Ref<string | null>
  onCreated?: (kp: KnowledgePoint) => void
}

export function useNodeCreator({ api, detailApi, sourceKpId, onCreated }: UseNodeCreatorOptions) {
  const store = useCourseStore()
  const form = reactive<{ name: string; type: KnowledgePointType; definition: string }>({ name: '', type: 'concept', definition: '' })
  const sources = ref<CreatorSource[]>([])
  const chosen = ref<Set<string>>(new Set())
  const hint = ref<string | null>(null)
  const error = ref<string | null>(null)
  const success = ref<string | null>(null)
  const busy = ref(false)
  let disposed = false
  onScopeDispose(() => { disposed = true })

  async function open(): Promise<void> {
    error.value = success.value = hint.value = null
    sources.value = []
    chosen.value = new Set()
    const kid = sourceKpId.value
    if (kid === null || store.courseId === null) {
      hint.value = '先在图谱或下拉框中选中一个知识点，新知识点将以它的来源作为依据。'
      return
    }
    const scope = store.beginRequest()
    try {
      const detail = await detailApi.get(scope.courseId, kid, { signal: scope.signal })
      if (disposed || !scope.isCurrent() || sourceKpId.value !== kid) return
      // 复用详情的校验：只取能定位（有页码或章节）的来源
      const refs: SourceRef[] = Array.isArray(detail.source_refs) ? detail.source_refs : []
      const views = refs.map((item, index) => toSourceView(item, index)).filter((v): v is SourceView => v !== null)
      sources.value = views.map((view) => ({ chunkId: view.chunkId, label: view.locationLabel, excerpt: view.excerpt ?? '' }))
      chosen.value = new Set(sources.value.map((s) => s.chunkId))
      if (sources.value.length === 0) hint.value = '选中的知识点没有可用的来源，请换一个知识点。'
    } catch (cause) {
      if (cause instanceof AbortedError || disposed || !scope.isCurrent()) return
      error.value = '读取来源失败，请稍后重试。'
    }
  }

  function toggleSource(chunkId: string): void {
    const next = new Set(chosen.value)
    if (next.has(chunkId)) next.delete(chunkId)
    else next.add(chunkId)
    chosen.value = next
  }

  async function submit(): Promise<void> {
    if (busy.value) return
    error.value = success.value = null
    if (store.courseId === null || sources.value.length === 0) {
      hint.value ??= '先在图谱或下拉框中选中一个知识点，新知识点将以它的来源作为依据。'
      return
    }
    const name = form.name.trim()
    const definition = form.definition.trim()
    if (name === '' || definition === '') {
      error.value = '请填写名称和定义。'
      return
    }
    const picked = sources.value.filter((s) => chosen.value.has(s.chunkId))
    if (picked.length === 0) {
      error.value = '至少选择一条来源。'
      return
    }
    const body: KnowledgePointCreate = { name, type: form.type, definition, sources: picked.map((s) => ({ chunk_id: s.chunkId })) }
    const scope = store.beginRequest()
    busy.value = true
    try {
      const kp = await api.create(scope.courseId, body, { signal: scope.signal })
      if (disposed || !scope.isCurrent()) return
      success.value = `已新建知识点：${kp.name}`
      form.name = ''
      form.definition = ''
      onCreated?.(kp)
    } catch (cause) {
      if (cause instanceof AbortedError || disposed || !scope.isCurrent()) return
      error.value = failureText(cause)
    } finally {
      busy.value = false
    }
  }

  return { form, sources, chosen, hint, error, success, busy, open, toggleSource, submit }
}
