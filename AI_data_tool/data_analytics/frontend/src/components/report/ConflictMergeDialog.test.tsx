import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import ConflictMergeDialog from './ConflictMergeDialog'

const base = { widget_type: 'bar', title: 'Sales', config: { measure: 'sales', sort: 'desc' } }

describe('ConflictMergeDialog (E09)', () => {
  it('saves at once when nothing was changed by both', () => {
    const onSave = vi.fn()
    render(<ConflictMergeDialog base={base} changedBy="sam@example.com"
      theirs={{ ...base, config: { ...base.config, measure: 'profit' } }}
      mine={{ ...base, title: 'Mine' }} onSave={onSave} onClose={vi.fn()} />)
    expect(screen.getByTestId('merge-summary')).toHaveTextContent('1 of your settings and 1 of sam@example.com')
    expect(screen.getByRole('dialog')).not.toContainElement(screen.queryByRole('radio'))
    fireEvent.click(screen.getByRole('button', { name: 'Save combined' }))
    expect(onSave).toHaveBeenCalledWith({ widget_type: 'bar', title: 'Mine', config: { measure: 'profit', sort: 'desc' } })
  })

  it('holds the save until every setting both changed has a choice', () => {
    const onSave = vi.fn()
    render(<ConflictMergeDialog base={base} changedBy={null}
      theirs={{ ...base, config: { measure: 'profit', sort: 'asc' } }}
      mine={{ ...base, config: { measure: 'units', sort: 'none' } }} onSave={onSave} onClose={vi.fn()} />)
    const save = screen.getByRole('button', { name: 'Save combined' })
    expect(save).toBeDisabled()
    const measure = screen.getByRole('group', { name: 'measure' })
    fireEvent.click(measure.querySelectorAll('input[type=radio]')[1])  // yours
    expect(save).toBeDisabled()
    const sort = screen.getByRole('group', { name: 'sort' })
    fireEvent.click(sort.querySelectorAll('input[type=radio]')[0])     // theirs
    expect(save).toBeEnabled()
    expect(sort).toHaveTextContent('Someone else')
    fireEvent.click(save)
    expect(onSave).toHaveBeenCalledWith({ widget_type: 'bar', title: 'Sales', config: { measure: 'units', sort: 'asc' } })
  })

  it('closes on Cancel without saving', () => {
    const onSave = vi.fn(), onClose = vi.fn()
    render(<ConflictMergeDialog base={base} theirs={base} mine={base} changedBy={null} onSave={onSave} onClose={onClose} />)
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onClose).toHaveBeenCalled()
    expect(onSave).not.toHaveBeenCalled()
  })
})
