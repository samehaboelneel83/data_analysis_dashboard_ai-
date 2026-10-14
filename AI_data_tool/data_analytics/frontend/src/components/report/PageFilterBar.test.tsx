import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import PageFilterBar, { type PageFilterColumn } from './PageFilterBar'
import type { PageFilter } from '../../lib/pageFilters'

vi.mock('../../services/api', () => ({
  widgetDataApi: {
    query: vi.fn(async (_ds: number, config: any, _c: unknown, wt: string) => {
      if (wt === 'bar') return { rows: [{ name: 1, value: 4 }, { name: 250, value: 2 }, { name: 500, value: 1 }] }
      const all = [{ name: 'delivered', value: 90 }, { name: 'shipped', value: 8 }, { name: 'canceled', value: 2 }]
      const q = config.filters?.[0]?.value
      return { rows: q ? all.filter(r => r.name.includes(q)) : all }
    }),
  },
}))

const COLS: PageFilterColumn[] = [
  { name: 'customer_id', kind: 'number', datasetId: 1 },
  { name: 'order_status', kind: 'text', datasetId: 1 },
  { name: 'bought_at', kind: 'date', datasetId: 1 },
]

function setup(filters: PageFilter[] = []) {
  const onChange = vi.fn()
  render(<PageFilterBar columns={COLS} filters={filters} onChange={onChange} />)
  return onChange
}

describe('PageFilterBar', () => {
  beforeEach(() => vi.clearAllMocks())

  it('filters the page by a number range: customer_id from 1 to 20', async () => {
    const onChange = setup()
    fireEvent.click(screen.getByTestId('page-filter-add'))
    fireEvent.click(screen.getByRole('option', { name: /customer_id/ }))
    // The data's own range is offered as a hint.
    expect(await screen.findByText('In the data: 1 – 500')).toBeInTheDocument()
    fireEvent.change(screen.getByTestId('page-filter-from'), { target: { value: '1' } })
    fireEvent.change(screen.getByTestId('page-filter-to'), { target: { value: '20' } })
    fireEvent.click(screen.getByTestId('page-filter-apply'))
    expect(onChange).toHaveBeenCalledWith([expect.objectContaining({ column: 'customer_id', kind: 'range', from: 1, to: 20 })])
  })

  it('picks text values from the data, searchable, with counts', async () => {
    const onChange = setup()
    fireEvent.click(screen.getByTestId('page-filter-add'))
    fireEvent.click(screen.getByRole('option', { name: /order_status/ }))
    const list = await screen.findByRole('listbox', { name: 'order_status' })
    await within(list).findByText('delivered')
    fireEvent.click(within(list).getByRole('option', { name: /delivered/ }))
    fireEvent.click(within(list).getByRole('option', { name: /shipped/ }))
    expect(screen.getByText('2 selected')).toBeInTheDocument()
    fireEvent.click(screen.getByTestId('page-filter-apply'))
    expect(onChange).toHaveBeenCalledWith([expect.objectContaining({ kind: 'values', values: ['delivered', 'shipped'] })])
  })

  it('can match text that contains a word instead', async () => {
    const onChange = setup()
    fireEvent.click(screen.getByTestId('page-filter-add'))
    fireEvent.click(screen.getByRole('option', { name: /order_status/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Contains' }))
    fireEvent.change(screen.getByTestId('page-filter-contains'), { target: { value: 'deliv' } })
    fireEvent.click(screen.getByTestId('page-filter-apply'))
    expect(onChange).toHaveBeenCalledWith([expect.objectContaining({ kind: 'contains', text: 'deliv' })])
  })

  it('shows each filter as a chip that can be changed or removed', async () => {
    const f: PageFilter = { id: 'a', column: 'customer_id', kind: 'range', from: 1, to: 20 }
    const onChange = setup([f])
    expect(screen.getByTestId('page-filter-chip')).toHaveTextContent('customer_id: 1 – 20')
    fireEvent.click(screen.getByRole('button', { name: /Remove filter: customer_id/ }))
    expect(onChange).toHaveBeenCalledWith([])
    fireEvent.click(screen.getByRole('button', { name: 'customer_id: 1 – 20' }))
    await waitFor(() => expect(screen.getByTestId('page-filter-from')).toHaveValue(1))
  })

  it('does not apply an empty filter', () => {
    const onChange = setup()
    fireEvent.click(screen.getByTestId('page-filter-add'))
    fireEvent.click(screen.getByRole('option', { name: /bought_at/ }))
    fireEvent.click(screen.getByTestId('page-filter-apply'))
    expect(onChange).toHaveBeenCalledWith([])
  })
})
