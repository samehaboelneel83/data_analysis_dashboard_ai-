import { describe, it, expect, beforeEach } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import { columnKind, describePageFilter, isActive, toQueryFilters, usePageFilters, type PageFilter } from './pageFilters'

describe('page filters', () => {
  it('picks a control from the column type', () => {
    expect(columnKind('numeric')).toBe('number')
    expect(columnKind('integer')).toBe('number')
    expect(columnKind('datetime')).toBe('date')
    expect(columnKind('text', 'date')).toBe('date')
    expect(columnKind('categorical')).toBe('text')
    expect(columnKind('text')).toBe('text')
  })

  it('turns each filter into the plain filters every chart understands', () => {
    const fs: PageFilter[] = [
      { id: 'a', column: 'customer_id', kind: 'range', from: 1, to: 20 },
      { id: 'b', column: 'price', kind: 'range', from: null, to: 100 },
      { id: 'c', column: 'bought', kind: 'dates', from: '2018-01-01', to: '2018-01-31' },
      { id: 'd', column: 'status', kind: 'values', values: ['delivered', 'shipped'] },
      { id: 'e', column: 'city', kind: 'contains', text: ' paulo ' },
    ]
    expect(toQueryFilters(fs)).toEqual([
      { column: 'customer_id', op: 'gte', value: 1 },
      { column: 'customer_id', op: 'lte', value: 20 },
      { column: 'price', op: 'lte', value: 100 },
      { column: 'bought', op: 'gte', value: '2018-01-01' },
      // The whole last day, not just its midnight.
      { column: 'bought', op: 'lte', value: '2018-01-31T23:59:59' },
      { column: 'status', op: 'in', value: ['delivered', 'shipped'] },
      { column: 'city', op: 'like', value: 'paulo' },
    ])
  })

  it('treats an empty filter as no filter', () => {
    expect(isActive({ id: 'x', column: 'p', kind: 'range', from: null, to: null })).toBe(false)
    expect(isActive({ id: 'x', column: 'p', kind: 'values', values: [] })).toBe(false)
    expect(isActive({ id: 'x', column: 'p', kind: 'contains', text: '  ' })).toBe(false)
    expect(toQueryFilters([{ id: 'x', column: 'p', kind: 'range', from: null, to: null }])).toEqual([])
  })

  it('says each filter in a few words', () => {
    expect(describePageFilter({ id: 'a', column: 'customer_id', kind: 'range', from: 1, to: 20 })).toBe('customer_id: 1 – 20')
    expect(describePageFilter({ id: 'b', column: 'price', kind: 'range', from: 1000 })).toBe('price ≥ 1,000')
    expect(describePageFilter({ id: 'c', column: 's', kind: 'values', values: ['a', 'b', 'c', 'd'] })).toBe('s: a, b +2')
  })

  describe('usePageFilters', () => {
    beforeEach(() => localStorage.clear())
    it('keeps each page its own filters, remembered for this viewer', () => {
      const { result, rerender } = renderHook(({ page }) => usePageFilters(7, page), { initialProps: { page: 1 } })
      act(() => result.current.setFilters([{ id: 'a', column: 'p', kind: 'range', from: 1, to: 2 }]))
      expect(result.current.query).toHaveLength(2)
      const first = result.current.query
      rerender({ page: 1 })
      // Same content, same array: charts are memoised on it.
      expect(result.current.query).toBe(first)
      rerender({ page: 2 })
      expect(result.current.filters).toEqual([])
      rerender({ page: 1 })
      expect(result.current.filters).toHaveLength(1)
    })
  })
})
