import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react'
import PagePropertiesPanel from './PagePropertiesPanel'
import type { ReportPage, Widget } from '../../types/report'

function page(overrides: Partial<ReportPage> = {}): ReportPage {
  return {
    id: 100, report_id: 1, name: 'Page 1', page_type: 'normal', position: 0,
    widgets: [], created_at: '2026-01-01', page_size: '16:9', ...overrides,
  }
}

function buttonWidget(overrides: Partial<Widget> = {}): Widget {
  return {
    id: 1, page_id: 100, widget_type: 'button', title: 'Go', config: { label: 'Go' },
    layout: { x: 0, y: 0, w: 2, h: 2 }, created_at: '2026-01-01', ...overrides,
  }
}

// ExpandableGroup persists open/closed state to localStorage, shared across tests.
beforeEach(() => localStorage.clear())

describe('every control in the panel can be named', () => {
  /**
   * The panel's `fld` helper renders a <label> with no `for`, so three of its
   * controls were labelled only visually: a screen reader announced "edit text"
   * and "combo box" with nothing to say what they set.
   *
   * The same omission is why nothing here was testable by label — which is how
   * the Interactions panel next door went a whole release saving nothing
   * without a single test noticing.
   */
  const LABELS = ['Tab name', 'Display title', 'Filter column']

  it.each(LABELS)('%s is reachable by its label', (label) => {
    render(<PagePropertiesPanel page={page()} columns={[
      { id: 1, name: 'department', dtype: 'text', missing_pct: 0, stats: {} } as never,
    ]} onUpdate={vi.fn()} />)
    expect(screen.getByLabelText(new RegExp(label, 'i'))).toBeInTheDocument()
  })

  it('typing in the tab name still reaches onUpdate', () => {
    vi.useFakeTimers()
    const onUpdate = vi.fn()
    render(<PagePropertiesPanel page={page()} columns={[]} onUpdate={onUpdate} />)
    fireEvent.change(screen.getByLabelText(/tab name/i), { target: { value: 'Overview' } })
    act(() => { vi.advanceTimersByTime(600) })
    expect(onUpdate).toHaveBeenCalledWith(expect.objectContaining({ name: 'Overview' }))
    vi.useRealTimers()
  })
})

describe('PagePropertiesPanel page size', () => {
  it('highlights the active page size preset and updates it on click', () => {
    vi.useFakeTimers()
    const onUpdate = vi.fn()
    render(<PagePropertiesPanel page={page({ page_size: '16:9' })} columns={[]} onUpdate={onUpdate} />)

    fireEvent.click(screen.getByRole('button', { name: '4:3' }))
    act(() => { vi.advanceTimersByTime(600) })

    expect(onUpdate).toHaveBeenCalledWith(expect.objectContaining({ page_size: '4:3' }))
    vi.useRealTimers()
  })
})

describe('PagePropertiesPanel section groups (Task B2)', () => {
  it('renders the panel restructured into named ExpandableGroups', () => {
    render(<PagePropertiesPanel page={page()} columns={[]} onUpdate={vi.fn()} />)
    expect(screen.getByRole('button', { name: /Identity/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Layout/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Behaviour/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Prompt/i })).toBeInTheDocument()
  })
})

describe('PagePropertiesPanel actions summary (Task B2)', () => {
  it('lists a button widget whose config has an action, and clicking it selects the widget', () => {
    const onSelectWidget = vi.fn()
    const navPage = page({ id: 200, name: 'Page 2' })
    const w = buttonWidget({ config: { label: 'Go', action: 'navigate', actionPageId: 200 } })
    render(<PagePropertiesPanel
      page={page({ widgets: [w] })}
      columns={[]} onUpdate={vi.fn()}
      pages={[page(), navPage]} bookmarks={[]} onSelectWidget={onSelectWidget} />)

    const row = screen.getByRole('button', { name: /Button 'Go' → navigate: Page 2/i })
    expect(row).toBeInTheDocument()

    fireEvent.click(row)
    expect(onSelectWidget).toHaveBeenCalledWith(w)
  })

  it('hides the Actions on this page section when no widget on the page has an action', () => {
    render(<PagePropertiesPanel
      page={page({ widgets: [buttonWidget({ config: { label: 'Go' } })] })}
      columns={[]} onUpdate={vi.fn()}
      pages={[page()]} bookmarks={[]} onSelectWidget={vi.fn()} />)
    expect(screen.queryByRole('button', { name: /Actions on this page/i })).not.toBeInTheDocument()
  })
})

