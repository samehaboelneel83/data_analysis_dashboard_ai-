import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithProviders as render, screen, fireEvent, waitFor } from '../../test/renderWithProviders'
import MeasuresPanel from './MeasuresPanel'
import { measuresApi } from '../../services/api'
import type { DatasetColumn } from '../../services/api'

vi.mock('../../services/api', () => ({
  measuresApi: {
    list: vi.fn(),
    save: vi.fn(),
    delete: vi.fn(),
    preview: vi.fn(),
  },
}))

const columns: DatasetColumn[] = [
  { id: 1, name: 'region', dtype: 'categorical', missing_pct: 0, stats: {} },
  { id: 2, name: 'sales', dtype: 'numeric', missing_pct: 0, stats: {} },
]

beforeEach(() => {
  // Return values were re-stubbed here but call history was not cleared, so a
  // `not.toHaveBeenCalled()` assertion saw the PREVIOUS test's call.
  vi.clearAllMocks()
  vi.mocked(measuresApi.list).mockResolvedValue([])
  vi.mocked(measuresApi.save).mockResolvedValue([])
  vi.mocked(measuresApi.delete).mockResolvedValue([])
  vi.mocked(measuresApi.preview).mockResolvedValue({ ok: true, dtype: 'float64', sample: [] })
})

describe('MeasuresPanel', () => {
  it('lists the measures returned by the API', async () => {
    vi.mocked(measuresApi.list).mockResolvedValue([
      { name: 'Margin', expression: 'SUM(profit) / SUM(sales) * 100' },
    ])

    render(<MeasuresPanel datasetId={1} columns={columns} onChanged={vi.fn()} />)

    expect(await screen.findByText('Margin')).toBeInTheDocument()
  })

  it('saves a new measure with its name and expression', async () => {
    const onChanged = vi.fn()
    render(<MeasuresPanel datasetId={1} columns={columns} onChanged={onChanged} />)

    fireEvent.click(await screen.findByRole('button', { name: /Add measure/i }))
    fireEvent.change(screen.getByPlaceholderText(/measure name/i), { target: { value: 'Pct' } })
    fireEvent.change(screen.getByPlaceholderText(/SUM\(/i), { target: { value: 'SUM(sales) / TOTAL(SUM(sales)) * 100' } })
    fireEvent.click(screen.getByRole('button', { name: /^Save$/i }))

    await waitFor(() => expect(measuresApi.save).toHaveBeenCalledWith(1, expect.objectContaining({
      name: 'Pct', expression: 'SUM(sales) / TOTAL(SUM(sales)) * 100',
    })))
  })

  it('offers TOTAL in the function palette, since it is measure-only', async () => {
    render(<MeasuresPanel datasetId={1} columns={columns} onChanged={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: /Add measure/i }))

    expect(screen.getByRole('button', { name: /TOTAL\(expr\)/i })).toBeInTheDocument()
  })

  it('offers CALC, the filter-context function', async () => {
    /**
     * The engine has had this for months -- `measure_eval.py` rewrites
     * `CALC(expr, "filter")` into an aggregate evaluated under a DIFFERENT row
     * filter than the visual's, which is the one thing people reach for DAX's
     * CALCULATE to do. It was implemented, tested, and callable, and appeared
     * NOWHERE in the frontend: zero hits for `CALC(` across src.
     *
     * An expensive engine nobody can find is indistinguishable from an engine
     * nobody built.
     */
    render(<MeasuresPanel datasetId={1} columns={columns} onChanged={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: /Add measure/i }))

    expect(screen.getByRole('button', { name: /CALC\(expr/i })).toBeInTheDocument()
  })

  it('offers SCOPE and ISINSCOPE, the per-level formula functions (Phase 6.5)', async () => {
    render(<MeasuresPanel datasetId={1} columns={columns} onChanged={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: /Add measure/i }))
    expect(screen.getByRole('button', { name: /SCOPE\(default/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /ISINSCOPE/i })).toBeInTheDocument()
  })

  it('does not offer row-level window functions, which have no meaning at aggregated grain', async () => {
    render(<MeasuresPanel datasetId={1} columns={columns} onChanged={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: /Add measure/i }))

    expect(screen.queryByRole('button', { name: /CUMSUM/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /GROUPSUM/i })).not.toBeInTheDocument()
  })

  it('previews against a chosen grouping column so the sample matches a real visual', async () => {
    vi.mocked(measuresApi.preview).mockResolvedValue({
      ok: true, dtype: 'float64',
      sample: [{ group: 'East', value: 25 }, { group: 'West', value: 75 }],
    })
    render(<MeasuresPanel datasetId={1} columns={columns} onChanged={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: /Add measure/i }))

    fireEvent.change(screen.getByPlaceholderText(/SUM\(/i), { target: { value: 'SUM(sales)' } })
    fireEvent.change(screen.getByLabelText(/Group by/i), { target: { value: 'region' } })
    fireEvent.click(screen.getByRole('button', { name: /Test/i }))

    await waitFor(() => expect(measuresApi.preview).toHaveBeenCalledWith(1, {
      expression: 'SUM(sales)', group_by: 'region',
    }))
    expect(await screen.findByText(/East/)).toBeInTheDocument()
  })

  it('surfaces a preview error instead of implying the expression is valid', async () => {
    vi.mocked(measuresApi.preview).mockResolvedValue({ ok: false, error: 'Unknown column: nope' })
    render(<MeasuresPanel datasetId={1} columns={columns} onChanged={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: /Add measure/i }))

    fireEvent.change(screen.getByPlaceholderText(/SUM\(/i), { target: { value: 'SUM(nope)' } })
    fireEvent.click(screen.getByRole('button', { name: /Test/i }))

    expect(await screen.findByText(/Unknown column: nope/)).toBeInTheDocument()
  })

  it('deletes a measure', async () => {
    vi.mocked(measuresApi.list).mockResolvedValue([{ name: 'Margin', expression: 'SUM(a)' }])
    render(<MeasuresPanel datasetId={1} columns={columns} onChanged={vi.fn()} />)
    await screen.findByText('Margin')

    fireEvent.click(screen.getByRole('button', { name: /Delete Margin/i }))
    // Destructive actions are guarded, so the dialog has to be accepted.
    fireEvent.click(await screen.findByRole('button', { name: /^delete$/i }))

    await waitFor(() => expect(measuresApi.delete).toHaveBeenCalledWith(1, 'Margin'))
  })

  it('cancelling the confirm leaves the measure alone', async () => {
    // Deleting a measure breaks every widget referencing it, across all
    // reports. Asserting the API is NOT called is what proves the guard;
    // merely rendering the dialog would pass even if the action ran anyway.
    vi.mocked(measuresApi.list).mockResolvedValue([{ name: 'Margin', expression: 'SUM(a)' }])
    render(<MeasuresPanel datasetId={1} columns={columns} onChanged={vi.fn()} />)
    await screen.findByText('Margin')

    fireEvent.click(screen.getByRole('button', { name: /Delete Margin/i }))
    expect(await screen.findByRole('alertdialog')).toHaveTextContent(/stops working/i)
    fireEvent.click(screen.getByRole('button', { name: /cancel/i }))

    await waitFor(() =>
      expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument())
    expect(measuresApi.delete).not.toHaveBeenCalled()
  })
})
