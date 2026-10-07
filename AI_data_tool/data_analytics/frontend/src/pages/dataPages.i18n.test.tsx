import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import type { ReactElement } from 'react'
import { renderWithProviders } from '../test/renderWithProviders'
import { DirectionProvider } from '../contexts/DirectionContext'
import { AuthContext } from '../contexts/AuthContext'
import { dataSourcesApi, metadataApi, monitoringApi, type GlossaryTerm } from '../services/api'
import MonitoringActivity from './monitoring/MonitoringActivity'
import GlossaryPanel from '../components/review/GlossaryPanel'
import Connections from './Connections'
import toast from 'react-hot-toast'
import { en, ar } from '../i18n/pages/dataPages'

/**
 * 8-i18n, dataPages: the Arabic side of Connections, the glossary and the
 * Activity log. The English side is pinned by each page's own tests.
 */

vi.mock('react-hot-toast', () => {
  const t = Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), loading: vi.fn(), dismiss: vi.fn() })
  return { default: t, toast: t }
})

function inArabic(ui: ReactElement) {
  localStorage.setItem('datalytics.language', 'ar')
  return renderWithProviders(<DirectionProvider><MemoryRouter>{ui}</MemoryRouter></DirectionProvider>)
}

beforeEach(() => { vi.restoreAllMocks() })
afterEach(() => {
  vi.restoreAllMocks()
  localStorage.removeItem('datalytics.language')
  localStorage.removeItem('datalytics.direction')
})

describe('dataPages messages', () => {
  it('en and ar hold the same keys', () => {
    expect(Object.keys(ar).sort()).toEqual(Object.keys(en).sort())
  })
})

describe('Activity in Arabic', () => {
  it('names a known action code in Arabic and shows an unknown one raw, left-to-right', async () => {
    vi.spyOn(monitoringApi, 'activity').mockResolvedValue([
      { id: 1, user_email: 'a@b.com', action: 'report.create', entity: 'report',
        entity_id: 4, detail: null, created_at: '2026-09-01T10:00:00Z' },
      { id: 2, user_email: 'a@b.com', action: 'gizmo.frobnicate', entity: null,
        entity_id: null, detail: null, created_at: '2026-09-01T11:00:00Z' },
    ])
    inArabic(<MonitoringActivity />)
    const known = await screen.findByText('إنشاء لوحة')
    // The code stays reachable for an admin who knows it.
    expect(known).toHaveAttribute('title', 'report.create')
    expect(screen.queryByText('report.create')).toBeNull()
    const unknown = screen.getByText('gizmo.frobnicate')
    expect(unknown.tagName).toBe('BDI')
    expect(unknown).toHaveAttribute('dir', 'ltr')
  })
})

describe('Glossary in Arabic', () => {
  const TERMS: GlossaryTerm[] = [
    { id: 1, term: 'GMV', definition: 'Gross merchandise value.', synonyms: [],
      maps_to_object: null, maps_to_column: 'amount', data_source_id: null },
    { id: 2, term: 'paid order', definition: 'status = 2.', synonyms: [],
      maps_to_object: 'orders', maps_to_column: null, data_source_id: 3 },
  ]

  it('reads in Arabic, with the term name isolated in the delete label', async () => {
    vi.spyOn(metadataApi, 'glossary').mockResolvedValue(TERMS)
    inArabic(<GlossaryPanel sourceId={3} canEdit />)
    expect(await screen.findByText('مصطلحات الأعمال')).toBeInTheDocument()
    expect(screen.getByText('على مستوى المؤسسة')).toBeInTheDocument()
    expect(screen.getByLabelText('حذف «⁨paid order⁩»')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /إضافة مصطلح/ })).toBeInTheDocument()
    expect(screen.queryByText(/Business terms|Add a term/)).toBeNull()
  })

  it('says it is empty in Arabic', async () => {
    vi.spyOn(metadataApi, 'glossary').mockResolvedValue([])
    inArabic(<GlossaryPanel sourceId={3} canEdit={false} />)
    expect(await screen.findByText(/لا توجد مصطلحات بعد/)).toBeInTheDocument()
  })
})

describe('Connections in Arabic', () => {
  const auth = {
    user: { id: 1, email: 'admin@x.y', role: { id: 1, name: 'Admin', is_org_admin: true } },
    login: vi.fn(), logout: vi.fn(), loading: false,
  }

  it('translates the page actions, the test toast and the new-connection dialog', async () => {
    vi.spyOn(dataSourcesApi, 'list').mockResolvedValue([
      { id: 1, name: 'Live DB', type: 'postgresql', config: {}, created_at: '2026-01-01' },
    ])
    vi.spyOn(dataSourcesApi, 'connectors').mockResolvedValue([
      { key: 'postgresql', label: 'PostgreSQL', icon: '🐘', category: 'Databases',
        default_port: 5432, driver_installed: true, supports_directquery: true, config_fields: [] },
    ])
    vi.spyOn(dataSourcesApi, 'test').mockResolvedValue({ ok: true })
    inArabic(<AuthContext.Provider value={auth as never}><Connections /></AuthContext.Provider>)

    expect(await screen.findByRole('button', { name: 'دمج قواعد البيانات' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'اختبار' }))
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('«⁨Live DB⁩» — تم الاتصال'))

    fireEvent.click(screen.getByRole('button', { name: /اتصال جديد/ }))
    const dialog = await screen.findByRole('dialog', { name: 'اتصال جديد' })
    expect(dialog).toHaveTextContent('اسم الاتصال *')
    expect(screen.getByRole('button', { name: 'إنشاء الاتصال' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'اختبار الاتصال' })).toBeInTheDocument()
  })
})
