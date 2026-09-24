# Row-Level Security Phase 3 — Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a login page, an auth-aware API client (bearer token attached to every request, automatic redirect to `/login` on 401), and admin screens for managing Roles, Users, and Row-Security-Rules — making the backend auth/RLS system (Phases 0-2, already merged) usable from the app's UI for the first time.

**Architecture:** A framework-agnostic token store + axios interceptor pair added to the existing `frontend/src/services/api.ts` (no new HTTP library). A React `AuthContext` (new) wraps the app inside `BrowserRouter`, owns the current user and a `loading` flag, and registers itself as the interceptor's 401 handler. A `ProtectedRoute` wrapper gates every existing route behind login; a `RequireAdmin` wrapper additionally gates the three new admin pages. The three admin pages follow this codebase's existing list+modal CRUD pattern (see `frontend/src/pages/Connections.tsx`) — no new UI library, no new state-management library.

**Tech Stack:** React 18 + TypeScript 5 + Vite 5 (existing). React Router v6 (existing). Axios (existing, extended with interceptors). `react-hot-toast` for feedback (existing). No new dependencies.

## Global Constraints

- Token storage key: `localStorage` key `datalytics_token` — a single string, the raw JWT (no wrapper object).
- Styling: inline `style={{}}` objects using the existing CSS custom properties (`var(--bg)`, `var(--surface)`, `var(--surface2)`, `var(--border)`, `var(--text)`, `var(--muted)`, `var(--accent)`, `var(--danger)`) — no CSS modules, no styled-components, no Tailwind. Buttons use the existing `.btn` / `.btn-primary` / `.btn-ghost` / `.btn-danger` / `.btn-sm` classes from `frontend/src/index.css`. Match `frontend/src/pages/Connections.tsx`'s exact patterns for list rows, modals, and form inputs (the `inp` style-object convention) — this is the closest existing analog to every admin page in this plan.
- Error handling: every API call's `.catch` surfaces `e?.response?.data?.detail ?? '<fallback message>'` via `toast.error(...)`, matching every existing page in this codebase. Never let an unhandled promise rejection reach the console silently.
- New TypeScript interfaces (User, Role, Organization, RowSecurityRule) live inline in `frontend/src/services/api.ts`, matching the existing convention for `Dataset`/`DataSource`/`DatasetColumn` (not a separate `types/` file — that's reserved for the report-builder's more extensively shared types).
- Per the design spec's explicit testing scope for this phase (`docs/superpowers/specs/2026-08-13-row-level-security-design.md`, Testing section): "Phase 3 adds minimal coverage for the auth-aware API client's 401-redirect behavior, consistent with this project's existing 'diff-based review over exhaustive component tests' convention." Only Task 1 (the API client's token/interceptor logic) gets real automated tests in this plan. The admin pages and Login page are verified by manual browser testing (Task 8), not new component test files — do not add component tests beyond what's explicitly specified per task.
- Backend API surface this phase consumes (already built and merged, no backend changes in this plan): `POST /api/v1/auth/login`, `GET /api/v1/auth/me`, `GET/POST /api/v1/admin/roles`, `PATCH/DELETE /api/v1/admin/roles/{id}`, `GET/POST /api/v1/admin/users`, `PATCH/DELETE /api/v1/admin/users/{id}`, `GET/POST /api/v1/admin/row-security-rules`, `PATCH/DELETE /api/v1/admin/row-security-rules/{id}`.
- `AuthProvider` must be mounted **inside** `<BrowserRouter>` (it calls `useNavigate`), and **outside** `<Routes>` so every route (including `/login`) can call `useAuth()`.

---

### Task 1: Auth-aware API client — token store + interceptors

**Files:**
- Modify: `frontend/src/services/api.ts`
- Test: `frontend/src/test/authInterceptor.test.ts`

**Interfaces:**
- Produces: `getAuthToken(): string | null`, `setAuthToken(token: string | null): void`, `setUnauthorizedHandler(handler: (() => void) | null): void`, `attachAuthHeader(config)` (request interceptor, exported for direct testing), `handleResponseError(error)` (response interceptor, exported for direct testing) — all in `frontend/src/services/api.ts`. Task 2's `AuthContext` consumes `getAuthToken`/`setAuthToken`/`setUnauthorizedHandler`.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/test/authInterceptor.test.ts`:

```ts
import { describe, it, expect, vi, beforeEach } from 'vitest'
import {
  getAuthToken, setAuthToken, setUnauthorizedHandler,
  attachAuthHeader, handleResponseError,
} from '../services/api'

describe('auth-aware API client', () => {
  beforeEach(() => {
    localStorage.clear()
    setAuthToken(null)
    setUnauthorizedHandler(null)
  })

  it('has no token by default', () => {
    expect(getAuthToken()).toBeNull()
  })

  it('persists a set token to localStorage and reflects it via getAuthToken', () => {
    setAuthToken('abc123')
    expect(getAuthToken()).toBe('abc123')
    expect(localStorage.getItem('datalytics_token')).toBe('abc123')
  })

  it('clearing the token removes it from localStorage', () => {
    setAuthToken('abc123')
    setAuthToken(null)
    expect(getAuthToken()).toBeNull()
    expect(localStorage.getItem('datalytics_token')).toBeNull()
  })

  it('attaches an Authorization header when a token is set', () => {
    setAuthToken('abc123')
    const config: any = { headers: {} }
    const result = attachAuthHeader(config)
    expect(result.headers.Authorization).toBe('Bearer abc123')
  })

  it('does not attach an Authorization header when no token is set', () => {
    const config: any = { headers: {} }
    const result = attachAuthHeader(config)
    expect(result.headers.Authorization).toBeUndefined()
  })

  it('a 401 response clears the token and invokes the unauthorized handler', async () => {
    setAuthToken('abc123')
    const handler = vi.fn()
    setUnauthorizedHandler(handler)

    await expect(handleResponseError({ response: { status: 401 } })).rejects.toBeTruthy()

    expect(getAuthToken()).toBeNull()
    expect(handler).toHaveBeenCalledTimes(1)
  })

  it('a non-401 error does not clear the token or invoke the handler', async () => {
    setAuthToken('abc123')
    const handler = vi.fn()
    setUnauthorizedHandler(handler)

    await expect(handleResponseError({ response: { status: 500 } })).rejects.toBeTruthy()

    expect(getAuthToken()).toBe('abc123')
    expect(handler).not.toHaveBeenCalled()
  })

  it('a 401 with no handler registered still clears the token without throwing', async () => {
    setAuthToken('abc123')
    await expect(handleResponseError({ response: { status: 401 } })).rejects.toBeTruthy()
    expect(getAuthToken()).toBeNull()
  })
})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npx vitest run src/test/authInterceptor.test.ts`
Expected: FAIL — none of `getAuthToken`/`setAuthToken`/`setUnauthorizedHandler`/`attachAuthHeader`/`handleResponseError` are exported from `api.ts` yet.

