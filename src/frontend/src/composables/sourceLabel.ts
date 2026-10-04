/**
 * L12（R04，ADR-085）：来源的一行文字「文件名 · 第 N 页 · 章节」，图谱来源与问答引用共用。
 * 文件名来自后端同课资料（契约可选 `document_name`）；缺失（资料已删除或不可读）时写「资料不可用」，
 * 不拿资料 ID 冒充文件名。
 */

export const MISSING_DOCUMENT = '资料不可用'
/** 片段超过这个字数时先折叠 */
export const EXCERPT_FOLD_CHARS = 600

export interface SourceLabelInput {
  documentName?: string | null
  page?: number | null
  sectionPath?: string | null
}

export function documentLabel(name: string | null | undefined): string {
  return typeof name === 'string' && name.trim() !== '' ? name : MISSING_DOCUMENT
}

export function locationLabel({ page, sectionPath }: SourceLabelInput): string {
  const parts: string[] = []
  if (typeof page === 'number' && Number.isInteger(page) && page >= 1) parts.push(`第 ${page} 页`)
  if (typeof sectionPath === 'string' && sectionPath.trim() !== '') parts.push(sectionPath)
  return parts.join(' · ')
}

export function formatSourceLine(input: SourceLabelInput): string {
  const location = locationLabel(input)
  return location === '' ? documentLabel(input.documentName) : `${documentLabel(input.documentName)} · ${location}`
}
