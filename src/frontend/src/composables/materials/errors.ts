import { ApiError, NetworkError, TimeoutError } from '../../api/http'
import { SUPPORTED_FORMATS_TEXT, formatBytes } from './files'
import type { ErrorBody } from './types'

const TASK_ERROR_MESSAGE: Partial<Record<ErrorBody['code'], string>> = {
  DOCUMENT_UNREADABLE: '文件无法解析（可能已损坏、加密或没有可提取的文本）。',
  LLM_UNAVAILABLE: '模型服务暂不可用，抽取未完成。',
  EXTRACTION_INCOMPLETE: '抽取失败的片段过多，任务未完成。',
  STORAGE_UNAVAILABLE: '存储暂不可用，写入失败。',
  CYCLE_DETECTED: '自动生成的前置关系成环且无法降级。',
  TASK_ATTEMPTS_EXHAUSTED: '处理多次中断，已停止重试。',
  BUDGET_EXCEEDED: '模型调用预算已用尽。',
  INTERNAL_ERROR: '处理过程中发生内部错误。',
}

/** 个人模型凭据导致的任务失败（ADR-080 决定 3、ADR-082 决定 4）：引导用户检查自己的配置 */
const CREDENTIAL_REASONS: ReadonlySet<string> = new Set(['auth', 'credential_revoked', 'credential_missing', 'credential_unreadable'])

export function taskErrorMessage(error: ErrorBody | null): string {
  const reason = error?.details?.reason
  if (error?.code === 'LLM_UNAVAILABLE' && typeof reason === 'string' && CREDENTIAL_REASONS.has(reason)) {
    return reason === 'auth'
      ? '模型服务拒绝了你的 API 密钥，任务已终止。请到「模型 API 设置」检查后重新上传。'
      : '你的模型 API 配置已清除或不可用，任务已终止。请到「模型 API 设置」保存后重新上传。'
  }
  return (error && TASK_ERROR_MESSAGE[error.code]) ?? '处理失败。'
}

export const NETWORK_MESSAGE = '无法连接服务器，请检查网络后重试。'

export function isNetworkFailure(cause: unknown): boolean {
  return cause instanceof NetworkError || cause instanceof TimeoutError
}

interface UploadFailure {
  message: string
  /** 同一文件可直接重试（网络、超时、服务端临时故障） */
  retryable: boolean
  /** 文件本身不合格，高亮上传控件 */
  fileInvalid: boolean
}

/** 413 `FILE_TOO_LARGE` 的 `details.limit_bytes`；缺失或不合法为 null */
export function limitBytesOf(cause: unknown): number | null {
  if (!(cause instanceof ApiError) || cause.code !== 'FILE_TOO_LARGE') return null
  const limit = cause.details?.limit_bytes
  return typeof limit === 'number' && Number.isInteger(limit) && limit > 0 ? limit : null
}

export function uploadFailure(cause: unknown, maxBytes: number | null): UploadFailure {
  if (isNetworkFailure(cause)) return { message: NETWORK_MESSAGE, retryable: true, fileInvalid: false }
  if (cause instanceof ApiError) {
    if (cause.code === 'UNSUPPORTED_FORMAT') {
      return {
        message: `文件格式不受支持或内容与扩展名不符，仅支持 ${SUPPORTED_FORMATS_TEXT}。`,
        retryable: false,
        fileInvalid: true,
      }
    }
    if (cause.code === 'FILE_TOO_LARGE') {
      const limit = limitBytesOf(cause) ?? maxBytes
      const text = limit === null ? '服务器上限' : `服务器上限 ${formatBytes(limit)}`
      return { message: `文件超过${text}，请压缩或拆分后上传。`, retryable: false, fileInvalid: true }
    }
    if (cause.code === 'MODEL_CONFIG_REQUIRED') {
      return { message: '尚未配置模型 API，请先到「模型 API 设置」保存配置后再上传。', retryable: false, fileInvalid: false }
    }
    if (cause.code === 'VALIDATION_ERROR') {
      return { message: '文件名不符合要求（可能为空或过长），请重命名后上传。', retryable: false, fileInvalid: true }
    }
    if (cause.status === 401) return { message: '登录已失效，请重新登录。', retryable: false, fileInvalid: false }
    if (cause.status === 403) return { message: '当前账号无权向该课程上传资料。', retryable: false, fileInvalid: false }
    if (cause.code === 'STORAGE_UNAVAILABLE') {
      return { message: '存储暂不可用，请稍后重试。', retryable: true, fileInvalid: false }
    }
  }
  return { message: '上传失败，请稍后重试。', retryable: true, fileInvalid: false }
}

export const CANCEL_REASON_MESSAGE: Record<string, string> = {
  persisting_uninterruptible: '资料正在入库，无法中断，将继续处理到待审核。',
  processing_finished: '处理已结束，无法取消；如需丢弃内容，请在审核中驳回。',
  already_terminal: '任务已结束，无法取消。',
}

export const DELETE_REASON_MESSAGE: Record<string, string> = {
  processing: '资料仍在处理中，不能删除。',
  contributed: '资料已进入图谱（待审核或已完成），不能删除。',
  cleanup_pending: '资料的图谱清理尚未完成，请稍后再删除。',
}

export function deleteErrorMessage(cause: unknown): string {
  if (isNetworkFailure(cause)) return '无法连接服务器，删除未提交，请检查网络后重试。'
  if (cause instanceof ApiError) {
    if (cause.status === 401) return '登录已失效，请重新登录。'
    if (cause.status === 403) return '当前账号无权删除该资料。'
  }
  return '删除失败，请稍后重试。'
}

export function cancelErrorMessage(cause: unknown): string {
  if (isNetworkFailure(cause)) return '无法连接服务器，取消未提交，请检查网络后重试。'
  if (cause instanceof ApiError) {
    if (cause.status === 401) return '登录已失效，请重新登录。'
    if (cause.status === 403) return '当前账号无权取消该任务。'
    if (cause.status === 404) return '任务不存在或已无权访问。'
  }
  return '取消失败，请稍后重试。'
}
