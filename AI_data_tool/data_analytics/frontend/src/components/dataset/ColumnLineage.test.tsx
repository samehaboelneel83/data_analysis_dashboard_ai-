/** A column's whole journey on screen (docs/pipeline/PLAN.md, P5). */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import ColumnLineage from './ColumnLineage'

vi.mock('../../services/api', () => ({ datasetsApi: { columnLineage: vi.fn() } }))
import { datasetsApi } from '../../services/api'

describe('ColumnLineage', () => {
  it('shows source, load, steps, formula, checks and uses, numbered in order', async () => {
    vi.mocked(datasetsApi.columnLineage).mockResolvedValue({
      name: 'amount_k',
      origin: { kind: 'calculated', expression: 'amount / 1000', inputs: ['amount'] },
      process: [
        { stage: 'source', kind: 'inputs', inputs: [{ name: 'amount', kind: 'source', source: 'Shop DB', source_id: 1,
          table: 'public.orders', column: 'amt', native_type: 'numeric', arrives_as: 'amt' } as never] },
        { stage: 'load', mode: 'import', strategy: 'incremental', cursor_column: 'updated_at', key_column: 'id',
          reconcile_deletes: true, has_query: true, query: 'SELECT amt FROM orders', last_refreshed_at: null,
          last_run: { status: 'failed', started_at: '2026-10-10T07:00:00Z', rows: null, duration_ms: 1200, error: 'source unreachable' } },
        { stage: 'steps', total_steps: 3, steps: [
          { index: 1, kind: 'rename', dataset: null, role: 'makes', detail: {} },
          { index: 2, kind: 'join', dataset: 'Regions', role: 'rows', detail: {} }] },
        { stage: 'formula', kind: 'calculated', expression: 'amount / 1000', inputs: ['amount'] },
        { stage: 'checks', checks: [{ kind: 'not_null', severity: 'block', enabled: true, column: 'amount' }] },
      ],
      used_by: [{ kind: 'widget', id: 4, label: 'Sales by month on Overview', where: 'measure' }],
      dataset: { id: 2, name: 'Orders', last_refreshed_at: null },
    })
    render(<ColumnLineage datasetId={2} name="amount_k" />)
    const box = await screen.findByTestId('column-lineage')
    const text = box.textContent ?? ''
    const order = ['Comes from', 'Loaded into Datalytics', 'Changed by these steps', 'Calculated',
                   'Checked before every load', 'Used by 1']
    order.reduce((at, label) => { const i = text.indexOf(label, at); expect(i).toBeGreaterThan(-1); return i }, 0)
    expect(box).toHaveTextContent('Shop DB › public.orders › amt')
    expect(box).toHaveTextContent('only rows past updated_at are read; rows are matched on id')
    expect(box).toHaveTextContent('Rows deleted at the source are removed.')
    expect(box).toHaveTextContent('source unreachable')
    expect(box).toHaveTextContent('Rename')
    expect(box).toHaveTextContent('Join — Regions')
    expect(box).toHaveTextContent('1 other step(s) do not touch it')
    expect(box).toHaveTextContent('Sales by month on Overview')
    fireEvent.click(screen.getByRole('button', { name: "Show the dataset's query" }))
    expect(box).toHaveTextContent('SELECT amt FROM orders')
  })
})
