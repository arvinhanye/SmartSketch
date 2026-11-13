import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { computed, defineComponent, effectScope, h, ref } from 'vue'
import { useEditHistory, HISTORY_LIMIT } from '../../src/frontend/src/composables/useEditHistory'
import { useRelationHistory } from '../../src/frontend/src/composables/useRelationHistory'
import type { RelationEditor } from '../../src/frontend/src/composables/useRelationEditor'

/**
 * UI-GRAPH-UNDO-04：撤销 / 重做记录（useEditHistory）与关系操作的反向操作（useRelationHistory）。
 * 教师页整页流程在 h14.test.ts。
 */
function step(log: string[], name: string, ok: { undo?: boolean; redo?: boolean } = {}) {
  return {
    label: name,
    undo: vi.fn(async () => {
      log.push(`undo ${name}`)
      return ok.undo ?? true
    }),
    redo: vi.fn(async () => {
      log.push(`redo ${name}`)
      return ok.redo ?? true
    }),
  }
}

describe('useEditHistory', () => {
  it('按后进先出撤销，再按原顺序重做；按钮说明是下一步的名字', async () => {
    const log: string[] = []
    const history = effectScope().run(() => useEditHistory())!
    expect([history.canUndo.value, history.canRedo.value]).toEqual([false, false])
    history.record(step(log, 'A'))
    history.record(step(log, 'B'))
    expect(history.undoLabel.value).toBe('B')
    await history.undo()
    expect([history.undoLabel.value, history.redoLabel.value]).toEqual(['A', 'B'])
    await history.undo()
    expect(history.canUndo.value).toBe(false)
    await history.redo()
    await history.redo()
    expect(log).toEqual(['undo B', 'undo A', 'redo A', 'redo B'])
    expect([history.canUndo.value, history.canRedo.value]).toEqual([true, false])
  })

  it('做了新操作后重做记录清空', async () => {
    const log: string[] = []
    const history = effectScope().run(() => useEditHistory())!
    history.record(step(log, 'A'))
    await history.undo()
    expect(history.canRedo.value).toBe(true)
    history.record(step(log, 'C'))
    expect(history.canRedo.value).toBe(false)
    expect(await history.redo()).toBe(false)
    expect(history.undoLabel.value).toBe('C')
  })

  it('反向操作失败：这一步移除并说明，其余记录保留，不自动重试', async () => {
    const log: string[] = []
    const history = effectScope().run(() => useEditHistory())!
    history.record(step(log, 'A'))
    history.record(step(log, 'B', { undo: false }))
    expect(await history.undo()).toBe(false)
    expect(history.notice.value).toEqual({ tone: 'error', text: '未撤销：B。这一步已从撤销记录中移除。' })
    expect([history.undoLabel.value, history.canRedo.value]).toEqual(['A', false])
    expect(await history.undo()).toBe(true)
    expect(history.notice.value).toEqual({ tone: 'success', text: '已撤销：A' })

    history.record(step(log, 'D', { redo: false }))
    await history.undo()
    expect(await history.redo()).toBe(false)
    expect(history.notice.value?.text).toBe('未重做：D。这一步已从记录中移除。')
    expect(history.canRedo.value).toBe(false)
  })

  it('一次只做一步：进行中再触发撤销或重做不重复执行；外部忙碌时也不执行', async () => {
    let release!: () => void
    const gate = new Promise<void>((resolve) => { release = resolve })
    const slow = { label: '慢', undo: vi.fn(async () => { await gate; return true }), redo: vi.fn(async () => true) }
    const busy = ref(false)
    const history = effectScope().run(() => useEditHistory({ busy: () => busy.value }))!
    history.record(slow)
    history.record({ label: '快', undo: vi.fn(async () => true), redo: vi.fn(async () => true) })
    await history.undo()
    const first = history.undo()
    expect(history.working.value).toBe(true)
    expect(await history.undo()).toBe(false)
    expect(await history.redo()).toBe(false)
    release()
    await first
    expect(slow.undo).toHaveBeenCalledTimes(1)

    busy.value = true
    expect(await history.redo()).toBe(false)
    expect(slow.redo).not.toHaveBeenCalled()
  })

  it(`最多保留 ${HISTORY_LIMIT} 步，超出时丢弃最早的；clear 清空两边`, async () => {
    const log: string[] = []
    const history = effectScope().run(() => useEditHistory())!
    for (let i = 0; i < HISTORY_LIMIT + 3; i += 1) history.record(step(log, `S${i}`))
    let count = 0
    while (history.canUndo.value) {
      await history.undo()
      count += 1
    }
    expect(count).toBe(HISTORY_LIMIT)
    expect(log.at(-1)).toBe('undo S3')
    history.clear()
    expect([history.canUndo.value, history.canRedo.value]).toEqual([false, false])
  })
})