- [ ] **Step 3: Implement the token store and interceptors**

In `frontend/src/services/api.ts`, after the existing `const api = axios.create({ baseURL: BASE })` line (currently line 5), insert:

```ts
const TOKEN_KEY = 'datalytics_token'
let authToken: string | null = localStorage.getItem(TOKEN_KEY)
let onUnauthorized: (() => void) | null = null

export function getAuthToken(): string | null {
  return authToken
}

export function setAuthToken(token: string | null): void {
  authToken = token
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

export function setUnauthorizedHandler(handler: (() => void) | null): void {
  onUnauthorized = handler
}

export function attachAuthHeader(config: any) {
  if (authToken) {
    config.headers = config.headers ?? {}
    config.headers.Authorization = `Bearer ${authToken}`
  }
  return config
}

export function handleResponseError(error: any) {
  if (error?.response?.status === 401) {
    setAuthToken(null)
    onUnauthorized?.()
  }
  return Promise.reject(error)
}

api.interceptors.request.use(attachAuthHeader)
api.interceptors.response.use(r => r, handleResponseError)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run src/test/authInterceptor.test.ts`
Expected: 8 passed.

- [ ] **Step 5: Run the full frontend test suite to check for regressions**

Run: `cd frontend && npm test`
Expected: all tests pass (the existing smoke test plus this new file).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/services/api.ts frontend/src/test/authInterceptor.test.ts
git commit -m "feat: add auth token store and axios interceptors to the API client"
```

---

### Task 2: Auth types, authApi, AuthContext, and the Login page

**Files:**
- Modify: `frontend/src/services/api.ts`
- Create: `frontend/src/contexts/AuthContext.tsx`
- Create: `frontend/src/pages/Login.tsx`

**Interfaces:**
- Consumes: `getAuthToken`, `setAuthToken`, `setUnauthorizedHandler` (Task 1).
- Produces: `Organization`, `Role`, `User` TS interfaces and `authApi.login`/`authApi.me` in `api.ts` (Task 4 and Task 5/6/7 reuse `Organization`/`Role`/`User`). `AuthProvider`, `useAuth()` (returns `{ user, loading, login, logout }`) in `AuthContext.tsx` — Task 3's `ProtectedRoute`/`RequireAdmin` and every admin page consume `useAuth()`.

- [ ] **Step 1: Add auth types and `authApi` to `api.ts`**

Append to `frontend/src/services/api.ts` (after the existing `dataSourcesApi` export at the end of the file):

```ts
export interface Organization {
  id: number
  name: string
}

export interface Role {
  id: number
  name: string
  is_org_admin: boolean
}

export interface User {
  id: number
  email: string
  is_active: boolean
  organization: Organization
  role: Role
}

export const authApi = {
  login: (email: string, password: string) =>
    api.post<{ access_token: string; token_type: string }>('/auth/login', { email, password }).then(r => r.data),
  me: () => api.get<User>('/auth/me').then(r => r.data),
}
```

- [ ] **Step 2: Create `AuthContext`**

Create `frontend/src/contexts/AuthContext.tsx`:

```tsx
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { authApi, getAuthToken, setAuthToken, setUnauthorizedHandler } from '../services/api'
import type { User } from '../services/api'

interface AuthContextValue {
  user: User | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()

  const logout = () => {
    setAuthToken(null)
    setUser(null)
    navigate('/login')
  }

  useEffect(() => {
    setUnauthorizedHandler(() => {
      setUser(null)
      navigate('/login')
    })
    return () => setUnauthorizedHandler(null)
  }, [navigate])

  useEffect(() => {
    const token = getAuthToken()
    if (!token) {
      setLoading(false)
      return
    }
    authApi.me()
      .then(setUser)
      .catch(() => setAuthToken(null))
      .finally(() => setLoading(false))
  }, [])

  const login = async (email: string, password: string) => {
    const { access_token } = await authApi.login(email, password)
    setAuthToken(access_token)
    const me = await authApi.me()
    setUser(me)
    navigate('/')
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
```

- [ ] **Step 3: Create the Login page**

Create `frontend/src/pages/Login.tsx`:

```tsx
import { useState, type FormEvent } from 'react'
import { useAuth } from '../contexts/AuthContext'
import toast from 'react-hot-toast'

export default function Login() {
  const { login, user } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)

  if (user) {
    // Already authenticated (e.g. navigated back to /login manually) — bounce home.
    window.location.replace('/')
    return null
  }

  const inp = {
    style: {
      width: '100%', fontSize: 13, padding: '8px 10px', boxSizing: 'border-box' as const,
      background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 6, color: 'var(--text)',
    },
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!email.trim() || !password) {
      toast.error('Email and password are required')
      return
    }
    setSubmitting(true)
    try {
      await login(email.trim(), password)
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? 'Invalid email or password')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--bg)' }}>
      <form onSubmit={handleSubmit} style={{
        background: 'var(--surface)', border: '1px solid var(--border)',
        borderRadius: 12, padding: 32, width: 360,
      }}>
        <div style={{ fontWeight: 800, fontSize: 20, color: 'var(--accent)', marginBottom: 24, textAlign: 'center' }}>
          Datalytics
        </div>
        <label style={{ display: 'block', marginBottom: 14 }}>
          <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 5 }}>Email</div>
          <input type="email" value={email} onChange={e => setEmail(e.target.value)} autoFocus {...inp} />
        </label>
        <label style={{ display: 'block', marginBottom: 20 }}>
          <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 5 }}>Password</div>
          <input type="password" value={password} onChange={e => setPassword(e.target.value)} {...inp} />
        </label>
        <button type="submit" className="btn btn-primary" disabled={submitting} style={{ width: '100%' }}>
          {submitting ? 'Signing in…' : 'Sign In'}
        </button>
      </form>
    </div>
  )
}
```

(`window.location.replace` rather than `useNavigate` for the already-authenticated bounce is deliberate — it avoids calling a hook conditionally after the early-return pattern above; a full reload here is cheap and this path is rare.)

- [ ] **Step 4: Verify the app still builds**

Run: `cd frontend && npx tsc --noEmit`
Expected: no type errors (Login.tsx and AuthContext.tsx aren't wired into App.tsx yet, so this only checks they compile standalone — full integration is Task 3).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/services/api.ts frontend/src/contexts/AuthContext.tsx frontend/src/pages/Login.tsx
git commit -m "feat: add AuthContext, authApi, and the Login page"
```

