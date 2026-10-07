<script setup lang="ts">
import { ref } from 'vue'
import { NODE_TYPE_LABELS, RELATION_TYPE_ORDER, type KnowledgePointType } from '../composables/useGraphFilters'
import { RELATION_STYLES, type RelationType } from '../graph/adapter'
import { useGraphObstacle } from '../graph/obstacles'
import { NODE_TYPE_FILL, NODE_TYPE_GLYPH } from '../graph/theme'
import AppIcon from './AppIcon.vue'

/**
 * 图例兼关系与类型筛选（规格 §4 第 4 层，借鉴 Bloom 的 Legend）：带计数，可按类隐藏；隐藏状态可见、可恢复。
 * 计数取整张图，不随筛选变化。可展开的图例是「软障碍」：标签要避开它，但镜头适应不为它缩小范围。
 */
const props = defineProps<{
  open: boolean
  hiddenRelations: readonly RelationType[]
  hiddenTypes: readonly KnowledgePointType[]
  relationCounts: Readonly<Record<RelationType, number>>
  typeCounts: Readonly<Record<KnowledgePointType, number>>
}>()

const emit = defineEmits<{
  'update:open': [open: boolean]
  toggleRelation: [type: RelationType]
  toggleType: [type: KnowledgePointType]
  restore: []
}>()

const root = ref<HTMLElement | null>(null)
useGraphObstacle(root, 'soft')

/** 箭头方向说明；`EXAMPLE_OF` 的方向契约未明文，这里不写，以画布箭头为准 */
const RELATION_HINTS: Partial<Record<RelationType, string>> = {
  PREREQUISITE: '先学 → 后学',
  CONTAINS: '上级 → 下级',
  RELATED_TO: '无方向',
}
const typeOrder = Object.keys(NODE_TYPE_LABELS) as KnowledgePointType[]
const hiddenCount = () => props.hiddenRelations.length + props.hiddenTypes.length
</script>

<template>
  <section ref="root" class="gw-legend" :class="{ 'is-closed': !open }" data-test="relation-legend" aria-label="图例与关系筛选">
    <button type="button" class="gw-legend__head" :aria-expanded="open" @click="emit('update:open', !open)">
      图例<AppIcon :name="open ? 'chevronDown' : 'chevron'" :size="16" />
    </button>
    <template v-if="open">
      <ul class="gw-legend__rel">
        <li v-for="type in RELATION_TYPE_ORDER" :key="type">
          <button
            type="button"
            :aria-pressed="!hiddenRelations.includes(type)"
            :aria-label="`${RELATION_STYLES[type].label}：${hiddenRelations.includes(type) ? '已隐藏，点击显示' : '显示中，点击隐藏'}`"
            :data-test="`legend-rel-${type}`"
            @click="emit('toggleRelation', type)"
          >
            <svg width="34" height="10" aria-hidden="true">
              <line
                x1="1"
                y1="5"
                :x2="RELATION_STYLES[type].directed ? 25 : 33"
                y2="5"
                :stroke="RELATION_STYLES[type].stroke"
                :stroke-width="RELATION_STYLES[type].lineWidth"
                :stroke-dasharray="RELATION_STYLES[type].lineDash.join(' ')"
              />
              <path v-if="RELATION_STYLES[type].directed" d="M33 5 25 1.5v7z" :fill="RELATION_STYLES[type].stroke" />
            </svg>
            <span>{{ RELATION_STYLES[type].label }}<small v-if="RELATION_HINTS[type]">{{ RELATION_HINTS[type] }}</small></span>
            <span class="gw-legend__count">{{ relationCounts[type] }}</span>
            <span v-if="hiddenRelations.includes(type)" class="gw-legend__off"><AppIcon name="eyeOff" :size="14" />已隐藏</span>
          </button>
        </li>
      </ul>
      <p v-if="hiddenCount() > 0" class="gw-legend__restore" role="status">
        已隐藏 {{ hiddenCount() }} 类 <button type="button" class="gw-link" data-test="legend-restore" @click="emit('restore')">恢复全部</button>
      </p>
      <ul class="gw-legend__types" aria-label="知识点类型，可按类型筛选">
        <li v-for="type in typeOrder" :key="type">
          <button
            type="button"
            :aria-pressed="!hiddenTypes.includes(type)"
            :aria-label="`${NODE_TYPE_LABELS[type]}，${typeCounts[type]} 个：${hiddenTypes.includes(type) ? '已隐藏，点击显示' : '显示中，点击隐藏'}`"
            :data-test="`legend-type-${type}`"
            @click="emit('toggleType', type)"
          >
            <span class="gw-glyph gw-glyph--s" :style="{ background: NODE_TYPE_FILL[type] }" aria-hidden="true">{{ NODE_TYPE_GLYPH[type] }}</span>
            {{ NODE_TYPE_LABELS[type] }}<small>{{ typeCounts[type] }}</small>
            <AppIcon v-if="hiddenTypes.includes(type)" name="eyeOff" :size="14" />
          </button>
        </li>
      </ul>
      <ul class="gw-legend__mastery" aria-label="掌握状态">
        <li><span class="gw-badge gw-badge--ok" aria-hidden="true">✓</span>已掌握</li>
        <li><span class="gw-badge gw-badge--warn" aria-hidden="true">◐</span>学习中</li>
        <li><span class="gw-badge gw-badge--none" aria-hidden="true" />未学习</li>
      </ul>
    </template>
  </section>
</template>
