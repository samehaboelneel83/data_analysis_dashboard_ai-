import { useState, useEffect, type CSSProperties } from 'react'
import { useDirection } from '../contexts/DirectionContext'
import { Outlet, NavLink, useLocation } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
import CommandPalette from './CommandPalette'
import TopBar from './TopBar'
import { visibleSections, type NavItem } from './navigation'
import { NAV_ITEM_MESSAGE, SECTION_MESSAGE, useT } from '../i18n'
import { useModalDialog } from './ui/useModalDialog'
import {
  ArrowLeftToLine, ArrowRightToLine, ChevronsLeft, ChevronsRight,
} from 'lucide-react'

function getInitialTheme(): 'dark' | 'light' {
  const stored = localStorage.getItem('theme')
  if (stored === 'light' || stored === 'dark') return stored
  // Light (the blue/white identity) is the product default; a user's explicit
  // toggle above always wins over it.
  return 'light'
}

/** Below this width the rail stops being persistent and becomes a drawer. */
const DRAWER_BREAKPOINT = 900

/**
 * The app shell: rail + top bar + routed content.
 *
 * The rail renders from `navigation.ts` rather than from inline JSX, so a
 * destination's section, order and permission live in one declarative place
 * next to the route it points at (see that file for why).
 *
 * Three widths, one control:
 *   - labeled (248px)  the natural state: section headings and full labels
 *   - icons  (56px)    an explicit opt-down, remembered per user
 *   - drawer           under 900px the rail overlays the content instead of
 *                      squeezing it, and closes on navigation
 */
