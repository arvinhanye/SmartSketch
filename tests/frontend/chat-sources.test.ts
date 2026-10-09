import { describe, expect, it } from 'vitest'
import { citationLine, copyText, sourcesPanel, STATUS_LABELS } from '../../src/frontend/src/composables/chatSources'
import type { Citation } from '../../src/frontend/src/composables/useChat'

// UI-QA-01 F1/F2/F4：状态文字、当前回答自己的出处、复制内容。
const c1: Citation = { index: 1, chunk_id: 'k1', document_id: 'd1', page: 46, section_path: '第3章 > 3.2 栈', text: 'x', document_name: 'ch3.md' }
const c2: Citation = { index: 2, chunk_id: 'k2', document_id: 'd2', text: 'y', section_path: '第3章 > 3.3 队列' }

describe('chatSources', () => {
  it('出处一行写法与图谱来源一致，缺文件名写「资料不可用」', () => {
    expect(citationLine(c1)).toBe('ch3.md · 第 46 页 · 第3章 > 3.2 栈')
    expect(citationLine(c2)).toBe('资料不可用 · 第3章 > 3.3 队列')
  })
  it('只有已回答的回答有出处；其余状态给出原因而不是别的回答的出处', () => {
    expect(sourcesPanel({ status: 'answered', citations: [c1] })).toEqual({ citations: [c1], hint: '' })
    expect(sourcesPanel(null).hint).toBe('点回答中的编号查看对应原文。')
    expect(sourcesPanel({ status: 'not_covered', citations: [] })).toEqual({ citations: [], hint: '这条回答没有出处：课程资料未覆盖这个问题。' })
    expect(sourcesPanel({ status: 'error', citations: [] }).hint).toBe('这条回答没有出处：本次回答未完成。')
    expect(sourcesPanel({ status: 'aborted', citations: [] }).hint).toBe('这条回答没有出处：已停止。')
    expect(sourcesPanel({ status: 'streaming', citations: [] }).hint).toBe('回答生成中，完成后在这里显示出处。')
  })
  it('复制文本是正文、空行、「出处：」和每条一行；没有出处时只有正文', () => {
    expect(copyText('栈后进先出[1][2]。', [c1, c2])).toBe(
      '栈后进先出[1][2]。\n\n出处：\n[1] ch3.md · 第 46 页 · 第3章 > 3.2 栈\n[2] 资料不可用 · 第3章 > 3.3 队列',
    )
    expect(copyText('只有正文', [])).toBe('只有正文')
  })
  it('状态标签文字', () => {
    expect(STATUS_LABELS).toEqual({ streaming: '生成中', answered: '已回答', not_covered: '资料未覆盖', error: '未完成', aborted: '已停止' })
  })
})
