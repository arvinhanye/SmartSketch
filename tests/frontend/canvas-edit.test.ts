import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { computed, effectScope, ref } from 'vue'
import CanvasEditLayer from '../../src/frontend/src/components/canvas/CanvasEditLayer.vue'
import { HOVER_LINGER_MS, UNDO_MS, useCanvasEditing } from '../../src/frontend/src/composables/useCanvasEditing'
import type { RelationEditor } from '../../src/frontend/src/composables/useRelationEditor'
import type { NodeAnchor } from '../../src/frontend/src/graph/hitTest'
import { createGraphLifecycle, type GraphCanvasData } from '../../src/frontend/src/graph/lifecycle'
import { FakeEnhancedGraph } from './fakeEnhancedGraph'

/**
 * UI-GRAPH-EDIT-02：画布上的直接操作——状态逻辑（useCanvasEditing）、浮层组件（CanvasEditLayer）与画布事件接线。
 * 教师页整页流程在 h14.test.ts；纯函数在 graph-direct-edit.test.ts。
 */
const NODES = [{ id: 'a', name: '甲' }, { id: 'b', name: '乙' }, { id: 'c', name: '丙' }]
const ANCHORS: NodeAnchor[] = [
  { kpId: 'a', x: 100, y: 100, r: 18 },
  { kpId: 'b', x: 300, y: 100, r: 18 },
  { kpId: 'c', x: 300, y: 300, r: 18 },
]
type Edge = { id: string; type: string; from_id: string; to_id: string; status: string }

function stub(edges: Edge[] = [{ id: 'r1', type: 'PREREQUISITE', from_id: 'a', to_id: 'b', status: 'approved' }, { id: 'r2', type: 'RELATED_TO', from_id: 'b', to_id: 'c', status: 'approved' }, { id: 'pending:1', type: 'CONTAINS', from_id: 'a', to_id: 'c', status: 'draft' }]) {
  const list = ref(edges)
  const saving = ref(false)
  const name = (id: string) => NODES.find((n) => n.id === id)?.name ?? id
  const labels: Record<string, string> = { PREREQUISITE: '前置', CONTAINS: '包含', RELATED_TO: '相关', EXAMPLE_OF: '应用实例' }
  const relations = {
    saving,
    error: ref<string | null>(null),
    conflict: ref(null),
    graph: computed(() => ({ edges: list.value, nodes: NODES })),
    nodeOptions: ref(NODES),
    describeRelation: (id: string) => {
      const e = list.value.find((x) => x.id === id)
      return e === undefined ? null : { id: e.id, type: e.type, typeLabel: labels[e.type], fromId: e.from_id, fromName: name(e.from_id), toId: e.to_id, toName: name(e.to_id), reversible: e.type !== 'RELATED_TO', pending: e.id.startsWith('pending:'), highlighted: false, downgraded: false }
    },
    changeType: vi.fn(async () => true),
    reverseRelation: vi.fn(async () => true),
    deleteRelation: vi.fn(async (id: string) => {
      list.value = list.value.filter((e) => e.id !== id)
      return true
    }),
    createBetween: vi.fn(async () => true),
    dismissConflict: vi.fn(),
  }
  return { relations: relations as unknown as RelationEditor, raw: relations, saving }
}

function setup(edges?: Edge[]) {
  const s = stub(edges)
  const handlers = { onDetail: vi.fn(), onEdit: vi.fn(), onDelete: vi.fn() }
  const scope = effectScope()
  const editing = scope.run(() => useCanvasEditing({ relations: s.relations, anchors: () => ANCHORS, ...handlers }))!
  return { editing, ...s, handlers, scope }
}

beforeEach(() => vi.useFakeTimers())
afterEach(() => {
  vi.useRealTimers()
  document.body.innerHTML = ''
})

// ---------------------------------------------------------------- 状态逻辑

