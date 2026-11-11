import type { Ref } from 'vue'
import type { components } from '../../../../contracts/v1/generated/typescript/openapi'
import type { CoursesApi } from '../../api/courses'
import type { MaterialsApi } from '../../api/materials'
import type { TaskEventsClient, TaskStage, TaskStreamState, TaskSubscription } from '../../api/taskEvents'
import type { CourseRequestScope } from '../../stores/course'

export type ErrorBody = components['schemas']['Error']

export type TaskStatusKind = 'processing' | 'cancelling' | 'awaiting_review' | 'completed' | 'failed' | 'cancelled'

export interface TaskStatus {
  kind: TaskStatusKind
  label: string
}

export type PageStatus = 'loading' | 'ready' | 'error' | 'forbidden'
/** C12 的连接状态，外加 `broken`：不可恢复地中断，可手动重新连接 */
export type StreamStatus = TaskStreamState | 'broken'

export interface MaterialRow {
  documentId: string
  filename: string
  formatLabel: string
  sizeLabel: string | null
  status: TaskStatus
  /** 本次会话跟踪的任务才有实时进度（0–100） */
  progressPercent: number | null
  canCancel: boolean
  cancelPending: boolean
  cancelError: string | null
  errorMessage: string | null
  /** 本次会话保留了该文件，可一键重新上传 */
  canRetry: boolean
  /** 失败/取消但没有文件可重试：引导重新选择文件 */
  needsReselect: boolean
  streamNotice: string | null
  canReconnect: boolean
  /** 失败/已取消的资料可删除（ADR-021） */
  canDelete: boolean
  confirmingDelete: boolean
  deletePending: boolean
  deleteError: string | null
}

export interface DeleteState {
  confirming: boolean
  pending: boolean
  error: string | null
  /** 409 后不再提供删除入口（清理未完成除外） */
  blocked: boolean
}

export interface TrackedTask {
  taskId: string
  documentId: string
  filename: string
  stage: TaskStage
  progress: number
  cancelRequested: boolean
  error: ErrorBody | null
  stream: StreamStatus
  cancelPending: boolean
  cancelError: string | null
}

/** 一次「打开某课程资料页」的生命周期；离开或切课即作废 */
export interface PageSession {
  courseId: string
  scope: CourseRequestScope
  controller: AbortController
  subs: Map<string, TaskSubscription>
  /** 本页已删除（或服务端已不存在）的资料；删除前发出的列表响应迟到时据此过滤，不让该行复现 */
  removed: Set<string>
  uploading: boolean
  disposed: boolean
}

export interface UseMaterialsOptions {
  materialsApi: MaterialsApi
  coursesApi: CoursesApi
  taskEvents: TaskEventsClient
  /** 当前路由中的课程 ID；`null` 表示已离开资料页 */
  courseId: Ref<string | null>
}