---

### Task 3: ProtectedRoute, RequireAdmin, Layout updates, and App.tsx wiring

**Files:**
- Create: `frontend/src/components/ProtectedRoute.tsx`
- Create: `frontend/src/components/RequireAdmin.tsx`
- Modify: `frontend/src/components/Layout.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `useAuth` (Task 2).
- Produces: `<ProtectedRoute />` and `<RequireAdmin />` (both `Outlet`-rendering route-wrapper components) — used directly in `App.tsx`'s route tree; no other task depends on their internals.

- [ ] **Step 1: Create `ProtectedRoute`**

Create `frontend/src/components/ProtectedRoute.tsx`:

```tsx
import { Navigate, Outlet } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'

export default function ProtectedRoute() {
  const { user, loading } = useAuth()
  if (loading) return <div style={{ padding: 40, color: 'var(--muted)' }}>Loading…</div>
  if (!user) return <Navigate to="/login" replace />
  return <Outlet />
}
```

- [ ] **Step 2: Create `RequireAdmin`**

Create `frontend/src/components/RequireAdmin.tsx`:

```tsx
import { Navigate, Outlet } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'

export default function RequireAdmin() {
  const { user } = useAuth()
  // Rendered only inside ProtectedRoute, so `user` is guaranteed non-null here —
  // this is a client-side UX guard only; the backend's require_org_admin dependency
  // is the actual enforcement (403 on every /admin/* endpoint for non-admins).
  if (!user?.role.is_org_admin) return <Navigate to="/" replace />
  return <Outlet />
}
```

- [ ] **Step 3: Update `Layout.tsx`**

In `frontend/src/components/Layout.tsx`, add the import at the top:

```tsx
import { useAuth } from '../contexts/AuthContext'
```

Inside the `Layout` function, after the existing `const toggle = ...` line, add:

```tsx
  const { user, logout } = useAuth()
```

In the sidebar `<nav>`, after the existing `<NavLink to="/connections" ...>` line and before the `<div style={{ flex: 1 }} />` spacer, add the admin section (only rendered for org-admin users):

```tsx
        {user?.role.is_org_admin && (
          <>
            <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase',
              letterSpacing: '.06em', padding: '16px 8px 4px' }}>Admin</div>
            <NavLink to="/admin/users" style={navStyle}>👤 Users</NavLink>
            <NavLink to="/admin/roles" style={navStyle}>🛡 Roles</NavLink>
            <NavLink to="/admin/row-security-rules" style={navStyle}>🔒 Row Security</NavLink>
          </>
        )}
