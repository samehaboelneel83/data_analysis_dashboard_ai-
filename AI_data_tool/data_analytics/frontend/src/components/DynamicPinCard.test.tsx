import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import DynamicPinCard from './DynamicPinCard'
import { insightsApi, narrateApi } from '../services/api'
import type { PinnedTileInfo } from '../services/api'

/**
 * The Dynamic Pin card: Insight Engine → Evidence Boundary → LLM Narrator.
 *
 * The properties worth defending: the badge renders from structured `figures`
 * only (never parsed out of prose); the sentence is TEMPLATE-FIRST so the
 * card never waits on the model; and a finding no longer detected says so
 * rather than vanishing or showing stale numbers.
 */

vi.mock('../services/api', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  insightsApi: { run: vi.fn(), runShared: vi.fn() },
  narrateApi: { one: vi.fn() },
}))

const TILE: PinnedTileInfo = {
  id: 9, pin_type: 'insight', position: 1, size: 'm', dataset_id: 32,
  dataset_name: 'Sales', finding_key: 'trend|date|revenue', created_at: 'x',
}

const FINDING = {
  kind: 'trend', score: 0.6,
  title: 'revenue in 2026-08 ran 26% above its monthly average',
  detail: '12.4M against an average of 9.8M.',
  columns: ['revenue', 'date'],
  figures: { delta_pct: 26.5, value: 12400000, direction: 'up' },
  novelty: 'changed' as const,
}

const draw = () => render(
  <MemoryRouter><DynamicPinCard tile={TILE} /></MemoryRouter>)

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(insightsApi.runShared).mockResolvedValue(
    { findings: [FINDING], narrative: '' } as never)
  vi.mocked(narrateApi.one).mockResolvedValue(null)
})

describe('the badge is data, not parsed prose', () => {
  it('renders the delta from figures', async () => {
    draw()
    expect(await screen.findByTestId('pin-badge')).toHaveTextContent('+26.5%')
  })

  it('renders no badge at all when figures are absent', async () => {
    // Absent, never NaN: an older stored scan may predate the figures field.
    vi.mocked(insightsApi.runShared).mockResolvedValue(
      { findings: [{ ...FINDING, figures: undefined }], narrative: '' } as never)
    draw()
    await screen.findByText(/26% above/)          // template sentence still shows
    expect(screen.queryByTestId('pin-badge')).toBeNull()
  })
})

describe('template-first narration', () => {
  it('shows the deterministic sentence without waiting for the model', async () => {
    let resolve!: (v: string | null) => void
    vi.mocked(narrateApi.one).mockReturnValue(
      new Promise(r => { resolve = r }) as never)
    draw()
    // The template is on screen while the narrator is still thinking.
    expect(await screen.findByText(/26% above its monthly average/)).toBeInTheDocument()
    resolve('Revenue rose 26.5% to 12.4M.')
    await waitFor(() =>
      expect(screen.getByText('Revenue rose 26.5% to 12.4M.')).toBeInTheDocument())
  })

  it('keeps the template when the narrator declines', async () => {
    // Null = guard rejected or model down; the deterministic sentence stands.
    draw()
    expect(await screen.findByText(/26% above its monthly average/)).toBeInTheDocument()
    await waitFor(() => expect(narrateApi.one).toHaveBeenCalled())
    expect(screen.getByText(/26% above its monthly average/)).toBeInTheDocument()
  })
})

describe('liveness and honesty', () => {
  it('evaluates through the SHARED insights request', async () => {
    // Five cards over one dataset must cost one scan, not five.
    draw()
    await screen.findByTestId('pin-badge')
    expect(insightsApi.runShared).toHaveBeenCalledWith(32)
  })

  it('says when the finding is no longer detected', async () => {
    vi.mocked(insightsApi.runShared).mockResolvedValue(
      { findings: [], narrative: '' } as never)
    draw()
    expect(await screen.findByTestId('pin-dormant'))
      .toHaveTextContent(/not currently detected/i)
    // And no narrator call for a finding that does not exist.
    expect(narrateApi.one).not.toHaveBeenCalled()
  })

  it('shows the novelty accent from the live evaluation', async () => {
    draw()
    expect(await screen.findByText('CHANGED')).toBeInTheDocument()
  })

  it('reports an evaluation failure as itself', async () => {
    vi.mocked(insightsApi.runShared).mockRejectedValue(new Error('down'))
    draw()
    expect(await screen.findByRole('alert')).toHaveTextContent(/could not evaluate/i)
  })
})