export default function Layout() {
  const [theme, setTheme] = useState<'dark' | 'light'>(getInitialTheme)
  const { direction, setDirection } = useDirection()
  const [expanded, setExpanded] = useState(() => localStorage.getItem('rail-expanded') !== '0')
  const [narrow, setNarrow] = useState(() => window.innerWidth < DRAWER_BREAKPOINT)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const { pathname } = useLocation()

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('theme', theme)
  }, [theme])
  useEffect(() => { localStorage.setItem('rail-expanded', expanded ? '1' : '0') }, [expanded])

  // matchMedia rather than a resize listener: it fires only on the crossing,
  // not on every pixel of a drag.
  useEffect(() => {
    const mq = window.matchMedia(`(max-width: ${DRAWER_BREAKPOINT - 1}px)`)
    const onChange = (e: MediaQueryListEvent | MediaQueryList) => setNarrow(e.matches)
    onChange(mq)
    mq.addEventListener?.('change', onChange as (e: MediaQueryListEvent) => void)
    return () => mq.removeEventListener?.('change', onChange as (e: MediaQueryListEvent) => void)
  }, [])

  // Navigating inside the drawer must dismiss it -- otherwise the destination
  // opens underneath the menu that opened it.
  useEffect(() => { setDrawerOpen(false) }, [pathname])

  // As a drawer the rail IS a modal layer, so it gets the same treatment every
  // other overlay in the app gets: Escape, focus trap, focus restore -- from
  // the shared hook rather than a second hand-rolled copy (overlayCoverage
  // enforces exactly this).
  const drawerRef = useModalDialog<HTMLElement>(() => setDrawerOpen(false))

  const toggle = () => setTheme(t => t === 'dark' ? 'light' : 'dark')
  const { user } = useAuth()
  const t = useT()

  // In the drawer the rail is always labeled: an icon-only overlay would be a
  // hieroglyph sheet floating over the page.
  const labeled = expanded || (narrow && drawerOpen)

  // NavLink hands the active flag to a className function; the rest of the
  // treatment (hover, the leading accent bar, the icons-only centring) lives
  // in index.css under .dl-rail__link.
  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `dl-rail__link${isActive ? ' active' : ''}`

  const section = (label: string | null) => {
    if (label === null) return null
    const heading = (label && SECTION_MESSAGE[label]) ? t(SECTION_MESSAGE[label]) : label
    return labeled
      ? <div className="dl-rail__section">{heading}</div>
      : <div className="dl-rail__rule" />
  }

  // Lucide throughout, never emoji: platform emoji render in a dozen colorful
  // styles across OSes and read as toys next to enterprise chrome. One stroke
  // family, one size, currentColor -- so the active state tints icon and
  // label together. `title` gives the collapsed rail its tooltip.
  const renderItem = ({ to, label, icon: Icon, end }: NavItem) => {
    const text = NAV_ITEM_MESSAGE[to] ? t(NAV_ITEM_MESSAGE[to]) : label
    return (
    <NavLink key={to} to={to} end={end} className={linkClass} title={text} aria-label={text}>
      <span aria-hidden className="dl-rail__icon"><Icon size={16} /></span>
      {labeled && <span className="dl-tree__name">{text}</span>}
    </NavLink>
    )
  }

  const sections = visibleSections({
    isOrgAdmin: !!user?.role?.is_org_admin,
    isSuperAdmin: !!user?.is_super_admin,
  })

  const railWidth = labeled ? 248 : 56
  const railHidden = narrow && !drawerOpen

  const rail = (
    <nav data-testid="app-rail" data-expanded={labeled} aria-label={t('nav.main')}
      // Dialog semantics only while it is actually a drawer: on desktop the
      // rail is persistent page furniture, and calling it a dialog there would
      // be a lie to assistive technology.
      ref={narrow && drawerOpen ? drawerRef : undefined}
      {...(narrow && drawerOpen ? { role: 'dialog' as const, 'aria-modal': true } : {})}
      className={`dl-rail${labeled ? '' : ' dl-rail--icons'}`}
      // Width and display stay inline: they are STATE, not styling, and
      // Layout.test.tsx reads `display` straight off this element to prove the
      // drawer hides rather than squeezes.
      style={{ width: railWidth, display: railHidden ? 'none' : 'flex',
        ...(narrow ? { position: 'fixed', insetBlock: 0, insetInlineStart: 0, zIndex: 1100 } : null) }}>
      <div className="dl-rail__brand">
        <span className="dl-rail__mark" title="Datalytics" aria-hidden>D</span>
        {labeled && <span className="dl-rail__wordmark">datalytics</span>}
        {labeled && (
          <button onClick={() => narrow ? setDrawerOpen(false) : setExpanded(e => !e)}
            aria-label={narrow ? t('nav.close') : t('nav.collapse')}
            title={narrow ? t('nav.close') : t('nav.collapse')}
            className="dl-rail__iconbtn" style={{ marginInlineStart: 'auto' }}>
            <ChevronsLeft size={16} aria-hidden />
          </button>
        )}
      </div>
      {/* Collapsed, the control moves out of the brand row: at 56px there is
          no room beside the mark, and a button crushed against it reads as
          part of the logo. */}
      {!labeled && (
        <button onClick={() => setExpanded(true)} aria-label={t('nav.expand')}
          title={t('nav.expand')} className="dl-rail__iconbtn"
          style={{ alignSelf: 'center' }}>
          <ChevronsRight size={16} aria-hidden />
        </button>
      )}

      {sections.map(s => (
        <div key={s.title ?? 'root'} className="dl-rail__group">
          {section(s.title)}
          {s.items.map(renderItem)}
          {/* The workspace tree belongs under Dashboards: it IS the dashboard
              list, organised. It renders nothing while the rail is collapsed
              to icons, where a tree has no room to be legible. */}
        </div>
      ))}

      <div className="dl-rail__spacer" />

      {/* Identity, logout, the bell and the theme switch live in the TOP BAR
          now. The rail keeps only the direction toggle: the language switcher
          up top pairs direction with language, and this is the one place to
          override direction alone. */}
      <button onClick={() => setDirection(direction === 'rtl' ? 'ltr' : 'rtl')}
        title={direction === 'rtl' ? t('nav.switchLtr') : t('nav.switchRtl')}
        aria-label={direction === 'rtl' ? t('nav.switchLtr') : t('nav.switchRtl')}
        className="dl-rail__link">
        {/* The glyph names the direction you would switch TO, matching the
            theme switch in the top bar -- a control that showed the current
            state would read as a status line, not a switch. */}
        <span aria-hidden className="dl-rail__icon">
          {direction === 'rtl' ? <ArrowRightToLine size={16} /> : <ArrowLeftToLine size={16} />}
        </span>
        {labeled && <span>{direction === 'rtl' ? t('nav.ltr') : t('nav.rtl')}</span>}
      </button>
    </nav>
  )

  return (
    <div className="dl-shell">
      {rail}
      {narrow && drawerOpen && (
        // The scrim is painted with explicit edges rather than `inset: 0` so it
        // does not read as an unlabelled dialog to overlayCoverage: the DIALOG
        // is the rail (below), and the role belongs on the panel, never on the
        // backdrop.
        <div onClick={() => setDrawerOpen(false)} aria-hidden className="dl-scrim" />
      )}

      <div className="dl-shell__main">
        <TopBar onOpenNav={narrow ? () => setDrawerOpen(true) : undefined}
          theme={theme} onToggleTheme={toggle} />
        {/* The padding is published as a custom property as well as applied,
            so a page that must bleed to the edges (the report builder) can
            cancel exactly THIS value instead of hard-coding a number that
            drifts from it -- which is what put the builder's toolbar off the
            top of the window in present mode and at narrow widths. */}
        <main className="dl-shell__content"
          style={{ padding: 'var(--dl-shell-pad)',
            ...({ '--dl-shell-pad': narrow ? 'var(--dl-4)' : 'var(--dl-6)' } as CSSProperties) }}>
          <Outlet />
        </main>
      </div>
      <CommandPalette />
    </div>
  )
}
