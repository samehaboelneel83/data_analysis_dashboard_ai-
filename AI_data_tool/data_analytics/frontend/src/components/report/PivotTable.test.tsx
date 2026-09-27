import { describe, it, expect } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import PivotTable, { spans, type PivotData } from './PivotTable'

// SAS's crosstab: Continent > Country down the side, Product Line > Product
// Category across the top, a measure under each column.
const data: PivotData = {
  type: 'pivot',
  row_fields: ['Continent', 'Country'],
  column_fields: ['Product Line', 'Product Category'],
  measures: ['Quantity Ordered'],
  column_keys: [['Sports', 'Golf'], ['Sports', 'Swim'], ['Outdoors', 'Tents']],
  rows: [
    { keys: ['Europe', 'France'], values: [15, 7, null] },
    { keys: ['Europe', 'Spain'], values: [4, null, 2] },
    { keys: ['Asia', 'China'], values: [null, 3, null] },
  ],
}

describe('spans', () => {
  it('counts consecutive entries sharing the leading keys', () => {
    expect(spans([['a', 1], ['a', 2], ['b', 1]], 0)).toEqual([2, 0, 1])
    expect(spans([['a', 1], ['a', 2], ['b', 1]], 1)).toEqual([1, 1, 1])
  })
})

describe('the nested crosstab', () => {
  it('stacks column levels as header rows, the outer spanning its children', () => {
    render(<PivotTable data={data} />)
    const sports = screen.getByRole('columnheader', { name: 'Sports' })
    expect(sports).toHaveAttribute('colspan', '2')
    expect(screen.getByRole('columnheader', { name: 'Golf' })).toHaveAttribute('colspan', '1')
    expect(screen.getAllByRole('columnheader', { name: 'Quantity Ordered' })).toHaveLength(3)
  })

  it('merges a repeated row label down the side', () => {
    render(<PivotTable data={data} />)
    expect(screen.getByRole('rowheader', { name: 'Europe' })).toHaveAttribute('rowspan', '2')
    expect(screen.getByRole('rowheader', { name: 'France' })).toBeInTheDocument()
    expect(screen.getAllByRole('rowheader', { name: 'Europe' })).toHaveLength(1)
  })

  it('draws an empty cell as a dash and a value formatted', () => {
    render(<PivotTable data={data} formats={{ 'Quantity Ordered': { type: 'number', decimals: 0 } }} />)
    const spain = screen.getByRole('rowheader', { name: 'Spain' }).closest('tr')!
    const cells = within(spain).getAllByRole('cell').map(c => c.textContent)
    expect(cells).toEqual(['4', '—', '2'])
  })

  it('several measures: one header each under every column', () => {
    render(<PivotTable data={{ ...data, measures: ['Qty', 'Cost'], column_keys: [['Sports', 'Golf']],
      rows: [{ keys: ['Europe', 'France'], values: [15, 3] }] }} />)
    expect(screen.getByRole('columnheader', { name: 'Golf' })).toHaveAttribute('colspan', '2')
    expect(screen.getByRole('columnheader', { name: 'Qty' })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'Cost' })).toBeInTheDocument()
  })
})
