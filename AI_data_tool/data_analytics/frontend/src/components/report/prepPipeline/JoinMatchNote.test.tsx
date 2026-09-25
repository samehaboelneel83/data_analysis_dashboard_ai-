import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import JoinMatchNote from './JoinMatchNote'
import { prepApi } from '../../../services/api'

vi.mock('../../../services/api', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  prepApi: { joinCheck: vi.fn() },
}))

describe('JoinMatchNote', () => {
  it('shows the match rate, the misses and the row multiplier', async () => {
    vi.mocked(prepApi.joinCheck).mockResolvedValue({
      rows: 6, matched_rows: 4, pct_rows: 66, blank_keys: 1, unmatched: [{ key: 'x', rows: 1 }], unmatched_values: 1,
      duplicate_right_keys: 1, duplicate_examples: [{ key: 'b', count: 2 }], rows_after: 7, type_mismatch: [],
    })
    render(<JoinMatchNote datasetId={1} index={0}
      steps={[{ kind: 'join', dataset_id: 2, how: 'left', left_on: 'cust', right_on: 'id' }]} />)
    const note = await screen.findByTestId('join-match', {}, { timeout: 2000 })
    expect(note.textContent).toContain('66% of rows find a match')
    expect(note.textContent).toContain('x (1)')
    expect(note.textContent).toContain('6 rows become 7')
    expect(prepApi.joinCheck).toHaveBeenCalledWith(1, [expect.objectContaining({ kind: 'join', dataset_id: 2 })], 0)
  })

  it('stays silent until the keys are chosen', () => {
    const { container } = render(<JoinMatchNote datasetId={1} index={0} steps={[{ kind: 'join', dataset_id: 2 }]} />)
    expect(container.textContent).toBe('')
  })
})

describe('JoinMatchNote (E06: fan-out, the other side, freshness)', () => {
  const base = { rows: 1000, matched_rows: 1000, pct_rows: 100, blank_keys: 0, unmatched: [], unmatched_values: 0,
    duplicate_right_keys: 0, duplicate_examples: [], type_mismatch: [] }

  it('states the rows after the join and the multiplier for a right join, with the orphans kept', async () => {
    vi.mocked(prepApi.joinCheck).mockResolvedValue({ ...base, rows_after: 1170, multiplier: 1.17,
      right_rows: 400, right_unmatched_rows: 30 })
    render(<JoinMatchNote datasetId={1} index={0}
      steps={[{ kind: 'join', dataset_id: 2, how: 'right', left_on: 'cust', right_on: 'id' }]}
      joined={{ name: 'Customers', last_refreshed_at: new Date(Date.now() - 3 * 86_400_000).toISOString() }} />)
    expect(await screen.findByTestId('join-fanout', {}, { timeout: 2000 })).toHaveTextContent('Rows after the join: 1,170 (×1.17)')
    const note = screen.getByTestId('join-match')
    expect(note).toHaveTextContent('30 of 400 rows of the joined data find no partner here and are kept with blank values.')
    expect(screen.getByTestId('join-freshness')).toHaveTextContent('“Customers” was last loaded 3 days ago')
  })

  it('says one row each when nothing multiplies, and that a left join leaves orphans out', async () => {
    vi.mocked(prepApi.joinCheck).mockResolvedValue({ ...base, rows_after: 1000, multiplier: 1,
      right_rows: 10, right_unmatched_rows: 2 })
    render(<JoinMatchNote datasetId={1} index={0}
      steps={[{ kind: 'join', dataset_id: 2, how: 'left', left_on: 'cust', right_on: 'id' }]}
      joined={{ name: 'Regions', last_refreshed_at: null }} />)
    expect(await screen.findByTestId('join-fanout', {}, { timeout: 2000 })).toHaveTextContent('(one row each)')
    expect(screen.getByTestId('join-match')).toHaveTextContent('and are left out.')
    expect(screen.getByTestId('join-freshness')).toHaveTextContent('has no load time recorded')
  })

  it('does not check a composite key the author is still picking', () => {
    vi.mocked(prepApi.joinCheck).mockClear()
    const { container } = render(<JoinMatchNote datasetId={1} index={0}
      steps={[{ kind: 'join', dataset_id: 2, left_ons: [''], right_ons: [''] }]} />)
    expect(container.textContent).toBe('')
    expect(prepApi.joinCheck).not.toHaveBeenCalled()
  })
})
