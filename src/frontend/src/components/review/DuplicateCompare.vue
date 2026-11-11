<script setup lang="ts">
import { computed } from 'vue'
import type { RouteLocationRaw } from 'vue-router'
import { RouterLink } from 'vue-router'
import type { SuspectedDuplicate } from '../../api/review'
import { NODE_TYPE_LABELS } from '../../composables/useGraphFilters'
import type { DraftState, ItemError } from '../../composables/useReview'
import type { SourceCount } from '../../composables/useSourceCounts'
import type { GraphExchange } from '../../graph/adapter'
import { mergePreview } from '../../graph/mergePreview'
import AppIcon from '../AppIcon.vue'
import MergePreviewGraph from './MergePreviewGraph.vue'

/**
 * 疑似重复一条展开后的对比与合并预览（UX-REVIEW-DEDUP-01）。
 * 只展示与转发：选哪个保留、合并、不是重复都发事件给页面；预览由 `mergePreview` 按草稿图推算。
 * 候选怎样产生由后端决定，这里只读 `candidates`，草稿图读不到或找不到这两个知识点时退回只有名称的形态。
 */
const props = defineProps<{
  pair: SuspectedDuplicate
  /** 草稿图谱；从未读到为 null */
  graph: GraphExchange | null
  /** 草稿图是否可用于对比与预览：过期（队列已更新、图没读到）时不能再展示旧的定义和小图 */
  graphState: DraftState
  /** 两个知识点的来源数量读取状态（知识点 ID → 状态）；未读取为 undefined */
  sources?: Record<string, SourceCount | undefined>
  /** 正在重新读取队列与草稿图 */
  reloading?: boolean
  primaryId: string
  busy: boolean
  error: ItemError | null
  /** 单选组的名字（页面内唯一） */
  radioName: string
  /** “在图谱中查看”的去向；没有图谱路由时为 null */
  graphLink: RouteLocationRaw | null
}>()

const emit = defineEmits<{ choose: [primaryId: string]; merge: []; reject: []; collapse: []; reloadGraph: [] }>()

const pairIds = computed(() => props.pair.candidates.map((c) => c.id))
/** 只有与队列同一轮读到的图才用来对比和预览 */
const usable = computed(() => (props.graphState === 'current' ? props.graph : null))
const preview = computed(() => (usable.value === null ? null : mergePreview(usable.value, pairIds.value, props.primaryId)))
const primaryName = computed(() => props.pair.candidates.find((c) => c.id === props.primaryId)?.name ?? '')
const otherName = computed(() => props.pair.candidates.find((c) => c.id !== props.primaryId)?.name ?? '')

function sourceText(state: SourceCount | undefined): string {
  if (state === undefined) return '来源数量未读取'
  if (state.state === 'loading') return '来源读取中…'
  if (state.state === 'error') return '来源数量读取失败'
  return `来源 ${state.count} 处`
}

const cards = computed(() =>
  props.pair.candidates.map((candidate) => {
    const graph = usable.value
    const node = graph?.nodes.find((n) => n.id === candidate.id)
    const chapter = node?.chapter_id == null ? '未分章' : (graph?.chapters?.find((c) => c.id === node.chapter_id)?.title ?? '未分章')
    const relations = graph?.edges.filter((e) => e.status !== 'rejected' && (e.from_id === candidate.id || e.to_id === candidate.id)).length ?? 0
    return {
      id: candidate.id,
      name: candidate.name,
      found: node !== undefined,
      definition: node?.definition ?? '',
      meta: node === undefined ? '' : `${NODE_TYPE_LABELS[node.type]} · ${chapter}`,
      aliases: node?.aliases ?? [],
      // 草稿图的节点不带来源：数量来自详情接口，读取中、失败与真实的 0 分开显示
      sources: sourceText(props.sources?.[candidate.id]),
      relations,
    }
  }),
)

const noPreviewReason = computed(() => {
  if (props.graphState === 'stale') return '队列已更新，但草稿图谱没有刷新成功：上一轮的定义与合并预览可能已过期，已隐藏。仍可以合并或标记。'
  if (props.graph === null) return '草稿图谱暂时读取不到，无法显示定义与合并预览；仍可以合并或标记。'
  return '草稿图谱里找不到这两个知识点（可能刚被修改），无法显示合并预览。'
})

