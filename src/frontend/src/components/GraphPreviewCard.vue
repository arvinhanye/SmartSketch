<script setup lang="ts">
import { ref } from 'vue'
import { NODE_TYPE_LABELS, type KnowledgePointType } from '../composables/useGraphFilters'
import { useGraphObstacle } from '../graph/obstacles'
import { NODE_TYPE_FILL, NODE_TYPE_GLYPH } from '../graph/theme'
import AppIcon from './AppIcon.vue'

/**
 * 单击节点后的轻量预览卡（规格 §7）：画布底部居中，侧栏不变。再次单击该节点或点「查看详情」才打开详情。
 * 列表接口不带定义，所以这里只放名称、类型、章节、掌握状态与先修/解锁数量；定义在详情里（不为预览多发请求）。
 */
defineProps<{
  name: string
  type: KnowledgePointType
  chapter: string
  masteryText: string
  mastery: 'mastered' | 'learning' | 'unknown'
  prerequisites: number
  unlocks: number
  /** 当前是否处于「只看相邻」 */
  localActive: boolean
}>()

const emit = defineEmits<{ close: []; open: []; toggleLocal: [] }>()

const root = ref<HTMLElement | null>(null)
useGraphObstacle(root)
</script>

<template>
  <aside ref="root" class="gw-preview" data-test="gw-preview" aria-label="知识点预览" aria-live="polite">
    <div class="gw-preview__top">
      <span class="gw-glyph" :style="{ background: NODE_TYPE_FILL[type] }" aria-hidden="true">{{ NODE_TYPE_GLYPH[type] }}</span>
      <span>{{ NODE_TYPE_LABELS[type] }}，{{ chapter }}</span>
      <button type="button" class="gw-iconbtn" aria-label="关闭预览" data-test="gw-preview-close" @click="emit('close')"><AppIcon name="close" /></button>
    </div>
    <p class="gw-preview__name">{{ name }}</p>
    <p class="gw-preview__meta">
      <span :data-mastery="mastery">{{ masteryText }}</span>
      <span>先修 {{ prerequisites }} 项</span>
      <span>学完可解锁 {{ unlocks }} 项</span>
    </p>
    <div class="gw-preview__actions">
      <button type="button" class="gw-btn" data-test="gw-preview-open" @click="emit('open')">查看详情</button>
      <button type="button" class="gw-btn gw-btn--ghost" data-test="gw-preview-local" :aria-pressed="localActive" @click="emit('toggleLocal')">
        {{ localActive ? '显示全部' : '只看相邻' }}
      </button>
      <span class="gw-hint">也可以再次点击该节点</span>
    </div>
  </aside>
</template>
