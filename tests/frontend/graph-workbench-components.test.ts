import { mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import GraphOverlay from '../../src/frontend/src/components/GraphOverlay.vue'
import GraphLegend from '../../src/frontend/src/components/GraphLegend.vue'
import GraphPreviewCard from '../../src/frontend/src/components/GraphPreviewCard.vue'
import LocalViewBar from '../../src/frontend/src/components/LocalViewBar.vue'
import ChapterMenu from '../../src/frontend/src/components/ChapterMenu.vue'
import GraphSidePanel from '../../src/frontend/src/components/GraphSidePanel.vue'
import { GRAPH_OBSTACLES_KEY, type ObstacleRegistry } from '../../src/frontend/src/graph/obstacles'

// Task 14 supplementary RED→GREEN coverage approved by the user on 2026-10-07.
const wrappers: VueWrapper[] = []
function track<T extends VueWrapper>(wrapper: T): T {
  wrappers.push(wrapper)
  return wrapper
}
function obstacles() {
  const off = vi.fn()
  const register = vi.fn(() => off)
  const registry: ObstacleRegistry = { register, boxes: () => ({ hard: [], soft: [] }), onChange: () => () => {} }
  return { off, register, global: { provide: { [GRAPH_OBSTACLES_KEY as symbol]: registry } } }
}
afterEach(() => {
  wrappers.splice(0).forEach((wrapper) => wrapper.unmount())
  document.body.innerHTML = ''
})

const legendProps = {
  open: true,
  hiddenRelations: ['PREREQUISITE'] as const,
  hiddenTypes: ['concept'] as const,
  relationCounts: { CONTAINS: 1, PREREQUISITE: 7, RELATED_TO: 2, EXAMPLE_OF: 3 },
  typeCounts: { concept: 8, theorem: 2, formula: 3, method: 4, example: 5 },
}
const chapters = [
  { id: 'c1', title: '第一章：线性结构', total: 8, done: 3 },
  { id: 'c2', title: '第二章：树', total: 6, done: 1 },
]

describe('工作台浮层与展示组件（任务 14）', () => {
  it('GraphOverlay 默认是硬障碍，保留插槽，卸载注销', () => {
    const registry = obstacles()
    const wrapper = track(mount(GraphOverlay, { global: registry.global, slots: { default: '<button>搜索</button>' } }))
    expect(wrapper.element.tagName).toBe('DIV')
    expect(wrapper.get('button').text()).toBe('搜索')
    expect(registry.register).toHaveBeenCalledWith(wrapper.element, 'hard')
    wrapper.unmount()
    expect(registry.off).toHaveBeenCalledTimes(1)
    wrappers.splice(wrappers.indexOf(wrapper), 1)
  })

  it('GraphOverlay 支持语义容器与软障碍', () => {
    const registry = obstacles()
    const wrapper = track(mount(GraphOverlay, { props: { as: 'section', kind: 'soft' }, global: registry.global }))
    expect(wrapper.element.tagName).toBe('SECTION')
    expect(registry.register).toHaveBeenCalledWith(wrapper.element, 'soft')
  })

  it('图例呈现全图计数、隐藏状态、方向文字并发送筛选与恢复事件', async () => {
    const registry = obstacles()
    const wrapper = track(mount(GraphLegend, { props: legendProps, global: registry.global }))
    expect(registry.register).toHaveBeenCalledWith(wrapper.element, 'soft')
    const relation = wrapper.get('[data-test="legend-rel-PREREQUISITE"]')
    expect(relation.attributes('aria-pressed')).toBe('false')
    expect(relation.attributes('aria-label')).toContain('已隐藏，点击显示')
    expect(relation.get('.gw-legend__count').text()).toBe('7')
    expect(relation.text()).toContain('先学 → 后学')
    const type = wrapper.get('[data-test="legend-type-concept"]')
    expect(type.attributes('aria-pressed')).toBe('false')
    expect(type.attributes('aria-label')).toContain('8 个')
    expect(wrapper.get('[role="status"]').text()).toContain('已隐藏 2 类')
    await relation.trigger('click')
    await type.trigger('click')
    await wrapper.get('[data-test="legend-restore"]').trigger('click')
    expect(wrapper.emitted('toggleRelation')).toEqual([['PREREQUISITE']])
    expect(wrapper.emitted('toggleType')).toEqual([['concept']])
    expect(wrapper.emitted('restore')).toEqual([[]])
    expect(wrapper.get('[aria-label="掌握状态"]').text()).toBe('✓已掌握◐学习中未学习')
  })

  it('图例收起后不呈现筛选项，开关事件携带下一状态', async () => {
    const wrapper = track(mount(GraphLegend, { props: { ...legendProps, open: false } }))
    expect(wrapper.find('[data-test="legend-rel-PREREQUISITE"]').exists()).toBe(false)
    const button = wrapper.get('button')
    expect(button.attributes('aria-expanded')).toBe('false')
    await button.trigger('click')
    expect(wrapper.emitted('update:open')).toEqual([[true]])
  })

  it('预览卡显示名称、类型、章节、掌握与先修/解锁数量；显式按钮分别发事件', async () => {
    const registry = obstacles()
    const wrapper = track(mount(GraphPreviewCard, {
      props: { name: '线性表', type: 'concept', chapter: '第一章', masteryText: '学习中', mastery: 'learning', prerequisites: 2, unlocks: 3, localActive: false },
      global: registry.global,
    }))
    expect(registry.register).toHaveBeenCalledWith(wrapper.element, 'hard')
    expect(wrapper.attributes('aria-label')).toBe('知识点预览')
    expect(wrapper.text()).toContain('概念，第一章')
    expect(wrapper.text()).toContain('线性表')
    expect(wrapper.get('[data-mastery="learning"]').text()).toBe('学习中')
    expect(wrapper.text()).toContain('先修 2 项')
    expect(wrapper.text()).toContain('学完可解锁 3 项')
    const local = wrapper.get('[data-test="gw-preview-local"]')
    expect(local.attributes('aria-pressed')).toBe('false')
    expect(local.text()).toBe('只看相邻')
    await local.trigger('click')
    await wrapper.get('[data-test="gw-preview-open"]').trigger('click')
    await wrapper.get('[data-test="gw-preview-close"]').trigger('click')
    expect(wrapper.emitted('toggleLocal')).toEqual([[]])
    expect(wrapper.emitted('open')).toEqual([[]])
    expect(wrapper.emitted('close')).toEqual([[]])
    await wrapper.setProps({ localActive: true })
    expect(local.attributes('aria-pressed')).toBe('true')
    expect(local.text()).toBe('显示全部')
  })

  it('局部视图条说明隐藏数量，1/2 跳与恢复按钮分别发事件', async () => {
    const registry = obstacles()
    const wrapper = track(mount(LocalViewBar, { props: { name: '线性表', hiddenCount: 12, hops: 1 }, global: registry.global }))
    expect(registry.register).toHaveBeenCalledWith(wrapper.element, 'hard')
    expect(wrapper.attributes('role')).toBe('status')
    expect(wrapper.text()).toContain('只看「线性表」的相邻知识，已隐藏 12 个')
    expect(wrapper.get('[data-test="gw-local-1"]').attributes('aria-pressed')).toBe('true')
    expect(wrapper.get('[data-test="gw-local-2"]').attributes('aria-pressed')).toBe('false')
    await wrapper.get('[data-test="gw-local-2"]').trigger('click')
    await wrapper.get('[data-test="gw-local-1"]').trigger('click')
    await wrapper.get('[data-test="gw-local-restore"]').trigger('click')
    expect(wrapper.emitted('setHops')).toEqual([[2], [1]])
    expect(wrapper.emitted('restore')).toEqual([[]])
  })

  it('章节菜单显示数量与当前章节，跳转后关闭并将焦点回按钮', async () => {
    const wrapper = track(mount(ChapterMenu, { props: { chapters, currentId: 'c1' }, attachTo: document.body }))
    const trigger = wrapper.get('[data-test="gw-chapter-button"]')
    await trigger.trigger('click')
    expect(trigger.attributes('aria-expanded')).toBe('true')
    expect(wrapper.get('[data-test="gw-chapter-c1"]').attributes('aria-current')).toBe('true')
    const target = wrapper.get('[data-test="gw-chapter-c2"]')
    expect(target.text()).toContain('共 6 个，已掌握 1')
    ;(target.element as HTMLButtonElement).focus()
    await target.trigger('click')
    await nextTick()
    expect(wrapper.emitted('jump')).toEqual([['c2']])
    expect(wrapper.find('[aria-label="跳转到章节"]').exists()).toBe(false)
    expect(document.activeElement).toBe(trigger.element)
  })

  it('章节菜单 Esc 关闭并将焦点回按钮', async () => {
    const wrapper = track(mount(ChapterMenu, { props: { chapters, currentId: null }, attachTo: document.body }))
    const trigger = wrapper.get('[data-test="gw-chapter-button"]')
    await trigger.trigger('click')
    const item = wrapper.get('[data-test="gw-chapter-c1"]')
    ;(item.element as HTMLButtonElement).focus()
    await item.trigger('keydown', { key: 'Escape' })
    await nextTick()
    expect(trigger.attributes('aria-expanded')).toBe('false')
    expect(document.activeElement).toBe(trigger.element)
  })

  it('章节菜单点菜单外关闭并将焦点回按钮（计划 Task 14 接口约定）', async () => {
    const wrapper = track(mount(ChapterMenu, { props: { chapters, currentId: null }, attachTo: document.body }))
    const trigger = wrapper.get('[data-test="gw-chapter-button"]')
    await trigger.trigger('click')
    ;(wrapper.get('[data-test="gw-chapter-c1"]').element as HTMLButtonElement).focus()
    document.body.dispatchEvent(new Event('pointerdown', { bubbles: true }))
    await nextTick()
    expect(trigger.attributes('aria-expanded')).toBe('false')
    expect(document.activeElement).toBe(trigger.element)
  })

  it('章节菜单禁用时按钮不可操作', () => {
    const wrapper = track(mount(ChapterMenu, { props: { chapters, currentId: null, disabled: true } }))
    expect(wrapper.get('[data-test="gw-chapter-button"]').attributes('disabled')).toBeDefined()
  })

  it('侧面板关闭时 inert，打开移除；并置/抽屉角色、详情标签、插槽与事件保留', async () => {
    const wrapper = track(mount(GraphSidePanel, {
      props: { open: false, docked: true, detail: false, label: '知识点详情：线性表', contentKey: 'course' },
      slots: { default: '<button data-test="business-hook">业务内容</button>' },
    }))
    expect(wrapper.attributes('inert')).toBeDefined()
    expect(wrapper.attributes('role')).toBe('complementary')
    expect(wrapper.attributes('aria-label')).toBe('课程说明')
    expect(wrapper.get('[data-test="business-hook"]').text()).toBe('业务内容')
    await wrapper.setProps({ open: true, docked: false, detail: true, contentKey: 'kp:a' })
    expect(wrapper.attributes('inert')).toBeUndefined()
    expect(wrapper.attributes('role')).toBe('dialog')
    expect(wrapper.attributes('aria-label')).toBe('知识点详情：线性表')
    await wrapper.get('[data-test="gw-back"]').trigger('click')
    await wrapper.get('[data-test="gw-panel-close"]').trigger('click')
    expect(wrapper.emitted('back')).toEqual([[]])
    expect(wrapper.emitted('close')).toEqual([[]])
  })
})
