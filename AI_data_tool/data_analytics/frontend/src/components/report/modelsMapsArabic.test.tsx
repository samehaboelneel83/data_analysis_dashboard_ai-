import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import type { ReactNode } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { DirectionProvider } from '../../contexts/DirectionContext'
import PredictionModelsPanel from '../dataset/PredictionModelsPanel'
import MapLayersEditor, { type MapLayerCfg } from './MapLayersEditor'
import MapPinsEditor from './MapPinsEditor'
import GraphLayersEditor from './GraphLayersEditor'
import { en, ar } from '../../i18n/pages/modelsMaps'
import { predictionModelsApi } from '../../services/api'

import { ConfirmProvider } from '../ui/ConfirmDialog'
vi.mock('../../services/api', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  predictionModelsApi: {
    list: vi.fn(), train: vi.fn(), score: vi.fn(), remove: vi.fn(), promote: vi.fn(), scoreJob: vi.fn(),
    checkDrift: vi.fn(), driftHistory: vi.fn().mockResolvedValue([]),
  },
  boundarySetsApi: { list: vi.fn().mockResolvedValue([]), get: vi.fn(), create: vi.fn(), remove: vi.fn() },
}))

/** 8-i18n: the Models tab and the map / graph editors in Arabic. */
const inArabic = (ui: ReactNode) => render(<DirectionProvider><ConfirmProvider><MemoryRouter>{ui}</MemoryRouter></ConfirmProvider></DirectionProvider>)

const columns = [
  { id: 1, name: 'region', dtype: 'categorical', missing_pct: 0, stats: {} },
  { id: 2, name: 'spend', dtype: 'numeric', missing_pct: 0, stats: {} },
  { id: 3, name: 'churn', dtype: 'categorical', missing_pct: 0, stats: {} },
] as never

const card = {
  target: 'churn', task: 'classification', model_family: 'random forest', score: 0.91,
  score_name: 'accuracy', candidates: [{ model: 'random forest', score: 0.91 }, { model: 'logistic regression', score: 0.84 }],
  baseline_score: 0.55, beats_baseline: false, predictors_used: ['region', 'spend'], predictors_skipped: [],
  n_train: 225, n_test: 75, n_fitted: 300, split: { kind: 'random', test_share: 0.25 },
  row_scope: 'every row', caveats: [], trained_by: 'ana@example.com', trained_at: '2026-09-20T10:00:00',
  dataset: { id: 1, name: 'Churn', row_count: 300, content_sha256: null, last_refreshed_at: null },
}
const model = {
  id: 7, name: 'Churn model', dataset_id: 1, target: 'churn', features: ['region', 'spend'],
  task: 'classification', model_family: 'random forest', score: 0.91, score_name: 'accuracy',
  created_at: '2026-09-11T00:00:00Z', version: 1, status: 'champion', card,
}

