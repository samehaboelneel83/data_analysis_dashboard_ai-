import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'
import { DirectionProvider } from '../../contexts/DirectionContext'
import { WidgetPlaceholder } from './WidgetPlaceholder'
import { AssignDataDialog, AddFieldDialog } from './DataRolesList'
import { DifferenceDialog, WhyDialog, describeFilter } from './ViewerKit'
import InteractionSettings from './InteractionSettings'
import { CrossFilterProvider } from './CrossFilterContext'
import { roleLabel } from './panelLabels'
import { en, ar } from '../../i18n/builder/canvas'
import { translate } from '../../i18n'

vi.mock('../../services/api', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  differenceApi: { check: vi.fn(() => new Promise(() => {})) },
}))

/** QA3 Batch C: the canvas, the Assign data dialog and the ⋮ pop-ups in Arabic. */
const inArabic = (ui: ReactNode) => render(<DirectionProvider>{ui}</DirectionProvider>)

describe('the canvas in Arabic (QA3 Batch C)', () => {
  beforeEach(() => localStorage.setItem('datalytics.language', 'ar'))
  afterEach(() => localStorage.removeItem('datalytics.language'))

  it('holds the same keys in both languages, with the same placeholders', () => {
    expect(Object.keys(ar).sort()).toEqual(Object.keys(en).sort())
    const names = (s: string) => [...s.matchAll(/\{(\w+)[},]/g)].map(m => m[1]).sort().join()
    // "تصفية واحدة" says the 1 in words, so the count is not needed.
    const inWords = new Set(['bc.canvas.chipFilters1'])
    const bad = (Object.keys(en) as (keyof typeof en)[]).filter(k => !inWords.has(k) && names(en[k]) !== names(ar[k]))
    expect(bad).toEqual([])
  })

  it('the placeholder names the missing role in Arabic, and the sentence ends in Arabic', () => {
    inArabic(<WidgetPlaceholder widget={{ widget_type: 'bar' }} missing={['Dimension']} onAssignData={() => {}} />)
    expect(screen.getByText('يحتاج إلى: البُعد')).toBeInTheDocument()
    expect(screen.getByText('عيّنة')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'إسناد البيانات' })).toBeInTheDocument()
    expect(screen.queryByText(/Needs|Sample|Assign data/)).toBeNull()
  })

  it('a reader sees the unfinished note in Arabic', () => {
    inArabic(<WidgetPlaceholder widget={{ widget_type: 'bar' }} missing={['Measure']} />)
    expect(screen.getByText('لم يُكمل المؤلف هذا العنصر بعد.')).toBeInTheDocument()
  })

  it('the Assign data dialog is titled in Arabic, the widget name kept apart', () => {
    inArabic(<AssignDataDialog objectName="Revenue by region" onClose={() => {}}><span /></AssignDataDialog>)
    expect(screen.getByRole('dialog', { name: 'إسناد البيانات: «Revenue by region»' })).toBeInTheDocument()
    expect(screen.getByText('Revenue by region').tagName).toBe('BDI')
    expect(screen.getByRole('button', { name: 'تم' })).toBeInTheDocument()
  })

  it('the Add field dialog translates the role and the field groups, not the fields', () => {
    inArabic(<AddFieldDialog heading="Measure" multi choices={[{ value: 'sales', label: 'sales', group: 'Numbers' }]}
      selected={[]} onApply={() => {}} onClose={() => {}} />)
    expect(screen.getByRole('dialog', { name: 'إضافة المقياس' })).toBeInTheDocument()
    expect(screen.getByText('الأرقام')).toBeInTheDocument()
    expect(screen.getByText('sales')).toBeInTheDocument()
  })

  it('the ⋮ pop-ups are titled in Arabic, with the Arabic question mark', () => {
    inArabic(<WhyDialog title="Sales" sections={[]} onClose={() => {}} />)
    expect(screen.getByRole('dialog', { name: 'لماذا أرى هذا؟ — Sales' })).toBeInTheDocument()
  })

  it('the difference check is titled in Arabic', () => {
    inArabic(<DifferenceDialog datasetId={1} dimension="region" measure="sales" aggregation="sum" filters={[]}
      names={['A', 'B']} initial={['A', 'B']} onClose={() => {}} />)
    expect(screen.getByRole('dialog', { name: 'هل هذا الفرق حقيقي؟' })).toBeInTheDocument()
  })

  it('the Interactions section is Arabic', () => {
    inArabic(<CrossFilterProvider>
      <InteractionSettings widget={{ id: 1, page_id: 1, widget_type: 'bar', title: 'A', config: {}, layout: { x: 0, y: 0, w: 4, h: 4 } } as never} />
    </CrossFilterProvider>)
    expect(screen.getByText('وضع التفاعل')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'معزول —' })).toBeInTheDocument()
  })
})

describe('role labels and filter sentences', () => {
  it('translates a full role label half by half, and leaves English alone', () => {
    expect(roleLabel('ar', 'Dimension (Group / X-axis)')).toBe('البُعد (المجموعة / المحور السيني)')
    expect(roleLabel('en', 'Dimension (Group / X-axis)')).toBe('Dimension (Group / X-axis)')
  })

  it('a filter reads the same in English with or without a translator', () => {
    const f = { column: 'country', op: 'in', value: ['EG', 'SA'] }
    expect(describeFilter(f, (k, v) => translate('en', k, v))).toBe(describeFilter(f))
    expect(describeFilter(f, (k, v) => translate('ar', k, v))).toBe('«country» أحد EG, SA')
  })
})
