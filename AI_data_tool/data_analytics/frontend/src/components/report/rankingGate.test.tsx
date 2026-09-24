import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import WidgetConfigPanel from './WidgetConfigPanel'
import { CrossFilterProvider } from './CrossFilterContext'
import { supportsRanking } from './widgetCapabilities'
import type { Widget } from '../../types/report'
import type { DatasetColumn } from '../../services/api'

/**
 * The Ranking group is offered exactly where the shaper honours it.
 *
 * Both failure directions are defects: offered-and-ignored is a control wired
 * to nothing (the capability file's founding bug), and honoured-but-hidden is
 * an unreachable capability (this codebase's most-repeated trap). The set
 * itself is pinned against the backend in test_frontend_constant_mirrors.py;
 * these prove the PANEL actually consults it.
 */

const col = (name: string, dtype: string): DatasetColumn =>
  ({ id: 0, name, dtype, missing_pct: 0, stats: {} } as DatasetColumn)

const COLUMNS = [col('region', 'text'), col('revenue', 'numeric')]

function panel(widgetType: string) {
  const widget: Widget = {
    id: 1, page_id: 100, widget_type: widgetType as Widget['widget_type'],
    title: '', config: {}, layout: { x: 0, y: 0, w: 6, h: 5 }, created_at: 'x',
  }
  render(
    <CrossFilterProvider>
      <WidgetConfigPanel widget={widget} columns={COLUMNS} onUpdate={vi.fn()} />
    </CrossFilterProvider>,
  )
}

beforeEach(() => { vi.useFakeTimers(); localStorage.clear() })
afterEach(() => vi.useRealTimers())

describe('the Ranking group is capability-gated', () => {
  it('offers Ranking on a bar chart', () => {
    panel('bar')
    expect(screen.getByText('Ranking')).toBeInTheDocument()
  })

  it('offers Ranking on a heatmap — the newly covered shaper', () => {
    panel('heatmap')
    expect(screen.getByText('Ranking')).toBeInTheDocument()
  })

  it('withholds Ranking from a sunburst, whose own top-N applies', () => {
    // The hierarchy family has its own reconciling HIER_MAX_CHILDREN + Other;
    // a second rank path would drift from the first.
    panel('sunburst')
    expect(screen.queryByText('Ranking')).toBeNull()
  })

  it('withholds Ranking from a kpi, which has nothing to rank', () => {
    panel('kpi')
    expect(screen.queryByText('Ranking')).toBeNull()
  })

  it('the gate function itself matches those cases', () => {
    expect(supportsRanking('bar')).toBe(true)
    expect(supportsRanking('heatmap')).toBe(true)
    expect(supportsRanking('sunburst')).toBe(false)
    expect(supportsRanking('kpi')).toBe(false)
  })
})
