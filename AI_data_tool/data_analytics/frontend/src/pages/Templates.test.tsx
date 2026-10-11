import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import Templates from './Templates'
import UseTemplateDialog from './templates/UseTemplateDialog'
import { ConfirmProvider } from '../components/ui/ConfirmDialog'
import { datasetsApi, templatesApi, type TemplateCard, type TemplateMatch } from '../services/api'

/** The template gallery: what is listed, how it is narrowed, favourites, and
 *  the mapping dialog that turns a template into a dashboard. */

const card = (over: Partial<TemplateCard>): TemplateCard => ({
  ref: 'builtin:overview', source: 'builtin', key: 'overview', name: 'Performance overview', description: 'server words',
  category: 'overview', tags: ['numbers'], slots: [{ id: 'value', label: 'The number to follow', kind: 'measure', required: true }],
  preview: [{ x: 0, y: 0, w: 3, h: 3, kind: 'kpi' }], style: {}, pages: 1, widgets: 8, metrics: 0, version: 1, uses: null,
  updated_at: null, favorite: false, mine: false, can_change: false, ...over,
})
const CARDS = [
  card({}),
  card({ ref: 'builtin:stages', key: 'stages', name: 'Stages and conversion', category: 'stages', tags: ['funnel'],
    slots: [{ id: 'stage', label: 'The stage each row is at', kind: 'stage', required: true }] }),
  card({ ref: 't:5', source: 'personal', key: null, name: 'My weekly view', description: 'what I look at on Mondays',
    category: 'trend', mine: true, can_change: true, version: 3 }),
]

beforeEach(() => {
  vi.restoreAllMocks()
  vi.spyOn(datasetsApi, 'list').mockResolvedValue([{ id: 7, name: 'rows' }] as never)
  vi.spyOn(templatesApi, 'list').mockResolvedValue({ templates: CARDS, categories: ['overview', 'trend', 'stages'] })
})

const mount = () => render(<MemoryRouter><ConfirmProvider><Templates /></ConfirmProvider></MemoryRouter>)
const names = () => screen.getAllByRole('article').map(a => a.getAttribute('aria-label'))

describe('the template gallery', () => {
  it('lists the platform’s templates in the catalogue’s words and a saved one in its author’s', async () => {
    mount()
    await waitFor(() => expect(names()).toEqual(['Performance overview', 'Stages and conversion', 'My weekly view']))
    const first = screen.getAllByRole('article')[0]
    // The built-in's description comes from the catalogue, not the server's fallback.
    expect(within(first).queryByText('server words')).not.toBeInTheDocument()
    expect(within(first).getByText(/Needs/).parentElement).toHaveTextContent('a number')
    expect(within(screen.getAllByRole('article')[2]).getByText('what I look at on Mondays')).toBeInTheDocument()
  })

  it('is narrowed by search, by kind and by whose it is', async () => {
    mount()
    await waitFor(() => expect(names()).toHaveLength(3))
    fireEvent.change(screen.getByLabelText('Search templates'), { target: { value: 'funnel' } })
    expect(names()).toEqual(['Stages and conversion'])
    fireEvent.change(screen.getByLabelText('Search templates'), { target: { value: '' } })
    fireEvent.click(screen.getByRole('button', { name: 'Trends' }))
    expect(names()).toEqual(['My weekly view'])
    fireEvent.click(screen.getByRole('button', { name: 'Every kind' }))
    fireEvent.click(screen.getByRole('button', { name: 'Built-in' }))
    expect(names()).toEqual(['Performance overview', 'Stages and conversion'])
  })

  it('offers changing only what is one’s own', async () => {
    mount()
    await waitFor(() => expect(names()).toHaveLength(3))
    expect(screen.queryByRole('button', { name: 'Delete: Performance overview' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Delete: My weekly view' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Make my own copy: Performance overview' })).toBeInTheDocument()
  })

  it('stars a template at once and tells the server', async () => {
    const fav = vi.spyOn(templatesApi, 'favorite').mockResolvedValue({ favorite: true })
    mount()
    await waitFor(() => expect(names()).toHaveLength(3))
    fireEvent.click(screen.getByRole('button', { name: 'Add Performance overview to favourites' }))
    expect(fav).toHaveBeenCalledWith('builtin:overview', true)
    expect(screen.getByRole('button', { name: 'Remove Performance overview from favourites' })).toHaveAttribute('aria-pressed', 'true')
    fireEvent.click(screen.getByRole('button', { name: 'Favourites' }))
    expect(names()).toEqual(['Performance overview'])
  })

  it('ranks by a chosen dataset and will not use what does not fit it', async () => {
    const list = vi.spyOn(templatesApi, 'list').mockResolvedValue({ categories: [], templates: [
      card({ fit: { usable: true, score: 0.9, widgets: { kept: 7, total: 8 }, missing: [] } }),
      card({ ref: 'builtin:stages', key: 'stages', name: 'Stages and conversion',
        slots: [{ id: 'stage', label: 'The stage each row is at', kind: 'stage', required: true }],
        fit: { usable: false, score: 0, widgets: { kept: 0, total: 7 }, missing: ['stage'] } })] })
    mount()
    await waitFor(() => expect(names()).toHaveLength(2))
    fireEvent.change(screen.getByLabelText('Match to a dataset'), { target: { value: '7' } })
    await waitFor(() => expect(list).toHaveBeenLastCalledWith(7))
    const [fits, not] = screen.getAllByRole('article')
    expect(within(fits).getByText('Fits: 7 of 8 charts')).toBeInTheDocument()
    expect(within(fits).getByText('Best match')).toBeInTheDocument()
    expect(within(not).getByText(/Does not fit this data/)).toHaveTextContent('The stage each row is at')
    expect(within(not).getByRole('button', { name: 'Use template' })).toBeDisabled()
  })
})

