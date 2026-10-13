import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent, within, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { renderWithProviders } from '../../test/renderWithProviders'
import Connections from '../Connections'
import { dataSourcesApi, datasetsApi, metadataApi } from '../../services/api'
import { AuthContext } from '../../contexts/AuthContext'
import type { ConnectorSpec, DataSource } from '../../services/api'

vi.mock('../../services/api', async () => ({
  ...(await vi.importActual<Record<string, unknown>>('../../services/api')),
  dataSourcesApi: { connectors: vi.fn(), list: vi.fn(), create: vi.fn(), update: vi.fn(), delete: vi.fn(), test: vi.fn(), testSettings: vi.fn() },
  datasetsApi: { list: vi.fn() },
  metadataApi: { latestSync: vi.fn() },
  jobsApi: { list: vi.fn().mockResolvedValue([]) },
  setupApi: { journeys: vi.fn().mockResolvedValue([]) },
}))

/** Autopilot step 7, Part A: the Connections list and the new-connection drawer. */

const PG: ConnectorSpec = { key: 'postgresql', label: 'PostgreSQL', icon: '', category: 'SQL', default_port: 5432, driver_installed: true, supports_directquery: true,
  config_fields: [{ name: 'host', label: 'Host', kind: 'text', required: true }] } as never
const LITE: ConnectorSpec = { ...PG, key: 'sqlite', label: 'SQLite', default_port: null, config_fields: [{ name: 'path', label: 'Path', kind: 'text', required: true }] } as never
const SOURCES: DataSource[] = [
  { id: 1, name: 'Warehouse', type: 'postgresql', config: { host: 'db.internal', database: 'sales' }, created_at: '2026-01-01' },
  { id: 2, name: 'Local file', type: 'sqlite', config: { path: '/data/demo_live.sqlite' }, created_at: '2026-01-01' },
]
const admin = { user: { id: 1, email: 'a@x.y', role: { id: 1, name: 'Admin', is_org_admin: true } }, login: vi.fn(), logout: vi.fn(), loading: false }
const page = () => renderWithProviders(<AuthContext.Provider value={admin as never}><MemoryRouter><Connections /></MemoryRouter></AuthContext.Provider>)
const row = (name: string) => screen.getByRole('link', { name }).closest('[role="row"]') as HTMLElement

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(dataSourcesApi.connectors).mockResolvedValue([PG, LITE])
  vi.mocked(dataSourcesApi.list).mockResolvedValue(structuredClone(SOURCES))
  vi.mocked(datasetsApi.list).mockResolvedValue([{ id: 9, data_source_id: 1 }, { id: 10, data_source_id: 1 }, { id: 11, data_source_id: null }] as never)
  vi.mocked(metadataApi.latestSync).mockImplementation(async (id: number) => (id === 1
    ? { status: 'ok', stages: [], finished_at: new Date(Date.now() - 2 * 3600_000).toISOString() }
    : { status: 'failed', stages: [], error: 'file not found', finished_at: new Date(Date.now() - 60_000).toISOString() }) as never)
})

describe('the list', () => {
  it('shows each connection with its type and place, its last sync, and the datasets that read from it', async () => {
    page()
    await screen.findByRole('link', { name: 'Warehouse' })
    await waitFor(() => expect(within(row('Warehouse')).getByText('Synced')).toBeInTheDocument())
    const wh = row('Warehouse')
    expect(wh).toHaveTextContent('PostgreSQL · db.internal/sales')
    expect(wh).toHaveTextContent('2 hours ago')
    expect(within(wh).getAllByRole('cell')[3]).toHaveTextContent('2')
    const lf = row('Local file')
    expect(lf).toHaveTextContent('Sync failed')
    expect(lf).toHaveTextContent('file not found')
    expect(lf).toHaveTextContent('demo_live.sqlite')
    expect(screen.getByText('2 connections')).toBeInTheDocument()
  })

  it('a failed test says so on the row, with Fix opening the connection to edit', async () => {
    vi.mocked(dataSourcesApi.test).mockResolvedValue({ ok: false, error: 'could not translate host name' } as never)
    page()
    await screen.findByRole('link', { name: 'Warehouse' })
    fireEvent.click(screen.getByRole('button', { name: 'Test Warehouse' }))
    await waitFor(() => expect(within(row('Warehouse')).getByText('Failing')).toBeInTheDocument())
    expect(within(row('Warehouse')).getByTestId('conn-test-error')).toHaveTextContent('could not translate host name')
    fireEvent.click(within(row('Warehouse')).getByRole('button', { name: 'Fix' }))
    expect(screen.getByRole('dialog', { name: 'Edit connection · Warehouse' })).toBeInTheDocument()
  })

  it('searches and filters by type', async () => {
    page()
    await screen.findByRole('link', { name: 'Warehouse' })
    fireEvent.change(screen.getByRole('searchbox', { name: 'Search connections' }), { target: { value: 'local' } })
    expect(screen.queryByRole('link', { name: 'Warehouse' })).toBeNull()
    fireEvent.change(screen.getByRole('searchbox', { name: 'Search connections' }), { target: { value: '' } })
    fireEvent.click(screen.getByRole('button', { name: 'Type' }))
    fireEvent.click(screen.getByRole('menuitemradio', { name: 'PostgreSQL' }))
    expect(screen.queryByRole('link', { name: 'Local file' })).toBeNull()
    expect(screen.getByText('1 connection')).toBeInTheDocument()
  })

  it('Open goes to the review page; the guided setup stays on every row', async () => {
    page()
    await screen.findByRole('link', { name: 'Warehouse' })
    expect(within(row('Warehouse')).getByRole('link', { name: 'Open Warehouse' })).toHaveAttribute('href', '/connections/1/review')
    expect(within(row('Warehouse')).getByRole('link', { name: /Guided setup/ })).toHaveAttribute('href', '/setup/1')
  })

  it('says how to start when there is nothing yet', async () => {
    vi.mocked(dataSourcesApi.list).mockResolvedValue([])
    page()
    expect(await screen.findByRole('heading', { name: 'Connect your first database' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Upload a file/ })).toHaveAttribute('href', '/upload')
  })
})

describe('the new-connection drawer', () => {
  it('starts with the type, searchable, then the details for that type', async () => {
    page()
    await screen.findByRole('link', { name: 'Warehouse' })
    fireEvent.click(screen.getByRole('button', { name: 'New Connection' }))
    const dlg = await screen.findByRole('dialog', { name: 'New connection' })
    expect(within(dlg).getAllByRole('radio').map(r => r.textContent)).toEqual(['PostgreSQL:5432', 'SQLite'])
    fireEvent.change(within(dlg).getByRole('textbox', { name: 'Search database types' }), { target: { value: 'lite' } })
    expect(within(dlg).getAllByRole('radio')).toHaveLength(1)
    fireEvent.click(within(dlg).getByRole('radio', { name: /SQLite/ }))
    fireEvent.click(within(dlg).getByRole('button', { name: 'Next' }))
    expect(within(dlg).getByText('SQLite', { selector: 'b' })).toBeInTheDocument()
    expect(within(dlg).getByText('Path *')).toBeInTheDocument()
    fireEvent.click(within(dlg).getByRole('button', { name: /Choose type/ }))
    expect(within(dlg).getByRole('radio', { name: /SQLite/ })).toHaveAttribute('aria-checked', 'true')
  })
})
