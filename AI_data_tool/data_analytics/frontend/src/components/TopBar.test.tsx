import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import TopBar from './TopBar'
import { CRUMB_EVENT } from '../lib/crumb'

/**
 * The top bar's three jobs: name the current page, open the ONE search
 * (the Ctrl+K palette -- not a second search box), and carry identity/logout.
 */

const logout = vi.fn()
vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { email: 'sara.omar@acme.com', role: { name: 'Admin', is_org_admin: true },
      organization: { name: 'Acme' } },
    logout,
  }),
}))
// The bell fetches on mount; it has its own tests.
vi.mock('./NotificationsBell', () => ({ default: () => <div data-testid="bell" /> }))

const renderAt = (path: string) =>
  render(<MemoryRouter initialEntries={[path]}><TopBar /></MemoryRouter>)

beforeEach(() => vi.clearAllMocks())

describe('TopBar', () => {
  it('titles the current page, longest route prefix winning', () => {
    renderAt('/monitoring/jobs')
    expect(screen.getByRole('heading', { name: 'Refresh & jobs' })).toBeInTheDocument()
  })

  it('puts the rail section in front of the page, as a breadcrumb', () => {
    renderAt('/admin/users')
    const trail = screen.getByRole('navigation', { name: 'Breadcrumb' })
    expect(trail).toHaveTextContent('Admin')
    expect(screen.getByRole('heading', { name: 'Users' })).toHaveAttribute('aria-current', 'page')
  })

  it('an admin page that is not itself in the rail still gets its section', () => {
    renderAt('/admin/connection-rules')
    expect(screen.getByRole('navigation', { name: 'Breadcrumb' })).toHaveTextContent('Admin')
  })

  it('names the record a detail page is showing, with the list as a link back', () => {
    renderAt('/datasets/170')
    act(() => { window.dispatchEvent(new CustomEvent(CRUMB_EVENT, { detail: { path: '/datasets/170', title: 'Sales 2024' } })) })
    expect(screen.getByRole('heading', { name: 'Sales 2024' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('link', { name: 'Datasets' })).toHaveAttribute('href', '/datasets')
    // A title sent for another path is never shown here.
    act(() => { window.dispatchEvent(new CustomEvent(CRUMB_EVENT, { detail: { path: '/reports/9', title: 'Other' } })) })
    expect(screen.queryByRole('heading', { name: 'Other' })).not.toBeInTheDocument()
  })

  it('Home has no section in front of it', () => {
    renderAt('/')
    expect(screen.getByRole('navigation', { name: 'Breadcrumb' }).textContent).toBe('Home')
  })

  it('falls back to Home for the root', () => {
    renderAt('/')
    expect(screen.getByRole('heading', { name: 'Home' })).toBeInTheDocument()
  })

  it('the search button opens the command palette, not a second search', () => {
    const heard = vi.fn()
    window.addEventListener('datalytics:open-palette', heard)
    renderAt('/')
    fireEvent.click(screen.getByRole('button', { name: /Search everything/ }))
    expect(heard).toHaveBeenCalledTimes(1)
    window.removeEventListener('datalytics:open-palette', heard)
  })

  it('shows identity initials and logs out from the menu', () => {
    renderAt('/')
    // "sara.omar" -> SO
    expect(screen.getByText('SO')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Account menu' }))
    expect(screen.getByText('sara.omar@acme.com')).toBeInTheDocument()
    expect(screen.getByText(/Admin · Acme/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('menuitem', { name: /Log out/ }))
    expect(logout).toHaveBeenCalledTimes(1)
  })

  it('Escape closes the account menu', () => {
    renderAt('/')
    fireEvent.click(screen.getByRole('button', { name: 'Account menu' }))
    expect(screen.getByRole('menu')).toBeInTheDocument()
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
  })
})

describe('TopBar — theme switch', () => {
  // The shell owns the theme (it stamps <html data-theme> and remembers it);
  // the header only offers the switch, beside the language switcher where the
  // app's other presentation control already lives.
  const renderWith = (theme: 'dark' | 'light', onToggleTheme = vi.fn()) =>
    render(<MemoryRouter initialEntries={['/']}>
      <TopBar theme={theme} onToggleTheme={onToggleTheme} />
    </MemoryRouter>)

  it('offers a switch to dark mode while the page is light, and calls back', () => {
    const onToggleTheme = vi.fn()
    renderWith('light', onToggleTheme)
    fireEvent.click(screen.getByRole('button', { name: 'Switch to dark mode' }))
    expect(onToggleTheme).toHaveBeenCalledTimes(1)
  })

  it('names the mode you would switch TO, not the one you are in', () => {
    renderWith('dark')
    expect(screen.getByRole('button', { name: 'Switch to light mode' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Switch to dark mode' })).not.toBeInTheDocument()
  })

  it('renders no switch when the shell does not provide one', () => {
    renderAt('/')
    expect(screen.queryByRole('button', { name: /Switch to (dark|light) mode/ })).not.toBeInTheDocument()
  })
})

describe('TopBar — narrow viewport', () => {
  const originalMatchMedia = window.matchMedia

  afterEach(() => { window.matchMedia = originalMatchMedia })

  it('keeps the account menu reachable by shrinking search and hiding the username', () => {
    window.matchMedia = vi.fn().mockImplementation(query => ({
      matches: query.includes('max-width: 767px'),
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
    }))
    const { container } = renderAt('/')
    const header = container.querySelector('header') as HTMLElement
    expect(['0', '0px']).toContain(header.style.minWidth)
    expect(screen.queryByText('sara.omar')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Account menu' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Search everything/ })).toBeInTheDocument()
    expect(screen.queryByText('Ctrl K')).not.toBeInTheDocument()
  })
})
