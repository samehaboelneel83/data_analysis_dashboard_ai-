import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import type { ReactNode } from 'react'
import { DirectionProvider } from '../../contexts/DirectionContext'
import { ConfirmProvider } from '../ui/ConfirmDialog'
import MeasuresPanel from './MeasuresPanel'
import AccessDialog from './AccessDialog'
import AccessExplainer from './AccessExplainer'
import SubscribeButton from './SubscribeButton'
import CustomCategoryPanel from './CustomCategoryPanel'
import { suggestWidgets } from './SuggestionsPane'
import { measuresApi, pageVisibilityApi, reportCapabilityApi, subscriptionApi, widgetDataApi } from '../../services/api'
import type { DatasetColumn } from '../../services/api'
import { en, ar } from '../../i18n/pages/panelsA'
import { translate } from '../../i18n'

vi.mock('../../services/api', () => ({
  measuresApi: { list: vi.fn(), save: vi.fn(), delete: vi.fn(), preview: vi.fn(), restore: vi.fn() },
  pageVisibilityApi: { roles: vi.fn() },
  reportCapabilityApi: { get: vi.fn(), set: vi.fn() },
  subscriptionApi: { get: vi.fn(), subscribe: vi.fn(), unsubscribe: vi.fn() },
  widgetDataApi: { query: vi.fn() },
  calcColumnsApi: { save: vi.fn() },
}))
vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }))

/** 8-i18n panelsA: the dataset panels and report dialogs in Arabic. */
const inArabic = (ui: ReactNode) =>
  render(<DirectionProvider><ConfirmProvider>{ui}</ConfirmProvider></DirectionProvider>)

const columns: DatasetColumn[] = [
  { id: 1, name: 'region', dtype: 'categorical', missing_pct: 0, stats: {} },
  { id: 2, name: 'sales', dtype: 'numeric', missing_pct: 0, stats: {} },
]

