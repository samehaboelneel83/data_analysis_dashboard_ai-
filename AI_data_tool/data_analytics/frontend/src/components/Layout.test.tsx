import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderWithProviders as render, screen, fireEvent } from '../test/renderWithProviders'
import { within } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import Layout from './Layout'

// Mutable so individual tests can drop the admin flag -- the rail's Monitoring
// and Admin sections must vanish with it, not merely grey out.
let mockUser: any = null

vi.mock('../contexts/AuthContext', async importOriginal => ({
  ...(await importOriginal<object>()),
  useAuth: () => ({ user: mockUser, logout: vi.fn() }),
}))

beforeEach(() => {
  mockUser = { email: 'a@b.com', role: { is_org_admin: true, name: 'Admin' }, organization: { name: 'Acme' } }
})

function renderLayout(initialPath = '/') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<div>Page Content</div>} />
          <Route path="reports/:id" element={<div>Report Builder Page</div>} />
        </Route>
      </Routes>
    </MemoryRouter>
  )
}

describe('Layout', () => {
  it('renders icon-rail navigation links', () => {
    renderLayout()
    expect(screen.getByRole('link', { name: /Home/i })).toBeInTheDocument()
    // "Dashboards", not "Reports": the rename is label-deep only (the route
    // stays /reports), and the rail is where users read the product name.
    expect(screen.getByRole('link', { name: /Dashboards/i })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /^Reports$/i })).not.toBeInTheDocument()
  })

  it('gives the AI family top-level entries: Ask AI and Insights', () => {
    // The agent and the insights engine are the platform's flagship analysis
    // features; both were previously reachable only from inside other pages.
    renderLayout()
    expect(screen.getByRole('link', { name: /Ask AI/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /^Insights$/i })).toBeInTheDocument()
  })

  it('shows the Monitoring section and Column security to an org admin', () => {
    renderLayout()
    expect(screen.getByRole('link', { name: /Refresh & jobs/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Deliveries/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Activity/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Column security/i })).toBeInTheDocument()
  })

  it('hides Monitoring and Admin entirely from a non-admin', () => {
    mockUser = { email: 'v@b.com', role: { is_org_admin: false, name: 'Viewer' }, organization: { name: 'Acme' } }
    renderLayout()
    expect(screen.queryByRole('link', { name: /Refresh & jobs/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /Activity/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /Column security/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /^Users$/i })).not.toBeInTheDocument()
    // The non-gated entries survive.
    expect(screen.getByRole('link', { name: /Ask AI/i })).toBeInTheDocument()
  })

  it('puts Upload and Connections in the rail under Data sources', () => {
    renderLayout()
    expect(screen.getByText('Data sources')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /^Upload$/i })).toHaveAttribute('href', '/upload')
    expect(screen.getByRole('link', { name: /^Connections$/i })).toHaveAttribute('href', '/connections')
  })

  it('offers no entry for objects the platform does not have', () => {
    // The rail deliberately omits Fabric-style nodes (Apps, Data Products,
    // Semantic Models, My/Published splits): no menu entry until the object
    // exists. A link would be a dead control.
    renderLayout()
    for (const ghost of [/Apps/i, /Data Products/i, /Semantic Models/i, /Published Reports/i]) {
      expect(screen.queryByRole('link', { name: ghost })).not.toBeInTheDocument()
    }
  })

  it('still renders the routed page content', () => {
    renderLayout()
    expect(screen.getByText('Page Content')).toBeInTheDocument()
  })
})

describe('Layout — narrow screens use a drawer', () => {
  /** Make matchMedia report the drawer breakpoint as matching. */
  function goNarrow() {
    window.matchMedia = ((query: string) => ({
      matches: true, media: query, onchange: null,
      addListener: () => {}, removeListener: () => {},
      addEventListener: () => {}, removeEventListener: () => {}, dispatchEvent: () => false,
    })) as unknown as typeof window.matchMedia
  }

  afterEach(() => {
    window.matchMedia = ((query: string) => ({
      matches: false, media: query, onchange: null,
      addListener: () => {}, removeListener: () => {},
      addEventListener: () => {}, removeEventListener: () => {}, dispatchEvent: () => false,
    })) as unknown as typeof window.matchMedia
  })

  it('hides the rail and offers a hamburger instead of squeezing the content', () => {
    goNarrow()
    renderLayout()
    // The rail element still exists (its links stay in the a11y tree for tests
    // and for the drawer), but it is not laid out beside the content.
    expect(screen.getByTestId('app-rail')).toHaveStyle({ display: 'none' })
    expect(screen.getByRole('button', { name: 'Open navigation' })).toBeInTheDocument()
  })

  it('the hamburger opens the drawer, and it opens LABELED', () => {
    // An icon-only overlay would be a hieroglyph sheet floating over the page.
    goNarrow()
    renderLayout()
    fireEvent.click(screen.getByRole('button', { name: 'Open navigation' }))
    const rail = screen.getByTestId('app-rail')
    expect(rail).not.toHaveStyle({ display: 'none' })
    expect(rail.dataset.expanded).toBe('true')
  })

  it('Escape closes the drawer', () => {
    goNarrow()
    renderLayout()
    fireEvent.click(screen.getByRole('button', { name: 'Open navigation' }))
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.getByTestId('app-rail')).toHaveStyle({ display: 'none' })
  })

  it('shows no hamburger on a desktop width -- the rail is already there', () => {
    renderLayout()
    expect(screen.queryByRole('button', { name: 'Open navigation' })).not.toBeInTheDocument()
  })
})

describe('Layout — the theme switch lives in the header', () => {
  afterEach(() => {
    localStorage.removeItem('theme')
    document.documentElement.removeAttribute('data-theme')
  })

  it('flips the document theme from the header and remembers it', () => {
    renderLayout()
    const header = screen.getByRole('banner')
    fireEvent.click(within(header).getByRole('button', { name: 'Switch to dark mode' }))
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
    expect(localStorage.getItem('theme')).toBe('dark')
    // The control now names the way back.
    expect(within(header).getByRole('button', { name: 'Switch to light mode' })).toBeInTheDocument()
  })

  it('offers the switch exactly once -- the rail no longer duplicates it', () => {
    // Two controls for one setting read as two settings. The rail keeps the
    // direction toggle (the language switcher pairs direction with language,
    // the rail lets you override it alone); the theme switch moved up.
    renderLayout()
    expect(screen.getAllByRole('button', { name: /Switch to (dark|light) mode/ })).toHaveLength(1)
    expect(within(screen.getByTestId('app-rail'))
      .queryByRole('button', { name: /Switch to (dark|light) mode/ })).not.toBeInTheDocument()
  })
})
