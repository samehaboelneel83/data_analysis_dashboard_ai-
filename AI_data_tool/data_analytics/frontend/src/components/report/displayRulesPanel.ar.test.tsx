import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { DirectionProvider } from '../../contexts/DirectionContext'
import DisplayRulesPanel from './DisplayRulesPanel'

/** QA3 Batch C: the display rules ("Report rules") read in Arabic; the values
 *  saved are unchanged. */

beforeEach(() => { localStorage.clear(); localStorage.setItem('datalytics.language', 'ar') })

describe('DisplayRulesPanel in Arabic', () => {
  it('labels, options and empty state are Arabic; saved values are not translated', () => {
    const onChange = vi.fn()
    render(<DirectionProvider><DisplayRulesPanel rules={[]} columns={['value', 'name']} numericColumns={['value']} onChange={onChange} /></DirectionProvider>)
    expect(screen.getByText('قواعد العرض')).toBeInTheDocument()
    expect(screen.getByText('لا توجد قواعد عرض بعد')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '+ إضافة قاعدة' }))
    const op = screen.getByLabelText('الشرط') as HTMLSelectElement
    expect(op.value).toBe('gt')
    expect(op.selectedOptions[0].textContent).toBe('أكبر من')
    expect((screen.getByLabelText('نوع القاعدة') as HTMLSelectElement).selectedOptions[0].textContent).toBe('تعبير')
    expect(screen.getByLabelText('العمود')).toBeInTheDocument()
    expect(screen.getByLabelText('تُطبَّق على')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'إزالة' })).toBeInTheDocument()
    fireEvent.change(op, { target: { value: 'between' } })
    expect(onChange.mock.lastCall?.[0][0].condition.op).toBe('between')
    expect(document.body.textContent).not.toMatch(/Display Rules|Rule kind|Operator|is greater than|Remove/)
  })
})
