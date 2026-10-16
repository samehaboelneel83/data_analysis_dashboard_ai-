/**
 * UAT-9: the average of a true/false field (on_time) showed 0.51, not 51%.
 *
 * A boolean is filed under "numeric" by the type probe (pandas counts bool as
 * numeric), so the column metadata cannot tell it from a rate. The SERVER
 * still knows -- the source file holds a bool -- and says so on the
 * widget-data result (`measure_true_false`) when the measure is its average.
 * WidgetBody reads that hint, so the builder, the viewer, a shared link, an
 * embed and print all show a percent, profiled dataset or not, unless the
 * author set a format of their own.
 */
import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { WidgetBody } from './WidgetBody'
import { measureFormat, fmtStr, withTrueFalseMeasure } from './chartUtils'
import type { CalcColumnFormat } from '../../services/api'

const kpi = (config: Record<string, unknown>, formats: Record<string, CalcColumnFormat | undefined>, value: number,
             hint = true) =>
  render(<WidgetBody widget={{ id: 1, page_id: 1, widget_type: 'kpi', title: 'On-time rate', config,
    layout: { x: 0, y: 0, w: 3, h: 2 } } as never}
    data={{ type: 'scalar', rows: [{ name: config.measure, value }], ...(hint ? { measure_true_false: true } : {}) } as never}
    allFormats={formats} localSelected={null} onClickPoint={() => {}} broadcasts={false} />)

describe('the average of a true/false column (server hint)', () => {
  it('shows as a percent with no profile and no format', () => {
    const { container } = kpi({ measure: 'on_time', aggregation: 'avg' }, {}, 0.5137)
    expect(container.textContent).toContain('51.4%')
    expect(container.textContent).not.toContain('0.51')
  })

  it('stays a plain number without the hint (a 0..1 rate)', () => {
    const { container } = kpi({ measure: 'discount_pct', aggregation: 'avg' }, {}, 0.5137, false)
    expect(container.textContent).toContain('0.51')
    expect(container.textContent).not.toContain('%')
  })

  it("an author's own format wins", () => {
    const own = { on_time: { type: 'number', decimals: 3 } as CalcColumnFormat }
    expect(withTrueFalseMeasure(own, 'on_time', { measure_true_false: true })).toBe(own)
    const { container } = kpi({ measure: 'on_time', aggregation: 'avg' }, own, 0.5137)
    expect(container.textContent).toContain('0.514')
    expect(container.textContent).not.toContain('%')
  })

  it('its sum and count stay plain numbers', () => {
    const fmt = withTrueFalseMeasure<CalcColumnFormat>({}, 'on_time', { measure_true_false: true }).on_time
    expect(fmtStr(2142, measureFormat(fmt, 'sum'))).toBe('2,142')
    expect(fmtStr(4200, measureFormat(fmt, 'count'))).toBe('4,200')
  })

  it('nothing changes without the hint', () => {
    const formats = { revenue: { type: 'currency', symbol: '$' } as CalcColumnFormat }
    expect(withTrueFalseMeasure(formats, 'revenue', { type: 'scalar' })).toBe(formats)
    expect(withTrueFalseMeasure(formats, 'revenue', null)).toBe(formats)
  })
})
