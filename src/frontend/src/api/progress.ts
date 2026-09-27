import type { InjectionKey } from 'vue'
import type { components } from '../../../contracts/v1/generated/typescript/openapi'
import type { HttpClient, RequestControl } from './http'

/**
 * 学习进度接口（I06）：只封装契约 `getProgress` / `updateProgress`（`GET`/`PUT /api/v1/courses/{cid}/progress`，B12、ADR-017）。
 * 不做状态、不做错误文案；错误按 B15 的错误类型原样抛出，由 `useLearning` 处理。
 *
 * - `GET` 返回绑定发布版 V 中**每个节点**的进度项（`ProgressResponse`），`graph_version` 即绑定版本。
 * - `PUT` 的请求体是 `ProgressUpdate[]`：契约里只有 `kp_id` 与 `status`（`additionalProperties: false`），
 *   **不新增 `graph_version` 字段或查询参数**（该契约的 `query?: never`）。版本绑定由调用方在
 *   `useLearning` 里完成：只在已显示版本上写入，并按响应的 `graph_version` 复核，见 ADR-075。
 * - 目标不在当前发布版时服务端整批拒绝：422 `VALIDATION_ERROR` + `details.fields[].reason = not_in_published_version`
 *   与 `details.graph_version`（草稿独有/已删除/他课同一 reason，不回显 kp_id）。
 */

export type ProgressEntry = components['schemas']['ProgressEntry']
export type ProgressResponse = components['schemas']['ProgressResponse']
export type ProgressUpdate = components['schemas']['ProgressUpdate']
export type ProgressInheritedSource = components['schemas']['ProgressInheritedSource']
export type MasteryStatus = components['schemas']['MasteryStatus']

export interface ProgressApi {
  /** 读当前学生在本课程绑定发布版上的每个节点进度；未发布 404 `GRAPH_NOT_PUBLISHED` */
  get(cid: string, control?: RequestControl): Promise<ProgressResponse>
  /** 批量写入掌握状态；空批次在本地拒绝（契约 `minItems = 1`），不发请求 */
  update(cid: string, updates: readonly ProgressUpdate[], control?: RequestControl): Promise<ProgressResponse>
}

/** 页面经 inject 取得进度接口，测试可注入假实现；未注入时页面不启用掌握标记（H11 旧接线保持原样） */
export const PROGRESS_API_KEY: InjectionKey<ProgressApi> = Symbol('smartsketch.progress-api')

export function createProgressApi(client: HttpClient): ProgressApi {
  return {
    get: (cid, control = {}) => client.request('get', '/api/v1/courses/{cid}/progress', { ...control, params: { cid } }),
    update: (cid, updates, control = {}) => {
      if (updates.length === 0) {
        return Promise.reject(new RangeError('进度写入批次不能为空（契约 minItems = 1）'))
      }
      return client.request('put', '/api/v1/courses/{cid}/progress', { ...control, params: { cid }, body: [...updates] })
    },
  }
}