```

Replace the existing `<div style={{ flex: 1 }} />` spacer and everything after it (the theme-toggle button, currently the last element before the closing `</nav>`) with the same spacer, the theme button (unchanged), and a new user-info/logout block:

```tsx
        <div style={{ flex: 1 }} />

        <button
          onClick={toggle}
          style={{
            display: 'flex', alignItems: 'center', gap: 8,
            padding: '8px 12px', borderRadius: 8, border: 'none',
            background: 'transparent', color: 'var(--muted)',
            fontSize: 13, cursor: 'pointer', width: '100%', transition: 'color .15s',
          }}
          onMouseEnter={e => (e.currentTarget.style.color = 'var(--text)')}
          onMouseLeave={e => (e.currentTarget.style.color = 'var(--muted)')}
        >
          {theme === 'dark' ? '☀ Light mode' : '☾ Dark mode'}
        </button>

        {user && (
          <div style={{ borderTop: '1px solid var(--border)', marginTop: 8, paddingTop: 8 }}>
            <div style={{ fontSize: 11, color: 'var(--text)', padding: '4px 8px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {user.email}
            </div>
            <div style={{ fontSize: 10, color: 'var(--muted)', padding: '0 8px 6px' }}>
              {user.organization.name} · {user.role.name}
            </div>
            <button
              onClick={logout}
              style={{
                display: 'flex', alignItems: 'center', gap: 8,
                padding: '8px 12px', borderRadius: 8, border: 'none',
                background: 'transparent', color: 'var(--muted)',
                fontSize: 13, cursor: 'pointer', width: '100%', transition: 'color .15s',
              }}
              onMouseEnter={e => (e.currentTarget.style.color = 'var(--text)')}
              onMouseLeave={e => (e.currentTarget.style.color = 'var(--muted)')}
            >
              ⎋ Log out
            </button>
          </div>
        )}
```

- [ ] **Step 4: Wire everything into `App.tsx`**

Replace the full contents of `frontend/src/App.tsx`:

```tsx
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { AuthProvider } from './contexts/AuthContext'
import ProtectedRoute from './components/ProtectedRoute'
import RequireAdmin from './components/RequireAdmin'
import Layout from './components/Layout'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Upload from './pages/Upload'
import DatasetDetail from './pages/DatasetDetail'
import Reports from './pages/Reports'
import ReportBuilder from './pages/ReportBuilder'
import Connections from './pages/Connections'
import AdminRoles from './pages/admin/AdminRoles'
import AdminUsers from './pages/admin/AdminUsers'
import AdminRowSecurityRules from './pages/admin/AdminRowSecurityRules'

export default function App() {
  return (
    <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route element={<ProtectedRoute />}>
            <Route path="/" element={<Layout />}>
              <Route index element={<Dashboard />} />
              <Route path="upload" element={<Upload />} />
              <Route path="datasets/:id" element={<DatasetDetail />} />
              <Route path="reports" element={<Reports />} />
              <Route path="connections" element={<Connections />} />
              <Route element={<RequireAdmin />}>
                <Route path="admin/roles" element={<AdminRoles />} />
                <Route path="admin/users" element={<AdminUsers />} />
                <Route path="admin/row-security-rules" element={<AdminRowSecurityRules />} />
              </Route>
            </Route>
            {/* ReportBuilder is full-page — its own sidebar replaces the global Layout */}
            <Route path="reports/:id" element={<ReportBuilder />} />
          </Route>
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}
```

Note: this references `AdminRoles`, `AdminUsers`, `AdminRowSecurityRules` from `pages/admin/`, which don't exist until Tasks 5-7. This task will not type-check or build cleanly on its own — that's expected and resolved once Task 4's placeholder-free implementation lands. If executed via subagent-driven-development, the implementer should still write this file exactly as specified (verifying it via `npx tsc --noEmit` will show three "Cannot find module" errors for the three admin page imports, and nothing else) rather than stubbing the imports out — Tasks 5-7 depend on this exact `App.tsx` content already being in place.

- [ ] **Step 5: Verify the expected (partial) type-check state**

Run: `cd frontend && npx tsc --noEmit`
Expected: exactly 3 errors, all "Cannot find module './pages/admin/AdminRoles'" (or `AdminUsers`/`AdminRowSecurityRules`) — no other errors. If any other error appears, fix it before committing.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/ProtectedRoute.tsx frontend/src/components/RequireAdmin.tsx \
        frontend/src/components/Layout.tsx frontend/src/App.tsx
git commit -m "feat: gate routes behind auth, add admin nav and logout to Layout"
```

---

### Task 4: Admin API client — roles, users, row-security-rules

**Files:**
- Modify: `frontend/src/services/api.ts`

**Interfaces:**
- Consumes: `Organization`, `Role`, `User` (Task 2).
- Produces: `AdminUser` (Role/User with a plain `role_id`-free shape identical to `User` — reused as-is), `RowSecurityRule` interface, `adminRolesApi`, `adminUsersApi`, `adminRlsRulesApi` — Tasks 5-7 consume these directly.

- [ ] **Step 1: Append the admin API groups**

Append to `frontend/src/services/api.ts` (after the `authApi` export added in Task 2):

```ts
export const adminRolesApi = {
  list:   () => api.get<Role[]>('/admin/roles').then(r => r.data),
  create: (body: { name: string; is_org_admin: boolean }) =>
    api.post<Role>('/admin/roles', body).then(r => r.data),
  update: (id: number, body: Partial<{ name: string; is_org_admin: boolean }>) =>
    api.patch<Role>(`/admin/roles/${id}`, body).then(r => r.data),
  delete: (id: number) => api.delete(`/admin/roles/${id}`),
}

export const adminUsersApi = {
  list:   () => api.get<User[]>('/admin/users').then(r => r.data),
  create: (body: { email: string; password: string; role_id: number }) =>
    api.post<User>('/admin/users', body).then(r => r.data),
  update: (id: number, body: Partial<{ email: string; password: string; role_id: number; is_active: boolean }>) =>
    api.patch<User>(`/admin/users/${id}`, body).then(r => r.data),
  delete: (id: number) => api.delete(`/admin/users/${id}`),
}

export interface RowSecurityRule {
  id: number
  role_id: number
  dataset_id: number
  filter_expr: string
  created_at: string
}

export const adminRlsRulesApi = {
  list:   () => api.get<RowSecurityRule[]>('/admin/row-security-rules').then(r => r.data),
  create: (body: { role_id: number; dataset_id: number; filter_expr: string }) =>
    api.post<RowSecurityRule>('/admin/row-security-rules', body).then(r => r.data),
  update: (id: number, body: { filter_expr: string }) =>
    api.patch<RowSecurityRule>(`/admin/row-security-rules/${id}`, body).then(r => r.data),
  delete: (id: number) => api.delete(`/admin/row-security-rules/${id}`),
}
```

- [ ] **Step 2: Verify the file still compiles in isolation**

Run: `cd frontend && npx tsc --noEmit`
Expected: same 3 errors as the end of Task 3 (the missing admin page modules) — no NEW errors from this change.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/services/api.ts
git commit -m "feat: add admin API client for roles, users, and row-security-rules"
```

---

### Task 5: Admin Roles page

**Files:**
- Create: `frontend/src/pages/admin/AdminRoles.tsx`

**Interfaces:**
- Consumes: `adminRolesApi`, `Role` (Task 4).

- [ ] **Step 1: Create the page**

Create `frontend/src/pages/admin/AdminRoles.tsx`:

```tsx
import { useEffect, useState } from 'react'
import { adminRolesApi } from '../../services/api'
import type { Role } from '../../services/api'
import toast from 'react-hot-toast'

function RoleModal({ initial, onSave, onClose }: {
  initial?: Role | null
  onSave: (r: Role) => void
  onClose: () => void
}) {
  const isEdit = !!initial
  const [name, setName] = useState(initial?.name ?? '')
  const [isOrgAdmin, setIsOrgAdmin] = useState(initial?.is_org_admin ?? false)
  const [saving, setSaving] = useState(false)

  const inp = {
    style: { width: '100%', fontSize: 12, padding: '5px 8px', boxSizing: 'border-box' as const,
      background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 4, color: 'var(--text)' },
  }

  const handleSave = async () => {
    if (!name.trim()) { toast.error('Name is required'); return }
    setSaving(true)
    try {
      const result = isEdit
        ? await adminRolesApi.update(initial!.id, { name, is_org_admin: isOrgAdmin })
        : await adminRolesApi.create({ name, is_org_admin: isOrgAdmin })
      onSave(result)
      toast.success(isEdit ? 'Updated' : 'Role created')
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Save failed')
    } finally { setSaving(false) }
  }

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.5)', display: 'flex',
      alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
      <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12,
        padding: 24, width: 400 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
          <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0 }}>{isEdit ? 'Edit Role' : 'New Role'}</h2>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 20, color: 'var(--muted)' }}>×</button>
        </div>

        <label style={{ display: 'block', marginBottom: 14 }}>
          <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>Role Name *</div>
          <input value={name} onChange={e => setName(e.target.value)} placeholder="Regional Manager" {...inp} />
        </label>

        <label style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 20, cursor: 'pointer' }}>
          <input type="checkbox" checked={isOrgAdmin} onChange={e => setIsOrgAdmin(e.target.checked)} />
          <span style={{ fontSize: 12 }}>Org admin (bypasses all row-security rules, can manage users/roles/rules)</span>
        </label>

        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn btn-primary" onClick={handleSave} disabled={saving} style={{ flex: 1 }}>
            {saving ? 'Saving…' : isEdit ? 'Save Changes' : 'Create'}
          </button>
          <button className="btn btn-ghost" onClick={onClose} style={{ fontSize: 12, padding: '6px 14px' }}>Cancel</button>
        </div>
      </div>
    </div>
  )
}

