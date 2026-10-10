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
    restore: vi.fn(),
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
    fireEvent.click(await screen.findByRole('button', { name: 'Write a formula myself' }))
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
    fireEvent.click(await screen.findByRole('button', { name: 'Write a formula myself' }))

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
    fireEvent.click(await screen.findByRole('button', { name: 'Write a formula myself' }))

    expect(screen.getByRole('button', { name: /CALC\(expr/i })).toBeInTheDocument()
  })

  it('offers SCOPE and ISINSCOPE, the per-level formula functions (Phase 6.5)', async () => {
    render(<MeasuresPanel datasetId={1} columns={columns} onChanged={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: /Add measure/i }))
    fireEvent.click(await screen.findByRole('button', { name: 'Write a formula myself' }))
    expect(screen.getByRole('button', { name: /SCOPE\(default/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /ISINSCOPE/i })).toBeInTheDocument()
  })

  it('does not offer row-level window functions, which have no meaning at aggregated grain', async () => {
    render(<MeasuresPanel datasetId={1} columns={columns} onChanged={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: /Add measure/i }))
    fireEvent.click(await screen.findByRole('button', { name: 'Write a formula myself' }))

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
    fireEvent.click(await screen.findByRole('button', { name: 'Write a formula myself' }))

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
    fireEvent.click(await screen.findByRole('button', { name: 'Write a formula myself' }))

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

describe('deleting a measure something still uses (E05)', () => {
  const inUse = () => Object.assign(new Error('409'), { response: { status: 409, data: {
    detail: "'Margin' is used by widget 'Margin by region on Sales'. Delete anyway with ?force=true." } } })

  it('names what uses it and deletes only when the person says so', async () => {
    vi.mocked(measuresApi.list).mockResolvedValue([{ name: 'Margin', expression: 'SUM(a)' }])
    vi.mocked(measuresApi.delete).mockReset()
      .mockRejectedValueOnce(inUse()).mockResolvedValueOnce([])
    render(<MeasuresPanel datasetId={1} columns={columns} onChanged={vi.fn()} />)
    await screen.findByText('Margin')

    fireEvent.click(screen.getByRole('button', { name: /Delete Margin/i }))
    fireEvent.click(await screen.findByRole('button', { name: /^delete$/i }))

    const second = await screen.findByRole('alertdialog')
    expect(second).toHaveTextContent("used by widget 'Margin by region on Sales'")
    expect(second).not.toHaveTextContent('force=true')     // an API detail, not advice for a person
    fireEvent.click(screen.getByRole('button', { name: 'Delete anyway' }))

    await waitFor(() => expect(measuresApi.delete).toHaveBeenLastCalledWith(1, 'Margin', true))
    expect(measuresApi.delete).toHaveBeenCalledTimes(2)
  })

  it('keeps it when the person backs out of the second question', async () => {
    vi.mocked(measuresApi.list).mockResolvedValue([{ name: 'Margin', expression: 'SUM(a)' }])
    vi.mocked(measuresApi.delete).mockReset().mockRejectedValueOnce(inUse())
    render(<MeasuresPanel datasetId={1} columns={columns} onChanged={vi.fn()} />)
    await screen.findByText('Margin')

    fireEvent.click(screen.getByRole('button', { name: /Delete Margin/i }))
    fireEvent.click(await screen.findByRole('button', { name: /^delete$/i }))
    await screen.findByRole('button', { name: 'Delete anyway' })
    fireEvent.click(screen.getByRole('button', { name: /cancel/i }))

    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument())
    expect(measuresApi.delete).toHaveBeenCalledTimes(1)
    expect(screen.getByText('Margin')).toBeInTheDocument()
  })
})

