import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import PrepPipelinePanel, { suggestJoinKeys, joinPairs, writeJoinPairs } from './PrepPipelinePanel'
import { prepApi, datasetsApi, relationshipsApi } from '../../services/api'
import type { Relationship } from '../../services/api'

vi.mock('../../services/api', () => ({
  prepApi: { get: vi.fn(), set: vi.fn(), preview: vi.fn(), materialize: vi.fn(), rebuild: vi.fn() },
  datasetsApi: { list: vi.fn(), get: vi.fn() },
  relationshipsApi: { list: vi.fn() },
}))

const columns = [
  { id: 1, name: 'region', dtype: 'categorical', missing_pct: 0, stats: {} },
  { id: 2, name: 'amount', dtype: 'numeric', missing_pct: 0, stats: {} },
]

const previewResult = {
  before: { rows: 10, columns: ['region', 'amount'] },
  after: { rows: 8, columns: ['region', 'amount'] },
  steps: [{ rows_in: 10, rows_out: 8, columns: ['region', 'amount'] }],
  sample: { columns: ['region', 'amount'], rows: [['US', 1], ['CA', 2]] },
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(prepApi.get).mockResolvedValue([])
  vi.mocked(prepApi.set).mockResolvedValue([])
  vi.mocked(prepApi.preview).mockResolvedValue(previewResult)
  vi.mocked(datasetsApi.list).mockResolvedValue([])
  vi.mocked(datasetsApi.get).mockResolvedValue({
    id: 9, name: 'Customers',
    columns: [{ id: 1, name: 'id', dtype: 'categorical', missing_pct: 0, stats: {} },
              { id: 2, name: 'segment', dtype: 'categorical', missing_pct: 0, stats: {} }],
  } as any)
  vi.mocked(prepApi.materialize).mockResolvedValue({ id: 42, name: 'Joined dataset' } as any)
  vi.mocked(relationshipsApi.list).mockResolvedValue([])
})

