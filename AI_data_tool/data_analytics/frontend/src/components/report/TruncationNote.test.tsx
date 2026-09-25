import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { TruncationNote, truncationSentence, SHOW_ALL_CEILING } from './TruncationNote'

describe('TruncationNote', () => {
  it('says what was cut, in one sentence', () => {
    expect(truncationSentence({ applied: true, shown: 20, of: 213 }, 'city')).toBe('Showing 20 of 213 city values')
  })
  it('a point plot counts points, and a nameless cut counts categories', () => {
    expect(truncationSentence({ applied: true, shown: 500, of: 2000, unit: 'points' }, 'x')).toBe('Showing 500 of 2,000 points')
    expect(truncationSentence({ applied: true, shown: 50, of: 80, unit: 'categories' })).toBe('Showing 50 of 80 categories')
    expect(truncationSentence({ applied: true, shown: 50, of: 80, unit: 'categories' }, 'region')).toBe('Showing 50 of 80 region values')
  })
  it('a table counts rows', () => {
    expect(truncationSentence({ applied: true, shown: 50, of: 120, unit: 'rows' })).toBe('Showing 50 of 120 rows')
  })
  it('renders nothing when nothing was cut', () => {
    const { container } = render(<TruncationNote t={{ applied: false, shown: 4, of: 4 }} />)
    expect(container.textContent).toBe('')
  })
  it('offers "Show all" to an editor and passes the full count', () => {
    const f = vi.fn()
    render(<TruncationNote t={{ applied: true, shown: 5, of: 14, reason: 'limit' }} dimension="country" onShowMore={f} />)
    fireEvent.click(screen.getByRole('button', { name: 'Show all' }))
    expect(f).toHaveBeenCalledWith(14)
  })
  it('caps a huge "show all" at a readable page', () => {
    const f = vi.fn()
    render(<TruncationNote t={{ applied: true, shown: 20, of: 90000 }} onShowMore={f} />)
    fireEvent.click(screen.getByRole('button', { name: `Show ${SHOW_ALL_CEILING}` }))
    expect(f).toHaveBeenCalledWith(SHOW_ALL_CEILING)
  })
  it('a reader sees the disclosure but no button', () => {
    render(<TruncationNote t={{ applied: true, shown: 5, of: 14 }} dimension="country" />)
    expect(screen.getByText(/Showing 5 of 14 country values/)).toBeTruthy()
    expect(screen.queryByRole('button')).toBeNull()
  })
})

describe('missingCategorySentence', () => {
  it('counts the rows and names the field, in the singular when it is one', async () => {
    const { missingCategorySentence } = await import('./TruncationNote')
    expect(missingCategorySentence(1200, 'region')).toBe('1,200 rows with no region are not shown')
    expect(missingCategorySentence(1, 'region')).toBe('1 row with no region is not shown')
    expect(missingCategorySentence(2)).toBe('2 rows with no category are not shown')
  })
})
