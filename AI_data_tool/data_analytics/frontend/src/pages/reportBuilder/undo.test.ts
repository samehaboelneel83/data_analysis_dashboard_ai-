import { describe, it, expect } from 'vitest'
import { UndoStack, IdAliases, describeConfigChange, changedKeys, COALESCE_MS, UNDO_LIMIT } from './undo'

const noop = async () => {}
const cmd = (label: string, coalesceKey?: string) => ({ label, undo: noop, redo: noop, coalesceKey })

describe('UndoStack', () => {
  it('undoes the latest edit first and exposes its sentence', () => {
    const s = new UndoStack()
    s.push(cmd('Add Bar Chart'), 0)
    s.push(cmd('Delete "Sales"'), 10_000)
    expect(s.undoLabel).toBe('Delete "Sales"')
    const e = s.takeUndo()!
    s.undone(e)
    expect(s.undoLabel).toBe('Add Bar Chart')
    expect(s.redoLabel).toBe('Delete "Sales"')
  })

  it('a new edit after an undo clears redo (history forks)', () => {
    const s = new UndoStack()
    s.push(cmd('A'), 0)
    s.undone(s.takeUndo()!)
    expect(s.redoLabel).toBe('A')
    s.push(cmd('B'), 5)
    expect(s.redoLabel).toBeNull()
  })

  it('coalesces a burst on one key: keeps the FIRST undo, the LAST redo', async () => {
    const s = new UndoStack()
    const calls: string[] = []
    s.push({ label: 'title 1', coalesceKey: 'cfg:1:title', undo: async () => { calls.push('undo-first') }, redo: async () => { calls.push('redo-1') } }, 0)
    s.push({ label: 'title 2', coalesceKey: 'cfg:1:title', undo: async () => { calls.push('undo-second') }, redo: async () => { calls.push('redo-2') } }, COALESCE_MS - 1)
    expect(s.past).toHaveLength(1)
    expect(s.undoLabel).toBe('title 2')
    const e = s.takeUndo()!
    await e.undo(); await e.redo()
    expect(calls).toEqual(['undo-first', 'redo-2'])
  })

  it('does not coalesce across keys or after the window', () => {
    const s = new UndoStack()
    s.push(cmd('a', 'k1'), 0)
    s.push(cmd('b', 'k2'), 1)
    s.push(cmd('c', 'k2'), 1 + COALESCE_MS + 1)
    expect(s.past).toHaveLength(3)
  })

  it('a redone entry never merges with the next edit', () => {
    const s = new UndoStack()
    s.push(cmd('a', 'k'), 0)
    s.undone(s.takeUndo()!)
    s.redone(s.takeRedo()!)
    s.push(cmd('b', 'k'), 1)
    expect(s.past).toHaveLength(2)
  })

  it('nothing merges across an undo, even inside the time window', () => {
    const s = new UndoStack()
    s.push(cmd('a', 'k'), 0)
    s.push(cmd('b', 'x'), 1)
    s.undone(s.takeUndo()!)
    s.push(cmd('c', 'k'), 2)
    expect(s.past.map(e => e.label)).toEqual(['a', 'c'])
  })

  it('caps history', () => {
    const s = new UndoStack()
    for (let i = 0; i < UNDO_LIMIT + 5; i++) s.push(cmd(`e${i}`), i * 10_000)
    expect(s.past).toHaveLength(UNDO_LIMIT)
    expect(s.past[0].label).toBe('e5')
  })
})

describe('IdAliases', () => {
  it('follows a recreate chain to the current id', () => {
    const a = new IdAliases()
    a.set(10, 20)   // delete undone -> recreated as 20
    a.set(20, 31)   // deleted again, recreated as 31
    expect(a.resolve(10)).toBe(31)
    expect(a.resolve(99)).toBe(99)
  })
  it('survives a cycle', () => {
    const a = new IdAliases()
    a.set(1, 2); a.set(2, 1)
    expect([1, 2]).toContain(a.resolve(1))
  })
})

describe('sentences', () => {
  it('names a single setting change with before and after', () => {
    expect(describeConfigChange('Bar Chart', {}, { x_col: 'region' }, 'Bar Chart', 'Bar Chart'))
      .toBe('Change x col of "Bar Chart" from none to region')
  })
  it('names a rename', () => {
    expect(describeConfigChange('A', { k: 1 }, { k: 1 }, 'A', 'B')).toBe('Rename "A" to "B"')
  })
  it('counts several changes', () => {
    expect(describeConfigChange('W', { a: 1 }, { a: 2, b: 3 }, 'W', 'W2')).toBe('Change 3 settings of "W"')
  })
  it('changedKeys compares values, not identity', () => {
    expect(changedKeys({ a: [1, 2] }, { a: [1, 2] })).toEqual([])
  })
})
