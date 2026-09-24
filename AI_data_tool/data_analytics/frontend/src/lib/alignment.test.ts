import { describe, it, expect } from 'vitest'
import { alignWidgets, distributeWidgets } from './alignment'

const layouts = {
  1: { x: 0, y: 0, w: 2, h: 2 },
  2: { x: 4, y: 3, w: 2, h: 2 },
  3: { x: 8, y: 6, w: 2, h: 2 },
}

describe('alignWidgets', () => {
  it('aligns left to the minimum x', () => {
    expect(alignWidgets(layouts, 'left')).toEqual({ 1: { x: 0 }, 2: { x: 0 }, 3: { x: 0 } })
  })
  it('aligns right to the maximum right edge (x + w)', () => {
    expect(alignWidgets(layouts, 'right')).toEqual({ 1: { x: 8 }, 2: { x: 8 }, 3: { x: 8 } })
  })
  it('aligns top to the minimum y', () => {
    expect(alignWidgets(layouts, 'top')).toEqual({ 1: { y: 0 }, 2: { y: 0 }, 3: { y: 0 } })
  })
})

describe('distributeWidgets', () => {
  it('spaces widgets evenly between the first and last horizontally', () => {
    const result = distributeWidgets(layouts, 'horizontal')
    expect(result[1].x).toBe(0)
    expect(result[3].x).toBe(8)
    expect(result[2].x).toBe(4)
  })
})
