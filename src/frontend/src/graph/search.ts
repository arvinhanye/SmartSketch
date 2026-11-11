/**
 * 知识点查找（UI-GRAPH-FIND-01）。纯函数，不依赖 G6 与 Vue，不修改输入。
 *
 * 匹配名称与别名；规范化：忽略大小写、全半角与首尾空白。
 * 排序：名称完全一致 > 名称以关键字开头 > 名称包含 > 别名完全一致 > 别名包含；同级保持输入顺序。
 */
export interface Searchable {
  kpId: string
  name: string
  aliases?: readonly string[]
}

export interface SearchHit {
  kpId: string
  name: string
  /** 经别名命中时是那个别名；按名称命中为 null */
  alias: string | null
}

export function normalizeQuery(text: string): string {
  return text.normalize('NFKC').toLowerCase().trim()
}

function rankOf(item: Searchable, wanted: string): { rank: number; alias: string | null } | null {
  const name = normalizeQuery(item.name)
  if (name === wanted) return { rank: 0, alias: null }
  if (name.startsWith(wanted)) return { rank: 1, alias: null }
  if (name.includes(wanted)) return { rank: 2, alias: null }
  let best: { rank: number; alias: string } | null = null
  for (const alias of item.aliases ?? []) {
    const text = normalizeQuery(alias)
    const rank = text === wanted ? 3 : text.includes(wanted) ? 4 : null
    if (rank !== null && (best === null || rank < best.rank)) best = { rank, alias }
  }
  return best
}

/** 关键字为空（或只有空白）时返回空数组 */
export function searchNodes(items: readonly Searchable[], query: string): SearchHit[] {
  const wanted = normalizeQuery(query)
  if (wanted === '') return []
  const ranked: Array<{ hit: SearchHit; rank: number; index: number }> = []
  items.forEach((item, index) => {
    const found = rankOf(item, wanted)
    if (found !== null) ranked.push({ hit: { kpId: item.kpId, name: item.name, alias: found.alias }, rank: found.rank, index })
  })
  return ranked.sort((a, b) => a.rank - b.rank || a.index - b.index).map((entry) => entry.hit)
}
