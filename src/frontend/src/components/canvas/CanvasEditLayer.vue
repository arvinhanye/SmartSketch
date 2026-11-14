<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import type { CanvasEditing } from '../../composables/useCanvasEditing'
import { RELATION_TYPES } from '../../composables/useRelationEditor'
import { RELATION_STYLES, type RelationType } from '../../graph/adapter'

/**
 * 画布上的编辑浮层（UI-GRAPH-EDIT-02）：关系线工具条、节点悬停工具（“⋯”与连接柄）、节点菜单、
 * 连线的虚线与目标外环、关系类型选择、撤销提示与错误说明。
 *
 * 放在 `GraphCanvas` 的插槽里，铺满画布容器，坐标与画布一致。本身不拦指针（`pointer-events: none`），
 * 只有具体的工具可点。状态与写入都在 `useCanvasEditing`，这里只画与转发。
 */
const props = defineProps<{ editing: CanvasEditing; error: string | null; conflict: readonly string[] | null }>()
const emit = defineEmits<{ dismissError: [] }>()

// 组合式返回的是一组 ref：包成 reactive 让模板直接读
const ed = computed(() => reactive(props.editing))
const root = ref<HTMLElement | null>(null)
const menuEl = ref<HTMLElement | null>(null)
const chooserEl = ref<HTMLElement | null>(null)
const typeOptions = RELATION_TYPES.map((type) => ({ type, label: RELATION_STYLES[type].label }))

/** 浮层不越出画布：按容器尺寸收紧 */
function clampTo(x: number, y: number, width: number, height: number): { left: string; top: string } {
  const w = root.value?.clientWidth ?? 0
  const h = root.value?.clientHeight ?? 0
  const left = w === 0 ? x : Math.max(8, Math.min(x, w - width - 8))
  const top = h === 0 ? y : Math.max(8, Math.min(y, h - height - 8))
  return { left: `${left}px`, top: `${top}px` }
}

const edgeStyle = computed(() => {
  const tool = ed.value.edgeTool
  return tool === null ? {} : clampTo(tool.at.x - 120, tool.at.y - 60, 240, 44)
})
const menuStyle = computed(() => {
  const menu = ed.value.menu
  return menu === null ? {} : clampTo(menu.at.x + 6, menu.at.y + 6, 184, 176)
})
const chooserStyle = computed(() => {
  const state = ed.value.connect
  return state === null || state.phase !== 'choosing' ? {} : clampTo(state.at.x + 22, state.at.y - 20, 208, 190)
})
const drag = computed(() => {
  const state = ed.value.connect
  return state !== null && state.phase === 'dragging' ? state : null
})
const choosing = computed(() => {
  const state = ed.value.connect
  return state !== null && state.phase === 'choosing' ? state : null
})
const picking = computed(() => {
  const state = ed.value.connect
  return state !== null && state.phase === 'picking' ? state : null
})

function point(event: PointerEvent): { x: number; y: number } {
  const box = root.value?.getBoundingClientRect()
  return { x: event.clientX - (box?.left ?? 0), y: event.clientY - (box?.top ?? 0) }
}
function onHandleDown(event: PointerEvent): void {
  const from = ed.value.hover
  if (event.button !== 0 || from === null) return
  event.preventDefault()
  ;(event.currentTarget as HTMLElement).setPointerCapture?.(event.pointerId)
  props.editing.startDrag(from, point(event))
}
// 拖动中的移动与松开挂在窗口上：指针离开连接柄、甚至离开画布也跟得上
function onWindowMove(event: PointerEvent): void {
  if (drag.value !== null) props.editing.dragTo(point(event))
}
function onWindowUp(): void {
  if (drag.value !== null) props.editing.endDrag()
}

function onEdgeType(event: Event): void {
  void props.editing.changeEdgeType((event.target as HTMLSelectElement).value as RelationType)
}

