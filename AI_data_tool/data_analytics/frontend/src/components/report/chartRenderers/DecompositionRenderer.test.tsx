import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import DecompositionRenderer from './DecompositionRenderer'

/**
 * The decomposition tree's job is to stay honest while the reader explores.
 *
 * Three things carry that: a share shown beside every number so nobody has to
 * divide in their head, a breadcrumb that makes every drill reversible, and a
 * visible mark on any level the SERVER chose rather than the reader.
 */
const props = (over: Record<string, unknown> = {}) => ({
  rows: [], cfg: {}, rtl: false, broadcasts: false, localSelected: null,
  onClickPoint: vi.fn(),
  data: {
    type: 'decomposition',
    total: 1000,
    path: [],
    split_by: 'region',
    auto: false,
    available: ['product', 'channel'],
    at_max_depth: false,
    children: [
      { name: 'EMEA', value: 600, rows: 60 },
      { name: 'APAC', value: 400, rows: 40 },
    ],
    ...(over.data as object ?? {}),
  },
  ...over,
})

describe('DecompositionRenderer', () => {
  it('shows the total and how it splits', () => {
    render(<DecompositionRenderer {...props() as any} />)
    // Localised: fmtStr goes through toLocaleString, and this environment does
    // not render Latin digits.
    expect(screen.getByText((1000).toLocaleString())).toBeInTheDocument()
    expect(screen.getByText('EMEA')).toBeInTheDocument()
    expect(screen.getByText('region')).toBeInTheDocument()
  })

  it('shows each part as a share of the whole', () => {
    // A bare "600" next to a total of 1,000 makes the reader do the division.
    render(<DecompositionRenderer {...props() as any} />)
    expect(screen.getByText(/60\.0%/)).toBeInTheDocument()
    expect(screen.getByText(/40\.0%/)).toBeInTheDocument()
  })

  it('drills into a child by extending the path', () => {
    const p = props()
    render(<DecompositionRenderer {...p as any} />)
    fireEvent.click(screen.getByText('EMEA'))

    expect(p.onClickPoint).toHaveBeenCalledWith(
      expect.objectContaining({ path: [{ field: 'region', value: 'EMEA' }] }))
  })

  it('climbs back out by truncating the path at a crumb', () => {
    // Every drill has to be reversible or an exploration becomes a maze.
    const p = props({ data: {
      total: 600, path: [{ field: 'region', value: 'EMEA' }], split_by: 'product',
      auto: false, available: ['channel'], at_max_depth: false,
      children: [{ name: 'Alpha', value: 600, rows: 60 }],
    } })
    render(<DecompositionRenderer {...p as any} />)

    fireEvent.click(screen.getByRole('button', { name: 'All' }))
    expect(p.onClickPoint).toHaveBeenCalledWith(expect.objectContaining({ path: [] }))
  })

  it('marks a level the server chose', () => {
    // A suggestion passed off as the reader's own decision is how an analysis
    // quietly becomes wrong.
    render(<DecompositionRenderer {...props({ data: {
      total: 1000, path: [], split_by: 'tier', auto: true,
      available: ['region'], at_max_depth: false,
      children: [{ name: 'Paid', value: 900, rows: 10 }],
    } }) as any} />)
    expect(screen.getByText(/suggested/)).toBeInTheDocument()
  })

  it('does not mark a level the reader chose', () => {
    render(<DecompositionRenderer {...props() as any} />)
    expect(screen.queryByText(/suggested/)).toBeNull()
  })

  it('says how many groups an Other bucket hides', () => {
    render(<DecompositionRenderer {...props({ data: {
      total: 1000, path: [], split_by: 'sku', auto: false,
      available: [], at_max_depth: false,
      children: [
        { name: 'A', value: 900, rows: 9 },
        { name: 'Other', value: 100, rows: 40, collapsed: 35, terminal: true },
      ],
    } }) as any} />)
    expect(screen.getByText(/35 more/)).toBeInTheDocument()
  })

  it('does not offer to drill a terminal bucket', () => {
    const p = props({ data: {
      total: 1000, path: [], split_by: 'sku', auto: false,
      available: ['region'], at_max_depth: false,
      children: [{ name: 'Other', value: 100, rows: 40, collapsed: 35, terminal: true }],
    } })
    render(<DecompositionRenderer {...p as any} />)
    fireEvent.click(screen.getByText(/Other/))
    expect(p.onClickPoint).not.toHaveBeenCalled()
  })

  it('renders an empty branch without breaking', () => {
    // A saved widget outlives its data; a vanished branch must be escapable.
    render(<DecompositionRenderer {...props({ data: {
      total: 0, path: [{ field: 'region', value: 'ATLANTIS' }], split_by: 'product',
      auto: false, available: [], at_max_depth: false, children: [],
    } }) as any} />)
    expect(screen.getByText(/No rows in this branch/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'All' })).toBeInTheDocument()
  })
})