describe('metric versions (E05)', () => {
  const versioned = {
    name: 'Margin', expression: 'SUM(profit) / SUM(sales) * 100', version: 2,
    history: [{ version: 1, expression: 'SUM(profit) / SUM(sales)', saved_at: '2026-09-20T10:00:00Z' }],
  }

  it('shows the version of a changed formula and restores an earlier one', async () => {
    vi.mocked(measuresApi.list).mockResolvedValue([versioned] as never)
    vi.mocked(measuresApi.restore).mockResolvedValue(
      [{ ...versioned, version: 3, expression: 'SUM(profit) / SUM(sales)' }] as never)
    const onChanged = vi.fn()
    render(<MeasuresPanel datasetId={1} columns={columns} onChanged={onChanged} />)

    fireEvent.click(await screen.findByRole('button', { name: /Version 2 of Margin/ }))
    const earlier = screen.getByRole('list', { name: 'Earlier formulas of Margin' })
    expect(earlier).toHaveTextContent('v1')
    expect(earlier).toHaveTextContent('SUM(profit) / SUM(sales)')
    expect(earlier).toHaveTextContent('2026-09-20')

    fireEvent.click(screen.getByRole('button', { name: 'Restore version 1 of Margin' }))
    await waitFor(() => expect(measuresApi.restore).toHaveBeenCalledWith(1, 'Margin', 1))
    await waitFor(() => expect(onChanged).toHaveBeenCalled())
  })

  it('shows no version badge on a formula that never changed', async () => {
    vi.mocked(measuresApi.list).mockResolvedValue([{ name: 'Total', expression: 'SUM(sales)', version: 1, history: [] }] as never)
    render(<MeasuresPanel datasetId={1} columns={columns} onChanged={vi.fn()} />)
    await screen.findByText('Total')
    expect(screen.queryByRole('button', { name: /Version/ })).toBeNull()
  })
})


describe('a new measure without writing a formula (2026-10-10)', () => {
  async function open() {
    render(<MeasuresPanel datasetId={1} columns={columns} onChanged={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: /Add measure/i }))
    expect(await screen.findByText('What do you want to measure?')).toBeInTheDocument()
  }

  it('summarise: picks the summary and the column, writes the formula and the name', async () => {
    await open()
    fireEvent.click(screen.getByRole('button', { name: /Summarise a column/ }))
    fireEvent.change(screen.getByLabelText('Summary'), { target: { value: 'MAX' } })
    fireEvent.change(screen.getByLabelText('Column'), { target: { value: 'sales' } })
    expect(screen.getByTestId('measure-written-formula')).toHaveTextContent('MAX(sales)')
    expect(screen.getByLabelText('Measure name')).toHaveValue('Highest sales')
    fireEvent.click(screen.getByRole('button', { name: /^Save$/i }))
    await waitFor(() => expect(measuresApi.save).toHaveBeenCalledWith(1,
      expect.objectContaining({ name: 'Highest sales', expression: 'MAX(sales)' })))
  })

  it('only some rows: the condition boxes write the filter', async () => {
    await open()
    fireEvent.click(screen.getByRole('button', { name: /Only some rows/ }))
    fireEvent.change(screen.getByLabelText('Column'), { target: { value: 'sales' } })
    fireEvent.change(screen.getByLabelText('Column of condition 1'), { target: { value: 'region' } })
    fireEvent.change(screen.getByLabelText('Value of condition 1'), { target: { value: 'EMEA' } })
    expect(screen.getByTestId('measure-written-formula')).toHaveTextContent("SUM(IF(region == 'EMEA', sales, 0))")
  })

  it('a broken measure is explained in plain words', async () => {
    vi.mocked(measuresApi.preview).mockResolvedValue({ ok: false, error: "name 'sale' is not defined",
      problem: { code: 'unknown_name', name: 'sale', suggest: 'sales' } })
    await open()
    fireEvent.click(screen.getByRole('button', { name: 'Write a formula myself' }))
    fireEvent.change(screen.getByPlaceholderText(/SUM\(/i), { target: { value: 'SUM(sale)' } })
    fireEvent.click(screen.getByRole('button', { name: /Test/i }))
    expect(await screen.findByText('There is no column or function called "sale". Did you mean "sales"?')).toBeInTheDocument()
  })
})