describe('using a template', () => {
  const match = (over: Partial<TemplateMatch> = {}): TemplateMatch => ({
    columns: [], slots: [{ id: 'value', label: 'The number to follow', kind: 'measure', required: true },
      { id: 'group', label: 'The main way to split it', kind: 'category', required: false }],
    candidates: { value: ['amount', 'planned'], group: ['team'] }, suggested: { value: ['amount'], group: ['team'] },
    mapping: { value: ['amount'], group: ['team'] },
    check: { ok: true, problems: [], missing: [], widgets: { kept: 8, total: 8 }, dropped: [] },
    preview: { pages: [], measures: [], dropped: [], skipped_metrics: [], filters: [] }, can_define_measures: true, ...over,
  })

  it('shows the suggested mapping, checks each change, and creates with what was chosen', async () => {
    const check = vi.spyOn(templatesApi, 'match').mockResolvedValue(match())
    const use = vi.spyOn(templatesApi, 'use').mockResolvedValue({ report_id: 3, name: 'x', dropped: [], refused: [], measures: [], skipped_metrics: [] })
    render(<MemoryRouter><UseTemplateDialog template={CARDS[0]} datasetId={7} onClose={() => {}} /></MemoryRouter>)
    await waitFor(() => expect(screen.getByText('8 of 8 charts will be drawn.')).toBeInTheDocument())
    expect(check).toHaveBeenCalledWith('builtin:overview', 7, undefined, undefined)
    expect(screen.getByLabelText(/The number to follow/)).toHaveValue('amount')
    check.mockResolvedValue(match({ mapping: { value: ['planned'] },
      check: { ok: true, problems: [], missing: ['group'], widgets: { kept: 5, total: 8 }, dropped: ['x'] },
      preview: { pages: [], measures: [], filters: [], skipped_metrics: [], dropped: [{ title: 'By group', needs: ['group'] }] } }))
    fireEvent.change(screen.getByLabelText(/The main way to split it/), { target: { value: '' } })
    await waitFor(() => expect(screen.getByText('5 of 8 charts will be drawn.')).toBeInTheDocument())
    expect(check).toHaveBeenLastCalledWith('builtin:overview', 7, { value: ['amount'] }, undefined)
    expect(screen.getByText('By group')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Create dashboard' }))
    await waitFor(() => expect(use).toHaveBeenCalledWith('builtin:overview', { dataset_id: 7, mapping: { value: ['planned'] }, name: undefined }))
  })

  it('asks for a dataset for each additional one the template reads, and shows its columns only then', async () => {
    const withOther = match({ datasets: [{ key: 'd2', label: 'costs', dataset_id: null }],
      slots: [{ id: 'value', label: 'The number to follow', kind: 'measure', required: true },
        { id: 'cost', label: 'cost', kind: 'measure', required: true, dataset: 'd2' }],
      candidates: { value: ['amount'], cost: ['spend'] }, mapping: { value: ['amount'] } })
    const check = vi.spyOn(templatesApi, 'match').mockResolvedValue(withOther)
    vi.spyOn(datasetsApi, 'list').mockResolvedValue([{ id: 7, name: 'rows' }, { id: 9, name: 'spending' }] as never)
    render(<MemoryRouter><UseTemplateDialog template={CARDS[0]} datasetId={7} onClose={() => {}} /></MemoryRouter>)
    const other = await screen.findByLabelText('Additional dataset: costs')
    expect(screen.queryByLabelText(/^cost/)).not.toBeInTheDocument()
    await waitFor(() => expect(within(other as HTMLElement).getByText('spending')).toBeInTheDocument())
    check.mockResolvedValue({ ...withOther, mapping: { value: ['amount'], cost: ['spend'] } })
    fireEvent.change(other, { target: { value: '9' } })
    await waitFor(() => expect(check).toHaveBeenLastCalledWith('builtin:overview', 7, undefined, { d2: 9 }))
    expect(await screen.findByLabelText(/^cost/)).toHaveValue('spend')
  })

  it('will not create while a required column is missing, and says which', async () => {
    vi.spyOn(templatesApi, 'match').mockResolvedValue(match({ mapping: {}, preview: null,
      check: { ok: false, problems: [{ slot: 'value', code: 'required_missing' }], missing: ['value'], widgets: { kept: 0, total: 8 }, dropped: [] } }))
    render(<MemoryRouter><UseTemplateDialog template={CARDS[0]} datasetId={7} onClose={() => {}} /></MemoryRouter>)
    await waitFor(() => expect(screen.getByText('Choose a column for “The number to follow”.')).toBeInTheDocument())
    expect(screen.getByRole('button', { name: 'Create dashboard' })).toBeDisabled()
  })
})
