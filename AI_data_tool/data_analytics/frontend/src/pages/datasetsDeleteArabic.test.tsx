import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Dashboard from './Dashboard'
import { datasetsApi } from '../services/api'
import { ConfirmProvider } from '../components/ui/ConfirmDialog'
import { DirectionProvider } from '../contexts/DirectionContext'
import { translate } from '../i18n'

/**
 * QA4 T6: the dataset delete dialog on the Datasets page spoke English in the
 * Arabic UI, and its punctuation landed on the wrong side
 * (`?Delete "Student cohorts (test)"`). It is a full Arabic sentence now, the
 * name isolated inside «» so a Latin name stays whole and ؟ ends the sentence.
 */

vi.mock('../services/api', () => ({
  pinsApi: { create: vi.fn(), list: vi.fn().mockResolvedValue([]), remove: vi.fn(), update: vi.fn() },
  datasetsApi: { list: vi.fn(), delete: vi.fn() },
  demoApi: { seed: vi.fn(), unseed: vi.fn() },
  insightsApi: { run: vi.fn(), runShared: vi.fn().mockResolvedValue({ findings: [], narrative: '' }) },
  narrateApi: { one: vi.fn().mockResolvedValue(null) },
  findingKey: (f: { kind: string; columns: string[] }) => [f.kind, ...[...f.columns].sort()].join('|'),
  clearWidgetDataClientCache: vi.fn(),
}))
vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }))
vi.mock('./datasetsList/DatasetPreview', () => ({ default: () => <aside data-testid="dataset-preview" /> }))

const NAME = 'Student cohorts (test)'
const ISOLATED = `⁨${NAME}⁩`

const renderPage = () => render(
  <DirectionProvider>
    <ConfirmProvider><MemoryRouter><Dashboard /></MemoryRouter></ConfirmProvider>
  </DirectionProvider>,
)

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(datasetsApi.list).mockResolvedValue([
    { id: 7, name: NAME, row_count: 10, col_count: 5, file_size: 283, created_at: '2026-08-22T00:00:00Z' },
  ] as never)
  vi.mocked(datasetsApi.delete).mockResolvedValue(undefined as never)
})
afterEach(() => { try { localStorage.removeItem('datalytics.language') } catch { /* jsdom */ } })

describe('the Datasets page delete, in Arabic (QA4 T6)', () => {
  it('names the row menu in Arabic, with the name isolated', async () => {
    localStorage.setItem('datalytics.language', 'ar')
    renderPage()
    expect(await screen.findByRole('button', { name: `إجراءات أخرى لمجموعة البيانات «${ISOLATED}»` })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /More actions/ })).toBeNull()
  })

  it('asks in Arabic: the title ends in ؟ after the isolated name, the body ends in a full stop', async () => {
    localStorage.setItem('datalytics.language', 'ar')
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: `إجراءات أخرى لمجموعة البيانات «${ISOLATED}»` }))
    fireEvent.click(screen.getByRole('menuitem', { name: translate('ar', 'datasets.delete') }))

    const dlg = await screen.findByRole('alertdialog')
    expect(dlg).toHaveAttribute('aria-label', `حذف «${ISOLATED}»؟`)
    expect(within(dlg).getByText(`حذف «${ISOLATED}»؟`)).toBeInTheDocument()
    expect(within(dlg).getByText('لا يمكن التراجع عن ذلك.')).toBeInTheDocument()
    expect(dlg.textContent).not.toMatch(/Delete|cannot be undone/)

    fireEvent.click(within(dlg).getByRole('button', { name: translate('ar', 'bc.shell.c.delete') }))
    await waitFor(() => expect(datasetsApi.delete).toHaveBeenCalledWith(7))
  })

  it('keeps the English text byte for byte', async () => {
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: `More actions for dataset ${NAME}` }))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Delete dataset' }))
    const dlg = await screen.findByRole('alertdialog')
    expect(dlg).toHaveAttribute('aria-label', `Delete "${NAME}"?`)
    expect(within(dlg).getByText('This cannot be undone.')).toBeInTheDocument()
  })
})

describe('the other delete / move confirmations (QA4 T6)', () => {
  it('Connections and Dashboards: Arabic isolates the names, English is unchanged', () => {
    const v = { name: 'Q1 Sales', to: 'Finance' }
    expect(translate('ar', 'bc.dialogs.deleteDashboard', v)).toBe('حذف اللوحة «⁨Q1 Sales⁩»؟')
    expect(translate('ar', 'bc.dialogs.deleteFolder', v)).toBe('حذف المجلد «⁨Q1 Sales⁩»؟')
    expect(translate('ar', 'bc.dialogs.moveDashboard', v)).toBe('نقل «⁨Q1 Sales⁩» إلى ⁨Finance⁩؟')
    expect(translate('en', 'bc.dialogs.deleteDashboard', v)).toBe(translate('en', 'dsh.deleteTitle', v))
    expect(translate('en', 'bc.dialogs.deleteFolder', v)).toBe(translate('en', 'dsh.folderDeleteTitle', v))
    expect(translate('en', 'bc.dialogs.moveDashboard', v)).toBe(translate('en', 'dsh.move.confirmTitle', v))
    expect(translate('en', 'bc.dialogs.deleteNamed', v)).toBe('Delete "Q1 Sales"?')
    expect(translate('en', 'bc.dialogs.cannotUndo')).toBe('This cannot be undone.')
  })
})
