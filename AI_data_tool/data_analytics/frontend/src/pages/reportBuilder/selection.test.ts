import { describe, it, expect } from 'vitest'
import { clickSelection, selectionCount, EMPTY_SELECTION } from './selection'

describe('canvas selection (QA3 A1)', () => {
  it('click → shift+click → shift+click counts every outlined widget; the last is primary', () => {
    let s = clickSelection(EMPTY_SELECTION, 1, false)
    expect(selectionCount(s)).toBe(1)
    s = clickSelection(s, 2, true)
    expect(selectionCount(s)).toBe(2)
    expect([...s.multi]).toEqual([1, 2])
    expect(s.primary).toBe(2)
    s = clickSelection(s, 3, true)
    expect(selectionCount(s)).toBe(3)
    expect([...s.multi]).toEqual([1, 2, 3])
    expect(s.primary).toBe(3)
  })

  it('shift+click on a selected widget removes it; one left becomes a single selection', () => {
    let s = clickSelection(clickSelection(clickSelection(EMPTY_SELECTION, 1, false), 2, true), 2, true)
    expect(s).toEqual({ primary: 1, multi: new Set() })
    s = clickSelection(s, 1, true)
    expect(selectionCount(s)).toBe(0)
  })

  it('removing the primary hands Properties to the last one still selected', () => {
    let s = clickSelection(EMPTY_SELECTION, 1, false)
    s = clickSelection(clickSelection(s, 2, true), 3, true)
    s = clickSelection(s, 3, true)
    expect(s.primary).toBe(2)
    expect(selectionCount(s)).toBe(2)
  })

  it('a plain click after a multi-selection starts over', () => {
    const s = clickSelection(clickSelection(clickSelection(EMPTY_SELECTION, 1, false), 2, true), 5, false)
    expect(s).toEqual({ primary: 5, multi: new Set() })
  })

  it('shift+click with nothing selected selects that one widget', () => {
    expect(clickSelection(EMPTY_SELECTION, 4, true)).toEqual({ primary: 4, multi: new Set() })
  })
})
