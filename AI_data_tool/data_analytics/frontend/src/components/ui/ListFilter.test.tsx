import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { useListFilter, matches } from './ListFilter'

/**
 * Dashboard, Reports and Connections each rendered their whole
 * collection with no way to narrow it -- fine at a demo's fifteen rows, useless
 * at four hundred, where finding one report means scrolling past every other.
 *
 * The filter is client-side because the list endpoints take no limit/offset,
 * and because filtering rows the browser already holds needs no API change and
 * adds no dependency.
 */

type Row = { name: string; description?: string | null }

function Harness({ items }: { items: Row[] }) {
  const f = useListFilter(items, r => [r.name, r.description], 'Search rows')
  return (
    <div>
      {f.input}
      <ul>{f.filtered.map(r => <li key={r.name}>{r.name}</li>)}</ul>
      {f.noMatches && <p>No matches</p>}
    </div>
  )
}

const many = (n: number): Row[] =>
  Array.from({ length: n }, (_, i) => ({ name: `row-${i}`, description: null }))

const search = () => screen.getByLabelText('Search rows')
const shown = () => screen.getAllByRole('listitem').map(li => li.textContent)

describe('matches', () => {
  it('is case-insensitive', () => {
    expect(matches(['Quarterly Revenue'], 'quarterly')).toBe(true)
  })

  it('matches a substring, not just a prefix', () => {
    // Users search for the distinctive word, which is rarely the first one.
    expect(matches(['Quarterly Revenue'], 'reven')).toBe(true)
  })

  it('ignores null and undefined fields', () => {
    // `description` is frequently null, and reading `.toLowerCase()` off it
    // would throw rather than simply not match.
    expect(matches([null, undefined, 'ok'], 'ok')).toBe(true)
    expect(matches([null, undefined], 'ok')).toBe(false)
  })

  it('treats an all-whitespace query as no query', () => {
    expect(matches(['anything'], '   ')).toBe(true)
  })
})

describe('useListFilter', () => {
  it('shows every row before a query is typed', () => {
    render(<Harness items={many(10)} />)
    expect(shown()).toHaveLength(10)
  })

  it('narrows to the matching rows', () => {
    render(<Harness items={many(20)} />)
    fireEvent.change(search(), { target: { value: 'row-1' } })
    // row-1 and row-10..row-19
    expect(shown()).toContain('row-1')
    expect(shown()).not.toContain('row-2')
  })

  it('searches every field the caller names, not just the first', () => {
    // Padded past the box's visibility threshold; the point under test is
    // which FIELDS are searched, not when the box appears.
    render(<Harness items={[
      { name: 'alpha', description: 'quarterly numbers' },
      { name: 'beta', description: 'something else' },
      ...many(8),
    ]} />)
    fireEvent.change(search(), { target: { value: 'quarterly' } })
    expect(shown()).toEqual(['alpha'])
  })

  it('restores the full list when the query is cleared', () => {
    render(<Harness items={many(10)} />)
    fireEvent.change(search(), { target: { value: 'row-3' } })
    expect(shown()).toHaveLength(1)
    fireEvent.change(search(), { target: { value: '' } })
    expect(shown()).toHaveLength(10)
  })

  it('reports no-matches separately from an empty collection', () => {
    // The page's own "nothing yet" copy is wrong here: the org DOES have rows,
    // this search just did not find any. Telling the user they have nothing
    // would be the same class of lie as rendering an outage as an empty state.
    render(<Harness items={many(10)} />)
    fireEvent.change(search(), { target: { value: 'zzzz' } })
    expect(screen.getByText('No matches')).toBeInTheDocument()
  })

  it('hides the box while the list is short enough to scan', () => {
    // Below the threshold the search box is chrome competing with the content
    // it would filter.
    render(<Harness items={many(3)} />)
    expect(screen.queryByLabelText('Search rows')).not.toBeInTheDocument()
  })

  it('shows the box once the list is long', () => {
    render(<Harness items={many(8)} />)
    expect(screen.getByLabelText('Search rows')).toBeInTheDocument()
  })
})