export default function AdminRoles() {
  const [roles, setRoles] = useState<Role[]>([])
  const [loading, setLoading] = useState(true)
  const [modal, setModal] = useState<'add' | Role | null>(null)

  useEffect(() => {
    adminRolesApi.list().then(setRoles).finally(() => setLoading(false))
  }, [])

  const handleSaved = (r: Role) => {
    setRoles(prev => {
      const idx = prev.findIndex(x => x.id === r.id)
      return idx >= 0 ? prev.map(x => x.id === r.id ? r : x) : [r, ...prev]
    })
    setModal(null)
  }

  const handleDelete = async (r: Role) => {
    if (!confirm(`Delete role "${r.name}"?`)) return
    try {
      await adminRolesApi.delete(r.id)
      setRoles(prev => prev.filter(x => x.id !== r.id))
      toast.success('Deleted')
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Delete failed')
    }
  }

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 24 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, flex: 1 }}>Roles</h1>
        <button className="btn btn-primary btn-sm" onClick={() => setModal('add')}>+ New Role</button>
      </div>

      {loading && <p style={{ color: 'var(--muted)' }}>Loading…</p>}

      {!loading && roles.length === 0 && (
        <div style={{ padding: 60, textAlign: 'center', background: 'var(--surface)',
          border: '1px solid var(--border)', borderRadius: 12, color: 'var(--muted)' }}>
          No roles yet
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {roles.map(r => (
          <div key={r.id} style={{ display: 'flex', alignItems: 'center', gap: 14,
            background: 'var(--surface)', border: '1px solid var(--border)',
            borderRadius: 10, padding: '14px 16px' }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontWeight: 700, fontSize: 14 }}>{r.name}</div>
              {r.is_org_admin && <div style={{ fontSize: 11, color: 'var(--accent)' }}>Org admin</div>}
            </div>
            <button className="btn btn-ghost btn-sm" onClick={() => setModal(r)} style={{ fontSize: 11 }}>Edit</button>
            <button className="btn btn-ghost btn-sm" onClick={() => handleDelete(r)} style={{ fontSize: 11, color: 'var(--danger)' }}>Delete</button>
          </div>
        ))}
      </div>

      {modal && (
        <RoleModal initial={modal === 'add' ? null : modal} onSave={handleSaved} onClose={() => setModal(null)} />
      )}
    </div>
  )
}
```

- [ ] **Step 2: Verify the app type-checks**

Run: `cd frontend && npx tsc --noEmit`
Expected: down to 2 errors — "Cannot find module './pages/admin/AdminUsers'" and "...AdminRowSecurityRules" (the `AdminRoles` error from Task 3 is now resolved).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/admin/AdminRoles.tsx
git commit -m "feat: add admin Roles page"
```

---

### Task 6: Admin Users page

**Files:**
- Create: `frontend/src/pages/admin/AdminUsers.tsx`

**Interfaces:**
- Consumes: `adminUsersApi`, `adminRolesApi`, `User`, `Role` (Task 4).

- [ ] **Step 1: Create the page**

Create `frontend/src/pages/admin/AdminUsers.tsx`:

