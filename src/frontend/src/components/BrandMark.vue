<script setup lang="ts">
import { computed } from 'vue'

/**
 * 智绘学途标志（UI-PINE-01）：阶梯形学习路线从空心起点经过一个节点走到终点。
 * - `color`：深松底块、白色路线、浅青与明黄节点（默认，浅色背景用）；
 * - `onDark`：白底块、深松路线（深色背景用）；
 * - `mono`：无底块的单色线稿。
 * 传入 `label` 时作为图片读出，否则对读屏隐藏（旁边已有文字名称时用）。
 */
const props = withDefaults(defineProps<{ size?: number; variant?: 'color' | 'onDark' | 'mono'; label?: string }>(), {
  size: 32,
  variant: 'color',
  label: undefined,
})

const palette = computed(() => {
  if (props.variant === 'onDark') return { tile: '#ffffff', line: '#0f3d36', start: '#ffffff', mid: '#0e6b5c', end: '#f5b82e' }
  if (props.variant === 'mono') return { tile: 'none', line: 'currentColor', start: 'transparent', mid: 'currentColor', end: 'currentColor' }
  return { tile: '#0f3d36', line: '#ffffff', start: '#0f3d36', mid: '#5fc3a8', end: '#f5b82e' }
})
</script>

<template>
  <svg
    :width="size"
    :height="size"
    viewBox="0 0 40 40"
    class="brand-mark"
    :role="label ? 'img' : undefined"
    :aria-label="label"
    :aria-hidden="label ? undefined : 'true'"
  >
    <rect v-if="palette.tile !== 'none'" width="40" height="40" rx="12" :fill="palette.tile" />
    <path d="M11 29V23a5 5 0 0 1 5-5h8a5 5 0 0 0 5-5v-2" fill="none" :stroke="palette.line" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" />
    <circle cx="11" cy="29" r="3.1" :fill="palette.start" :stroke="palette.line" stroke-width="2" />
    <circle cx="20" cy="18" r="3.2" :fill="palette.mid" />
    <circle cx="29" cy="11" r="3.7" :fill="palette.end" />
  </svg>
</template>