// ---- 菜单的键盘：↑/↓ 移动，Enter 执行（按钮自带），E 编辑，L 连线
function menuItems(): HTMLButtonElement[] {
  return [...(menuEl.value?.querySelectorAll<HTMLButtonElement>('[role="menuitem"]') ?? [])]
}
function onMenuKey(event: KeyboardEvent): void {
  const items = menuItems()
  const index = items.indexOf(document.activeElement as HTMLButtonElement)
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault()
    const next = event.key === 'ArrowDown' ? (index + 1) % items.length : (index - 1 + items.length) % items.length
    items[next]?.focus()
  } else if (event.key.toLowerCase() === 'e') {
    event.preventDefault()
    props.editing.menuAction('edit')
  } else if (event.key.toLowerCase() === 'l') {
    event.preventDefault()
    props.editing.menuAction('connect')
  }
}
watch(
  () => ed.value.menu,
  async (menu) => {
    if (menu === null) return
    await nextTick()
    menuItems()[0]?.focus()
  },
)
watch(choosing, async (state) => {
  if (state === null) return
  await nextTick()
  chooserEl.value?.querySelector<HTMLButtonElement>('button:not(:disabled)')?.focus()
})

function onWindowKey(event: KeyboardEvent): void {
  if (event.key !== 'Escape') return
  const active = ed.value.edgeTool !== null || ed.value.menu !== null || ed.value.connect !== null
  if (!active) return
  event.preventDefault()
  props.editing.dismiss()
}
onMounted(() => {
  window.addEventListener('keydown', onWindowKey)
  window.addEventListener('pointermove', onWindowMove)
  window.addEventListener('pointerup', onWindowUp)
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onWindowKey)
  window.removeEventListener('pointermove', onWindowMove)
  window.removeEventListener('pointerup', onWindowUp)
})
</script>

