import type { ChatEntry, Citation } from './useChat'
import { formatSourceLine } from './sourceLabel'

/** 回答状态标签文字（UI-QA-01 F1）：图标之外必须有文字 */
export const STATUS_LABELS: Record<ChatEntry['status'], string> = {
  streaming: '生成中',
  answered: '已回答',
  not_covered: '资料未覆盖',
  error: '未完成',
  aborted: '已停止',
}

/** 「文件名 · 第 N 页 · 章节」，出处面板、列表与复制共用（缺文件名写「资料不可用」） */
export function citationLine(citation: Citation): string {
  return formatSourceLine({ documentName: citation.document_name, page: citation.page, sectionPath: citation.section_path })
}

const NO_SOURCE: Partial<Record<ChatEntry['status'], string>> = {
  not_covered: '这条回答没有出处：课程资料未覆盖这个问题。',
  error: '这条回答没有出处：本次回答未完成。',
  aborted: '这条回答没有出处：已停止。',
  streaming: '回答生成中，完成后在这里显示出处。',
}

/** 右侧「出处」面板只显示当前回答自己的出处；没有出处时写明原因，不借用别的回答的出处（F2） */
export function sourcesPanel(entry: { status: ChatEntry['status']; citations: readonly Citation[] } | null): {
  citations: readonly Citation[]
  hint: string
} {
  if (entry === null) return { citations: [], hint: '点回答中的编号查看对应原文。' }
  if (entry.status === 'answered') {
    return { citations: entry.citations, hint: entry.citations.length === 0 ? '点回答中的编号查看对应原文。' : '' }
  }
  return { citations: [], hint: NO_SOURCE[entry.status] ?? '' }
}

/** 复制内容：正文 + 空行 + 「出处：」+ 每条一行；没有出处时只有正文（F4） */
export function copyText(answer: string, citations: readonly Citation[]): string {
  if (citations.length === 0) return answer
  return `${answer}\n\n出处：\n${citations.map((c) => `[${c.index}] ${citationLine(c)}`).join('\n')}`
}
