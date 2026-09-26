import { computed, ref, shallowRef, toValue, watch, type ComputedRef, type MaybeRefOrGetter, type Ref } from 'vue'
import type { components } from '../../../contracts/v1/generated/typescript/openapi'
import type { KnowledgePoint, RelationType } from '../graph/adapter'
import type {
  CanvasEdge,
  CanvasElementState,
  CanvasNode,
  GraphCanvasData,
  GraphLayoutName,
} from '../graph/lifecycle'

/**
 * 图谱搜索、筛选、布局与选中（H05）。
 *
 * 作用于适配图（H03 `toG6Data` 的节点与边），不接触后端原始响应。
 * - 知识点可见 ⇔ 类型、审核状态、章节均在所选范围内，且名称包含搜索词；
 * - 关系可见 ⇔ 关系类型、审核状态在所选范围内，且两个端点都可见（因此没有悬空边）；
 * - 输出按输入顺序，并给元素打上 `rejected` / `lowConfidence` / `selected` 状态供画布区分样式；
 * - 选中与布局独立于筛选条件：清空筛选、切换布局都不改选中；筛选隐藏选中节点时保留选中并报告。
 */

export type KnowledgePointType = KnowledgePoint['type']
export type ReviewStatus = KnowledgePoint['status']
export type Chapter = components['schemas']['Chapter']

export type ChapterFilter = { kind: 'all' } | { kind: 'none' } | { kind: 'chapter'; id: string }

export interface GraphFilterState {
  /** 按知识点名称包含匹配；忽略大小写、全半角与首尾空白，空白串等于不搜索 */
  query: string
  relationTypes: RelationType[]
  nodeTypes: KnowledgePointType[]
  /** 节点与关系共用的审核状态 */
  statuses: ReviewStatus[]
  chapter: ChapterFilter
}

export interface ChapterOption {
  value: ChapterFilter
  label: string
}

export interface GraphSummary {
  nodes: number
  totalNodes: number
  edges: number
  totalEdges: number
}

export const RELATION_TYPE_ORDER: readonly RelationType[] = Object.freeze([
  'CONTAINS',
  'PREREQUISITE',
  'RELATED_TO',
  'EXAMPLE_OF',
])

/** 知识点类型与中文名（S2 表 6.3 五类） */
export const NODE_TYPE_LABELS: Readonly<Record<KnowledgePointType, string>> = Object.freeze({
  concept: '概念',
  theorem: '定理',
  formula: '公式',
  method: '方法',
  example: '例题',
})

export const STATUS_LABELS: Readonly<Record<ReviewStatus, string>> = Object.freeze({
  draft: '待审核',
  low_confidence: '低置信度',
  approved: '已通过',
  rejected: '已驳回',
})

const NODE_TYPE_ORDER = Object.keys(NODE_TYPE_LABELS) as KnowledgePointType[]
const STATUS_ORDER = Object.keys(STATUS_LABELS) as ReviewStatus[]

export function defaultFilterState(): GraphFilterState {
  return {
    query: '',
    relationTypes: [...RELATION_TYPE_ORDER],
    nodeTypes: [...NODE_TYPE_ORDER],
    statuses: [...STATUS_ORDER],
    chapter: { kind: 'all' },
  }
}

function cloneState(state: GraphFilterState): GraphFilterState {
  return {
    query: state.query,
    relationTypes: [...state.relationTypes],
    nodeTypes: [...state.nodeTypes],
    statuses: [...state.statuses],
    chapter: { ...state.chapter },
  }
}

function sameSet<T>(a: readonly T[], b: readonly T[]): boolean {
  const left = new Set(a)
  const right = new Set(b)
  return left.size === right.size && [...left].every((item) => right.has(item))
}

function sameChapter(a: ChapterFilter, b: ChapterFilter): boolean {
  if (a.kind !== b.kind) return false
  return a.kind !== 'chapter' || a.id === (b as { id: string }).id
}

export function sameFilterState(a: GraphFilterState, b: GraphFilterState): boolean {
  return (
    normalize(a.query) === normalize(b.query) &&
    sameSet(a.relationTypes, b.relationTypes) &&
    sameSet(a.nodeTypes, b.nodeTypes) &&
    sameSet(a.statuses, b.statuses) &&
    sameChapter(a.chapter, b.chapter)
  )
}

function normalize(text: string): string {
  return text.normalize('NFKC').toLowerCase().trim()
}

function reviewState(status: ReviewStatus): CanvasElementState[] {
  if (status === 'rejected') return ['rejected']
  if (status === 'low_confidence') return ['lowConfidence']
  return []
}

function chapterMatches(filter: ChapterFilter, chapterId: string | null): boolean {
  if (filter.kind === 'all') return true
  if (filter.kind === 'none') return chapterId === null
  return chapterId === filter.id
}

