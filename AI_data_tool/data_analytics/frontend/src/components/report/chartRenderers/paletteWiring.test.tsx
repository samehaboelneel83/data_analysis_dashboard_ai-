import { describe, it, expect, beforeAll, afterAll } from 'vitest'
import { render, waitFor } from '@testing-library/react'
import { applyTheme, seriesColor } from '../chartUtils'
import BarChartRenderer from './BarChartRenderer'
import LineChartRenderer from './LineChartRenderer'
import DualAxisBarChartRenderer from './DualAxisBarChartRenderer'
import ScatterChartRenderer from './ScatterChartRenderer'
import HistogramRenderer from './HistogramRenderer'

// A report's palette must reach EVERY object on it. Twenty-six renderers drew
// their marks in the app's accent colour or in fixed hexes (#a78bfa for a
// second series...), so choosing a palette changed some charts and not others.
//
// Two guards: the source of every renderer may name a fixed colour only for
// chrome or for a colour that carries meaning (allowed below, each with its
// reason); and a handful of real renders must come out in the palette.

const SOURCES = import.meta.glob('./*Renderer.tsx', { query: '?raw', import: 'default', eager: true }) as Record<string, string>

/** Lines that may name a fixed colour, and why. */
const ALLOWED: RegExp[] = [
  /selected|localSelected|active|hover|focus/i,          // selection / interaction state is chrome
  /goal|Reference|ReferenceLine/,                         // a goal or reference line is an annotation
  /isIncrease/,                                           // waterfall: up is green, down is red -- meaning
  />= target|value >= target/,                            // gauge: target met is green -- meaning
  /var\(--(danger|warning|success)/,                      // status colours are meaning
  /<b style=\{\{ color: 'var\(--accent\)' \}\}>|color: 'var\(--accent\)' \}\}>→/, // model card text emphasis
  /color: '#f59e0b'/,                                     // custom graph: a warning notice, not a mark
  /THEMES\./,
  /stroke: '#fff'/,                                       // a white ring round a hovered point
  /strokeDasharray="6 4"/,                                // the map's drawn radius filter (chrome)
  /fill="var\(--accent\)" fillOpacity=\{0\.12\}$/,        // …and its fill
  /strokeDasharray="2 3" \/>\}/,                          // forecast: the goal line's second stroke
  /good \? 'color-mix/,                                   // model card: a good result is highlighted -- meaning
  /accentId/,                                             // model: the row being explained is highlighted
  /m === metric/,                                         // network: the chosen metric's label (chrome)
]

describe('every renderer draws its data in the report palette', () => {
  it('no data mark is fixed to the accent or to a hex colour', () => {
    const offenders: string[] = []
    for (const [file, src] of Object.entries(SOURCES)) {
      src.split('\n').forEach((line, i) => {
        if (!/var\(--accent\)|['"]#[0-9a-fA-F]{6}['"]/.test(line)) return
        if (ALLOWED.some(r => r.test(line))) return
        offenders.push(`${file}:${i + 1}: ${line.trim().slice(0, 120)}`)
      })
    }
    expect(offenders).toEqual([])
  })
})

describe('a chosen palette colours the charts', () => {
  const PALETTE = ['#101010', '#202020', '#303030', '#404040']
  const original = Element.prototype.getBoundingClientRect
  beforeAll(() => {
    applyTheme('custom:test', { 'custom:test': PALETTE })
    Element.prototype.getBoundingClientRect = () => ({
      width: 600, height: 400, top: 0, left: 0, right: 600, bottom: 400, x: 0, y: 0, toJSON() {},
    }) as DOMRect
  })
  afterAll(() => { applyTheme('default'); Element.prototype.getBoundingClientRect = original })

  const base = { data: {}, cfg: {}, rtl: false, broadcasts: false, localSelected: null, onClickPoint: () => {}, plotW: 600, plotH: 400 }
  const rows = [{ name: 'A', value: 3, value2: 30 }, { name: 'B', value: 5, value2: 50 }, { name: 'C', value: 4, value2: 40 }]
  const paints = (c: HTMLElement) => new Set([...c.querySelectorAll('[fill],[stroke]')]
    .flatMap(e => [e.getAttribute('fill'), e.getAttribute('stroke')]))

  it('seriesColor reads the palette, wrapping round', () => {
    expect([seriesColor(0), seriesColor(1), seriesColor(5)]).toEqual(['#101010', '#202020', '#202020'])
  })

  it.each([
    ['bar', BarChartRenderer, {}],
    ['line', LineChartRenderer, {}],
    ['scatter', ScatterChartRenderer, { rows: [{ x: 1, y: 2, name: 'a' }, { x: 2, y: 3, name: 'b' }] }],
    ['histogram', HistogramRenderer, { rows: [{ name: '0-1', value: 3, bin_start: 0, bin_end: 1 }, { name: '1-2', value: 5, bin_start: 1, bin_end: 2 }] }],
  ] as const)('%s draws its series in the palette', async (_n, R, extra) => {
    const { container } = render(<div style={{ width: 600, height: 400 }}><R {...base} rows={rows} {...(extra as object)} /></div>)
    await waitFor(() => expect(paints(container)).toContain('#101010'), { timeout: 5000 })
  })

  it('a second measure takes the palette\'s second colour, not a fixed purple', async () => {
    const { container } = render(<div style={{ width: 600, height: 400 }}>
      <DualAxisBarChartRenderer {...base} rows={rows} cfg={{ measure2: 'value2' }} /></div>)
    await waitFor(() => {
      const seen = paints(container)
      expect(seen).toContain('#101010')
      expect(seen).toContain('#202020')
      expect(seen).not.toContain('#a78bfa')
    }, { timeout: 5000 })
  })
})
