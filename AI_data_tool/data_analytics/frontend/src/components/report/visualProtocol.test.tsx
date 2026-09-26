/**
 * E16: the custom-visual protocol is versioned, and there is an SDK.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { CustomVisual, VISUAL_PROTOCOL_VERSION } from './CustomVisual'
import sdkSource from '../../../public/sdk/datalytics-visual-1.js?raw'

function messageFrom(source: unknown, data: unknown) {
  const ev = new MessageEvent('message', { data, origin: 'null' })
  Object.defineProperty(ev, 'source', { value: source, configurable: true })
  return ev
}

describe('the host', () => {
  beforeEach(() => vi.restoreAllMocks())

  const draw = (onSelect?: (v: unknown) => void) => {
    render(<CustomVisual url="/sdk/example-bars.html" title="Sales bars" data={{ rows: [{ name: 'North', value: 3 }] }}
      widgetType="custom_visual" onSelect={onSelect} />)
    const frame = screen.getByTitle('Sales bars') as HTMLIFrameElement
    const post = vi.spyOn(frame.contentWindow!, 'postMessage')
    return { frame, post }
  }

  it('sends the data with its version and the context a visual needs', () => {
    const { frame, post } = draw(vi.fn())
    frame.dispatchEvent(new Event('load'))
    const [msg, target] = post.mock.calls.at(-1)!
    expect(target).toBe('*')
    expect(msg).toMatchObject({
      type: 'datalytics:data', version: VISUAL_PROTOCOL_VERSION, data: { rows: [{ name: 'North', value: 3 }] },
      context: { title: 'Sales bars', widget_type: 'custom_visual', locale: 'en', dir: 'ltr', can_select: true },
    })
    expect(Object.keys((msg as { context: { theme: object } }).context.theme).sort()).toEqual(['accent', 'muted', 'surface', 'text'])
  })

  it('answers a hello with its version and capabilities, then the data', () => {
    const { frame, post } = draw(vi.fn())
    window.dispatchEvent(messageFrom(frame.contentWindow, { type: 'datalytics:hello', version: 1 }))
    const types = post.mock.calls.map(c => (c[0] as { type: string }).type)
    expect(types.slice(-2)).toEqual(['datalytics:hello', 'datalytics:data'])
    expect(post.mock.calls.at(-2)![0]).toEqual({ type: 'datalytics:hello', version: 1, capabilities: ['select', 'clear'] })
  })

  it('a display-only visual is told it cannot select, and its selections do nothing', () => {
    const { frame, post } = draw(undefined)
    window.dispatchEvent(messageFrom(frame.contentWindow, { type: 'datalytics:hello', version: 1 }))
    expect(post.mock.calls.at(-2)![0]).toMatchObject({ capabilities: [] })
    expect((post.mock.calls.at(-1)![0] as { context: { can_select: boolean } }).context.can_select).toBe(false)
  })

  it('ignores a hello from any other window', () => {
    const { post } = draw(vi.fn())
    const before = post.mock.calls.length
    window.dispatchEvent(messageFrom({}, { type: 'datalytics:hello', version: 1 }))
    expect(post.mock.calls.length).toBe(before)
  })
})

describe('the SDK', () => {
  /** Runs the SDK against a stand-in window whose parent records messages. */
  function load() {
    const parent = { postMessage: vi.fn() }
    let listener: ((e: { source: unknown; data: unknown }) => void) | null = null
    const global: Record<string, unknown> = {
      parent, console,
      addEventListener: (_: string, fn: typeof listener) => { listener = fn },
    }
    new Function('window', sdkSource)(global)
    const api = global.DatalyticsVisual as {
      version: number; host: { version: number; capabilities: string[] } | null
      onData: (cb: (d: unknown, c: unknown) => void) => () => void
      select: (v: unknown) => boolean; clear: () => boolean
    }
    const fromHost = (data: unknown, source: unknown = parent) => listener!({ source, data })
    return { api, parent, fromHost }
  }

  it('says hello on load', () => {
    const { parent, api } = load()
    expect(api.version).toBe(1)
    expect(parent.postMessage).toHaveBeenCalledWith({ type: 'datalytics:hello', version: 1 }, '*')
  })

  it('hands data and context to the visual, including data that came before it listened', () => {
    const { api, fromHost } = load()
    fromHost({ type: 'datalytics:data', version: 1, data: { rows: [1] }, context: { locale: 'ar' } })
    const cb = vi.fn()
    api.onData(cb)
    expect(cb).toHaveBeenCalledWith({ rows: [1] }, { locale: 'ar' })
    fromHost({ type: 'datalytics:data', version: 1, data: { rows: [2] }, context: {} })
    expect(cb).toHaveBeenLastCalledWith({ rows: [2] }, {})
  })

  it('ignores messages from anything but the host', () => {
    const { api, fromHost } = load()
    const cb = vi.fn()
    api.onData(cb)
    fromHost({ type: 'datalytics:data', data: { rows: [9] } }, {})
    expect(cb).not.toHaveBeenCalled()
  })

  it('selects and clears only when the host said it can', () => {
    const { api, parent, fromHost } = load()
    fromHost({ type: 'datalytics:hello', version: 1, capabilities: ['select', 'clear'] })
    expect(api.select('Europe')).toBe(true)
    expect(parent.postMessage).toHaveBeenLastCalledWith({ type: 'datalytics:select', value: 'Europe', version: 1 }, '*')
    expect(api.clear()).toBe(true)
    const display = load()
    display.fromHost({ type: 'datalytics:hello', version: 1, capabilities: [] })
    expect(display.api.select('Europe')).toBe(false)
  })
})
