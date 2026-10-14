import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import toast from 'react-hot-toast'
import ReportBuilder from '../ReportBuilder'
import ShortcutsDialog from './ShortcutsDialog'
import { reportsApi, datasetsApi } from '../../services/api'
import { PromptProvider } from '../../components/ui/PromptDialog'
import { ConfirmProvider } from '../../components/ui/ConfirmDialog'
import { translate } from '../../i18n'
import { DirectionProvider } from '../../contexts/DirectionContext'

/**
 * QA3 Batch C: the builder's shell in Arabic -- the delete-page question as
 * one sentence with the name in «», the empty page pointing at the side the
 * fields panel is really on, toasts as whole templates, and the shortcuts
 * sheet's "Click".
 */
vi.mock('react-hot-toast', () => {
  const t = Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), loading: vi.fn(), dismiss: vi.fn() })
  return { default: t, toast: t, Toaster: () => null }
})

vi.mock('../../services/api', () => ({
  // SubscribeButton sits in the always-visible header, so this page
  // renders it for every test here -- an unmocked call crashes them all.
  subscriptionApi: { get: vi.fn().mockResolvedValue({ subscribed: false }),
                     subscribe: vi.fn(), unsubscribe: vi.fn() },
  // Phase 7.3: the header asks what this user may do (share, download...).
  authzApi: { decisions: vi.fn().mockResolvedValue([]) },
  reportsApi: {
    get: vi.fn(), list: vi.fn().mockResolvedValue([]), update: vi.fn(), addPage: vi.fn(), updatePage: vi.fn(), deletePage: vi.fn(), versions: vi.fn().mockResolvedValue([]),
    addWidget: vi.fn(), updateWidget: vi.fn(), deleteWidget: vi.fn(),
    listBookmarks: vi.fn().mockResolvedValue([]), addBookmark: vi.fn(), deleteBookmark: vi.fn(),
    getRevision: vi.fn().mockResolvedValue(0),
    getClassification: vi.fn().mockResolvedValue({ label: null, options: [] }),
    setClassification: vi.fn(),
    addCommonFilter: vi.fn(), deleteCommonFilter: vi.fn(),
  },
  datasetsApi: { get: vi.fn(), list: vi.fn() },
  dataSourcesApi: { list: vi.fn().mockResolvedValue([]) },
  hierarchyApi: { get: vi.fn().mockResolvedValue([]), autoGenerate: vi.fn().mockResolvedValue([]), reorder: vi.fn() },
  analysisApi: { get: vi.fn().mockResolvedValue(null), run: vi.fn() },
  calcColumnsApi: { list: vi.fn().mockResolvedValue([]), save: vi.fn(), delete: vi.fn(), preview: vi.fn() },
  measuresApi: { list: vi.fn().mockResolvedValue([]), save: vi.fn(), delete: vi.fn(), preview: vi.fn() },
  customFunctionsApi: { list: vi.fn().mockResolvedValue([]), save: vi.fn(), delete: vi.fn(), preview: vi.fn() },
  columnFormatsApi: { get: vi.fn().mockResolvedValue({}), set: vi.fn() },
  dataPreviewApi: { query: vi.fn().mockResolvedValue({ columns: [], rows: [], total: 0 }) },
  prepApi: { get: vi.fn().mockResolvedValue([]), set: vi.fn(), preview: vi.fn() },
  dataViewsApi: { list: vi.fn().mockResolvedValue([]), save: vi.fn(), apply: vi.fn(), delete: vi.fn() },
  columnMetaApi: { get: vi.fn(), set: vi.fn() },
  // The field list's geography classification lists the org's uploaded
  // boundary sets. This mock is exhaustive: a missing export fails every
  // test in the file with a mock error rather than an import error.
  boundarySetsApi: { list: vi.fn().mockResolvedValue([]), get: vi.fn(), create: vi.fn(), remove: vi.fn() },
  translationsApi: { list: vi.fn().mockResolvedValue({}), save: vi.fn() },
  relationshipsApi: { list: vi.fn().mockResolvedValue([]), create: vi.fn(), delete: vi.fn() },
  widgetDataApi: { query: vi.fn().mockResolvedValue({ rows: [], sampled: false }) },
  themesApi: { list: vi.fn().mockResolvedValue([]), create: vi.fn(), delete: vi.fn() },
  parametersApi: { list: vi.fn().mockResolvedValue([]), save: vi.fn() },
  pageTemplatesApi: { builtins: vi.fn().mockResolvedValue([]), list: vi.fn().mockResolvedValue([]), saveFrom: vi.fn(), addFrom: vi.fn(), delete: vi.fn() },
  pageVisibilityApi: { roles: vi.fn().mockResolvedValue([]), get: vi.fn().mockResolvedValue({ role_ids: [] }), set: vi.fn() },
  schedulesApi: { list: vi.fn().mockResolvedValue([]), create: vi.fn(), delete: vi.fn(), runNow: vi.fn() },
  deliveriesApi: { list: vi.fn().mockResolvedValue([]) },
  // View mode (7d) reads the top bar's model light, as Ask AI does.
  lastLlmEndpoints: () => null,
  getLlmChoice: () => null,
  LLM_ENDPOINTS_EVENT: 'datalytics:llm-endpoints',
  LLM_CHOICE_EVENT: 'datalytics:llm-choice',
  // The Share dialog (7c) reads grants, guest links and embed configs.
  reportGrantsApi: { list: vi.fn().mockResolvedValue([]), create: vi.fn(), remove: vi.fn() },
  shareLinksApi: { list: vi.fn().mockResolvedValue([]), create: vi.fn(), revoke: vi.fn() },
  embedConfigsApi: { list: vi.fn().mockResolvedValue([]), create: vi.fn(), setEnabled: vi.fn(), delete: vi.fn() },
  COMMON_TIMEZONES: ['UTC', 'Asia/Riyadh'],
  widgetTemplatesApi: { list: vi.fn().mockResolvedValue([]), create: vi.fn(), delete: vi.fn() },
  columnsApi: { duplicate: vi.fn() },
}))

