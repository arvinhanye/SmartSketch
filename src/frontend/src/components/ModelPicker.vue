<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import AppIcon from './AppIcon.vue'

const props = defineProps<{ id: string; modelValue: string; models: string[]; disabled?: boolean; placeholder?: string; describedby?: string; testPrefix: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
const root = ref<HTMLElement | null>(null), input = ref<HTMLInputElement | null>(null)
const open = ref(false), all = ref(false), active = ref(-1), above = ref(false)
const matches = computed(() => all.value ? props.models : props.models.filter(name => name.toLowerCase().includes(props.modelValue.trim().toLowerCase())))
const listId = computed(() => `${props.id}-options`)
function place() {
 const box = root.value?.getBoundingClientRect()
 above.value = !!box && innerHeight - box.bottom < 180 && box.top > innerHeight - box.bottom
}
function show() { if (props.disabled) return; place(); open.value = true; active.value = -1 }
function type(event: Event) {
 emit('update:modelValue', (event.target as HTMLInputElement).value)
 all.value = false; show()
}
function toggle() {
 if (open.value && all.value) { open.value = false; return }
 input.value?.focus(); all.value = true; show()
}
function choose(name: string) { emit('update:modelValue', name); open.value = false; active.value = -1; input.value?.focus() }
async function key(event: KeyboardEvent) {
 if (event.key === 'Escape') { open.value = false; return }
 if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
  event.preventDefault()
  if (!open.value) { all.value = !props.modelValue; show() }
  if (!matches.value.length) return
  const step = event.key === 'ArrowDown' ? 1 : -1
  active.value = active.value < 0 ? (step > 0 ? 0 : matches.value.length - 1) : (active.value + step + matches.value.length) % matches.value.length
  await nextTick(); root.value?.querySelector(`#${props.id}-option-${active.value}`)?.scrollIntoView?.({block: 'nearest'})
 } else if (event.key === 'Enter' && open.value) {
  event.preventDefault()
  const name = matches.value[active.value]
  if (name) choose(name); else open.value = false
 }
}
function outside(event: PointerEvent) { if (!root.value?.contains(event.target as Node)) open.value = false }
function blur(event: FocusEvent) { if (!root.value?.contains(event.relatedTarget as Node | null)) open.value = false }
watch(() => [props.models, props.disabled], () => { active.value = -1; if (props.disabled || !props.models.length) open.value = false })
onMounted(() => document.addEventListener('pointerdown', outside))
onBeforeUnmount(() => document.removeEventListener('pointerdown', outside))
</script>

<template>
 <div ref="root" class="model-picker" @focusout="blur">
  <input :id="id" ref="input" :value="modelValue" :data-test="`${testPrefix}-model`" type="text" role="combobox" aria-autocomplete="list" :aria-expanded="open" :aria-controls="listId" :aria-activedescendant="open && active >= 0 ? `${id}-option-${active}` : undefined" :aria-describedby="describedby" :placeholder="placeholder || '输入模型名称，或展开列表选择'" autocomplete="off" spellcheck="false" :disabled="disabled" @input="type" @focus="all = false; show()" @keydown="key" />
  <button type="button" class="model-picker__toggle" :data-test="`${testPrefix}-model-toggle`" :disabled="disabled" :aria-expanded="open" :aria-controls="listId" aria-label="展开全部模型列表" @mousedown.prevent @click="toggle"><AppIcon name="chevron" :size="16" /></button>
  <div v-if="open" :id="listId" class="model-picker__menu" :class="{ 'is-above': above }" role="listbox" aria-label="可用模型">
   <button v-for="(name,index) in matches" :id="`${id}-option-${index}`" :key="name" type="button" role="option" :aria-selected="name === modelValue" :class="{ 'is-active': index === active }" tabindex="-1" @mousedown.prevent @click="choose(name)">{{ name }}</button>
   <p v-if="!matches.length" class="model-picker__empty" role="status">{{ modelValue ? `无匹配模型，可直接使用“${modelValue}”` : '尚未获取模型，可直接输入名称或刷新列表。' }}</p>
  </div>
 </div>
</template>

<style scoped>
.model-picker { position: relative; min-width: 0; }
.model-picker input { padding-right: 38px !important; }
.model-picker__toggle { position: absolute; right: 1px; top: 1px; bottom: 1px; width: 34px; display: grid; place-items: center; border: 0; border-radius: 0 5px 5px 0; color: var(--gw-text-2); background: transparent; cursor: pointer; }
.model-picker__toggle:hover:not(:disabled) { background: var(--gw-hover); }
.model-picker__toggle svg { transform: rotate(90deg); }
.model-picker__menu { position: absolute; z-index: 30; top: calc(100% + 5px); left: 0; right: 0; max-height: 200px; overflow-y: auto; padding: 4px; border: 1px solid var(--gw-line); border-radius: 8px; background: #fff; box-shadow: 0 8px 24px #1921361a; }
.model-picker__menu.is-above { top: auto; bottom: calc(100% + 5px); }
.model-picker__menu button { display: block; width: 100%; padding: 9px 10px; border: 0; border-radius: 5px; background: transparent; color: var(--gw-text); font-size: 13px; text-align: left; overflow-wrap: anywhere; cursor: pointer; }
.model-picker__menu button:hover, .model-picker__menu button.is-active { background: var(--gw-selected); color: var(--gw-accent); }
.model-picker__empty { margin: 0; padding: 10px; font-size: 12px; line-height: 20px; color: var(--gw-text-2); }
</style>
