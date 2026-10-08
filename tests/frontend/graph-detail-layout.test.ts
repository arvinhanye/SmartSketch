import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { describe, expect, it } from 'vitest'
import KnowledgeDetail from '../../src/frontend/src/components/KnowledgeDetail.vue'
import { KNOWLEDGE_DETAIL_API_KEY } from '../../src/frontend/src/api/knowledgeDetail'
import { useCourseStore } from '../../src/frontend/src/stores/course'

// CSS policy checks complement real-browser geometry acceptance: jsdom does not lay out.
const css = readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), '../../src/frontend/src/styles/graph-workspace.css'), 'utf8')
function rule(selector: string): string {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return [...css.matchAll(new RegExp(`(?:^|\\n)${escaped}\\s*\\{([^}]+)\\}`, 'g'))].map((m) => m[1]).join('\n')
}
function makeDetail(showClose?: boolean) {
  const pinia = createPinia()
  setActivePinia(pinia)
  useCourseStore(pinia).selectCourse('c1')
  return mount(KnowledgeDetail, {
    props: { kpId: null, ...(showClose === undefined ? {} : { showClose }) },
    global: { plugins: [pinia], provide: { [KNOWLEDGE_DETAIL_API_KEY as symbol]: { get: async () => { throw new Error('empty detail must not fetch') } } } },
  })
}

describe('详情关闭入口按使用场景保留', () => {
  it('教师等既有调用默认保留关闭按钮和 Esc 事件', async () => {
    const wrapper = makeDetail()
    await wrapper.get('[data-test="kd-close"]').trigger('click')
    await wrapper.trigger('keydown', { key: 'Escape' })
    expect(wrapper.emitted('close')).toEqual([[], []])
    wrapper.unmount()
  })
  it('学生工作台可移除关闭叉；Esc 留给工作台抽屉/预览处理', async () => {
    const wrapper = makeDetail(false)
    await flushPromises()
    expect(wrapper.find('[data-test="kd-close"]').exists()).toBe(false)
    await wrapper.trigger('keydown', { key: 'Escape' })
    expect(wrapper.emitted('close')).toBeUndefined()
    wrapper.unmount()
  })
})

describe('用户确认的自适应详情布局规则', () => {
  it('并置面板按工作区比例分配（默认 25%，由拖动/键盘分隔条写入 --gw-panel-width），而非固定 320px', () => {
    expect(rule('.graph-workspace.gw')).toMatch(/grid-template-columns:\s*var\(--gw-panel-width,\s*25%\)\s+minmax\(0,\s*1fr\)/)
    expect(rule('.graph-workspace .gw-divider')).toMatch(/left:\s*calc\(var\(--gw-panel-width,\s*25%\)\s*-\s*5px\)/)
  })
  it('窄屏打开的覆盖面板占工作区 90%，参与页面高度计算', () => {
    expect(rule('.graph-workspace.gw.is-overlay .gw-panel')).toMatch(/width:\s*90%/)
    expect(rule('.graph-workspace.gw.is-overlay .gw-panel.is-open')).toMatch(/position:\s*relative/)
  })
  it('面板内容不再使用内部滚动容器，也不以 hidden 截断', () => {
    expect(rule('.graph-workspace .gw-panel__scroll')).toMatch(/overflow:\s*visible/)
    expect(rule('.graph-workspace .gw-panel')).toMatch(/overflow:\s*visible/)
  })
  it('详情覆盖规则高于组件 scoped 样式，清除重复内边距和内部滚动', () => {
    const body = rule('.graph-workspace aside.knowledge-detail')
    expect(body).toMatch(/padding:\s*0(?:px)?\s*;/)
    expect(body).toMatch(/overflow:\s*visible/)
    expect(body).toMatch(/min-width:\s*0/)
  })
  it('掌握按钮列和业务容器允许缩窄，文本可换行', () => {
    expect(rule('.graph-workspace .gw-seg')).toMatch(/repeat\(3,\s*minmax\(0,\s*1fr\)\)/)
    expect(rule('.graph-workspace .gw-seg button')).toMatch(/min-width:\s*0/)
    expect(rule('.graph-workspace .gw-seg button')).toMatch(/overflow-wrap:\s*anywhere/)
  })
  it('窄屏业务网格的列下限为零，不被长推荐和三个掌握按钮撑宽', () => {
    expect(rule('.graph-workspace .student-graph__learning, .graph-workspace .student-graph__mastery')).toMatch(/grid-template-columns:\s*minmax\(0,\s*1fr\)/)
  })
  it('并置面板收起后移出布局，隐藏的长详情不撑高页面', () => {
    expect(rule('.graph-workspace.gw.is-collapsed .gw-panel')).toMatch(/display:\s*none/)
    expect(rule('.graph-workspace.gw.is-collapsed')).toMatch(/grid-template-columns:\s*minmax\(0,\s*1fr\)\s*;/)
  })
  it('长内容撑开页面；画布保留视口高度，不由侧栏滚动或裁切', () => {
    const app = rule('.app--graph')
    expect(app).toMatch(/height:\s*auto/)
    expect(app).toMatch(/overflow:\s*visible/)
    expect(rule('.graph-workspace .gw-stage')).toMatch(/position:\s*sticky/)
    expect(rule('.app--graph .student-graph > .graph-workspace')).toMatch(/height:\s*auto/)
  })
})
