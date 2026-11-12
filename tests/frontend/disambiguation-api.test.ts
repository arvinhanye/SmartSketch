import { describe, expect, it, vi } from 'vitest'
import { createDisambiguationApi } from '../../src/frontend/src/api/disambiguation'
import type { HttpClient } from '../../src/frontend/src/api/http'
import { DUPLICATE_REASON_LABELS, isQueue } from '../../src/frontend/src/composables/useReview'

describe('消歧接口与既有审核页兼容', () => {
  it('四个入口传递课程、计划、组、修订号及取消信号', async () => {
    const request = vi.fn().mockResolvedValue({})
    const api = createDisambiguationApi({ request } as unknown as HttpClient)
    const signal = new AbortController().signal
    await api.getCoverage('c', { signal })
    await api.listMerges('c', { cursor: 'cursor', limit: 2 }, { signal })
    await api.previewUndo('c', 'p', 'g', 7, { signal })
    await api.undo('c', 'p', 'g', 7, { signal })
    expect(request.mock.calls).toEqual([
      ['get', '/api/v1/courses/{cid}/review/disambiguation', { params: { cid: 'c' }, signal }],
      ['get', '/api/v1/courses/{cid}/review/merges', { params: { cid: 'c' }, query: { cursor: 'cursor', limit: 2 }, signal }],
      ['post', '/api/v1/courses/{cid}/review/merges/{plan_id}/{group_id}/undo-preview', { params: { cid: 'c', plan_id: 'p', group_id: 'g' }, body: { expected_revision: 7 }, signal }],
      ['post', '/api/v1/courses/{cid}/review/merges/{plan_id}/{group_id}/undo', { params: { cid: 'c', plan_id: 'p', group_id: 'g' }, body: { expected_revision: 7 }, signal }],
    ])
  })

  it('冲突原样交给调用方，不把请求完成当成撤销成功', async () => {
    const conflict = new Error('REVISION_CONFLICT')
    const api = createDisambiguationApi({ request: vi.fn().mockRejectedValue(conflict) } as unknown as HttpClient)
    await expect(api.undo('c', 'p', 'g', 1)).rejects.toBe(conflict)
  })

  it('现有队列校验接受新增语义候选，原因有中文标签', () => {
    const counts = { low_confidence_relations: 0, suspected_duplicates: 1, isolated_nodes: 0 }
    expect(isQueue({ low_confidence_relations: [], isolated_nodes: [], totals: counts,
      next_cursors: { low_confidence_relations: null, suspected_duplicates: null, isolated_nodes: null },
      suspected_duplicates: [{ candidates: [{ id: 'a', name: '哈希表' }, { id: 'b', name: '散列表' }], similarity: 0, reason: 'semantic_uncertain' }],
      disambiguation: { status: 'partial' },
    })).toBe(true)
    expect(DUPLICATE_REASON_LABELS.semantic_uncertain).toBe('同义关系仍需确认')
    expect(DUPLICATE_REASON_LABELS.merge_blocked).toBe('同义提案未通过自动合并约束')
  })
})
