<script setup lang="ts">
import { computed, inject, onActivated, onBeforeUnmount, onMounted, ref, toRaw, watch } from 'vue'
import { useReducedMotion } from '../composables/useReducedMotion'
import type { Positions } from '../graph/chapterLayout'
import {
  createGraphLifecycle,
  GRAPH_FACTORY_KEY,
  loadG6Graph,
  type GraphCanvasData,
  type GraphLayoutName,
  type GraphLifecycle,
  type LifecycleStatus,
} from '../graph/lifecycle'
import { GRAPH_OBSTACLES_KEY, useGraphObstacle } from '../graph/obstacles'
import { MASTERY_TEXT, masteryOfStates } from '../graph/presentation'
import AppIcon from './AppIcon.vue'

/**
 * 课程知识图谱画布（H04）：只负责把适配图画出来并支持缩放、拖拽。
 * 数据请求、筛选与详情由页面和后续组件负责；`graph` 为 null 表示数据尚未到达。
 * L13：初始视口不低于可读缩放（`data-zoom` 记录当前缩放）；`focus(kpId)` 供页面在搜索、跳转后聚焦。
 *
 * 增强模式（`enhanced`，学生图谱页，UI-GRAPH-PILOT-01）：章节分区布局（`positions`）、语义缩放与标签避让、
 * 悬停强淡化、章节外框（`scope`）、小地图与缩放控件、悬停 tooltip。关闭时与 H04 一致（教师页沿用）。
 * 增强模式下切换布局或位置变化会重建画布（选中等状态随数据保留）。
 */
const props = withDefaults(
  defineProps<{
    graph: GraphCanvasData | null
    label?: string
    layout?: GraphLayoutName
    enhanced?: boolean
    audience?: 'student' | 'teacher'
    /** 章节分区布局的位置（知识点 ID → 坐标）；增强模式下 null 表示还在计算，画布等它 */
    positions?: Positions | null
    /** 章节外框成员（知识点 ID）；null 为没有 */
    scope?: readonly string[] | null
  }>(),
  { label: '课程知识图谱', layout: 'hierarchical', enhanced: false, audience: 'student', positions: null, scope: null },
)

const emit = defineEmits<{ nodeClick: [kpId: string]; blankClick: [] }>()

const factory = inject(GRAPH_FACTORY_KEY, loadG6Graph)
const registry = inject(GRAPH_OBSTACLES_KEY, null)
const reduced = useReducedMotion()
const root = ref<HTMLElement | null>(null)
const stage = ref<HTMLElement | null>(null)
const mini = ref<HTMLElement | null>(null)
const controls = ref<HTMLElement | null>(null)
const status = ref<LifecycleStatus | 'idle'>('idle')
const drawnOnce = ref(false)
const zoom = ref<number | null>(null)
/** 小地图默认展开；<1024px 默认收起（规格 §5.1） */
const miniOpen = ref(typeof window === 'undefined' || window.innerWidth >= 1024)
const tip = ref<{ text: string; x: number; y: number } | null>(null)
let lifecycle: GraphLifecycle | null = null
let tipTimer: ReturnType<typeof setTimeout> | null = null
let stopObstacles: (() => void) | null = null
/**
 * 最近一次请求聚焦的知识点：画布建好之前请求的聚焦在建好后执行；重建（换布局、换位置）后回到它，
 * 而不是退回整图适配（L14：视口跟随最近一次聚焦）
 */
let lastFocus: string | null = null

// 小地图与缩放控件本身也是画布上的浮层
useGraphObstacle(controls, 'hard')

/** 增强模式 + 层次布局时要等章节布局算好才建图（避免先画一遍 dagre 再跳变） */
const ready = computed(
  () => props.graph !== null && (!props.enhanced || props.layout !== 'hierarchical' || props.positions !== null),
)
const loading = computed(() => !ready.value || (!drawnOnce.value && status.value !== 'error'))
const empty = computed(() => !loading.value && props.graph !== null && props.graph.nodes.length === 0)
const ariaLabel = computed(() =>
  props.graph === null
    ? `${props.label}：加载中`
    : `${props.label}：${props.graph.nodes.length} 个知识点，${props.graph.edges.length} 条关系`,
)

