import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { WidgetBody } from './WidgetBody'

/** A KPI with its recent history: the change against the previous complete
 *  period and a sparkline (server: services/widget_data.kpi_trend). */
const trend = {
  granularity: 'month', date: 'when', current: 150, previous: 100, change: 50, change_pct: 50,
  period: '2024-08', previous_period: '2024-07', partial_dropped: false,
  series: [{ period: '2024-06', value: 90 }, { period: '2024-07', value: 100 }, { period: '2024-08', value: 150 }],
}
const kpi = (config: Record<string, unknown>, data: Record<string, unknown>) => render(<WidgetBody
  widget={{ id: 1, page_id: 1, widget_type: 'kpi', title: 'Total', config, layout: { x: 0, y: 0, w: 3, h: 3 } } as never}
  data={{ type: 'scalar', rows: [{ name: 'amount', value: 840 }], ...data } as never}
  localSelected={null} onClickPoint={() => {}} broadcasts={false} />)

describe('KPI with its history', () => {
  it('shows the change and the sparkline beside the number', () => {
    kpi({ measure: 'amount', aggregation: 'sum', sparkline_date: 'when' }, { trend })
    expect(screen.getByTestId('kpi-change').textContent).toContain('▲ 50.0%')
    expect(screen.getByRole('img', { name: 'trend sparkline' })).toBeInTheDocument()
    expect(screen.getByTestId('kpi-trend').getAttribute('title')).toContain('2024-07')
  })

  it('lays the card out to be read at a glance: change as a pill, history filled across the card', () => {
    kpi({ measure: 'amount', aggregation: 'sum', sparkline_date: 'when', trend_good: 'up' }, { trend })
    const pill = screen.getByTestId('kpi-change')
    expect(pill.style.borderRadius).toBe('999px')
    const line = screen.getByRole('img', { name: 'trend sparkline' })
    expect(line.getAttribute('width')).toBe('100%')                     // as wide as the card, whatever its size
    expect(line.getAttribute('preserveAspectRatio')).toBe('none')
    const fill = screen.getByTestId('sparkline-fill')
    expect(fill.getAttribute('fill')).toMatch(/^url\(#spark/)           // a gradient, not a flat colour
    expect(screen.getByTestId('kpi-trend').contains(line)).toBe(true)
    expect(screen.getByTestId('kpi-trend').contains(pill)).toBe(false)  // the pill sits beside the number
  })

  it('shows the same period a year before beside the previous period, when the server sent one', () => {
    kpi({ measure: 'amount', aggregation: 'sum', sparkline_date: 'when', trend_good: 'up' },
      { trend: { ...trend, year_ago: { period: '2023-08', value: 200, change: -50, change_pct: -25 } } })
    const line = screen.getByTestId('kpi-year-ago')
    expect(line.textContent).toContain('▼ 25.0%')
    expect(line.textContent).toContain('vs 2023-08')
    expect(screen.getByTestId('kpi-change').textContent).toContain('▲ 50.0%')
  })

  it('has no year-before line without one', () => {
    kpi({ measure: 'amount', aggregation: 'sum', sparkline_date: 'when' }, { trend: { ...trend, year_ago: null } })
    expect(screen.queryByTestId('kpi-year-ago')).toBeNull()
  })

  it('shows how far along its stored target the number is', () => {
    kpi({ measure: 'amount', aggregation: 'sum', target_value: 1000 },
      { target: { value: 1000, period: null, applies: true, against: 840, label: null, pct: 84, remaining: 160, met: false } })
    const line = screen.getByTestId('kpi-target')
    expect(line.textContent).toContain('84%')
    expect(line.textContent).toContain('1,000')
    expect(line.getAttribute('data-met')).toBe('no')
  })

  it('says why a per-period target could not be applied instead of showing a wrong share', () => {
    kpi({ measure: 'amount', aggregation: 'sum', target_value: 1000, target_period: 'month' },
      { target: { value: 1000, period: 'month', applies: false, reason: 'The target is for each month, and this number has no history by month to set against it.' } })
    expect(screen.getByTestId('kpi-target').textContent).toContain('no history by month')
  })

  it('colours the change by which way is good for this number, and not at all when nobody said', () => {
    const { unmount } = kpi({ measure: 'delay', aggregation: 'avg', sparkline_date: 'when', trend_good: 'down' }, { trend })
    expect(screen.getByTestId('kpi-change').style.color).toContain('danger')     // up, and up is bad here
    unmount()
    kpi({ measure: 'amount', aggregation: 'sum', sparkline_date: 'when' }, { trend })
    expect(screen.getByTestId('kpi-change').style.color).toContain('muted')
  })

  it('a KPI with no history is the plain number it always was', () => {
    kpi({ measure: 'amount', aggregation: 'sum' }, {})
    expect(screen.queryByTestId('kpi-trend')).toBeNull()
    expect(screen.getByText('840')).toBeInTheDocument()
  })
})
