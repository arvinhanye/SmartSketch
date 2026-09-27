import { expect, test as base, type Page } from '@playwright/test'

export const test = base
export { expect }

export const appUrl = process.env.E2E_BASE_URL ?? 'http://127.0.0.1:5173'
export const teacherUsername = process.env.E2E_TEACHER_USERNAME ?? 'demo_teacher'
export const teacherPassword = process.env.E2E_TEACHER_PASSWORD ?? ''
export const studentUsername = process.env.E2E_STUDENT_USERNAME ?? 'demo_student'
export const studentPassword = process.env.E2E_STUDENT_PASSWORD ?? ''

export async function login(page: Page, username: string, password: string): Promise<void> {
  await page.goto(appUrl)
  await page.getByLabel('用户名').fill(username)
  await page.getByLabel('密码').fill(password)
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page.getByRole('heading', { name: '我的课程' })).toBeVisible()
}

export type UploadFile = { name: string; mimeType: string; buffer: Buffer }

const lesson = 'Chapter 3: Stack and Queue. A stack is last in first out. A queue is first in first out.'
// 中文正文供 txt/md/docx 使用：演示模型（LLM_MODE=demo）按中文定义句抽取知识点；
// PDF 用内置 Helvetica 字体只能写 ASCII，保持英文。
const lessonZh = '第3章 栈与队列\n\n栈是一种只允许在一端进行插入和删除的线性表，特点是后进先出。' +
  '队列是一种只允许在一端插入、在另一端删除的线性表，特点是先进先出。' +
  '循环队列是用数组实现队列的一种方式。学习队列之前需要先掌握栈。'

function pdf(text: string): Buffer {
  const stream = `BT /F1 12 Tf 40 750 Td (${text}) Tj ET`
  const objects = [
    '<< /Type /Catalog /Pages 2 0 R >>',
    '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
    '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
    '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
    `<< /Length ${Buffer.byteLength(stream)} >>\nstream\n${stream}\nendstream`,
  ]
  let body = '%PDF-1.4\n'
  const offsets = [0]
  for (const [index, object] of objects.entries()) {
    offsets.push(Buffer.byteLength(body))
    body += `${index + 1} 0 obj\n${object}\nendobj\n`
  }
  const xref = Buffer.byteLength(body)
  body += `xref\n0 ${offsets.length}\n0000000000 65535 f \n`
  for (const offset of offsets.slice(1)) body += `${String(offset).padStart(10, '0')} 00000 n \n`
  body += `trailer\n<< /Size ${offsets.length} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`
  return Buffer.from(body)
}

function crc32(data: Buffer): number {
  let crc = 0xffffffff
  for (const byte of data) {
    crc ^= byte
    for (let bit = 0; bit < 8; bit++) crc = (crc >>> 1) ^ ((crc & 1) ? 0xedb88320 : 0)
  }
  return (crc ^ 0xffffffff) >>> 0
}

function zip(files: Record<string, string>): Buffer {
  const local: Buffer[] = []
  const central: Buffer[] = []
  let offset = 0
  for (const [name, content] of Object.entries(files)) {
    const filename = Buffer.from(name)
    const data = Buffer.from(content)
    const crc = crc32(data)
    const header = Buffer.alloc(30)
    header.writeUInt32LE(0x04034b50, 0)
    header.writeUInt16LE(20, 4)
    header.writeUInt32LE(crc, 14)
    header.writeUInt32LE(data.length, 18)
    header.writeUInt32LE(data.length, 22)
    header.writeUInt16LE(filename.length, 26)
    local.push(header, filename, data)
    const directory = Buffer.alloc(46)
    directory.writeUInt32LE(0x02014b50, 0)
    directory.writeUInt16LE(20, 4)
    directory.writeUInt16LE(20, 6)
    directory.writeUInt32LE(crc, 16)
    directory.writeUInt32LE(data.length, 20)
    directory.writeUInt32LE(data.length, 24)
    directory.writeUInt16LE(filename.length, 28)
    directory.writeUInt32LE(offset, 42)
    central.push(directory, filename)
    offset += header.length + filename.length + data.length
  }
  const directorySize = central.reduce((size, part) => size + part.length, 0)
  const end = Buffer.alloc(22)
  end.writeUInt32LE(0x06054b50, 0)
  end.writeUInt16LE(Object.keys(files).length, 8)
  end.writeUInt16LE(Object.keys(files).length, 10)
  end.writeUInt32LE(directorySize, 12)
  end.writeUInt32LE(offset, 16)
  return Buffer.concat([...local, ...central, end])
}

function docx(text: string): Buffer {
  return zip({
    '[Content_Types].xml': '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>',
    '_rels/.rels': '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>',
    'word/document.xml': `<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>${text}</w:t></w:r></w:p></w:body></w:document>`,
  })
}

export const fourFormats: UploadFile[] = [
  { name: 'stack-queue.txt', mimeType: 'text/plain', buffer: Buffer.from(lessonZh) },
  { name: 'stack-queue.md', mimeType: 'text/markdown', buffer: Buffer.from(`# 栈与队列\n\n${lessonZh}\n`) },
  { name: 'stack-queue.pdf', mimeType: 'application/pdf', buffer: pdf(lesson) },
  { name: 'stack-queue.docx', mimeType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', buffer: docx(lessonZh.replace(/\n/g, ' ')) },
]
