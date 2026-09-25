import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import SourceReview from './SourceReview'
import { metadataApi, type ReviewQueue, type SyncRun } from '../services/api'
import live from '../test/fixtures/live-catalog.json'

/**
 * The review page against a REAL catalog.
 *
 * Every other test in this suite uses data I wrote, which means they can only
 * confirm the component does what I expected — including where what I expected
 * was wrong. This fixture is a slice of an actual `GET /review` response from a
 * live PostgreSQL source: real table names, real Arabic values, real generated
 * descriptions, and both declared and inferred relationships side by side.
 *
 * It exists because the shape a real database produces has repeatedly differed
 * from the shape a small hand-written fixture suggests — views with no row
 * count, tables that join to nothing, descriptions carrying non-Latin text,
 * and 1,354 columns where three were assumed.
 *
 * Trimmed from 82 objects / 235 relationships / 1,354 columns to a
 * representative subset, because the value here is FIDELITY, not volume. Volume
 * is covered by generated fixtures in SourceReview.test.tsx, which can assert
 * exact counts without drifting every time someone re-syncs.
 */

vi.mock('react-hot-toast', () => ({
  default: { success: vi.fn(), error: vi.fn() },
}))

const QUEUE = live as unknown as ReviewQueue

const RUN: SyncRun = {
  id: 14, status: 'ok', trigger: 'manual', finished_at: '2026-08-24T17:20:00Z',
  stages: [
    { name: 'discover', status: 'ok', ms: 4047,
      detail: { objects: 82, columns: 1354, declared_foreign_keys: 28, views: 48 } },
    { name: 'sample', status: 'ok', ms: 514510,
      detail: { objects_sampled: 63, objects_empty: 6, objects_timed_out: 8 } },
    { name: 'profile', status: 'ok', ms: 3944, detail: { columns_profiled: 1119 } },
    { name: 'infer_keys', status: 'ok', ms: 243257,
      detail: { proposed: 207, high_confidence: 96 } },
    { name: 'describe', status: 'ok', ms: 205414,
      detail: { llm_used: true, source_overview: true, columns_described: 1150 } },
    { name: 'drift', status: 'ok', ms: 17, detail: { changed: false } },
  ],
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/connections/2/review']}>
      <Routes>
        <Route path="/connections/:id/review" element={<SourceReview />} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.restoreAllMocks()
  vi.spyOn(metadataApi, 'review').mockResolvedValue(structuredClone(QUEUE))
  vi.spyOn(metadataApi, 'latestSync').mockResolvedValue(structuredClone(RUN))
  vi.spyOn(metadataApi, 'confirm').mockResolvedValue(
    { confirmed: 0, rejected: 0, columns_updated: 0 })
})

