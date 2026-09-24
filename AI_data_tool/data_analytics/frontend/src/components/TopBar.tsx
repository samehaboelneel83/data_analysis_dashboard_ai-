import { useEffect, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
import NotificationsBell from './NotificationsBell'
import LanguageSwitcher from './LanguageSwitcher'
import { messageForPath, useT } from '../i18n'
import { ChevronDown, LogOut, Menu, Moon, Search, Sun } from 'lucide-react'
import { MOBILE_QUERY, useMediaQuery } from '../hooks/useMediaQuery'

/**
 * The top bar: where am I, find anything, notifications, who am I.
 *
 * The rail below stays pure navigation -- the bell and the identity/logout
 * controls moved up here, which is where every enterprise tool puts them and
 * therefore where people look first. Search is a BUTTON, not a second input:
 * the Ctrl+K palette already is the app's search, and a separate box would be
 * a competing, weaker copy of it. The button opens the same palette (and
 * advertises the shortcut for next time).
 *
 * The theme switch sits here too, beside the language switcher, so the two
 * presentation controls a reader reaches for are next to each other. The
 * SHELL owns the theme (it stamps <html data-theme> and remembers the choice);
 * this bar only shows the switch it is handed, and shows none when rendered
 * without a shell.
 */


function initials(email: string): string {
  const name = email.split('@')[0]
  const parts = name.split(/[._-]+/).filter(Boolean)
  return ((parts[0]?.[0] ?? '') + (parts[1]?.[0] ?? '')).toUpperCase() || name.slice(0, 2).toUpperCase()
}

export default function TopBar({ onOpenNav, theme, onToggleTheme }: {
  onOpenNav?: () => void
  /** Current theme, from the shell. The switch renders only when both this
   *  and `onToggleTheme` are supplied. */
  theme?: 'dark' | 'light'
  onToggleTheme?: () => void
} = {}) {
  const { pathname } = useLocation()
  const { user, logout } = useAuth()
  const t = useT()
  const [menuOpen, setMenuOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)
  const compact = useMediaQuery(MOBILE_QUERY)

  // Outside click / Escape close the user menu -- a menu that only closes by
  // re-clicking its trigger strands keyboard and mouse users alike.
  useEffect(() => {
    if (!menuOpen) return
    const onDown = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false)
    }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setMenuOpen(false) }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [menuOpen])

  return (
    <header style={{ height: 52, flexShrink: 0, background: 'var(--surface)',
      borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center',
      gap: compact ? 8 : 12, padding: compact ? '0 10px' : '0 20px',
      // No `overflow: hidden` here: the bar's own dropdowns (account menu,
      // language, notifications) are absolutely positioned BELOW this 52px
      // strip, and clipping the header clipped them out of sight entirely.
      // The only thing that needed clipping is the title, and the <h1> below
      // already truncates itself.
      minWidth: 0 }}>
      {/* Only rendered below the drawer breakpoint, where the rail is hidden --
          on desktop the rail is always present and a hamburger would open
          something already open. */}
      {onOpenNav && (
        <button onClick={onOpenNav} aria-label={t('nav.open')} title={t('nav.open')}
          style={{ display: 'inline-flex', alignItems: 'center', background: 'none',
            border: 'none', cursor: 'pointer', color: 'var(--muted)', padding: 4 }}>
          <Menu size={18} />
        </button>
      )}
      <h1 style={{ fontSize: 15, fontWeight: 700, margin: 0, whiteSpace: 'nowrap',
        overflow: 'hidden', textOverflow: 'ellipsis', minWidth: 0, flex: compact ? '1 1 0' : undefined }}>
        {t(messageForPath(pathname))}
      </h1>

      <div style={{ flex: 1 }} />

      <button
        onClick={() => window.dispatchEvent(new CustomEvent('datalytics:open-palette'))}
        aria-label={t('top.searchAria')} title={t('top.searchAria')}
        style={{ display: 'flex', alignItems: 'center', gap: 8,
          minWidth: compact ? 0 : 180, flexShrink: 0,
          background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 8,
          padding: compact ? '6px 8px' : '6px 10px', cursor: 'pointer', color: 'var(--muted)', fontSize: 12.5,
          fontFamily: 'var(--sans)' }}>
        <span aria-hidden style={{ display: 'inline-flex' }}><Search size={14} /></span>
        {!compact && <span style={{ flex: 1, textAlign: 'start' }}>{t('top.search')}</span>}
        {!compact && (
          <span aria-hidden style={{ fontFamily: 'var(--mono)', fontSize: 10.5,
            border: '1px solid var(--border)', borderRadius: 4, padding: '1px 5px',
            background: 'var(--surface)' }}>Ctrl K</span>
        )}
      </button>

      <LanguageSwitcher />

      {theme && onToggleTheme && (
        // The glyph and the label name the mode you would switch TO -- a
        // control that showed the current state would read as a status
        // line, not a switch. Same convention as the rail's direction toggle.
        <button onClick={onToggleTheme}
          aria-label={theme === 'dark' ? t('top.light') : t('top.dark')}
          title={theme === 'dark' ? t('top.lightTitle') : t('top.darkTitle')}
          style={{ display: 'inline-flex', alignItems: 'center', background: 'none',
            border: 'none', cursor: 'pointer', padding: '5px 7px', borderRadius: 8,
            color: 'var(--muted)' }}>
          {theme === 'dark'
            ? <Sun size={17} strokeWidth={1.9} aria-hidden />
            : <Moon size={17} strokeWidth={1.9} aria-hidden />}
        </button>
      )}

      <NotificationsBell />

      {user && (
        <div ref={menuRef} style={{ position: 'relative' }}>
          <button onClick={() => setMenuOpen(o => !o)}
            aria-label={t('top.account')} aria-expanded={menuOpen} aria-haspopup="menu"
            style={{ display: 'flex', alignItems: 'center', gap: 8, background: 'none',
              border: 'none', cursor: 'pointer', padding: '4px 6px', borderRadius: 8,
              color: 'var(--text)', fontFamily: 'var(--sans)' }}>
            <span aria-hidden style={{ width: 28, height: 28, borderRadius: '50%',
              background: 'var(--accent)', color: 'var(--mc-accent-fg)', display: 'inline-flex',
              alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 700 }}>
              {initials(user.email)}
            </span>
            {!compact && (
              <span style={{ fontSize: 12.5, fontWeight: 600, maxWidth: 160, overflow: 'hidden',
                textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {user.email.split('@')[0]}
              </span>
            )}
            <span aria-hidden style={{ display: 'inline-flex', color: 'var(--muted)' }}><ChevronDown size={12} /></span>
          </button>

          {menuOpen && (
            <div role="menu" aria-label={t('top.accountMenu')}
              style={{ position: 'absolute', insetInlineEnd: 0, top: '115%', zIndex: 900,
                minWidth: 220, background: 'var(--surface)', border: '1px solid var(--border)',
                borderRadius: 10, boxShadow: '0 8px 24px rgb(15 23 42 / .12)', padding: 6 }}>
              <div style={{ padding: '8px 10px', borderBottom: '1px solid var(--border)', marginBottom: 4 }}>
                <div style={{ fontSize: 12.5, fontWeight: 650, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {user.email}
                </div>
                <div style={{ fontSize: 11, color: 'var(--muted)' }}>
                  {user.role?.name}{user.organization?.name ? ` · ${user.organization.name}` : ''}
                </div>
              </div>
              <button role="menuitem" onClick={() => { setMenuOpen(false); logout() }}
                style={{ display: 'flex', alignItems: 'center', gap: 8, width: '100%',
                  background: 'none', border: 'none', cursor: 'pointer', textAlign: 'start',
                  padding: '8px 10px', borderRadius: 7, fontSize: 12.5, color: 'var(--danger)',
                  fontFamily: 'var(--sans)' }}>
                <span aria-hidden style={{ display: 'inline-flex' }}><LogOut size={13} /></span> {t('top.logout')}
              </button>
            </div>
          )}
        </div>
      )}
    </header>
  )
}
