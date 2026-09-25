# Application Shell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the app's sidebar chrome with a ribbon + thin navigation rail, add a
Report/Data/Model view switcher inside the report editor, and add join-key-only relationship
metadata with a diagram to define/view it — per
`docs/superpowers/specs/2026-08-15-application-shell-design.md`.

**Architecture:** Frontend: a new `RibbonContext` (mirrors the existing `CrossFilterContext`
pattern) lets whichever page is mounted inject content into four fixed ribbon tabs. `Layout.tsx`
is restructured to a thin icon-only nav rail + the ribbon; `ReportBuilder.tsx` is brought under
that same `Layout` (it currently bypasses it entirely) and gains a Report/Data/Model view strip.
Backend: one new `Relationship` table (join-key only, admin CRUD mirroring the existing
`RowSecurityRule` pattern) plus additive columns on `ReportPage` for page sizing and two new
`page_type` values.

**Tech Stack:** FastAPI + SQLAlchemy async + Pydantic (backend), React + TypeScript + Vite +
Vitest/Testing Library (frontend), pytest + httpx (backend tests).

## Global Constraints

- Every new backend list/get/update/delete endpoint enforces org scoping via `check_org` (see
  `backend/app/core/org_scope.py`) — 404, never 403, on cross-org access (established convention,
  see `2026-08-13-row-level-security-design.md`).
