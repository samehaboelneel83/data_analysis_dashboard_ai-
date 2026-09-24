import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import WidgetRenderer from './WidgetRenderer'
import { CrossFilterProvider } from './CrossFilterContext'
import { widgetDataApi } from '../../services/api'
import type { Widget, ReportPage } from '../../types/report'

vi.mock('../../services/api', () => ({
  widgetDataApi: { query: vi.fn(), export: vi.fn() },
}))

const child = (id: number, title: string, containerId: number, layout = { x: 0, y: 0, w: 6, h: 3 }): Widget => ({
  id, page_id: 1, widget_type: 'text',
  title, config: { content: `${title} body`, container_id: containerId }, layout,
} as never)

const containerWidget = (mode?: string, extra: Partial<Widget> = {}): Widget => ({
  id: 10, page_id: 1, widget_type: 'container', title: 'My Container',
  config: mode ? { container_mode: mode } : {}, layout: { x: 0, y: 0, w: 6, h: 6 },
  ...extra,
} as never)

const pageWith = (...widgets: Widget[]): ReportPage[] => ([{
  id: 1, report_id: 1, name: 'P', page_type: 'normal', position: 0, widgets,
} as never])

const renderContainer = (mode?: string, children?: Widget[]) => {
  const c = containerWidget(mode)
  const kids = children ?? [child(11, 'First', 10), child(12, 'Second', 10, { x: 0, y: 3, w: 6, h: 3 } as never)]
  return render(
    <CrossFilterProvider>
      <WidgetRenderer widget={c} datasetId={1} pages={pageWith(c, ...kids)} />
    </CrossFilterProvider>
  )
}

beforeEach(() => vi.clearAllMocks())

describe('container widget', () => {
  it('renders its children and nothing else', () => {
    const stranger = child(99, 'Stranger', 555)   // belongs to a different container
    renderContainer(undefined, [child(11, 'First', 10), stranger])
    expect(screen.getByText('First body')).toBeInTheDocument()
    expect(screen.queryByText('Stranger body')).not.toBeInTheDocument()
  })

  it('is a named group for assistive tech', () => {
    renderContainer()
    expect(screen.getByRole('group', { name: 'My Container' })).toBeInTheDocument()
  })

  it('tabs mode shows one child at a time and switches on click', () => {
    renderContainer('tabs')
    expect(screen.getByRole('tab', { name: 'First' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByText('First body')).toBeInTheDocument()
    // The unselected tab's child must be ABSENT, not merely hidden -- that is what
    // distinguishes tabs from the group mode with everything stacked.
    expect(screen.queryByText('Second body')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('tab', { name: 'Second' }))
    expect(screen.getByText('Second body')).toBeInTheDocument()
    expect(screen.queryByText('First body')).not.toBeInTheDocument()
  })

  it('collapsible mode hides children behind its header', () => {
    renderContainer('prompt')
    expect(screen.getByText('First body')).toBeInTheDocument()
    const header = screen.getByRole('button', { name: /My Container/ })
    expect(header).toHaveAttribute('aria-expanded', 'true')
    fireEvent.click(header)
    expect(screen.queryByText('First body')).not.toBeInTheDocument()
  })

  it('an empty container says how to fill it rather than rendering a void', () => {
    renderContainer(undefined, [])
    expect(screen.getByText(/assign widgets/i)).toBeInTheDocument()
  })

  it('never fetches data of its own', () => {
    renderContainer()
    expect(widgetDataApi.query).not.toHaveBeenCalled()
  })
})

describe('the precision container', () => {
  /**
   * Overlapping objects positioned freely over a background image — SAS's
   * precision container, and the last layout gap in the comparison.
   *
   * Most of it was already here: `group` and `scroll` position children
   * absolutely from their own layout, so overlap has always been possible. What
   * was missing is a background to position over, and a stacking order — two
   * overlapping widgets with no z-order stack by document order, which is the
   * order they happen to be sorted in, so "bring to front" was not expressible.
   */
  const precise = (extra: Record<string, unknown> = {}) => ({
    id: 10, page_id: 1, widget_type: 'container', title: 'Floorplan',
    config: { container_mode: 'precision', ...extra },
    layout: { x: 0, y: 0, w: 6, h: 6 },
  } as never as Widget)

  const drawPrecision = (extra: Record<string, unknown> = {}, kids?: Widget[]) => {
    const c = precise(extra)
    const children = kids ?? [
      child(11, 'Back', 10, { x: 0, y: 0, w: 4, h: 3 } as never),
      child(12, 'Front', 10, { x: 1, y: 1, w: 4, h: 3 } as never),
    ]
    return render(
      <CrossFilterProvider>
        <WidgetRenderer widget={c} datasetId={1} pages={pageWith(c, ...children)} />
      </CrossFilterProvider>
    )
  }

  it('draws its children', () => {
    drawPrecision()
    expect(screen.getByText('Back body')).toBeInTheDocument()
    expect(screen.getByText('Front body')).toBeInTheDocument()
  })

  it('lets them overlap rather than clipping or reflowing', () => {
    // Two children whose rectangles intersect must both be positioned, not
    // pushed apart — that is the entire point of a precision layout.
    const { container } = drawPrecision()
    const placed = container.querySelectorAll('[data-precision-child]')
    expect(placed).toHaveLength(2)
    for (const el of placed) {
      expect((el as HTMLElement).style.position).toBe('absolute')
    }
  })

  it('shows a background image when one is set', () => {
    const { container } = drawPrecision({ background_url: 'https://x.invalid/plan.png' })
    const bg = container.querySelector('[data-precision-background]') as HTMLElement
    expect(bg).toBeTruthy()
    expect(bg.style.backgroundImage).toContain('plan.png')
  })

  it('has no background element when none is set', () => {
    const { container } = drawPrecision()
    expect(container.querySelectorAll('[data-precision-child]')).toHaveLength(2)
    expect(container.querySelector('[data-precision-background]')).toBeNull()
  })

  it('stacks children by their z order', () => {
    const { container } = drawPrecision({}, [
      child(11, 'Back', 10, { x: 0, y: 0, w: 4, h: 3 } as never),
      { ...child(12, 'Front', 10, { x: 1, y: 1, w: 4, h: 3 } as never),
        config: { content: 'Front body', container_id: 10, z: 5 } } as never,
    ])
    const placed = [...container.querySelectorAll('[data-precision-child]')] as HTMLElement[]
    const zs = placed.map(el => Number(el.style.zIndex || 0))
    expect(Math.max(...zs)).toBe(5)
  })

  it('leaves unstacked children at zero rather than inventing an order', () => {
    // Document order is an accident of sorting; treating it as intent would
    // make "bring to front" mean whatever the sort happened to do.
    const { container } = drawPrecision()
    const placed = [...container.querySelectorAll('[data-precision-child]')] as HTMLElement[]
    // Length first: `.every()` over an empty list is vacuously true, so without
    // this the assertion passed before the feature existed at all.
    expect(placed).toHaveLength(2)
    expect(placed.every(el => Number(el.style.zIndex || 0) === 0)).toBe(true)
  })

  it('refuses a background that is not an http(s) image', () => {
    // Same rule the custom visual and image widgets already apply.
    const { container } = drawPrecision({ background_url: 'javascript:alert(1)' })
    expect(container.querySelectorAll('[data-precision-child]')).toHaveLength(2)
    expect(container.querySelector('[data-precision-background]')).toBeNull()
  })

  it('still says when it is empty', () => {
    drawPrecision({}, [])
    expect(screen.getByText(/empty container/i)).toBeInTheDocument()
  })
})
