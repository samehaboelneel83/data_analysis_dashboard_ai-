import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import ScatterChartRenderer from './ScatterChartRenderer'

/** C-07: a scatter whose X is a text dimension ("Aurora Suite") drew axes and
 *  no points -- recharts drops every non-numeric x -- and said nothing. */
const base = { data: {}, cfg: {}, rtl: false, broadcasts: false, localSelected: null,
  onClickPoint: () => {}, plotW: 400, plotH: 300 } as any

describe('ScatterChartRenderer (C-07)', () => {
  it('says the X axis needs numbers when every x is text', () => {
    render(<ScatterChartRenderer {...base} rows={[{ name: 'Aurora Suite', value: 10 }, { name: 'Nimbus', value: 4 }]} />)
    expect(screen.getByText(/X must be a number/i)).toBeInTheDocument()
  })
  it('draws normally when x is numeric', () => {
    render(<ScatterChartRenderer {...base} rows={[{ name: 170, value: 60 }, { name: 180, value: 75 }]} />)
    expect(screen.queryByText(/X must be a number/i)).toBeNull()
  })
})
