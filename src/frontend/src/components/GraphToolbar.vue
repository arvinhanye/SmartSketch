<script setup lang="ts">
import { computed, useId } from 'vue'
import {
  NODE_TYPE_LABELS,
  RELATION_TYPE_ORDER,
  STATUS_LABELS,
  type ChapterOption,
  type GraphFilterState,
  type GraphSummary,
  type KnowledgePointType,
  type ReviewStatus,
} from '../composables/useGraphFilters'
import { RELATION_STYLES, type RelationType } from '../graph/adapter'
import type { GraphLayoutName } from '../graph/lifecycle'

/**
 * 图谱工具栏（H05）：搜索、关系图例兼按关系筛选、知识点类型、审核状态、章节、布局切换与清空。
 * 只发出新的筛选条件，不改动传入的对象；筛选计算在 `useGraphFilters`。
 */
const props = withDefaults(
  defineProps<{
    modelValue: GraphFilterState
    layout: GraphLayoutName
    chapters?: ChapterOption[]
    summary?: GraphSummary | null
    canClear?: boolean
    selectedHidden?: boolean
    /** 是否显示审核状态筛选与图例；学生看已发布图时关闭（H11），审核状态对学生无意义 */
    showStatuses?: boolean
  }>(),
  { chapters: () => [], summary: null, canClear: false, selectedHidden: false, showStatuses: true },
)

const emit = defineEmits<{
  'update:modelValue': [state: GraphFilterState]
  'update:layout': [layout: GraphLayoutName]
  clear: []
}>()

const uid = useId()

const relationItems = RELATION_TYPE_ORDER.map((type) => ({ type, style: RELATION_STYLES[type] }))
const nodeTypeItems = (Object.keys(NODE_TYPE_LABELS) as KnowledgePointType[]).map((type) => ({
  type,
  label: NODE_TYPE_LABELS[type],
}))
const statusItems = (Object.keys(STATUS_LABELS) as ReviewStatus[]).map((status) => ({
  status,
  label: STATUS_LABELS[status],
}))
const layoutItems: Array<{ value: GraphLayoutName; label: string }> = [
  { value: 'hierarchical', label: '层次' },
  { value: 'force', label: '力导向' },
]

function patch(change: Partial<GraphFilterState>): void {
  emit('update:modelValue', { ...props.modelValue, ...change })
}

/** 按固定顺序切换集合中的一项，输出新数组 */
function toggled<T>(order: readonly T[], current: readonly T[], item: T, on: boolean): T[] {
  return order.filter((x) => (x === item ? on : current.includes(x)))
}

function checked(event: Event): boolean {
  return (event.target as HTMLInputElement).checked
}

function onRelation(type: RelationType, event: Event): void {
  patch({ relationTypes: toggled(RELATION_TYPE_ORDER, props.modelValue.relationTypes, type, checked(event)) })
}

function onNodeType(type: KnowledgePointType, event: Event): void {
  const order = nodeTypeItems.map((item) => item.type)
  patch({ nodeTypes: toggled(order, props.modelValue.nodeTypes, type, checked(event)) })
}

function onStatus(status: ReviewStatus, event: Event): void {
  const order = statusItems.map((item) => item.status)
  patch({ statuses: toggled(order, props.modelValue.statuses, status, checked(event)) })
}

function onQuery(event: Event): void {
  patch({ query: (event.target as HTMLInputElement).value })
}

/** 下拉值：`all` 或章节选项的下标 */
const chapterValue = computed(() => {
  const current = props.modelValue.chapter
  if (current.kind === 'all') return 'all'
  const index = props.chapters.findIndex(
    (option) =>
      option.value.kind === current.kind &&
      (current.kind !== 'chapter' || (option.value as { id: string }).id === current.id),
  )
  return index < 0 ? 'all' : String(index)
})

function onChapter(event: Event): void {
  const value = (event.target as HTMLSelectElement).value
  const option = value === 'all' ? undefined : props.chapters[Number(value)]
  patch({ chapter: option === undefined ? { kind: 'all' } : { ...option.value } })
}

function onLayout(layout: GraphLayoutName): void {
  if (layout !== props.layout) emit('update:layout', layout)
}

const summaryText = computed(() => {
  const s = props.summary
  if (s === null) return ''
  if (s.totalNodes > 0 && s.nodes === 0) return '没有符合条件的知识点，可清空筛选。'
  return `显示 ${s.nodes} / ${s.totalNodes} 个知识点，${s.edges} / ${s.totalEdges} 条关系。`
})
</script>

