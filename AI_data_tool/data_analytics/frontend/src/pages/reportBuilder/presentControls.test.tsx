import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import PresentControls from './PresentControls'

/** QA2 Visual 8: Present repeated the title ("Demo — Sales Overview · Demo —
 *  Sales Overview") when the page's display title is the dashboard's name. */
describe('Present title (QA2 Visual 8)', () => {
  const props = { activeId: 1, onGo: vi.fn(), onExit: vi.fn(), onAsk: vi.fn(), aiOpen: false, onCloseAi: vi.fn() }
  it('shows the page name once when it is the dashboard name', () => {
    const { container } = render(<PresentControls title="Demo — Sales Overview" pages={[{ id: 1, name: 'Demo — Sales Overview' }]} {...props} />)
    expect(container.querySelector('.dl-pr-ttl')?.textContent).toBe('Demo — Sales Overview')
  })
  it('keeps a different page name beside the title', () => {
    render(<PresentControls title="Sales" pages={[{ id: 1, name: 'Regions' }, { id: 2, name: 'Trend' }]} {...props} />)
    expect(screen.getByText('Regions')).toBeInTheDocument()
  })
})