const facts = computed(() => {
  const s = preview.value?.summary
  if (s === undefined) return []
  const out = [`改接到「${primaryName.value}」的关系 ${s.moved} 条`]
  if (s.deduplicated > 0) out.push(`重复的关系合并掉 ${s.deduplicated} 条`)
  if (s.dropped > 0) out.push(`两者之间的关系去掉 ${s.dropped} 条`)
  if (s.addedAliases.length > 0) out.push(`新增别名：${s.addedAliases.join('、')}`)
  return out
})
</script>

<template>
  <fieldset class="review__merge rv-dup" data-test="rv-merge-panel">
    <legend>选择要保留的知识点</legend>

    <div class="rv-dup__cards">
      <label v-for="card in cards" :key="card.id" class="rv-dup__card" :class="{ 'is-primary': card.id === primaryId }" data-test="rv-dup-card" :data-id="card.id">
        <span class="rv-dup__head">
          <input type="radio" data-test="rv-primary" :name="radioName" :value="card.id" :checked="card.id === primaryId" :disabled="busy" @change="emit('choose', card.id)" />
          <strong>{{ card.name }}</strong>
          <span class="rv-dup__tag">{{ card.id === primaryId ? '保留' : '并入' }}</span>
        </span>
        <template v-if="card.found">
          <span class="rv-dup__def" data-test="rv-dup-definition">{{ card.definition || '（没有定义）' }}</span>
          <span class="rv-dup__meta">{{ card.meta }}</span>
          <span v-if="card.aliases.length > 0" class="rv-dup__meta">别名：{{ card.aliases.join('、') }}</span>
          <span class="rv-dup__meta" data-test="rv-dup-counts">{{ card.sources }} · 关系 {{ card.relations }} 条</span>
        </template>
        <span v-else class="rv-dup__meta" data-test="rv-dup-counts">{{ card.sources }}</span>
      </label>
    </div>

    <template v-if="preview">
      <div class="rv-dup__graphs" data-test="rv-dup-preview">
        <MergePreviewGraph :graph="preview.before" label="合并前" />
        <MergePreviewGraph :graph="preview.after" label="合并后（预计）" />
      </div>
      <p class="rv-dup__facts" data-test="rv-dup-facts"><span class="rv-dup__swatch" aria-hidden="true" />{{ facts.join(' · ') }}</p>
    </template>
    <p v-else class="rv-dup__nopreview" data-test="rv-dup-no-preview" role="status">
      {{ noPreviewReason }}
      <button type="button" data-test="rv-dup-reload" :disabled="busy || reloading" @click="emit('reloadGraph')">{{ reloading ? '正在重新读取…' : '重新读取' }}</button>
    </p>

    <p class="rv-dup__summary" data-test="rv-merge-summary">
      「{{ otherName }}」将并入「{{ primaryName }}」：名称并入别名，关系与来源迁到主知识点，主知识点被锁定。合并后无法一键撤销；上图是按规则推算的预计结果。
    </p>

    <div v-if="error" class="rv-dup__error" data-test="rv-item-error" role="alert">
      <p>{{ error.message }}</p>
      <p v-if="error.cycle" data-test="rv-cycle">
        环路：<template v-for="(step, index) in error.cycle" :key="`${step.kpId}-${index}`">
          <span v-if="index > 0"> → </span>{{ step.name }}
        </template>
      </p>
    </div>

    <div class="review__actions rv-dup__actions">
      <button type="button" class="rv-dup__primary" data-test="rv-merge-confirm" :disabled="busy" title="合并（快捷键 M）" @click="emit('merge')">合并到「{{ primaryName }}」</button>
      <button type="button" data-test="rv-not-duplicate" :disabled="busy" title="不是重复（快捷键 N）" @click="emit('reject')">不是重复</button>
      <button type="button" class="rv-dup__quiet" data-test="rv-merge-cancel" :disabled="busy" @click="emit('collapse')">收起</button>
      <RouterLink v-if="graphLink" class="rv-dup__link" data-test="rv-dup-graph-link" :to="graphLink"><AppIcon name="graph" :size="16" />在图谱中查看</RouterLink>
      <span class="rv-dup__keys" aria-hidden="true">M 合并 · N 不是重复 · ← → 上一条 / 下一条</span>
    </div>
  </fieldset>
</template>
