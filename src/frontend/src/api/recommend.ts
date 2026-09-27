import type { InjectionKey } from 'vue'
import type { components } from '../../../contracts/v1/generated/typescript/openapi'
import type { HttpClient, RequestControl } from './http'

/**
 * 下一步推荐接口（I06）：只封装契约 `getRecommendations`（`GET /api/v1/courses/{cid}/recommend`，I05、ADR-014 修订 1）。
 * 不做状态、不做错误文案；错误按 B15 的错误类型原样抛出，由 `useLearning` 处理。
 *
 * - 200 只有两个判别状态：`recommendations`（有候选，列表至多 `limit` 条、`total_eligible` 为截断前候选总数）
 *   与 `all_mastered`（V 非空且全部掌握，空列表）。不存在 `no_graph`。
 * - 未发布 404 `GRAPH_NOT_PUBLISHED`；已提交版完整性故障 500 `INTERNAL_ERROR`（`details` 只含 `request_id`）。
 * - `limit` 正整数、默认 10、最大 50，超出范围整请求拒绝；越界在本地拒绝，不发请求。
 */

export type RecommendResponse = components['schemas']['RecommendResponse']
export type RecommendListResponse = components['schemas']['RecommendListResponse']
export type RecommendAllMasteredResponse = components['schemas']['RecommendAllMasteredResponse']
export type Recommendation = components['schemas']['Recommendation']
export type RecommendFactors = components['schemas']['RecommendFactors']
export type RecommendWeightedFactors = components['schemas']['RecommendWeightedFactors']
export type RecommendReasonFacts = components['schemas']['RecommendReasonFacts']

export interface RecommendQuery {
  limit?: number
}

export interface RecommendApi {
  /** 读下一步推荐；未发布 404 `GRAPH_NOT_PUBLISHED`，全部掌握走 200 `all_mastered` */
  get(cid: string, query?: RecommendQuery, control?: RequestControl): Promise<RecommendResponse>
}

/** 页面经 inject 取得推荐接口，测试可注入假实现；未注入时页面不渲染推荐区 */
export const RECOMMEND_API_KEY: InjectionKey<RecommendApi> = Symbol('smartsketch.recommend-api')

export function createRecommendApi(client: HttpClient): RecommendApi {
  return {
    get: (cid, query = {}, control = {}) => {
      const limit = query.limit
      if (limit !== undefined && (!Number.isInteger(limit) || limit < 1 || limit > 50)) {
        return Promise.reject(new RangeError(`推荐条数上限必须是 1～50 的整数：${String(limit)}`))
      }
      return client.request('get', '/api/v1/courses/{cid}/recommend', { ...control, params: { cid }, query })
    },
  }
}