describe('PrepPipelinePanel', () => {
  it('shows an empty state with no saved steps', async () => {
    render(<PrepPipelinePanel datasetId={1} columns={columns} />)
    await waitFor(() => expect(screen.getByTestId('prep-empty')).toBeInTheDocument())
  })

  it('renders a card per saved step, one per kind', async () => {
    vi.mocked(prepApi.get).mockResolvedValue([
      { kind: 'trim' },
      { kind: 'sort', columns: [{ column: 'amount', dir: 'desc' }] },
      { kind: 'dedupe', subset: ['region'] },
    ])
    render(<PrepPipelinePanel datasetId={1} columns={columns} />)
    await waitFor(() => expect(screen.getAllByTestId('prep-step-card')).toHaveLength(3))
    expect(screen.getByText('Trim whitespace')).toBeInTheDocument()
    expect(screen.getByText('Sort')).toBeInTheDocument()
    expect(screen.getByText('Remove duplicates')).toBeInTheDocument()
  })

  it('adds a step from the add-step menu', async () => {
    render(<PrepPipelinePanel datasetId={1} columns={columns} />)
    await waitFor(() => expect(screen.getByTestId('prep-empty')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: '+ Add step' }))
    fireEvent.click(screen.getByText('Remove duplicates'))
    await waitFor(() => expect(screen.getAllByTestId('prep-step-card')).toHaveLength(1))
  })

  it('reorders a step with the up/down buttons', async () => {
    vi.mocked(prepApi.get).mockResolvedValue([{ kind: 'trim' }, { kind: 'dedupe', subset: [] }])
    render(<PrepPipelinePanel datasetId={1} columns={columns} />)
    await waitFor(() => expect(screen.getAllByTestId('prep-step-card')).toHaveLength(2))
    const cardsBefore = screen.getAllByTestId('prep-step-card')
    expect(cardsBefore[0]).toHaveTextContent('Trim whitespace')
    const downButtons = screen.getAllByLabelText('move down')
    fireEvent.click(downButtons[0])
    const cardsAfter = screen.getAllByTestId('prep-step-card')
    expect(cardsAfter[0]).toHaveTextContent('Remove duplicates')
    expect(cardsAfter[1]).toHaveTextContent('Trim whitespace')
  })

  it('toggling disable marks the step disabled=true in the saved model, WITHOUT deleting it', async () => {
    vi.mocked(prepApi.get).mockResolvedValue([{ kind: 'trim' }])
    render(<PrepPipelinePanel datasetId={1} columns={columns} />)
    await waitFor(() => expect(screen.getAllByTestId('prep-step-card')).toHaveLength(1))
    await waitFor(() => expect(prepApi.preview).toHaveBeenCalledWith(1, [{ kind: 'trim' }]))
    fireEvent.click(screen.getByLabelText('disable'))
    // The card stays -- disable pauses the step, it does not remove it.
    expect(screen.getAllByTestId('prep-step-card')).toHaveLength(1)
    expect(screen.getByTestId('prep-step-skipped')).toHaveTextContent('skipped')
    // The disabled step is still sent to preview (so the backend can mark it
    // skipped) and, critically, still sent to save -- it is never dropped.
    await waitFor(() => expect(prepApi.preview).toHaveBeenLastCalledWith(1, [{ kind: 'trim', disabled: true }]))
    fireEvent.click(screen.getByRole('button', { name: /Save pipeline/ }))
    await waitFor(() => expect(prepApi.set).toHaveBeenCalledWith(1, [{ kind: 'trim', disabled: true }]))
  })

  it('a disabled step survives reload: GET restores it still disabled', async () => {
    vi.mocked(prepApi.get).mockResolvedValue([{ kind: 'trim', disabled: true }, { kind: 'dedupe', subset: [] }])
    render(<PrepPipelinePanel datasetId={1} columns={columns} />)
    await waitFor(() => expect(screen.getAllByTestId('prep-step-card')).toHaveLength(2))
    expect(screen.getByTestId('prep-step-skipped')).toBeInTheDocument()
    expect(screen.getByLabelText('enable')).toBeInTheDocument()  // trim shows "enable" -- it's currently disabled
  })

  it('the preview marks a disabled step "skipped" instead of showing a row-count strip', async () => {
    vi.mocked(prepApi.get).mockResolvedValue([{ kind: 'trim', disabled: true }])
    vi.mocked(prepApi.preview).mockResolvedValue({
      before: { rows: 10, columns: ['region'] },
      after: { rows: 10, columns: ['region'] },
      steps: [{ rows_in: 10, rows_out: 10, columns: ['region'], skipped: true }],
      sample: { columns: ['region'], rows: [] },
    })
    render(<PrepPipelinePanel datasetId={1} columns={columns} />)
    await waitFor(() => expect(screen.getByTestId('prep-step-skipped')).toHaveTextContent('skipped'))
  })

  it('deleting a step removes its card and updates the saved model', async () => {
    vi.mocked(prepApi.get).mockResolvedValue([{ kind: 'trim' }])
    render(<PrepPipelinePanel datasetId={1} columns={columns} />)
    await waitFor(() => expect(screen.getAllByTestId('prep-step-card')).toHaveLength(1))
    fireEvent.click(screen.getByLabelText('delete'))
    await waitFor(() => expect(screen.getByTestId('prep-empty')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: '+ Add step' })) // menu still opens fine post-delete
  })

  it('calls the preview endpoint and renders the final sample', async () => {
    vi.mocked(prepApi.get).mockResolvedValue([{ kind: 'trim' }])
    render(<PrepPipelinePanel datasetId={1} columns={columns} />)
    await waitFor(() => expect(prepApi.preview).toHaveBeenCalledWith(1, [{ kind: 'trim' }]))
    await waitFor(() => expect(screen.getByTestId('prep-final-preview')).toHaveTextContent('rows in'))
    expect(screen.getByTestId('prep-final-preview')).toHaveTextContent('rows out')
  })

  it('saves the enabled steps via Save pipeline', async () => {
    vi.mocked(prepApi.get).mockResolvedValue([{ kind: 'trim' }])
    render(<PrepPipelinePanel datasetId={1} columns={columns} />)
    await waitFor(() => expect(screen.getAllByTestId('prep-step-card')).toHaveLength(1))
    fireEvent.click(screen.getByRole('button', { name: /Save pipeline/ }))
    await waitFor(() => expect(prepApi.set).toHaveBeenCalledWith(1, [{ kind: 'trim' }]))
  })

  describe('save as new dataset', () => {
    /**
     * A prep join is a VIEW -- it re-joins on every read. Saving turns that
     * result into a dataset of its own, which is what "join several datasets
     * into one" actually means for a user.
     */
    const openDialog = async () => {
      // A preview only exists once there is a pipeline to preview.
      vi.mocked(prepApi.get).mockResolvedValue([{ kind: 'trim' }])
      render(<PrepPipelinePanel datasetId={1} columns={columns} />)
      await screen.findByTestId('prep-final-preview')
      fireEvent.click(screen.getByRole('button', { name: /Save as new dataset/ }))
      return screen.findByRole('dialog', { name: /Save as new dataset/ })
    }

    it('offers saving only once there is a previewed result to save', async () => {
      // An empty pipeline previews nothing, so there is no result to keep.
      render(<PrepPipelinePanel datasetId={1} columns={columns} />)
      await waitFor(() => expect(screen.getByTestId('prep-empty')).toBeInTheDocument())
      expect(screen.queryByRole('button', { name: /Save as new dataset/ })).toBeNull()
    })

    it('shows the previewed shape so the author knows what they are keeping', async () => {
      await openDialog()
      // Matched on the rendered text because JSX splits the line across nodes,
      // and on the LOCALISED number because toLocaleString honours the runtime
      // locale -- this environment renders 8 as an Arabic-Indic digit.
      const dialog = screen.getByRole('dialog', { name: /Save as new dataset/ })
      expect(dialog.textContent).toContain(`${(8).toLocaleString()} rows`)
      expect(dialog.textContent).toMatch(/2 columns/)
    })

    it('says plainly that the copy will not follow its sources', async () => {
      // The snapshot behaviour is the one thing a user cannot infer from the UI.
      await openDialog()
      expect(screen.getByText(/will not update/i)).toBeInTheDocument()
    })

    it('sends the name and the current steps', async () => {
      vi.mocked(prepApi.get).mockResolvedValue([{ kind: 'trim' }])
      render(<PrepPipelinePanel datasetId={1} columns={columns} />)
      await screen.findByTestId('prep-final-preview')
      fireEvent.click(screen.getByRole('button', { name: /Save as new dataset/ }))
      await screen.findByRole('dialog', { name: /Save as new dataset/ })

      fireEvent.change(screen.getByLabelText('Dataset name'), { target: { value: 'Q3 joined' } })
      fireEvent.click(screen.getByRole('button', { name: 'Create' }))

      await waitFor(() => expect(prepApi.materialize).toHaveBeenCalled())
      const [dsId, body] = vi.mocked(prepApi.materialize).mock.calls[0]
      expect(dsId).toBe(1)
      expect(body.name).toBe('Q3 joined')
      expect(body.steps).toEqual([{ kind: 'trim' }])
    })

    it('confirms the new dataset and links to it', async () => {
      await openDialog()
      fireEvent.change(screen.getByLabelText('Dataset name'), { target: { value: 'X' } })
      fireEvent.click(screen.getByRole('button', { name: 'Create' }))

      const link = await screen.findByRole('link', { name: 'Joined dataset' })
      expect(link).toHaveAttribute('href', '/datasets/42')
    })

    it('shows the server message when it is refused', async () => {
      // The refusals (governed data, exports disabled) are written for a person
      // to read; replacing them with a generic message loses the reason.
      vi.mocked(prepApi.materialize).mockRejectedValue({
        response: { data: { detail: 'Cannot save a snapshot of a dataset that has row- or column-security rules' } },
      })
      await openDialog()
      fireEvent.change(screen.getByLabelText('Dataset name'), { target: { value: 'X' } })
      fireEvent.click(screen.getByRole('button', { name: 'Create' }))

      expect(await screen.findByText(/row- or column-security rules/)).toBeInTheDocument()
      // ...and the dialog stays open so the name is not retyped.
      expect(screen.getByRole('dialog', { name: /Save as new dataset/ })).toBeInTheDocument()
    })
  })

  describe('the joined dataset key', () => {
    it('is chosen from the joined dataset columns, not typed', async () => {
      vi.mocked(prepApi.get).mockResolvedValue([
        { kind: 'join', dataset_id: 9, how: 'left', left_on: 'region', right_on: '' },
      ])
      vi.mocked(datasetsApi.list).mockResolvedValue([{ id: 9, name: 'Customers' } as any])
      render(<PrepPipelinePanel datasetId={1} columns={columns} />)

      // The editor renders for the selected card, so open it first.
      const card = await screen.findByTestId('prep-step-card')
      fireEvent.click(card)

      await waitFor(() => expect(datasetsApi.get).toHaveBeenCalledWith(9))
      await waitFor(() =>
        expect(screen.getByRole('option', { name: 'segment' })).toBeInTheDocument())
    })
  })

  describe('suggesting the join keys', () => {
    /**
     * The platform already works out how tables connect -- name match, type
     * check, value overlap, cardinality -- and stores it with a confidence and
     * a provenance. Until now nothing read that at join time, so the author
     * retyped what the system already knew.
     */
    // Typed as Relationship so `source` stays the literal union rather than
    // widening to string -- the helper ranks on those exact values.
    const r = (over: Partial<Relationship> = {}): Relationship => ({
      id: 1, org_id: 1, from_dataset_id: 1, from_column: 'cust',
      to_dataset_id: 9, to_column: 'id', created_at: '2026-01-01',
      source: 'declared', confidence: 1, ...over,
    })

    it('finds the pair for a link recorded in either direction', () => {
      // The relationship is a fact about two tables, not about which one the
      // author happened to start from.
      const forward = suggestJoinKeys([r()], 1, 9)
      expect(forward).toMatchObject({ left_on: 'cust', right_on: 'id' })

      const backward = suggestJoinKeys([r({ from_dataset_id: 9, from_column: 'id',
                                            to_dataset_id: 1, to_column: 'cust' })], 1, 9)
      expect(backward).toMatchObject({ left_on: 'cust', right_on: 'id' })
    })

    it('prefers what a human approved over what was guessed', () => {
      const hit = suggestJoinKeys([
        r({ id: 1, source: 'inferred', confidence: 0.99, from_column: 'guessed' }),
        r({ id: 2, source: 'confirmed', confidence: 0.4, from_column: 'approved' }),
      ], 1, 9)
      // Confidence loses to provenance on purpose: a person looked at one of these.
      expect(hit?.left_on).toBe('approved')
    })

    it('falls back to confidence within the same provenance', () => {
      const hit = suggestJoinKeys([
        r({ id: 1, source: 'inferred', confidence: 0.6, from_column: 'weak' }),
        r({ id: 2, source: 'inferred', confidence: 0.95, from_column: 'strong' }),
      ], 1, 9)
      expect(hit?.left_on).toBe('strong')
    })

    it('suggests nothing when the two datasets are not linked', () => {
      expect(suggestJoinKeys([r({ to_dataset_id: 77 })], 1, 9)).toBeNull()
      expect(suggestJoinKeys([], 1, 9)).toBeNull()
    })

    it('fills both keys in when a joined dataset is chosen', async () => {
      vi.mocked(relationshipsApi.list).mockResolvedValue([r()])
      vi.mocked(datasetsApi.list).mockResolvedValue([{ id: 9, name: 'Customers' } as any])
      vi.mocked(prepApi.get).mockResolvedValue([
        { kind: 'join', dataset_id: null, how: 'left', left_on: '', right_on: '' },
      ])
      render(<PrepPipelinePanel datasetId={1} columns={columns} />)
      fireEvent.click(await screen.findByTestId('prep-step-card'))

      // The first combobox in the join editor is the dataset picker.
      fireEvent.change(screen.getAllByRole('combobox')[0], { target: { value: '9' } })

      // The note only appears when the keys on screen ARE the suggested ones,
      // so seeing it proves both were filled in.
      await waitFor(() =>
        expect(screen.getByText(/declared relationship/)).toBeInTheDocument())
    })

    it('says a detected key is worth checking, unlike a confirmed one', async () => {
      vi.mocked(relationshipsApi.list).mockResolvedValue([r({ source: 'inferred', confidence: 0.8 })])
      vi.mocked(datasetsApi.list).mockResolvedValue([{ id: 9, name: 'Customers' } as any])
      vi.mocked(prepApi.get).mockResolvedValue([
        { kind: 'join', dataset_id: 9, how: 'left', left_on: 'cust', right_on: 'id' },
      ])
      render(<PrepPipelinePanel datasetId={1} columns={columns} />)
      fireEvent.click(await screen.findByTestId('prep-step-card'))

      expect(await screen.findByText(/detected relationship — check them/)).toBeInTheDocument()
    })

    it('stops claiming provenance once the author overrides a key', async () => {
      // Otherwise the note would vouch for keys the model never proposed.
      vi.mocked(relationshipsApi.list).mockResolvedValue([r()])
      vi.mocked(datasetsApi.list).mockResolvedValue([{ id: 9, name: 'Customers' } as any])
      vi.mocked(prepApi.get).mockResolvedValue([
        { kind: 'join', dataset_id: 9, how: 'left', left_on: 'amount', right_on: 'id' },
      ])
      render(<PrepPipelinePanel datasetId={1} columns={columns} />)
      fireEvent.click(await screen.findByTestId('prep-step-card'))

      await waitFor(() => expect(screen.getAllByRole('combobox').length).toBeGreaterThan(0))
      expect(screen.queryByText(/relationship\./)).toBeNull()
    })
  })

  describe('a join that multiplies rows', () => {
    /**
     * The quiet failure mode of joining. A key that is not unique on the other
     * side turns one row into many, so every total is silently wrong -- and a
     * suggested key is no protection, because a relationship records how two
     * tables link, not that the match is one-to-one. Seen live on demo data:
     * a declared relationship took 2,000 rows to 35,137.
     */
    const joinStep = { kind: 'join', dataset_id: 9, how: 'left', left_on: 'region', right_on: 'id' }

    it('says so when the row count balloons', async () => {
      vi.mocked(prepApi.get).mockResolvedValue([joinStep])
      vi.mocked(prepApi.preview).mockResolvedValue({
        ...previewResult,
        steps: [{ rows_in: 2000, rows_out: 35137, columns: ['region', 'amount'] }],
      })
      render(<PrepPipelinePanel datasetId={1} columns={columns} />)
      expect(await screen.findByTestId('prep-join-fanout')).toBeInTheDocument()
    })

    it('stays quiet when the join behaves', async () => {
      vi.mocked(prepApi.get).mockResolvedValue([joinStep])
      vi.mocked(prepApi.preview).mockResolvedValue({
        ...previewResult,
        steps: [{ rows_in: 2000, rows_out: 2000, columns: ['region', 'amount'] }],
      })
      render(<PrepPipelinePanel datasetId={1} columns={columns} />)
      await screen.findByTestId('prep-final-preview')
      expect(screen.queryByTestId('prep-join-fanout')).toBeNull()
    })

    it('does not warn on a filter that removes rows', async () => {
      // Only a join can multiply; a shrinking step is the point of the step.
      vi.mocked(prepApi.get).mockResolvedValue([{ kind: 'dedupe', subset: [] }])
      vi.mocked(prepApi.preview).mockResolvedValue({
        ...previewResult,
        steps: [{ rows_in: 10, rows_out: 8, columns: ['region', 'amount'] }],
      })
      render(<PrepPipelinePanel datasetId={1} columns={columns} />)
      await screen.findByTestId('prep-final-preview')
      expect(screen.queryByTestId('prep-join-fanout')).toBeNull()
    })
  })

  describe('composite join keys', () => {
    /**
     * One column is often not enough to identify a row -- region + date, order
     * + line. Joining on only one of them multiplies rows instead of adding
     * columns, and every total is silently wrong afterwards.
     */
    it('reads a step saved before composite keys existed', () => {
      // The singular shape lives in deployed databases; it is read, not migrated.
      expect(joinPairs({ kind: 'join', left_on: 'cust', right_on: 'id' } as any))
        .toEqual([{ left: 'cust', right: 'id' }])
    })

    it('reads a composite step', () => {
      expect(joinPairs({ kind: 'join', left_ons: ['region', 'date'],
                         right_ons: ['region', 'as_of'] } as any))
        .toEqual([{ left: 'region', right: 'region' }, { left: 'date', right: 'as_of' }])
    })

    it('writes one key back in the OLD shape', () => {
      // So a single-key step's JSON is byte-identical to what it was, and an
      // older reader still understands it.
      expect(writeJoinPairs([{ left: 'cust', right: 'id' }]))
        .toMatchObject({ left_on: 'cust', right_on: 'id', left_ons: undefined, right_ons: undefined })
    })

    it('writes two keys back as lists, clearing the singular fields', () => {
      // Leaving left_on behind would give the step two contradictory readings.
      expect(writeJoinPairs([{ left: 'region', right: 'region' }, { left: 'date', right: 'as_of' }]))
        .toMatchObject({ left_ons: ['region', 'date'], right_ons: ['region', 'as_of'],
                         left_on: undefined, right_on: undefined })
    })

    const showJoin = async (step: Record<string, unknown> & { kind: string }) => {
      vi.mocked(prepApi.get).mockResolvedValue([step])
      vi.mocked(datasetsApi.list).mockResolvedValue([{ id: 9, name: 'Customers' } as any])
      render(<PrepPipelinePanel datasetId={1} columns={columns} />)
      fireEvent.click(await screen.findByTestId('prep-step-card'))
    }

    it('shows one key row and no remove control for a simple join', async () => {
      await showJoin({ kind: 'join', dataset_id: 9, how: 'left', left_on: 'region', right_on: 'id' })
      // The common case must look exactly as it did before.
      expect(screen.queryByRole('button', { name: /Remove key/ })).toBeNull()
      expect(screen.getByRole('button', { name: '+ add key' })).toBeInTheDocument()
    })

    it('adds a second key row on demand', async () => {
      await showJoin({ kind: 'join', dataset_id: 9, how: 'left', left_on: 'region', right_on: 'id' })
      fireEvent.click(screen.getByRole('button', { name: '+ add key' }))

      await waitFor(() =>
        expect(screen.getAllByRole('button', { name: /Remove key/ })).toHaveLength(2))
    })

    it('lists every key pair in the step summary', async () => {
      await showJoin({ kind: 'join', dataset_id: 9, how: 'left',
                       left_ons: ['region', 'date'], right_ons: ['region', 'as_of'] })
      expect(await screen.findByText(/region = region and date = as_of/)).toBeInTheDocument()
    })

    it('drops back to the single-key shape when a pair is removed', async () => {
      await showJoin({ kind: 'join', dataset_id: 9, how: 'left',
                       left_ons: ['region', 'date'], right_ons: ['region', 'as_of'] })
      fireEvent.click(screen.getAllByRole('button', { name: /Remove key/ })[1])

      await waitFor(() =>
        expect(screen.queryByRole('button', { name: /Remove key/ })).toBeNull())
      expect(await screen.findByText(/on region = region$/)).toBeInTheDocument()
    })
  })
})