describe('useCanvasEditing：关系线', () => {
  it('点击关系线打开工具条；保存中的临时线、不存在的线不打开', () => {
    const { editing } = setup()
    editing.openEdge({ relationId: 'pending:1', x: 10, y: 10 })
    editing.openEdge({ relationId: 'nope', x: 10, y: 10 })
    expect(editing.edgeTool.value).toBe(null)
    editing.openEdge({ relationId: 'r1', x: 200, y: 90 })
    expect(editing.edgeTool.value).toEqual({ relationId: 'r1', at: { x: 200, y: 90 } })
    expect(editing.edgeRow.value).toMatchObject({ fromName: '甲', toName: '乙', typeLabel: '前置', reversible: true })
  })

  it('改类型、反转各调一次对应方法；有请求在途时不调', async () => {
    const { editing, raw, saving } = setup()
    editing.openEdge({ relationId: 'r1', x: 0, y: 0 })
    await editing.changeEdgeType('CONTAINS')
    await editing.reverseEdge()
    expect(raw.changeType).toHaveBeenCalledWith('r1', 'CONTAINS')
    expect(raw.reverseRelation).toHaveBeenCalledWith('r1')
    saving.value = true
    await editing.changeEdgeType('RELATED_TO')
    await editing.reverseEdge()
    await editing.deleteEdge()
    expect(raw.changeType).toHaveBeenCalledTimes(1)
    expect(raw.reverseRelation).toHaveBeenCalledTimes(1)
    expect(raw.deleteRelation).not.toHaveBeenCalled()
  })

  it('删除不确认，成功后给可撤销提示，到时自动消失；撤销按原类型和端点重新建一条', async () => {
    const { editing, raw } = setup()
    editing.openEdge({ relationId: 'r1', x: 0, y: 0 })
    await editing.deleteEdge()
    expect(raw.deleteRelation).toHaveBeenCalledWith('r1')
    expect(editing.edgeTool.value).toBe(null)
    expect(editing.undo.value?.text).toBe('已删除关系：甲 → 乙（前置）')
    await editing.undoDelete()
    expect(raw.createBetween).toHaveBeenCalledWith('a', 'b', 'PREREQUISITE', '已恢复关系：甲 → 乙。')
    expect(editing.undo.value).toBe(null)

    editing.openEdge({ relationId: 'r2', x: 0, y: 0 })
    await editing.deleteEdge()
    expect(editing.undo.value).not.toBe(null)
    vi.advanceTimersByTime(UNDO_MS + 1)
    expect(editing.undo.value).toBe(null)
    await editing.undoDelete()
    expect(raw.createBetween).toHaveBeenCalledTimes(1)
  })

  it('删除失败不出现撤销提示；撤销失败说明关系未恢复', async () => {
    const { editing, raw } = setup()
    raw.deleteRelation.mockResolvedValueOnce(false)
    editing.openEdge({ relationId: 'r1', x: 0, y: 0 })
    await editing.deleteEdge()
    expect(editing.undo.value).toBe(null)

    editing.openEdge({ relationId: 'r1', x: 0, y: 0 })
    await editing.deleteEdge()
    raw.createBetween.mockResolvedValueOnce(false)
    await editing.undoDelete()
    expect(editing.undoError.value).toContain('关系未恢复')
  })
})

describe('useCanvasEditing：悬停工具与节点菜单', () => {
  it('悬停节点出现工具；离开后稍留片刻再消失，指针进入工具则保留', () => {
    const { editing } = setup()
    editing.onNodeHover('b')
    expect(editing.hover.value).toEqual(ANCHORS[1])
    editing.onNodeHover(null)
    vi.advanceTimersByTime(HOVER_LINGER_MS - 50)
    expect(editing.hover.value).not.toBe(null)
    editing.holdHover()
    vi.advanceTimersByTime(HOVER_LINGER_MS * 2)
    expect(editing.hover.value).not.toBe(null)
    editing.releaseHover()
    vi.advanceTimersByTime(HOVER_LINGER_MS + 1)
    expect(editing.hover.value).toBe(null)
  })

  it('菜单四项各回到页面对应的处理；“从这里连线…”进入点选状态', () => {
    const { editing, handlers } = setup()
    for (const [action, handler] of [['detail', handlers.onDetail], ['edit', handlers.onEdit], ['delete', handlers.onDelete]] as const) {
      editing.openMenu({ kpId: 'a', x: 1, y: 2 })
      expect(editing.menu.value).toEqual({ kpId: 'a', at: { x: 1, y: 2 } })
      editing.menuAction(action)
      expect(handler).toHaveBeenCalledWith('a')
      expect(editing.menu.value).toBe(null)
    }
    editing.openMenu({ kpId: 'a', x: 1, y: 2 })
    editing.menuAction('connect')
    expect(editing.connect.value).toEqual({ phase: 'picking', from: 'a' })
    // 连线进行中不再打开菜单、工具条和悬停工具
    editing.openMenu({ kpId: 'b', x: 0, y: 0 })
    editing.openEdge({ relationId: 'r1', x: 0, y: 0 })
    editing.onNodeHover('b')
    expect([editing.menu.value, editing.edgeTool.value, editing.hover.value]).toEqual([null, null, null])
  })
})

