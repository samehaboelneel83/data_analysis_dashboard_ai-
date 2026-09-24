import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import SmallMultiplesRenderer from './SmallMultiplesRenderer'

/**
 * The one thing this visual must get right is the SHARED SCALE. Comparing the
 * panels to one another is the whole reason to face a chart rather than draw
 * several, and per-panel axes would render a small category identically to a
 * large one — the single way small multiples lie.
 */
const props = (over: Record<string, unknown> = {}) => ({
  rows: [], cfg: {}, rtl: false, broadcasts: false, localSelected: null,
  onClickPoint: vi.fn(),
  data: {
    type: 'small_multiples',
    facet_by: 'region',
    inner: 'bar',
    omitted: 0,
    max_value: 1000,
    panels: [
      { name: 'EMEA', result: { rows: [{ name: 'Jan', value: 1000 }] } },
      { name: 'APAC', result: { rows: [{ name: 'Jan', value: 100 }] } },
    ],
    ...(over.data as object ?? {}),
  },
  ...over,
})

const barWidth = (el: Element) =>
  (el as HTMLElement).style.width

describe('SmallMultiplesRenderer', () => {
  it('draws one panel per facet value', () => {
    render(<SmallMultiplesRenderer {...props() as any} />)
    expect(screen.getByText('EMEA')).toBeInTheDocument()
    expect(screen.getByText('APAC')).toBeInTheDocument()
  })

  it('scales every panel against the shared maximum', () => {
    // 100 against a shared max of 1000 must draw at ~10%, NOT at 100% as it
    // would if the panel scaled against its own single row.
    const { container } = render(<SmallMultiplesRenderer {...props() as any} />)
    const bars = Array.from(container.querySelectorAll('div[style*="width"]'))
      .map(barWidth).filter(w => w.endsWith('%'))
    expect(bars).toContain('100%')
    expect(bars.some(w => parseFloat(w) > 5 && parseFloat(w) < 20)).toBe(true)
  })

  it('says how many facets were left off the page', () => {
    // A reader comparing panels cannot see what never made it on.
    render(<SmallMultiplesRenderer {...props({ data: {
      facet_by: 'sku', omitted: 18, max_value: 10,
      panels: [{ name: 'S1', result: { rows: [{ name: 'a', value: 10 }] } }],
    } }) as any} />)
    expect(screen.getByText(/18 more/)).toBeInTheDocument()
  })

  it('stays quiet when nothing was omitted', () => {
    render(<SmallMultiplesRenderer {...props() as any} />)
    expect(screen.queryByText(/not shown/)).toBeNull()
  })

  it('admits when panels could not share a scale', () => {
    // Better to say the comparison is unreliable than to imply one silently.
    render(<SmallMultiplesRenderer {...props({ data: {
      facet_by: 'region', omitted: 0, max_value: null,
      panels: [
        { name: 'A', result: { rows: [{ name: 'x', value: 5 }] } },
        { name: 'B', result: { rows: [{ name: 'x', value: 9 }] } },
      ],
    } }) as any} />)
    expect(screen.getByText(/scaled independently/)).toBeInTheDocument()
  })

  it('renders a panel that has no rows without breaking', () => {
    render(<SmallMultiplesRenderer {...props({ data: {
      facet_by: 'region', omitted: 0, max_value: 10,
      panels: [
        { name: 'Full', result: { rows: [{ name: 'x', value: 10 }] } },
        { name: 'Empty', result: { rows: [] } },
      ],
    } }) as any} />)
    expect(screen.getByText('Empty')).toBeInTheDocument()
    expect(screen.getByText('no rows')).toBeInTheDocument()
  })

  it('shows an empty state rather than a blank box', () => {
    render(<SmallMultiplesRenderer {...props({ data: {
      facet_by: 'region', omitted: 0, max_value: null, panels: [],
    } }) as any} />)
    expect(screen.getByText('No data.')).toBeInTheDocument()
  })
})
