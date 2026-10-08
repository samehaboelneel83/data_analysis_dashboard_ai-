import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import type { ReactNode } from 'react'
import { ConfirmProvider } from '../../components/ui/ConfirmDialog'
import { DirectionProvider } from '../../contexts/DirectionContext'
import AdminCustomConnectors from './AdminCustomConnectors'
import AdminMaps from './AdminMaps'
import AdminSso from './AdminSso'
import { ConnectionModal } from '../connections/ConnectionModal'

/**
 * QA5: F4 (the browser autofilled the admin's own login into a connector's
 * Username/Password), L6 (connector field labels in English), L7 (starter packs
 * in English, garbled in RTL) and the SSO provider line's period.
 */

vi.mock('../../services/api', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  customConnectorsApi: { list: vi.fn().mockResolvedValue([]), create: vi.fn(), update: vi.fn(), delete: vi.fn() },
  dataSourcesApi: { connectors: vi.fn(), testSettings: vi.fn(), create: vi.fn(), update: vi.fn(), test: vi.fn() },
  mapSettingsApi: { get: vi.fn().mockResolvedValue({ tile_url: null, attribution: null, contrast_tile_url: null }), set: vi.fn() },
  boundarySetsApi: { list: vi.fn().mockResolvedValue([]), packs: vi.fn(), installPack: vi.fn() },
  ssoApi: { getConfig: vi.fn().mockResolvedValue({ configured: false }), putConfig: vi.fn(), deleteConfig: vi.fn() },
}))
vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }))

import { dataSourcesApi, boundarySetsApi } from '../../services/api'

const field = (name: string, label: string, kind = 'text') =>
  ({ name, label, kind, required: name === 'host', default: null, placeholder: '', options: [], secret: kind === 'password', show_if: null })
const CATALOG = [{
  key: 'postgresql', label: 'PostgreSQL', icon: '', category: 'SQL', default_port: 5432,
  driver_installed: true, supports_directquery: true, is_custom: false,
  config_fields: [
    field('host', 'Host'), field('username', 'Username'), field('password', 'Password', 'password'),
    field('schema', 'Schema (optional)'), field('ssl_root_cert', 'CA certificate file on the server (verify modes)'),
    field('mystery', 'Mystery field'),
  ],
}]
vi.mocked(dataSourcesApi.connectors).mockResolvedValue(CATALOG as never)

const PACKS = [{
  id: 'egypt-governorates', name: 'Egypt governorates', feature_count: 27, country: 'EG', level: 'admin-1',
  description: 'All 27 governorates. Matches English (Cairo), transliterated (Al Qahirah), Arabic (القاهرة, with or without محافظة, with or without hamza), ISO 3166-2 (EG-C) and common spellings (Sharkia, Fayoum, Menoufia...).',
  source: 'Natural Earth', license: 'Public domain (Natural Earth terms of use)', license_url: null,
}, {
  id: 'unknown-pack', name: 'Atlantis districts', feature_count: 3, country: null, level: null,
  description: 'Server-only prose.', source: 'Somewhere', license: 'Some licence', license_url: null,
}]
vi.mocked(boundarySetsApi.packs).mockResolvedValue(PACKS as never)

const renderIn = (lang: 'en' | 'ar', ui: ReactNode) => {
  localStorage.setItem('datalytics.language', lang)
  return render(<DirectionProvider><ConfirmProvider>{ui}</ConfirmProvider></DirectionProvider>)
}
afterEach(() => { try { localStorage.removeItem('datalytics.language') } catch { /* jsdom */ } })

const expectNoAutofill = (dlg: HTMLElement) => {
  const inputs = [...dlg.querySelectorAll('input:not([type=checkbox])')] as HTMLInputElement[]
  expect(inputs.length).toBeGreaterThan(0)
  const ids = new Set<string>()
  for (const el of inputs) {
    expect(el.getAttribute('autocomplete'), el.outerHTML).toBe(el.type === 'password' ? 'new-password' : 'off')
    // Distinct from the login form's username/password, so no saved login matches.
    for (const attr of ['name', 'id'] as const) {
      const v = el.getAttribute(attr)
      expect(v, `${attr} on ${el.outerHTML}`).toBeTruthy()
      expect(['username', 'password', 'email']).not.toContain(v)
    }
    expect(ids.has(el.id)).toBe(false)
    ids.add(el.id)
  }
}

