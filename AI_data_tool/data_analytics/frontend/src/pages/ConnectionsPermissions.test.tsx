/* The Connections page must not offer what the server will refuse.
 *
 * Found by photographing every screen as every persona. A Guest — a role the
 * product presents as a read-only viewer — was shown the full row of actions on
 * every connection: Test, Query builder, Browse, Metadata, Edit, Delete, and a
 * "+ New Connection" button. The API is not fooled; it answers 403. But a button
 * that exists in order to be refused is worse than no button: the person cannot
 * tell whether they did something wrong, whether the product is broken, or
 * whether they were never allowed.
 *
 * `RequireAdmin` already does exactly this for whole routes, with a comment
 * saying it is a UX guard and the backend is the enforcement. This applies the
 * same idea inside a page a non-admin is legitimately allowed to open.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { renderWithProviders } from '../test/renderWithProviders'
import Connections from './Connections'
import { dataSourcesApi, datasetsApi } from '../services/api'
import { AuthContext } from '../contexts/AuthContext'

vi.mock('../services/api', async () => ({
  ...(await vi.importActual<Record<string, unknown>>('../services/api')),
  dataSourcesApi: {
    list: vi.fn(), connectors: vi.fn(), schema: vi.fn(), preview: vi.fn(),
    import: vi.fn(), create: vi.fn(), update: vi.fn(), delete: vi.fn(), test: vi.fn(),
  },
  datasetsApi: {
    combine: vi.fn(),
  },
}))

const SOURCES = [
  { id: 18, name: 'Moodle LMS (Egyptian University)', type: 'sqlite',
    config: {}, created_at: '2026-01-01' },
]

function renderAs(isAdmin: boolean) {
  const value = {
    user: { id: 1, email: 'x@y.z', role: { id: 1, name: 'Guest', is_org_admin: isAdmin } },
    login: vi.fn(), logout: vi.fn(), loading: false,
  }
  return renderWithProviders(
    <AuthContext.Provider value={value as never}>
      <MemoryRouter><Connections /></MemoryRouter>
    </AuthContext.Provider>)
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(dataSourcesApi.list).mockResolvedValue(SOURCES as never)
  vi.mocked(dataSourcesApi.connectors).mockResolvedValue({ connectors: [], presets: [] } as never)
})

describe('Connections, as a non-admin', () => {
  it('still shows the connections — reading them is allowed', async () => {
    renderAs(false)
    expect(await screen.findByText('Moodle LMS (Egyptian University)')).toBeInTheDocument()
  })

  it('does not offer to create a connection', async () => {
    renderAs(false)
    await screen.findByText('Moodle LMS (Egyptian University)')
    expect(screen.queryByRole('button', { name: /new connection/i })).toBeNull()
  })

  it.each(['Test', 'Browse', 'Query builder'])(
    'does not offer %s', async (label) => {
      renderAs(false)
      await screen.findByText('Moodle LMS (Egyptian University)')
      expect(screen.queryByRole('button', { name: new RegExp(label, 'i') })).toBeNull()
    })

  it('does not offer the row menu that holds Edit and Delete', async () => {
    /* Edit and Delete moved into the ⋯ menu, so `queryByRole('button', Edit)`
       now passes whether they are withheld or merely un-opened -- it would go
       green on a leak. The MENU is what must be absent, and with no trigger
       there is no way to reach either item. */
    renderAs(false)
    await screen.findByText('Moodle LMS (Egyptian University)')
    expect(screen.queryByRole('button', { name: /more actions/i })).toBeNull()
  })

  it('says why the actions are absent, rather than just hiding them', async () => {
    /* Silently removing controls leaves someone hunting for a button that used
       to be in the screenshot their colleague sent. One sentence prevents that. */
    renderAs(false)
    await screen.findByText('Moodle LMS (Egyptian University)')
    expect(screen.getByText(/administrator/i)).toBeInTheDocument()
  })
})

describe('Connections, as an admin', () => {
  it('offers everything', async () => {
    renderAs(true)
    await screen.findByText('Moodle LMS (Egyptian University)')
    expect(screen.getByRole('button', { name: /new connection/i })).toBeInTheDocument()
    for (const label of ['Test', 'Browse', 'Query builder']) {
      expect(screen.getByRole('button', { name: new RegExp(label, 'i') })).toBeInTheDocument()
    }
  })

  it('offers Metadata, Edit and Delete in the row menu', async () => {
    /* Same guarantee as before the restyle, one click deeper: these three are
       menu items now rather than a fourth, fifth and sixth ghost button. */
    renderAs(true)
    await screen.findByText('Moodle LMS (Egyptian University)')

    fireEvent.click(screen.getAllByRole('button', { name: /more actions/i })[0])
    for (const label of ['Metadata', 'Edit', 'Delete']) {
      expect(screen.getByRole('menuitem', { name: new RegExp(label, 'i') }))
        .toBeInTheDocument()
    }
  })

  it('shows no explanation banner', async () => {
    renderAs(true)
    await screen.findByText('Moodle LMS (Egyptian University)')
    expect(screen.queryByText(/administrator/i)).toBeNull()
  })
})

describe('combining tables from several databases', () => {
  const TWO = [...SOURCES, { id: 19, name: 'ERP (Alexandria)', type: 'sqlite', config: {}, created_at: '2026-01-01' }]

  it('is an admin action', async () => {
    renderAs(false)
    await screen.findByText('Moodle LMS (Egyptian University)')
    expect(screen.queryByRole('button', { name: 'Combine databases' })).toBeNull()
  })

  it('imports a table from each connection and appends them into one dataset', async () => {
    vi.mocked(dataSourcesApi.list).mockResolvedValue(TWO as never)
    vi.mocked(dataSourcesApi.schema).mockResolvedValue({ tables: [{ name: 'sales', kind: 'table' }] } as never)
    vi.mocked(datasetsApi.combine).mockResolvedValue({ id: 77, name: 'All branches' } as never)
    renderAs(true)
    fireEvent.click(await screen.findByRole('button', { name: 'Combine databases' }))
    const dialog = await screen.findByRole('dialog', { name: 'Combine databases' })
    expect(dialog).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('New dataset name'), { target: { value: 'All branches' } })
    for (const [i, id] of [[1, '18'], [2, '19']] as const) {
      fireEvent.change(screen.getByLabelText(`Connection ${i}`), { target: { value: id } })
      await waitFor(() => expect(screen.getByLabelText(`Table ${i}`)).toHaveTextContent('sales'))
      fireEvent.change(screen.getByLabelText(`Table ${i}`), { target: { value: 'sales' } })
    }
    fireEvent.change(screen.getByLabelText('Label 2'), { target: { value: 'Alex' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create dataset' }))
    await waitFor(() => expect(datasetsApi.combine).toHaveBeenCalledWith({
      name: 'All branches', how: 'append', on: [],
      sources: [{ data_source_id: 18, table: 'sales', label: undefined },
                { data_source_id: 19, table: 'sales', label: 'Alex' }],
    }))
  })
})

describe('Connections: a failed test says why, and keeps saying it (role tour, 2026-10-10)', () => {
  it('shows the reason on the row, not only in a toast that vanishes', async () => {
    vi.mocked(dataSourcesApi.test).mockResolvedValue({ ok: false,
      error: 'could not translate host name "qa-db.invalid" to address' } as never)
    renderAs(true)
    await screen.findByText('Moodle LMS (Egyptian University)')
    fireEvent.click(screen.getByRole('button', { name: 'Test' }))
    expect(await screen.findByTestId('conn-test-error'))
      .toHaveTextContent('could not translate host name "qa-db.invalid"')
  })
})