function showTip(info: { kpId: string; clientX: number; clientY: number } | null): void {
  if (tipTimer !== null) clearTimeout(tipTimer)
  tip.value = null
  if (info === null || root.value === null) return
  const box = root.value.getBoundingClientRect()
  // tooltip 延迟 300ms 出现（规格 §9）：名称与掌握状态文字，完整名称不依赖标签是否显示
  tipTimer = setTimeout(() => {
    const node = props.graph?.nodes.find((n) => n.data.kpId === info.kpId)
    if (node === undefined) return
    tip.value = {
      text: props.audience === 'teacher'
        ? `${node.data.name}（${({draft:'待审核',approved:'已通过',rejected:'已驳回'} as Record<string,string>)[node.data.status] ?? node.data.status}${node.data.locked ? ' · 已锁定' : ''}${node.data.source === 'manual' ? ' · 人工来源' : ''}）`
        : `${node.data.name}（${MASTERY_TEXT[masteryOfStates(node.states)]}）`,
      x: info.clientX - box.left,
      y: info.clientY - box.top,
    }
  }, 300)
}

function start(): void {
  if (stage.value === null || props.graph === null || !ready.value) return
  drawnOnce.value = false
  // 适配图可能是响应式代理；生命周期会复制一份交给 G6
  lifecycle = createGraphLifecycle(stage.value, {
    data: toRaw(props.graph),
    layout: props.layout,
    positions: props.enhanced && props.positions !== null ? toRaw(props.positions) : null,
    enhance: props.enhanced
      ? {
          obstacles: () => (stage.value !== null && registry !== null ? registry.boxes(stage.value) : { hard: [], soft: [] }),
          minimap: mini.value,
          reduceMotion: () => reduced.value,
          onBlankClick: () => emit('blankClick'),
          onHover: showTip,
        }
      : undefined,
    factory,
    onNodeClick: (kpId) => emit('nodeClick', kpId),
    onStatus: (next) => {
      status.value = next
      if (next === 'ready') drawnOnce.value = true
    },
    onZoom: (value) => {
      zoom.value = Math.round(value * 100) / 100
    },
  })
  if (props.scope !== null) lifecycle.setScope(props.scope)
  if (lastFocus !== null) lifecycle.focus(lastFocus)
}

/** 把视口移到该知识点；画布尚未建好时在首次渲染后执行 */
function focus(kpId: string): void {
  lastFocus = kpId
  lifecycle?.focus(kpId)
}

defineExpose({
  focus,
  /** 把一组知识点（缺省为全部可见节点）整体放进视口（章节跳转、局部视图、适应画布） */
  fitTo: (kpIds?: readonly string[]) => lifecycle?.fitTo(kpIds),
  /** 节点在视口外时才移动镜头（面板里的显式选择） */
  ensureVisible: (kpId: string) => lifecycle?.ensureVisible(kpId),
})

const zoomBy = (ratio: number): void => lifecycle?.zoomBy(ratio)
const fitAll = (): void => lifecycle?.fitTo()
const leaveHover = (): void => lifecycle?.leaveHover()

function stop(): void {
  showTip(null)
  lifecycle?.destroy()
  lifecycle = null
}

function retry(): void {
  stop()
  start()
}

onMounted(() => {
  start()
  // 浮层出现、消失、展开收起时重新排布标签
  stopObstacles = registry?.onChange(() => lifecycle?.relayoutLabels()) ?? null
})

watch(
  () => props.graph,
  (graph) => {
    if (graph === null) return
    if (lifecycle === null) start()
    else lifecycle.update(toRaw(graph))
  },
)

// 布局降级或恢复时重建，等待 DOM 更新后取得增强模式的小地图容器。
watch(() => props.enhanced, retry, { flush: 'post' })

// 位置就绪（章节布局算完）后建图
watch(ready, (now) => {
  if (now && lifecycle === null) start()
})

// 位置在重新计算（换版本）：旧画布对应的是另一张图，先拆掉，等新位置到了由 `ready` 重建；
// 位置从一份换成另一份（没经过 null）同样重建。首次到达（null → 位置）由 `ready` 负责建图，这里不重复建
watch(
  () => props.positions,
  (now, before) => {
    if (!props.enhanced || lifecycle === null) return
    if (now === null) stop()
    else if (before !== null) retry()
  },
)

// 层次布局下切换：普通模式在原图上进行，节点状态（含选中）随数据保留（H05）；增强模式的章节布局是预先算好的位置，重建
watch(
  () => props.layout,
  (layout) => {
    if (props.enhanced) {
      if (lifecycle !== null) retry()
    } else lifecycle?.setLayout(layout)
  },
)

