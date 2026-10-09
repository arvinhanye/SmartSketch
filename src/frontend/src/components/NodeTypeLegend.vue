<script setup lang="ts">
import { NODE_TYPE_LABELS, type KnowledgePointType } from '../composables/useGraphFilters'
import { NODE_TYPE_FILL, NODE_TYPE_GLYPH } from '../graph/theme'

/**
 * 节点类型图例（教师图谱页）：画布上的节点只用颜色和一个单字区分类型，这里给出名称与个数，
 * 点击某一类即显示/隐藏该类（与工具栏“筛选”里的知识点类型是同一份状态）。计数取整张草稿图，不随筛选变化。
 */
defineProps<{
  counts: Readonly<Record<KnowledgePointType, number>>
  hidden: readonly KnowledgePointType[]
}>()
const emit = defineEmits<{ toggle: [type: KnowledgePointType]; restore: [] }>()
const order = Object.keys(NODE_TYPE_LABELS) as KnowledgePointType[]
</script>

<template>
  <ul class="node-legend" data-test="node-legend" aria-label="知识点类型图例，可按类型显示或隐藏">
    <li v-for="type in order" :key="type">
      <button
        type="button"
        class="node-legend__item"
        :aria-pressed="!hidden.includes(type)"
        :aria-label="`${NODE_TYPE_LABELS[type]}，${counts[type]} 个：${hidden.includes(type) ? '已隐藏，点击显示' : '显示中，点击隐藏'}`"
        :title="`${NODE_TYPE_LABELS[type]}（${NODE_TYPE_GLYPH[type]}）${counts[type]} 个 · 点击${hidden.includes(type) ? '显示' : '隐藏'}`"
        :data-test="`node-legend-${type}`"
        @click="emit('toggle', type)"
      >
        <span class="node-legend__glyph" :style="{ background: NODE_TYPE_FILL[type] }" aria-hidden="true">{{ NODE_TYPE_GLYPH[type] }}</span>
        {{ NODE_TYPE_LABELS[type] }}<small>{{ counts[type] }}</small>
      </button>
    </li>
    <li v-if="hidden.length > 0">
      <button type="button" class="node-legend__restore" data-test="node-legend-restore" @click="emit('restore')">恢复全部类型</button>
    </li>
  </ul>
</template>

<style scoped>
.node-legend {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.node-legend__item {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  min-height: 28px;
  padding: 0 9px 0 4px;
  border: 1px solid var(--gw-edge, #747a87);
  border-radius: 14px;
  background: var(--gw-panel, #f8f9fb);
  color: var(--gw-text, #1d2433);
  font-size: 12px;
  cursor: pointer;
}
.node-legend__item:hover {
  background: var(--gw-hover, #eceef2);
}
.node-legend__item[aria-pressed='false'] {
  background: var(--gw-hover, #eceef2);
  color: var(--gw-text-3, #6b7280);
  text-decoration: line-through;
}
.node-legend__item[aria-pressed='false'] .node-legend__glyph {
  opacity: 0.45;
}
.node-legend__item small {
  color: var(--gw-text-2, #4b5262);
  font-size: 11px;
}
.node-legend__glyph {
  display: grid;
  place-items: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  border: 1px solid #5b6070;
  font-size: 11px;
  line-height: 1;
}
.node-legend__restore {
  min-height: 28px;
  padding: 0 8px;
  border: 0;
  background: transparent;
  color: var(--gw-accent, #5145cd);
  font-size: 12px;
  cursor: pointer;
}
</style>
