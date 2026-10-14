import { describe, expect, it } from 'vitest'
import { act, render } from '@testing-library/react'
import { LOOK_EVENT, useLookChrome, type LookMode } from './lookChrome'

function Open({ mode }: { mode?: string | null }) { useLookChrome(mode); return null }

describe("a dashboard's look and the app around it", () => {
  it('tells the shell its mode while open, and gives it back on leaving', () => {
    const heard: LookMode[] = []
    const on = (e: Event) => heard.push((e as CustomEvent<LookMode>).detail)
    window.addEventListener(LOOK_EVENT, on)
    const { rerender, unmount } = render(<Open mode="dark" />)
    expect(heard.at(-1)).toBe('dark')
    act(() => rerender(<Open mode="light" />))
    expect(heard.at(-1)).toBe('light')
    // A dashboard with no look of its own asks for nothing.
    act(() => rerender(<Open mode="auto" />))
    expect(heard.at(-1)).toBeNull()
    act(() => rerender(<Open mode="dark" />))
    unmount()
    expect(heard.at(-1)).toBeNull()
    window.removeEventListener(LOOK_EVENT, on)
  })
})
