import { useState, useEffect, type CSSProperties } from 'react'
import { useDirection } from '../contexts/DirectionContext'
import { Outlet, NavLink, useLocation } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
import CommandPalette from './CommandPalette'
import TopBar from './TopBar'
import { FOLDED_BY_DEFAULT, isUnder, visibleSections, type NavItem } from './navigation'
import { NAV_ITEM_MESSAGE, SECTION_MESSAGE, useT } from '../i18n'
import { useModalDialog } from './ui/useModalDialog'
import {
  ArrowLeftToLine, ArrowRightToLine, ChevronDown, ChevronsLeft, ChevronsRight,
} from 'lucide-react'

function getInitialTheme(): 'dark' | 'light' {
  const stored = localStorage.getItem('theme')
  if (stored === 'light' || stored === 'dark') return stored
  // Light (the blue/white identity) is the product default; a user's explicit
  // toggle above always wins over it.
  return 'light'
}

/** Folded rail sections, by section title. Only explicit choices are stored:
 *  a title absent from the map takes its FOLDED_BY_DEFAULT default, so a
 *  section added later arrives in its intended state for everyone. */
function getInitialFolds(): Record<string, boolean> {
  try {
    const raw = JSON.parse(localStorage.getItem('rail-folded') ?? '{}')
    return raw && typeof raw === 'object' ? raw : {}
  } catch { return {} }
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
  const [folds, setFolds] = useState<Record<string, boolean>>(getInitialFolds)
  const { pathname } = useLocation()

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('theme', theme)
  }, [theme])
  useEffect(() => { localStorage.setItem('rail-expanded', expanded ? '1' : '0') }, [expanded])
  useEffect(() => {
    try { localStorage.setItem('rail-folded', JSON.stringify(folds)) } catch { /* storage full or blocked: folds just won't persist */ }
  }, [folds])

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
  // The command palette's "Switch theme" command: the shell owns the theme,
  // so the palette asks rather than writing the attribute itself.
  useEffect(() => {
    const on = () => setTheme(t => t === 'dark' ? 'light' : 'dark')
    window.addEventListener('datalytics:toggle-theme', on)
    return () => window.removeEventListener('datalytics:toggle-theme', on)
  }, [])
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

  // Labeled, a section heading is the button that folds it: the whole name is
  // the target, and aria-expanded carries the state. While folded it shows
  // how many pages are inside, so a folded section never reads as empty.
  // Collapsed to icons there is no room for a name, so the heading is a rule
  // and every entry stays visible.
  const section = (label: string | null, count: number, bodyId: string) => {
    if (label === null) return null
    const heading = (label && SECTION_MESSAGE[label]) ? t(SECTION_MESSAGE[label]) : label
    if (!labeled) return <div className="dl-rail__rule" />
    const folded = isFolded(label)
    return (
      <button type="button" className="dl-rail__section dl-rail__section--toggle"
        aria-expanded={!folded} aria-controls={bodyId} onClick={() => toggleFold(label)}>
        <span className="dl-rail__section-name">{heading}</span>
        {folded && (
          <span className="dl-rail__count" title={t('nav.sectionItems', { n: count })}>
            <span aria-hidden>{count}</span>
            <span className="dl-sr-only">{t('nav.sectionItems', { n: count })}</span>
          </span>
        )}
        <span aria-hidden className={`dl-rail__chev${folded ? ' dl-rail__chev--folded' : ''}`}>
          <ChevronDown size={14} />
        </span>
      </button>
    )
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

  // A section is folded by the viewer's last choice, else by its default.
  const isFolded = (title: string | null) =>
    title !== null && (folds[title] ?? FOLDED_BY_DEFAULT.has(title))
  const toggleFold = (title: string) =>
    setFolds(f => ({ ...f, [title]: !(f[title] ?? FOLDED_BY_DEFAULT.has(title)) }))

  // Arriving on a page inside a folded section unfolds it: the rail must
  // always show where you are. It is recorded as a choice, so folding it
  // again from here sticks.
  useEffect(() => {
    // Prefix match, ignoring `end`: /datasets/170 lives under Datasets for the
    // rail's purposes even though the Datasets LINK is only active on /datasets.
    const home = sections.find(s => s.title !== null && s.items.some(i => isUnder(pathname, { to: i.to })))
    if (home?.title && isFolded(home.title)) setFolds(f => ({ ...f, [home.title as string]: false }))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname])

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

      {sections.map(s => {
        const bodyId = `rail-section-${(s.title ?? 'root').toLowerCase().replace(/\W+/g, '-')}`
        const hideItems = labeled && isFolded(s.title)
        return (
        <div key={s.title ?? 'root'} className="dl-rail__group">
          {section(s.title, s.items.length, bodyId)}
          <div id={bodyId} className="dl-rail__items">
            {!hideItems && s.items.map(renderItem)}
          </div>
          {/* The workspace tree belongs under Dashboards: it IS the dashboard
              list, organised. It renders nothing while the rail is collapsed
              to icons, where a tree has no room to be legible. */}
        </div>
        )
      })}

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
      <a href="#main" className="dl-skip-link">{t('top.skipToContent')}</a>
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
        <main id="main" tabIndex={-1} className="dl-shell__content"
          style={{ padding: 'var(--dl-shell-pad)',
            ...({ '--dl-shell-pad': narrow ? 'var(--dl-4)' : 'var(--dl-6)' } as CSSProperties) }}>
          <Outlet />
        </main>
      </div>
      <CommandPalette />
    </div>
  )
}
