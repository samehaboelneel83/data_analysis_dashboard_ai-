import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import ConvertToMenu, { CONVERT_WIDGET_EVENT } from './ConvertToMenu'
import type { Widget } from '../../types/report'

const bar = { id: 7, page_id: 1, widget_type: 'bar', title: 'Revenue by region',
  config: { dimension: 'region', measure: 'revenue', aggregation: 'sum' },
  layout: { x: 0, y: 0, w: 6, h: 4 }, created_at: '' } as Widget

describe('Convert to, in a widget menu', () => {
  it('drills in two steps -- families, then types -- and converts on the type', () => {
    const onDone = vi.fn()
    const seen: unknown[] = []
    const on = (e: Event) => seen.push((e as CustomEvent).detail)
    window.addEventListener(CONVERT_WIDGET_EVENT, on)
    render(<ConvertToMenu widget={bar} itemStyle={{}} onDone={onDone} />)

    const root = screen.getByRole('menuitem', { name: /Convert to/ })
    expect(root).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(root)
    const families = screen.getByRole('menu', { name: 'Convert to' })
    const basic = within(families).getByRole('menuitem', { name: /^Basic/ })
    expect(within(families).queryByRole('menuitem', { name: 'Line Chart' })).toBeNull()   // not until a family opens
    fireEvent.click(basic)
    fireEvent.click(within(screen.getByRole('menu', { name: 'Basic' })).getByRole('menuitem', { name: /Line/ }))

    window.removeEventListener(CONVERT_WIDGET_EVENT, on)
    expect(seen).toEqual([{ widgetId: 7, widget_type: 'line',
      config: { dimension: 'region', measure: 'revenue', aggregation: 'sum' },
      label: expect.stringMatching(/Convert "Revenue by region" to Line/) }])
    expect(onDone).toHaveBeenCalled()
  })

  it('lists only families that have a type the widget can become, and never a map for a chart', () => {
    render(<ConvertToMenu widget={bar} itemStyle={{}} onDone={() => {}} />)
    fireEvent.click(screen.getByRole('menuitem', { name: /Convert to/ }))
    const families = within(screen.getByRole('menu', { name: 'Convert to' }))
      .getAllByRole('menuitem').map(b => (b.textContent ?? '').replace(/\d+$/, ''))
    expect(families).not.toContain('Maps')
    expect(families.length).toBeGreaterThan(1)
  })

  it('is absent where nothing can be converted', () => {
    const text = { ...bar, widget_type: 'text', config: { content: 'hi' } } as Widget
    const { container } = render(<ConvertToMenu widget={text} itemStyle={{}} onDone={() => {}} />)
    expect(container.innerHTML).toBe('')
  })
})
