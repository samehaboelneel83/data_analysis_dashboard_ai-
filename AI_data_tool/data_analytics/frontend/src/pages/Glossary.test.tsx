import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import Glossary from './Glossary'
import { dataSourcesApi, datasetsApi, metadataApi } from '../services/api'

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
})