/** 纯函数：不修改输入；输出的节点与边是新对象（`data`/`style` 与输入共享，画布生命周期会再复制） */
export function filterGraph(
  graph: GraphCanvasData,
  state: GraphFilterState,
  selectedKpId: string | null,
): GraphCanvasData {
  const query = normalize(state.query)
  const nodeTypes = new Set(state.nodeTypes)
  const statuses = new Set(state.statuses)
  const relationTypes = new Set(state.relationTypes)

  const nodes: CanvasNode[] = []
  for (const node of graph.nodes) {
    const d = node.data
    if (!nodeTypes.has(d.type) || !statuses.has(d.status) || !chapterMatches(state.chapter, d.chapterId)) continue
    if (query !== '' && !normalize(d.name).includes(query)) continue
    const states = reviewState(d.status)
    if (selectedKpId !== null && d.kpId === selectedKpId) states.push('selected')
    nodes.push({ id: node.id, data: node.data, states })
  }

  const present = new Set(nodes.map((node) => node.id))
  const edges: CanvasEdge[] = []
  for (const edge of graph.edges) {
    if (!relationTypes.has(edge.data.type) || !statuses.has(edge.data.status)) continue
    if (!present.has(edge.source) || !present.has(edge.target)) continue
    edges.push({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      data: edge.data,
      style: edge.style,
      states: reviewState(edge.data.status),
    })
  }
  return { nodes, edges }
}

function byCodePoint(a: string, b: string): number {
  return a < b ? -1 : a > b ? 1 : 0
}

/**
 * 章节下拉选项：只列图中出现的章节，按目录 `order`（再按 ID）排序，标题取目录，目录缺失时用 ID；
 * 有未分章知识点时末尾加「未分章」。
 */
export function chapterOptions(graph: GraphCanvasData, chapters: readonly Chapter[] = []): ChapterOption[] {
  const catalog = new Map(chapters.map((chapter) => [chapter.id, chapter]))
  const ids = new Set<string>()
  let unchaptered = false
  for (const node of graph.nodes) {
    if (node.data.chapterId === null) unchaptered = true
    else ids.add(node.data.chapterId)
  }
  const order = (id: string) => catalog.get(id)?.order ?? Number.POSITIVE_INFINITY
  const sorted = [...ids].sort((a, b) => order(a) - order(b) || byCodePoint(a, b))
  const options: ChapterOption[] = sorted.map((id) => ({
    value: { kind: 'chapter', id },
    label: catalog.get(id)?.title ?? id,
  }))
  if (unchaptered) options.push({ value: { kind: 'none' }, label: '未分章' })
  return options
}

export interface UseGraphFiltersOptions {
  /** 覆盖默认条件（如教师视图默认隐藏驳回项）；`clear` 回到这里 */
  initial?: Partial<GraphFilterState>
  layout?: GraphLayoutName
}

export interface GraphFilters {
  state: Ref<GraphFilterState>
  layout: Ref<GraphLayoutName>
  /** 选中的知识点 ID（契约 ID） */
  selected: Ref<string | null>
  /** 交给 `GraphCanvas` 的可见图；源图未到时为 null */
  visible: ComputedRef<GraphCanvasData | null>
  summary: ComputedRef<GraphSummary | null>
  isDefault: ComputedRef<boolean>
  /** 有选中项但被当前筛选隐藏 */
  selectedHidden: ComputedRef<boolean>
  clear(): void
  select(kpId: string | null): void
  toggleRelationType(type: RelationType): void
}

export function useGraphFilters(
  source: MaybeRefOrGetter<GraphCanvasData | null>,
  options: UseGraphFiltersOptions = {},
): GraphFilters {
  const initial = cloneState({ ...defaultFilterState(), ...options.initial })
  const state = ref<GraphFilterState>(cloneState(initial))
  const layout = ref<GraphLayoutName>(options.layout ?? 'hierarchical')
  const selected = shallowRef<string | null>(null)

  const graph = computed(() => toValue(source))

  const visible = computed(() => {
    const g = graph.value
    return g === null ? null : filterGraph(g, state.value, selected.value)
  })

  const summary = computed<GraphSummary | null>(() => {
    const g = graph.value
    const v = visible.value
    if (g === null || v === null) return null
    return { nodes: v.nodes.length, totalNodes: g.nodes.length, edges: v.edges.length, totalEdges: g.edges.length }
  })

  const isDefault = computed(() => sameFilterState(state.value, initial))

  const selectedHidden = computed(() => {
    const kpId = selected.value
    const v = visible.value
    return kpId !== null && v !== null && !v.nodes.some((node) => node.data.kpId === kpId)
  })

  // 新图里已没有选中的知识点（被删除、换课程）时清除选中
  watch(graph, (g) => {
    const kpId = selected.value
    if (g !== null && kpId !== null && !g.nodes.some((node) => node.data.kpId === kpId)) selected.value = null
  })

  return {
    state,
    layout,
    selected,
    visible,
    summary,
    isDefault,
    selectedHidden,
    clear() {
      state.value = cloneState(initial)
    },
    select(kpId) {
      selected.value = kpId
    },
    toggleRelationType(type) {
      const current = state.value.relationTypes
      state.value = {
        ...state.value,
        relationTypes: current.includes(type)
          ? current.filter((t) => t !== type)
          : RELATION_TYPE_ORDER.filter((t) => t === type || current.includes(t)),
      }
    },
  }
}
