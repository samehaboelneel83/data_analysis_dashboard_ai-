import { describe, it, expect } from 'vitest'
import { seedRoleValues } from './helpers'

describe('C-07 round 2: an old scatter opens with its dimension as the X axis', () => {
  it('X shows the dimension it always drew on X; the dimension stays the label', () => {
    const v = seedRoleValues({ dimension: 'height', measure: 'weight' }, 'scatter')
    expect(v.measure2).toBe('height')
    expect(v.measure).toBe('weight')
    expect(v.category).toBe('height')
  })
  it('a scatter with its own X measure is left alone', () => {
    const v = seedRoleValues({ dimension: 'product', measure: 'weight', measure2: 'units' }, 'scatter')
    expect(v.measure2).toBe('units')
  })
})
