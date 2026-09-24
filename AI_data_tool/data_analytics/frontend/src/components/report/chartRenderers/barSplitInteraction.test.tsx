import { describe, it, expect, vi } from 'vitest'
import { cloneElement, type ReactElement } from 'react'
import { render, fireEvent, waitFor } from '@testing-library/react'
import BarChartRenderer from './BarChartRenderer'
import type { ChartRendererProps } from './types'

/**
 * A bar split by a second field (region x channel) must behave like an unsplit
 * one: a click filters the page by its category, and the tooltip names each
 * series. Both were missing -- adding a colour silently took away the chart's
 * ability to filter, and its tooltip read ": 138" four times.
 */

// jsdom gives ResponsiveContainer no size, so the chart would never draw.
vi.mock('recharts', async (orig) => {
  const m = await orig<Record<string, unknown>>()
  return {
    ...m,
    ResponsiveContainer: ({ children }: { children: ReactElement }) =>
      cloneElement(children, { width: 600, height: 300 } as never),
  }
})

const data = {
  type: 'crosstab',
  columns: ['region', 'Online', 'Retail', 'Total'],
  rows: [['Asia Pacific', 138, 127, 265], ['Europe', 120, 131, 251]],
}

const props = (over: Partial<ChartRendererProps> = {}): ChartRendererProps => ({
  rows: [], data, cfg: {}, rtl: false, broadcasts: true, localSelected: null,
  onClickPoint: () => {}, ruleStyles: undefined, ...over,
} as ChartRendererProps)

describe('a split bar chart', () => {
  it('filters by the category that was clicked', async () => {
    const onClickPoint = vi.fn()
    const { container } = render(<BarChartRenderer {...props({ onClickPoint })} />)
    const surface = container.querySelector('.recharts-wrapper')!
    expect(surface).not.toBeNull()
    // Left half of the plot = the first category.
    fireEvent.mouseMove(surface, { clientX: 150, clientY: 150 })
    fireEvent.click(surface, { clientX: 150, clientY: 150 })
    await waitFor(() => expect(onClickPoint).toHaveBeenCalledWith('Asia Pacific'))
  })

  it('does not filter when the widget does not broadcast', () => {
    const onClickPoint = vi.fn()
    const { container } = render(<BarChartRenderer {...props({ onClickPoint, broadcasts: false })} />)
    const surface = container.querySelector('.recharts-wrapper')!
    fireEvent.mouseMove(surface, { clientX: 150, clientY: 150 })
    fireEvent.click(surface, { clientX: 150, clientY: 150 })
    expect(onClickPoint).not.toHaveBeenCalled()
  })

  it('names every series in its tooltip', async () => {
    const { container } = render(<BarChartRenderer {...props()} />)
    fireEvent.mouseMove(container.querySelector('.recharts-wrapper')!, { clientX: 150, clientY: 150 })
    await waitFor(() => {
      const tip = container.querySelector('.recharts-tooltip-wrapper')?.textContent ?? ''
      expect(tip).toContain('Online')
      expect(tip).toContain('Retail')
    })
  })
})

describe('dual-axis charts filter the page too', () => {
  it.each([
    ['DualAxisBarChartRenderer'], ['DualAxisBarLineChartRenderer'], ['DualAxisLineChartRenderer'],
    ['DualAxisTimeSeriesRenderer'], ['ComparativeTimeSeriesRenderer'],
  ])('%s', async (name) => {
    const { default: R } = await import(`./${name}.tsx`)
    const onClickPoint = vi.fn()
    const rows = [{ name: 'Q1', value: 10, value2: 3 }, { name: 'Q2', value: 12, value2: 4 }]
    const { container } = render(<R {...props({ rows, data: {}, onClickPoint })} />)
    const surface = container.querySelector('.recharts-wrapper')!
    fireEvent.mouseMove(surface, { clientX: 100, clientY: 150 })
    fireEvent.click(surface, { clientX: 100, clientY: 150 })
    await waitFor(() => expect(onClickPoint).toHaveBeenCalledWith('Q1'))
  })
})
