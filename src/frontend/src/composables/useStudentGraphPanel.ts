import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch, type Ref } from 'vue'
import type GraphSidePanel from '../components/GraphSidePanel.vue'
import { readPanelWidth, writePanelWidth } from './usePanelWidthPreference'

interface StudentGraphPanelOptions {
  selected: Readonly<Ref<string | null>>
  previewId: Readonly<Ref<string | null>>
  focus: { clearPreview(): void }
}

/** Workspace measurements, divider controls, drawer visibility and focus cleanup. */
export function useStudentGraphPanel({ selected, previewId, focus }: StudentGraphPanelOptions) {
  // ---------------------------------------------------------------- 面板：按容器宽度判断并置/覆盖
  const ws = ref<HTMLElement | null>(null)
  const panel = ref<InstanceType<typeof GraphSidePanel> | null>(null)
  const panelToggle = ref<HTMLButtonElement | null>(null)
  const wsWidth = ref(0)
  /** 可调并置面板；窄屏仍使用覆盖抽屉。 */
  const docked = computed(() => wsWidth.value >= 960)
  // 宽度记在本浏览器（UI-GRAPH-FIND-01）；存储不可用时按默认 25%
  const preferredPanelWidth = ref(readPanelWidth('student-graph') ?? 25)
  const minPanelWidth = computed(() => Math.max(20, 280 / Math.max(wsWidth.value, 1) * 100))
  const maxPanelWidth = computed(() => Math.min(45, (wsWidth.value - 640) / Math.max(wsWidth.value, 1) * 100))
  const panelWidth = computed(() => Math.min(maxPanelWidth.value, Math.max(minPanelWidth.value, preferredPanelWidth.value)))
  const resizingPanel = ref(false)
  function setPanelWidth(value: number): void {
    preferredPanelWidth.value = Math.min(maxPanelWidth.value, Math.max(minPanelWidth.value, value))
    writePanelWidth('student-graph', preferredPanelWidth.value)
  }
  function moveDivider(event: PointerEvent): void {
    if (!resizingPanel.value || ws.value === null) return
    const rect = ws.value.getBoundingClientRect()
    if (rect.width > 0) setPanelWidth((event.clientX - rect.left) / rect.width * 100)
  }
  function startDivider(event: PointerEvent): void {
    if (event.button !== 0) return
    event.preventDefault()
    resizingPanel.value = true
    const handle = event.currentTarget as HTMLElement
    handle.focus()
    handle.setPointerCapture(event.pointerId)
  }
  function endDivider(event: PointerEvent): void {
    resizingPanel.value = false
    const handle = event.currentTarget as HTMLElement
    if (handle.hasPointerCapture(event.pointerId)) handle.releasePointerCapture(event.pointerId)
  }
  function keyDivider(event: KeyboardEvent): void {
    const values: Record<string, number> = {
      ArrowLeft: panelWidth.value - 2, ArrowRight: panelWidth.value + 2,
      Home: minPanelWidth.value, End: maxPanelWidth.value,
    }
    const value = values[event.key]
    if (value === undefined) return
    event.preventDefault()
    setPanelWidth(value)
  }
  const dockedOpen = ref(true)
  const overlayOpen = ref(false)
  const panelVisible = computed(() => (docked.value ? dockedOpen.value : overlayOpen.value))
  let observer: ResizeObserver | null = null
  const measureWorkspace = (): void => {
    wsWidth.value = ws.value?.clientWidth ?? 0
  }

  function openPanel(): void {
    if (docked.value) dockedOpen.value = true
    else overlayOpen.value = true
    void nextTick(() => panel.value?.el?.querySelector<HTMLElement>('[data-focus-start]')?.focus())
  }
  function closePanel(): void {
    if (docked.value) dockedOpen.value = false
    else overlayOpen.value = false
    void nextTick(() => panelToggle.value?.focus())
  }
  // 覆盖模式下选中知识点时抽屉同时打开；并置模式下面板本来就在
  watch(selected, (now) => {
    if (now !== null && !docked.value) overlayOpen.value = true
  })
  watch(docked, (now) => {
    if (now) overlayOpen.value = false
  })
  // Esc 依次关闭：章节菜单（菜单自己处理）→ 覆盖抽屉 → 预览
  function onKey(event: KeyboardEvent): void {
    if (event.key !== 'Escape') return
    if (!docked.value && overlayOpen.value) closePanel()
    else if (previewId.value !== null) focus.clearPreview()
  }
  onMounted(() => {
    window.addEventListener('keydown', onKey)
    if (ws.value !== null) {
      // 首帧先同步量一次：避免第一次渲染按「0 宽」判成覆盖模式，后台标签页也不依赖观察器回调
      wsWidth.value = ws.value.clientWidth
      if (typeof ResizeObserver === 'function') {
        observer = new ResizeObserver(measureWorkspace)
        observer.observe(ws.value)
      } else window.addEventListener('resize', measureWorkspace)
    }
  })
  onBeforeUnmount(() => {
    window.removeEventListener('keydown', onKey)
    window.removeEventListener('resize', measureWorkspace)
    observer?.disconnect()
  })

  return {
    ws, panel, panelToggle, docked, minPanelWidth, maxPanelWidth, panelWidth,
    resizingPanel, setPanelWidth, moveDivider, startDivider, endDivider, keyDivider,
    dockedOpen, overlayOpen, panelVisible, openPanel, closePanel,
  }
}
