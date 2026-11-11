/**
 * 焦点是否在搜索框里（UI-GRAPH-FIND-01）。
 *
 * 详情、编辑面板在载入新知识点后通常把焦点移到标题，方便读屏从名称开始播报；
 * 但用户正在搜索框里用回车逐个定位命中时不能抢走焦点，否则无法连续按回车。此时位置由搜索旁的状态文字播报。
 */
export function isSearchFocused(): boolean {
  const active = document.activeElement
  return active instanceof HTMLInputElement && active.type === 'search'
}
