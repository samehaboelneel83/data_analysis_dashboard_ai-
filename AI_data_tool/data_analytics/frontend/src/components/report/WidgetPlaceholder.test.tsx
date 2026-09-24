import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { WidgetPlaceholder, missingRequiredRoles, familyOf, emptyPickerReason } from './WidgetPlaceholder'

describe('missingRequiredRoles', () => {
  it('names the required role a new bar chart still needs', () => {
    expect(missingRequiredRoles({ widget_type: 'bar', config: {} } as never)).toEqual(['Dimension'])
  })
  it('is empty once the role is filled', () => {
    expect(missingRequiredRoles({ widget_type: 'bar', config: { dimension: 'region' } } as never)).toEqual([])
  })
  it('treats an empty string or list as unfilled', () => {
    expect(missingRequiredRoles({ widget_type: 'bar', config: { dimension: '' } } as never)).toEqual(['Dimension'])
  })
})

describe('familyOf', () => {
  it('maps widget types to a sample shape', () => {
    expect(familyOf('bar')).toBe('bars')
    expect(familyOf('line')).toBe('line')
    expect(familyOf('donut')).toBe('pie')
    expect(familyOf('map_choropleth')).toBe('map')
    expect(familyOf('scatter')).toBe('scatter')
  })
})

describe('WidgetPlaceholder', () => {
  it('says what is needed and offers Assign data in edit mode', () => {
    const onAssign = vi.fn()
    render(<WidgetPlaceholder widget={{ widget_type: 'bar' }} missing={['Dimension']} onAssignData={onAssign} />)
    expect(screen.getByText('Needs Dimension')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Assign data' }))
    expect(onAssign).toHaveBeenCalledOnce()
  })
  it('a reader gets no button, and an explanation', () => {
    render(<WidgetPlaceholder widget={{ widget_type: 'bar' }} missing={['Dimension']} />)
    expect(screen.queryByRole('button')).toBeNull()
    expect(screen.getByText(/has not finished this widget/)).toBeTruthy()
  })
})

describe('emptyPickerReason -- an empty picker always says why', () => {
  it('no dataset at all', () => {
    expect(emptyPickerReason(false, 'numeric')).toMatch(/No dataset is attached/)
  })
  it('no column of the kind the field takes', () => {
    expect(emptyPickerReason(true, 'numeric')).toMatch(/no numeric columns/)
    expect(emptyPickerReason(true, 'datetime')).toMatch(/no date columns/)
  })
})
