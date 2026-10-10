import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, waitFor, within } from '@testing-library/react'
import { renderWithProviders as render, screen } from '../../test/renderWithProviders'
import CalcColumnsPanel from './CalcColumnsPanel'

vi.mock('../../services/api', () => ({
  columnsApi: { duplicate: vi.fn() },
  calcColumnsApi: { list: vi.fn().mockResolvedValue([]), save: vi.fn(), delete: vi.fn(), preview: vi.fn() },
  customFunctionsApi: { list: vi.fn().mockResolvedValue([]), save: vi.fn(), delete: vi.fn(), preview: vi.fn() },
}))

// ExpressionBuilder is a large, independent component -- stubbed here to a
// summary of the one prop this task changes, so this file tests
// CalcColumnsPanel's own responsibility (building functionsCatalog) rather
// than re-testing ExpressionBuilder's internals.
vi.mock('../expr/ExpressionBuilder', () => ({
  default: (props: { functionsCatalog: { label: string; items: { label: string }[] }[] }) => (
    <div data-testid="expr-builder">
      {props.functionsCatalog.map(cat => (
        <div key={cat.label} data-testid={`cat-${cat.label}`}>
          {cat.items.map(item => <span key={item.label}>{item.label}</span>)}
        </div>
      ))}
    </div>
  ),
}))

import { calcColumnsApi, customFunctionsApi } from '../../services/api'

describe('CalcColumnsPanel custom functions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(customFunctionsApi.list).mockResolvedValue([])
  })

  it('renders the custom-functions management panel', async () => {
    render(<CalcColumnsPanel datasetId={5} columns={[]} onChanged={vi.fn()} />)
    expect(await screen.findByText('Custom functions')).toBeInTheDocument()
  })

  it('offers a saved custom function in the expression palette', async () => {
    vi.mocked(customFunctionsApi.list).mockResolvedValue([
      { name: 'PROFIT_MARGIN', params: ['revenue', 'cost'], expression: '(revenue - cost) / revenue' },
    ])
    render(<CalcColumnsPanel datasetId={5} columns={[]} onChanged={vi.fn()} />)

    fireEvent.click(await screen.findByRole('button', { name: '+ Add' }))
    // A new column starts from "What do you want to make?"; the formula is one click away.
    fireEvent.click(await screen.findByRole('button', { name: 'Write a formula myself' }))
    await waitFor(() => expect(screen.getByTestId('cat-Custom')).toBeInTheDocument())
    // Scoped to the palette's Custom category, not just anywhere on screen --
    // CustomFunctionsPanel's own management list renders the same
    // "NAME(params)" text for this function elsewhere in the document.
    const customCat = screen.getByTestId('cat-Custom')
    expect(within(customCat).getByText('PROFIT_MARGIN(revenue, cost)')).toBeInTheDocument()
  })

  it('does not add a "Custom" category when there are no custom functions', async () => {
    render(<CalcColumnsPanel datasetId={5} columns={[]} onChanged={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: '+ Add' }))
    // A new column starts from "What do you want to make?"; the formula is one click away.
    fireEvent.click(await screen.findByRole('button', { name: 'Write a formula myself' }))
    await screen.findByTestId('expr-builder')
    expect(screen.queryByTestId('cat-Custom')).toBeNull()
  })
})

describe('deleting a calculated column something still uses (E05)', () => {
  it('asks again with what uses it, then deletes with force', async () => {
    const { calcColumnsApi } = await import('../../services/api')
    vi.mocked(calcColumnsApi.list).mockResolvedValue([{ name: 'unit', expression: '[profit] / [sales]' }] as never)
    vi.mocked(calcColumnsApi.delete).mockReset()
      .mockRejectedValueOnce(Object.assign(new Error('409'), { response: { status: 409, data: {
        detail: "'unit' is used by measure 'U'. Delete anyway with ?force=true." } } }))
      .mockResolvedValueOnce([] as never)
    render(<CalcColumnsPanel datasetId={3} columns={[]} onChanged={vi.fn()} />)
    await screen.findByText('unit')

    fireEvent.click(screen.getByTitle('Delete'))
    fireEvent.click(await screen.findByRole('button', { name: /^delete$/i }))
    expect(await screen.findByRole('alertdialog')).toHaveTextContent("used by measure 'U'")
    fireEvent.click(screen.getByRole('button', { name: 'Delete anyway' }))

    await waitFor(() => expect(calcColumnsApi.delete).toHaveBeenLastCalledWith(3, 'unit', true))
  })
})


