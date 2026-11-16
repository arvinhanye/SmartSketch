import type { MaterialsApi, TaskActivity, TaskActivityPhase } from '../../api/materials'
import { ApiError } from '../../api/http'
import { ALL_STAGES } from './status'

export const ACTIVITY_LABEL: Record<TaskActivityPhase, string> = {
  queued: '等待开始处理', parsing: '正在解析资料', entities: '正在提取知识点',
  disambiguating: '正在核对知识点含义', relations: '正在抽取关系', repair: '正在修正模型输出',
  merging: '正在融合知识点与关系', persisting: '正在保存图谱', cancelling: '正在停止处理',
  cancelled: '已停止，完成的结果已保留', awaiting_review: '已生成，等待审核', completed: '已完成',
  failed: '处理已停止', waiting: '等待处理继续', retrying: '等待自动重试',
}

function object(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
const count = (value: unknown) => typeof value === 'number' && Number.isInteger(value) && value >= 0
const instant = (value: unknown) => typeof value === 'string' && Number.isFinite(Date.parse(value))
function units(value: unknown): boolean {
  return object(value) && count(value.completed) && count(value.failed) && count(value.total) &&
    Number(value.completed) + Number(value.failed) <= Number(value.total)
}

function globalDisambiguation(value: unknown): boolean {
  if (value === null) return true
  if (!object(value)) return false
  const names = ['total', 'completed', 'failed', 'deferred', 'reused', 'inflight', 'pending', 'total_possible']
  if (!names.every((name) => count(value[name]))) return false
  return Number(value.total) === Number(value.completed) + Number(value.failed) + Number(value.deferred) +
    Number(value.inflight) + Number(value.pending) && Number(value.reused) <= Number(value.completed) &&
    Number(value.total_possible) >= Number(value.total) &&
    ['planning', 'running', 'complete'].includes(String(value.phase)) && instant(value.updated_at) &&
    (value.phase !== 'complete' || (value.inflight === 0 && value.pending === 0))
}

/** 拒绝跨任务、无效时间和计数，避免把损坏的进度显示成真实完成。 */
export function isTaskActivity(value: unknown, taskId: string): value is TaskActivity {
  return object(value) && value.task_id === taskId && typeof value.stage === 'string' && ALL_STAGES.has(value.stage) &&
    typeof value.progress === 'number' && Number.isFinite(value.progress) && value.progress >= 0 && value.progress <= 1 &&
    typeof value.phase === 'string' && Object.hasOwn(ACTIVITY_LABEL, value.phase) &&
    typeof value.cancel_requested === 'boolean' && typeof value.worker_active === 'boolean' &&
    typeof value.resumable === 'boolean' && count(value.attempt) && instant(value.observed_at) && instant(value.last_activity_at) &&
    (value.retry_at === null || instant(value.retry_at)) && units(value.chunks) && units(value.sections) &&
    object(value.disambiguation) && count(value.disambiguation.completed) && globalDisambiguation(value.global_disambiguation) &&
    Array.isArray(value.active_requests) &&
    value.active_requests.every((request) => object(request) && typeof request.purpose === 'string' &&
      count(request.count) && Number(request.count) > 0 && instant(request.started_at))
}

export interface ActivityWatch { refresh(): void; close(): void }

/** 一次读取结束再安排下一次，切课/继续任务时关闭旧 reader，使迟到响应失效。 */
export function watchTaskActivity(options: {
  api: MaterialsApi
  taskId: string
  signal: AbortSignal
  shouldPoll(): boolean
  stateVersion(): number
  onActivity(value: TaskActivity): void
  onUnavailable(): void
}): ActivityWatch {
  const controller = new AbortController()
  let timer: ReturnType<typeof setTimeout> | undefined
  let closed = false
  let pending = false
  let refreshAfterPending = false
  let forbidden = false
  const close = () => {
    if (closed) return
    closed = true
    controller.abort()
    if (timer !== undefined) clearTimeout(timer)
    options.signal.removeEventListener('abort', close)
  }
  options.signal.addEventListener('abort', close, { once: true })
  const refresh = () => {
    if (closed || forbidden) return
    if (timer !== undefined) clearTimeout(timer)
    if (pending) { refreshAfterPending = true; return }
    pending = true
    const version = options.stateVersion()
    void options.api.taskActivity(options.taskId, { signal: controller.signal }).then((value) => {
      if (closed) return
      if (version !== options.stateVersion()) { refreshAfterPending = true; return }
      if (!isTaskActivity(value, options.taskId)) { options.onUnavailable(); return }
      options.onActivity(value)
    }).catch((cause: unknown) => {
      if (closed) return
      forbidden = cause instanceof ApiError && [401, 403, 404].includes(cause.status)
      options.onUnavailable()
    }).finally(() => {
      pending = false
      if (closed || forbidden) return
      if (refreshAfterPending) { refreshAfterPending = false; refresh(); return }
      if (options.shouldPoll()) timer = setTimeout(refresh, 3000)
    })
  }
  if (options.signal.aborted) close()
  else refresh()
  return { refresh, close }
}

export function formatDuration(ms: number): string {
  const seconds = Math.max(0, Math.floor(ms / 1000))
  if (seconds < 60) return `${seconds} 秒`
  const minutes = Math.floor(seconds / 60)
  return minutes < 60 ? `${minutes} 分 ${seconds % 60} 秒` : `${Math.floor(minutes / 60)} 小时 ${minutes % 60} 分`
}
