import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import SourceReview from './SourceReview'
import { dataSourcesApi, metadataApi, type ReviewEntity, type ReviewQueue, type SyncRun } from '../services/api'

/**
 * Stage 7 — human confirmation.
 *
 * The behaviour under test is the one that makes ARCHITECTURE.md's ten-minute
 * target reachable: high-confidence proposals arrive PRE-SELECTED, so the common
 * case is one button rather than N decisions. If that pre-selection ever breaks,
 * the review step silently becomes a per-edge slog and nobody would notice from
 * a screenshot.
 */

vi.mock('react-hot-toast', () => ({
  default: { success: vi.fn(), error: vi.fn() },
}))

const SOURCE = {
  id: 7, name: 'maps', type: 'postgresql',
  description: 'Tracks map regions through a review workflow.',
  description_source: 'inferred',
  allow_llm_sampling: true,
  sync_status: 'ok', last_synced_at: '2026-08-24T10:00:00Z',
}

const QUEUE: ReviewQueue = {
  source: SOURCE,
  datasets: [
    { id: 1, name: 'customers', is_deprecated: false,
      description: 'Customer records.', description_source: 'inferred' },
    { id: 2, name: 'orders', is_deprecated: false,
      description: null, description_source: null },
    { id: 3, name: 'orders_old', is_deprecated: true,
      description: null, description_source: null },
  ],
  relationships: [
    {
      id: 10, from_dataset_id: 2, from_dataset: 'orders', from_column: 'customer_id',
      to_dataset_id: 1, to_dataset: 'customers', to_column: 'id',
      confidence: 0.98, source: 'inferred', cardinality: 'many_to_one',
      evidence: { overlap: 0.98, name_score: 1.0, child_distinct: 90, parent_distinct: 100,
                  high_confidence: true },
      needs_review: true,
    },
    {
      id: 11, from_dataset_id: 2, from_dataset: 'orders', from_column: 'ref_code',
      to_dataset_id: 1, to_dataset: 'customers', to_column: 'id',
      confidence: 0.78, source: 'inferred', cardinality: 'many_to_one',
      evidence: { overlap: 0.78, name_score: 0.4, child_distinct: 40, parent_distinct: 100,
                  high_confidence: false },
      needs_review: true,
    },
    {
      id: 12, from_dataset_id: 1, from_dataset: 'customers', from_column: 'region_id',
      to_dataset_id: 2, to_dataset: 'orders', to_column: 'id',
      confidence: 1.0, source: 'confirmed', cardinality: 'many_to_one',
      evidence: null, needs_review: false,
    },
  ],
  columns: [
    {
      id: 100, dataset_id: 2, dataset: 'orders', name: 'st_cd', dtype: 'integer',
      semantic_type: null, description: 'A status code.', description_source: 'inferred',
      needs_review: true,
      enum_labels: { '1': 'new', '2': 'paid' }, enum_labels_source: 'inferred',
    },
  ],
}

const RUN: SyncRun = {
  id: 5, status: 'ok', trigger: 'manual', finished_at: '2026-08-24T10:00:00Z',
  stages: [
    { name: 'discover', status: 'ok', ms: 12, detail: { datasets: 3 } },
    { name: 'profile', status: 'ok', ms: 40, detail: { columns_profiled: 8 } },
    { name: 'infer_keys', status: 'ok', ms: 80, detail: { proposed: 2, high_confidence: 1 } },
    { name: 'infer_semantic', status: 'ok', ms: 20, detail: { llm_used: false } },
    { name: 'drift', status: 'ok', ms: 5, detail: { changed: false } },
  ],
}


/** Checkboxes that are page controls rather than proposal rows: the model
 *  toggle in the overview, and the graph's view/expand switches. */
function proposalCheckboxes(screenRef: typeof screen): HTMLElement[] {
  const controls = [
    /Let the model describe this source/,
    /Include views/,
    /Show every table at once/,
  ].map(re => screenRef.queryByLabelText(re)).filter(Boolean) as HTMLElement[]
  // Per-object "canonical" toggles, one per described object -- not a
  // proposal, so excluded the same way the named controls above are.
  const canonicalToggles = screenRef.getAllByRole('checkbox', { name: /canonical/i })
  return screenRef.getAllByRole('checkbox')
    .filter(box => !controls.includes(box) && !canonicalToggles.includes(box))
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/connections/7/review']}>
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
  vi.spyOn(metadataApi, 'entities').mockResolvedValue([])
  vi.spyOn(metadataApi, 'confirmEntities').mockResolvedValue({ updated: 0 })
})

