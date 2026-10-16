/**
 * UAT-9: the average of a true/false field (on_time) showed 0.51, not 51%.
 *
 * A boolean is filed under "numeric" by the type probe (pandas counts bool as
 * numeric), so nothing marked it; its average -- the share that is true --
 * was printed as a plain number. The builder now recognises a true/false
 * column from the dataset profile (0 and 1 at both ends, every percentile 0
 * or 1) and, where the author set no format, shows its average as a percent.
 */
import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { WidgetBody } from './WidgetBody'
import { measureFormat, fmtStr } from './chartUtils'
import { trueFalseColumns, withTrueFalseFormats } from '../../lib/fieldHints'
import type { CalcColumnFormat } from '../../services/api'

const ANALYSIS = { numeric: { columns: {
  on_time:      { min: 0, max: 1, p5: 0, p25: 0, median: 1, p75: 1, p95: 1, mean: 0.51 },
  discount_pct: { min: 0, max: 1, p5: 0, p25: 0.05, median: 0.1, p75: 0.2, p95: 0.6 },
  revenue:      { min: 3, max: 9000, p5: 10, p25: 100, median: 300, p75: 900, p95: 4000 },
} } }

const kpi = (config: Record<string, unknown>, formats: Record<string, CalcColumnFormat | undefined>, value: number) =>
  render(<WidgetBody widget={{ id: 1, page_id: 1, widget_type: 'kpi', title: 'On-time rate', config,
    layout: { x: 0, y: 0, w: 3, h: 2 } } as never}
    data={{ type: 'scalar', rows: [{ name: config.measure, value }] } as never}
    allFormats={formats} localSelected={null} onClickPoint={() => {}} broadcasts={false} />)

describe('a true/false column', () => {
  it('is recognised from the profile; a spread-out rate is not', () => {
    expect(trueFalseColumns(ANALYSIS)).toEqual(['on_time'])
  })

  it('its average shows as a percent', () => {
    const formats = withTrueFalseFormats<CalcColumnFormat>({}, ANALYSIS)
    const { container } = kpi({ measure: 'on_time', aggregation: 'avg' }, formats, 0.5137)
    expect(container.textContent).toContain('51.4%')
    expect(container.textContent).not.toContain('0.51')
  })

  it('its sum and count stay plain numbers', () => {
    const fmt = withTrueFalseFormats<CalcColumnFormat>({}, ANALYSIS).on_time
    expect(fmtStr(2142, measureFormat(fmt, 'sum'))).toBe('2,142')
    expect(fmtStr(4200, measureFormat(fmt, 'count'))).toBe('4,200')
  })

  it("an author's own format wins", () => {
    const own = { on_time: { type: 'number', decimals: 3 } as CalcColumnFormat }
    const formats = withTrueFalseFormats(own, ANALYSIS)
    expect(formats.on_time).toBe(own.on_time)
    const { container } = kpi({ measure: 'on_time', aggregation: 'avg' }, formats, 0.5137)
    expect(container.textContent).toContain('0.514')
  })

  it('nothing changes for a dataset without one', () => {
    const formats = { revenue: { type: 'currency', symbol: '$' } as CalcColumnFormat }
    expect(withTrueFalseFormats(formats, { numeric: { columns: { revenue: ANALYSIS.numeric.columns.revenue } } })).toBe(formats)
  })
})
