import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import GlossaryPanel from './GlossaryPanel'
import { metadataApi, type GlossaryTerm } from '../../services/api'

/**
 * The three glossary endpoints shipped with the retrieval work and had NO caller
 * until this panel existed — so the table the agent and the dashboard designer
 * both read could only ever be empty, and a model asked about "GMV" had to guess
 * which column that was.
 *
 * These tests pin the caller: that it reads, that it writes, and that it does not
 * offer a control the endpoint would refuse.
 */

const TERMS: GlossaryTerm[] = [
  { id: 1, term: 'GMV', definition: 'Gross merchandise value.',
    synonyms: ['إجمالي المبيعات'], maps_to_object: null,
    maps_to_column: 'amount', data_source_id: null },
  { id: 2, term: 'paid order', definition: 'status = 2.', synonyms: [],
    maps_to_object: 'orders', maps_to_column: null, data_source_id: 3 },
]

beforeEach(() => {
  vi.restoreAllMocks()
  vi.spyOn(metadataApi, 'glossary').mockResolvedValue(TERMS)
})

// The spies above live on a SHARED module object, and vitest reuses the module
// registry across files in a worker. `restoreAllMocks` in beforeEach protects
// only this file's own tests -- without this afterEach the last test's spies
// stay installed for every file that runs after it. That is exactly how this
// suite has broken an unrelated page before.
afterEach(() => { vi.restoreAllMocks() })

describe('GlossaryPanel', () => {
  it('shows the terms the source and the organisation have defined', async () => {
    render(<GlossaryPanel sourceId={3} canEdit />)
    expect(await screen.findByText('GMV')).toBeInTheDocument()
    expect(screen.getByText('paid order')).toBeInTheDocument()
    expect(screen.getByText('إجمالي المبيعات')).toBeInTheDocument()
  })

  it('marks an organisation-wide term, because it applies beyond this connection', async () => {
    render(<GlossaryPanel sourceId={3} canEdit />)
    expect(await screen.findByText('organisation-wide')).toBeInTheDocument()
  })

  it('offers no delete for an organisation-wide term — the endpoint refuses it', async () => {
    /* A dead control is the defect this codebase's capability map exists to
       prevent: a button that always fails teaches people the feature is broken. */
    render(<GlossaryPanel sourceId={3} canEdit />)
    await screen.findByText('GMV')
    expect(screen.queryByLabelText('Delete GMV')).toBeNull()
    expect(screen.getByLabelText('Delete paid order')).toBeInTheDocument()
  })

  it('a member reads the vocabulary but is offered no way to change it', async () => {
    render(<GlossaryPanel sourceId={3} canEdit={false} />)
    expect(await screen.findByText('GMV')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Add a term/ })).toBeNull()
    expect(screen.queryByLabelText('Delete paid order')).toBeNull()
  })

  it('adds a term with its aliases split on commas', async () => {
    const add = vi.spyOn(metadataApi, 'addTerm')
      .mockResolvedValue({ ...TERMS[1], id: 9 })
    render(<GlossaryPanel sourceId={3} canEdit />)
    fireEvent.click(await screen.findByRole('button', { name: /Add a term/ }))

    fireEvent.change(screen.getByPlaceholderText('GMV'), { target: { value: 'churn' } })
    fireEvent.change(screen.getByPlaceholderText(/Gross merchandise value/),
                     { target: { value: 'left in the last 90 days' } })
    fireEvent.change(screen.getByPlaceholderText(/gross sales/),
                     { target: { value: 'attrition,  lapsed ' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(add).toHaveBeenCalledWith(3, expect.objectContaining({
      term: 'churn',
      definition: 'left in the last 90 days',
      synonyms: ['attrition', 'lapsed'],
    })))
  })

  it('says what to do when there is nothing yet, rather than showing a blank box', async () => {
    vi.spyOn(metadataApi, 'glossary').mockResolvedValue([])
    render(<GlossaryPanel sourceId={3} canEdit />)
    expect(await screen.findByText(/No terms yet/)).toBeInTheDocument()
  })

  it('a failed load explains itself and offers a retry', async () => {
    vi.spyOn(metadataApi, 'glossary').mockRejectedValue(new Error('nope'))
    render(<GlossaryPanel sourceId={3} canEdit />)
    /* A persistent banner, never a toast: a toast fades and leaves the reader
       with an empty panel and no way back. */
    expect(await screen.findByRole('button', { name: /retry|try again/i })).toBeInTheDocument()
  })
})