describe('SourceReview', () => {
  it('pre-selects only the high-confidence proposals', async () => {
    renderPage()
    // Two proposals, one of them high-confidence -> exactly one pre-selected.
    await waitFor(() => expect(screen.getByText(/Confirm 1 selected/)).toBeInTheDocument())
  })

  it('counts pending separately from settled', async () => {
    renderPage()
    await waitFor(() =>
      expect(screen.getByText(/2 awaiting review · 1 settled/)).toBeInTheDocument())
  })

  it('shows the evidence for each proposal rather than hiding it behind a click', async () => {
    // A user who must open something to judge it will approve without looking,
    // which turns review into a rubber stamp.
    renderPage()
    // 98% appears twice on purpose — once on the graph edge label, once on the
    // row beneath it — so this asserts presence rather than uniqueness.
    await waitFor(() => expect(screen.getAllByText(/98%/).length).toBeGreaterThan(0))
    // One evidence block per pending proposal, both rendered inline.
    expect(screen.getAllByText(/of the child column/i).length).toBe(2)
  })

  it('confirms exactly the selected relationships', async () => {
    renderPage()
    await waitFor(() => screen.getByText(/Confirm 1 selected/))
    fireEvent.click(screen.getByText(/Confirm 1 selected/))

    await waitFor(() => expect(metadataApi.confirm).toHaveBeenCalledWith(
      7, { relationship_ids: [10] }))
  })

  it('lets a proposal be toggled off before confirming', async () => {
    renderPage()
    await waitFor(() => screen.getByText(/Confirm 1 selected/))

    // The overview panel's "let the model describe this source" switch is also
    // a checkbox and sits above these, so select the proposal rows explicitly
    // rather than by position.
    const proposals = proposalCheckboxes(screen)
    expect(proposals.length).toBe(2)

    fireEvent.click(proposals[0])
    await waitFor(() => expect(screen.getByText(/Confirm 0 selected/)).toBeInTheDocument())
  })

  it('rejects a single proposal without touching the others', async () => {
    renderPage()
    await waitFor(() => screen.getAllByText('Reject'))
    fireEvent.click(screen.getAllByText('Reject')[0])
    await waitFor(() => expect(metadataApi.confirm).toHaveBeenCalledWith(
      7, { rejected_relationship_ids: [10] }))
  })

  it('reports per-stage sync results rather than one overall verdict', async () => {
    // Stages fail independently by design, so a single status would misrepresent
    // a partial run as a failure.
    renderPage()
    await waitFor(() => expect(screen.getByText('Discover tables')).toBeInTheDocument())
    expect(screen.getByText('Infer relationships')).toBeInTheDocument()
    expect(screen.getByText(/2 proposed \(1 high confidence\)/)).toBeInTheDocument()
  })

  it('surfaces a 409 as "already running" rather than a generic failure', async () => {
    const toast = (await import('react-hot-toast')).default
    vi.spyOn(metadataApi, 'sync').mockRejectedValue({ response: { status: 409 } })
    renderPage()
    await waitFor(() => screen.getByText('Run sync'))
    fireEvent.click(screen.getByText('Run sync'))
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith(
      'A sync is already running for this source'))
  })

  it('polls the run and reports progress while it is still going', async () => {
    // The whole reason the sync moved to the background: stages have to become
    // visible DURING the run, not all at once when it finishes.
    vi.spyOn(metadataApi, 'sync').mockResolvedValue(
      { sync_run_id: 9, status: 'running', stages: [] })

    const partial: SyncRun = {
      id: 9, status: 'running', stages: [
        { name: 'discover', status: 'ok', ms: 5, detail: { datasets: 3 } },
        { name: 'sample', status: 'ok', ms: 40, detail: { datasets_sampled: 3 } },
      ],
    }
    const done: SyncRun = { ...RUN, id: 9 }

    const status = vi.spyOn(metadataApi, 'syncStatus')
      .mockResolvedValueOnce(partial)
      .mockResolvedValue(done)

    renderPage()
    await waitFor(() => screen.getByText('Run sync'))
    fireEvent.click(screen.getByText('Run sync'))

    // Mid-run: the button counts the stages seen so far.
    await waitFor(() => expect(screen.getByText(/Syncing… 2\/6/)).toBeInTheDocument(),
                  { timeout: 4000 })
    expect(status).toHaveBeenCalledWith(7, 9)
  })

  it('stops polling and says so once the run finishes', async () => {
    const toast = (await import('react-hot-toast')).default
    vi.spyOn(metadataApi, 'sync').mockResolvedValue(
      { sync_run_id: 9, status: 'running', stages: [] })
    vi.spyOn(metadataApi, 'syncStatus').mockResolvedValue({ ...RUN, id: 9 })

    renderPage()
    await waitFor(() => screen.getByText('Run sync'))
    fireEvent.click(screen.getByText('Run sync'))

    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('Sync finished'),
                  { timeout: 4000 })
    // Button returns to its resting state rather than spinning forever.
    await waitFor(() => expect(screen.getByText('Run sync')).toBeEnabled())
  })

  it('reports a partial run as a failure with the stage count', async () => {
    const toast = (await import('react-hot-toast')).default
    vi.spyOn(metadataApi, 'sync').mockResolvedValue(
      { sync_run_id: 9, status: 'running', stages: [] })
    vi.spyOn(metadataApi, 'syncStatus').mockResolvedValue({
      id: 9, status: 'partial', stages: [
        { name: 'discover', status: 'ok', ms: 3 },
        { name: 'sample', status: 'failed', ms: 8, error: 'permission denied' },
      ],
    })

    renderPage()
    await waitFor(() => screen.getByText('Run sync'))
    fireEvent.click(screen.getByText('Run sync'))

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith(
      'Sync finished with 1 failed stage(s)'), { timeout: 4000 })
  })

  it('switches to the columns tab and saves an edited description', async () => {
    renderPage()
    await waitFor(() => screen.getByText(/Columns \(1\)/))
    fireEvent.click(screen.getByText(/Columns \(1\)/))

    const input = await screen.findByDisplayValue('A status code.')
    fireEvent.change(input, { target: { value: 'Order lifecycle state' } })
    fireEvent.click(screen.getByText('Save'))

    await waitFor(() => expect(metadataApi.confirm).toHaveBeenCalledWith(
      7, { column_updates: [{ id: 100, description: 'Order lifecycle state' }] }))
  })

  it('marks a generated description as not yet confirmed', async () => {
    renderPage()
    await waitFor(() => screen.getByText(/Columns \(1\)/))
    fireEvent.click(screen.getByText(/Columns \(1\)/))
    expect(await screen.findByText(/Generated — not yet confirmed/)).toBeInTheDocument()
  })

  // ── T2: enum value labels, editable per column ──────────────────────────

  it('renders enum labels for a column that has them', async () => {
    renderPage()
    await waitFor(() => screen.getByText(/Columns \(1\)/))
    fireEvent.click(screen.getByText(/Columns \(1\)/))

    expect(await screen.findByText('1 = new, 2 = paid')).toBeInTheDocument()
  })

  it('shows no label UI for a column without enum labels', async () => {
    vi.spyOn(metadataApi, 'review').mockResolvedValue({
      ...structuredClone(QUEUE),
      columns: [{ ...structuredClone(QUEUE.columns[0]), enum_labels: null, enum_labels_source: null }],
    })
    renderPage()
    await waitFor(() => screen.getByText(/Columns \(1\)/))
    fireEvent.click(screen.getByText(/Columns \(1\)/))

    await screen.findByDisplayValue('A status code.')
    expect(screen.queryByText(/Edit labels/)).not.toBeInTheDocument()
    expect(screen.queryByText(/1 = new/)).not.toBeInTheDocument()
  })

  it('edits a label and saves it through column_updates', async () => {
    renderPage()
    await waitFor(() => screen.getByText(/Columns \(1\)/))
    fireEvent.click(screen.getByText(/Columns \(1\)/))

    fireEvent.click(await screen.findByText('Edit labels'))
    const labelInput = await screen.findByDisplayValue('new')
    fireEvent.change(labelInput, { target: { value: 'Just placed' } })

    // The enum-labels Save button sits inside the same cell as the label
    // inputs, ahead of the (disabled, unrelated) description Save button in
    // the next cell.
    fireEvent.click(screen.getAllByText('Save')[0])

    await waitFor(() => expect(metadataApi.confirm).toHaveBeenCalledWith(
      7, { column_updates: [{ id: 100, enum_labels: { '1': 'Just placed', '2': 'paid' } }] }))
  })

  it('shows a persistent error banner when the initial load fails, not a toast', async () => {
    // The whole page has nothing to show without the review queue -- a toast
    // that fades leaves the user staring at a blank page with no explanation
    // and no way to retry.
    const toast = (await import('react-hot-toast')).default
    vi.spyOn(metadataApi, 'review').mockRejectedValue(new Error('down'))
    renderPage()

    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(toast.error).not.toHaveBeenCalledWith('Could not load the review queue')
  })

  it('retries the initial load from the error banner and recovers', async () => {
    vi.spyOn(metadataApi, 'review')
      .mockRejectedValueOnce(new Error('down'))
      .mockResolvedValueOnce(structuredClone(QUEUE))
    renderPage()

    const alert = await screen.findByRole('alert')
    fireEvent.click(within(alert).getByText('Try again'))

    await waitFor(() => expect(screen.getByText(/Confirm 1 selected/)).toBeInTheDocument())
  })

  it('renders an empty queue without error', async () => {
    vi.spyOn(metadataApi, 'review').mockResolvedValue(
      { source: SOURCE, datasets: [], relationships: [], columns: [] })
    renderPage()
    await waitFor(() =>
      expect(screen.getByText(/Run a sync to read this connection/)).toBeInTheDocument())
  })

  it('shows the database description after a sync', async () => {
    // The question a person actually has after connecting a source: what is in
    // here? Column descriptions do not answer it.
    renderPage()
    await waitFor(() => expect(screen.getByText(
      /Tracks map regions through a review workflow/)).toBeInTheDocument())
  })

  it('says a generated description is not yet confirmed', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByText(
      /Written by the model.*Not yet confirmed/s)).toBeInTheDocument())
  })

  it('explains the blank state instead of just showing nothing', async () => {
    // A blank panel with no explanation is how a working feature gets written
    // off as broken.
    vi.spyOn(metadataApi, 'review').mockResolvedValue({
      ...structuredClone(QUEUE),
      source: { ...SOURCE, description: null, allow_llm_sampling: false },
    })
    renderPage()
    await waitFor(() => expect(screen.getByText(
      /switched off for this source/)).toBeInTheDocument())
  })

  it('turns the model on for this source', async () => {
    const settings = vi.spyOn(metadataApi, 'settings').mockResolvedValue(
      { allow_llm_sampling: true, description: null, description_source: null })
    vi.spyOn(metadataApi, 'review').mockResolvedValue({
      ...structuredClone(QUEUE),
      source: { ...SOURCE, description: null, allow_llm_sampling: false },
    })

    renderPage()
    const box = await screen.findByLabelText(/Let the model describe this source/)
    fireEvent.click(box)

    await waitFor(() => expect(settings).toHaveBeenCalledWith(
      7, { allow_llm_sampling: true }))
  })

  it('lets the description be edited by hand', async () => {
    const settings = vi.spyOn(metadataApi, 'settings').mockResolvedValue(
      { allow_llm_sampling: true, description: 'Mine.', description_source: 'confirmed' })

    renderPage()
    fireEvent.click(await screen.findByText('Edit'))
    // The page-wide search input is also a textbox, so pick the textarea, which
    // is the description editor.
    const editor = screen.getAllByRole('textbox')
      .find(el => el.tagName === 'TEXTAREA')!
    fireEvent.change(editor, { target: { value: 'Mine, and correct.' } })
    fireEvent.click(screen.getByText('Save'))

    await waitFor(() => expect(settings).toHaveBeenCalledWith(
      7, { description: 'Mine, and correct.' }))
  })

  it('lists what each table holds, tables and views apart', async () => {
    renderPage()
    await waitFor(() => expect(
      screen.getByText(/Tables — what each one holds \(1\)/)).toBeInTheDocument())
  })

  it('marks an object canonical through the object_updates path', async () => {
    // T1: the source-of-truth flag agent/nodes/generate.py's prompt checks.
    renderPage()
    await waitFor(() => screen.getByText(/Tables — what each one holds \(1\)/))
    fireEvent.click(screen.getByText(/Tables — what each one holds \(1\)/))

    const toggle = await screen.findByRole('checkbox', { name: /canonical/i })
    expect(toggle).not.toBeChecked()
    fireEvent.click(toggle)

    await waitFor(() => expect(metadataApi.confirm).toHaveBeenCalledWith(
      7, { object_updates: [{ id: 1, is_canonical: true }] }))
  })

  // ── behaviour that only appears at the size a real database actually is ──
  //
  // This page was built and tested against three tables. The user's source has
  // 82 objects, 235 relationships and 1,354 columns. None of the problems below
  // are visible from a small fixture, and all of them make the page unusable.

  const BIG: ReviewQueue = {
    source: SOURCE,
    datasets: [
      ...Array.from({ length: 60 }, (_, i) => ({
        id: 1000 + i, name: `lonely_table_${i}`, kind: 'table',
        is_deprecated: false, description: null, description_source: null,
      })),
      { id: 1, name: 'customers', kind: 'table', is_deprecated: false,
        description: 'Customer records.', description_source: 'inferred' },
      { id: 2, name: 'orders', kind: 'table', is_deprecated: false,
        description: null, description_source: null },
      { id: 3, name: 'order_report', kind: 'view', is_deprecated: false,
        description: 'A reporting view.', description_source: 'inferred' },
    ],
    relationships: [QUEUE.relationships[0]],
    columns: [
      ...Array.from({ length: 300 }, (_, i) => ({
        id: 5000 + i, dataset_id: 1000, dataset: 'lonely_table_0',
        name: `col_${i}`, dtype: 'text', semantic_type: null,
        description: null, description_source: null, needs_review: false,
      })),
      { id: 9001, dataset_id: 1, dataset: 'customers', name: 'email_address',
        dtype: 'text', semantic_type: 'email', description: 'Contact address.',
        description_source: 'inferred', needs_review: true },
    ],
  }

  it('centres on one table rather than drawing the whole schema', async () => {
    // 63 tables, one relationship. Drawing all of them produces a hairball with
    // no answer in it; centring on the busiest table produces a picture.
    vi.spyOn(metadataApi, 'review').mockResolvedValue(structuredClone(BIG))
    renderPage()
    await waitFor(() =>
      expect(screen.getByText(/and what\s+it joins to/)).toBeInTheDocument())
  })

  it('states how much of the schema is on screen', async () => {
    // A graph that quietly shows a subset is worse than a crowded one, because
    // the reader cannot tell it happened.
    vi.spyOn(metadataApi, 'review').mockResolvedValue(structuredClone(BIG))
    renderPage()
    await waitFor(() =>
      expect(screen.getByText(/of 2 connected objects shown/)).toBeInTheDocument())
  })

  it('hides views by default and offers them behind a switch', async () => {
    // Half a real source's objects were views, and a view's joins are inherited
    // from the tables underneath rather than being facts about the schema.
    vi.spyOn(metadataApi, 'review').mockResolvedValue(structuredClone(BIG))
    renderPage()
    const toggle = await screen.findByLabelText(/Include views/)
    expect(toggle).not.toBeChecked()
  })

  it('can expand to the whole schema on request', async () => {
    vi.spyOn(metadataApi, 'review').mockResolvedValue(structuredClone(BIG))
    renderPage()
    const showAll = await screen.findByLabelText(/Show every table at once/)
    fireEvent.click(showAll)
    await waitFor(() =>
      expect(screen.getByText(/All 2 connected objects/)).toBeInTheDocument())
  })

  it('reports the size of the whole catalog, not just what needs review', async () => {
    vi.spyOn(metadataApi, 'review').mockResolvedValue(structuredClone(BIG))
    renderPage()
    await waitFor(() =>
      expect(screen.getByText(/63 tables · 301 columns/)).toBeInTheDocument())
  })

  it('separates tables from views in the overview', async () => {
    vi.spyOn(metadataApi, 'review').mockResolvedValue(structuredClone(BIG))
    renderPage()
    await waitFor(() => expect(screen.getByText('62')).toBeInTheDocument())   // tables
    expect(screen.getByText('1')).toBeInTheDocument()                          // views
  })

  it('filters columns by name across the whole catalog', async () => {
    // 1,354 rows with no way to find one is not a review surface.
    vi.spyOn(metadataApi, 'review').mockResolvedValue(structuredClone(BIG))
    renderPage()
    await waitFor(() => screen.getByPlaceholderText(/Search tables, columns/))

    fireEvent.change(screen.getByPlaceholderText(/Search tables, columns/),
                     { target: { value: 'email_address' } })

    await waitFor(() => expect(screen.getByText(/Columns \(1\)/)).toBeInTheDocument())
  })

  it('groups columns under their table instead of one flat list', async () => {
    vi.spyOn(metadataApi, 'review').mockResolvedValue(structuredClone(BIG))
    renderPage()
    await waitFor(() => screen.getByText(/Columns \(301\)/))
    fireEvent.click(screen.getByText(/Columns \(301\)/))

    await waitFor(() =>
      expect(screen.getByText(/301 columns across 2 tables/)).toBeInTheDocument())
    expect(screen.getByText(/\(300 columns\)/)).toBeInTheDocument()
  })

  it('narrows the graph to a searched table', async () => {
    vi.spyOn(metadataApi, 'review').mockResolvedValue(structuredClone(BIG))
    renderPage()
    await waitFor(() => screen.getByPlaceholderText(/Search tables, columns/))

    fireEvent.change(screen.getByPlaceholderText(/Search tables, columns/),
                     { target: { value: 'lonely_table_7' } })

    await waitFor(() => expect(
      screen.getByText(/No relationships involve a table/)).toBeInTheDocument())
  })

  // ── Task R3: entities — named business objects, and their grain ─────────

  describe('entities', () => {
    const ENTITIES: ReviewEntity[] = [
      { id: 1, name: 'customer', business_name: 'Customer',
        grain: 'One row per customer.', description: 'A person who placed orders.',
        primary_object: 'customers', source: 'inferred' },
    ]

    it('shows a count in the tab and lists the drafted entity', async () => {
      vi.spyOn(metadataApi, 'entities').mockResolvedValue(structuredClone(ENTITIES))
      renderPage()
      await waitFor(() => expect(screen.getByText(/Entities \(1\)/)).toBeInTheDocument())
      fireEvent.click(screen.getByText(/Entities \(1\)/))

      expect(await screen.findByText('customer')).toBeInTheDocument()
      expect(screen.getByDisplayValue('Customer')).toBeInTheDocument()
      expect(screen.getByDisplayValue('One row per customer.')).toBeInTheDocument()
      expect(screen.getByText('Not yet confirmed')).toBeInTheDocument()
    })

    it('explains the empty state instead of showing nothing', async () => {
      renderPage()
      await waitFor(() => expect(screen.getByText(/Entities \(0\)/)).toBeInTheDocument())
      fireEvent.click(screen.getByText(/Entities \(0\)/))
      expect(await screen.findByText(/No entities yet/)).toBeInTheDocument()
    })

    it('confirms an entity through the entities/confirm route', async () => {
      vi.spyOn(metadataApi, 'entities').mockResolvedValue(structuredClone(ENTITIES))
      renderPage()
      await waitFor(() => screen.getByText(/Entities \(1\)/))
      fireEvent.click(screen.getByText(/Entities \(1\)/))

      fireEvent.click(await screen.findByText('Confirm'))
      await waitFor(() => expect(metadataApi.confirmEntities).toHaveBeenCalledWith(
        7, { updates: [{ id: 1, confirm: true }] }))
    })

    it('edits a field and saves it through the entities/confirm route', async () => {
      vi.spyOn(metadataApi, 'entities').mockResolvedValue(structuredClone(ENTITIES))
      renderPage()
      await waitFor(() => screen.getByText(/Entities \(1\)/))
      fireEvent.click(screen.getByText(/Entities \(1\)/))

      const grainInput = await screen.findByDisplayValue('One row per customer.')
      fireEvent.change(grainInput, { target: { value: 'One row per confirmed customer.' } })
      fireEvent.click(screen.getByText('Save'))

      await waitFor(() => expect(metadataApi.confirmEntities).toHaveBeenCalledWith(
        7, { updates: [{
          id: 1, business_name: 'Customer',
          grain: 'One row per confirmed customer.',
          description: 'A person who placed orders.',
        }] }))
    })
  })
})