```tsx
import { useEffect, useState } from 'react'
import { adminUsersApi, adminRolesApi } from '../../services/api'
import type { User, Role } from '../../services/api'
import toast from 'react-hot-toast'

function UserModal({ initial, roles, onSave, onClose }: {
  initial?: User | null
  roles: Role[]
  onSave: (u: User) => void
  onClose: () => void
}) {
  const isEdit = !!initial
  const [email, setEmail] = useState(initial?.email ?? '')
  const [password, setPassword] = useState('')
  const [roleId, setRoleId] = useState<number | ''>(initial?.role.id ?? roles[0]?.id ?? '')
  const [isActive, setIsActive] = useState(initial?.is_active ?? true)
  const [saving, setSaving] = useState(false)

  const inp = {
    style: { width: '100%', fontSize: 12, padding: '5px 8px', boxSizing: 'border-box' as const,
      background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 4, color: 'var(--text)' },
  }

  const handleSave = async () => {
    if (!email.trim()) { toast.error('Email is required'); return }
    if (!isEdit && !password) { toast.error('Password is required for a new user'); return }
    if (roleId === '') { toast.error('Role is required'); return }
    setSaving(true)
    try {
      const result = isEdit
        ? await adminUsersApi.update(initial!.id, {
            email, role_id: roleId as number, is_active: isActive,
            ...(password ? { password } : {}),
          })
        : await adminUsersApi.create({ email, password, role_id: roleId as number })
      onSave(result)
      toast.success(isEdit ? 'Updated' : 'User created')
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Save failed')
    } finally { setSaving(false) }
  }

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.5)', display: 'flex',
      alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
      <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12,
        padding: 24, width: 420 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
          <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0 }}>{isEdit ? 'Edit User' : 'New User'}</h2>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 20, color: 'var(--muted)' }}>×</button>
        </div>

        <label style={{ display: 'block', marginBottom: 12 }}>
          <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>Email *</div>
          <input type="email" value={email} onChange={e => setEmail(e.target.value)} {...inp} />
        </label>

        <label style={{ display: 'block', marginBottom: 12 }}>
          <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>
            {isEdit ? 'New Password (leave blank to keep current)' : 'Password *'}
          </div>
          <input type="password" value={password} onChange={e => setPassword(e.target.value)} autoComplete="new-password" {...inp} />
        </label>

        <label style={{ display: 'block', marginBottom: 12 }}>
          <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>Role *</div>
          <select value={roleId} onChange={e => setRoleId(e.target.value ? Number(e.target.value) : '')} {...inp}>
            <option value="">Select a role…</option>
            {roles.map(r => <option key={r.id} value={r.id}>{r.name}{r.is_org_admin ? ' (admin)' : ''}</option>)}
          </select>
        </label>

        {isEdit && (
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 20, cursor: 'pointer' }}>
            <input type="checkbox" checked={isActive} onChange={e => setIsActive(e.target.checked)} />
            <span style={{ fontSize: 12 }}>Active (unchecking deactivates the account without deleting it)</span>
          </label>
        )}

        <div style={{ display: 'flex', gap: 8, marginTop: isEdit ? 0 : 20 }}>
          <button className="btn btn-primary" onClick={handleSave} disabled={saving} style={{ flex: 1 }}>
            {saving ? 'Saving…' : isEdit ? 'Save Changes' : 'Create'}
          </button>
          <button className="btn btn-ghost" onClick={onClose} style={{ fontSize: 12, padding: '6px 14px' }}>Cancel</button>
        </div>
      </div>
    </div>
  )
}

export default function AdminUsers() {
  const [users, setUsers] = useState<User[]>([])
  const [roles, setRoles] = useState<Role[]>([])
  const [loading, setLoading] = useState(true)
  const [modal, setModal] = useState<'add' | User | null>(null)

  useEffect(() => {
    Promise.all([adminUsersApi.list(), adminRolesApi.list()])
      .then(([u, r]) => { setUsers(u); setRoles(r) })
      .finally(() => setLoading(false))
  }, [])

  const handleSaved = (u: User) => {
    setUsers(prev => {
      const idx = prev.findIndex(x => x.id === u.id)
      return idx >= 0 ? prev.map(x => x.id === u.id ? u : x) : [u, ...prev]
    })
    setModal(null)
  }

  const handleDelete = async (u: User) => {
    if (!confirm(`Delete user "${u.email}"?`)) return
    try {
      await adminUsersApi.delete(u.id)
      setUsers(prev => prev.filter(x => x.id !== u.id))
      toast.success('Deleted')
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Delete failed')
    }
  }

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 24 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, flex: 1 }}>Users</h1>
        <button className="btn btn-primary btn-sm" onClick={() => setModal('add')} disabled={roles.length === 0}>
          + New User
        </button>
      </div>

      {loading && <p style={{ color: 'var(--muted)' }}>Loading…</p>}

      {!loading && roles.length === 0 && (
        <div style={{ padding: 16, marginBottom: 16, background: 'var(--surface2)', border: '1px solid var(--border)',
          borderRadius: 8, fontSize: 12, color: 'var(--muted)' }}>
          Create a role first — every user needs one.
        </div>
      )}

      {!loading && users.length === 0 && roles.length > 0 && (
        <div style={{ padding: 60, textAlign: 'center', background: 'var(--surface)',
          border: '1px solid var(--border)', borderRadius: 12, color: 'var(--muted)' }}>
          No users yet
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {users.map(u => (
          <div key={u.id} style={{ display: 'flex', alignItems: 'center', gap: 14,
            background: 'var(--surface)', border: '1px solid var(--border)',
            borderRadius: 10, padding: '14px 16px' }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontWeight: 700, fontSize: 14 }}>
                {u.email}
                {!u.is_active && <span style={{ marginLeft: 8, fontSize: 11, color: 'var(--danger)' }}>Inactive</span>}
              </div>
              <div style={{ fontSize: 11, color: 'var(--muted)' }}>{u.role.name}{u.role.is_org_admin ? ' (admin)' : ''}</div>
            </div>
            <button className="btn btn-ghost btn-sm" onClick={() => setModal(u)} style={{ fontSize: 11 }}>Edit</button>
            <button className="btn btn-ghost btn-sm" onClick={() => handleDelete(u)} style={{ fontSize: 11, color: 'var(--danger)' }}>Delete</button>
          </div>
        ))}
      </div>

      {modal && (
        <UserModal
          initial={modal === 'add' ? null : modal}
          roles={roles}
          onSave={handleSaved}
          onClose={() => setModal(null)}
        />
      )}
    </div>
  )
}
```

- [ ] **Step 2: Verify the app type-checks**

Run: `cd frontend && npx tsc --noEmit`
Expected: down to 1 error — "Cannot find module './pages/admin/AdminRowSecurityRules'".

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/admin/AdminUsers.tsx
git commit -m "feat: add admin Users page"
```

---

### Task 7: Admin Row-Security-Rules page

**Files:**
- Create: `frontend/src/pages/admin/AdminRowSecurityRules.tsx`

**Interfaces:**
- Consumes: `adminRlsRulesApi`, `adminRolesApi`, `RowSecurityRule`, `Role` (Task 4), `datasetsApi`, `Dataset` (existing, from `api.ts`).

- [ ] **Step 1: Create the page**

Create `frontend/src/pages/admin/AdminRowSecurityRules.tsx`:

```tsx
import { useEffect, useState } from 'react'
import { adminRlsRulesApi, adminRolesApi, datasetsApi } from '../../services/api'
import type { RowSecurityRule, Role, Dataset } from '../../services/api'
import toast from 'react-hot-toast'