describe('a page background image', () => {
  /**
   * The SAS page this was measured against is a photograph with a bar chart,
   * two headline numbers and a line plot floating on it. Two halves: somewhere
   * to put the picture (here) and objects that draw no panel of their own
   * (`config.transparent`, in WidgetConfigPanel).
   */
  it('saves the image the author typed', async () => {
    const onUpdate = vi.fn()
    render(<PagePropertiesPanel reportId={1} page={page()} columns={[]} onUpdate={onUpdate} />)

    fireEvent.change(screen.getByLabelText(/background image/i),
      { target: { value: 'https://images.example/shop.jpg' } })
    await waitFor(() => expect(onUpdate).toHaveBeenCalledWith(
      expect.objectContaining({ background_url: 'https://images.example/shop.jpg' })))
  })

  it('clears it with an empty box rather than leaving the old one', async () => {
    // `undefined` would mean "unchanged" to a partial PATCH, so an author who
    // cleared the field would watch the picture stay.
    const onUpdate = vi.fn()
    render(<PagePropertiesPanel reportId={1}
      page={{ ...page(), background_url: 'https://images.example/shop.jpg' }}
      columns={[]} onUpdate={onUpdate} />)

    fireEvent.change(screen.getByLabelText(/background image/i), { target: { value: '' } })
    await waitFor(() => expect(onUpdate).toHaveBeenCalledWith(
      expect.objectContaining({ background_url: '' })))
  })

  it('shows the one the page already has', () => {
    render(<PagePropertiesPanel reportId={1}
      page={{ ...page(), background_url: 'https://images.example/shop.jpg' }}
      columns={[]} onUpdate={vi.fn()} />)
    expect(screen.getByLabelText(/background image/i))
      .toHaveValue('https://images.example/shop.jpg')
  })
})

/**
 * The same panel, the same behaviour.
 *
 * The widget properties panel has a "Filter settings" box; this one did not —
 * so the search an author had just learned to use stopped working the moment
 * they selected the page. One panel with two behaviours is worse than neither,
 * because the reader has to remember which half they are in.
 */
describe('filtering the page settings', () => {
  const renderPanel = () =>
    render(<PagePropertiesPanel page={page()} columns={[]} onUpdate={vi.fn()} />)

  it('narrows to the group that matches', () => {
    renderPanel()
    fireEvent.change(screen.getByLabelText(/filter settings/i), { target: { value: 'layout' } })

    expect(screen.getByText(/layout/i)).toBeInTheDocument()
    expect(screen.queryByText(/^identity$/i)).not.toBeInTheDocument()
  })

  it('says when nothing matches instead of emptying the panel', () => {
    renderPanel()
    fireEvent.change(screen.getByLabelText(/filter settings/i), { target: { value: 'zzzz' } })
    expect(screen.getByText(/no setting matches/i)).toBeInTheDocument()
  })

  it('restores every group when the box is cleared', () => {
    renderPanel()
    const box = screen.getByLabelText(/filter settings/i)
    fireEvent.change(box, { target: { value: 'layout' } })
    fireEvent.change(box, { target: { value: '' } })
    expect(screen.getByText(/^identity$/i)).toBeInTheDocument()
  })
})

describe('the last visible page', () => {
  it('cannot be hidden or turned into a pop-up, and says why', () => {
    const only = page({ id: 1, page_type: 'normal' })
    render(<PagePropertiesPanel page={only} pages={[only, page({ id: 2, page_type: 'popup' })]} columns={[]} onUpdate={vi.fn()} />)
    const hidden = screen.getByDisplayValue('hidden') as HTMLInputElement
    expect(hidden.disabled).toBe(true)
    expect(screen.getAllByText('Not available: this is the only visible page').length).toBeGreaterThan(0)
  })

  it('can be hidden when another page is visible', () => {
    const a = page({ id: 1, page_type: 'normal' })
    render(<PagePropertiesPanel page={a} pages={[a, page({ id: 2, page_type: 'normal' })]} columns={[]} onUpdate={vi.fn()} />)
    expect((screen.getByDisplayValue('hidden') as HTMLInputElement).disabled).toBe(false)
  })
})
