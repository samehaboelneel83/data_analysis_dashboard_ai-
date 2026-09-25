import { describe, it, expect, beforeAll } from 'vitest'
import { render, waitFor } from '@testing-library/react'
import DualAxisBarLineChartRenderer from './DualAxisBarLineChartRenderer'
import DualAxisBarChartRenderer from './DualAxisBarChartRenderer'
import DualAxisLineChartRenderer from './DualAxisLineChartRenderer'
import DualAxisTimeSeriesRenderer from './DualAxisTimeSeriesRenderer'
import ComparativeTimeSeriesRenderer from './ComparativeTimeSeriesRenderer'

/**
 * A dual-axis chart with only one measure must not invent a second series.
 *
 * Photographed on a hospital dashboard: "Volume and wait by department" was
 * configured with one measure, and its legend read `wait_minutes` and `value2`
 * — `value2` being the renderer's own internal data key, shown to a hospital
 * manager as though it were a metric. Behind it sat an empty line and a right-
 * hand axis scaled to nothing.
 *
 * `name={cfg.measure2 ?? 'value2'}` is where it comes from: the fallback treats
 * a missing second measure as a naming problem when it is really an absence.
 * A one-measure dual-axis chart is a perfectly legitimate thing to build — it
 * should simply draw one series.
 */
beforeAll(() => {
  // recharts renders nothing inside a 0x0 ResponsiveContainer, which would make
  // every assertion below pass vacuously. Same polyfill as axisOptions.integration.
  Element.prototype.getBoundingClientRect = () => ({
    width: 600, height: 400, top: 0, left: 0, right: 600, bottom: 400, x: 0, y: 0, toJSON() {},
  }) as DOMRect
})

const RENDERERS = {
  dual_axis_bar_line: DualAxisBarLineChartRenderer,
  dual_axis_bar: DualAxisBarChartRenderer,
  dual_axis_line: DualAxisLineChartRenderer,
  dual_axis_time_series: DualAxisTimeSeriesRenderer,
  comparative_time_series: ComparativeTimeSeriesRenderer,
} as const

const ONE = [{ name: 'Cardiology', value: 70 }, { name: 'ENT', value: 64 }]
const TWO = [{ name: 'Cardiology', value: 70, value2: 9 },
             { name: 'ENT', value: 64, value2: 4 }]

function draw(Renderer: any, rows: any[], cfg: Record<string, unknown>) {
  return render(
    <div style={{ width: 600, height: 400 }}>
      <Renderer rows={rows} data={{ rows }} cfg={cfg} rtl={false} broadcasts={false}
                localSelected={null} onClickPoint={() => {}} />
    </div>)
}

describe.each(Object.entries(RENDERERS))('%s with only one measure', (_name, Renderer) => {
  it('never shows the internal key as a series name', async () => {
    const { container } = draw(Renderer, ONE, { measure: 'wait_minutes' })
    await waitFor(() => expect(container.querySelector('.recharts-wrapper')).toBeTruthy())
    expect(container.textContent).not.toContain('value2')
    // the comparative renderer spells its phantom 'series B' -- same defect
    expect(container.textContent).not.toContain('series B')
  })

  it('still names the measure it does have', async () => {
    const { container } = draw(Renderer, ONE, { measure: 'wait_minutes' })
    await waitFor(() => expect(container.textContent).toContain('wait_minutes'))
  })
})

describe.each(Object.entries(RENDERERS))('%s with two measures', (_name, Renderer) => {
  it('draws and names both', async () => {
    const { container } = draw(Renderer, TWO,
      { measure: 'wait_minutes', measure2: 'length_of_stay_days' })
    await waitFor(() => expect(container.textContent).toContain('wait_minutes'))
    expect(container.textContent).toContain('length_of_stay_days')
  })
})