describe('QA5 F4: credential fields in admin forms are not autofilled', () => {
  it('the custom connector "new" dialog', async () => {
    renderIn('en', <AdminCustomConnectors />)
    fireEvent.click(await screen.findByRole('button', { name: 'New custom connector' }))
    const dlg = await screen.findByRole('dialog', { name: 'New custom connector' })
    expectNoAutofill(dlg)
    expect(dlg.querySelector('input[type=password]')?.getAttribute('name')).toBe('connector-password')
    expect(within(dlg).getByLabelText('Username').getAttribute('id')).toBe('connector-username')
  })

  it('the connection dialog', () => {
    renderIn('en', <ConnectionModal catalog={CATALOG as never} onSave={() => {}} onClose={() => {}} />)
    const dlg = screen.getByRole('dialog')
    expectNoAutofill(dlg)
    expect(dlg.querySelector('input[type=password]')?.getAttribute('name')).toBe('conn-password')
  })
})

describe('QA5 L6: connector field labels', () => {
  it('English shows the server labels as sent', async () => {
    renderIn('en', <AdminCustomConnectors />)
    fireEvent.click(await screen.findByRole('button', { name: 'New custom connector' }))
    const dlg = await screen.findByRole('dialog')
    for (const l of ['Host', 'Username', 'Password', 'Schema (optional)', 'CA certificate file on the server (verify modes)', 'Mystery field'])
      expect(within(dlg).getByText(l)).toBeInTheDocument()
  })

  it('Arabic translates known field keys and keeps the server text for unknown ones', async () => {
    renderIn('ar', <AdminCustomConnectors />)
    fireEvent.click(await screen.findByRole('button', { name: 'موصّل مخصص جديد' }))
    const dlg = await screen.findByRole('dialog')
    for (const l of ['المضيف', 'اسم المستخدم', 'كلمة المرور', 'المخطط (اختياري)']) expect(within(dlg).getByText(l)).toBeInTheDocument()
    expect(within(dlg).getByText('Mystery field')).toBeInTheDocument()
    expect(dlg.textContent).not.toMatch(/Host|Username|Password|Schema|CA certificate/)
  })

  it('the connection dialog in Arabic', () => {
    renderIn('ar', <ConnectionModal catalog={CATALOG as never} onSave={() => {}} onClose={() => {}} />)
    const dlg = screen.getByRole('dialog')
    expect(within(dlg).getByText('المضيف *')).toBeInTheDocument()
    expect(dlg.textContent).not.toMatch(/Username|Password/)
  })
})

describe('QA5 L7: starter packs', () => {
  it('English is unchanged', async () => {
    renderIn('en', <AdminMaps />)
    expect(await screen.findByText('Egypt governorates')).toBeInTheDocument()
    const li = screen.getByText('Egypt governorates').closest('li')!
    expect(li.textContent).toContain(`— 27 regions. ${PACKS[0].description} Source: Natural Earth; licence: Public domain (Natural Earth terms of use).`)
  })

  it('Arabic translates known packs; server text keeps its own direction', async () => {
    renderIn('ar', <AdminMaps />)
    expect(await screen.findByText('محافظات مصر')).toBeInTheDocument()
    const li = screen.getByText('محافظات مصر').closest('li')!
    expect(li.textContent).toContain('ملكية عامة (وفق شروط استخدام Natural Earth)')
    expect(li.textContent).not.toMatch(/Egypt governorates|All 27|Public domain/)
    // An unknown pack: the server's words, isolated with dir="auto".
    const desc = screen.getByText('Server-only prose.')
    expect(desc.getAttribute('dir')).toBe('auto')
    expect(screen.getByText('Some licence').getAttribute('dir')).toBe('auto')
    expect(screen.getByText('Atlantis districts')).toBeInTheDocument()
  })
})

describe('QA5: the SSO provider line', () => {
  it('English is unchanged; Arabic isolates the product list', async () => {
    const { unmount } = renderIn('en', <AdminSso />)
    const en = await screen.findByText('Azure AD / Entra, Okta, Google, Auth0, Keycloak')
    expect(en.parentElement!.textContent).toBe('Azure AD / Entra, Okta, Google, Auth0, Keycloak.')
    unmount()
    renderIn('ar', <AdminSso />)
    const list = await screen.findByText('Azure AD / Entra, Okta, Google, Auth0, Keycloak')
    expect(list.tagName).toBe('BDI')
    expect(list.getAttribute('dir')).toBe('ltr')
    expect(list.parentElement!.textContent).toBe('يعمل مع Azure AD / Entra, Okta, Google, Auth0, Keycloak وغيرها.')
  })
})