describe('useCanvasEditing：连线', () => {
  it('点选：节点点击被连线用掉；点起点自己不算；点到目标后进入类型选择并做成环预判', () => {
    const { editing } = setup()
    expect(editing.consumeNodeClick('b')).toBe(false)
    editing.openMenu({ kpId: 'b', x: 0, y: 0 })
    editing.menuAction('connect')
    expect(editing.consumeNodeClick('b')).toBe(true)
    expect(editing.connect.value?.phase).toBe('picking')
    // 已有 甲 →前置→ 乙：乙 → 甲 再加前置会成环
    expect(editing.consumeNodeClick('a')).toBe(true)
    expect(editing.connect.value).toEqual({ phase: 'choosing', from: 'b', to: 'a', at: { x: 100, y: 100 }, prerequisiteBlocked: true })
  })

  it('拖动：经过目标时标出目标与是否成环；松在目标上进入类型选择，松在空白或起点上取消', () => {
    const { editing } = setup()
    editing.startDrag(ANCHORS[0]!, { x: 118, y: 100 })
    expect(editing.connect.value).toMatchObject({ phase: 'dragging', from: 'a', target: null })
    editing.dragTo({ x: 104, y: 100 })
    expect(editing.connect.value).toMatchObject({ target: null })
    editing.dragTo({ x: 296, y: 296 })
    expect(editing.connect.value).toMatchObject({ target: { kpId: 'c' }, cycle: false })
    editing.endDrag()
    expect(editing.connect.value).toEqual({ phase: 'choosing', from: 'a', to: 'c', at: { x: 300, y: 300 }, prerequisiteBlocked: false })

    editing.dismiss()
    editing.startDrag(ANCHORS[1]!, { x: 300, y: 100 })
    editing.dragTo({ x: 100, y: 102 })
    expect(editing.connect.value).toMatchObject({ target: { kpId: 'a' }, cycle: true })
    editing.dragTo({ x: 200, y: 200 })
    editing.endDrag()
    expect(editing.connect.value).toBe(null)
  })

  it('选定类型才新建；成环时“前置”被拦下而其他类型可以；有请求在途时不发', async () => {
    const { editing, raw, saving } = setup()
    editing.startDrag(ANCHORS[1]!, { x: 300, y: 100 })
    editing.dragTo({ x: 100, y: 100 })
    editing.endDrag()
    await editing.confirmType('PREREQUISITE')
    expect(raw.createBetween).not.toHaveBeenCalled()
    expect(editing.connect.value?.phase).toBe('choosing')
    saving.value = true
    await editing.confirmType('RELATED_TO')
    expect(raw.createBetween).not.toHaveBeenCalled()
    saving.value = false
    await editing.confirmType('RELATED_TO')
    expect(raw.createBetween).toHaveBeenCalledWith('b', 'a', 'RELATED_TO')
    expect(editing.connect.value).toBe(null)
  })

  it('画布移动或点空白：收起工具条、菜单、类型选择；“点选连线”继续等目标；dismiss 全部取消', () => {
    const { editing } = setup()
    editing.openEdge({ relationId: 'r1', x: 0, y: 0 })
    editing.onViewChange()
    expect(editing.edgeTool.value).toBe(null)
    editing.openMenu({ kpId: 'a', x: 0, y: 0 })
    editing.menuAction('connect')
    editing.onViewChange()
    expect(editing.connect.value).toEqual({ phase: 'picking', from: 'a' })
    editing.consumeNodeClick('c')
    editing.onViewChange()
    expect(editing.connect.value).toBe(null)
    editing.openMenu({ kpId: 'a', x: 0, y: 0 })
    editing.menuAction('connect')
    editing.dismiss()
    expect(editing.connect.value).toBe(null)
  })
})

// ---------------------------------------------------------------- 浮层组件

function mountLayer(edges?: Edge[]) {
  const ctx = setup(edges)
  const wrapper = mount(CanvasEditLayer, { attachTo: document.body, props: { editing: ctx.editing, error: null, conflict: null } })
  return { ...ctx, wrapper }
}

