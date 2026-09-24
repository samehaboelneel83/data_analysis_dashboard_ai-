import { describe, expect, it } from 'vitest'
import { isolines } from './contours'

describe('isolines', () => {
  it('rings a single peak', () => {
    // 3x3 grid, peak in the middle: the 0.5 line crosses every edge around it.
    const segs = isolines([0, 0, 0, 0, 1, 0, 0, 0, 0], 3, 3, 0.5)
    expect(segs).toHaveLength(4)
    for (const [[x0, y0], [x1, y1]] of segs) {
      for (const [x, y] of [[x0, y0], [x1, y1]]) {
        expect(Math.abs(x - 1) + Math.abs(y - 1)).toBeCloseTo(0.5)
      }
    }
  })
  it('draws nothing where the grid never crosses the level', () => {
    expect(isolines([0.2, 0.2, 0.2, 0.2], 2, 2, 0.5)).toEqual([])
    expect(isolines([0.9, 0.9, 0.9, 0.9], 2, 2, 0.5)).toEqual([])
  })
})
