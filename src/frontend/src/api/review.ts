import type { InjectionKey } from 'vue'
import type { components } from '../../../contracts/v1/generated/typescript/openapi'
import type { HttpClient, RequestControl } from './http'

/**
 * 教师审核队列接口（H09）：只封装契约 `getReviewQueue` 与 `resolveReviewItem`（F11，ADR-060）。
 * 不做状态、不做错误文案；错误按 B15 的错误类型原样抛出，由 `useReview` 处理。
 *
 * - 不带 `kind` 时三栏各返回第一页；带 `kind` 与该栏的 `cursor` 时只填该栏（键集分页）。
 * - 疑似重复的 `merge` 走 F10 `mergeKnowledgePoints` 的全部规则，可能 409 `CYCLE_DETECTED` / `COURSE_BUSY`。
 */

export type ReviewQueue = components['schemas']['ReviewQueue']
export type ReviewItemKind = components['schemas']['ReviewItemKind']
export type ReviewCounts = components['schemas']['ReviewCounts']
export type ReviewAction = components['schemas']['ReviewAction']
export type ReviewActionResult = components['schemas']['ReviewActionResult']
export type SuspectedDuplicate = components['schemas']['SuspectedDuplicate']
export type KnowledgePointRef = components['schemas']['KnowledgePointRef']
export type Relation = components['schemas']['Relation']

export interface ReviewPageQuery {
  kind?: ReviewItemKind
  cursor?: string
  limit?: number
}

export interface ReviewApi {
  getQueue(cid: string, query?: ReviewPageQuery, control?: RequestControl): Promise<ReviewQueue>
  resolve(cid: string, action: ReviewAction, control?: RequestControl): Promise<ReviewActionResult>
}

/** 页面经 inject 取得审核接口，测试可注入假实现；未提供时页面用 `HTTP_CLIENT_KEY` 的客户端构造 */
export const REVIEW_API_KEY: InjectionKey<ReviewApi> = Symbol('smartsketch.review-api')

export function createReviewApi(client: HttpClient): ReviewApi {
  return {
    getQueue: (cid, query = {}, control = {}) =>
      client.request('get', '/api/v1/courses/{cid}/review', { ...control, params: { cid }, query }),
    resolve: (cid, action, control = {}) =>
      client.request('post', '/api/v1/courses/{cid}/review/actions', { ...control, params: { cid }, body: action }),
  }
}