function RuleModal({ initial, roles, datasets, onSave, onClose }: {
  initial?: RowSecurityRule | null
  roles: Role[]
  datasets: Dataset[]
  onSave: (r: RowSecurityRule) => void
  onClose: () => void
}) {
  const isEdit = !!initial
  const [roleId, setRoleId] = useState<number | ''>(initial?.role_id ?? roles[0]?.id ?? '')
  const [datasetId, setDatasetId] = useState<number | ''>(initial?.dataset_id ?? datasets[0]?.id ?? '')
  const [filterExpr, setFilterExpr] = useState(initial?.filter_expr ?? '')
  const [saving, setSaving] = useState(false)

  const inp = {
    style: { width: '100%', fontSize: 12, padding: '5px 8px', boxSizing: 'border-box' as const,
      background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 4, color: 'var(--text)' },
  }

  const handleSave = async () => {
    if (!isEdit && (roleId === '' || datasetId === '')) { toast.error('Role and dataset are required'); return }
    if (!filterExpr.trim()) { toast.error('Filter expression is required'); return }
    setSaving(true)
    try {
      const result = isEdit
        ? await adminRlsRulesApi.update(initial!.id, { filter_expr: filterExpr })
        : await adminRlsRulesApi.create({ role_id: roleId as number, dataset_id: datasetId as number, filter_expr: filterExpr })
      onSave(result)
      toast.success(isEdit ? 'Updated' : 'Rule created')
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Save failed — check the filter expression syntax')
    } finally { setSaving(false) }
  }

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.5)', display: 'flex',
      alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
      <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12,
        padding: 24, width: 460 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
          <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0 }}>{isEdit ? 'Edit Row-Security Rule' : 'New Row-Security Rule'}</h2>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 20, color: 'var(--muted)' }}>×</button>
        </div>

        {/* Role and dataset are fixed once a rule is created (unique per role+dataset pair) — only filter_expr is editable. */}
        <label style={{ display: 'block', marginBottom: 12 }}>
          <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>Role *</div>
          <select value={roleId} onChange={e => setRoleId(e.target.value ? Number(e.target.value) : '')} disabled={isEdit} {...inp}>
            <option value="">Select a role…</option>
            {roles.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}
          </select>
        </label>

        <label style={{ display: 'block', marginBottom: 12 }}>
          <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>Dataset *</div>
          <select value={datasetId} onChange={e => setDatasetId(e.target.value ? Number(e.target.value) : '')} disabled={isEdit} {...inp}>
            <option value="">Select a dataset…</option>
            {datasets.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
        </label>

        <label style={{ display: 'block', marginBottom: 8 }}>
          <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>Filter Expression *</div>
          <textarea
            value={filterExpr}
            onChange={e => setFilterExpr(e.target.value)}
            placeholder="region == 'North'"
            rows={3}
            style={{ width: '100%', fontFamily: 'var(--mono)', fontSize: 12, padding: '6px 8px',
              background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 6,
              color: 'var(--text)', resize: 'vertical', boxSizing: 'border-box' }}
          />
        </label>
        <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 20 }}>
          Rows where this expression is false are hidden from every user assigned this role, for this dataset.
          Validated against the dataset's actual data on save.
        </div>

        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn btn-primary" onClick={handleSave} disabled={saving} style={{ flex: 1 }}>
            {saving ? 'Saving…' : isEdit ? 'Save Changes' : 'Create'}
          </button>
          <button className="btn btn-ghost" onClick={onClose} style={{ fontSize: 12, padding: '6px 14px' }}>Cancel</button>
        </div>
      </div>
    </div>
  )
}

export default function AdminRowSecurityRules() {
  const [rules, setRules] = useState<RowSecurityRule[]>([])
  const [roles, setRoles] = useState<Role[]>([])
  const [datasets, setDatasets] = useState<Dataset[]>([])
  const [loading, setLoading] = useState(true)
  const [modal, setModal] = useState<'add' | RowSecurityRule | null>(null)

  useEffect(() => {
    Promise.all([adminRlsRulesApi.list(), adminRolesApi.list(), datasetsApi.list()])
      .then(([r, ro, d]) => { setRules(r); setRoles(ro); setDatasets(d) })
      .finally(() => setLoading(false))
  }, [])

  const roleName = (id: number) => roles.find(r => r.id === id)?.name ?? `Role #${id}`
  const datasetName = (id: number) => datasets.find(d => d.id === id)?.name ?? `Dataset #${id}`

  const handleSaved = (r: RowSecurityRule) => {
    setRules(prev => {
      const idx = prev.findIndex(x => x.id === r.id)
      return idx >= 0 ? prev.map(x => x.id === r.id ? r : x) : [r, ...prev]
    })
    setModal(null)
  }

  const handleDelete = async (r: RowSecurityRule) => {
    if (!confirm(`Delete this rule for "${roleName(r.role_id)}" on "${datasetName(r.dataset_id)}"?`)) return
    try {
      await adminRlsRulesApi.delete(r.id)
      setRules(prev => prev.filter(x => x.id !== r.id))
      toast.success('Deleted')
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Delete failed')
    }
  }

  const canCreate = roles.length > 0 && datasets.length > 0

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 24 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, flex: 1 }}>Row Security Rules</h1>
        <button className="btn btn-primary btn-sm" onClick={() => setModal('add')} disabled={!canCreate}>
          + New Rule
        </button>
      </div>

      {loading && <p style={{ color: 'var(--muted)' }}>Loading…</p>}

      {!loading && !canCreate && (
        <div style={{ padding: 16, marginBottom: 16, background: 'var(--surface2)', border: '1px solid var(--border)',
          borderRadius: 8, fontSize: 12, color: 'var(--muted)' }}>
          You need at least one role and one dataset before creating a rule.
        </div>
      )}

      {!loading && rules.length === 0 && canCreate && (
        <div style={{ padding: 60, textAlign: 'center', background: 'var(--surface)',
          border: '1px solid var(--border)', borderRadius: 12, color: 'var(--muted)' }}>
          No row-security rules yet — roles with no rule for a dataset see every row within their org.
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {rules.map(r => (
          <div key={r.id} style={{ display: 'flex', alignItems: 'center', gap: 14,
            background: 'var(--surface)', border: '1px solid var(--border)',
            borderRadius: 10, padding: '14px 16px' }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontWeight: 700, fontSize: 14 }}>
                {roleName(r.role_id)} <span style={{ color: 'var(--muted)', fontWeight: 400 }}>on</span> {datasetName(r.dataset_id)}
              </div>
              <div style={{ fontSize: 11, color: 'var(--muted)', fontFamily: 'var(--mono)' }}>{r.filter_expr}</div>
            </div>
            <button className="btn btn-ghost btn-sm" onClick={() => setModal(r)} style={{ fontSize: 11 }}>Edit</button>
            <button className="btn btn-ghost btn-sm" onClick={() => handleDelete(r)} style={{ fontSize: 11, color: 'var(--danger)' }}>Delete</button>
          </div>
        ))}
      </div>

      {modal && (
        <RuleModal
          initial={modal === 'add' ? null : modal}
          roles={roles}
          datasets={datasets}
          onSave={handleSaved}
          onClose={() => setModal(null)}
        />
      )}
    </div>
  )
}
```

- [ ] **Step 2: Verify the app type-checks cleanly end-to-end**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors — every module referenced in `App.tsx` now exists.

- [ ] **Step 3: Run the full frontend test suite**

Run: `cd frontend && npm test`
Expected: all tests pass (no regressions from Tasks 2-7; the only test file is still `authInterceptor.test.ts` plus the pre-existing smoke test, per this plan's Global Constraints).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/admin/AdminRowSecurityRules.tsx
git commit -m "feat: add admin Row Security Rules page"
```

