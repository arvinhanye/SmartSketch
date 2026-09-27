import type { InjectionKey } from 'vue'
import type { components } from '../../../contracts/v1/generated/typescript/openapi'
import type { HttpClient, RequestControl } from './http'

/**
 * 已发布图谱读取接口（H11）：只封装契约 `getGraph`（`GET /api/v1/courses/{cid}/graph`）的**按版本读取**。
 *
 * 契约规定省略 `version` 时课程内教师读草稿，所以本封装把 `version` 设为必填：
 * 经此接口的任何请求都显式指定发布版本号，调用方无法借它读到草稿（ADR-063）。
 * 不做状态、不做错误文案；错误按 B15 的错误类型原样抛出，由 composable 处理。
 */

export type GraphExchange = components['schemas']['GraphExchange']

export interface PublishedGraphApi {
  /** 读取指定发布版本；未发布 404 `GRAPH_NOT_PUBLISHED`，版本号不存在 404 `NOT_FOUND` */
  getPublished(cid: string, version: number, control?: RequestControl): Promise<GraphExchange>
}

/** 页面经 inject 取得图谱接口，测试可注入假实现；未提供时页面用 `HTTP_CLIENT_KEY` 的客户端构造 */
export const PUBLISHED_GRAPH_API_KEY: InjectionKey<PublishedGraphApi> = Symbol('smartsketch.published-graph-api')

export function createPublishedGraphApi(client: HttpClient): PublishedGraphApi {
  return {
    getPublished: (cid, version, control = {}) => {
      if (!Number.isInteger(version) || version < 1) {
        return Promise.reject(new RangeError(`发布版本号必须是正整数：${String(version)}`))
      }
      return client.request('get', '/api/v1/courses/{cid}/graph', { ...control, params: { cid }, query: { version } })
    },
  }
}

/**
 * 草稿图谱读取接口（H14）：`getGraph` **不带** `version`，课程内教师得到草稿（`graph_version` 为 null）。
 * 与 `PublishedGraphApi` 分开注入，学生页拿不到本接口；是否为课程教师由页面先按 `Course.my_role` 判断。
 */
export interface DraftGraphApi {
  /** 读取草稿；非课程教师 403 `COURSE_FORBIDDEN` / `ROLE_FORBIDDEN` */
  getDraft(cid: string, control?: RequestControl): Promise<GraphExchange>
}

export const DRAFT_GRAPH_API_KEY: InjectionKey<DraftGraphApi> = Symbol('smartsketch.draft-graph-api')

export function createDraftGraphApi(client: HttpClient): DraftGraphApi {
  return {
    getDraft: (cid, control = {}) => client.request('get', '/api/v1/courses/{cid}/graph', { ...control, params: { cid } }),
  }
}
