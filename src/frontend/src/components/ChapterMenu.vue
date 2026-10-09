<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useGraphObstacle } from '../graph/obstacles'
import AppIcon from './AppIcon.vue'

/**
 * 章节跳转菜单（规格 §4）：大图只能靠可读缩放浏览，按章节把镜头带到整章。
 * 每项显示本章知识点数量与已掌握数量；Esc 或点菜单外关闭，关闭后焦点回到按钮。
 */
export interface ChapterItem {
  id: string
  title: string
  total: number
  done: number
}

defineProps<{ chapters: readonly ChapterItem[]; currentId: string | null; disabled?: boolean }>()
const emit = defineEmits<{ jump: [chapterId: string] }>()

const root = ref<HTMLElement | null>(null)
const button = ref<HTMLButtonElement | null>(null)
const open = ref(false)
useGraphObstacle(root)

function close(focusButton: boolean): void {
  open.value = false
  if (focusButton) void nextTick(() => button.value?.focus())
}
function onDocumentPointer(event: PointerEvent): void {
  if (open.value && !root.value?.contains(event.target as Node | null)) close(true)
}
function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape' && open.value) {
    event.stopPropagation()
    close(true)
  }
}
function jump(id: string): void {
  open.value = false
  emit('jump', id)
  void nextTick(() => button.value?.focus())
}

onMounted(() => document.addEventListener('pointerdown', onDocumentPointer))
onBeforeUnmount(() => document.removeEventListener('pointerdown', onDocumentPointer))
</script>

<template>
  <div ref="root" class="gw-chap" @keydown="onKeydown">
    <button
      ref="button"
      type="button"
      class="gw-tool gw-tool--text"
      data-test="gw-chapter-button"
      aria-haspopup="true"
      :aria-expanded="open"
      :disabled="disabled"
      @click="open = !open"
    >
      <AppIcon name="chapters" />章节<AppIcon name="chevronDown" :size="14" />
    </button>
    <div v-if="open" class="gw-menu" role="group" aria-label="跳转到章节">
      <button
        v-for="chapter in chapters"
        :key="chapter.id"
        type="button"
        class="gw-menu__item"
        :class="{ 'is-current': chapter.id === currentId }"
        :aria-current="chapter.id === currentId ? 'true' : undefined"
        :data-test="`gw-chapter-${chapter.id}`"
        @click="jump(chapter.id)"
      >
        <span class="gw-menu__title">{{ chapter.title }}</span>
        <span class="gw-menu__meta">共 {{ chapter.total }} 个，已掌握 {{ chapter.done }}</span>
      </button>
    </div>
  </div>
</template>