---

### Task 8: Build verification and manual end-to-end browser check

**Files:** none (verification only — no code changes expected; if this step finds a bug, fix it in the file(s) it lives in and commit the fix here).

**Interfaces:** none — this task consumes the complete app from Tasks 1-7.

- [ ] **Step 1: Full production build**

Run: `cd frontend && npm run build`
Expected: builds successfully with no TypeScript errors, no Vite errors.

- [ ] **Step 2: Backend bootstrap check**

The manual browser check below needs a running backend with at least one org admin account. If you don't already have credentials, create one:

Run: `cd backend && python scripts/create_org_admin.py "Manual QA Org" qa-admin@example.com qa-password-123`

(This script was built in Phase 0 — `backend/scripts/create_org_admin.py`. If it reports the email is already in use, that's fine, reuse those credentials.)

- [ ] **Step 3: Start both dev servers**

Run the backend: `cd backend && uvicorn app.main:app --reload` (or however this project's backend is normally started — check `backend/README.md` or existing dev workflow if `uvicorn` isn't the right invocation).
Run the frontend: `cd frontend && npm run dev` (starts on port 3000 per `vite.config.ts`).

- [ ] **Step 4: Manual verification checklist**

Using a real browser (or an automated browser driver — this project has `playwright` available as a dev dependency, useful for scripted verification without hand-clicking), verify each of the following. This is the "use the feature in a browser before reporting complete" step for this UI-heavy plan — do not skip it or mark this task done from a build/type-check pass alone:

1. Visiting `http://localhost:3000/` while logged out redirects to `/login`.
2. Submitting the login form with wrong credentials shows a toast error and does not navigate away from `/login`.
3. Submitting the login form with the QA admin credentials from Step 2 navigates to `/` and shows the Dashboard.
4. The sidebar shows the QA admin's email, org name, and role name at the bottom, plus an "Admin" section (Users / Roles / Row Security links) since this account is an org admin.
5. Navigating to `/admin/roles`, creating a new non-admin role, editing it, and deleting it all work and reflect immediately in the list.
6. Navigating to `/admin/users`, creating a new user assigned to a non-admin role, editing their email/role/active-status, and deleting them all work.
7. Navigating to `/admin/row-security-rules` (with at least one dataset already uploaded — upload one via `/upload` first if none exist) — create a rule for the non-admin role from step 5 against that dataset with a real filter expression referencing one of the dataset's actual columns; confirm it saves. Try creating a rule with a nonsense filter expression (e.g. `not a valid expr(((`) and confirm the backend's validation error surfaces as a toast, not a silent failure or unhandled crash.
8. Log out (sidebar button) — confirm it navigates to `/login` and that navigating back to `/` afterward redirects to `/login` again (session is really cleared, not just UI state).
9. Log back in as the restricted non-admin user created in step 6 (using whatever password was set) — confirm the Admin nav section is NOT visible in the sidebar, and confirm manually navigating the browser to `/admin/roles` redirects away to `/` rather than showing the page.
10. **401-redirect proof:** while logged in, open the browser's dev tools, manually corrupt the `datalytics_token` value in `localStorage` (e.g. append garbage characters), then trigger any API call (e.g. click a nav link that fetches data). Confirm the app redirects to `/login` rather than showing a broken/blank page — this is the behavior Task 1's automated test covers in isolation; this step proves it also works through the real UI.

If any check fails, fix the underlying issue in the relevant file from Tasks 1-7, re-run the specific check, then continue down the list. Do not report this task complete until all 10 checks pass.

- [ ] **Step 5: Final full-suite re-run**

Run: `cd frontend && npm test` and `cd backend && python -m pytest -q`
Expected: both green — this plan makes no backend changes, so the backend suite should be unaffected, but re-running confirms nothing was accidentally broken during manual QA (e.g. if Step 4 required a code fix).

- [ ] **Step 6: Commit (only if Step 4 required fixes; otherwise skip)**

```bash
git add -A
git commit -m "fix: address issues found during Phase 3 manual browser verification"
```

---

## Post-Plan State

After Task 8, the frontend has a complete, working auth flow: a login page, a bearer-token-aware API client that transparently attaches the token to every request and redirects to `/login` on any 401 (expired token, revoked session, or a deactivated account), and three admin screens (Users, Roles, Row Security Rules) that let an org admin fully manage the RLS system built in Phases 0-2 without touching the API directly. Every existing route is now login-gated; the three new admin routes are additionally gated to org-admin users only, with the backend's own `require_org_admin` dependency as the real enforcement boundary and this frontend gate as a UX nicety on top. This completes the full Row-Level Security rollout described in `docs/superpowers/specs/2026-08-13-row-level-security-design.md`.
