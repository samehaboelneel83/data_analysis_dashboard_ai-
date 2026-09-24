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
