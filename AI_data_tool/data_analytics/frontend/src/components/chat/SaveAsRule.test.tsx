import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import SaveAsRule, { definedTerm, looksLikeDefinition } from './SaveAsRule'
import { metadataApi } from '../../services/api'

describe('Save as a business rule (3.8)', () => {
  it('spots definitions in English and Arabic, not plain questions', () => {
    expect(looksLikeDefinition('current employee means dept_emp.to_date = 9999-01-01')).toBe(true)
    expect(looksLikeDefinition('الموظف الحالي يعني to_date = 9999-01-01')).toBe(true)
    expect(looksLikeDefinition('how many employees per department?')).toBe(false)
  })

  it('pulls out the term being defined', () => {
    expect(definedTerm('current employee means to_date = 9999-01-01')).toBe('current employee')
    expect(definedTerm('By headcount I mean distinct emp_no')).toBe('headcount')
  })

  it('saves a glossary term with the rule, applied always', async () => {
    const add = vi.spyOn(metadataApi, 'addTerm').mockResolvedValue({ id: 1 } as never)
    render(<SaveAsRule sourceId={7} text="current employee means to_date = 9999-01-01" />)
    fireEvent.click(screen.getByRole('button', { name: /save as a business rule/i }))
    expect(screen.getByLabelText(/term/i)).toHaveValue('current employee')
    fireEvent.click(screen.getByRole('button', { name: /save rule/i }))
    await waitFor(() => expect(add).toHaveBeenCalledWith(7, {
      term: 'current employee', definition: 'current employee means to_date = 9999-01-01',
      rule: 'current employee means to_date = 9999-01-01', always: true }))
    expect(await screen.findByText(/saved as a business rule/i)).toBeInTheDocument()
  })
})