describe('CanvasEditLayer', () => {
  it('关系线工具条：类型下拉、反转、删除；“相关”没有反转；请求在途时都不可用', async () => {
    const { wrapper, editing, raw, saving } = mountLayer()
    editing.openEdge({ relationId: 'r1', x: 200, y: 90 })
    await flushPromises()
    expect(wrapper.get('[data-test="ce-edge"]').attributes('aria-label')).toBe('关系：甲 → 乙')
    expect((wrapper.get('[data-test="ce-edge-type"]').element as HTMLSelectElement).value).toBe('PREREQUISITE')
    await wrapper.get('[data-test="ce-edge-type"]').setValue('CONTAINS')
    expect(raw.changeType).toHaveBeenCalledWith('r1', 'CONTAINS')
    await wrapper.get('[data-test="ce-edge-reverse"]').trigger('click')
    expect(raw.reverseRelation).toHaveBeenCalledTimes(1)
    saving.value = true
    await flushPromises()
    expect(wrapper.get('[data-test="ce-edge-delete"]').attributes('disabled')).toBeDefined()
    saving.value = false

    editing.openEdge({ relationId: 'r2', x: 200, y: 90 })
    await flushPromises()
    expect(wrapper.find('[data-test="ce-edge-reverse"]').exists()).toBe(false)
    await wrapper.get('[data-test="ce-edge-delete"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="ce-edge"]').exists()).toBe(false)
    expect(wrapper.get('[data-test="ce-undo"]').text()).toContain('已删除关系：乙 → 丙（相关）')
    await wrapper.get('[data-test="ce-undo-btn"]').trigger('click')
    expect(raw.createBetween).toHaveBeenCalledWith('b', 'c', 'RELATED_TO', expect.any(String))
  })

  it('悬停工具：“⋯”打开菜单；菜单里 ↓ 移动焦点，E 编辑，L 连线，Esc 关闭', async () => {
    const { wrapper, editing, handlers } = mountLayer()
    editing.onNodeHover('a')
    await flushPromises()
    expect(wrapper.find('[data-test="ce-handle"]').exists()).toBe(true)
    await wrapper.get('[data-test="ce-more"]').trigger('click')
    const menu = wrapper.get('[data-test="ce-menu"]')
    expect(menu.attributes('aria-label')).toBe('「甲」的操作')
    expect(wrapper.find('[data-test="ce-more"]').exists()).toBe(false)
    expect(document.activeElement).toBe(wrapper.get('[data-test="ce-menu-detail"]').element)
    await menu.trigger('keydown', { key: 'ArrowDown' })
    expect(document.activeElement).toBe(wrapper.get('[data-test="ce-menu-edit"]').element)
    await menu.trigger('keydown', { key: 'e' })
    expect(handlers.onEdit).toHaveBeenCalledWith('a')

    editing.openMenu({ kpId: 'a', x: 10, y: 10 })
    await flushPromises()
    await wrapper.get('[data-test="ce-menu"]').trigger('keydown', { key: 'L' })
    expect(wrapper.get('[data-test="ce-picking"]').text()).toContain('从「甲」连线')

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', cancelable: true }))
    await flushPromises()
    expect(wrapper.find('[data-test="ce-picking"]').exists()).toBe(false)
  })

  it('从连接柄按下开始拖线，窗口上的移动与松开推进连线；成环的目标有说明且“前置”不可选', async () => {
    const { wrapper, editing, raw } = mountLayer()
    editing.onNodeHover('b')
    await flushPromises()
    wrapper.get('[data-test="ce-handle"]').element.dispatchEvent(new MouseEvent('pointerdown', { button: 0, clientX: 318, clientY: 100, bubbles: true, cancelable: true }))
    await flushPromises()
    expect(wrapper.find('[data-test="ce-drag"]').exists()).toBe(true)
    window.dispatchEvent(new MouseEvent('pointermove', { clientX: 100, clientY: 100 }))
    await flushPromises()
    expect(wrapper.get('[data-test="ce-drag-hint"]').text()).toContain('前置会形成环')
    expect(wrapper.get('[data-test="ce-drag"] circle').classes()).toContain('is-cycle')
    window.dispatchEvent(new MouseEvent('pointerup', { clientX: 100, clientY: 100 }))
    await flushPromises()
    const chooser = wrapper.get('[data-test="ce-chooser"]')
    expect(chooser.text()).toContain('乙 → 甲')
    expect(wrapper.get('[data-test="ce-type-PREREQUISITE"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-test="ce-chooser-cycle"]').text()).toContain('会形成环')
    await wrapper.get('[data-test="ce-type-CONTAINS"]').trigger('click')
    expect(raw.createBetween).toHaveBeenCalledWith('b', 'a', 'CONTAINS')
    expect(wrapper.find('[data-test="ce-chooser"]').exists()).toBe(false)
  })

  it('非左键按下连接柄不开始拖线；错误与环路显示在画布上并可关闭', async () => {
    const { wrapper, editing } = mountLayer()
    editing.onNodeHover('a')
    await flushPromises()
    wrapper.get('[data-test="ce-handle"]').element.dispatchEvent(new MouseEvent('pointerdown', { button: 2, bubbles: true, cancelable: true }))
    await flushPromises()
    expect(wrapper.find('[data-test="ce-drag"]').exists()).toBe(false)

    await wrapper.setProps({ error: null, conflict: ['甲', '乙', '甲'] })
    expect(wrapper.get('[data-test="ce-error"]').text()).toContain('环路：甲 → 乙 → 甲')
    await wrapper.setProps({ error: '无法连接服务器，已撤销本次改动，请检查网络后重试。', conflict: null })
    expect(wrapper.get('[data-test="ce-error"]').text()).toContain('无法连接服务器')
    await wrapper.get('[data-test="ce-error"] button').trigger('click')
    expect(wrapper.emitted('dismissError')).toHaveLength(1)
  })
})