watch(
  () => props.scope,
  (scope) => lifecycle?.setScope(scope),
)

onActivated(() => lifecycle?.refreshSize())
onBeforeUnmount(() => {
  stopObstacles?.()
  stop()
})
</script>

<template>
  <section
    ref="root"
    class="graph-canvas"
    :class="{ 'graph-canvas--enhanced': enhanced }"
    data-test="graph-canvas"
    :data-zoom="zoom ?? undefined"
    :aria-busy="loading ? 'true' : 'false'"
    @pointerleave="leaveHover"
  >
    <div ref="stage" class="graph-canvas__stage" role="img" :aria-label="ariaLabel" />
    <div v-if="status === 'error'" class="graph-canvas__overlay" role="alert">
      <p>图谱渲染失败，请重试。</p>
      <button type="button" @click="retry">重试</button>
    </div>
    <p v-else-if="loading" class="graph-canvas__overlay" role="status">图谱加载中…</p>
    <p v-else-if="empty" class="graph-canvas__overlay" role="status">暂无知识点</p>

    <!-- 小地图与缩放控件：缩略图只画节点，遮罩框是当前视口；装饰性，键盘等价路径是搜索、章节跳转与列表 -->
    <div v-if="enhanced" ref="controls" class="gw-map" role="group" aria-label="地图与缩放">
      <div v-show="miniOpen" ref="mini" class="gw-mini" aria-hidden="true" />
      <div class="gw-map__ctl">
        <button type="button" class="gw-tool" :aria-label="miniOpen ? '收起小地图' : '展开小地图'" :title="audience === 'student' ? (miniOpen ? '收起小地图' : '展开小地图') : undefined" :aria-pressed="miniOpen" @click="miniOpen = !miniOpen">
          <AppIcon name="map" />
        </button>
        <button type="button" class="gw-tool" aria-label="放大" :title="audience === 'student' ? '放大' : undefined" @click="zoomBy(1.25)"><AppIcon name="plus" /></button>
        <button type="button" class="gw-tool" aria-label="缩小" :title="audience === 'student' ? '缩小' : undefined" @click="zoomBy(0.8)"><AppIcon name="minus" /></button>
        <button type="button" class="gw-tool" aria-label="适应画布" :title="audience === 'student' ? '适应画布' : undefined" @click="fitAll"><AppIcon name="fit" /></button>
      </div>
    </div>
    <div v-if="tip" class="gw-tip" role="tooltip" :style="{ left: `${tip.x + 14}px`, top: `${tip.y + 14}px` }">{{ tip.text }}</div>
  </section>
</template>

<style scoped>
.graph-canvas {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 480px;
}

.graph-canvas__stage {
  /* G6 会把容器改为 position: relative，所以尺寸不能靠绝对定位撑开 */
  width: 100%;
  height: 100%;
  min-height: 480px;
  overflow: hidden;
}

.graph-canvas__overlay {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin: 0;
  pointer-events: none;
}

.graph-canvas__overlay button {
  pointer-events: auto;
}

/* 增强模式：画布填满工作区，不再自带最小高度 */
.graph-canvas--enhanced,
.graph-canvas--enhanced .graph-canvas__stage {
  min-height: 0;
}

.gw-map {
  position: absolute;
  z-index: 6;
  right: 16px;
  bottom: 16px;
  display: flex;
  align-items: flex-end;
  gap: 8px;
}
.gw-mini {
  width: 180px;
  height: 120px;
  border: 1px solid var(--gw-edge);
  border-radius: 10px;
  background: var(--gw-panel);
  overflow: hidden;
  box-shadow: 0 1px 2px rgb(29 36 51 / 10%);
}
.gw-map__ctl {
  display: grid;
  gap: 6px;
}
.gw-tip {
  position: absolute;
  z-index: 5;
  max-width: 280px;
  padding: 6px 10px;
  border-radius: var(--ss-radius-sm);
  background: var(--gw-panel);
  color: var(--gw-text);
  border: 1px solid var(--gw-line);
  font-size: 12px;
  line-height: 18px;
  box-shadow: var(--ss-shadow-pop-light);
  pointer-events: none;
  animation: gw-tip-in 120ms var(--ss-ease);
}
@keyframes gw-tip-in {
  from {
    opacity: 0;
    transform: translateY(2px);
  }
  to {
    opacity: 1;
    transform: none;
  }
}
@media (prefers-reduced-motion: reduce) {
  .gw-tip {
    animation-duration: 1ms;
  }
}
</style>
