import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import AppIcon from '../../src/frontend/src/components/AppIcon.vue'
import { DESTINATION_ICONS } from '../../src/frontend/src/components/navIcons'

describe('入口图标：一个去向一个图标，不同去向不共用', () => {
  it('所有去向的图标互不相同', () => {
    const icons = Object.values(DESTINATION_ICONS)
    expect(new Set(icons).size).toBe(icons.length)
  })

  it('每个去向的图标都真实存在（AppIcon 会为未知名称渲染空图）', () => {
    for (const name of Object.values(DESTINATION_ICONS)) {
      const html = mount(AppIcon, { props: { name } }).html()
      expect(html, name).toMatch(/<(path|circle|rect)/)
    }
  })

  it('课程概览的入口卡与左侧导航用同一套映射：资料≠课程列表、成员≠概览', () => {
    expect(DESTINATION_ICONS.materials).not.toBe(DESTINATION_ICONS.course)
    expect(DESTINATION_ICONS.members).not.toBe(DESTINATION_ICONS.overview)
  })
})
