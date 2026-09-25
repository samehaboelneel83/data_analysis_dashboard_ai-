import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { WidgetPlaceholder, missingRequiredRoles, missingWidgetOptions, familyOf, emptyPickerReason } from './WidgetPlaceholder'
import { WidgetBody } from './WidgetBody'

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

describe('missingWidgetOptions (BUG-038)', () => {
  const need = (widget_type: string, config: Record<string, unknown> = {}) =>
    missingWidgetOptions({ widget_type, config } as never)

  it('names what a hierarchy, a layered map or a scorer still needs', () => {
    for (const t of ['tree', 'sunburst', 'icicle', 'circle_pack', 'dendrogram', 'org']) {
      expect(need(t), t).toEqual(['Hierarchy levels'])
    }
    expect(need('map_layers')).toEqual(['Country or Latitude/Longitude'])
    expect(need('model_score')).toEqual(['Saved model'])
    expect(need('model_compare')).toEqual(['Models to compare'])
  })

  it('is satisfied by either hierarchy mode, either map layer, or a chosen model', () => {
    expect(need('sunburst', { levels: ['region', 'city'] })).toEqual([])
    expect(need('org', { id_col: 'id', parent_col: 'manager' })).toEqual([])
    expect(need('org', { id_col: 'id' })).toEqual(['Hierarchy levels'])
    expect(need('map_layers', { dimension: 'country' })).toEqual([])
    expect(need('map_layers', { lat: 'lat', lon: 'lon' })).toEqual([])
    expect(need('map_layers', { lat: 'lat' })).toEqual(['Country or Latitude/Longitude'])
    expect(need('model_score', { prediction_model_id: 4 })).toEqual([])
    expect(need('bar')).toEqual([])
  })

  it('an unfinished hierarchy shows the placeholder, not "No data."', () => {
    render(<WidgetBody widget={{ id: 1, page_id: 1, widget_type: 'icicle', title: 'Icicle', config: {},
      layout: { x: 0, y: 0, w: 6, h: 4 } } as never} data={{ rows: [] }}
      localSelected={null} onClickPoint={() => {}} broadcasts={false} />)
    expect(screen.getByTestId('widget-placeholder')).toHaveTextContent('Needs Hierarchy levels')
    expect(screen.queryByText('No data.')).toBeNull()
  })
})
