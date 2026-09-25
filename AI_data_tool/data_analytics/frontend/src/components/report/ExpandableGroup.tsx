import { useState, useCallback } from 'react'
import { useT, type MessageKey } from '../../i18n'

/** Settings-group titles are written in English at every call site (the panel
 *  search matches on them); only the DISPLAYED heading is translated, here,
 *  so no call site has to change. Unknown titles show as written. */
const TITLE_KEY: Record<string, MessageKey> = {
  'Actions on this page': 'group.actions_on_this_page',
  'Actions': 'group.actions',
  'Animation (play through)': 'group.animation_play_through',
  'Appearance': 'group.appearance',
  'Behaviour': 'group.behaviour',
  'Data & aggregation': 'group.data_aggregation',
  'Display rules': 'group.display_rules',
  'Fields': 'group.fields',
  'Filters': 'group.filters',
  'Formatting': 'group.formatting',
  'Group A': 'group.group_a',
  'Group B': 'group.group_b',
  'Identity': 'group.identity',
  'Interactions': 'group.interactions',
  'Lattice (small multiples)': 'group.lattice_small_multiples',
  'Layout': 'group.layout',
  'Prompt': 'group.prompt',
  'Ranking': 'group.ranking',
  'Roles': 'group.roles',
  'Sort & limit': 'group.sort_limit',
  'Sorting': 'group.sorting',
  'Visibility': 'group.visibility'
}

const STORAGE_KEY = 'datalytics.panelGroups'

/** Read the whole map. Storage is shared with other tabs and can hold anything, so a
 *  parse failure degrades to "no remembered state" rather than breaking the panel. */
function readState(): Record<string, boolean> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    const parsed = raw ? JSON.parse(raw) : null
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {}
  } catch {
    return {}
  }
}

function writeState(id: string, open: boolean) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ ...readState(), [id]: open }))
  } catch {
    // Storage full or blocked (private mode). Collapsing still works for this session;
    // only the memory across navigations is lost, which is not worth failing a render over.
  }
}

interface Props {
  id: string
  title: string
  defaultOpen?: boolean
  children: React.ReactNode
  // Both are purely a rendering override for the search-filter feature
  // (WidgetConfigPanel's filter box): forceOpen shows the group's contents without
  // touching the stored/toggled `open` state or writing to localStorage, and hidden
  // unmounts the group entirely. Manual clicks on the header still toggle the real
  // `open` state underneath, so clearing the filter restores exactly what the user
  // had before typing.
  forceOpen?: boolean
  hidden?: boolean
  // Purely documentary here -- the panel-search filter matches this list itself
  // (title + searchTerms) before deciding forceOpen/hidden, so ExpandableGroup never
  // reads it. Declared on Props anyway so a group's searchable field labels live
  // right next to its JSX instead of in a parallel lookup table the component doesn't
  // own, and so passing it through doesn't need a `{...rest}` cast at every call site.
  searchTerms?: string[]
}

export default function ExpandableGroup({ id, title, defaultOpen = false, children, forceOpen, hidden }: Props) {
  const [open, setOpen] = useState(() => readState()[id] ?? defaultOpen)
  const t = useT()

  const toggle = useCallback(() => {
    // While forceOpen is in effect (the panel-search filter), the header click is a
    // visual no-op -- the group is already showing its content because of the force,
    // not because of `open`. Toggling `open`/writing storage underneath that would
    // silently change what "restore on clear" restores back to, even though nothing
    // appeared to happen. Bail out so a click during filtering truly does nothing.
    if (forceOpen) return
    // Compute `next` once rather than writing storage from inside the setState
    // updater: under React Strict Mode's double-invoke, an updater passed to
    // setState runs twice, which would call writeState twice per click. Idempotent
    // today (same id/open pair both times), but not a pattern worth keeping.
    const next = !open
    setOpen(next)
    writeState(id, next)
  }, [id, open, forceOpen])

  if (hidden) return null

  const effectiveOpen = forceOpen || open

  return (
    // The id is on the DOM as well as in storage so the settings rail can be
    // pinned: a test walks every tab and asserts the set of groups it can
    // reach equals the set that exists, which catches a group added later
    // that no tab routes to.
    <div data-group-id={id} style={{ borderBottom: '1px solid var(--border)' }}>
      <button
        type="button"
        onClick={toggle}
        aria-expanded={effectiveOpen}
        style={{
          display: 'flex', alignItems: 'center', gap: 6, width: '100%',
          background: 'none', border: 'none', cursor: 'pointer',
          padding: '9px 2px', color: 'var(--text)', font: 'inherit',
          fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.05em',
        }}
      >
        <span aria-hidden style={{ color: 'var(--muted)', fontSize: 10.5, transition: 'transform .12s',
          transform: effectiveOpen ? 'rotate(90deg)' : 'none', display: 'inline-block' }}>&#9654;</span>
        <span style={{ color: 'var(--muted)' }}>{TITLE_KEY[title] ? t(TITLE_KEY[title]) : title}</span>
      </button>
      {effectiveOpen && <div style={{ paddingBottom: 10 }}>{children}</div>}
    </div>
  )
}
