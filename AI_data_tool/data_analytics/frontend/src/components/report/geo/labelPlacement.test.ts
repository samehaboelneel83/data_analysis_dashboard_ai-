import { describe, it, expect } from 'vitest'
import { placeLabels } from './labelPlacement'

describe('placeLabels', () => {
  it('leaves an isolated label where it was asked', () => {
    const got = placeLabels([{ id: 'Tokyo', x: 100, y: 80, text: 'Tokyo' }])
    expect(got.Tokyo).toEqual({ x: 100, y: 80 })
  })

  it('moves a second label off a first one that shares its point', () => {
    const got = placeLabels([
      { id: 'London', x: 200, y: 120, text: 'London' },
      { id: 'Frankfurt', x: 200, y: 120, text: 'Frankfurt' },
    ])
    expect(got.London).toEqual({ x: 200, y: 120 })
    expect(got.Frankfurt.x !== 200 || got.Frankfurt.y !== 120).toBe(true)
    const sameSpot = got.London.x === got.Frankfurt.x && got.London.y === got.Frankfurt.y
    expect(sameSpot).toBe(false)
  })
})
