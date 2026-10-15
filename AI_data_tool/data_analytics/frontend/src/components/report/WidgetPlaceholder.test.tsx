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

describe('C-03: a config whose roles sit in a nested `roles` dict', () => {
  it('counts the nested roles as assigned, as the server does', () => {
    expect(missingRequiredRoles({ widget_type: 'map_contour',
      config: { roles: { lat: 'a', lon: 'b' } } } as never)).toEqual([])
    expect(missingWidgetOptions({ widget_type: 'map_layers',
      config: { roles: { lat: 'a', lon: 'b' } } } as never)).toEqual([])
  })
  it('a contour result (a grid, no rows) is drawn, not replaced by the placeholder', () => {
    render(<WidgetBody widget={{ id: 1, page_id: 1, widget_type: 'map_contour', title: 'Contour',
      config: { lat: 'a', lon: 'b' }, layout: { x: 0, y: 0, w: 6, h: 4 } } as never}
      data={{ type: 'geo_contour', grid: [[0, 1], [1, 2]] }}
      localSelected={null} onClickPoint={() => {}} broadcasts={false} />)
    expect(screen.queryByTestId('widget-placeholder')).toBeNull()
  })
})

describe('C-10: an unassigned point or bubble map is unfinished', () => {
  it('needs a country or a coordinate pair', () => {
    for (const wt of ['map_points', 'map_bubbles']) {
      expect(missingWidgetOptions({ widget_type: wt, config: {} } as never)).toEqual(['Country or Latitude/Longitude'])
      expect(missingWidgetOptions({ widget_type: wt, config: { dimension: 'country' } } as never)).toEqual([])
      expect(missingWidgetOptions({ widget_type: wt, config: { lat: 'a', lon: 'b' } } as never)).toEqual([])
    }
  })
  it('names the missing half of a coordinate pair', () => {
    expect(missingWidgetOptions({ widget_type: 'map_points', config: { lat: 'a' } } as never)).toEqual(['Longitude'])
    expect(missingWidgetOptions({ widget_type: 'map_points', config: { lon: 'b', dimension: 'c' } } as never)).toEqual(['Latitude'])
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

describe('a bar of several measures and no category (score group items)', () => {
  it('is finished, and one measure alone still needs a category', async () => {
    const { measuresAsBars, missingRequiredRoles } = await import('./WidgetPlaceholder')
    const items = { widget_type: 'bar', config: { measures: ['q1', 'q2', 'q3'], aggregation: 'avg' } } as never
    expect(measuresAsBars(items)).toEqual(['q1', 'q2', 'q3'])
    expect(missingRequiredRoles(items)).toEqual([])
    const one = { widget_type: 'bar', config: { measures: ['q1'], aggregation: 'avg' } } as never
    expect(measuresAsBars(one)).toBeNull()
    expect(missingRequiredRoles(one).length).toBeGreaterThan(0)
  })
})

describe('C-14: a category chart given only a measure is unfinished', () => {
  it('a pie with a measure and a scalar answer shows "Needs Dimension", not one solid disc', () => {
    render(<WidgetBody widget={{ id: 1, page_id: 1, widget_type: 'pie', title: 'Pie',
      config: { measure: 'revenue' }, layout: { x: 0, y: 0, w: 6, h: 4 } } as never}
      data={{ type: 'scalar', rows: [{ name: 'revenue', value: 100 }] }}
      localSelected={null} onClickPoint={() => {}} broadcasts={false} />)
    expect(screen.getByTestId('widget-placeholder')).toHaveTextContent(/Needs Dimension/)
  })
  it('a KPI with a scalar answer draws its number', () => {
    render(<WidgetBody widget={{ id: 1, page_id: 1, widget_type: 'kpi', title: 'K',
      config: { measure: 'revenue' }, layout: { x: 0, y: 0, w: 3, h: 3 } } as never}
      data={{ type: 'scalar', rows: [{ name: 'revenue', value: 100 }] }}
      localSelected={null} onClickPoint={() => {}} broadcasts={false} />)
    expect(screen.queryByTestId('widget-placeholder')).toBeNull()
  })
})

describe('C-23: small multiples needs its split field', () => {
  it('a small multiple without facet_by is unfinished', () => {
    expect(missingRequiredRoles({ widget_type: 'small_multiples', config: { dimension: 'category' } } as never))
      .toEqual(['Split into multiples by'])
    expect(missingRequiredRoles({ widget_type: 'small_multiples', config: { dimension: 'category', facet_by: 'region' } } as never))
      .toEqual([])
  })
})

describe('C-07: a scatter offers an X measure', () => {
  it('has an optional numeric X role beside its Y measure', async () => {
    const { ROLE_SPECS, roleAccepts } = await import('../../types/report')
    const x = ROLE_SPECS.scatter.find(r => r.role === 'measure2')
    expect(x).toMatchObject({ required: false })
    expect(roleAccepts('measure2')).toBe('numeric')
  })
})
