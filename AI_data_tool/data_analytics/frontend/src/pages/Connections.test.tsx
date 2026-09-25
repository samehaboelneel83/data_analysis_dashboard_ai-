import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { renderWithProviders } from '../test/renderWithProviders'
import Connections, { SchemaBrowser } from './Connections'
import { dataSourcesApi, jobsApi } from '../services/api'
import { AuthContext } from '../contexts/AuthContext'
import type { ConnectorSpec, DataSource, Job } from '../services/api'

vi.mock('../services/api', async () => ({
  ...(await vi.importActual<Record<string, unknown>>('../services/api')),
  dataSourcesApi: {
    schema: vi.fn(),
    preview: vi.fn(),
    import: vi.fn(),
    queueImport: vi.fn(),
    connectors: vi.fn(),
    list: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    test: vi.fn(),
    testSettings: vi.fn(),
  },
  jobsApi: {
    list: vi.fn().mockResolvedValue([]),
    get: vi.fn(),
    cancel: vi.fn(),
    retry: vi.fn(),
  },
}))

const DS: DataSource = { id: 1, name: 'Live DB', type: 'postgresql', config: {}, created_at: '2026-01-01' }

function job(over: Partial<Job> = {}): Job {
  return {
    id: 77, kind: 'dataset.import', state: 'queued', subject: 'Live DB · sales → sales',
    progress: { stage: 'queued' }, result: null, error: null, error_code: null,
    attempt: 0, max_attempts: 3, cancel_requested: false, retry_of: null, created_by: 1,
    created_at: null, started_at: null, finished_at: null, updated_at: null, ...over,
  }
}

function renderBrowser() {
  return render(
    <MemoryRouter>
      <SchemaBrowser ds={DS} onClose={() => {}} />
    </MemoryRouter>
  )
}

describe('SchemaBrowser dataset-mode toggle', () => {
  it('queues an import as a durable job by default, with an idempotency key', async () => {
    vi.mocked(dataSourcesApi.schema).mockResolvedValue({ tables: [{ name: 'sales', kind: 'table' }] })
    vi.mocked(dataSourcesApi.preview).mockResolvedValue({ columns: ['region'], rows: [['east']], total: 1 })
    vi.mocked(dataSourcesApi.queueImport).mockResolvedValue(job({ state: 'queued' }))
    vi.mocked(jobsApi.get).mockResolvedValue(job({ state: 'queued' }))

    renderBrowser()
    fireEvent.click(await screen.findByText('sales'))
    await screen.findByText(/1 rows preview/)

    fireEvent.click(screen.getByText(/Import as Dataset/))

    await waitFor(() => expect(dataSourcesApi.queueImport).toHaveBeenCalledWith(
      1, { dataset_name: 'sales', table: 'sales', query: undefined }, expect.any(String)))
    // The request path is not used for an import any more.
    expect(dataSourcesApi.import).not.toHaveBeenCalled()
    // The dialog follows the job, and says it can be closed.
    expect(await screen.findByText('Waiting to start')).toBeInTheDocument()
    expect(screen.getByText(/You can close this window/)).toBeInTheDocument()
  })

  it('imports with mode "directquery" when the toggle is switched', async () => {
    vi.mocked(dataSourcesApi.schema).mockResolvedValue({ tables: [{ name: 'sales', kind: 'table' }] })
    vi.mocked(dataSourcesApi.preview).mockResolvedValue({ columns: ['region'], rows: [['east']], total: 1 })
    vi.mocked(dataSourcesApi.import).mockResolvedValue({ id: 1, name: 'sales', row_count: 0, col_count: 1, mode: 'directquery' })

    renderBrowser()
    fireEvent.click(await screen.findByText('sales'))
    await screen.findByText(/1 rows preview/)

    fireEvent.click(screen.getByText('DirectQuery'))
    fireEvent.click(screen.getByText(/Import as Dataset|Create DirectQuery Dataset/))

    await waitFor(() => expect(dataSourcesApi.import).toHaveBeenCalledWith(1, 'sales', 'sales', undefined, 'directquery'))
  })
})

describe('ConnectionModal custom preset resolution', () => {
  const BUILTIN: ConnectorSpec = {
    key: 'postgresql', label: 'PostgreSQL', icon: '🐘', category: 'Databases',
    default_port: 5432, driver_installed: true, supports_directquery: true, config_fields: [],
  }
  const CUSTOM: ConnectorSpec = {
    key: 'custom:7', label: 'Acme Postgres', icon: '🐘', category: 'Custom',
    default_port: 5432, driver_installed: true, supports_directquery: true,
    is_custom: true, base_type: 'postgresql', custom_connector_id: 7, config_fields: [],
  }

  function renderPage() {
    // "+ New Connection" is admin-only now: the API refuses connection
    // administration to anyone else, so the page no longer offers it. This test
    // is about preset resolution, not permissions, so it renders as an admin.
    const auth = {
      user: { id: 1, email: 'admin@x.y', role: { id: 1, name: 'Admin', is_org_admin: true } },
      login: vi.fn(), logout: vi.fn(), loading: false,
    }
    return renderWithProviders(
      <AuthContext.Provider value={auth as never}>
      <MemoryRouter>
        <Connections />
      </MemoryRouter>
      </AuthContext.Provider>
    )
  }

  it('saves a custom preset with its base_type and custom_connector_id, not the "custom:N" key', async () => {
    vi.mocked(dataSourcesApi.connectors).mockResolvedValue([BUILTIN, CUSTOM])
    vi.mocked(dataSourcesApi.list).mockResolvedValue([])
    vi.mocked(dataSourcesApi.create).mockResolvedValue({
      id: 99, name: 'My Custom Conn', type: 'postgresql', config: {}, created_at: '2026-01-01',
      custom_connector_id: 7, custom_connector_label: 'Acme Postgres',
    })

    renderPage()

    fireEvent.click(await screen.findByRole('button', { name: /New Connection/ }))

    const select = await screen.findByLabelText('Type') as HTMLSelectElement
    fireEvent.change(select, { target: { value: 'custom:7' } })

    fireEvent.change(screen.getByLabelText('Connection name *'), { target: { value: 'My Custom Conn' } })

    fireEvent.click(screen.getByRole('button', { name: 'Create connection' }))

    await waitFor(() => expect(dataSourcesApi.create).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'postgresql', custom_connector_id: 7 })
    ))
    const call = vi.mocked(dataSourcesApi.create).mock.calls[0][0]
    expect(call.type).not.toBe('custom:7')
    expect(call.custom_connector_id).not.toBeUndefined()
  })

  it('tests the settings in the form before anything is saved', async () => {
    vi.mocked(dataSourcesApi.create).mockClear()
    vi.mocked(dataSourcesApi.connectors).mockResolvedValue([BUILTIN, CUSTOM])
    vi.mocked(dataSourcesApi.list).mockResolvedValue([])
    vi.mocked(dataSourcesApi.testSettings).mockResolvedValue({ ok: false, error: 'password authentication failed for user "x"' })

    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: /New Connection/ }))
    fireEvent.click(await screen.findByRole('button', { name: 'Test connection' }))

    expect(await screen.findByRole('status')).toBeInTheDocument()
    expect(dataSourcesApi.testSettings).toHaveBeenCalledWith(expect.objectContaining({ type: 'postgresql', source_id: undefined }))
    expect(dataSourcesApi.create).not.toHaveBeenCalled()
  })
})