describe('useEditHistory：快捷键', () => {
  afterEach(() => {
    document.body.innerHTML = ''
  })
  function press(init: KeyboardEventInit, target: EventTarget = document.body): KeyboardEvent {
    const event = new KeyboardEvent('keydown', { bubbles: true, cancelable: true, ...init })
    target.dispatchEvent(event)
    return event
  }

  it('Ctrl/⌘+Z 撤销，Ctrl/⌘+Shift+Z 与 Ctrl+Y 重做；输入框里不触发；没有可撤销的不拦截按键', async () => {
    const log: string[] = []
    let history!: ReturnType<typeof useEditHistory>
    const Host = defineComponent({
      setup() {
        history = useEditHistory({ shortcuts: true })
        return () => h('div', [h('input'), h('textarea')])
      },
    })
    const w = mount(Host, { attachTo: document.body })
    expect(press({ key: 'z', ctrlKey: true }).defaultPrevented).toBe(false)
    history.record(step(log, 'A'))
    history.record(step(log, 'B'))

    expect(press({ key: 'z', metaKey: true }, w.get('input').element).defaultPrevented).toBe(false)
    expect(press({ key: 'z', ctrlKey: true }, w.get('textarea').element).defaultPrevented).toBe(false)
    expect(log).toEqual([])

    expect(press({ key: 'z', metaKey: true }).defaultPrevented).toBe(true)
    await flushPromises()
    expect(press({ key: 'Z', ctrlKey: true, shiftKey: true }).defaultPrevented).toBe(true)
    await flushPromises()
    press({ key: 'z', ctrlKey: true })
    await flushPromises()
    press({ key: 'y', ctrlKey: true })
    await flushPromises()
    expect(log).toEqual(['undo B', 'redo B', 'undo B', 'redo B'])
    expect(press({ key: 'z' }).defaultPrevented).toBe(false)
    w.unmount()
    press({ key: 'z', ctrlKey: true })
    await flushPromises()
    expect(log).toHaveLength(4)
  })
})

// ---------------------------------------------------------------- 关系操作的反向操作

type Edge = { id: string; type: string; from_id: string; to_id: string; status: string }

/** 假关系编辑器：像真实后端一样，改类型或反转后关系编号会变（按“类型 + 端点”重新派生） */
function fakeRelations(initial: Edge[]) {
  const edges = ref<Edge[]>(initial)
  const idOf = (e: { type: string; from_id: string; to_id: string }) => `rel:${e.type}:${e.from_id}:${e.to_id}`
  const labels: Record<string, string> = { PREREQUISITE: '前置', CONTAINS: '包含', RELATED_TO: '相关', EXAMPLE_OF: '应用实例' }
  const fail = ref(false)
  const raw = {
    saving: ref(false),
    fromId: ref<string | null>(null),
    toId: ref<string | null>(null),
    draftType: ref('PREREQUISITE'),
    graph: computed(() => ({ edges: edges.value, nodes: [] })),
    describeRelation: (id: string) => {
      const e = edges.value.find((x) => x.id === id)
      return e === undefined ? null : { id: e.id, type: e.type, typeLabel: labels[e.type], fromId: e.from_id, fromName: e.from_id.toUpperCase(), toId: e.to_id, toName: e.to_id.toUpperCase(), reversible: e.type !== 'RELATED_TO', pending: false, highlighted: false, downgraded: false }
    },
    createBetween: vi.fn(async (from: string, to: string, type: string) => {
      if (fail.value) return false
      const next = { type, from_id: from, to_id: to, status: 'draft' }
      edges.value = [...edges.value, { ...next, id: idOf(next) }]
      return true
    }),
    createRelation: vi.fn(async () => false),
    changeType: vi.fn(async (id: string, type: string) => {
      if (fail.value) return false
      edges.value = edges.value.map((e) => (e.id === id ? { ...e, type, id: idOf({ ...e, type }) } : e))
      return true
    }),
    reverseRelation: vi.fn(async (id: string) => {
      if (fail.value) return false
      edges.value = edges.value.map((e) => (e.id === id ? { ...e, from_id: e.to_id, to_id: e.from_id, id: idOf({ type: e.type, from_id: e.to_id, to_id: e.from_id }) } : e))
      return true
    }),
    deleteRelation: vi.fn(async (id: string) => {
      if (fail.value) return false
      edges.value = edges.value.filter((e) => e.id !== id)
      return true
    }),
  }
  return { raw, relations: raw as unknown as RelationEditor, edges, fail, idOf }
}
const triples = (edges: Edge[]) => edges.map((e) => `${e.from_id}-${e.type}->${e.to_id}`).sort()

function setupRelations(initial: Edge[] = [{ id: 'rel:CONTAINS:a:b', type: 'CONTAINS', from_id: 'a', to_id: 'b', status: 'approved' }]) {
  const fake = fakeRelations(initial)
  const scope = effectScope()
  const history = scope.run(() => useEditHistory())!
  const recorded = scope.run(() => useRelationHistory(fake.relations, history))!
  return { ...fake, history, recorded }
}

