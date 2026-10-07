import { computed, ref, type ComputedRef, type Ref } from 'vue'

/**
 * 预览 / 详情状态机（规格 §7）。
 *
 * - 画布单击一个节点：进入**预览**（高亮 + 预览卡），侧栏不变；
 * - 再次单击同一节点（或已打开详情的那个节点）：打开详情；
 * - 详情已打开时单击另一个节点：只预览新节点，侧栏保持当前详情，直到再次单击；
 * - 点空白处 / Esc / 预览卡 ✕：取消预览，详情不受影响；
 * - 面板、列表、推荐、关联知识里的选择与问答链接是显式选择，直接打开详情。
 */
export interface PreviewFocus {
  /** 画布上处于预览状态的知识点 */
  previewId: Ref<string | null>
  /** 画布上高亮的知识点：预览中的优先，否则是已打开详情的 */
  highlightId: ComputedRef<string | null>
  /** 画布单击 */
  onNodeClick(kpId: string): void
  /** 进入预览（搜索回车） */
  preview(kpId: string): void
  /** 打开详情（预览卡「查看详情」、面板里的显式选择） */
  open(kpId: string | null): void
  clearPreview(): void
}

export function usePreviewFocus(options: { selected: Ref<string | null>; select: (kpId: string | null) => void }): PreviewFocus {
  const previewId = ref<string | null>(null)
  const highlightId = computed(() => previewId.value ?? options.selected.value)

  function open(kpId: string | null): void {
    previewId.value = null
    options.select(kpId)
  }

  return {
    previewId,
    highlightId,
    onNodeClick(kpId) {
      if (previewId.value === kpId || options.selected.value === kpId) open(kpId)
      else previewId.value = kpId
    },
    preview(kpId) {
      previewId.value = kpId
    },
    open,
    clearPreview() {
      previewId.value = null
    },
  }
}
