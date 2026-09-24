import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import CustomCategoryPanel from './CustomCategoryPanel'
import { calcColumnsApi, widgetDataApi } from '../../services/api'
import type { DatasetColumn } from '../../services/api'

vi.mock('../../services/api', () => ({
  calcColumnsApi: { save: vi.fn() },
  widgetDataApi: { query: vi.fn() },
}))

/**
 * Answer the two range probes the panel makes for a numeric column.
 *
 * The fixture below used to carry `stats: { min: 0, max: 100 }` and the panel
 * read the edges straight off it — but `DatasetColumn.stats` is a field nothing
 * in the application ever writes, so those numbers existed only in this file.
 * The binning path was dead in production and green here. The range is fetched
 * now, so the test has to answer the fetch.
 */
function answerRange(min: number, max: number, rest: unknown = { rows: [] }) {
  vi.mocked(widgetDataApi.query).mockImplementation((...args: unknown[]) => {
    const cfg = args[1] as { aggregation?: string }
    if (cfg?.aggregation === 'min') {
      return Promise.resolve({ type: 'scalar', rows: [{ name: 'x', value: min }] } as never)
    }
    if (cfg?.aggregation === 'max') {
      return Promise.resolve({ type: 'scalar', rows: [{ name: 'x', value: max }] } as never)
    }
    return Promise.resolve(rest as never)
  })
}

const columns: DatasetColumn[] = [
  { id: 1, name: 'region', dtype: 'categorical', missing_pct: 0, stats: {} },
  // `stats` stays empty because that is what the application produces; the
  // range these tests need is answered by `answerRange` above.
  { id: 2, name: 'sales', dtype: 'numeric', missing_pct: 0, stats: {} },
]

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(calcColumnsApi.save).mockResolvedValue([])
  vi.mocked(widgetDataApi.query).mockResolvedValue({
    rows: [{ name: 'US', value: 3 }, { name: 'CA', value: 2 }, { name: 'UK', value: 1 }],
    sampled: false,
  } as any)
})

describe('CustomCategoryPanel grouping', () => {
  it('loads the distinct values of the chosen category column', async () => {
    render(<CustomCategoryPanel datasetId={1} columns={columns} onSaved={vi.fn()} />)

    fireEvent.change(screen.getByLabelText(/Source column/i), { target: { value: 'region' } })

    expect(await screen.findByText('US')).toBeInTheDocument()
    expect(screen.getByText('CA')).toBeInTheDocument()
  })

  it('saves a SWITCH expression built from the assigned groups', async () => {
    const onSaved = vi.fn()
    render(<CustomCategoryPanel datasetId={1} columns={columns} onSaved={onSaved} />)
    fireEvent.change(screen.getByLabelText(/Source column/i), { target: { value: 'region' } })
    await screen.findByText('US')

    fireEvent.change(screen.getByLabelText(/New column name/i), { target: { value: 'Continent' } })
    // Assign US to a group called "Americas".
    fireEvent.change(screen.getByLabelText('Group for US'), { target: { value: 'Americas' } })
    fireEvent.click(screen.getByRole('button', { name: /^Create$/i }))

    await waitFor(() => expect(calcColumnsApi.save).toHaveBeenCalledWith(1, expect.objectContaining({
      name: 'Continent',
      expression: 'SWITCH(region, "US", "Americas", "Other")',
    })))
    expect(onSaved).toHaveBeenCalled()
  })

  it('will not save without a name', async () => {
    render(<CustomCategoryPanel datasetId={1} columns={columns} onSaved={vi.fn()} />)
    fireEvent.change(screen.getByLabelText(/Source column/i), { target: { value: 'region' } })
    await screen.findByText('US')
    fireEvent.change(screen.getByLabelText('Group for US'), { target: { value: 'Americas' } })

    fireEvent.click(screen.getByRole('button', { name: /^Create$/i }))

    expect(calcColumnsApi.save).not.toHaveBeenCalled()
    expect(await screen.findByText(/needs a name/i)).toBeInTheDocument()
  })

  it('will not save when no value has been assigned to a group', async () => {
    render(<CustomCategoryPanel datasetId={1} columns={columns} onSaved={vi.fn()} />)
    fireEvent.change(screen.getByLabelText(/Source column/i), { target: { value: 'region' } })
    await screen.findByText('US')
    fireEvent.change(screen.getByLabelText(/New column name/i), { target: { value: 'Continent' } })

    fireEvent.click(screen.getByRole('button', { name: /^Create$/i }))

    expect(calcColumnsApi.save).not.toHaveBeenCalled()
  })
})