describe('a new calculated column without writing code (2026-10-10)', () => {
  const columns = [
    { id: 1, name: 'price', dtype: 'numeric', missing_pct: 0, stats: {} },
    { id: 2, name: 'make', dtype: 'categorical', missing_pct: 0, stats: {} },
  ] as never[]

  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(customFunctionsApi.list).mockResolvedValue([])
  })

  async function open() {
    render(<CalcColumnsPanel datasetId={5} columns={columns} onChanged={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: '+ Add' }))
    expect(await screen.findByText('What do you want to make?')).toBeInTheDocument()
  }

  it('bands: the form writes the formula and names the column', async () => {
    await open()
    fireEvent.click(screen.getByRole('button', { name: /Group numbers into bands/ }))
    fireEvent.change(screen.getByLabelText('Number column'), { target: { value: 'price' } })
    fireEvent.change(screen.getByLabelText('Upper limit of band 1'), { target: { value: '500000' } })
    fireEvent.change(screen.getByLabelText('Label of band 1'), { target: { value: 'Budget' } })
    fireEvent.change(screen.getByLabelText('Upper limit of band 2'), { target: { value: '200' } })
    // Limits out of order are explained, not written.
    expect(screen.getByRole('status')).toHaveTextContent('must be bigger')
    fireEvent.change(screen.getByLabelText('Upper limit of band 2'), { target: { value: '1500000' } })
    fireEvent.change(screen.getByLabelText('Label of band 2'), { target: { value: 'Mid' } })
    fireEvent.change(screen.getByLabelText('Label for all other rows'), { target: { value: 'Luxury' } })
    expect(screen.getByTestId('calc-written-formula'))
      .toHaveTextContent("IF(price < 500000, 'Budget', IF(price < 1500000, 'Mid', 'Luxury'))")
    expect(screen.getByLabelText('Column name')).toHaveValue('price_band')
  })

  it('Test shows how many rows got each label', async () => {
    vi.mocked(calcColumnsApi.preview).mockResolvedValue({ ok: true, dtype: 'text', sample: ['Budget'],
      summary: { kind: 'labels', rows: 9319, empty: 0, distinct: 2, top: [['Budget', 9000], ['Mid', 319]] } })
    await open()
    fireEvent.click(screen.getByRole('button', { name: /Combine text/ }))
    fireEvent.change(screen.getByLabelText('Column 1 to combine'), { target: { value: 'make' } })
    fireEvent.change(screen.getByLabelText('Column 2 to combine'), { target: { value: 'price' } })
    fireEvent.click(screen.getByRole('button', { name: /Test/ }))
    const result = await screen.findByTestId('calc-test-result')
    expect(result).toHaveTextContent('2 different labels over 9,319 rows')
    expect(result).toHaveTextContent('Budget · 9,000')
  })

  it('label rules: the Test result stays on screen (it was wiped on the next render)', async () => {
    vi.mocked(calcColumnsApi.preview).mockResolvedValue({ ok: true, dtype: 'text', sample: ['Hot'],
      summary: { kind: 'labels', rows: 10, empty: 0, distinct: 2, top: [['Hot', 3], ['Other', 7]] } })
    await open()
    fireEvent.click(screen.getByRole('button', { name: /Label rows by conditions/ }))
    fireEvent.change(screen.getByLabelText('Column of condition 1'), { target: { value: 'make' } })
    fireEvent.change(screen.getByLabelText('Value of condition 1'), { target: { value: 'Kia' } })
    fireEvent.change(screen.getByLabelText('Label for rule 1'), { target: { value: 'Hot' } })
    fireEvent.change(screen.getByLabelText('Label for all other rows'), { target: { value: 'Other' } })
    expect(screen.getByTestId('calc-written-formula')).toHaveTextContent("IF(make == 'Kia', 'Hot', 'Other')")
    fireEvent.click(screen.getByRole('button', { name: /Test/ }))
    expect(await screen.findByTestId('calc-test-result')).toHaveTextContent('Hot · 3')
    await new Promise(r => setTimeout(r, 50))
    expect(screen.getByTestId('calc-test-result')).toHaveTextContent('Other · 7')
  })

  it('a broken formula is explained, with the raw error behind "Show details"', async () => {
    vi.mocked(calcColumnsApi.preview).mockResolvedValue({ ok: false, error: "name 'cot' is not defined",
      problem: { code: 'unknown_name', name: 'cot', suggest: 'cost' } })
    await open()
    fireEvent.click(screen.getByRole('button', { name: 'Write a formula myself' }))
    // The stubbed ExpressionBuilder has no box; a test still needs an expression.
    fireEvent.click(screen.getByRole('button', { name: '← Back to the choices' }))
    fireEvent.click(screen.getByRole('button', { name: /Part of a date/ }))
    fireEvent.change(screen.getByLabelText('Date column'), { target: { value: 'make' } })
    fireEvent.click(screen.getByRole('button', { name: /Test/ }))
    const result = await screen.findByTestId('calc-test-result')
    expect(result).toHaveTextContent('There is no column or function called "cot". Did you mean "cost"?')
    expect(result).not.toHaveTextContent('is not defined')
    fireEvent.click(within(result).getByRole('button', { name: 'Show details' }))
    expect(result).toHaveTextContent("name 'cot' is not defined")
  })
})
