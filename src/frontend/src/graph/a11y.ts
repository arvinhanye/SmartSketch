/**
 * G6 会把每层 canvas 设成 `tabindex="1"`：4 层 canvas 成了页面最先的 4 个 Tab 停靠点，没有名称也没有焦点环。
 * 画布是指针交互层（键盘等价路径是搜索、章节菜单、列表与详情，见 `specs/course-knowledge-graph.md`），
 * 所以把容器里的 canvas 一律移出 Tab 顺序；G6 重建画布或重设属性时同样处理。返回停止函数。
 */
export function keepCanvasOutOfTabOrder(container: HTMLElement): () => void {
  const apply = (): void => {
    for (const canvas of container.querySelectorAll('canvas')) {
      if (canvas.getAttribute('tabindex') !== '-1') canvas.setAttribute('tabindex', '-1')
    }
  }
  apply()
  if (typeof MutationObserver === 'undefined') return () => undefined
  const observer = new MutationObserver(apply)
  observer.observe(container, { childList: true, subtree: true, attributes: true, attributeFilter: ['tabindex'] })
  return () => observer.disconnect()
}
