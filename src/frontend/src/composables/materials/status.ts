import type { TaskStage } from '../../api/taskEvents'
import type { StreamStatus, TaskStatus } from './types'

const STAGE_LABEL: Record<TaskStage, string> = {
  queued: '排队中',
  parsing: '解析中',
  extracting: '抽取中',
  merging: '融合中',
  persisting: '入库中',
  awaiting_review: '待审核',
  completed: '已完成审核',
  failed: '处理失败',
  cancelled: '已取消',
}

export const ACTIVE_STAGES: ReadonlySet<TaskStage> = new Set(['queued', 'parsing', 'extracting', 'merging', 'persisting'])
/** 可发起取消的阶段；`persisting` 不可中断（`specs/task-processing.md` §1） */
export const CANCELLABLE_STAGES: ReadonlySet<TaskStage> = new Set(['queued', 'parsing', 'extracting', 'merging'])
export const ALL_STAGES: ReadonlySet<string> = new Set(Object.keys(STAGE_LABEL))

/** 「取消中」与「已取消」分开：前者是非终态上的标志位，后者是终态 */
export function taskStatusOf({ stage, cancelRequested }: { stage: TaskStage; cancelRequested: boolean }): TaskStatus {
  const label = STAGE_LABEL[stage]
  switch (stage) {
    case 'cancelled':
    case 'failed':
    case 'completed':
    case 'awaiting_review':
      return { kind: stage, label }
    default:
      return cancelRequested ? { kind: 'cancelling', label: '取消中' } : { kind: 'processing', label }
  }
}

export const STREAM_NOTICE: Partial<Record<StreamStatus, string>> = {
  reconnecting: '实时连接中断，正在重连…',
  polling: '实时连接不可用，已改为定时刷新进度。',
  broken: '进度连接已中断，状态可能不是最新。',
}