// ---------------------------------------------------------------- 画布事件接线

describe('画布生命周期：关系线点击、节点右键与节点位置', () => {
  const node = (id: string) => ({ id: `kp:${id}`, data: { kpId: id, name: id, type: 'concept', level: 1, chapterId: null, status: 'approved', confidence: 1, source: 'ai', locked: false } })
  const data = { nodes: [node('a'), node('b')], edges: [{ id: 'rel:r1', source: 'kp:a', target: 'kp:b', data: { relationId: 'r1', type: 'PREREQUISITE', directed: true, status: 'approved', confidence: 1, source: 'ai', downgraded: false }, style: { stroke: '#000', lineWidth: 2, lineDash: [], endArrow: true, labelText: '前置' } }] } as unknown as GraphCanvasData

  it('edge:click / node:contextmenu 换成契约 ID 回调；anchors 给出屏幕位置与半径', async () => {
    vi.useRealTimers()
    const onEdgeClick = vi.fn()
    const onNodeMenu = vi.fn()
    const onTransform = vi.fn()
    let fake!: FakeEnhancedGraph
    const container = document.createElement('div')
    Object.defineProperty(container, 'clientWidth', { value: 800 })
    Object.defineProperty(container, 'clientHeight', { value: 600 })
    const lifecycle = createGraphLifecycle(container, {
      data,
      enhance: { onEdgeClick, onNodeMenu, onTransform },
      factory: (init) => (fake = new FakeEnhancedGraph({ 'kp:a': [100, 50], 'kp:b': [300, 200] }, init)),
    })
    await vi.waitFor(() => expect(lifecycle.status).toBe('ready'))

    fake.emit('edge:click', { target: { id: 'rel:r1' }, client: { x: 210, y: 120 } })
    fake.emit('edge:click', { target: { id: 'rel:nope' }, client: { x: 0, y: 0 } })
    expect(onEdgeClick.mock.calls).toEqual([[{ relationId: 'r1', clientX: 210, clientY: 120 }]])
    fake.emit('node:contextmenu', { target: { id: 'kp:b' }, client: { x: 305, y: 198 } })
    expect(onNodeMenu.mock.calls).toEqual([[{ kpId: 'b', clientX: 305, clientY: 198 }]])

    // 回归：只有真正的平移 / 缩放才通知 onTransform；数据更新后的重绘不算
    expect(onTransform).not.toHaveBeenCalled()
    lifecycle.update({ nodes: data.nodes, edges: data.edges.map((e) => ({ ...e, states: ['active'] })) } as GraphCanvasData)
    await vi.waitFor(() => expect(lifecycle.status).toBe('ready'))
    await new Promise((resolve) => setTimeout(resolve, 150))
    expect(onTransform).not.toHaveBeenCalled()
    fake.emit('aftertransform')
    expect(onTransform).toHaveBeenCalledTimes(1)

    const anchors = lifecycle.anchors()
    expect(anchors.map((a) => a.kpId)).toEqual(['a', 'b'])
    const zoom = fake.zoom
    const expected = fake.getViewportByCanvas([100, 50])
    expect([anchors[0]!.x, anchors[0]!.y]).toEqual([expected[0], expected[1]])
    expect(anchors[0]!.r).toBeGreaterThanOrEqual(18 * zoom)
    lifecycle.destroy()
    expect(lifecycle.anchors()).toEqual([])
  })
})
