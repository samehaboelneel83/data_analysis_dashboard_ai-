import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import AdminCustomConnectors from './AdminCustomConnectors'
import { customConnectorsApi, dataSourcesApi } from '../../services/api'
import { ConfirmProvider } from '../../components/ui/ConfirmDialog'

vi.mock('../../services/api', () => ({
  customConnectorsApi: {
    list: vi.fn(), create: vi.fn(), update: vi.fn(), delete: vi.fn(),
  },
  dataSourcesApi: { connectors: vi.fn() },
}))

const BASE_CATALOG = [{
  key: 'postgresql', label: 'PostgreSQL', icon: '🐘', category: 'SQL',
  default_port: 5432, driver_installed: true, supports_directquery: true,
  config_fields: [
    { name: 'host', label: 'Host', kind: 'text', required: true, default: null, placeholder: '', options: [], secret: false, show_if: null },
    { name: 'port', label: 'Port', kind: 'number', required: false, default: 5432, placeholder: '', options: [], secret: false, show_if: null },
  ],
}]

function renderPage() {
  return render(<ConfirmProvider><AdminCustomConnectors /></ConfirmProvider>)
}

describe('AdminCustomConnectors', () => {
  beforeEach(() => {
    vi.mocked(dataSourcesApi.connectors).mockResolvedValue(BASE_CATALOG as any)
  })

  it('lists existing presets', async () => {
    vi.mocked(customConnectorsApi.list).mockResolvedValue([
      { id: 1, key: 'acme-pg', label: 'Acme Postgres', base_type: 'postgresql',
        base_config: { host: '***REDACTED***' }, locked_fields: ['host'], created_at: '2026-01-01' },
    ])

    renderPage()

    expect(await screen.findByText('Acme Postgres')).toBeInTheDocument()
  })

  it('shows an empty state when there are no presets', async () => {
    vi.mocked(customConnectorsApi.list).mockResolvedValue([])

    renderPage()

    expect(await screen.findByText(/no custom connectors/i)).toBeInTheDocument()
  })

  it('deletes a preset after confirming', async () => {
    vi.mocked(customConnectorsApi.list).mockResolvedValue([
      { id: 1, key: 'acme-pg', label: 'Acme Postgres', base_type: 'postgresql',
        base_config: {}, locked_fields: [], created_at: '2026-01-01' },
    ])
    vi.mocked(customConnectorsApi.delete).mockResolvedValue(undefined as any)

    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: /delete/i }))
    // ConfirmDialog's own confirm button defaults to "Delete" too (see
    // ConfirmDialog.tsx's `confirmLabel ?? 'Delete'`) -- findAllByRole avoids
    // ambiguity between the row's button and the dialog's once both exist.
    const deleteButtons = await screen.findAllByRole('button', { name: /delete/i })
    fireEvent.click(deleteButtons[deleteButtons.length - 1])

    await waitFor(() => expect(customConnectorsApi.delete).toHaveBeenCalledWith(1))
  })
})

describe('AdminCustomConnectors — fields typed by kind (QA E-11)', () => {
  const CATALOG = [{
    ...BASE_CATALOG[0],
    config_fields: [
      ...BASE_CATALOG[0].config_fields,
      { name: 'ssl_mode', label: 'TLS', kind: 'select', required: false, default: 'default', placeholder: '',
        options: ['default', 'disable', 'require', 'verify-ca', 'verify-full'], secret: false, show_if: null },
    ],
  }]

  it('renders TLS as a select of its modes and Port as a number', async () => {
    vi.mocked(dataSourcesApi.connectors).mockResolvedValue(CATALOG as any)
    vi.mocked(customConnectorsApi.list).mockResolvedValue([])
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: /New custom connector/ }))
    const tls = document.getElementById('connector-ssl_mode') as HTMLSelectElement
    expect(tls.tagName).toBe('SELECT')
    expect(Array.from(tls.options).map(o => o.value)).toEqual(['', 'default', 'disable', 'require', 'verify-ca', 'verify-full'])
    const port = document.getElementById('connector-port') as HTMLInputElement
    expect(port).toHaveAttribute('type', 'number')
  })

  it('sends a typed port as a number', async () => {
    vi.mocked(dataSourcesApi.connectors).mockResolvedValue(CATALOG as any)
    vi.mocked(customConnectorsApi.list).mockResolvedValue([])
    vi.mocked(customConnectorsApi.create).mockResolvedValue({ id: 3, key: 'k', label: 'L', base_type: 'postgresql',
      base_config: {}, locked_fields: [], created_at: '' } as any)
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: /New custom connector/ }))
    fireEvent.change(document.getElementById('connector-label')!, { target: { value: 'L' } })
    fireEvent.change(document.getElementById('connector-key')!, { target: { value: 'k' } })
    fireEvent.change(document.getElementById('connector-port')!, { target: { value: '6543' } })
    fireEvent.change(document.getElementById('connector-ssl_mode')!, { target: { value: 'require' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create' }))
    await waitFor(() => expect(customConnectorsApi.create).toHaveBeenCalledWith(expect.objectContaining({
      base_config: { port: 6543, ssl_mode: 'require' } })))
  })

  it('says "1 locked field" and "2 locked fields"', async () => {
    vi.mocked(customConnectorsApi.list).mockResolvedValue([
      { id: 1, key: 'a', label: 'One', base_type: 'postgresql', base_config: {}, locked_fields: ['host'], created_at: '' },
      { id: 2, key: 'b', label: 'Two', base_type: 'postgresql', base_config: {}, locked_fields: ['host', 'port'], created_at: '' },
    ] as any)
    renderPage()
    expect(await screen.findByText(/1 locked field$/)).toBeInTheDocument()
    expect(screen.getByText(/2 locked fields$/)).toBeInTheDocument()
  })
})
