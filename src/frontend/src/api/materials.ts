import type { InjectionKey } from 'vue'
import type { components } from '../../../contracts/v1/generated/typescript/openapi'
import type { HttpClient, RequestControl } from './http'
import type { TaskEventsClient } from './taskEvents'

/**
 * 资料与处理任务接口（H02）：只封装契约 `listDocuments`、`uploadDocument`、`deleteDocument`、
 * `getUploadPolicy` 与 `cancelTask`。
 * 不做状态、不做错误文案；错误按 B15 的错误类型原样抛出，由 composable 处理。
 * 进度订阅走 C12 的 `TaskEventsClient`，此处只提供其注入键。
 */

export type MaterialDocument = components['schemas']['Document']
export type DocumentFormat = components['schemas']['DocumentFormat']
export type UploadAccepted = components['schemas']['UploadAccepted']
export type TaskSnapshot = components['schemas']['Task']
export type UploadPolicy = components['schemas']['UploadPolicy']
/** 409 `TASK_NOT_CANCELLABLE` 的 `details`（`specs/task-processing.md` §4） */
export type TaskNotCancellableDetails = components['schemas']['TaskNotCancellableError']['details']

export interface MaterialsApi {
  /** 课程资料列表（课程教师）；`parse_status` 与 `task_id` 取该资料最新任务（D-16、ADR-021） */
  list(cid: string, control?: RequestControl): Promise<MaterialDocument[]>
  /** 以 multipart 字段 `file` 上传，202 返回任务 ID；413/415/422 等按错误类型抛出 */
  upload(cid: string, file: File, control?: RequestControl): Promise<UploadAccepted>
  /** 删除全部任务为失败/已取消的资料（ADR-021），204；不可删为 409 `DOCUMENT_NOT_DELETABLE` */
  deleteDocument(cid: string, did: string, control?: RequestControl): Promise<void>
  /** 服务端当前上传上限（ADR-022：`max_bytes` = `UPLOAD_MAX_BYTES`，课程教师） */
  uploadPolicy(cid: string, control?: RequestControl): Promise<UploadPolicy>
  /** 协作式取消；受理均为 200，以响应体 `stage` 与 `cancel_requested` 为准，不可取消为 409 */
  cancelTask(tid: string, control?: RequestControl): Promise<TaskSnapshot>
}

/** 视图经 inject 取得资料接口，测试可注入假实现 */
export const MATERIALS_API_KEY: InjectionKey<MaterialsApi> = Symbol('smartsketch.materials-api')

/** 视图经 inject 取得 C12 任务流客户端（`main.ts` 用同一个会话 HTTP 客户端构造） */
export const TASK_EVENTS_CLIENT_KEY: InjectionKey<TaskEventsClient> = Symbol('smartsketch.task-events-client')

export function createMaterialsApi(client: HttpClient): MaterialsApi {
  return {
    list: (cid, control = {}) => client.request('get', '/api/v1/courses/{cid}/documents', { ...control, params: { cid } }),
    upload: (cid, file, control = {}) => {
      const body = new FormData()
      body.append('file', file, file.name)
      return client.request('post', '/api/v1/courses/{cid}/documents', { ...control, params: { cid }, body })
    },
    deleteDocument: async (cid, did, control = {}) => {
      await client.request('delete', '/api/v1/courses/{cid}/documents/{did}', { ...control, params: { cid, did } })
    },
    uploadPolicy: (cid, control = {}) =>
      client.request('get', '/api/v1/courses/{cid}/upload-policy', { ...control, params: { cid } }),
    cancelTask: (tid, control = {}) =>
      client.request('post', '/api/v1/tasks/{tid}/cancel', { ...control, params: { tid } }),
  }
}