describe('CustomCategoryPanel binning', () => {
  it('switches to interval binning for a numeric column and prefills its edges', async () => {
    answerRange(0, 100)
    render(<CustomCategoryPanel datasetId={1} columns={columns} onSaved={vi.fn()} />)

    fireEvent.change(screen.getByLabelText(/Source column/i), { target: { value: 'sales' } })

    // Numeric columns get a bin count instead of a value list.
    expect(await screen.findByLabelText(/Number of bins/i)).toBeInTheDocument()
    expect(screen.queryByText('US')).not.toBeInTheDocument()
  })

  it('saves a nested IF expression for the chosen bins', async () => {
    answerRange(0, 100)
    render(<CustomCategoryPanel datasetId={1} columns={columns} onSaved={vi.fn()} />)
    fireEvent.change(screen.getByLabelText(/Source column/i), { target: { value: 'sales' } })
    await screen.findByLabelText(/Number of bins/i)

    fireEvent.change(screen.getByLabelText(/New column name/i), { target: { value: 'Sales Band' } })
    fireEvent.change(screen.getByLabelText(/Number of bins/i), { target: { value: '2' } })
    fireEvent.click(screen.getByRole('button', { name: /^Create$/i }))

    await waitFor(() => expect(calcColumnsApi.save).toHaveBeenCalledWith(1, expect.objectContaining({
      name: 'Sales Band',
      // 2 bins over [0, 100] -> edges [0, 50, 100] -> two closed intervals.
      expression: 'IF(sales < 50, "0-50", "50-100")',
    })))
  })

  it('shows the expression it is about to save so the author can check it', async () => {
    answerRange(0, 100)
    render(<CustomCategoryPanel datasetId={1} columns={columns} onSaved={vi.fn()} />)
    fireEvent.change(screen.getByLabelText(/Source column/i), { target: { value: 'sales' } })
    await screen.findByLabelText(/Number of bins/i)

    expect(await screen.findByText(/IF\(sales </)).toBeInTheDocument()
  })
})

describe('binning a real numeric column', () => {
  /**
   * The numeric half of this panel had never worked, and its own tests hid it.
   *
   * Bin edges came from `sourceCol.stats.min/max`. `DatasetColumn.stats` is a
   * declared field that **nothing ever writes**: `stats={}` is passed literally
   * at every creation site (`routers/datasets.py:189`, `dataflows.py:352`,
   * `:384`), and 0 of 506 columns in the dev database have any. So min and max
   * both fell back to 0, `defaultBinEdges(0, 0, n)` returned no edges, and
   * Create answered "Pick at least two bin edges" — every time, for every
   * dataset. Found by driving the real page, not by a test.
   *
   * The fixture above is what concealed it: it supplies `stats: {min, max}`,
   * inventing a field the application never produces. A fixture that fabricates
   * data makes a dead feature look covered.
   *
   * The range is now fetched the same way the distinct values already were —
   * through `widgetDataApi`, so row-level security and column rules apply to it
   * exactly as they do to every other number on screen.
   */
  const realColumns: DatasetColumn[] = [
    { id: 1, name: 'region', dtype: 'categorical', missing_pct: 0, stats: {} },
    // As every column actually arrives: no stats at all.
    { id: 2, name: 'revenue', dtype: 'numeric', missing_pct: 0, stats: {} },
  ]

  const scalar = (v: number) => ({ type: 'scalar', rows: [{ name: 'revenue', value: v }] })

  beforeEach(() => {
    vi.mocked(widgetDataApi.query).mockImplementation((...args: unknown[]) => {
      const cfg = args[1] as { aggregation?: string }
      if (cfg?.aggregation === 'min') return Promise.resolve(scalar(-12011.64) as never)
      if (cfg?.aggregation === 'max') return Promise.resolve(scalar(16069.26) as never)
      return Promise.resolve({ rows: [] } as never)
    })
  })

  const pick = async () => {
    render(<CustomCategoryPanel datasetId={1} columns={realColumns} onSaved={vi.fn()} />)
    fireEvent.change(screen.getByLabelText(/source column/i), { target: { value: 'revenue' } })
  }

  it('asks the server for the column’s range', async () => {
    await pick()
    await waitFor(() => {
      const aggs = vi.mocked(widgetDataApi.query).mock.calls
        .map(c => (c[1] as { aggregation?: string })?.aggregation)
      expect(aggs).toContain('min')
      expect(aggs).toContain('max')
    })
  })

  it('offers edges spanning the real data, not 0 to 0', async () => {
    // Edges are rounded to the step's magnitude (~7,020 here), so the raw
    // minimum appears as -12012, not -12011.64.
    await pick()
    // The edges line specifically: the expression preview below it repeats the
    // same numbers, so a loose matcher finds both and fails on "multiple".
    expect(await screen.findByText(
      (t, el) => el?.children.length === 0 && /^edges: -12012/.test(t)))
      .toBeInTheDocument()
  })

  it('can actually create the binned column', async () => {
    // The whole point. This is what answered "Pick at least two bin edges".
    vi.mocked(calcColumnsApi.save).mockResolvedValue([] as never)
    await pick()
    await screen.findByText(
      (t, el) => el?.children.length === 0 && /^edges: -12012/.test(t))
    fireEvent.change(screen.getByLabelText(/new column name/i),
      { target: { value: 'Revenue Band' } })
    fireEvent.click(screen.getByRole('button', { name: /create/i }))

    await waitFor(() => expect(calcColumnsApi.save).toHaveBeenCalled())
    const [, col] = vi.mocked(calcColumnsApi.save).mock.calls[0]
    expect((col as { name: string }).name).toBe('Revenue Band')
    expect((col as { expression: string }).expression).toMatch(/IF\(/)
  })

  it('says the range is loading rather than offering an impossible bin', async () => {
    let release: (v: unknown) => void = () => {}
    vi.mocked(widgetDataApi.query).mockReturnValue(
      new Promise(res => { release = res }) as never)
    await pick()
    expect(await screen.findByText(/reading the range/i)).toBeInTheDocument()
    release({ rows: [] })
  })

  it('says so when the range cannot be read, instead of failing at Create', async () => {
    vi.mocked(widgetDataApi.query).mockRejectedValue(new Error('down'))
    await pick()
    expect(await screen.findByText(/could not read/i)).toBeInTheDocument()
  })

  it('refuses a column whose values are all the same', async () => {
    // No range means no bins, and that is a fact about the data — it should be
    // said plainly rather than surfacing as "pick at least two bin edges".
    vi.mocked(widgetDataApi.query).mockResolvedValue(scalar(5) as never)
    await pick()
    expect(await screen.findByText(/every value.*the same|no range/i)).toBeInTheDocument()
  })
})

describe('CustomCategoryPanel coverage', () => {
  it('says how many rows the groups cover and which values fall to Other', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({
      rows: [{ name: 'US', value: 6 }, { name: 'CA', value: 3 }, { name: 'UK', value: 1 }],
      truncation: { applied: true, shown: 3, of: 40 },
    } as any)
    render(<CustomCategoryPanel datasetId={1} columns={columns} onSaved={vi.fn()} />)
    fireEvent.change(screen.getByLabelText(/Source column/i), { target: { value: 'region' } })
    const input = await screen.findByLabelText('Group for US')
    fireEvent.change(input, { target: { value: 'North America' } })
    const status = screen.getByTestId('category-coverage').textContent ?? ''
    expect(status).toContain('60% of rows go to a named group')
    expect(status).toContain('4 rows (2 values) fall to “Other”: CA, UK')
    expect(status).toContain('Listing the 3 most common of 40 values')
  })
})

