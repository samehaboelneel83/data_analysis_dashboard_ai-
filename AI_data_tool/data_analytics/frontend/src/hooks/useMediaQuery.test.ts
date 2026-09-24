import { describe, it, expect, vi, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useMediaQuery } from './useMediaQuery'

function mockMatchMedia(initialMatches: boolean) {
  let listener: (() => void) | null = null
  const mql = {
    matches: initialMatches,
    media: '',
    onchange: null,
    addEventListener: (_: string, cb: () => void) => { listener = cb },
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: () => false,
  }
  window.matchMedia = vi.fn().mockReturnValue(mql) as unknown as typeof window.matchMedia
  return {
    change(next: boolean) {
      mql.matches = next
      listener?.()
    },
  }
}

const realMatchMedia = window.matchMedia
afterEach(() => { window.matchMedia = realMatchMedia })

describe('useMediaQuery', () => {
  it('returns the current match state on mount', () => {
    mockMatchMedia(true)
    const { result } = renderHook(() => useMediaQuery('(max-width: 767px)'))
    expect(result.current).toBe(true)
  })

  it('updates when the media query match state changes', () => {
    const control = mockMatchMedia(false)
    const { result } = renderHook(() => useMediaQuery('(max-width: 767px)'))
    expect(result.current).toBe(false)

    act(() => control.change(true))
    expect(result.current).toBe(true)
  })
})
