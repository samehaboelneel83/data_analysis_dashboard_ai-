import { describe, it, expect } from 'vitest'
import { readingOrder, tabOrder } from './readingOrder'

const w = (id: number, x: number, y: number, wd = 3, h = 2, config: Record<string, unknown> = {}) =>
  ({ id, layout: { x, y, w: wd, h }, config })

describe('reading order (QA3 A8)', () => {
  // KPI 1..4 across the top, a chart under them, stored in a jumbled order
  const page = [w(4, 9, 0), w(5, 0, 2, 12, 5), w(2, 3, 0), w(1, 0, 0), w(3, 6, 0)]

  it('is top to bottom, then left to right', () => {
    expect(readingOrder(page, false).map(x => x.id)).toEqual([1, 2, 3, 4, 5])
  })

  it('is right to left in Arabic', () => {
    expect(readingOrder(page, true).map(x => x.id)).toEqual([4, 3, 2, 1, 5])
  })

  it('follows a move', () => {
    const moved = page.map(x => x.id === 1 ? w(1, 0, 7) : x)
    expect(readingOrder(moved, false).map(x => x.id)).toEqual([2, 3, 4, 5, 1])
  })

  it('a custom Tab order wins; widgets without one follow in reading order', () => {
    const custom = page.map(x => x.id === 3 ? { ...x, config: { tabIndex: 1 } } : x.id === 1 ? { ...x, config: { tabIndex: 2 } } : x)
    expect(tabOrder(custom, false).map(x => x.id)).toEqual([3, 1, 2, 4, 5])
  })

  it('without a custom order, Tab order is reading order', () => {
    expect(tabOrder(page, true).map(x => x.id)).toEqual([4, 3, 2, 1, 5])
  })
})
