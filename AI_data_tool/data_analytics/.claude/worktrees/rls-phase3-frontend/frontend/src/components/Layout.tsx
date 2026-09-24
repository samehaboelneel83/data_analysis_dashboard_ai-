import { useState, useEffect } from 'react'
import { Outlet, NavLink } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'

function getInitialTheme(): 'dark' | 'light' {
  const stored = localStorage.getItem('theme')
  if (stored === 'light' || stored === 'dark') return stored
  return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'
}

const navStyle = ({ isActive }: { isActive: boolean }): React.CSSProperties => ({
  display: 'flex', alignItems: 'center', gap: 8,
  padding: '8px 12px', borderRadius: 8, textDecoration: 'none', fontSize: 13,
  color: isActive ? 'var(--accent)' : 'var(--muted)',
  background: isActive ? 'rgba(108,143,255,.1)' : 'transparent',
  fontWeight: isActive ? 600 : 400, transition: 'all .15s',
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
    <div style={{ display: 'flex', height: '100%' }}>
      {/* Sidebar */}
      <nav style={{
        width: 200, flexShrink: 0,
        background: 'var(--surface)', borderRight: '1px solid var(--border)',
        display: 'flex', flexDirection: 'column', padding: '20px 12px', gap: 4,
      }}>
        <div style={{ fontWeight: 800, fontSize: 17, color: 'var(--accent)', marginBottom: 20, paddingLeft: 8 }}>
          Datalytics
        </div>
        <NavLink to="/"       style={navStyle} end>⊞ Datasets</NavLink>
        <NavLink to="/upload" style={navStyle}>↑ Upload</NavLink>
        <NavLink to="/reports" style={navStyle}>📊 Reports</NavLink>
        <NavLink to="/connections" style={navStyle}>🔌 Connections</NavLink>

        {user?.role.is_org_admin && (
          <>
            <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase',
              letterSpacing: '.06em', padding: '16px 8px 4px' }}>Admin</div>
            <NavLink to="/admin/users" style={navStyle}>👤 Users</NavLink>
            <NavLink to="/admin/roles" style={navStyle}>🛡 Roles</NavLink>
            <NavLink to="/admin/row-security-rules" style={navStyle}>🔒 Row Security</NavLink>
          </>
        )}

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
      </nav>

      {/* Main content */}
      <main style={{ flex: 1, overflow: 'auto', padding: 28, background: 'var(--bg)' }}>
        <Outlet />
      </main>
    </div>
  )
}
