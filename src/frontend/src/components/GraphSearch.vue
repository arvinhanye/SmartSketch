<script setup lang="ts">
import { computed, ref, useId, watch } from 'vue'
import AppIcon from './AppIcon.vue'
import GraphOverlay from './GraphOverlay.vue'

/**
 * 图谱搜索框（UI-GRAPH-FIND-01）：输入即高亮（由页面处理），下方给出候选；回车依次定位下一个命中，
 * Shift+回车上一个；↑/↓ 在候选里移动，回车选定；Esc 收起候选。
 * 只发事件，不持有查找逻辑：命中列表与当前位置由页面给。
 */
export interface SearchOption {
  kpId: string
  name: string
  /** 章节与类型等说明 */
  meta: string
  /** 经别名命中时的别名 */
  alias: string | null
}

const props = withDefaults(
  defineProps<{
    modelValue: string
    options: readonly SearchOption[]
    /** 当前定位到第几个命中（0 起）；还没定位为 -1 */
    cursor: number
    /** 候选最多显示几条 */
    limit?: number
  }>(),
  { limit: 8 },
)
const emit = defineEmits<{
  'update:modelValue': [query: string]
  /** 定位下一个（1）或上一个（-1）命中 */
  step: [delta: 1 | -1]
  pick: [kpId: string]
}>()

const uid = useId()
const listId = `${uid}-list`
const root = ref<HTMLElement | null>(null)
const input = ref<HTMLInputElement | null>(null)
const open = ref(false)
/** 候选里键盘移动到的那一项；-1 表示没有（此时回车是“下一个命中”） */
const active = ref(-1)

const shown = computed(() => props.options.slice(0, props.limit))
const hasQuery = computed(() => props.modelValue.trim() !== '')
const expanded = computed(() => open.value && shown.value.length > 0)
const countText = computed(() => {
  const total = props.options.length
  if (!hasQuery.value) return ''
  if (total === 0) return '无匹配'
  return props.cursor >= 0 ? `${props.cursor + 1} / ${total}` : `共 ${total} 个`
})

watch(
  () => props.options,
  () => {
    active.value = -1
  },
)

function close(): void {
  open.value = false
  active.value = -1
}

function onInput(event: Event): void {
  emit('update:modelValue', (event.target as HTMLInputElement).value)
  open.value = true
}

function pick(kpId: string): void {
  close()
  emit('pick', kpId)
}

function onSubmit(): void {
  const option = expanded.value && active.value >= 0 ? shown.value[active.value] : undefined
  if (option !== undefined) pick(option.kpId)
  else {
    close()
    emit('step', 1)
  }
}

function onKeydown(event: KeyboardEvent): void {
  if (event.isComposing) return
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    if (shown.value.length === 0) return
    event.preventDefault()
    const count = shown.value.length
    if (!open.value) {
      open.value = true
      active.value = event.key === 'ArrowDown' ? 0 : count - 1
    } else if (event.key === 'ArrowDown') active.value = active.value + 1 >= count ? 0 : active.value + 1
    else active.value = active.value <= 0 ? count - 1 : active.value - 1
  } else if (event.key === 'Enter' && event.shiftKey) {
    event.preventDefault()
    close()
    emit('step', -1)
  } else if (event.key === 'Escape' && expanded.value) {
    // 只收起候选；页面的 Esc（取消预览、关闭抽屉）留给下一次
    event.preventDefault()
    event.stopPropagation()
    close()
  }
}

function onFocusOut(event: FocusEvent): void {
  if (!root.value?.contains(event.relatedTarget as Node | null)) close()
}

defineExpose({
  /** 聚焦搜索框并全选（快捷键 `/`） */
  focus: () => {
    input.value?.focus()
    input.value?.select()
  },
})
</script>

<template>
  <div ref="root" class="gw-searchbox" @focusout="onFocusOut">
    <GraphOverlay as="form" class="gw-search" role="search" @submit.prevent="onSubmit">
      <AppIcon name="search" :size="16" />
      <input
        ref="input"
        type="search"
        role="combobox"
        aria-label="搜索知识点"
        aria-autocomplete="list"
        :aria-expanded="expanded"
        :aria-controls="listId"
        :aria-activedescendant="expanded && active >= 0 ? `${uid}-opt-${active}` : undefined"
        placeholder="搜索知识点，回车定位"
        title="搜索名称或别名；回车定位下一个，Shift+回车上一个（快捷键 /）"
        autocomplete="off"
        :value="modelValue"
        @input="onInput"
        @keydown="onKeydown"
      />
      <template v-if="hasQuery">
        <span class="gw-search__count" data-test="gw-search-count" role="status">{{ countText }}</span>
        <button type="button" class="gw-search__nav gw-search__nav--prev" data-test="gw-search-prev" aria-label="上一个匹配" title="上一个匹配（Shift+回车）" :disabled="options.length === 0" @click="emit('step', -1)">
          <AppIcon name="chevronDown" :size="14" />
        </button>
        <button type="button" class="gw-search__nav" data-test="gw-search-next" aria-label="下一个匹配" title="下一个匹配（回车）" :disabled="options.length === 0" @click="emit('step', 1)">
          <AppIcon name="chevronDown" :size="14" />
        </button>
      </template>
      <kbd v-else class="gw-search__kbd" aria-hidden="true">/</kbd>
    </GraphOverlay>
    <ul v-if="expanded" :id="listId" class="gw-menu gw-search__list" role="listbox" aria-label="匹配的知识点" data-test="gw-search-list">
      <li
        v-for="(option, index) in shown"
        :id="`${uid}-opt-${index}`"
        :key="option.kpId"
        class="gw-menu__item"
        :class="{ 'is-current': index === active }"
        role="option"
        :aria-selected="index === active"
        data-test="gw-search-option"
        @pointerdown.prevent
        @click="pick(option.kpId)"
      >
        <span class="gw-menu__title">{{ option.name }}</span>
        <span class="gw-menu__meta">{{ option.alias === null ? option.meta : `别名：${option.alias} · ${option.meta}` }}</span>
      </li>
      <li v-if="options.length > shown.length" class="gw-search__more" role="presentation">还有 {{ options.length - shown.length }} 个，回车逐个查看</li>
    </ul>
  </div>
</template>
