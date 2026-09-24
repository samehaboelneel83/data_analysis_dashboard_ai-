import { describe, it, expect } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { CrossFilterProvider, useCrossFilter } from './CrossFilterContext'

function wrapper({ children }: { children: React.ReactNode }) {
  return <CrossFilterProvider>{children}</CrossFilterProvider>
}

describe('CrossFilterContext multi-value + page scoping', () => {
  it('carries an array value from emitMultiFilter and stamps the source page', () => {
    const { result } = renderHook(() => useCrossFilter(), { wrapper })
    act(() => result.current.emitMultiFilter(1, 100, 'region', ['North', 'South'], 'region in (North, South)'))
    expect(result.current.activeFilters[0].value).toEqual(['North', 'South'])
    expect(result.current.activeFilters[0].sourcePageId).toBe(100)
  })

  it('only returns filters emitted on the same page by default', () => {
    const { result } = renderHook(() => useCrossFilter(), { wrapper })
    act(() => result.current.emitFilter(1, 100, 'region', 'North', 'region = North'))
    expect(result.current.getFiltersFor(2, 100)).toHaveLength(1)
    expect(result.current.getFiltersFor(2, 200)).toHaveLength(0)
  })

  it('lets a widget marked syncAllPages reach every page', () => {
    const { result } = renderHook(() => useCrossFilter(), { wrapper })
    act(() => {
      result.current.setInteraction(1, { broadcasts: true, receives: true, syncAllPages: true })
      result.current.emitFilter(1, 100, 'region', 'North', 'region = North')
    })
    expect(result.current.getFiltersFor(2, 200)).toHaveLength(1)
  })
})

describe('CrossFilterContext per-pair actions (manual mode)', () => {
  it('a source with explicit actions reaches only its listed targets — and transitively theirs', () => {
    const { result } = renderHook(() => useCrossFilter(), { wrapper })
    act(() => {
      // A(1) acts on B(2); B(2) acts on C(3); D(4) is off the graph.
      result.current.setInteraction(1, { broadcasts: true, receives: true, actions: [{ targetId: 2, mode: 'filter' }] })
      result.current.setInteraction(2, { broadcasts: true, receives: true, actions: [{ targetId: 3, mode: 'filter' }] })
      result.current.emitFilter(1, 100, 'region', 'North', 'region = North')
    })
    expect(result.current.getFiltersFor(2, 100)).toHaveLength(1)  // direct A→B
    expect(result.current.getFiltersFor(3, 100)).toHaveLength(1)  // transitive A→B→C
    expect(result.current.getFiltersFor(4, 100)).toHaveLength(0)  // not on the action graph
  })

  it('terminates on a cycle rather than looping forever', () => {
    const { result } = renderHook(() => useCrossFilter(), { wrapper })
    act(() => {
      result.current.setInteraction(1, { broadcasts: true, receives: true, actions: [{ targetId: 2, mode: 'filter' }] })
      result.current.setInteraction(2, { broadcasts: true, receives: true, actions: [{ targetId: 1, mode: 'filter' }] })
      result.current.emitFilter(1, 100, 'x', 'v', 'x = v')
    })
    expect(result.current.getFiltersFor(2, 100)).toHaveLength(1)  // A→B still reaches
    expect(result.current.getFiltersFor(1, 100)).toHaveLength(0)  // source never receives its own filter
  })
})
