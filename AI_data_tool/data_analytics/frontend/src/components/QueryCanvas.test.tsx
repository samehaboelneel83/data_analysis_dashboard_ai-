import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import QueryCanvas from './QueryCanvas'

const props = {
  tables: ['orders', 'customers'],
  kinds: { orders: 'table', customers: 'view' },
  columnsByTable: { orders: ['id', 'customer_id'], customers: ['id', 'name'] },
  joins: [],
  onAddJoin: vi.fn(),
  onCycleJoin: vi.fn(),
  onRemoveJoin: vi.fn(),
}

describe('QueryCanvas', () => {
  it('renders a box per table with its kind badge and columns', () => {
    render(<QueryCanvas {...props} />)
    expect(screen.getByTestId('canvas-table-orders')).toHaveTextContent('orders')
    expect(screen.getByTestId('canvas-table-customers')).toHaveTextContent('view')
    expect(screen.getByRole('button', { name: 'customer_id' })).toBeInTheDocument()
  })

  it('click-connects two columns across tables into a join', () => {
    const onAddJoin = vi.fn()
    render(<QueryCanvas {...props} onAddJoin={onAddJoin} />)
    fireEvent.click(screen.getByRole('button', { name: 'customer_id' }))
    expect(screen.getByText(/Joining from orders.customer_id/)).toBeInTheDocument()
    fireEvent.click(screen.getAllByRole('button', { name: 'id' })[1])   // customers.id
    expect(onAddJoin).toHaveBeenCalledWith({
      left_table: 'orders', left_column: 'customer_id',
      table: 'customers', right_column: 'id', how: 'left',
    })
  })

  it('clicking two columns in the SAME table re-arms instead of self-joining', () => {
    const onAddJoin = vi.fn()
    render(<QueryCanvas {...props} onAddJoin={onAddJoin} />)
    fireEvent.click(screen.getByRole('button', { name: 'customer_id' }))
    fireEvent.click(screen.getAllByRole('button', { name: 'id' })[0])   // orders.id
    expect(onAddJoin).not.toHaveBeenCalled()
    expect(screen.getByText(/Joining from orders.id/)).toBeInTheDocument()
  })

  it('D3: column checkbox reflects selection and toggles it', () => {
    const onToggleColumn = vi.fn()
    render(<QueryCanvas {...props} selectedColumns={new Set(['orders.id'])} onToggleColumn={onToggleColumn} />)
    const idCheckbox = screen.getByLabelText('Include orders.id') as HTMLInputElement
    expect(idCheckbox.checked).toBe(true)
    const custIdCheckbox = screen.getByLabelText('Include orders.customer_id') as HTMLInputElement
    expect(custIdCheckbox.checked).toBe(false)
    fireEvent.click(custIdCheckbox)
    expect(onToggleColumn).toHaveBeenCalledWith('orders', 'customer_id')
  })

  it('D3: aggregation badge only shows for selected columns and cycles on click', () => {
    const onCycleAggregation = vi.fn()
    render(<QueryCanvas {...props} selectedColumns={new Set(['orders.id'])}
      aggByColumn={{ 'orders.id': 'sum' }} onCycleAggregation={onCycleAggregation} />)
    expect(screen.queryByLabelText('Aggregation orders.customer_id')).not.toBeInTheDocument()
    const badge = screen.getByLabelText('Aggregation orders.id')
    expect(badge).toHaveTextContent('sum')
    fireEvent.click(badge)
    expect(onCycleAggregation).toHaveBeenCalledWith('orders', 'id')
  })

  it('the x removes the join', () => {
    const onRemoveJoin = vi.fn()
    render(<QueryCanvas {...props}
      joins={[{ left_table: 'orders', left_column: 'customer_id', table: 'customers', right_column: 'id', how: 'left' }]}
      onRemoveJoin={onRemoveJoin} />)
    fireEvent.click(screen.getByLabelText('Remove join 1'))
    expect(onRemoveJoin).toHaveBeenCalledWith(0)
  })

  it('the edge label opens a picker offering every join type', () => {
    // Replaces the old cycle button: with five types, cycling made finding
    // "full outer" a guessing game, and it could never reach `cross` at all.
    render(<QueryCanvas {...props}
      joins={[{ left_table: 'orders', left_column: 'customer_id', table: 'customers', right_column: 'id', how: 'left' }]} />)
    expect(screen.queryByRole('menu', { name: 'Join type' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByTestId('join-label-0'))

    const menu = screen.getByRole('menu', { name: 'Join type' })
    for (const label of ['Inner', 'Left', 'Right', 'Full outer', 'Cross']) {
      expect(within(menu).getByRole('menuitemradio', { name: new RegExp(label) })).toBeInTheDocument()
    }
    // The current type is marked, not merely displayed.
    expect(within(menu).getByRole('menuitemradio', { name: /Left/ })).toHaveAttribute('aria-checked', 'true')
  })

  it('picking a type sets it outright', () => {
    const onSetJoinType = vi.fn()
    render(<QueryCanvas {...props}
      joins={[{ left_table: 'orders', left_column: 'customer_id', table: 'customers', right_column: 'id', how: 'left' }]}
      onSetJoinType={onSetJoinType} />)
    fireEvent.click(screen.getByTestId('join-label-0'))
    fireEvent.click(screen.getByRole('menuitemradio', { name: /Full outer/ }))
    expect(onSetJoinType).toHaveBeenCalledWith(0, 'full')
  })

  it('offers a close button on joined tables but never on the base', () => {
    // Closing the base would not tidy the diagram, it would empty the query.
    const onCloseTable = vi.fn()
    render(<QueryCanvas {...props} onCloseTable={onCloseTable} />)
    expect(screen.queryByTestId('close-table-orders')).not.toBeInTheDocument()
    fireEvent.click(screen.getByTestId('close-table-customers'))
    expect(onCloseTable).toHaveBeenCalledWith('customers')
  })
})
