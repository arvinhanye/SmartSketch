import type { InjectionKey } from 'vue'
import type { components } from '../../../contracts/v1/generated/typescript/openapi'
import type { HttpClient, RequestControl } from './http'

/**
 * 知识点详情接口（H06）：只封装契约 `getKnowledgePoint`（`GET /api/v1/courses/{cid}/kp/{kid}`）。
 * 教师读草稿、学生读当前发布版本由后端按身份决定（ADR-030），前端不传版本。
 * 不做状态、不做错误文案；错误按 B15 的错误类型原样抛出，由 composable 处理。
 */

export type KnowledgePointDetail = components['schemas']['KnowledgePointDetail']
export type SourceRef = components['schemas']['SourceRef']
export type KnowledgePointRef = components['schemas']['KnowledgePointRef']

export interface KnowledgeDetailApi {
  /** 知识点详情与出处；不存在 404 `NOT_FOUND`，学生读未发布课程 404 `GRAPH_NOT_PUBLISHED` */
  get(cid: string, kid: string, control?: RequestControl): Promise<KnowledgePointDetail>
}

/** 组件经 inject 取得详情接口，测试可注入假实现；未提供时组件用 `HTTP_CLIENT_KEY` 的客户端构造 */
export const KNOWLEDGE_DETAIL_API_KEY: InjectionKey<KnowledgeDetailApi> = Symbol('smartsketch.knowledge-detail-api')

export function createKnowledgeDetailApi(client: HttpClient): KnowledgeDetailApi {
  return {
    get: (cid, kid, control = {}) =>
      client.request('get', '/api/v1/courses/{cid}/kp/{kid}', { ...control, params: { cid, kid } }),
  }
}