const ar = (k: Parameters<typeof translate>[1], v?: Record<string, string | number>) => translate('ar', k, v)

function report() {
  return {
    id: 1, name: 'Sales', dataset_id: 10, additional_dataset_ids: [], created_at: '2026-01-01', updated_at: '2026-01-01',
    my_capability: 'data',
    pages: [
      { id: 100, report_id: 1, name: 'Page 1', page_type: 'normal', position: 0, widgets: [], created_at: '2026-01-01', layout_mode: 'free' },
      { id: 101, report_id: 1, name: 'QA3 صفحة', page_type: 'normal', position: 1, widgets: [], created_at: '2026-01-01', layout_mode: 'free' },
    ],
  }
}

function renderBuilder() {
  return render(
    <DirectionProvider><ConfirmProvider><PromptProvider>
      <MemoryRouter initialEntries={['/reports/1?edit=1']}>
        <Routes><Route path="/reports/:id" element={<ReportBuilder />} /></Routes>
      </MemoryRouter>
    </PromptProvider></ConfirmProvider></DirectionProvider>
  )
}

describe('the builder shell in Arabic (QA3 Batch C)', () => {
  beforeEach(() => {
    localStorage.setItem('datalytics.language', 'ar'); localStorage.setItem('datalytics.direction', 'rtl')
    vi.mocked(reportsApi.get).mockResolvedValue(report() as any)
    vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales Data', columns: [] } as any)
  })
  afterEach(() => { localStorage.removeItem('datalytics.language'); localStorage.removeItem('datalytics.direction') })

  it('asks before deleting a page in one Arabic sentence, the name in «»', async () => {
    renderBuilder()
    fireEvent.click(await screen.findByRole('button', { name: ar('bd.pg.menu', { name: 'QA3 صفحة' }) }))
    fireEvent.click(screen.getByRole('menuitem', { name: ar('bd.pg.delete') }))
    const dialog = await screen.findByRole('alertdialog').catch(() => screen.findByRole('dialog'))
    // the name is isolated (FSI…PDI) so a mixed-direction name stays whole
    expect(within(dialog).getByText('حذف الصفحة «\u2068QA3 صفحة\u2069»؟')).toBeInTheDocument()
    expect(within(dialog).getByRole('button', { name: 'حذف' })).toBeInTheDocument()
    expect(within(dialog).getByText('ستُحذف عناصرها معها.')).toBeInTheDocument()
    expect(dialog.textContent).not.toMatch(/Delete page/)
  })

  it('an empty page points at the fields panel on the right', async () => {
    renderBuilder()
    const empty = await screen.findByTestId('empty-page')
    expect(empty.textContent).toContain('من اللوحة اليمنى')
    expect(empty.textContent).not.toMatch(/left panel|اليسرى/)
    expect(within(empty).getByText('حقلًا').tagName).toBe('B')
  })

  it('a new page is announced in Arabic', async () => {
    vi.mocked(reportsApi.addPage).mockResolvedValue({ id: 102, report_id: 1, name: 'Page 3', position: 2, widgets: [] } as any)
    renderBuilder()
    fireEvent.click(await screen.findByRole('button', { name: ar('bd.pg.add') }))
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('أُضيفت صفحة'))
  })

  it('a widget added is one template with its name in «»', () => {
    expect(ar('bc.shell.t.added', { name: 'أعمدة' })).toBe('أُضيف «أعمدة»')
    expect(translate('en', 'bc.shell.t.added', { name: 'Bar' })).toBe('Bar added')
  })

  it('the shortcuts sheet says "Click" in Arabic', () => {
    render(<DirectionProvider><ShortcutsDialog onClose={() => {}} /></DirectionProvider>)
    const kbds = Array.from(document.querySelectorAll('kbd')).map(k => k.textContent)
    expect(kbds).toContain('نقرة')
    expect(kbds).not.toContain('Click')
    expect(kbds).toContain('Shift')
  })
})