<template>
  <div ref="root" class="ce-layer" data-test="ce-layer">
    <!-- 连线拖动：虚线跟随指针，目标外环 -->
    <svg v-if="drag" class="ce-drag" data-test="ce-drag" aria-hidden="true">
      <line :x1="drag.start.x" :y1="drag.start.y" :x2="drag.pointer.x" :y2="drag.pointer.y" />
      <circle v-if="drag.target" :class="{ 'is-cycle': drag.cycle }" :cx="drag.target.x" :cy="drag.target.y" :r="drag.target.r + 6" />
    </svg>
    <p v-if="drag?.target" class="ce-hint" :class="{ 'is-warn': drag.cycle }" data-test="ce-drag-hint" role="status" :style="clampTo(drag.target.x + drag.target.r + 12, drag.target.y - 14, 150, 28)">
      {{ drag.cycle ? '前置会形成环，可选其他类型' : '松开后选关系类型' }}
    </p>

    <!-- 悬停工具：菜单按钮与连接柄 -->
    <template v-if="ed.hover && !ed.menu && !ed.edgeTool && !ed.connect">
      <button
        type="button"
        class="ce-more"
        data-test="ce-more"
        aria-label="更多操作"
        title="更多操作（也可以在节点上点右键）"
        :style="{ left: `${ed.hover.x + ed.hover.r * 0.72 - 2}px`, top: `${ed.hover.y - ed.hover.r * 0.72 - 20}px` }"
        @pointerenter="editing.holdHover"
        @pointerleave="editing.releaseHover"
        @click="editing.openMenu({ kpId: ed.hover.kpId, x: ed.hover.x + ed.hover.r, y: ed.hover.y - ed.hover.r })"
      >
        ⋯
      </button>
      <button
        type="button"
        class="ce-handle"
        data-test="ce-handle"
        aria-label="从这里拖出连线"
        title="按住拖到另一个知识点，建立关系"
        :style="{ left: `${ed.hover.x + ed.hover.r - 3}px`, top: `${ed.hover.y - 8}px` }"
        @pointerenter="editing.holdHover"
        @pointerleave="editing.releaseHover"
        @pointerdown="onHandleDown"
      />
    </template>

    <!-- 节点菜单 -->
    <div v-if="ed.menu" ref="menuEl" class="ce-menu" data-test="ce-menu" role="menu" :aria-label="`「${editing.nameOf(ed.menu.kpId)}」的操作`" :style="menuStyle" @keydown="onMenuKey">
      <button type="button" role="menuitem" data-test="ce-menu-detail" @click="editing.menuAction('detail')">查看详情</button>
      <button type="button" role="menuitem" data-test="ce-menu-edit" @click="editing.menuAction('edit')">编辑知识点<kbd>E</kbd></button>
      <button type="button" role="menuitem" class="is-accent" data-test="ce-menu-connect" @click="editing.menuAction('connect')">从这里连线…<kbd>L</kbd></button>
      <hr />
      <button type="button" role="menuitem" class="is-danger" data-test="ce-menu-delete" @click="editing.menuAction('delete')">删除…</button>
    </div>

    <!-- 关系线工具条 -->
    <div v-if="ed.edgeTool && ed.edgeRow" class="ce-edge" data-test="ce-edge" role="toolbar" :aria-label="`关系：${ed.edgeRow.fromName} → ${ed.edgeRow.toName}`" :style="edgeStyle">
      <label class="ce-edge__type">
        <span class="visually-hidden">关系类型</span>
        <select data-test="ce-edge-type" :value="ed.edgeRow.type" :disabled="ed.busy" @change="onEdgeType">
          <option v-for="option in typeOptions" :key="option.type" :value="option.type">{{ option.label }}</option>
        </select>
      </label>
      <button v-if="ed.edgeRow.reversible" type="button" data-test="ce-edge-reverse" :disabled="ed.busy" title="把起点和终点对调" @click="editing.reverseEdge">⇄ 反转</button>
      <button type="button" class="is-danger" data-test="ce-edge-delete" :disabled="ed.busy" title="删除这条关系（之后可以撤销）" @click="editing.deleteEdge">删除</button>
    </div>

    <!-- 点选连线的提示 -->
    <p v-if="picking" class="ce-banner" data-test="ce-picking" role="status">
      从「{{ editing.nameOf(picking.from) }}」连线：点击目标知识点完成，Esc 取消
      <button type="button" data-test="ce-picking-cancel" @click="editing.dismiss">取消</button>
    </p>

    <!-- 关系类型选择 -->
    <div v-if="choosing" ref="chooserEl" class="ce-chooser" data-test="ce-chooser" role="group" :aria-label="`选择「${editing.nameOf(choosing.from)}」到「${editing.nameOf(choosing.to)}」的关系类型`" :style="chooserStyle">
      <p class="ce-chooser__title">{{ editing.nameOf(choosing.from) }} → {{ editing.nameOf(choosing.to) }}</p>
      <button
        v-for="option in typeOptions"
        :key="option.type"
        type="button"
        :data-test="`ce-type-${option.type}`"
        :disabled="ed.busy || (option.type === 'PREREQUISITE' && choosing.prerequisiteBlocked)"
        @click="editing.confirmType(option.type)"
      >
        {{ option.label }}
      </button>
      <p v-if="choosing.prerequisiteBlocked" class="ce-chooser__note" data-test="ce-chooser-cycle">“前置”会形成环，不能选。</p>
    </div>

    <!-- 撤销删除 -->
    <p v-if="ed.undo" class="ce-toast" data-test="ce-undo" role="status">
      <span>{{ ed.undo.text }}</span>
      <button type="button" data-test="ce-undo-btn" :disabled="ed.busy" title="按原来的类型和端点重新建立；原关系的编号、来源与审核状态不会恢复" @click="editing.undoDelete">撤销</button>
      <button type="button" class="ce-toast__x" aria-label="关闭提示" @click="editing.dismissUndo">×</button>
    </p>

    <!-- 画布上发起的操作失败时，原因就显示在画布上（不要求打开“编辑关系”页签） -->
    <div v-if="error || conflict || ed.undoError" class="ce-toast is-error" data-test="ce-error" role="alert">
      <span>
        <!-- 成环时组合式给的错误文案里已经带了环路；只有没有文案时才由这里补上环路 -->
        <template v-if="ed.undoError ?? error">{{ ed.undoError ?? error }}</template>
        <template v-else>这样改会让前置关系成环，未保存。环路：{{ (conflict ?? []).join(' → ') }}</template>
      </span>
      <button type="button" class="ce-toast__x" aria-label="关闭提示" @click="emit('dismissError')">×</button>
    </div>
  </div>
</template>
