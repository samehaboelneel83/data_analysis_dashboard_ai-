import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import type { ReactNode } from 'react'
import { DirectionProvider } from '../../contexts/DirectionContext'
import { StepEditor } from './prepPipeline/StepEditor'
import PrepStepsPanel, { describeStep } from './PrepStepsPanel'
import OutlierDetailsDialog from './OutlierDetailsDialog'
import RelativeDateEditor from './RelativeDateEditor'
import DataViewsBar from './DataViewsBar'
import { en, ar } from '../../i18n/pages/panelsB'
import { translate, type TranslateFn } from '../../i18n'
import { outlierApi, prepApi, dataViewsApi } from '../../services/api'

vi.mock('../../services/api', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  outlierApi: { details: vi.fn() },
  prepApi: { get: vi.fn(), set: vi.fn(), preview: vi.fn(), joinCheck: vi.fn() },
  datasetsApi: { list: vi.fn(() => Promise.resolve([])), get: vi.fn() },
  dataViewsApi: { list: vi.fn(), save: vi.fn(), apply: vi.fn(), delete: vi.fn(), setDefault: vi.fn() },
}))

/** 8-i18n panelsB: the prep pipeline, the step list, the outlier dialog, the
 *  relative date editor and the data-view bar in Arabic. */
const inArabic = (ui: ReactNode) => render(<DirectionProvider>{ui}</DirectionProvider>)
const tAr: TranslateFn = (k, v) => translate('ar', k, v)

