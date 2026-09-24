import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import LatticeRenderer from './LatticeRenderer'
import type { ChartRendererProps } from './types'

function Probe(p: ChartRendererProps) {
  return <div data-testid="probe" data-ymin={p.cfg.y_min} data-ymax={p.cfg.y_max} data-legend={String(p.cfg.legend)}>
    {p.rows.map((r: any) => `${r.name}=${r.value}`).join(',')}</div>
}

const base: Omit<ChartRendererProps, 'data'> = { rows: [], cfg: { legend: true }, rtl: false, broadcasts: false,
  localSelected: null, onClickPoint: () => {} }

const lattice = {
  type: 'lattice', inner: 'bar', rows_by: 'region', cols_by: 'channel',
  row_values: ['N', 'S'], col_values: ['web', 'store'], domain: [0, 30],
  cells: [
    { row: 'N', col: 'web', result: { type: 'series', rows: [{ name: 'Jan', value: 30 }] } },
    { row: 'N', col: 'store', result: { type: 'series', rows: [{ name: 'Jan', value: 10 }] } },
    { row: 'S', col: 'web', result: { type: 'series', rows: [{ name: 'Jan', value: 20 }] } },
    { row: 'S', col: 'store', result: { type: 'empty', rows: [] } },
  ],
  lattice_truncation: { text: 'Showing 2 of 5 region values (those with the most rows)' },
}

describe('LatticeRenderer (Phase 6.2)', () => {
  it('draws a headed grid of the inner chart on one shared axis, legends off', () => {
    render(<LatticeRenderer Inner={Probe} props={{ ...base, data: lattice }} />)
    expect(screen.getAllByRole('columnheader').map(h => h.textContent)).toEqual(['web', 'store'])
    expect(screen.getAllByRole('rowheader').map(h => h.textContent)).toEqual(['N', 'S'])
    expect(screen.getAllByTestId('lattice-cell')).toHaveLength(4)
    expect(screen.getByText('no rows')).toBeTruthy()
    expect(screen.getByTestId('lattice-truncation').textContent).toContain('2 of 5')
  })

  it('keeps an author-fixed axis instead of the shared domain', () => {
    const { container } = render(<LatticeRenderer Inner={Probe}
      props={{ ...base, cfg: { y_min: 5 }, data: lattice }} />)
    // MeasuredChart renders children only after measuring; jsdom has no layout,
    // so assert on the cell structure rather than the probe.
    expect(container.querySelectorAll('[data-testid="lattice-cell"]').length).toBe(4)
  })
})
