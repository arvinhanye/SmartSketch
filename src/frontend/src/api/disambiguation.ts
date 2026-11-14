import type { components } from '../../../contracts/v1/generated/typescript/openapi'
import type { HttpClient, RequestControl } from './http'

export type DisambiguationCoverage = components['schemas']['DisambiguationCoverage']
export type FusionMergeHistory = components['schemas']['FusionMergeHistory']
export type FusionUndoResult = components['schemas']['FusionUndoResult']

/** 只封装已落地的后端协议；页面控制预览、确认、刷新与请求代次。 */
export function createDisambiguationApi(client: HttpClient) {
  return {
    getCoverage: (cid: string, control: RequestControl = {}): Promise<DisambiguationCoverage> =>
      client.request('get', '/api/v1/courses/{cid}/review/disambiguation', { ...control, params: { cid } }),
    listMerges: (cid: string, query: { cursor?: string; limit?: number } = {}, control: RequestControl = {}): Promise<FusionMergeHistory> =>
      client.request('get', '/api/v1/courses/{cid}/review/merges', { ...control, params: { cid }, query }),
    previewUndo: (cid: string, planId: string, groupId: string, expectedRevision: number, control: RequestControl = {}): Promise<FusionUndoResult> =>
      client.request('post', '/api/v1/courses/{cid}/review/merges/{plan_id}/{group_id}/undo-preview', {
        ...control, params: { cid, plan_id: planId, group_id: groupId }, body: { expected_revision: expectedRevision },
      }),
    undo: (cid: string, planId: string, groupId: string, expectedRevision: number, control: RequestControl = {}): Promise<FusionUndoResult> =>
      client.request('post', '/api/v1/courses/{cid}/review/merges/{plan_id}/{group_id}/undo', {
        ...control, params: { cid, plan_id: planId, group_id: groupId }, body: { expected_revision: expectedRevision },
      }),
  }
}
