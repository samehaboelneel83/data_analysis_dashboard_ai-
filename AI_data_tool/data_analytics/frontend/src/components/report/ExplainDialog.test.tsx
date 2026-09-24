/**
 * The generated sentence beside the factors.
 *
 * SAS's automated explanation speaks; ours returned a bar list and a plot and
 * left the reader to phrase the finding. The server now offers a sentence
 * through the same guarded path the pin cards use — but it is an ADDITION to
 * the answer, so the dialog has to work exactly as before without one. In an
 * air-gapped install there is no model at all, which makes the absent case the
 * normal one rather than the edge.
 *
 * And when there IS a sentence it must be marked as generated: a reader
 * deciding something on the strength of a line has a right to know a model
 * wrote it rather than a statistician.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import ExplainDialog from './ExplainDialog'
import { explainApi } from '../../services/api'

vi.mock('../../services/api', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  explainApi: { explain: vi.fn(), goalSeek: vi.fn() },
}))

const result = (over: object = {}) => ({
  response: 'revenue',
  factors: [{ column: 'spend', kind: 'numeric', score: 0.93, relative: 1 }],
  relationship: null,
  note: null,
  narrative: null,
  narrative_source: null,
  ...over,
})

beforeEach(() => vi.clearAllMocks())

const open = () => render(
  <ExplainDialog datasetId={1} column="revenue" onClose={vi.fn()} />)

describe('ExplainDialog narrative', () => {
  it('shows the sentence when the server offers one', async () => {
    vi.mocked(explainApi.explain).mockResolvedValue(result({
      narrative: 'Spend is the strongest driver of revenue.',
      narrative_source: 'model',
    }) as never)
    open()
    expect(await screen.findByText(/strongest driver of revenue/)).toBeInTheDocument()
  })

  it('says the sentence was generated', async () => {
    vi.mocked(explainApi.explain).mockResolvedValue(result({
      narrative: 'Spend is the strongest driver of revenue.',
      narrative_source: 'model',
    }) as never)
    open()
    expect(await screen.findByText(/generated/i)).toBeInTheDocument()
  })

  it('shows the factors and nothing else when there is no sentence', async () => {
    // The air-gapped case. A blank line where prose would go reads as a
    // sentence that failed to load.
    vi.mocked(explainApi.explain).mockResolvedValue(result() as never)
    open()
    expect(await screen.findByText(/relative importance/i)).toBeInTheDocument()
    expect(screen.queryByText(/generated/i)).not.toBeInTheDocument()
  })
})
