import { describe, it, expect, vi, beforeAll, afterEach } from 'vitest'
import { render, waitFor } from '@testing-library/react'
import WidgetRenderer from './WidgetRenderer'
import { CrossFilterProvider } from './CrossFilterContext'
import { DirectionProvider } from '../../contexts/DirectionContext'
import { widgetDataApi } from '../../services/api'
import type { Widget } from '../../types/report'

vi.mock('../../services/api', () => ({
  pinsApi: { create: vi.fn().mockResolvedValue({}), list: vi.fn().mockResolvedValue([]), remove: vi.fn().mockResolvedValue(undefined) },
  widgetDataApi: { query: vi.fn() },
}))

const CITIES = ['Tokyo', 'Hamburg', 'Sydney', 'Sao Paulo', 'Dubai',
                'Singapore', 'London', 'New York', 'Frankfurt', 'Los Angeles']

// Mutable so one suite can render both a wide and a narrow tile.
let TW = 890, TH = 420
beforeAll(() => {
  Element.prototype.getBoundingClientRect = () => ({
    width: TW, height: TH, top: 0, left: 0, right: TW, bottom: TH, x: 0, y: 0, toJSON() {},
  }) as DOMRect
})
afterEach(() => { localStorage.clear(); document.documentElement.dir = 'ltr' })

const widget: Widget = {
  id: 1, page_id: 100, widget_type: 'bar', title: 'BAR CHART',
  config: { dimension: 'name' }, layout: { x: 0, y: 0, w: 12, h: 6 },
  created_at: '2026-01-01',
}

async function draw(rtl: boolean) {
  vi.mocked(widgetDataApi.query).mockResolvedValue({
    rows: CITIES.map((name, i) => ({ name, value: 10 + i * 3 })), sampled: false,
  } as never)
  if (rtl) {
    localStorage.setItem('datalytics.direction', 'rtl')
    document.documentElement.dir = 'rtl'
  }
  const { container } = render(
    <DirectionProvider>
      <CrossFilterProvider>
        <div style={{ width: TW, height: TH }}>
          <WidgetRenderer widget={widget} datasetId={10} />
        </div>
      </CrossFilterProvider>
    </DirectionProvider>)
  await waitFor(() => {
    if (!container.querySelector('.recharts-xAxis .recharts-cartesian-axis-tick-value')) {
      throw new Error('axis not drawn yet')
    }
  })
  const xt = Array.from(container.querySelectorAll('.recharts-xAxis .recharts-cartesian-axis-tick-value'))
  const yt = container.querySelector('.recharts-yAxis .recharts-cartesian-axis-tick-value')
  return {
    count: xt.length,
    transform: xt[0]?.getAttribute('transform') ?? null,
    anchor: xt[0]?.getAttribute('text-anchor'),
    yTickX: Number(yt?.getAttribute('x')),
  }
}

/**
 * The whole chain, not one link: language -> DirectionProvider -> widgetIsRtl
 * -> WidgetRenderer -> MeasuredChart -> xAxisProps -> the rendered SVG.
 *
 * Every part of this was individually correct while the app still drew tilted,
 * crowded Arabic axes, because the planner was being handed a NOMINAL tile
 * size rather than the measured one -- a seam nothing tested. At the nominal
 * 560 the slot is 47.6px and "Los Angeles" needs 74.2, so the axis rotated on
 * a tile where the labels fit flat.
 */
describe('SEAM: an Arabic page renders its category axis from the MEASURED tile', () => {
  it('puts the value axis on the right, proving rtl reached the axis builder', async () => {
    const r = await draw(true)
    expect(r.yTickX).toBeGreaterThan(TW / 2)
  })

  it('leaves labels upright on a wide tile, where they genuinely fit', async () => {
    TW = 890
    const r = await draw(true)
    expect(r.count).toBe(CITIES.length)
    expect(r.anchor).toBe('middle')      // middle == upright
    expect(r.transform).toBeNull()       // and no rotation at all
  })

  it('tilts them the MIRRORED way once the tile is too narrow', async () => {
    TW = 380
    const r = await draw(true)
    // Positive rotation with a `start` anchor is the RTL mirror. The negative
    // angle that reads correctly in English sends the text up into the plot
    // when the anchor flips.
    expect(r.transform).toMatch(/rotate\(30/)
    expect(r.anchor).toBe('start')
    TW = 890
  })

  it('tilts the other way on the same narrow tile in English', async () => {
    TW = 380
    const r = await draw(false)
    expect(r.transform).toMatch(/rotate\(-30/)
    expect(r.anchor).toBe('end')
    TW = 890
  })
})
