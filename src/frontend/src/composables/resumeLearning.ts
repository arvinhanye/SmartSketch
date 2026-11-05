import { onScopeDispose, ref, watch, type Ref } from 'vue'
import type { ProgressApi, ProgressResponse } from '../api/progress'
import type { RecommendApi, RecommendResponse } from '../api/recommend'

/**
 * 学生课程列表页的「继续学习」主卡（UI-PINE-01）。
 *
 * - 候选：本人以学生身份加入、且有已发布版本的课程，最多看前 5 门（每门一次进度请求）。
 * - 选课：自身进度行 `updated_at` 最新的那门；都没有学习记录时取第一门候选，主卡写「开始学习」。
 * - 下一步：只取该课程第一条推荐；全部掌握时没有下一步知识点。
 * - 任一请求失败时主卡不出现，课程列表照常显示（主卡只是捷径，不承担错误提示）。
 */

const MAX_CANDIDATES = 5

export interface ProgressSummary {
  mastered: number
  learning: number
  total: number
}

/** 主卡只用到课程的这几个字段（课程列表的视图模型 `CourseCard` 满足它） */
export interface ResumeCourse {
  id: string
  name: string
  myRole: string
  publishedVersion: number | null
}

export interface ResumeState {
  course: ResumeCourse
  hasActivity: boolean
  summary: ProgressSummary
  next: { kpId: string; name: string } | null
  reason: string
  graphVersion: number
}

/** 自身进度行的最近更新时间；没有任何自身行时为 null */
export function lastActivity(progress: ProgressResponse): string | null {
  let latest: string | null = null
  for (const entry of progress.entries) {
    if (entry.updated_at === null) continue
    if (latest === null || Date.parse(entry.updated_at) > Date.parse(latest)) latest = entry.updated_at
  }
  return latest
}

/** 按 status（含继承）统计掌握情况 */
export function summarizeProgress(progress: ProgressResponse): ProgressSummary {
  let mastered = 0
  let learning = 0
  for (const entry of progress.entries) {
    if (entry.status === 'mastered') mastered += 1
    else if (entry.status === 'learning') learning += 1
  }
  return { mastered, learning, total: progress.entries.length }
}

/** 主卡上的一句短理由；推荐候选本身已满足前置，所以不能解锁时只说明前置已掌握 */
export function resumeReason(response: RecommendResponse): string {
  if (response.state === 'all_mastered') return '本课程知识点已全部掌握'
  const first = response.recommendations[0]
  if (first === undefined) return '本课程知识点已全部掌握'
  return first.unlock_count > 0 ? `学完可解锁 ${first.unlock_count} 个知识点` : '前置知识已掌握'
}

export function useResumeLearning(options: {
  courses: Ref<readonly ResumeCourse[]>
  enabled: Ref<boolean>
  progressApi: ProgressApi | null
  recommendApi: RecommendApi | null
  sessionKey: Ref<string | null>
}) {
  const resume = ref<ResumeState | null>(null)
  let controller: AbortController | null = null

  async function load(): Promise<void> {
    controller?.abort()
    controller = null
    resume.value = null
    const { progressApi, recommendApi } = options
    if (!options.enabled.value || progressApi === null || recommendApi === null) return
    const candidates = options.courses.value
      .filter((course) => course.myRole === 'student' && course.publishedVersion !== null)
      .slice(0, MAX_CANDIDATES)
    if (candidates.length === 0) return
    const current = new AbortController()
    controller = current
    try {
      const progresses = await Promise.all(candidates.map((course) => progressApi.get(course.id, { signal: current.signal })))
      let pick = 0
      let pickTime: number | null = null
      progresses.forEach((progress, index) => {
        const at = lastActivity(progress)
        if (at === null) return
        const time = Date.parse(at)
        if (pickTime === null || time > pickTime) {
          pick = index
          pickTime = time
        }
      })
      const course = candidates[pick]!
      const recommendation = await recommendApi.get(course.id, { limit: 1 }, { signal: current.signal })
      if (current.signal.aborted || controller !== current) return
      const first = recommendation.state === 'recommendations' ? recommendation.recommendations[0] : undefined
      resume.value = {
        course,
        hasActivity: pickTime !== null,
        summary: summarizeProgress(progresses[pick]!),
        next: first === undefined ? null : { kpId: first.kp_id, name: first.name },
        reason: resumeReason(recommendation),
        graphVersion: recommendation.graph_version,
      }
    } catch {
      if (controller === current) resume.value = null
    }
  }

  watch([options.courses, options.enabled, options.sessionKey], () => void load(), { immediate: true })
  onScopeDispose(() => controller?.abort())

  return { resume }
}
