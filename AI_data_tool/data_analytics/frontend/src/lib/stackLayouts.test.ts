import { describe, it, expect } from 'vitest'
import { stackBelow } from './stackLayouts'

const overlaps = (a: { x: number; y: number; w: number; h: number }, b: typeof a) =>
  a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h

describe('stackBelow (F-15)', () => {
  it('places three new widgets below the page and below each other, never on top of one another', () => {
    const page = [{ x: 0, y: 0, w: 6, h: 4 }, { x: 6, y: 0, w: 6, h: 7 }]
    const got = stackBelow(page, [{ w: 6, h: 5 }, { w: 12, h: 4 }, { w: 6, h: 5 }])
    expect(got.map(b => b.y)).toEqual([7, 12, 16])
    const all = [...page, ...got]
    for (let i = 0; i < all.length; i++) for (let j = i + 1; j < all.length; j++) expect(overlaps(all[i], all[j])).toBe(false)
  })

  it('starts at the top of an empty page', () => {
    expect(stackBelow([], [{ w: 6, h: 5 }])).toEqual([{ x: 0, y: 0, w: 6, h: 5 }])
  })
})
