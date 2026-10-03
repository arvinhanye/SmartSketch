import type { InjectionKey } from 'vue'
import type { components } from '../../../contracts/v1/generated/typescript/openapi'
import type { HttpClient, RequestControl } from './http'

/**
 * 当前用户的个人模型 API 配置（L10，ADR-080）：只封装契约的四个操作。
 * 响应永不含密钥；请求里的 `api_key` 只在保存与测试时出现一次，本模块与调用方都不缓存它。
 */

export type ModelConfig = components['schemas']['ModelConfig']
export type ModelConfigUpdate = components['schemas']['ModelConfigUpdate']
export type ModelConfigTestRequest = components['schemas']['ModelConfigTestRequest']
export type ModelConfigTestResult = components['schemas']['ModelConfigTestResult']

export interface ModelConfigApi {
  get(control?: RequestControl): Promise<ModelConfig>
  save(body: ModelConfigUpdate, control?: RequestControl): Promise<ModelConfig>
  clear(control?: RequestControl): Promise<void>
  /** 不带 `body` 测试已保存的配置；带则测试这组值而不保存 */
  test(body?: ModelConfigTestRequest, control?: RequestControl): Promise<ModelConfigTestResult>
}

export const MODEL_CONFIG_API_KEY: InjectionKey<ModelConfigApi> = Symbol('smartsketch.model-config-api')

export function createModelConfigApi(client: HttpClient): ModelConfigApi {
  return {
    get: (control = {}) => client.request('get', '/api/v1/me/model-config', { ...control }),
    save: (body, control = {}) => client.request('put', '/api/v1/me/model-config', { ...control, body }),
    clear: async (control = {}) => {
      await client.request('delete', '/api/v1/me/model-config', { ...control })
    },
    test: (body, control = {}) =>
      client.request('post', '/api/v1/me/model-config/test', body === undefined ? { ...control } : { ...control, body }),
  }
}
