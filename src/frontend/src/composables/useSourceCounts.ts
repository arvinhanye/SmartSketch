import { onScopeDispose, shallowRef, toValue, watch, type MaybeRefOrGetter } from 'vue'
import type { KnowledgeDetailApi } from '../api/knowledgeDetail'

/**
 * 知识点来源数量的按需读取（DEDUP-FIX F2）。
 *
 * 草稿图谱接口的节点不带 `source_refs`，所以“这个知识点有几处来源”只能问详情接口。这里只在调用方要求时读
 * （审核页展开一对疑似重复时读这两个），不预取。
 * - 按「课程 + 知识点 + 修订号」缓存：同一修订重复展开不再请求；修订号变了（被编辑、被合并进别的知识点）自然失效；
 * - 区分读取中、读取失败和真实的数量（含 0）：失败不冒充 0；
 * - 换课程或卸载时作废在途请求并清空，迟到的响应不会写进别的课程。
 */
export type SourceCount = { state: 'loading' } | { state: 'ready'; count: number } | { state: 'error' }

export interface SourceTarget {
  id: string
  /** 草稿图里的修订号；读不到草稿图时传 0 */
  revision: number
}

export interface UseSourceCounts {
  /** 该修订的来源数量状态；还没要求读取时为 undefined */
  of(target: SourceTarget): SourceCount | undefined
  /** 读取尚未读过（或上次失败）的；已有结果或正在读的不重复请求 */
  ensure(targets: readonly SourceTarget[]): void
  /** 丢弃这些知识点的全部缓存（合并成功后调用） */
  invalidate(ids: readonly string[]): void
}

export function useSourceCounts(options: { api: KnowledgeDetailApi | null; courseId: MaybeRefOrGetter<string | null> }): UseSourceCounts {
  const cache = shallowRef<ReadonlyMap<string, SourceCount>>(new Map())
  let generation = 0
  let controller = new AbortController()

  const keyOf = (target: SourceTarget) => `${target.id}@${target.revision}`
  function put(key: string, value: SourceCount | null): void {
    const next = new Map(cache.value)
    if (value === null) next.delete(key)
    else next.set(key, value)
    cache.value = next
  }
  function reset(): void {
    generation += 1
    controller.abort()
    controller = new AbortController()
    cache.value = new Map()
  }

  async function read(cid: string, target: SourceTarget): Promise<void> {
    const key = keyOf(target)
    const token = generation
    put(key, { state: 'loading' })
    try {
      const detail = await options.api!.get(cid, target.id, { signal: controller.signal })
      if (token !== generation) return
      const refs = (detail as { source_refs?: unknown }).source_refs
      put(key, Array.isArray(refs) ? { state: 'ready', count: refs.length } : { state: 'error' })
    } catch {
      if (token !== generation) return
      put(key, { state: 'error' })
    }
  }

  watch(() => toValue(options.courseId), reset)
  onScopeDispose(reset)

  return {
    of: (target) => cache.value.get(keyOf(target)),
    ensure(targets) {
      const cid = toValue(options.courseId)
      if (options.api === null || cid === null) return
      for (const target of targets) {
        const existing = cache.value.get(keyOf(target))
        if (existing === undefined || existing.state === 'error') void read(cid, target)
      }
    },
    invalidate(ids) {
      const next = new Map(cache.value)
      for (const key of next.keys()) if (ids.some((id) => key.startsWith(`${id}@`))) next.delete(key)
      cache.value = next
    },
  }
}
