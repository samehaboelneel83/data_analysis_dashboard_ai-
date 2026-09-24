import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { CustomVisual } from './WidgetRenderer'

/**
 * A custom visual that can select, not just display.
 *
 * The widget already posts its shaped data INTO an author-supplied page. The
 * page could draw anything and select nothing — so a custom visual sat outside
 * every dashboard's interaction model, and clicking a region on a hand-built
 * map filtered none of the charts beside it.
 *
 * **The security model is the interesting part, and it is deliberately narrow.**
 * The frame is `sandbox="allow-scripts"`, so its origin is opaque — every
 * message from it arrives with `origin === "null"`, which is exactly what a
 * hostile sandboxed frame elsewhere on the page would also send. Origin
 * checking is therefore worthless here, and the honest check is IDENTITY:
 * `event.source === iframe.contentWindow` names one frame and nothing else.
 *
 * And the frame chooses the VALUE only. The report chooses the column (the
 * widget's own dimension) and applies it through the same gate a click on a bar
 * goes through, so a custom visual has exactly the power of a click — it cannot
 * name a column it was not given, and cannot filter a page whose interaction
 * settings forbid it.
 */

function messageFrom(source: unknown, data: unknown, origin = 'null') {
  const ev = new MessageEvent('message', { data, origin })
  // jsdom will not let `source` be set through the constructor for a plain
  // object, and the component compares by identity, so define it directly.
  Object.defineProperty(ev, 'source', { value: source, configurable: true })
  return ev
}

const draw = (onSelect = vi.fn()) => {
  const utils = render(
    <CustomVisual url="https://viz.example.invalid/map" title="Hand-built map"
      data={{ rows: [] }} onSelect={onSelect} />)
  const frame = screen.getByTitle('Hand-built map') as HTMLIFrameElement
  return { ...utils, frame, onSelect }
}

beforeEach(() => vi.clearAllMocks())

describe('a selection coming back out', () => {
  it('applies a value the frame sends', async () => {
    const { frame, onSelect } = draw()
    window.dispatchEvent(messageFrom(frame.contentWindow,
      { type: 'datalytics:select', value: 'Europe' }))
    await waitFor(() => expect(onSelect).toHaveBeenCalledWith('Europe'))
  })

  it('clears when the frame says the selection is gone', async () => {
    const { frame, onSelect } = draw()
    window.dispatchEvent(messageFrom(frame.contentWindow, { type: 'datalytics:clear' }))
    await waitFor(() => expect(onSelect).toHaveBeenCalledWith(null))
  })

  it('passes a numeric value through as a number', async () => {
    // A year or an id selected in the frame must not arrive as "2024".
    const { frame, onSelect } = draw()
    window.dispatchEvent(messageFrom(frame.contentWindow,
      { type: 'datalytics:select', value: 2024 }))
    await waitFor(() => expect(onSelect).toHaveBeenCalledWith(2024))
  })
})

describe('what it refuses', () => {
  it('ignores a message from any other window', async () => {
    /**
     * The whole security argument. Another sandboxed iframe on the page sends
     * `origin: "null"` too, so only the frame's own identity distinguishes it.
     */
    const { onSelect } = draw()
    const impostor = { postMessage: () => {} }
    window.dispatchEvent(messageFrom(impostor,
      { type: 'datalytics:select', value: 'Europe' }))
    await new Promise(r => setTimeout(r, 20))
    expect(onSelect).not.toHaveBeenCalled()
  })

  it('ignores a message with no source at all', async () => {
    const { onSelect } = draw()
    window.dispatchEvent(messageFrom(null,
      { type: 'datalytics:select', value: 'Europe' }))
    await new Promise(r => setTimeout(r, 20))
    expect(onSelect).not.toHaveBeenCalled()
  })

  it('ignores message types it does not know', async () => {
    const { frame, onSelect } = draw()
    window.dispatchEvent(messageFrom(frame.contentWindow,
      { type: 'datalytics:navigate', url: 'https://evil.example.invalid' }))
    window.dispatchEvent(messageFrom(frame.contentWindow, { type: 'select', value: 'x' }))
    await new Promise(r => setTimeout(r, 20))
    expect(onSelect).not.toHaveBeenCalled()
  })

  it('ignores a payload that is not an object', async () => {
    const { frame, onSelect } = draw()
    for (const junk of ['datalytics:select', 42, null, undefined]) {
      window.dispatchEvent(messageFrom(frame.contentWindow, junk))
    }
    await new Promise(r => setTimeout(r, 20))
    expect(onSelect).not.toHaveBeenCalled()
  })

  it('does not let the frame choose which column is filtered', async () => {
    /**
     * The frame sends a VALUE. The report supplies the column — its own
     * dimension — so a custom visual cannot filter on `salary` because it
     * asked to. A `column` in the payload is ignored, not honoured.
     */
    const { frame, onSelect } = draw()
    window.dispatchEvent(messageFrom(frame.contentWindow,
      { type: 'datalytics:select', value: 'Europe', column: 'salary' }))
    await waitFor(() => expect(onSelect).toHaveBeenCalledTimes(1))
    expect(onSelect).toHaveBeenCalledWith('Europe')
  })

  it('stops listening once the widget is gone', async () => {
    // A listener outliving its iframe is both a leak and a way for a later
    // frame to reach a dead handler.
    const { frame, onSelect, unmount } = draw()
    unmount()
    window.dispatchEvent(messageFrom(frame.contentWindow,
      { type: 'datalytics:select', value: 'Europe' }))
    await new Promise(r => setTimeout(r, 20))
    expect(onSelect).not.toHaveBeenCalled()
  })
})

describe('a visual that only displays', () => {
  it('works exactly as before when no handler is given', () => {
    // Two-way is opt-in from the report's side: a widget on a page whose
    // interactions forbid broadcasting gets no handler and must not break.
    render(<CustomVisual url="https://viz.example.invalid/map" title="Display only"
      data={{ rows: [] }} />)
    expect(screen.getByTitle('Display only')).toBeInTheDocument()
  })

  it('still refuses a non-embeddable url', () => {
    render(<CustomVisual url="javascript:alert(1)" title="Bad" data={null} />)
    expect(screen.queryByTitle('Bad')).toBeNull()
  })
})