describe('Source health: index advice', () => {
  // DirectQuery latency on a big table is the customer's index situation, not
  // ours. Measured at 10M rows: an index on the FILTERED column cut a governed
  // query by a quarter; one on the grouped column changed nothing. This tab
  // shows what the platform has watched itself filter on, and hands the DBA a
  // statement to paste. Fetched on first open, like schema drift.
  const ADVICE = {
    tables: [{ table: 'orders', columns: [
      { column: 'region', runs: 12, avg_ms: 950, score: 11400, indexed: false, recommended: true,
        statement: 'CREATE INDEX ON "orders" ("region");' },
      { column: 'tenant', runs: 40, avg_ms: 20, score: 800, indexed: true, recommended: false,
        statement: null },
    ] }],
    min_runs: 3, observed_days: 30, runs_considered: 52, index_check: 'checked' as const,
  }

  it('shows a recommendation with its paste-ready statement', async () => {
    const spy = vi.spyOn(dataSourcesApi, 'indexAdvice').mockResolvedValue(ADVICE)
    renderPage()
    await waitFor(() => expect(screen.getByText(/Confirm 1 selected/)).toBeInTheDocument())
    expect(spy).not.toHaveBeenCalled()          // not until the tab is opened
    fireEvent.click(screen.getByRole('button', { name: /source health/i }))
    expect(await screen.findByText('CREATE INDEX ON "orders" ("region");')).toBeInTheDocument()
    expect(screen.getByText(/12 runs/)).toBeInTheDocument()
    expect(spy).toHaveBeenCalledWith(7)
  })

  it('says when a column is already indexed instead of recommending it', async () => {
    vi.spyOn(dataSourcesApi, 'indexAdvice').mockResolvedValue(ADVICE)
    renderPage()
    await waitFor(() => expect(screen.getByText(/Confirm 1 selected/)).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: /source health/i }))
    const row = (await screen.findByText('tenant')).closest('tr') as HTMLElement
    expect(within(row).getByText(/already indexed/i)).toBeInTheDocument()
    expect(within(row).queryByText(/CREATE INDEX/)).not.toBeInTheDocument()
  })

  it('says so when the customer database could not be checked', async () => {
    vi.spyOn(dataSourcesApi, 'indexAdvice').mockResolvedValue({ ...ADVICE, index_check: 'unavailable' })
    renderPage()
    await waitFor(() => expect(screen.getByText(/Confirm 1 selected/)).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: /source health/i }))
    expect(await screen.findByText(/could not be checked/i)).toBeInTheDocument()
  })

  it('says index checks are Postgres-only for another dialect, and pastes nothing', async () => {
    vi.spyOn(dataSourcesApi, 'indexAdvice').mockResolvedValue({
      ...ADVICE, index_check: 'unsupported',
      tables: [{ table: 'orders', columns: [{ column: 'region', runs: 12, avg_ms: 950, score: 11400,
        indexed: null, recommended: true, statement: null }] }],
    })
    renderPage()
    await waitFor(() => expect(screen.getByText(/Confirm 1 selected/)).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: /source health/i }))
    expect(await screen.findByText(/Postgres-only/i)).toBeInTheDocument()
    expect(screen.queryByText(/CREATE INDEX/)).not.toBeInTheDocument()
  })

  it('explains an empty result rather than showing a blank tab', async () => {
    vi.spyOn(dataSourcesApi, 'indexAdvice').mockResolvedValue({ ...ADVICE, tables: [], runs_considered: 0 })
    renderPage()
    await waitFor(() => expect(screen.getByText(/Confirm 1 selected/)).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: /source health/i }))
    expect(await screen.findByText(/no DirectQuery runs/i)).toBeInTheDocument()
  })
})


describe('arriving while a sync is already running', () => {
  /* Creating a connection now starts a sync and sends the user straight here.
     Before this, the page read the run ONCE and showed a frozen snapshot: the
     stages never advanced, the queue never refilled, and the only way to see the
     result was to reload a page that gave no hint it needed reloading. */

  const RUNNING: SyncRun = { id: 42, status: 'running', stages: [], trigger: 'on_create' }

  it('follows a sync it did not start', async () => {
    vi.spyOn(metadataApi, 'latestSync').mockResolvedValue(RUNNING)
    const status = vi.spyOn(metadataApi, 'syncStatus').mockResolvedValue(
      { id: 42, status: 'ok', stages: [] } as SyncRun)
    renderPage()
    await waitFor(() => expect(status).toHaveBeenCalledWith(7, 42),
                  { timeout: 5000 })
  })

  it('does not follow a run that has already finished', async () => {
    const status = vi.spyOn(metadataApi, 'syncStatus')
    renderPage()
    await screen.findByText(/maps/)
    expect(status).not.toHaveBeenCalled()
  })
})
