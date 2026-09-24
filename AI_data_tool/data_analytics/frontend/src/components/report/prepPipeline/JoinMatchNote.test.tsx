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
