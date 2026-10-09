import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import NodeTypeLegend from '../../src/frontend/src/components/NodeTypeLegend.vue'

const counts = { concept: 55, theorem: 1, formula: 4, method: 3, example: 1 }

describe('节点类型图例（教师图谱页）', () => {
  it('列出五类知识点：名称、个数、单字标记，按钮带可访问名称', () => {
    const wrapper = mount(NodeTypeLegend, { props: { counts, hidden: [] } })
    const items = wrapper.findAll('.node-legend__item')
    expect(items.map((i) => i.text())).toEqual(['概 概念55', '理 定理1', '式 公式4', '法 方法3', '例 例题1'])
    expect(wrapper.get('[data-test="node-legend-concept"]').attributes('aria-label')).toBe('概念，55 个：显示中，点击隐藏')
    expect(wrapper.find('[data-test="node-legend-restore"]').exists()).toBe(false)
  })

  it('点击某一类发出 toggle；已隐藏的类型显示“已隐藏”状态与恢复入口', async () => {
    const wrapper = mount(NodeTypeLegend, { props: { counts, hidden: ['theorem'] } })
    await wrapper.get('[data-test="node-legend-method"]').trigger('click')
    expect(wrapper.emitted('toggle')).toEqual([['method']])
    const hidden = wrapper.get('[data-test="node-legend-theorem"]')
    expect(hidden.attributes('aria-pressed')).toBe('false')
    expect(hidden.attributes('aria-label')).toBe('定理，1 个：已隐藏，点击显示')
    await wrapper.get('[data-test="node-legend-restore"]').trigger('click')
    expect(wrapper.emitted('restore')).toHaveLength(1)
  })
})