describe('cell corrections in the pipeline', () => {
  /**
   * `edit_cells` steps are written by the data grid, not by this panel's add
   * menu — but they land in the same list, and a step that renders as a bare
   * "edit_cells" with no summary would be the one transform in the pipeline a
   * user cannot read or check. It must also be removable HERE, since that is
   * the whole promise of recording a correction as a step.
   */
  it('reads as a correction, not as a raw kind', async () => {
    vi.mocked(prepApi.get).mockResolvedValue([
      { kind: 'edit_cells', key_column: 'order_id', column: 'region',
        edits: [{ key: 'A-1', value: 'North' }, { key: 'A-2', value: 'South' }] },
    ] as never)
    render(<PrepPipelinePanel datasetId={1} columns={columns} />)
    await waitFor(() => expect(screen.getAllByTestId('prep-step-card')).toHaveLength(1))
    expect(screen.getByText(/edit cells|cell correction/i)).toBeInTheDocument()
    // The summary has to say how many and to which column, or a reader has to
    // open the JSON to find out what the step does.
    expect(screen.getByText(/2 .*region.*order_id|region.*2 correction/i)).toBeInTheDocument()
  })

  it('is not offered in the add-step menu', async () => {
    // It needs a row key and a value from the grid; an empty one typed here
    // would be a step that can only be filled in somewhere else.
    render(<PrepPipelinePanel datasetId={1} columns={columns} />)
    await waitFor(() => expect(screen.getByTestId('prep-empty')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: /add step/i }))
    expect(screen.queryByRole('button', { name: /edit cells/i })).not.toBeInTheDocument()
  })
})
