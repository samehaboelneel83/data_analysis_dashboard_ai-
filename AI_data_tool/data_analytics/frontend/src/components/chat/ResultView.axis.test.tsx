import { describe, it, expect, afterEach } from 'vitest'
import { render, waitFor } from '@testing-library/react'
import ResultView from './ResultView'
import { DirectionContext } from '../../contexts/DirectionContext'
import type { AgentResult } from '../../services/api'

/**
 * QA4-V9: the Ask AI answer chart's category labels overlapped (an Arabic
 * question about revenue per region: four region names drawn on top of each
 * other). The renderer is the Builder's, but the chat never told it how wide
 * the chart was, so the shared axis planner assumed a nominal 560px plot and
 * judged the labels to fit upright. The answer chart is now measured the same
 * way a Builder tile is, so the same ladder applies: tilt, thin, clip.
 */

const realRect = Element.prototype.getBoundingClientRect
function sizeEverything(w: number, h: number) {
  Element.prototype.getBoundingClientRect = () => ({
    width: w, height: h, top: 0, left: 0, right: w, bottom: h, x: 0, y: 0, toJSON() {},
  }) as DOMRect
}
afterEach(() => { Element.prototype.getBoundingClientRect = realRect })

const REGIONS = ['القاهرة الكبرى', 'الإسكندرية', 'الدلتا والقناة', 'صعيد مصر']
const result = (names: string[]): AgentResult => ({
  step: 1, columns: ['region', 'revenue'],
  rows: names.map((n, i) => [n, 1000 * (i + 1)]),
  total: names.length, truncated: false,
} as unknown as AgentResult)

function renderAnswer(names: string[], rtl: boolean) {
  const dir = {
    direction: rtl ? 'rtl' as const : 'ltr' as const, rtl,
    setDirection: () => {}, language: rtl ? 'ar' as const : 'en' as const, setLanguage: () => {},
  }
  return render(
    <DirectionContext.Provider value={dir}>
      <ResultView results={[result(names)]} presentation={{ format: 'bar', limit: null } as never} />
    </DirectionContext.Provider>,
  )
}

/** The rotation of each drawn x tick, from its `rotate(a, x, y)` transform
 *  (0 when upright), and the text it shows. */
async function xTicks(container: HTMLElement) {
  await waitFor(() =>
    expect(container.querySelectorAll('.recharts-xAxis .recharts-cartesian-axis-tick-value').length)
      .toBeGreaterThan(0))
  return [...container.querySelectorAll('.recharts-xAxis .recharts-cartesian-axis-tick-value')].map(el => {
    const m = /rotate\((-?[\d.]+)/.exec(el.getAttribute('transform') ?? '')
    return { angle: m ? Number(m[1]) : 0, text: el.textContent ?? '', anchor: el.getAttribute('text-anchor') }
  })
}

describe('the answer chart lays out its category axis like a Builder chart (QA4-V9)', () => {
  it('tilts four Arabic region names in a chat-width chart instead of overlapping them', async () => {
    sizeEverything(360, 240)
    const { container } = renderAnswer(REGIONS, true)
    const ticks = await xTicks(container)
    expect(ticks).toHaveLength(4)
    // RTL: the tilt mirrors (positive angle, `start` anchor) rather than the
    // canvas being flipped -- the same rule the Builder's axes follow.
    for (const t of ticks) {
      expect(t.angle).toBeGreaterThan(0)
      expect(t.anchor).toBe('start')
    }
  })

  it('tilts the other way in LTR', async () => {
    sizeEverything(360, 240)
    const { container } = renderAnswer(REGIONS, false)
    const ticks = await xTicks(container)
    for (const t of ticks) {
      expect(t.angle).toBeLessThan(0)
      expect(t.anchor).toBe('end')
    }
  })

  it('keeps short labels upright when the chart is wide enough for them', async () => {
    sizeEverything(900, 240)
    const { container } = renderAnswer(['North', 'South', 'East', 'West'], false)
    const ticks = await xTicks(container)
    expect(ticks.map(t => t.angle)).toEqual([0, 0, 0, 0])
  })

  it('clips a long category name with an ellipsis', async () => {
    sizeEverything(360, 240)
    const long = 'Northern Industrial Development Region'
    const { container } = renderAnswer([long, 'South', 'East', 'West'], false)
    const ticks = await xTicks(container)
    const first = ticks.find(t => t.text.startsWith('Northern'))!
    expect(first.text.endsWith('…')).toBe(true)
    expect(first.text.length).toBeLessThan(long.length)
  })
})
