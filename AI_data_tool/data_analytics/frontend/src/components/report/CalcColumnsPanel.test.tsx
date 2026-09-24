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

import { customFunctionsApi } from '../../services/api'

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
    await screen.findByTestId('expr-builder')
    expect(screen.queryByTestId('cat-Custom')).toBeNull()
  })
})