<template>
  <div class="graph-toolbar" role="toolbar" aria-label="图谱筛选">
    <input
      class="graph-toolbar__search"
      type="search"
      aria-label="搜索知识点"
      placeholder="搜索知识点"
      :value="modelValue.query"
      @input="onQuery"
    />

    <fieldset class="graph-toolbar__group" data-test="relation-legend">
      <legend>关系</legend>
      <label v-for="item in relationItems" :key="item.type" :data-relation="item.type">
        <input
          type="checkbox"
          :checked="modelValue.relationTypes.includes(item.type)"
          @change="onRelation(item.type, $event)"
        />
        <svg class="graph-toolbar__swatch" width="32" height="10" viewBox="0 0 32 10" aria-hidden="true">
          <line
            x1="1"
            y1="5"
            :x2="item.style.directed ? 25 : 31"
            y2="5"
            :stroke="item.style.stroke"
            :stroke-width="item.style.lineWidth"
            :stroke-dasharray="item.style.lineDash.length > 0 ? item.style.lineDash.join(' ') : undefined"
          />
          <polygon v-if="item.style.directed" data-test="arrow" points="24,1 31,5 24,9" :fill="item.style.stroke" />
        </svg>
        {{ item.style.label }}
      </label>
    </fieldset>

    <fieldset class="graph-toolbar__group">
      <legend>知识点类型</legend>
      <label v-for="item in nodeTypeItems" :key="item.type" :data-node-type="item.type">
        <input
          type="checkbox"
          :checked="modelValue.nodeTypes.includes(item.type)"
          @change="onNodeType(item.type, $event)"
        />
        {{ item.label }}
      </label>
    </fieldset>

    <fieldset v-if="showStatuses" class="graph-toolbar__group" data-test="status-filter">
      <legend>审核状态</legend>
      <label v-for="item in statusItems" :key="item.status" :data-status="item.status">
        <input
          type="checkbox"
          :checked="modelValue.statuses.includes(item.status)"
          @change="onStatus(item.status, $event)"
        />
        <span
          data-test="swatch"
          class="graph-toolbar__node-swatch"
          :class="`graph-toolbar__node-swatch--${item.status}`"
          aria-hidden="true"
        />
        {{ item.label }}
      </label>
    </fieldset>

    <label class="graph-toolbar__chapter">
      章节
      <select :value="chapterValue" @change="onChapter">
        <option value="all">全部章节</option>
        <option v-for="(option, index) in chapters" :key="index" :value="String(index)">{{ option.label }}</option>
      </select>
    </label>

    <div class="graph-toolbar__group" role="radiogroup" aria-label="布局">
      <label v-for="item in layoutItems" :key="item.value">
        <input
          type="radio"
          :name="`${uid}-layout`"
          :value="item.value"
          :checked="layout === item.value"
          @change="onLayout(item.value)"
        />
        {{ item.label }}
      </label>
    </div>

    <button type="button" data-test="clear" :disabled="!canClear" @click="emit('clear')">清空筛选</button>

    <p class="graph-toolbar__summary" data-test="summary" aria-live="polite">
      {{ summaryText }}
      <span v-if="selectedHidden">选中的知识点已被筛选隐藏。</span>
    </p>
  </div>
</template>

<style scoped>
.graph-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 16px;
  padding: 8px 0;
}

.graph-toolbar__search {
  min-width: 12em;
}

.graph-toolbar__group {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 12px;
  margin: 0;
  padding: 2px 8px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
}

.graph-toolbar__group legend {
  padding: 0 4px;
  font-size: 12px;
}

.graph-toolbar__group label,
.graph-toolbar__chapter {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.graph-toolbar__swatch {
  flex: none;
}

/* 与画布节点状态样式（lifecycle.ts buildGraphOptions 的 node.state）一致 */
.graph-toolbar__node-swatch {
  display: inline-block;
  width: 12px;
  height: 12px;
  border: 1.5px solid #1677ff;
  border-radius: 50%;
  background: #ffffff;
}

.graph-toolbar__node-swatch--low_confidence {
  border-color: #fa8c16;
  border-style: dashed;
}

.graph-toolbar__node-swatch--rejected {
  border-color: #bfbfbf;
  border-style: dashed;
  opacity: 0.4;
}

.graph-toolbar__summary {
  flex-basis: 100%;
  margin: 0;
  font-size: 12px;
}
</style>
