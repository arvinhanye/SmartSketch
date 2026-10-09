import { describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { usePreviewFocus } from '../../src/frontend/src/composables/usePreviewFocus'

function setup(initial: string | null = null) {
  const selected = ref<string | null>(initial)
  const select = vi.fn((kpId: string | null) => {
    selected.value = kpId
  })
  return { selected, select, focus: usePreviewFocus({ selected, select }) }
}

describe('usePreviewFocus', () => {
  it('单击节点只进入预览，不打开详情', () => {
    const { focus, select, selected } = setup()
    focus.onNodeClick('a')
    expect(focus.previewId.value).toBe('a')
    expect(focus.highlightId.value).toBe('a')
    expect(select).not.toHaveBeenCalled()
    expect(selected.value).toBeNull()
  })
  it('再次单击同一节点才打开详情，并结束预览', () => {
    const { focus, select, selected } = setup()
    focus.onNodeClick('a')
    focus.onNodeClick('a')
    expect(select).toHaveBeenCalledWith('a')
    expect(selected.value).toBe('a')
    expect(focus.previewId.value).toBeNull()
    expect(focus.highlightId.value).toBe('a')
  })
  it('详情已打开时单击另一个节点：只预览新节点，详情保持不变', () => {
    const { focus, select, selected } = setup('a')
    focus.onNodeClick('b')
    expect(focus.previewId.value).toBe('b')
    expect(focus.highlightId.value).toBe('b')
    expect(selected.value).toBe('a')
    expect(select).not.toHaveBeenCalled()
    focus.onNodeClick('b')
    expect(selected.value).toBe('b')
  })
  it('单击已打开详情的节点：保持打开，不进入预览', () => {
    const { focus, selected } = setup('a')
    focus.onNodeClick('a')
    expect(selected.value).toBe('a')
    expect(focus.previewId.value).toBeNull()
  })
  it('取消预览后回到详情节点的高亮；详情不受影响', () => {
    const { focus, selected } = setup('a')
    focus.onNodeClick('b')
    focus.clearPreview()
    expect(focus.highlightId.value).toBe('a')
    expect(selected.value).toBe('a')
  })
  it('搜索回车进入预览（不是直接打开详情）', () => {
    const { focus, select } = setup()
    focus.preview('c')
    expect(focus.previewId.value).toBe('c')
    expect(select).not.toHaveBeenCalled()
  })
  it('面板、列表、推荐里的显式选择直接打开详情；传 null 返回课程说明', () => {
    const { focus, selected } = setup()
    focus.preview('c')
    focus.open('d')
    expect(selected.value).toBe('d')
    expect(focus.previewId.value).toBeNull()
    focus.open(null)
    expect(selected.value).toBeNull()
  })
})
