import type { DocumentFormat } from '../../api/materials'

/** 与后端 `file_storage._EXTENSIONS` 一致（大小写不敏感） */
export const MATERIAL_EXTENSIONS = ['.pdf', '.docx', '.txt', '.md', '.markdown'] as const
export const SUPPORTED_FORMATS_TEXT = 'PDF、DOCX、TXT、Markdown（.md / .markdown）'
/** `<input accept>`：扩展名 + 契约 `uploadDocument` 声明的媒体类型 */
export const MATERIAL_ACCEPT = [
  ...MATERIAL_EXTENSIONS,
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'text/plain',
  'text/markdown',
].join(',')

const FORMAT_BY_EXTENSION: Record<(typeof MATERIAL_EXTENSIONS)[number], DocumentFormat> = {
  '.pdf': 'pdf',
  '.docx': 'docx',
  '.txt': 'txt',
  '.md': 'markdown',
  '.markdown': 'markdown',
}
export const FORMAT_LABEL: Record<DocumentFormat, string> = { pdf: 'PDF', docx: 'DOCX', txt: 'TXT', markdown: 'Markdown' }

function extensionOf(name: string): string {
  const dot = name.lastIndexOf('.')
  // 与后端 Path.suffix 一致：「.md」这类只有点前缀的名字没有扩展名
  return dot <= 0 ? '' : name.slice(dot).toLowerCase()
}

export function formatOf(name: string): DocumentFormat | null {
  const ext = extensionOf(name)
  return (FORMAT_BY_EXTENSION as Record<string, DocumentFormat | undefined>)[ext] ?? null
}

/** 扩展名归一：.markdown 与 .md 视为同一格式 */
function splitName(filename: string): { stem: string; format: string } | null {
  const lower = filename.trim().toLowerCase()
  const dot = lower.lastIndexOf('.')
  if (dot <= 0 || dot === lower.length - 1) return null
  const format = lower.slice(dot + 1)
  return { stem: lower.slice(0, dot), format: format === 'markdown' ? 'md' : format }
}

/**
 * C05-4：已上传资料里与 ``filename`` 同名、但格式不同的那份（如已有 ch3.md 再传 ch3.pdf）；没有为 null。
 * 同一章两种格式都上传会抽出大量同名知识点，跨资料融合不在本期（R05），只提示、不阻止。
 */
export function sameChapterOtherFormat(filename: string, existing: readonly string[]): string | null {
  const target = splitName(filename)
  if (target === null) return null
  return existing.find((name) => {
    const other = splitName(name)
    return other !== null && other.stem === target.stem && other.format !== target.format
  }) ?? null
}

export function formatBytes(bytes: number): string {
  const mib = bytes / (1024 * 1024)
  if (mib >= 1) return `${Number.isInteger(mib) ? mib : mib.toFixed(1)} MiB`
  const kib = bytes / 1024
  if (kib >= 1) return `${Number.isInteger(kib) ? kib : kib.toFixed(1)} KiB`
  return `${bytes} B`
}

const UNSUPPORTED_MESSAGE = `不支持该文件格式，仅支持 ${SUPPORTED_FORMATS_TEXT}。`

/**
 * 本地校验；通过返回 null，否则返回提示文案。
 * `maxBytes` 为服务端上传上限（ADR-022）；`null` 表示未知，此时不做大小校验，交服务端 413 判定。
 */
export function validateMaterialFile(file: File, maxBytes: number | null): string | null {
  if (formatOf(file.name) === null) return UNSUPPORTED_MESSAGE
  if (file.size === 0) return '文件为空，请选择有内容的资料。'
  if (maxBytes !== null && file.size > maxBytes) {
    return `文件大小 ${formatBytes(file.size)} 超过 ${formatBytes(maxBytes)} 上限，请压缩或拆分后上传。`
  }
  return null
}
