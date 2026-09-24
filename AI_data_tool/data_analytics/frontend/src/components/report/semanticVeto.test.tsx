import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { WidgetBody, semanticFix } from './WidgetBody'

/**
 * The server refuses a summed year, coordinate or id (code `semantic_veto`),
 * and the widget offers the aggregation that means something in one click.
 */
describe('semantic veto on a widget', () => {
  it('picks the aggregation that means something', () => {
    expect(semanticFix({ measure: 'year', aggregation: 'sum' }))
      .toEqual({ patch: { aggregation: 'max' }, label: 'Use Maximum of year' })
    expect(semanticFix({ measure: 'revenue', measure2: 'customer_id', aggregation: 'sum' }))
      .toEqual({ patch: { aggregation2: 'countd' }, label: 'Use Distinct count of customer_id' })
    expect(semanticFix({ measure: 'latitude' })).toEqual({ patch: { aggregation: 'avg' }, label: 'Use Average of latitude' })
    expect(semanticFix({ measure: 'revenue', aggregation: 'sum' })).toBeNull()
  })

  it('shows the refusal with a one-click fix for an author', () => {
    const onApplyFix = vi.fn()
    render(<WidgetBody
      widget={{ id: 1, page_id: 1, widget_type: 'bar', title: 'Year by region',
        config: { dimension: 'region', measure: 'year', aggregation: 'sum' },
        layout: { x: 0, y: 0, w: 6, h: 5 } } as never}
      data={null}
      fetchError={{ code: 'semantic_veto', detail: 'Summing year adds up years -- the result is not a year.' }}
      localSelected={null} onClickPoint={() => {}} broadcasts={false} onApplyFix={onApplyFix} />)
    expect(screen.getByText(/adds up years/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Use Maximum of year' }))
    expect(onApplyFix).toHaveBeenCalledWith({ aggregation: 'max' }, 'Use Maximum of year')
  })

  it('a reader sees why, without a button they cannot use', () => {
    render(<WidgetBody
      widget={{ id: 1, page_id: 1, widget_type: 'bar', title: 't',
        config: { dimension: 'region', measure: 'year', aggregation: 'sum' },
        layout: { x: 0, y: 0, w: 6, h: 5 } } as never}
      data={null}
      fetchError={{ code: 'semantic_veto', detail: 'Summing year adds up years.' }}
      localSelected={null} onClickPoint={() => {}} broadcasts={false} />)
    expect(screen.getByText(/adds up years/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Use Maximum/ })).not.toBeInTheDocument()
  })
})