describe('panelsA in Arabic (8-i18n)', () => {
  beforeEach(() => { vi.clearAllMocks(); localStorage.setItem('datalytics.language', 'ar') })
  afterEach(() => localStorage.removeItem('datalytics.language'))

  it('holds the same keys in both languages, with the same placeholders', () => {
    expect(Object.keys(ar).sort()).toEqual(Object.keys(en).sort())
    const names = (s: string) => [...s.matchAll(/\{(\w+)[},]/g)].map(m => m[1]).sort().join()
    const bad = (Object.keys(en) as (keyof typeof en)[]).filter(k => names(en[k]) !== names(ar[k]))
    expect(bad).toEqual([])
  })

  it('the Measures panel speaks Arabic; the measure and its formula stay as typed', async () => {
    vi.mocked(measuresApi.list).mockResolvedValue([
      { name: 'Margin', expression: 'SUM(profit) / SUM(sales) * 100' },
    ])
    inArabic(<MeasuresPanel datasetId={1} columns={columns} onChanged={vi.fn()} />)
    expect((await screen.findByText('Margin')).tagName).toBe('BDI')
    expect(screen.getByText('ƒx المقاييس')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '+ إضافة مقياس' })).toBeInTheDocument()
    expect(screen.getByText('SUM(profit) / SUM(sales) * 100')).toHaveAttribute('dir', 'ltr')
    expect(screen.queryByText(/Add measure|Evaluated after filters/)).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: 'حذف «⁨Margin⁩»' }))
    expect(await screen.findByText('حذف المقياس «⁨Margin⁩»؟')).toBeInTheDocument()
    expect(screen.getByText(/لا يمكن التراجع عن ذلك\./)).toBeInTheDocument()
  })

  it('the Measures editor and its palette are Arabic, the function names are not', async () => {
    vi.mocked(measuresApi.list).mockResolvedValue([])
    inArabic(<MeasuresPanel datasetId={1} columns={columns} onChanged={vi.fn()} />)
    expect(await screen.findByText('لا توجد مقاييس بعد')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '+ إضافة مقياس' }))
    // A new measure starts from the Arabic "What do you want to measure?" forms.
    expect(screen.getByText('ماذا تريد أن تقيس؟')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /الحصة من الإجمالي/ })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'سأكتب الصيغة بنفسي' }))
    expect(screen.getByPlaceholderText('اسم المقياس (مثلًا: نسبة المبيعات من الإجمالي)')).toBeInTheDocument()
    expect(screen.getByLabelText('التجميع حسب')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'حفظ' })).toBeInTheDocument()
    const sum = screen.getByRole('button', { name: 'SUM(col)' })
    expect(sum).toHaveAttribute('title', 'المجموع لكل مجموعة في العنصر المرئي الحالي')
  })

  it('the access dialog names the role apart from the sentence', async () => {
    vi.mocked(pageVisibilityApi.roles).mockResolvedValue([{ id: 7, name: 'HR managers' }])
    vi.mocked(reportCapabilityApi.get).mockResolvedValue({})
    inArabic(<AccessDialog reportId={1} onClose={() => {}} />)
    const sel = await screen.findByLabelText('مستوى الوصول لـ«⁨HR managers⁩»') as HTMLSelectElement
    expect(sel.selectedOptions[0].textContent).toBe('افتراضي — عرض بعد النشر')
    expect(screen.getByRole('dialog', { name: 'الوصول إلى التقرير' })).toBeInTheDocument()
    expect(screen.getByText('الوصول إلى التقرير حسب الدور')).toBeInTheDocument()
  })

  it('"Your access" translates the actions and keeps the rule as code', () => {
    inArabic(<AccessExplainer onClose={() => {}} sensitivity={{ effective: 'Restricted' }} decisions={[
      { resource: 'report', id: 1, action: 'view', allowed: true, reason: 'Shared with your role.' },
      { resource: 'report', id: 1, action: 'data_rules', allowed: true, reason: 'x',
        rules: [{ dataset_id: 3, dataset_name: 'Workforce', row_rule: "owner == 'a'", hidden_columns: [] }] },
    ] as never} />)
    expect(screen.getByRole('dialog', { name: 'وصولك' })).toBeInTheDocument()
    expect(screen.getByText('فتح هذا التقرير')).toBeInTheDocument()
    expect(screen.getByLabelText('مسموح')).toBeInTheDocument()
    const box = screen.getByTestId('access-data-rules')
    expect(box.textContent).toContain("الصفوف: فقط حيث owner == 'a'")
    expect(box.textContent).toContain('الأعمدة: كلها')
    expect(screen.getByTestId('access-sensitivity').textContent).toContain('لا روابط ضيوف ولا تضمين')
  })

  it('the subscribe dialog is Arabic, its choices included', async () => {
    vi.mocked(subscriptionApi.get).mockResolvedValue({ subscribed: false } as never)
    inArabic(<SubscribeButton reportId={1} />)
    fireEvent.click(await screen.findByRole('button', { name: 'اشتراك' }))
    const dialog = await screen.findByRole('dialog', { name: 'الاشتراك في هذا التقرير' })
    expect(within(dialog).getByText('أرسل لي هذا التقرير بالبريد')).toBeInTheDocument()
    const often = within(dialog).getByLabelText('كم مرة') as HTMLSelectElement
    expect([...often.options].map(o => o.textContent)).toEqual(['يوميًا', 'أسبوعيًا', 'شهريًا'])
    fireEvent.change(often, { target: { value: 'weekly' } })
    expect((within(dialog).getByLabelText('يوم الأسبوع') as HTMLSelectElement).options[0].textContent).toBe('الاثنين')
  })

  it('Group & Bin counts the values left over in Arabic plural forms; "Other" stays the group name', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({
      rows: [{ name: 'US', value: 6 }, { name: 'CA', value: 3 }, { name: 'UK', value: 1 }],
    } as never)
    inArabic(<CustomCategoryPanel datasetId={1} columns={columns} onSaved={vi.fn()} />)
    fireEvent.change(screen.getByLabelText('العمود المصدر'), { target: { value: 'region' } })
    fireEvent.change(await screen.findByLabelText('المجموعة لـ«⁨US⁩»'), { target: { value: 'NA' } })
    const status = screen.getByTestId('category-coverage').textContent ?? ''
    expect(status).toContain('60% من الصفوف تذهب إلى مجموعة مسمّاة')
    expect(status).toContain('(قيمتان) تذهب إلى «⁨Other⁩»: ⁨CA، UK⁩')
    expect(screen.getByRole('button', { name: 'إنشاء' })).toBeInTheDocument()
  })

  it('suggested titles read in Arabic, the column names kept apart', () => {
    const tr = (k: Parameters<typeof translate>[1], v?: Record<string, string | number>) => translate('ar', k, v)
    const titles = suggestWidgets(columns, null, 0, {}, tr).map(s => s.title)
    expect(titles).toContain('عدد الصفوف حسب ⁨region⁩')
    expect(titles).toContain('⁨sales⁩ حسب ⁨region⁩')
    // English unchanged when no translator is given
    expect(suggestWidgets(columns, null, 0).map(s => s.title)).toContain('Number of rows by region')
  })
})
