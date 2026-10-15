import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import ColumnTermsPanel from './ColumnTermsPanel'
import { metadataApi, type GlossaryTerm } from '../../services/api'

/** B-21: the Columns tab shows the business term a column stands for, links
 *  to it in the glossary, and lets an admin link a term to a column. */
const TERMS: GlossaryTerm[] = [
  { id: 7, term: 'Revenue', definition: 'What was sold', synonyms: ['turnover'], maps_to_object: null,
    maps_to_column: 'amount', data_source_id: null, dataset_id: 5 },
  { id: 1, term: 'GMV', definition: null, synonyms: [], maps_to_object: null,
    maps_to_column: null, data_source_id: null },
]

beforeEach(() => { vi.restoreAllMocks() })
afterEach(() => { vi.restoreAllMocks() })

const at = (ui: React.ReactElement) => render(<MemoryRouter>{ui}</MemoryRouter>)

describe('ColumnTermsPanel', () => {
  it('shows each linked column with its term, linked to the glossary', async () => {
    vi.spyOn(metadataApi, 'datasetGlossary').mockResolvedValue(TERMS)
    at(<ColumnTermsPanel datasetId={5} columns={['amount', 'region']} canEdit={false} />)
    const link = await screen.findByRole('link', { name: 'Revenue' })
    expect(link.getAttribute('href')).toBe('/glossary?dataset=5#term-7')
    expect(screen.getByText('amount')).toBeInTheDocument()
    // A term that names no column of this dataset is not a column's term.
    expect(screen.queryByRole('link', { name: 'GMV' })).toBeNull()
    // A member is offered no way to add one.
    expect(screen.queryByRole('link', { name: /Link a business term/ })).toBeNull()
  })

  it('offers an admin a link per column that opens the glossary on that column', async () => {
    vi.spyOn(metadataApi, 'datasetGlossary').mockResolvedValue([])
    at(<ColumnTermsPanel datasetId={5} columns={['amount', 'region']} canEdit />)
    expect(await screen.findByText('No column is linked to a business term yet.')).toBeInTheDocument()
    const add = screen.getByRole('link', { name: 'Link a business term to region' })
    expect(add.getAttribute('href')).toBe('/glossary?dataset=5&column=region')
  })

  it('says nothing when the glossary cannot be read', async () => {
    vi.spyOn(metadataApi, 'datasetGlossary').mockRejectedValue(new Error('404'))
    const { container } = at(<ColumnTermsPanel datasetId={5} columns={['amount']} canEdit />)
    await new Promise(r => setTimeout(r, 0))
    expect(container.textContent).toBe('')
  })
})