- New DB columns/tables are added via `_migrate()` in `backend/app/main.py` (idempotent
  `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`) — this project does not use Alembic (see
  `2026-08-13-row-level-security-design.md`'s "Migrations" section for why).
- Frontend API calls go through `frontend/src/services/api.ts`'s `api` axios instance — new
  endpoints get a new exported `*Api` object there, following the existing `dataSourcesApi`/
  `hierarchyApi` shape.
- No new frontend dependencies — build the diagram and rail with plain React/CSS, matching how
  `ReportBuilder.tsx`'s existing grid (no drag-and-drop library) and `Connections.tsx`'s toggle
  were built this session.
- TDD throughout: write the failing test, watch it fail, implement, watch it pass, commit — the
  discipline already established all session (see e.g. `backend/tests/test_direct_query_plan.py`'s
  history for the pattern).

---

## File Structure

**New files:**
- `frontend/src/components/RibbonContext.tsx` — provider + `useRibbon()` hook
- `frontend/src/components/Ribbon.tsx` — the four-tab bar component
- `frontend/src/components/report/DataView.tsx` — read-only paginated data grid for the report editor's Data view
- `frontend/src/components/report/ModelView.tsx` — relationship diagram + create-relationship form
- `frontend/src/components/report/StatusBar.tsx` — page info + save status strip
- `frontend/src/pages/admin/AdminRelationships.tsx` — not created; relationships are managed from `ModelView.tsx` directly (report-scoped), no separate admin page needed
- `backend/app/routers/relationships.py` — `Relationship` CRUD, mirrors `admin.py`'s row-security-rule section

**Modified files:**
- `frontend/src/components/Layout.tsx` — sidebar becomes an icon rail + `<RibbonProvider><Ribbon/></RibbonProvider>`
- `frontend/src/App.tsx` — `reports/:id` route moves inside the `Layout` route
- `frontend/src/pages/ReportBuilder.tsx` — duplicate top nav removed; gains Report/Data/Model view strip; widget catalog relocates into the ribbon's Insert tab
- `frontend/src/services/api.ts` — new `relationshipsApi`
- `backend/app/models/models.py` — `Relationship`; `ReportPage.page_size`/`custom_width`/`custom_height`
- `backend/app/main.py` — migration statements
- `backend/app/schemas/schemas.py` — `RelationshipCreate`/`Update`/`Out`; `PageCreate`/`Update`/`Out` gain page-size fields
- `backend/app/main.py` (router registration) — mount `relationships.router`

---

## PHASE 1 — Ribbon Shell + Navigation Rail

### Task 1: RibbonContext

**Files:**
- Create: `frontend/src/components/RibbonContext.tsx`
- Test: `frontend/src/components/RibbonContext.test.tsx`

**Interfaces:**
- Produces: `RibbonProvider` (component, wraps children), `useRibbon()` returning
  `{ tabs: Record<RibbonTab, ReactNode>, setTabContent: (tab: RibbonTab, content: ReactNode) => void, clearTabContent: (tab: RibbonTab) => void }`
  where `type RibbonTab = 'home' | 'insert' | 'modeling' | 'view'`.

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/RibbonContext.test.tsx
import { describe, it, expect } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import { useEffect } from 'react'
import { RibbonProvider, useRibbon } from './RibbonContext'

function Injector({ tab, text }: { tab: 'home' | 'insert' | 'modeling' | 'view'; text: string }) {
  const { setTabContent, clearTabContent } = useRibbon()
  useEffect(() => {
    setTabContent(tab, <span>{text}</span>)
    return () => clearTabContent(tab)
  }, [tab, text, setTabContent, clearTabContent])
  return null
}

function Reader({ tab }: { tab: 'home' | 'insert' | 'modeling' | 'view' }) {
  const { tabs } = useRibbon()
  return <div data-testid="reader">{tabs[tab]}</div>
}

describe('RibbonContext', () => {
  it('shows content set by a mounted component', () => {
    render(
      <RibbonProvider>
        <Injector tab="home" text="Upload" />
        <Reader tab="home" />
      </RibbonProvider>
    )
    expect(screen.getByTestId('reader')).toHaveTextContent('Upload')
  })

  it('clears content when the setting component unmounts', () => {
    function Wrapper({ mounted }: { mounted: boolean }) {
      return (
        <RibbonProvider>
          {mounted && <Injector tab="insert" text="Add Visual" />}
          <Reader tab="insert" />
        </RibbonProvider>
      )
    }
    const { rerender } = render(<Wrapper mounted={true} />)
    expect(screen.getByTestId('reader')).toHaveTextContent('Add Visual')
    act(() => rerender(<Wrapper mounted={false} />))
    expect(screen.getByTestId('reader')).toHaveTextContent('')
  })

  it('keeps tabs independent of each other', () => {
    render(
      <RibbonProvider>
        <Injector tab="home" text="A" />
        <Injector tab="view" text="B" />
        <Reader tab="home" />
      </RibbonProvider>
    )
    expect(screen.getByTestId('reader')).toHaveTextContent('A')
    expect(screen.getByTestId('reader')).not.toHaveTextContent('B')
  })
})
```

- [ ] **Step 2: Run and confirm it fails** — `npx vitest run src/components/RibbonContext.test.tsx` — expect `Cannot find module './RibbonContext'`.

- [ ] **Step 3: Implement**

```tsx
// frontend/src/components/RibbonContext.tsx
import React, { createContext, useContext, useState, useCallback, ReactNode } from 'react'

export type RibbonTab = 'home' | 'insert' | 'modeling' | 'view'

interface RibbonState {
  tabs: Record<RibbonTab, ReactNode>
  setTabContent: (tab: RibbonTab, content: ReactNode) => void
  clearTabContent: (tab: RibbonTab) => void
}

const EMPTY_TABS: Record<RibbonTab, ReactNode> = { home: null, insert: null, modeling: null, view: null }

const RibbonContext = createContext<RibbonState | null>(null)

export function RibbonProvider({ children }: { children: ReactNode }) {
  const [tabs, setTabs] = useState<Record<RibbonTab, ReactNode>>(EMPTY_TABS)

  const setTabContent = useCallback((tab: RibbonTab, content: ReactNode) => {
    setTabs(prev => ({ ...prev, [tab]: content }))
  }, [])

  const clearTabContent = useCallback((tab: RibbonTab) => {
    setTabs(prev => ({ ...prev, [tab]: null }))
  }, [])

  return (
    <RibbonContext.Provider value={{ tabs, setTabContent, clearTabContent }}>
      {children}
    </RibbonContext.Provider>
  )
}

export function useRibbon(): RibbonState {
  const ctx = useContext(RibbonContext)
  if (!ctx) throw new Error('useRibbon must be used inside RibbonProvider')
  return ctx
}
```

- [ ] **Step 4: Run and confirm it passes** — `npx vitest run src/components/RibbonContext.test.tsx`

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/RibbonContext.tsx frontend/src/components/RibbonContext.test.tsx
git commit -m "Add RibbonContext for contextual ribbon-tab content injection"
```

---

### Task 2: Ribbon component

**Files:**
- Create: `frontend/src/components/Ribbon.tsx`
- Test: `frontend/src/components/Ribbon.test.tsx`

**Interfaces:**
- Consumes: `useRibbon()` from Task 1.
- Produces: `Ribbon` (default export, no props) — renders the 4 tab buttons + active tab's content;
  clicking a tab button sets it active; `Ctrl+F6` focuses the first tab button.

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/Ribbon.test.tsx
import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import Ribbon from './Ribbon'
import { RibbonProvider, useRibbon } from './RibbonContext'
import { useEffect } from 'react'

function Seed() {
  const { setTabContent } = useRibbon()
  useEffect(() => {
    setTabContent('home', <button>Upload</button>)
    setTabContent('insert', <button>Add Visual</button>)
  }, [setTabContent])
  return null
}

function renderRibbon() {
  return render(
    <RibbonProvider>
      <Seed />
      <Ribbon />
    </RibbonProvider>
  )
}

describe('Ribbon', () => {
  it('shows all four tab labels', () => {
    renderRibbon()
    expect(screen.getByRole('tab', { name: 'Home' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Insert' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Modeling' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'View' })).toBeInTheDocument()
  })

  it('shows Home tab content by default', () => {
    renderRibbon()
    expect(screen.getByRole('button', { name: 'Upload' })).toBeVisible()
  })

  it('switches content when a different tab is clicked', () => {
    renderRibbon()
    fireEvent.click(screen.getByRole('tab', { name: 'Insert' }))
    expect(screen.getByRole('button', { name: 'Add Visual' })).toBeVisible()
  })

  it('marks the active tab with aria-selected', () => {
    renderRibbon()
    fireEvent.click(screen.getByRole('tab', { name: 'Insert' }))
    expect(screen.getByRole('tab', { name: 'Insert' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tab', { name: 'Home' })).toHaveAttribute('aria-selected', 'false')
  })
})
```

- [ ] **Step 2: Run and confirm it fails** — `npx vitest run src/components/Ribbon.test.tsx`

- [ ] **Step 3: Implement**

```tsx
// frontend/src/components/Ribbon.tsx
import { useState, useRef, useEffect } from 'react'
import { useRibbon, RibbonTab } from './RibbonContext'

const TAB_LABELS: { key: RibbonTab; label: string }[] = [
  { key: 'home', label: 'Home' },
  { key: 'insert', label: 'Insert' },
  { key: 'modeling', label: 'Modeling' },
  { key: 'view', label: 'View' },
]

export default function Ribbon() {
  const { tabs } = useRibbon()
  const [active, setActive] = useState<RibbonTab>('home')
  const tabRefs = useRef<Record<RibbonTab, HTMLButtonElement | null>>({ home: null, insert: null, modeling: null, view: null })

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.ctrlKey && e.key === 'F6') {
        e.preventDefault()
        tabRefs.current[active]?.focus()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [active])

  const handleTabKeyDown = (e: React.KeyboardEvent, idx: number) => {
    if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return
    e.preventDefault()
    const dir = e.key === 'ArrowRight' ? 1 : -1
    const nextIdx = (idx + dir + TAB_LABELS.length) % TAB_LABELS.length
    const nextTab = TAB_LABELS[nextIdx].key
    setActive(nextTab)
    tabRefs.current[nextTab]?.focus()
  }

  return (
    <div style={{ borderBottom: '1px solid var(--border)', background: 'var(--surface)', flexShrink: 0 }}>
      <div role="tablist" aria-label="Ribbon" style={{ display: 'flex', gap: 2, padding: '0 12px' }}>
        {TAB_LABELS.map(({ key, label }, idx) => (
          <button
            key={key}
            ref={el => { tabRefs.current[key] = el }}
            role="tab"
            aria-selected={active === key}
            tabIndex={active === key ? 0 : -1}
            onClick={() => setActive(key)}
            onKeyDown={e => handleTabKeyDown(e, idx)}
            style={{
              padding: '8px 14px', border: 'none', background: 'none', cursor: 'pointer',
              fontSize: 12, fontWeight: active === key ? 700 : 400,
              color: active === key ? 'var(--accent)' : 'var(--muted)',
              borderBottom: active === key ? '2px solid var(--accent)' : '2px solid transparent',
              fontFamily: 'var(--sans)',
            }}
          >
            {label}
          </button>
        ))}
      </div>
      <div style={{ padding: '8px 12px', minHeight: 40, display: 'flex', alignItems: 'center', gap: 8 }}>
        {tabs[active]}
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Run and confirm it passes** — `npx vitest run src/components/Ribbon.test.tsx`

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/Ribbon.tsx frontend/src/components/Ribbon.test.tsx
git commit -m "Add Ribbon component: 4 fixed tabs with keyboard navigation"
```

---

### Task 3: Layout.tsx — icon rail + ribbon replace the sidebar

**Files:**
- Modify: `frontend/src/components/Layout.tsx` (full rewrite of the `nav` block, lines 30-102)
- Test: `frontend/src/components/Layout.test.tsx`

**Interfaces:**
- Consumes: `RibbonProvider`, `Ribbon` (Task 1-2).
- Produces: `Layout` still default-exports a component rendering `<Outlet/>`; no prop/behavior
  contract other tasks depend on beyond "the ribbon is present and app-wide."

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/Layout.test.tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import Layout from './Layout'

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({ user: { email: 'a@b.com', role: { is_org_admin: true, name: 'Admin' }, organization: { name: 'Acme' } }, logout: vi.fn() }),
}))

function renderLayout() {
  return render(
    <MemoryRouter initialEntries={['/']}>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<div>Page Content</div>} />
        </Route>
      </Routes>
    </MemoryRouter>
  )
}

describe('Layout', () => {
  it('renders the ribbon tabs', () => {
    renderLayout()
    expect(screen.getByRole('tab', { name: 'Home' })).toBeInTheDocument()
  })

  it('renders icon-rail navigation links', () => {
    renderLayout()
    expect(screen.getByRole('link', { name: /Datasets/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Reports/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Connections/i })).toBeInTheDocument()
  })

  it('still renders the routed page content', () => {
    renderLayout()
    expect(screen.getByText('Page Content')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run and confirm it fails** — `npx vitest run src/components/Layout.test.tsx` — fails on missing ribbon tab role.

- [ ] **Step 3: Implement** — replace the file's `nav` block. The icon rail keeps the same links,
  now icon-only (44px wide) with `title` tooltips instead of text labels; the ribbon sits above the
  routed content.

```tsx
// frontend/src/components/Layout.tsx
import { useState, useEffect } from 'react'
import { Outlet, NavLink } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
import { RibbonProvider } from './RibbonContext'
import Ribbon from './Ribbon'

function getInitialTheme(): 'dark' | 'light' {
  const stored = localStorage.getItem('theme')
  if (stored === 'light' || stored === 'dark') return stored
  return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'
}

const railLinkStyle = ({ isActive }: { isActive: boolean }): React.CSSProperties => ({
  display: 'flex', alignItems: 'center', justifyContent: 'center',
  width: 40, height: 40, borderRadius: 8, textDecoration: 'none', fontSize: 17,
  color: isActive ? 'var(--accent)' : 'var(--muted)',
  background: isActive ? 'rgba(108,143,255,.1)' : 'transparent',
})

export default function Layout() {
  const [theme, setTheme] = useState<'dark' | 'light'>(getInitialTheme)

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('theme', theme)
  }, [theme])

  const toggle = () => setTheme(t => t === 'dark' ? 'light' : 'dark')
  const { user, logout } = useAuth()

  return (
    <RibbonProvider>
      <div style={{ display: 'flex', height: '100%' }}>
        {/* Icon rail */}
        <nav style={{
          width: 56, flexShrink: 0,
          background: 'var(--surface)', borderRight: '1px solid var(--border)',
          display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '14px 8px', gap: 6,
        }}>
          <div style={{ fontWeight: 800, fontSize: 15, color: 'var(--accent)', marginBottom: 10 }} title="Datalytics">D</div>
          <NavLink to="/" end style={railLinkStyle} title="Datasets" aria-label="Datasets">⊞</NavLink>
          <NavLink to="/upload" style={railLinkStyle} title="Upload" aria-label="Upload">↑</NavLink>
          <NavLink to="/reports" style={railLinkStyle} title="Reports" aria-label="Reports">📊</NavLink>
          <NavLink to="/connections" style={railLinkStyle} title="Connections" aria-label="Connections">🔌</NavLink>

          {user?.role.is_org_admin && (
            <>
              <div style={{ borderTop: '1px solid var(--border)', width: 28, margin: '6px 0' }} />
              <NavLink to="/admin/users" style={railLinkStyle} title="Users" aria-label="Users">👤</NavLink>
              <NavLink to="/admin/roles" style={railLinkStyle} title="Roles" aria-label="Roles">🛡</NavLink>
              <NavLink to="/admin/row-security-rules" style={railLinkStyle} title="Row Security" aria-label="Row Security">🔒</NavLink>
            </>
          )}

          <div style={{ flex: 1 }} />

          <button
            onClick={toggle}
            title={theme === 'dark' ? 'Light mode' : 'Dark mode'}
            style={{ ...railLinkStyle({ isActive: false }), border: 'none', cursor: 'pointer' }}
          >
            {theme === 'dark' ? '☀' : '☾'}
          </button>

          {user && (
            <button
              onClick={logout}
              title={`${user.email} — Log out`}
              style={{ ...railLinkStyle({ isActive: false }), border: 'none', cursor: 'pointer', fontSize: 14 }}
            >
              ⎋
            </button>
          )}
        </nav>

        {/* Ribbon + routed content */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
          <Ribbon />
          <main style={{ flex: 1, overflow: 'auto', padding: 28, background: 'var(--bg)' }}>
            <Outlet />
          </main>
        </div>
      </div>
    </RibbonProvider>
  )
}
```

- [ ] **Step 4: Run and confirm it passes** — `npx vitest run src/components/Layout.test.tsx`

- [ ] **Step 5: Run the full frontend suite to check for regressions** — `npx vitest run` — fix any
  test that asserted on the old sidebar's text labels (search for `getByText('Datasets')`-style
  assertions against nav links in other test files first).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/Layout.tsx frontend/src/components/Layout.test.tsx
git commit -m "Replace Layout sidebar with icon rail + global ribbon"
```

---

### Task 4: Bring ReportBuilder under Layout; remove its duplicate nav

**Files:**
- Modify: `frontend/src/App.tsx:36-38`
- Modify: `frontend/src/pages/ReportBuilder.tsx:280-300` (the duplicate top nav block)

**Interfaces:**
- Consumes: nothing new.
- Produces: `reports/:id` now renders inside `<Layout>`, so `Ribbon`/`RibbonProvider` wrap it too.

- [ ] **Step 1: Move the route.** In `App.tsx`, move the `reports/:id` route to be a child of the
  `Layout` route instead of a sibling:

```tsx
// Before:
//   <Route path="/" element={<Layout />}> ... </Route>
//   <Route path="reports/:id" element={<ReportBuilder />} />
// After:
<Route path="/" element={<Layout />}>
  <Route index element={<Dashboard />} />
  <Route path="upload" element={<Upload />} />
  <Route path="datasets/:id" element={<DatasetDetail />} />
  <Route path="reports" element={<Reports />} />
  <Route path="reports/:id" element={<ReportBuilder />} />
  <Route path="connections" element={<Connections />} />
  <Route element={<RequireAdmin />}>
    <Route path="admin/roles" element={<AdminRoles />} />
    <Route path="admin/users" element={<AdminUsers />} />
    <Route path="admin/row-security-rules" element={<AdminRowSecurityRules />} />
  </Route>
</Route>
```

Remove the now-stale comment `{/* ReportBuilder is full-page — its own sidebar replaces the global Layout */}`.

- [ ] **Step 2: Remove ReportBuilder's duplicate nav.** Find and delete the `<nav>` block containing
  the `NavLink to="/" `/`upload`/`reports` links (currently around line 295-298 — search for
  `⊞ Datasets` inside `ReportBuilder.tsx` to locate it precisely, since exact line numbers shift as
  earlier tasks land). Leave the "Analytics" section / Widgets-Data-View tabs below it untouched for
  now (Task 8 relocates the Widgets tab into the ribbon).

- [ ] **Step 3: Manually verify** — run the app (`npm run dev` in `frontend/`), open a report, and
  confirm: the icon rail and ribbon appear above/beside the report editor exactly as they do on
  every other page, and clicking Datasets/Reports/Connections in the rail navigates correctly from
  inside an open report.

- [ ] **Step 4: Run the full frontend suite** — `npx vitest run` — fix any test asserting on
  ReportBuilder's old duplicate nav.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/App.tsx frontend/src/pages/ReportBuilder.tsx
git commit -m "Bring ReportBuilder under the global Layout shell"
```

---

## PHASE 2 — Report/Data/Model View Switcher

### Task 5: View strip + view state in ReportBuilder

**Files:**
- Modify: `frontend/src/pages/ReportBuilder.tsx`
- Test: extend `frontend/src/pages/ReportBuilder.test.tsx` (new file if none exists — check first;
  none was found earlier this session, so create it)

**Interfaces:**
- Produces: a new `activeView` state (`'report' | 'data' | 'model'`, default `'report'`) and a
  left-edge icon strip that sets it. `DataView`/`ModelView` (Tasks 6-7) are rendered conditionally
  on this state.

- [ ] **Step 1: Write the failing test** — a minimal smoke test asserting the strip exists and
  switches which view renders (using the same `datasetsApi`/`reportsApi` mocking pattern as
  `DatasetDetail.test.tsx`):

```tsx
// frontend/src/pages/ReportBuilder.test.tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import ReportBuilder from './ReportBuilder'
import { reportsApi, datasetsApi } from '../services/api'

vi.mock('../services/api', () => ({
  reportsApi: {
    get: vi.fn(), update: vi.fn(), addPage: vi.fn(), updatePage: vi.fn(), deletePage: vi.fn(),
    addWidget: vi.fn(), updateWidget: vi.fn(), deleteWidget: vi.fn(),
  },
  datasetsApi: { get: vi.fn(), list: vi.fn() },
  hierarchyApi: { get: vi.fn() },
}))

function baseReport() {
  return {
    id: 1, name: 'Sales', dataset_id: 10, additional_dataset_ids: [], created_at: '2026-01-01', updated_at: '2026-01-01',
    pages: [{ id: 100, report_id: 1, name: 'Page 1', page_type: 'normal', position: 0, widgets: [], created_at: '2026-01-01' }],
  }
}

function renderBuilder() {
  return render(
    <MemoryRouter initialEntries={['/reports/1']}>
      <Routes><Route path="/reports/:id" element={<ReportBuilder />} /></Routes>
    </MemoryRouter>
  )
}

describe('ReportBuilder view switcher', () => {
  it('shows Report/Data/Model view icons and defaults to Report', async () => {
    vi.mocked(reportsApi.get).mockResolvedValue(baseReport() as any)
    vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales Data', columns: [] } as any)
    renderBuilder()
    expect(await screen.findByRole('button', { name: /Report/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^Data$/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Model/i })).toBeInTheDocument()
  })

  it('switches to the Model view placeholder when clicked', async () => {
    vi.mocked(reportsApi.get).mockResolvedValue(baseReport() as any)
    vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales Data', columns: [] } as any)
    renderBuilder()
    fireEvent.click(await screen.findByRole('button', { name: /Model/i }))
    expect(await screen.findByTestId('model-view')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run and confirm it fails.**

- [ ] **Step 3: Implement.** Add near the top of the `ReportBuilder` function body (alongside the
  other `useState` calls):

```tsx
const [activeView, setActiveView] = useState<'report' | 'data' | 'model'>('report')
```

Add the icon strip immediately above the existing canvas render, and wrap the existing canvas JSX
so it only renders when `activeView === 'report'`:

```tsx
<div style={{ display: 'flex', gap: 4, padding: '6px 12px', borderBottom: '1px solid var(--border)' }}>
  {(['report', 'data', 'model'] as const).map(v => (
    <button key={v} onClick={() => setActiveView(v)}
      style={{ padding: '5px 12px', border: 'none', borderRadius: 6, cursor: 'pointer', fontSize: 12,
        background: activeView === v ? 'var(--accent)' : 'transparent',
        color: activeView === v ? '#fff' : 'var(--muted)' }}>
      {v === 'report' ? '📊 Report' : v === 'data' ? '🗂 Data' : '🔗 Model'}
    </button>
  ))}
</div>
{activeView === 'report' && ( /* existing canvas JSX goes here, unchanged */ )}
{activeView === 'data' && dataset && <DataView datasetId={dataset.id} />}
{activeView === 'model' && report && <ModelView report={report} datasets={datasets} />}
```

(`DataView`/`ModelView` don't exist yet — Tasks 6-7 create them. For this task, stub them inline as
placeholders returning `<div data-testid="model-view">Model view</div>` /
`<div data-testid="data-view">Data view</div>` so this task's test passes without depending on
later tasks; Tasks 6-7 replace the stubs with real imports.)

- [ ] **Step 4: Run and confirm it passes.**

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/ReportBuilder.tsx frontend/src/pages/ReportBuilder.test.tsx
git commit -m "Add Report/Data/Model view switcher to the report editor"
```

---

### Task 6: DataView component

**Files:**
- Create: `frontend/src/components/report/DataView.tsx`
- Test: `frontend/src/components/report/DataView.test.tsx`

**Interfaces:**
- Consumes: `dataPreviewApi.query` (existing, `frontend/src/services/api.ts`).
- Produces: `DataView({ datasetId }: { datasetId: number })` — default export.

**Deliberately minimal v1** (documented in the spec as a pragmatic scope call, not the full
DatasetDetail feature set): a read-only paginated grid, no filter/sort/search UI. Those exist
already on `DatasetDetail.tsx`'s own Data tab for standalone dataset browsing; this view is for
quick reference while building a report, not a replacement for that page.

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/report/DataView.test.tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import DataView from './DataView'
import { dataPreviewApi } from '../../services/api'

vi.mock('../../services/api', () => ({ dataPreviewApi: { query: vi.fn() } }))

describe('DataView', () => {
  it('renders a table of the dataset rows', async () => {
    vi.mocked(dataPreviewApi.query).mockResolvedValue({
      columns: ['region', 'revenue'], rows: [['east', 100], ['west', 50]], total: 2,
    })
    render(<DataView datasetId={10} />)
    expect(await screen.findByText('east')).toBeInTheDocument()
    expect(screen.getByText('west')).toBeInTheDocument()
    expect(dataPreviewApi.query).toHaveBeenCalledWith(10, [], [], 100, 0)
  })

  it('shows a loading state before data arrives', () => {
    vi.mocked(dataPreviewApi.query).mockReturnValue(new Promise(() => {}))
    render(<DataView datasetId={10} />)
    expect(screen.getByText(/Loading/i)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run and confirm it fails.**

- [ ] **Step 3: Implement**

```tsx
// frontend/src/components/report/DataView.tsx
import { useEffect, useState } from 'react'
import { dataPreviewApi } from '../../services/api'

export default function DataView({ datasetId }: { datasetId: number }) {
  const [data, setData] = useState<{ columns: string[]; rows: unknown[][]; total: number } | null>(null)

  useEffect(() => {
    setData(null)
    dataPreviewApi.query(datasetId, [], [], 100, 0).then(setData)
  }, [datasetId])

  if (!data) return <p style={{ color: 'var(--muted)', padding: 16 }}>Loading…</p>

  return (
    <div style={{ overflow: 'auto', padding: 12 }}>
      <table style={{ fontSize: 12 }}>
        <thead><tr>{data.columns.map(c => <th key={c}>{c}</th>)}</tr></thead>
        <tbody>
          {data.rows.map((row, i) => (
            <tr key={i}>{(row as unknown[]).map((v, j) => <td key={j}>{v == null ? '—' : String(v)}</td>)}</tr>
          ))}
        </tbody>
      </table>
      <p style={{ fontSize: 11, color: 'var(--muted)', marginTop: 8 }}>Showing {data.rows.length} of {data.total} rows</p>
    </div>
  )
}
```

- [ ] **Step 4: Run and confirm it passes.**

- [ ] **Step 5: Wire it into ReportBuilder** — replace Task 5's inline `data-view` stub:

```tsx
import DataView from '../components/report/DataView'
// ...
{activeView === 'data' && dataset && <DataView datasetId={dataset.id} />}
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/report/DataView.tsx frontend/src/components/report/DataView.test.tsx frontend/src/pages/ReportBuilder.tsx
git commit -m "Add read-only DataView for the report editor's Data view"
```

---

### Task 7: ModelView placeholder

**Files:**
- Create: `frontend/src/components/report/ModelView.tsx`
- Test: `frontend/src/components/report/ModelView.test.tsx`

**Interfaces:**
- Produces: `ModelView({ report, datasets }: { report: Report; datasets: Record<number, Dataset> })`
  — default export. Phase 2 ships an empty state only; Task 13 replaces the body with the real
  diagram once `Relationship` (Task 9-11) exists.

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/report/ModelView.test.tsx
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import ModelView from './ModelView'

describe('ModelView', () => {
  it('renders the model-view container', () => {
    render(<ModelView report={{ id: 1, dataset_id: 10, additional_dataset_ids: [] } as any} datasets={{}} />)
    expect(screen.getByTestId('model-view')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run and confirm it fails.**

- [ ] **Step 3: Implement**

```tsx
// frontend/src/components/report/ModelView.tsx
import type { Report, Dataset } from '../../services/api'

export default function ModelView({ report, datasets }: { report: Report; datasets: Record<number, Dataset> }) {
  const datasetIds = [report.dataset_id, ...(report.additional_dataset_ids ?? [])].filter((id): id is number => id != null)

  return (
    <div data-testid="model-view" style={{ padding: 16 }}>
      {datasetIds.length < 2 ? (
        <p style={{ color: 'var(--muted)', fontSize: 13 }}>
          Add a second dataset to this report (via the Data tab in report settings) to define relationships between them.
        </p>
      ) : (
        <p style={{ color: 'var(--muted)', fontSize: 13 }}>Relationship diagram coming up next.</p>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Run and confirm it passes.**

- [ ] **Step 5: Wire it into ReportBuilder** — replace Task 5's inline `model-view` stub:

```tsx
import ModelView from '../components/report/ModelView'
// ...
{activeView === 'model' && report && <ModelView report={report} datasets={datasets} />}
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/report/ModelView.tsx frontend/src/components/report/ModelView.test.tsx frontend/src/pages/ReportBuilder.tsx
git commit -m "Add ModelView placeholder ahead of relationship metadata"
```

---

### Task 8: Relocate the widget catalog (Insert) into the ribbon

**Files:**
- Modify: `frontend/src/pages/ReportBuilder.tsx`

**Interfaces:**
- Consumes: `useRibbon()` (Task 1), existing `WIDGET_CATALOG` (`frontend/src/types/report.ts`) and
  `addWidget` function already defined in `ReportBuilder.tsx`.

- [ ] **Step 1: Write the failing test** — extend `ReportBuilder.test.tsx`:

```tsx
it('puts the widget catalog in the ribbon Insert tab, not a side panel', async () => {
  vi.mocked(reportsApi.get).mockResolvedValue(baseReport() as any)
  vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales Data', columns: [] } as any)
  render(
    <MemoryRouter initialEntries={['/reports/1']}>
      <Routes><Route path="/reports/:id" element={<ReportBuilder />} /></Routes>
    </MemoryRouter>
  )
  await screen.findByRole('button', { name: /Report/i })
  // Insert tab content is injected via RibbonContext, which ReportBuilder must be wrapped in for
  // this test -- if ReportBuilder is rendered standalone (not under Layout) in this test file,
  // wrap it in <RibbonProvider> here so useRibbon() doesn't throw.
})
```

  (This task's real verification is manual + the full suite, since asserting ribbon content from
  a component not wrapped in `Layout` requires wrapping the test render in `RibbonProvider`
  directly — do that in this test file's render helper: wrap the `<Routes>` in `<RibbonProvider>`.)

- [ ] **Step 2: Implement.** In `ReportBuilder.tsx`, import `useRibbon` and, in a `useEffect`
  keyed on `editMode` (so the catalog only appears in the ribbon while editing, matching today's
  `!editMode` guard), inject the existing catalog grid JSX into the `insert` tab and clear it on
  unmount:

```tsx
import { useRibbon } from '../components/RibbonContext'
// ...
const { setTabContent, clearTabContent } = useRibbon()
useEffect(() => {
  setTabContent('insert', (
    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
      {WIDGET_CATALOG.map(w => (
        <button key={w.type} onClick={() => editMode && addWidget(w.type)}
          disabled={!editMode}
          style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2, padding: '6px 10px',
            background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 6,
            cursor: editMode ? 'pointer' : 'default', fontSize: 10, opacity: editMode ? 1 : 0.45 }}>
          <span style={{ fontSize: 15 }}>{w.icon}</span>
          <span>{w.label}</span>
        </button>
      ))}
    </div>
  ))
  return () => clearTabContent('insert')
}, [editMode, setTabContent, clearTabContent])
```

Then remove the `'widgets'` branch of the old `leftPanel` toggle (and the `leftPanel` state/tabs
entirely, since Widgets moved to the ribbon and Data-View's fields list is kept as-is under a
simplified always-visible panel — no toggle needed once there's only one thing left in it).

- [ ] **Step 3: Run the full frontend suite** — `npx vitest run` — fix fallout.

- [ ] **Step 4: Manually verify** — open a report in edit mode, confirm the widget catalog appears
  under the ribbon's Insert tab and clicking an icon adds that widget type to the canvas, exactly
  as the old left-panel button did.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/ReportBuilder.tsx frontend/src/pages/ReportBuilder.test.tsx
git commit -m "Move widget catalog from side panel into ribbon Insert tab"
```

---

## PHASE 3 — Relationship Metadata (backend)

### Task 9: Relationship model + migration

**Files:**
- Modify: `backend/app/models/models.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_relationship_model.py`

**Interfaces:**
- Produces: `Relationship` ORM class — `id, org_id, from_dataset_id, from_column, to_dataset_id, to_column, created_at`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_relationship_model.py
from app.models.models import Relationship


async def test_relationship_persists_join_key(db_session):
    from app.models.models import Dataset, Organization
    org = Organization(name="Acme")
    db_session.add(org)
    await db_session.flush()
    orders = Dataset(name="Orders", org_id=org.id)
    customers = Dataset(name="Customers", org_id=org.id)
    db_session.add_all([orders, customers])
    await db_session.flush()

    rel = Relationship(
        org_id=org.id, from_dataset_id=orders.id, from_column="customer_id",
        to_dataset_id=customers.id, to_column="id",
    )
    db_session.add(rel)
    await db_session.commit()
    await db_session.refresh(rel)

    assert rel.from_column == "customer_id"
    assert rel.to_column == "id"
```

- [ ] **Step 2: Run and confirm it fails** — `python -m pytest tests/test_relationship_model.py -q` — `ImportError`.

- [ ] **Step 3: Implement.** Add to `models.py` after the `RowSecurityRule` class:

```python
class Relationship(Base):
    __tablename__ = "relationships"
    id              = Column(Integer, primary_key=True)
    org_id          = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    from_dataset_id = Column(Integer, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)
    from_column     = Column(String(255), nullable=False)
    to_dataset_id   = Column(Integer, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)
    to_column       = Column(String(255), nullable=False)
    created_at      = Column(DateTime(timezone=True), default=datetime.utcnow)

    from_dataset = relationship("Dataset", foreign_keys=[from_dataset_id])
    to_dataset   = relationship("Dataset", foreign_keys=[to_dataset_id])
```

No `_migrate()` statement is needed for the table itself — `Base.metadata.create_all` in
`main.py`'s `lifespan` already creates any brand-new table automatically (established convention,
see the RLS spec's Migrations section: this is how `organizations`/`roles`/`users` were added).

- [ ] **Step 4: Run and confirm it passes.**

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/models.py backend/tests/test_relationship_model.py
git commit -m "Add Relationship model (join-key-only dataset relationships)"
```

---

### Task 10: Relationship schemas

**Files:**
- Modify: `backend/app/schemas/schemas.py`

**Interfaces:**
- Produces: `RelationshipCreate { from_dataset_id: int, from_column: str, to_dataset_id: int, to_column: str }`,
  `RelationshipOut { id, org_id, from_dataset_id, from_column, to_dataset_id, to_column, created_at }`.
  No `RelationshipUpdate` — relationships are delete-and-recreate, not edited in place (matches the
  spec's "simple join key only" framing; nothing partial to update).

- [ ] **Step 1: Add to `schemas.py`**, after `RowSecurityRuleOut`:

```python
class RelationshipCreate(BaseModel):
    from_dataset_id: int
    from_column: str
    to_dataset_id: int
    to_column: str


class RelationshipOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    org_id: int
    from_dataset_id: int
    from_column: str
    to_dataset_id: int
    to_column: str
    created_at: datetime
```

(No test file — this is a plain Pydantic model with no logic; it's exercised by Task 11's router
tests.)

- [ ] **Step 2: Commit**

```bash
git add backend/app/schemas/schemas.py
git commit -m "Add Relationship request/response schemas"
```

---

### Task 11: Relationship CRUD router

**Files:**
- Create: `backend/app/routers/relationships.py`
- Modify: `backend/app/main.py` (register the router)
- Test: `backend/tests/test_relationships_org_scoping.py`

**Interfaces:**
- Produces: `GET /relationships` (list, org-scoped), `POST /relationships` (create, validates
  columns exist), `DELETE /relationships/{id}` (org-scoped 404).

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_relationships_org_scoping.py
from sqlalchemy import select
from app.models.models import Dataset, DatasetColumn, Relationship


async def _seed_dataset_with_column(db_session, org_id, name, col_name):
    ds = Dataset(name=name, org_id=org_id)
    db_session.add(ds)
    await db_session.flush()
    db_session.add(DatasetColumn(dataset_id=ds.id, name=col_name, dtype="numeric"))
    await db_session.commit()
    await db_session.refresh(ds)
    return ds


async def test_create_relationship_with_valid_columns(client, db_session, two_orgs, auth_headers):
    org_id = two_orgs["a"]["org"].id
    orders = await _seed_dataset_with_column(db_session, org_id, "Orders", "customer_id")
    customers = await _seed_dataset_with_column(db_session, org_id, "Customers", "id")

    resp = await client.post(
        "/api/v1/relationships",
        json={"from_dataset_id": orders.id, "from_column": "customer_id", "to_dataset_id": customers.id, "to_column": "id"},
        headers=auth_headers["a"],
    )

    assert resp.status_code == 200
    result = await db_session.execute(select(Relationship).where(Relationship.id == resp.json()["id"]))
    assert result.scalar_one() is not None


async def test_create_relationship_rejects_unknown_column(client, db_session, two_orgs, auth_headers):
    org_id = two_orgs["a"]["org"].id
    orders = await _seed_dataset_with_column(db_session, org_id, "Orders", "customer_id")
    customers = await _seed_dataset_with_column(db_session, org_id, "Customers", "id")

    resp = await client.post(
        "/api/v1/relationships",
        json={"from_dataset_id": orders.id, "from_column": "does_not_exist", "to_dataset_id": customers.id, "to_column": "id"},
        headers=auth_headers["a"],
    )

    assert resp.status_code == 400


async def test_create_relationship_cross_org_dataset_returns_404(client, db_session, two_orgs, auth_headers):
    org_b_ds = await _seed_dataset_with_column(db_session, two_orgs["b"]["org"].id, "Other Org Data", "id")
    orders = await _seed_dataset_with_column(db_session, two_orgs["a"]["org"].id, "Orders", "customer_id")

    resp = await client.post(
        "/api/v1/relationships",
        json={"from_dataset_id": orders.id, "from_column": "customer_id", "to_dataset_id": org_b_ds.id, "to_column": "id"},
        headers=auth_headers["a"],
    )

    assert resp.status_code == 404


async def test_list_relationships_only_returns_own_org(client, db_session, two_orgs, auth_headers):
    org_id = two_orgs["a"]["org"].id
    orders = await _seed_dataset_with_column(db_session, org_id, "Orders", "customer_id")
    customers = await _seed_dataset_with_column(db_session, org_id, "Customers", "id")
    db_session.add(Relationship(org_id=org_id, from_dataset_id=orders.id, from_column="customer_id", to_dataset_id=customers.id, to_column="id"))
    db_session.add(Relationship(org_id=two_orgs["b"]["org"].id, from_dataset_id=orders.id, from_column="x", to_dataset_id=customers.id, to_column="y"))
    await db_session.commit()

    resp = await client.get("/api/v1/relationships", headers=auth_headers["a"])

    assert resp.status_code == 200
    assert len(resp.json()) == 1


async def test_delete_relationship_cross_org_returns_404(client, db_session, two_orgs, auth_headers):
    org_id = two_orgs["b"]["org"].id
    orders = await _seed_dataset_with_column(db_session, org_id, "Orders", "customer_id")
    customers = await _seed_dataset_with_column(db_session, org_id, "Customers", "id")
    rel = Relationship(org_id=org_id, from_dataset_id=orders.id, from_column="customer_id", to_dataset_id=customers.id, to_column="id")
    db_session.add(rel)
    await db_session.commit()
    await db_session.refresh(rel)

    resp = await client.delete(f"/api/v1/relationships/{rel.id}", headers=auth_headers["a"])

    assert resp.status_code == 404
```

- [ ] **Step 2: Run and confirm all 5 fail** — `python -m pytest tests/test_relationships_org_scoping.py -q` — `404 Not Found` on every request (route doesn't exist).

- [ ] **Step 3: Implement the router**

```python
# backend/app/routers/relationships.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..core.database import get_db
from ..core.org_scope import check_org
from ..dependencies import get_current_user
from ..models.models import Dataset, DatasetColumn, Relationship, User
from ..schemas.schemas import RelationshipCreate, RelationshipOut

router = APIRouter(prefix="/relationships", tags=["relationships"])


async def _check_column_exists(db: AsyncSession, dataset_id: int, column: str) -> None:
    result = await db.execute(
        select(DatasetColumn).where(DatasetColumn.dataset_id == dataset_id, DatasetColumn.name == column)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(400, f"Column '{column}' does not exist on dataset {dataset_id}")


@router.get("", response_model=list[RelationshipOut])
async def list_relationships(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(select(Relationship).where(Relationship.org_id == current_user.org_id))
    return result.scalars().all()


@router.post("", response_model=RelationshipOut)
async def create_relationship(body: RelationshipCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    from_ds = await db.get(Dataset, body.from_dataset_id)
    check_org(from_ds, current_user, "Dataset not found")
    to_ds = await db.get(Dataset, body.to_dataset_id)
    check_org(to_ds, current_user, "Dataset not found")

    await _check_column_exists(db, body.from_dataset_id, body.from_column)
    await _check_column_exists(db, body.to_dataset_id, body.to_column)

    rel = Relationship(
        org_id=current_user.org_id, from_dataset_id=body.from_dataset_id, from_column=body.from_column,
        to_dataset_id=body.to_dataset_id, to_column=body.to_column,
    )
    db.add(rel)
    await db.commit()
    await db.refresh(rel)
    return rel


@router.delete("/{relationship_id}", status_code=204)
async def delete_relationship(relationship_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    rel = await db.get(Relationship, relationship_id)
    check_org(rel, current_user, "Relationship not found")
    await db.delete(rel)
    await db.commit()
```

- [ ] **Step 4: Register the router in `main.py`**

```python
from .routers import relationships
# ...
app.include_router(relationships.router, prefix="/api/v1")
```

- [ ] **Step 5: Run and confirm all 5 pass.**

- [ ] **Step 6: Run the full backend suite** — `python -m pytest tests/ -q` — confirm no regressions.

- [ ] **Step 7: Commit**

```bash
git add backend/app/routers/relationships.py backend/app/main.py backend/tests/test_relationships_org_scoping.py
git commit -m "Add Relationship CRUD API, validated like RowSecurityRule"
```

---

## PHASE 4 — Model View Diagram

### Task 12: relationshipsApi client

**Files:**
- Modify: `frontend/src/services/api.ts`

**Interfaces:**
- Produces: `Relationship` interface + `relationshipsApi.{list, create, delete}`.

- [ ] **Step 1: Add to `api.ts`**, after `filterExprApi`:

```ts
export interface Relationship {
  id: number
  org_id: number
  from_dataset_id: number
  from_column: string
  to_dataset_id: number
  to_column: string
  created_at: string
}

export const relationshipsApi = {
  list:   ()                                                                          => api.get<Relationship[]>('/relationships').then(r => r.data),
  create: (body: { from_dataset_id: number; from_column: string; to_dataset_id: number; to_column: string }) =>
    api.post<Relationship>('/relationships', body).then(r => r.data),
  delete: (id: number)                                                                => api.delete(`/relationships/${id}`),
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/services/api.ts
git commit -m "Add relationshipsApi client"
```

---

### Task 13: ModelView diagram

**Files:**
- Modify: `frontend/src/components/report/ModelView.tsx`
- Modify: `frontend/src/components/report/ModelView.test.tsx`

**Interfaces:**
- Consumes: `relationshipsApi` (Task 12).
- Produces: same `ModelView` signature as Task 7, now with real content.

- [ ] **Step 1: Write the failing test** (replaces Task 7's test)

```tsx
// frontend/src/components/report/ModelView.test.tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import ModelView from './ModelView'
import { relationshipsApi } from '../../services/api'

vi.mock('../../services/api', () => ({ relationshipsApi: { list: vi.fn(), create: vi.fn(), delete: vi.fn() } }))

const REPORT = { id: 1, dataset_id: 10, additional_dataset_ids: [20] } as any
const DATASETS = {
  10: { id: 10, name: 'Orders', columns: [{ id: 1, name: 'customer_id', dtype: 'numeric', missing_pct: 0, stats: {} }] },
  20: { id: 20, name: 'Customers', columns: [{ id: 2, name: 'id', dtype: 'numeric', missing_pct: 0, stats: {} }] },
} as any

describe('ModelView diagram', () => {
  it('shows a box for each dataset attached to the report', async () => {
    vi.mocked(relationshipsApi.list).mockResolvedValue([])
    render(<ModelView report={REPORT} datasets={DATASETS} />)
    expect(await screen.findByText('Orders')).toBeInTheDocument()
    expect(screen.getByText('Customers')).toBeInTheDocument()
  })

  it('shows an existing relationship between the two datasets', async () => {
    vi.mocked(relationshipsApi.list).mockResolvedValue([
      { id: 1, org_id: 1, from_dataset_id: 10, from_column: 'customer_id', to_dataset_id: 20, to_column: 'id', created_at: '2026-01-01' },
    ])
    render(<ModelView report={REPORT} datasets={DATASETS} />)
    expect(await screen.findByText(/customer_id.*↔.*id/)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run and confirm it fails.**

- [ ] **Step 3: Implement**

```tsx
// frontend/src/components/report/ModelView.tsx
import { useEffect, useState } from 'react'
import type { Report, Dataset, Relationship } from '../../services/api'
import { relationshipsApi } from '../../services/api'

export default function ModelView({ report, datasets }: { report: Report; datasets: Record<number, Dataset> }) {
  const datasetIds = [report.dataset_id, ...(report.additional_dataset_ids ?? [])].filter((id): id is number => id != null)
  const [relationships, setRelationships] = useState<Relationship[]>([])
  const [showForm, setShowForm] = useState(false)

  useEffect(() => {
    relationshipsApi.list().then(all =>
      setRelationships(all.filter(r => datasetIds.includes(r.from_dataset_id) && datasetIds.includes(r.to_dataset_id)))
    )
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [report.id])

  if (datasetIds.length < 2) {
    return (
      <div data-testid="model-view" style={{ padding: 16 }}>
        <p style={{ color: 'var(--muted)', fontSize: 13 }}>
          Add a second dataset to this report to define relationships between them.
        </p>
      </div>
    )
  }

  return (
    <div data-testid="model-view" style={{ padding: 16 }}>
      <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', marginBottom: 20 }}>
        {datasetIds.map(id => (
          <div key={id} style={{ border: '1px solid var(--border)', borderRadius: 8, padding: 10, minWidth: 160, background: 'var(--surface)' }}>
            <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 6 }}>{datasets[id]?.name ?? `Dataset ${id}`}</div>
            {(datasets[id]?.columns ?? []).map(c => (
              <div key={c.name} style={{ fontSize: 11, color: 'var(--muted)' }}>{c.name}</div>
            ))}
          </div>
        ))}
      </div>

      <div style={{ marginBottom: 12 }}>
        {relationships.map(r => (
          <div key={r.id} style={{ fontSize: 12, marginBottom: 4 }}>
            {datasets[r.from_dataset_id]?.name}.{r.from_column} ↔ {datasets[r.to_dataset_id]?.name}.{r.to_column}
          </div>
        ))}
      </div>

      <button className="btn btn-primary btn-sm" onClick={() => setShowForm(true)}>+ Add relationship</button>

      {showForm && (
        <RelationshipForm
          datasetIds={datasetIds}
          datasets={datasets}
          onCreated={rel => { setRelationships(prev => [...prev, rel]); setShowForm(false) }}
          onCancel={() => setShowForm(false)}
        />
      )}
    </div>
  )
}

function RelationshipForm({ datasetIds, datasets, onCreated, onCancel }: {
  datasetIds: number[]
  datasets: Record<number, Dataset>
  onCreated: (r: Relationship) => void
  onCancel: () => void
}) {
  const [fromDs, setFromDs] = useState(datasetIds[0])
  const [fromCol, setFromCol] = useState('')
  const [toDs, setToDs] = useState(datasetIds[1] ?? datasetIds[0])
  const [toCol, setToCol] = useState('')
  const [error, setError] = useState<string | null>(null)

  const submit = async () => {
    if (!fromCol || !toCol) { setError('Choose a column on both sides'); return }
    try {
      const rel = await relationshipsApi.create({ from_dataset_id: fromDs, from_column: fromCol, to_dataset_id: toDs, to_column: toCol })
      onCreated(rel)
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'Failed to create relationship')
    }
  }

  return (
    <div style={{ border: '1px solid var(--border)', borderRadius: 8, padding: 12, marginTop: 8, maxWidth: 420 }}>
      <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
        <select value={fromDs} onChange={e => setFromDs(Number(e.target.value))}>
          {datasetIds.map(id => <option key={id} value={id}>{datasets[id]?.name}</option>)}
        </select>
        <select value={fromCol} onChange={e => setFromCol(e.target.value)}>
          <option value="">Column…</option>
          {(datasets[fromDs]?.columns ?? []).map(c => <option key={c.name} value={c.name}>{c.name}</option>)}
        </select>
      </div>
      <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
        <select value={toDs} onChange={e => setToDs(Number(e.target.value))}>
          {datasetIds.map(id => <option key={id} value={id}>{datasets[id]?.name}</option>)}
        </select>
        <select value={toCol} onChange={e => setToCol(e.target.value)}>
          <option value="">Column…</option>
          {(datasets[toDs]?.columns ?? []).map(c => <option key={c.name} value={c.name}>{c.name}</option>)}
        </select>
      </div>
      {error && <p style={{ color: 'var(--danger)', fontSize: 12 }}>{error}</p>}
      <div style={{ display: 'flex', gap: 8 }}>
        <button className="btn btn-primary btn-sm" onClick={submit}>Create</button>
        <button className="btn btn-ghost btn-sm" onClick={onCancel}>Cancel</button>
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Run and confirm it passes.**

- [ ] **Step 5: Run the full frontend suite.**

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/report/ModelView.tsx frontend/src/components/report/ModelView.test.tsx
git commit -m "Build the relationship diagram and create-relationship form"
```

---

## PHASE 5 — Canvas Presets, Page Nav, Status Bar

### Task 14: ReportPage page-size columns

**Files:**
- Modify: `backend/app/models/models.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/schemas/schemas.py`
- Test: `backend/tests/test_report_page_size.py`

**Interfaces:**
- Produces: `ReportPage.page_size` (`'16:9' | '4:3' | 'custom'`, default `'16:9'`),
  `custom_width`/`custom_height` (nullable `Integer`).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_report_page_size.py
from app.models.models import Report, ReportPage


async def test_page_size_defaults_to_16_9(db_session):
    report = Report(name="R")
    db_session.add(report)
    await db_session.flush()
    page = ReportPage(report_id=report.id, name="Page 1")
    db_session.add(page)
    await db_session.commit()
    await db_session.refresh(page)

    assert page.page_size == "16:9"
    assert page.custom_width is None


async def test_page_size_can_be_set_to_custom_dimensions(db_session):
    report = Report(name="R")
    db_session.add(report)
    await db_session.flush()
    page = ReportPage(report_id=report.id, name="Page 1", page_size="custom", custom_width=1200, custom_height=800)
    db_session.add(page)
    await db_session.commit()
    await db_session.refresh(page)

    assert page.custom_width == 1200
    assert page.custom_height == 800
```

- [ ] **Step 2: Run and confirm it fails** — `TypeError: 'page_size' is an invalid keyword argument for ReportPage`.

- [ ] **Step 3: Implement.** In `models.py`'s `ReportPage` class, add:

```python
    page_size     = Column(String(20), nullable=False, default="16:9", server_default="16:9")
    custom_width  = Column(Integer, nullable=True)
    custom_height = Column(Integer, nullable=True)
```

In `main.py`'s `_migrate()`, add:

```python
    "ALTER TABLE report_pages ADD COLUMN IF NOT EXISTS page_size VARCHAR(20) NOT NULL DEFAULT '16:9'",
    "ALTER TABLE report_pages ADD COLUMN IF NOT EXISTS custom_width INTEGER",
    "ALTER TABLE report_pages ADD COLUMN IF NOT EXISTS custom_height INTEGER",
```

In `schemas.py`, add the three fields to `PageCreate`, `PageUpdate`, and `PageOut`:

```python
# PageCreate: page_size: str = "16:9"; custom_width: Optional[int] = None; custom_height: Optional[int] = None
# PageUpdate: page_size: Optional[str] = None; custom_width: Optional[int] = None; custom_height: Optional[int] = None
# PageOut:    page_size: str = "16:9"; custom_width: Optional[int] = None; custom_height: Optional[int] = None
```

No router change needed — `update_page` in `reports.py` already applies any `PageUpdate` field
generically via `setattr` (confirmed at `backend/app/routers/reports.py:103-108`).

- [ ] **Step 4: Run and confirm it passes.**

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/models.py backend/app/main.py backend/app/schemas/schemas.py backend/tests/test_report_page_size.py
git commit -m "Add page-size fields to ReportPage (16:9/4:3/custom)"
```

---

### Task 15: page_type gains tooltip/drillthrough

**Files:**
- Modify: `frontend/src/types/report.ts` (the `PageType` union)
- Test: extend wherever page-type UI is tested, or add a minimal render test if none exists —
  check `frontend/src/pages/ReportBuilder.test.tsx` first for a page-management section to extend

**Interfaces:**
- Produces: `export type PageType = 'normal' | 'hidden' | 'popup' | 'tooltip' | 'drillthrough'`.

No backend change needed — `page_type` is already a plain unconstrained `String(20)` column and
`PageCreate.page_type: str = "normal"` already accepts any string; only the frontend type union and
the "omit from tab strip" filter need to change.

- [ ] **Step 1: Update the type**

```ts
// frontend/src/types/report.ts
export type PageType = 'normal' | 'hidden' | 'popup' | 'tooltip' | 'drillthrough'
```

- [ ] **Step 2: Find and extend the page-tab-strip filter.** Search `ReportBuilder.tsx` for where
  `'hidden'` pages are excluded from the bottom tab strip (e.g. `page_type !== 'hidden'` or
  `.filter(p => p.page_type === 'normal')`) and extend that condition to also exclude `'tooltip'`
  and `'drillthrough'`:

```tsx
.filter(p => p.page_type !== 'hidden' && p.page_type !== 'tooltip' && p.page_type !== 'drillthrough')
```

- [ ] **Step 3: Add the two new options to the page-properties selector.** In
  `frontend/src/components/report/PagePropertiesPanel.tsx:11-15`, extend the `PAGE_TYPES` array:

```tsx
const PAGE_TYPES: { value: PageType; label: string; desc: string }[] = [
  { value: 'normal',      label: 'Normal',      desc: 'Standard visible tab' },
  { value: 'hidden',      label: 'Hidden',       desc: 'Tab hidden in view mode' },
  { value: 'popup',       label: 'Popup',        desc: 'Rendered as floating overlay' },
  { value: 'tooltip',     label: 'Tooltip',      desc: 'Shown as a hover tooltip on another visual (not yet triggerable)' },
  { value: 'drillthrough',label: 'Drillthrough', desc: 'Reached by drilling through from another page (not yet triggerable)' },
]
```

  No other change needed in this file — the existing radio-button rendering (around line 73) maps
  over `PAGE_TYPES` generically and already calls `onUpdate({ page_type: pageType })` on change.

- [ ] **Step 4: Manually verify** — set a page's `page_type` to `'drillthrough'` via this panel,
  confirm it disappears from the bottom tab strip (Step 2's filter).

- [ ] **Step 5: Run the full frontend suite.**

- [ ] **Step 6: Commit**

```bash
git add frontend/src/types/report.ts frontend/src/pages/ReportBuilder.tsx frontend/src/components/report/PagePropertiesPanel.tsx
git commit -m "Add tooltip/drillthrough page types (tagging only, no trigger mechanics)"
```

---

### Task 16: Page-size presets in the ribbon View tab

**Files:**
- Modify: `frontend/src/pages/ReportBuilder.tsx`

**Interfaces:**
- Consumes: `useRibbon()`, `reportsApi.updatePage` (existing), `ReportPage.page_size` (Task 14).

- [ ] **Step 1: Write the failing test** — extend `ReportBuilder.test.tsx`:

```tsx
it('updates the active page size when a preset is chosen in the ribbon View tab', async () => {
  vi.mocked(reportsApi.get).mockResolvedValue(baseReport() as any)
  vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales Data', columns: [] } as any)
  vi.mocked(reportsApi.updatePage).mockResolvedValue({} as any)
  render(/* ...wrapped in RibbonProvider as in Task 8's test... */)
  fireEvent.click(await screen.findByRole('tab', { name: 'View' }))
  fireEvent.click(screen.getByRole('button', { name: '4:3' }))
  expect(reportsApi.updatePage).toHaveBeenCalledWith(1, 100, { page_size: '4:3' })
})
```

- [ ] **Step 2: Run and confirm it fails.**

- [ ] **Step 3: Implement.** In the same ribbon-content `useEffect` pattern as Task 8, inject into
  the `view` tab:

```tsx
useEffect(() => {
  if (!activePage) return
  setTabContent('view', (
    <div style={{ display: 'flex', gap: 4 }}>
      {(['16:9', '4:3', 'custom'] as const).map(size => (
        <button key={size} onClick={() => reportsApi.updatePage(report!.id, activePage.id, { page_size: size })}
          style={{ padding: '5px 10px', fontSize: 11, border: '1px solid var(--border)', borderRadius: 6,
            background: activePage.page_size === size ? 'var(--accent)' : 'var(--surface2)',
            color: activePage.page_size === size ? '#fff' : 'var(--text)', cursor: 'pointer' }}>
          {size}
        </button>
      ))}
    </div>
  ))
  return () => clearTabContent('view')
}, [activePage, report, setTabContent, clearTabContent])
```

- [ ] **Step 4: Run and confirm it passes.**

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/ReportBuilder.tsx
git commit -m "Add page-size presets to the ribbon View tab"
```

---

### Task 17: Status bar

**Files:**
- Create: `frontend/src/components/report/StatusBar.tsx`
- Test: `frontend/src/components/report/StatusBar.test.tsx`
- Modify: `frontend/src/pages/ReportBuilder.tsx`

**Interfaces:**
- Produces: `StatusBar({ pageIndex, pageCount, saveState }: { pageIndex: number; pageCount: number; saveState: 'saved' | 'saving' })`.

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/report/StatusBar.test.tsx
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import StatusBar from './StatusBar'

describe('StatusBar', () => {
  it('shows page position', () => {
    render(<StatusBar pageIndex={1} pageCount={4} saveState="saved" />)
    expect(screen.getByText('Page 2 of 4')).toBeInTheDocument()
  })

  it('shows Saved when saveState is saved', () => {
    render(<StatusBar pageIndex={0} pageCount={1} saveState="saved" />)
    expect(screen.getByText('Saved')).toBeInTheDocument()
  })

  it('shows Saving… when saveState is saving', () => {
    render(<StatusBar pageIndex={0} pageCount={1} saveState="saving" />)
    expect(screen.getByText('Saving…')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run and confirm it fails.**

- [ ] **Step 3: Implement**

```tsx
// frontend/src/components/report/StatusBar.tsx
export default function StatusBar({ pageIndex, pageCount, saveState }: {
  pageIndex: number
  pageCount: number
  saveState: 'saved' | 'saving'
}) {
  return (
    <div style={{
      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      padding: '4px 12px', borderTop: '1px solid var(--border)', background: 'var(--surface)',
      fontSize: 11, color: 'var(--muted)', flexShrink: 0,
    }}>
      <span>Page {pageIndex + 1} of {pageCount}</span>
      <span>{saveState === 'saving' ? 'Saving…' : 'Saved'}</span>
    </div>
  )
}
```

- [ ] **Step 4: Run and confirm it passes.**

- [ ] **Step 5: Wire into ReportBuilder** — render `<StatusBar>` at the bottom of the editor,
  computing `pageIndex` from `report.pages.findIndex(p => p.id === activePage?.id)`,
  `pageCount` from `report.pages.length`, and `saveState` from whatever loading/saving flag the
  component already tracks for widget/page updates (if none exists yet, add a simple
  `const [saving, setSaving] = useState(false)` set around the existing `updateWidget`/`updatePage`
  calls).

- [ ] **Step 6: Run the full frontend suite.**

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/report/StatusBar.tsx frontend/src/components/report/StatusBar.test.tsx frontend/src/pages/ReportBuilder.tsx
git commit -m "Add status bar: page position and save state"
```

---

## Final Verification

- [ ] **Backend:** `cd backend && python -m pytest tests/ -q` — full suite green, no regressions
  against the pre-existing baseline.
- [ ] **Frontend:** `cd frontend && npx vitest run` — full suite green.
- [ ] **Manual smoke test:** run the app (`docker compose up` or local dev servers), confirm: the
  ribbon and icon rail appear on every page; opening a report shows the Report/Data/Model strip;
  Insert-tab widget catalog still adds widgets; Model view lists datasets and lets you create a
  relationship; a page's size preset persists after reload; the status bar shows correct page
  position.