describe('SourceReview against a real catalog', () => {
  it('renders without throwing on real data', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByText('Review data source')).toBeInTheDocument())
  })

  it('shows the database description the model actually wrote', async () => {
    renderPage()
    await waitFor(() =>
      expect(screen.getByText(new RegExp(QUEUE.source.description!.slice(0, 40)
        .replace(/[.*+?^${}()|[\]\\]/g, '\\$&')))).toBeInTheDocument())
  })

  it('distinguishes declared relationships from inferred ones', async () => {
    // The whole review interaction rests on this: a declared key is enforced by
    // the database and is not up for confirmation; an inferred one is a
    // proposal. The fixture deliberately carries both.
    const declared = QUEUE.relationships.filter(r => r.source === 'declared')
    const inferred = QUEUE.relationships.filter(r => r.source === 'inferred')
    expect(declared.length).toBeGreaterThan(0)
    expect(inferred.length).toBeGreaterThan(0)

    renderPage()
    await waitFor(() => screen.getByText(/awaiting review/))
    expect(screen.getByText(
      new RegExp(`${inferred.length} awaiting review · ${declared.length} settled`)),
    ).toBeInTheDocument()
  })

  it('never asks the user to confirm a key the database already enforces', async () => {
    renderPage()
    await waitFor(() => screen.getByText(/awaiting review/))
    const controls = [/Let the model describe this source/, /Include views/,
                      /Show every table at once/]
      .map(re => screen.queryByLabelText(re)).filter(Boolean) as HTMLElement[]
    // Per-object "canonical" toggles, one per described object -- not a
    // proposal, so excluded the same way the named controls above are.
    const canonicalToggles = screen.getAllByRole('checkbox', { name: /canonical/i })
    const proposals = screen.getAllByRole('checkbox')
      .filter(box => !controls.includes(box) && !canonicalToggles.includes(box))
    const inferred = QUEUE.relationships.filter(r => r.source === 'inferred')
    expect(proposals.length).toBe(inferred.length)
  })

  it('counts views separately from tables', async () => {
    const views = QUEUE.datasets.filter(d => d.kind === 'view').length
    expect(views).toBeGreaterThan(0)
    renderPage()
    await waitFor(() => expect(screen.getByText(String(views))).toBeInTheDocument())
  })

  it('states how much of the schema is on screen', async () => {
    const connected = new Set<number>()
    QUEUE.relationships.forEach(r => {
      connected.add(r.from_dataset_id); connected.add(r.to_dataset_id)
    })
    const isolated = QUEUE.datasets.filter(d => !connected.has(d.id)).length
    expect(isolated).toBeGreaterThan(0)

    renderPage()
    // The graph centres on one table, so the footer states how much of the
    // schema is on screen rather than how much was dropped.
    await waitFor(() =>
      expect(screen.getByText(/connected objects shown/)).toBeInTheDocument())
  })

  it('renders non-Latin descriptions without mangling them', async () => {
    // Arabic values and descriptions come back from this source. A component
    // that assumed Latin text would be visibly wrong here and nowhere else.
    renderPage()
    await waitFor(() => screen.getByText(/Columns \(/))
    const withText = QUEUE.columns.find(c => c.description)
    if (withText) {
      fireEvent.click(screen.getByText(/Columns \(/))
      await waitFor(() =>
        expect(screen.getAllByDisplayValue(withText.description!).length)
          .toBeGreaterThan(0))
    }
  })

  it('reports the real per-stage sync result', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByText('Discover tables')).toBeInTheDocument())
    expect(screen.getByText(/1119 columns/)).toBeInTheDocument()
    expect(screen.getByText(/207 proposed \(96 high confidence\)/)).toBeInTheDocument()
  })

  it('searches across the real table names', async () => {
    const target = QUEUE.datasets[0].name
    renderPage()
    await waitFor(() => screen.getByPlaceholderText(/Search tables, columns/))
    fireEvent.change(screen.getByPlaceholderText(/Search tables, columns/),
                     { target: { value: target } })
    // Whatever it narrows to, the page must survive the filter.
    await waitFor(() => expect(screen.getByText('Review data source')).toBeInTheDocument())
  })
})

describe('objects the sync gave up on', () => {
  /**
   * Sampling gives each object a fixed time budget, and on this source the same
   * handful of `v_student_solution_aligned_correction_*` views spend that whole
   * budget on every run without ever returning rows. So an object that hits the
   * deadline is remembered and skipped from then on.
   *
   * That trade is only acceptable while the skip stays visible and undoable.
   * These tests hold that line: a table that quietly stops being described,
   * with nothing on the page to explain why, is indistinguishable from a bug —
   * and the person who can judge whether the view has since been fixed is the
   * one reading this page.
   */
  function withSkipped() {
    const q = structuredClone(QUEUE)
    q.datasets[0].sample_timed_out_at = '2026-08-24T17:20:00Z'
    vi.spyOn(metadataApi, 'review').mockResolvedValue(q)
    return q
  }

  it('says which objects are being skipped, and why', async () => {
    const q = withSkipped()
    renderPage()
    await waitFor(() =>
      expect(screen.getByText(/too long to sample/i)).toBeInTheDocument())
    expect(screen.getAllByText(q.datasets[0].name).length).toBeGreaterThan(0)
  })

  it('reassures that skipping costs freshness, not what is already known', async () => {
    withSkipped()
    renderPage()
    await waitFor(() =>
      expect(screen.getByText(/only the sample\s+stops being refreshed|only the sample/i))
        .toBeInTheDocument())
  })

  it('offers a way back, and clearing the flag is all it does', async () => {
    const q = withSkipped()
    const confirm = vi.spyOn(metadataApi, 'confirm').mockResolvedValue(
      { confirmed: 0, rejected: 0, columns_updated: 1 })
    const sync = vi.spyOn(metadataApi, 'sync')

    renderPage()
    await waitFor(() =>
      expect(screen.getByText(/try again on the next sync/i)).toBeInTheDocument())
    fireEvent.click(screen.getByText(/try again on the next sync/i))

    await waitFor(() => expect(confirm).toHaveBeenCalledWith(2, {
      object_updates: [{ id: q.datasets[0].id, retry_sample: true }],
    }))
    // Deliberately not a sync trigger: one object is not worth a run, and
    // someone clearing these usually clears several before starting one.
    expect(sync).not.toHaveBeenCalled()
  })

  it('shows nothing at all when no object was skipped', async () => {
    // The common case. A warning panel that is always on screen stops being
    // read, which would cost the panel its only job.
    renderPage()
    await waitFor(() => expect(screen.getByText('Review data source')).toBeInTheDocument())
    expect(screen.queryByText(/too long to sample/i)).not.toBeInTheDocument()
  })
})
