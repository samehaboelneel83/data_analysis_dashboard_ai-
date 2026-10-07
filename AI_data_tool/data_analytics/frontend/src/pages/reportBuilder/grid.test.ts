import { describe, it, expect, afterEach } from 'vitest'
import { widgetIdAtPoint } from './grid'

function box(el: HTMLElement, left: number, top: number, w: number, h: number) {
  el.getBoundingClientRect = () => ({ left, top, right: left + w, bottom: top + h, width: w, height: h, x: left, y: top, toJSON: () => ({}) })
}

describe('widgetIdAtPoint (QA3 A2)', () => {
  afterEach(() => { document.body.innerHTML = ''; document.documentElement.dir = '' })

  function canvas() {
    const c = document.createElement('div')
    const kpi = document.createElement('div'); kpi.setAttribute('data-widget-id', '7'); box(kpi, 900, 100, 200, 120)
    const bar = document.createElement('div'); bar.setAttribute('data-widget-id', '8'); box(bar, 100, 300, 600, 300)
    // an outline / size tag drawn over the bar, outside its subtree
    const overlay = document.createElement('div'); box(overlay, 100, 300, 600, 300)
    c.append(kpi, bar, overlay)
    document.body.append(c)
    return c
  }

  it('finds the widget under the pointer even with an overlay on top', () => {
    expect(widgetIdAtPoint(canvas(), 400, 450)).toBe(8)
  })

  it('works the same in a right-to-left document', () => {
    document.documentElement.dir = 'rtl'
    const c = canvas()
    expect(widgetIdAtPoint(c, 1000, 150)).toBe(7)
    expect(widgetIdAtPoint(c, 400, 450)).toBe(8)
  })

  it('empty canvas space is no widget', () => {
    expect(widgetIdAtPoint(canvas(), 800, 50)).toBeNull()
  })
})