describe('models and maps in Arabic (8-i18n)', () => {
  beforeEach(() => localStorage.setItem('datalytics.language', 'ar'))
  afterEach(() => localStorage.removeItem('datalytics.language'))

  it('holds the same keys in both languages, with the same placeholders', () => {
    expect(Object.keys(ar).sort()).toEqual(Object.keys(en).sort())
    // A plural's branches ("one {it}") are words, not placeholders.
    const names = (s: string) => [...new Set([...s.replace(/\b(zero|one|two|few|many|other)\s*\{[^{}]*\}/g, '')
      .matchAll(/\{(\w+)[},]/g)].map(m => m[1]))].sort().join()
    const bad = (Object.keys(en) as (keyof typeof en)[]).filter(k => names(en[k]) !== names(ar[k]))
    expect(bad).toEqual([])
  })

  it('the Models tab names the approach in Arabic, not as the server code', async () => {
    vi.mocked(predictionModelsApi.list).mockResolvedValue([model] as never)
    inArabic(<PredictionModelsPanel datasetId={1} columns={columns} />)
    const m = await screen.findByTestId('model-7')
    expect(m).toHaveTextContent('الغابة العشوائية')
    expect(m).toHaveTextContent('الانحدار اللوجستي')
    expect(m).not.toHaveTextContent('random forest')
    expect(m).not.toHaveTextContent('logistic regression')
    // The model's own name is the author's and stays as written.
    expect(within(m).getByRole('heading', { name: 'Churn model' })).toBeInTheDocument()
    expect(within(m).getByRole('button', { name: 'حذف «⁨Churn model⁩»' })).toBeInTheDocument()
  })

  it('the model card reads in Arabic, with the names and numbers kept apart', async () => {
    vi.mocked(predictionModelsApi.list).mockResolvedValue([model] as never)
    inArabic(<PredictionModelsPanel datasetId={1} columns={columns} />)
    fireEvent.click(await screen.findByRole('button', { name: /بطاقة|Model card/ }))
    const c = screen.getByTestId('model-card')
    expect(c).toHaveTextContent('درّبه ana@example.com')
    expect(c).toHaveTextContent('كل الصفوف')
    expect(c).toHaveTextContent('لا يتفوق على هذا التخمين.')
    expect(screen.getByText('ana@example.com').tagName).toBe('BDI')
    expect(screen.getByText('0.550').closest('bdi')?.getAttribute('dir')).toBe('ltr')
    expect(c).not.toHaveTextContent(/Trained by|Chosen on|held-out|Predictors:/)
    expect(screen.getByText(/^حُفظ هذا الإصدار قبل أن تُحفظ ملفات التدريب/)).toBeInTheDocument()
  })

  it('the map layers editor is in Arabic, the column names as they are', () => {
    const layers: MapLayerCfg[] = [{ id: 'a', kind: 'regions' }, { id: 'b', kind: 'lines' }]
    inArabic(<MapLayersEditor value={layers} onChange={() => {}} columns={columns} />)
    expect(screen.getByText('الطبقات')).toBeInTheDocument()
    expect(screen.getByText('(الأدنى أولًا)')).toBeInTheDocument()
    expect(screen.getByLabelText('الطبقة 1: المنطقة')).toBeInTheDocument()
    expect(screen.getByLabelText('حدود الطبقة 1')).toBeInTheDocument()
    expect(screen.getByLabelText('الطبقة 2: خط عرض البداية')).toBeInTheDocument()
    expect(screen.getAllByRole('option', { name: 'خطوط (من ← إلى)' })).toHaveLength(2)
    expect(screen.getAllByRole('option', { name: 'الدول (مدمجة)' }).length).toBeGreaterThan(0)
    expect(screen.getAllByRole('option', { name: 'region' }).length).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: 'إزالة الطبقة 2' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '+ إضافة طبقة' })).toBeInTheDocument()
    expect(document.body.textContent).not.toMatch(/Layers|Region|Boundaries|Add layer|select column/)
  })

  it('an empty layer stack explains itself in Arabic', () => {
    inArabic(<MapLayersEditor value={[]} onChange={() => {}} columns={columns} />)
    expect(screen.getByText(/^لا توجد طبقات بعد/)).toBeInTheDocument()
  })

  it('a pin with a bad latitude says so in Arabic', () => {
    inArabic(<MapPinsEditor value={[{ label: 'Depot', lat: '95', lon: '2' }]} onChange={() => {}} />)
    expect(screen.getByLabelText('خط العرض لـ «⁨Depot⁩»')).toBeInTheDocument()
    expect(screen.getByText(/^يجب أن يكون خط العرض بين/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'إضافة دبوس' })).toBeInTheDocument()
  })

  it('the graph layers editor translates the marks and aggregations, not the values sent', () => {
    const onChange = vi.fn()
    inArabic(<GraphLayersEditor value={[{ measure: 'spend', mark: 'bar', aggregation: 'sum', axis: 'left' }]}
      columns={columns} onChange={onChange} />)
    const agg = screen.getByLabelText('التجميع لـ «⁨spend⁩»') as HTMLSelectElement
    expect([...agg.options].map(o => o.textContent)).toContain('المتوسط')
    fireEvent.change(agg, { target: { value: 'avg' } })
    expect(onChange.mock.calls[0][0][0].aggregation).toBe('avg')
    expect(screen.getByRole('option', { name: 'أعمدة' })).toBeInTheDocument()
  })
})
