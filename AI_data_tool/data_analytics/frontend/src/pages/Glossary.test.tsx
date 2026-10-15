import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import Glossary from './Glossary'
import { dataSourcesApi, datasetsApi, metadataApi, type GlossaryTerm } from '../services/api'
import { AuthContext } from '../contexts/AuthContext'

/** B-21: an uploaded dataset has no connection, so the glossary page offers
 *  datasets too, and opens on the dataset (and column) a link names. */
beforeEach(() => {
  vi.restoreAllMocks()
  try { localStorage.clear() } catch { /* */ }
  vi.spyOn(dataSourcesApi, 'list').mockResolvedValue([{ id: 3, name: 'Warehouse' }] as never)
  vi.spyOn(datasetsApi, 'list').mockResolvedValue([{ id: 5, name: 'Demo — Sales', columns: [] }] as never)
  vi.spyOn(metadataApi, 'glossary').mockResolvedValue([])
})
afterEach(() => { vi.restoreAllMocks() })

describe('Glossary page', () => {
  it('works with no connection at all: a dataset can hold the terms', async () => {
    vi.spyOn(dataSourcesApi, 'list').mockResolvedValue([])
    const read = vi.spyOn(metadataApi, 'datasetGlossary').mockResolvedValue([])
    render(<MemoryRouter initialEntries={['/glossary']}><Glossary /></MemoryRouter>)
    await waitFor(() => expect(read).toHaveBeenCalledWith(5))
    expect(screen.getByRole('option', { name: 'Demo — Sales' })).toBeInTheDocument()
  })

  it('opens on the dataset a link names', async () => {
    const read = vi.spyOn(metadataApi, 'datasetGlossary').mockResolvedValue([])
    render(<MemoryRouter initialEntries={['/glossary?dataset=5']}><Glossary /></MemoryRouter>)
    await waitFor(() => expect(read).toHaveBeenCalledWith(5))
    expect((screen.getByLabelText('Connection or dataset') as HTMLSelectElement).value).toBe('d:5')
  })

  /* B-21 step 1: org-wide terms (no connection, no dataset) apply to every
     connection and dataset; the page now writes them too. */
  const GMV: GlossaryTerm = { id: 11, term: 'GMV', definition: 'Gross merchandise value', synonyms: ['turnover'],
    maps_to_object: null, maps_to_column: null, data_source_id: null, dataset_id: null }
  const as = (admin: boolean) => ({ user: { role: { is_org_admin: admin } } }) as unknown as React.ContextType<typeof AuthContext>
  const openOrgWide = async (admin: boolean) => {
    render(<MemoryRouter initialEntries={['/glossary']}><AuthContext.Provider value={as(admin)}>
      <Glossary /></AuthContext.Provider></MemoryRouter>)
    const select = await screen.findByLabelText('Connection or dataset') as HTMLSelectElement
    fireEvent.change(select, { target: { value: 'o' } })
    return select
  }

  it('offers "All data (org-wide)" first, before every connection and dataset', async () => {
    render(<MemoryRouter initialEntries={['/glossary']}><Glossary /></MemoryRouter>)
    const select = await screen.findByLabelText('Connection or dataset') as HTMLSelectElement
    expect(select.options[0].textContent).toBe('All data (org-wide)')
    expect(select.options[0].value).toBe('o')
    expect(Array.from(select.options).map(o => o.textContent)).toEqual(['All data (org-wide)', 'Warehouse', 'Demo — Sales'])
  })

  it('an admin adds, edits and deletes org-wide terms through the org-wide API', async () => {
    const read = vi.spyOn(metadataApi, 'orgGlossary').mockResolvedValue([GMV])
    const add = vi.spyOn(metadataApi, 'addOrgTerm').mockResolvedValue({ ...GMV, id: 12, term: 'ARR' })
    const update = vi.spyOn(metadataApi, 'updateOrgTerm').mockResolvedValue({ ...GMV, rule: 'amount > 0' })
    const remove = vi.spyOn(metadataApi, 'deleteOrgTerm').mockResolvedValue({} as never)
    const scoped = vi.spyOn(metadataApi, 'addTerm')
    const select = await openOrgWide(true)
    expect(await screen.findByText('GMV')).toBeInTheDocument()
    expect(read).toHaveBeenCalled()
    expect(select.value).toBe('o')
    // Every term here is org-wide: no "organisation-wide" badge on each row.
    expect(screen.queryByText('organisation-wide')).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: /Add a term/ }))
    fireEvent.change(screen.getByPlaceholderText('GMV'), { target: { value: 'ARR' } })
    fireEvent.change(screen.getByPlaceholderText(/gross sales/), { target: { value: 'annual run rate, ' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(add).toHaveBeenCalledWith(expect.objectContaining({
      term: 'ARR', synonyms: ['annual run rate'] })))
    expect(scoped).not.toHaveBeenCalled()

    const rule = screen.getByLabelText('Rule for GMV')
    fireEvent.change(rule, { target: { value: 'amount > 0' } })
    fireEvent.blur(rule)
    await waitFor(() => expect(update).toHaveBeenCalledWith(11, { rule: 'amount > 0' }))
    fireEvent.click(screen.getByLabelText('Delete GMV'))
    await waitFor(() => expect(remove).toHaveBeenCalledWith(11))
  })

  it('a member reads the org-wide terms but cannot change them', async () => {
    vi.spyOn(metadataApi, 'orgGlossary').mockResolvedValue([{ ...GMV, rule: 'amount > 0' }])
    await openOrgWide(false)
    expect(await screen.findByText('GMV')).toBeInTheDocument()
    expect(screen.getByText('amount > 0')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Add a term/ })).toBeNull()
    expect(screen.queryByLabelText('Delete GMV')).toBeNull()
    expect(screen.queryByLabelText('Rule for GMV')).toBeNull()
    expect((screen.getByLabelText('Always apply GMV') as HTMLInputElement).disabled).toBe(true)
  })
})
