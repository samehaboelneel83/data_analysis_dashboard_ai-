import { renderWithProviders as render, screen, fireEvent, within } from '../../test/renderWithProviders'
import { describe, it, expect, vi } from 'vitest'
import HistoryPanel from './HistoryPanel'
import type { AgentConversation } from '../../services/api'
import { translate } from '../../i18n'

/** Step 10, Part D: the History rail. */

const at = (daysAgo: number, h: number) => { const d = new Date(); d.setDate(d.getDate() - daysAgo); d.setHours(h, 5, 0, 0); return d.toISOString() }
const CONVS: AgentConversation[] = [
  { id: 3, title: 'Total revenue by region', data_source_id: null, dataset_ids: [1], created_at: at(0, 10) },
  { id: 2, title: 'Units by category', data_source_id: null, dataset_ids: [1], created_at: at(3, 9) },
  { id: 1, title: 'No date', data_source_id: null, dataset_ids: [1], created_at: null },
]
const panel = (extra: Partial<Parameters<typeof HistoryPanel>[0]> = {}) => {
  const props = {
    conversations: CONVS, selected: 3 as number | null, onSelect: vi.fn(), onNew: vi.fn(), editing: null, onEdit: vi.fn(), onSave: vi.fn(),
    onCancelEdit: vi.fn(), onDelete: vi.fn(), collapsed: false, onToggleCollapsed: vi.fn(), mobileOpen: false, onCloseMobile: vi.fn(), ...extra,
  }
  return { props, ...render(<HistoryPanel {...props} />) }
}

describe('the History rail', () => {
  it('groups threads into Today and Earlier, each with its title and when it was created', () => {
    const { container } = panel()
    expect(screen.getByRole('heading', { name: 'History' })).toBeInTheDocument()
    expect([...container.querySelectorAll('.dl-hist__group')].map(g => g.textContent)).toEqual(['Today', 'Earlier'])
    const today = screen.getByRole('button', { name: /^Total revenue by region/ })
    expect(today).toHaveAttribute('aria-current', 'true')
    expect(today.querySelector('.dl-hist__pick-when')?.textContent).toMatch(/10:05/)
    const older = screen.getByRole('button', { name: /^Units by category/ })
    expect(older).not.toHaveAttribute('aria-current')
    expect(older.querySelector('.dl-hist__pick-when')?.textContent).toMatch(/[A-Z][a-z]{2} \d{1,2}/)
    expect(screen.getByRole('button', { name: /^No date/ }).querySelector('.dl-hist__pick-when')).toBeNull()
    expect(screen.getByText('Questions are saved per dataset.')).toBeInTheDocument()
  })

  it('picks, starts a new chat, renames and deletes through the page', () => {
    const { props } = panel()
    fireEvent.click(screen.getByRole('button', { name: /^Units by category/ }))
    expect(props.onSelect).toHaveBeenCalledWith(2)
    fireEvent.click(screen.getByRole('button', { name: 'New chat' }))
    expect(props.onNew).toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Rename Units by category' }))
    expect(props.onEdit).toHaveBeenCalledWith({ id: 2, title: 'Units by category' })
    fireEvent.click(screen.getByRole('button', { name: 'Delete Units by category' }))
    expect(props.onDelete).toHaveBeenCalledWith(CONVS[1])
    fireEvent.click(screen.getByRole('button', { name: 'Collapse history' }))
    expect(props.onToggleCollapsed).toHaveBeenCalled()
  })

  it('renames in place: Enter saves, Escape cancels', () => {
    const { props } = panel({ editing: { id: 2, title: 'Units' } })
    const field = screen.getByRole('textbox', { name: 'Title' })
    expect(field).toHaveValue('Units')
    fireEvent.change(field, { target: { value: 'Units sold' } })
    expect(props.onEdit).toHaveBeenCalledWith({ id: 2, title: 'Units sold' })
    fireEvent.keyDown(field, { key: 'Enter' })
    expect(props.onSave).toHaveBeenCalledTimes(1)
    fireEvent.keyDown(field, { key: 'Escape' })
    expect(props.onCancelEdit).toHaveBeenCalled()
  })

  it('says what it will hold before any data is chosen, with New chat off', () => {
    panel({ conversations: [], selected: undefined, scope: 'none' })
    expect(screen.getByText('Pick a dataset to see its questions.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'New chat' })).toBeDisabled()
  })

  it('says there are none yet, for a dataset and for a connection', () => {
    const a = panel({ conversations: [], selected: null })
    expect(screen.getByText('No questions yet for this dataset.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'New chat' })).toBeEnabled()
    a.unmount()
    panel({ conversations: [], selected: null, scope: 'source' })
    expect(screen.getByText('No questions yet for this connection.')).toBeInTheDocument()
    expect(screen.getByText('Questions are saved per connection.')).toBeInTheDocument()
  })

  it('as an overlay it closes from its own button, the scrim and Escape', () => {
    const { props, container } = panel({ mobileOpen: true })
    fireEvent.click(screen.getByRole('button', { name: 'Hide history' }))
    fireEvent.click(container.querySelector('.dl-hist__scrim')!)
    fireEvent.keyDown(within(container).getByRole('complementary'), { key: 'Escape' })
    expect(props.onCloseMobile).toHaveBeenCalledTimes(3)
  })

  it('is in Arabic', () => {
    for (const k of ['ask2.hist.hide', 'ask2.hist.pick', 'ask2.hist.none', 'ask2.hist.noneSource', 'ask2.hist.foot', 'ask2.hist.footSource', 'ask2.hist.titleField'] as const) {
      expect(translate('ar', k), k).not.toBe(translate('en', k))
    }
    expect(translate('ar', 'ask2.hist.rename', { title: 'X' })).toBe('إعادة تسمية X')
  })
})
