import { beforeEach, describe, expect, it } from 'vitest'
import { MAX_OPEN, closeOpen, markOpen, readOpen } from './openReports'

beforeEach(() => sessionStorage.clear())

describe('open reports', () => {
  it('keeps the order of opening, renames in place, and closes', () => {
    markOpen({ id: 1, name: 'Sales' }); markOpen({ id: 2, name: 'HR' }); markOpen({ id: 1, name: 'Sales 2026' })
    expect(readOpen()).toEqual([{ id: 1, name: 'Sales 2026' }, { id: 2, name: 'HR' }])
    expect(closeOpen(1)).toEqual([{ id: 2, name: 'HR' }])
  })
  it('drops the oldest past the limit', () => {
    for (let i = 1; i <= MAX_OPEN + 2; i++) markOpen({ id: i, name: `R${i}` })
    const ids = readOpen().map(r => r.id)
    expect(ids).toHaveLength(MAX_OPEN)
    expect(ids[0]).toBe(3)
  })
})