describe('useRelationHistory', () => {
  it('新建：撤销删掉它，重做再建回来', async () => {
    const { recorded, history, edges } = setupRelations()
    expect(await recorded.createBetween('a', 'c', 'PREREQUISITE')).toBe(true)
    expect(history.undoLabel.value).toBe('新建关系 A → C（前置）')
    await history.undo()
    expect(triples(edges.value)).toEqual(['a-CONTAINS->b'])
    await history.redo()
    expect(triples(edges.value)).toEqual(['a-CONTAINS->b', 'a-PREREQUISITE->c'])
  })

  it('改类型：编号变了也能撤销回原类型，再重做', async () => {
    const { recorded, history, edges } = setupRelations()
    await recorded.changeType('rel:CONTAINS:a:b', 'PREREQUISITE')
    expect(edges.value[0]!.id).toBe('rel:PREREQUISITE:a:b')
    expect(history.undoLabel.value).toBe('把 A → B 的类型由“包含”改为“前置”')
    await history.undo()
    expect(triples(edges.value)).toEqual(['a-CONTAINS->b'])
    await history.redo()
    expect(triples(edges.value)).toEqual(['a-PREREQUISITE->b'])
  })

  it('反转：撤销再反转回来', async () => {
    const { recorded, history, edges } = setupRelations()
    await recorded.reverseRelation('rel:CONTAINS:a:b')
    expect(triples(edges.value)).toEqual(['b-CONTAINS->a'])
    expect(history.undoLabel.value).toBe('反转 A → B（包含）')
    await history.undo()
    expect(triples(edges.value)).toEqual(['a-CONTAINS->b'])
    await history.redo()
    expect(triples(edges.value)).toEqual(['b-CONTAINS->a'])
  })

  it('删除：撤销按原类型和端点重新建立，重做再删掉', async () => {
    const { recorded, history, edges } = setupRelations()
    await recorded.deleteRelation('rel:CONTAINS:a:b')
    expect(history.undoLabel.value).toBe('删除关系 A → B（包含）')
    await history.undo()
    expect(triples(edges.value)).toEqual(['a-CONTAINS->b'])
    await history.redo()
    expect(edges.value).toEqual([])
  })

  it('“相关”无方向：存成另一个方向也能找回', async () => {
    const { recorded, history, edges, idOf } = setupRelations([])
    await recorded.createBetween('a', 'b', 'RELATED_TO')
    // 后端把它存成了 b → a
    edges.value = [{ id: idOf({ type: 'RELATED_TO', from_id: 'b', to_id: 'a' }), type: 'RELATED_TO', from_id: 'b', to_id: 'a', status: 'draft' }]
    expect(await history.undo()).toBe(true)
    expect(edges.value).toEqual([])
  })

  it('操作本身失败不进记录；反向操作失败或关系已不在时该步移除', async () => {
    const { recorded, history, edges, fail } = setupRelations()
    fail.value = true
    expect(await recorded.changeType('rel:CONTAINS:a:b', 'PREREQUISITE')).toBe(false)
    expect(history.canUndo.value).toBe(false)
    fail.value = false

    await recorded.createBetween('a', 'c', 'CONTAINS')
    edges.value = edges.value.filter((e) => e.to_id !== 'c') // 别人把它删了
    expect(await history.undo()).toBe(false)
    expect(history.canUndo.value).toBe(false)
    expect(history.notice.value?.tone).toBe('error')
  })

  it('撤销、重做执行的反向操作不会再被记一遍；面板里的“添加关系”也进记录', async () => {
    const { recorded, history, raw, edges } = setupRelations()
    await recorded.deleteRelation('rel:CONTAINS:a:b')
    await history.undo()
    await history.redo()
    // 来回一趟之后记录里仍然只有这一步，没有多出“新建”“删除”
    expect(history.undoLabel.value).toBe('删除关系 A → B（包含）')
    expect(history.canRedo.value).toBe(false)
    await history.undo()
    expect(history.canUndo.value).toBe(false)
    expect(history.redoLabel.value).toBe('删除关系 A → B（包含）')

    raw.fromId.value = 'a'
    raw.toId.value = 'd'
    raw.draftType.value = 'EXAMPLE_OF'
    expect(await recorded.createRelation()).toBe(true)
    expect(raw.toId.value).toBe(null)
    expect(history.undoLabel.value).toBe('新建关系 A → D（应用实例）')
    expect(triples(edges.value)).toContain('a-EXAMPLE_OF->d')
    // 起点或终点没选：交回原来的校验提示，不进记录
    raw.toId.value = null
    await recorded.createRelation()
    expect(raw.createRelation).toHaveBeenCalledTimes(1)
  })
})