describe('panelsB in Arabic (8-i18n)', () => {
  beforeEach(() => { localStorage.setItem('datalytics.language', 'ar'); vi.clearAllMocks() })
  afterEach(() => localStorage.removeItem('datalytics.language'))

  it('holds the same keys in both languages, with the same placeholders', () => {
    expect(Object.keys(ar).sort()).toEqual(Object.keys(en).sort())
    const names = (s: string) => [...s.matchAll(/\{(\w+)[},]/g)].map(m => m[1]).sort().join()
    const bad = (Object.keys(en) as (keyof typeof en)[]).filter(k => names(en[k]) !== names(ar[k]))
    expect(bad).toEqual([])
  })

  it('the step editor labels an outlier step in Arabic and keeps the option values', () => {
    const cols = [{ name: 'amount', dtype: 'float' }] as never
    inArabic(<StepEditor step={{ kind: 'outliers', columns: [], method: 'iqr', k: 1.5, action: 'flag', name: '_Outlier_' }}
      columns={cols} otherDatasets={[]} onChange={() => {}} />)
    expect(screen.getByText('الأعمدة الرقمية')).toBeInTheDocument()
    const method = screen.getByRole('combobox', { name: 'طريقة كشف القيم الشاذة' }) as HTMLSelectElement
    expect(method.value).toBe('iqr')
    expect(screen.getByRole('option', { name: 'وسمها في عمود' })).toHaveValue('flag')
    expect(screen.getByLabelText('اسم عمود الوسم')).toHaveValue('_Outlier_')
    // The column name is data: shown as written, isolated.
    expect(screen.getByText('amount').tagName).toBe('BDI')
    expect(screen.queryByText(/Numeric columns|Threshold|flag in a column/)).toBeNull()
  })

  it('the step editor translates join choices but sends the code', () => {
    const onChange = vi.fn()
    inArabic(<StepEditor step={{ kind: 'join', dataset_id: null, how: 'left', left_on: '', right_on: '' }}
      columns={[]} otherDatasets={[]} onChange={onChange} />)
    expect(screen.getByRole('option', { name: 'يسار' })).toHaveValue('left')
    expect(screen.getByText('+ إضافة مفتاح')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('عمودهم')).toBeInTheDocument()
    fireEvent.change(screen.getByDisplayValue('يسار'), { target: { value: 'inner' } })
    expect(onChange).toHaveBeenCalledWith({ how: 'inner' })
  })

  it('a step reads as an Arabic sentence, names kept apart', () => {
    expect(describeStep({ kind: 'rename', column: 'a', to: 'b' }, tAr)).toBe('إعادة تسمية «⁨a⁩» ← «⁨b⁩»')
    expect(describeStep({ kind: 'edit_cells', column: 'region', key_column: 'id', edits: [{}, {}] } as never, tAr))
      .toBe('تصحيح خليتين في «⁨region⁩»، بالمطابقة على «⁨id⁩»')
    // English is unchanged without a translator.
    expect(describeStep({ kind: 'rename', column: 'a', to: 'b' })).toBe('Rename a → b')
  })

  it('the step list panel speaks Arabic', async () => {
    vi.mocked(prepApi.get).mockResolvedValue([{ kind: 'trim' }])
    inArabic(<PrepStepsPanel datasetId={1} columns={['region']} />)
    expect(await screen.findByText('حذف المسافات الزائدة (كل الأعمدة النصية)')).toBeInTheDocument()
    expect(screen.getByText('خطوات التحضير')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'حذف الخطوة ⁨1⁩' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '+ إضافة خطوة' }))
    expect(screen.getByRole('option', { name: 'إزالة الصفوف المكررة' })).toHaveValue('drop_duplicates')
  })

  it('the outlier dialog is titled and filled in Arabic', async () => {
    vi.mocked(outlierApi.details).mockResolvedValue({
      column: 'amount', detector: 'iqr',
      stats: { min: 10, q1: 10, median: 12, q3: 12, max: 1000, fence_low: 7, fence_high: 15 },
      outliers: { count: 1, total_rows: 21, columns: ['who', 'amount'], rows: [['r20', 1000]] },
      impact: { share_of_sum: 0.8197, mean_with: 58.1, mean_without: 11 },
    } as never)
    inArabic(<OutlierDetailsDialog datasetId={5} column="amount" onClose={() => {}} />)
    expect(screen.getByRole('dialog', { name: 'القيم الشاذة في «⁨amount⁩»' })).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText(/تقع خارج 1.5×IQR/)).toBeInTheDocument())
    expect(screen.getByText('الأثر')).toBeInTheDocument()
    expect(screen.getByText('صفوف القيم الشاذة')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'إغلاق' })).toBeInTheDocument()
    expect(screen.queryByText(/Impact|Outlier rows|fall beyond/)).toBeNull()
  })

  it('the relative date editor reuses the Builder presets and counts in Arabic', () => {
    inArabic(<RelativeDateEditor label="تصفية 1" value={{ mode: 'last', unit: 'day', n: 30, anchor: 'data_max' }} onChange={() => {}} />)
    expect(screen.getByText('آخر 30 يومًا · من آخر تاريخ في البيانات')).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'آخر 30 يومًا' })).toHaveValue('l30d')
    expect(screen.getByLabelText('تصفية 1: الفترة')).toBeInTheDocument()
  })

  it('the relative date editor says two months in the dual', () => {
    inArabic(<RelativeDateEditor label="ت" value={{ mode: 'last', unit: 'month', n: 2, anchor: 'today', include_current: true }} onChange={() => {}} />)
    expect(screen.getByText('آخر شهرين (مع الحالي) · من اليوم')).toBeInTheDocument()
    expect(screen.getByText('تضمين الشهر الحالي')).toBeInTheDocument()
  })

  it('the data-view bar speaks Arabic and quotes the name', async () => {
    vi.mocked(dataViewsApi.list).mockResolvedValue([] as never)
    vi.mocked(dataViewsApi.save).mockResolvedValue({ id: 9, name: 'Q2' } as never)
    inArabic(<DataViewsBar datasetId={7} />)
    fireEvent.click(await screen.findByRole('button', { name: 'حفظ الإعدادات كقالب…' }))
    fireEvent.change(screen.getByLabelText('اسم عرض البيانات'), { target: { value: 'Q2' } })
    fireEvent.click(screen.getByRole('button', { name: 'حفظ' }))
    await waitFor(() => expect(screen.getByTestId('dataview-status')).toHaveTextContent('حُفظ قالب الإعدادات «⁨Q2⁩»'))
  })
})
