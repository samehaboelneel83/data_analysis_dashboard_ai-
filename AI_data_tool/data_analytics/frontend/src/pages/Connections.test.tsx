import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { renderWithProviders } from '../test/renderWithProviders'
import Connections, { SchemaBrowser } from './Connections'
import { dataSourcesApi } from '../services/api'
import { AuthContext } from '../contexts/AuthContext'
import type { ConnectorSpec, DataSource } from '../services/api'

vi.mock('../services/api', async () => ({
  ...(await vi.importActual<Record<string, unknown>>('../services/api')),
  dataSourcesApi: {
    schema: vi.fn(),
    preview: vi.fn(),
    import: vi.fn(),
    connectors: vi.fn(),
    list: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    test: vi.fn(),
  },
}))

const DS: DataSource = { id: 1, name: 'Live DB', type: 'postgresql', config: {}, created_at: '2026-01-01' }

function renderBrowser() {
  return render(
    <MemoryRouter>
      <SchemaBrowser ds={DS} onClose={() => {}} />
    </MemoryRouter>
  )
}

describe('SchemaBrowser dataset-mode toggle', () => {
  it('imports with mode "import" by default', async () => {
    vi.mocked(dataSourcesApi.schema).mockResolvedValue({ tables: [{ name: 'sales', kind: 'table' }] })
    vi.mocked(dataSourcesApi.preview).mockResolvedValue({ columns: ['region'], rows: [['east']], total: 1 })
    vi.mocked(dataSourcesApi.import).mockResolvedValue({ id: 1, name: 'sales', row_count: 1, col_count: 1, mode: 'import' })

    renderBrowser()
    fireEvent.click(await screen.findByText('sales'))
    await screen.findByText(/1 rows preview/)

    fireEvent.click(screen.getByText(/Import as Dataset/))

    await waitFor(() => expect(dataSourcesApi.import).toHaveBeenCalledWith(1, 'sales', 'sales', undefined, 'import'))
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

    fireEvent.change(screen.getByLabelText('Connection Name *'), { target: { value: 'My Custom Conn' } })

    fireEvent.click(screen.getByRole('button', { name: 'Create' }))

    await waitFor(() => expect(dataSourcesApi.create).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'postgresql', custom_connector_id: 7 })
    ))
    const call = vi.mocked(dataSourcesApi.create).mock.calls[0][0]
    expect(call.type).not.toBe('custom:7')
    expect(call.custom_connector_id).not.toBeUndefined()
  })
})
