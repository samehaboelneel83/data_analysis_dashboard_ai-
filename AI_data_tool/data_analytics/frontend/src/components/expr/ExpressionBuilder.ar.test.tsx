import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import ExpressionBuilder from './ExpressionBuilder'
import { StepEditor } from '../report/prepPipeline/StepEditor'
import { DirectionProvider } from '../../contexts/DirectionContext'
import { OP_GROUPS } from '../report/calcColumns/catalog'
import type { DatasetColumn } from '../../services/api'

/** QA5 L1 / L2 / R1: the expression builder and the filter-rows step in Arabic. */
const columns: DatasetColumn[] = [
  { id: 1, name: 'date', dtype: 'datetime', missing_pct: 0, stats: {} },
  { id: 2, name: 'amount', dtype: 'numeric', missing_pct: 0, stats: {} },
]

beforeEach(() => { localStorage.setItem('datalytics.language', 'ar'); localStorage.setItem('datalytics.direction', 'rtl') })
afterEach(() => { localStorage.removeItem('datalytics.language'); localStorage.removeItem('datalytics.direction') })

describe('ExpressionBuilder in Arabic (QA5 L1, R1)', () => {
  const renderAr = (value = '') => render(
    <DirectionProvider>
      <ExpressionBuilder layout="panels" columns={columns} functionsCatalog={[]} opGroups={OP_GROUPS}
        value={value} onChange={vi.fn()} />
    </DirectionProvider>,
  )

  it('translates the mode toggle, the pane headings and the operator groups', () => {
    renderAr()
    for (const ar of ['بسيط', 'متقدم', 'الحقول', 'الدوال', 'العوامل', 'حسابية', 'مقارنة', 'منطقية', 'النظام']) {
      expect(screen.getByText(ar)).toBeInTheDocument()
    }
    for (const en of ['Simple', 'Advanced', 'Attributes', 'Functions', 'Operators', 'Arithmetic', 'Comparison', 'Logical', 'System']) {
      expect(screen.queryByText(en)).toBeNull()
    }
  })

  it('shows a column\'s type as a separate, translated word with the code kept', () => {
    renderAr()
    const btn = screen.getByRole('button', { name: /date/ })
    const tag = btn.querySelector('[data-dtype]')!
    expect(tag.textContent).toBe('تاريخ ووقت')
    expect(tag.getAttribute('data-dtype')).toBe('datetime')
    expect(btn.querySelector('bdi')!.textContent).toBe('date')
  })

  it('translates the system-parameter hints', () => {
    renderAr()
    expect(screen.getByRole('button', { name: 'USEREMAIL()' })).toHaveAttribute('title', 'بريد المستخدم الحالي')
  })

  it('renders every operator inside a left-to-right isolate, and the textarea is LTR', () => {
    renderAr('amount >= 5')
    for (const op of ['>=', '<=', '!=', '(', ')']) {
      const bdi = within(screen.getByRole('button', { name: op })).getByText(op)
      expect(bdi.tagName).toBe('BDI')
      expect(bdi).toHaveAttribute('dir', 'ltr')
    }
    expect(screen.getByRole('textbox')).toHaveAttribute('dir', 'ltr')
  })
})

describe('the filter-rows step editor in Arabic (QA5 L2)', () => {
  const renderStep = (expression = '') => render(
    <DirectionProvider>
      <StepEditor step={{ kind: 'filter_rows', expression }} columns={columns} otherDatasets={[]} onChange={vi.fn()} />
    </DirectionProvider>,
  )

  it('translates "+ Condition", "+ Function", the empty expression and the value kinds', () => {
    renderStep()
    expect(screen.getByRole('button', { name: 'إضافة شرط' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'إضافة دالة' })).toBeInTheDocument()
    expect(screen.getByText('(تعبير فارغ)')).toBeInTheDocument()
    expect(screen.queryByText(/Condition|Function|empty expression/)).toBeNull()
    const kinds = [...screen.getByLabelText('نوع القيمة').querySelectorAll('option')].map(o => o.textContent)
    expect(kinds).toEqual(['قيمة', 'عمود', 'معامل'])
  })

  it('translates "is blank" and isolates the comparison symbols', () => {
    renderStep()
    const ops = [...screen.getByLabelText('العامل').querySelectorAll('option')].map(o => o.textContent)
    expect(ops).toContain('فارغ')
    expect(ops).toContain('غير فارغ')
    expect(ops).toContain('⁦≥⁩')
    expect(ops.join(' ')).not.toMatch(/blank/)
    expect(screen.getByLabelText('حذف الصف')).toBeInTheDocument()
  })
})
