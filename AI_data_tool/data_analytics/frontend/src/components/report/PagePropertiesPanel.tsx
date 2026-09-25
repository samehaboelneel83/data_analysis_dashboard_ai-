import { useT, type MessageKey } from '../../i18n'
import React, { useState, useEffect, useRef } from 'react'
import { Check } from 'lucide-react'
import toast from 'react-hot-toast'
import type { ReportPage, PageType, Widget, Bookmark } from '../../types/report'
import type { DatasetColumn } from '../../services/api'
import { pageVisibilityApi } from '../../services/api'
import ExpandableGroup from './ExpandableGroup'

interface Props {
  reportId?: number
  page:     ReportPage
  columns:  DatasetColumn[]
  onUpdate: (data: Partial<ReportPage>) => void
  // Task B2 "Actions on this page" list — the report's other pages (to resolve a
  // navigate action's target name) and bookmarks (to resolve a bookmark action's
  // target name), plus the existing widget-selection setter so clicking a row jumps
  // straight to that widget's own config panel. All optional: the list itself is
  // omitted (not merely empty) when pages/onSelectWidget aren't supplied, same as
  // every other optional-prop section in this panel.
  pages?: ReportPage[]
  bookmarks?: Bookmark[]
  onSelectWidget?: (widget: Widget) => void
  /** The report's colour palettes, when the caller lets this panel switch
   *  them. The palette is REPORT-wide; it lives here because this is the
   *  panel an author has open when nothing is selected. */
  palettes?: { key: string; name: string; colors: string[] }[]
  currentPalette?: string
  onPalette?: (key: string) => void
}

const PAGE_TYPES: { value: PageType; label: string; desc: string }[] = [
  { value: 'normal',      label: 'Normal',      desc: 'Standard visible tab' },
  { value: 'hidden',      label: 'Hidden',       desc: 'Tab hidden in view mode' },
  { value: 'popup',       label: 'Popup',        desc: 'Rendered as floating overlay' },
  { value: 'tooltip',     label: 'Tooltip',      desc: 'Shown as a hover tooltip on another visual' },
  { value: 'drillthrough',label: 'Drillthrough', desc: 'Reached by drilling through from another page' },
]

// One-line summary of a button's action, e.g. "Button 'Go' → navigate: Page 2".
// Mirrors the action kinds WidgetConfigPanel's Actions group can write.
function actionSummary(w: Widget, pages: ReportPage[], bookmarks: Bookmark[]): string {
  const cfg = w.config as Record<string, unknown>
  const label = w.title || 'Button'
  const action = cfg.action as string
  switch (action) {
    case 'navigate': {
      const target = pages.find(p => p.id === cfg.actionPageId)
      return `Button '${label}' → navigate: ${target?.name ?? '—'}`
    }
    case 'bookmark': {
      const bm = bookmarks.find(b => b.id === cfg.actionBookmarkId)
      return `Button '${label}' → apply bookmark: ${bm?.name ?? '—'}`
    }
    case 'url':
      return `Button '${label}' → open URL: ${(cfg.actionUrl as string) ?? '—'}`
    case 'report':
      return `Button '${label}' → go to report #${cfg.actionReportId ?? '—'}`
    case 'set_param':
      return `Button '${label}' → set ${(cfg.actionParamName as string) ?? '?'} = ${(cfg.actionParamValue as string) ?? ''}`
    default:
      return `Button '${label}' → ${action}`
  }
}

export default function PagePropertiesPanel({ reportId, page, columns, onUpdate, pages, bookmarks, onSelectWidget, palettes, currentPalette, onPalette }: Props) {
  const tr = useT()
  /** Finding a setting by name. The widget panel beside this one has had this
   *  since it grew past a screenful; without it here the search an author just
   *  learned stopped working the moment they selected the page. */
  const [filterText, setFilterText] = useState('')

  const [orgRoles, setOrgRoles] = useState<{ id: number; name: string }[]>([])
  const [visibleRoleIds, setVisibleRoleIds] = useState<number[]>([])
  useEffect(() => {
    if (!reportId) return
    pageVisibilityApi.roles().then(setOrgRoles)
      .catch(() => toast.error('Could not load roles'))
    pageVisibilityApi.get(reportId, page.id).then(v => setVisibleRoleIds(v.role_ids)).catch(() => {})
  }, [reportId, page.id])

  const toggleRole = (roleId: number) => {
    if (!reportId) return
    const next = visibleRoleIds.includes(roleId)
      ? visibleRoleIds.filter(r => r !== roleId)
      : [...visibleRoleIds, roleId]
    // Optimistic, then REVERTED on failure. Swallowing this was the most
    // consequential silent catch in the app: page visibility is a security
    // control, and a failed write left the panel showing a page as restricted
    // to certain roles when the server still had it visible to everyone.
    const previous = visibleRoleIds
    setVisibleRoleIds(next)
    pageVisibilityApi.set(reportId, page.id, next).catch(() => {
      setVisibleRoleIds(previous)
      toast.error('Could not save page visibility — the page is unchanged')
    })
  }
  const [name,          setName]          = useState(page.name)
  const [title,         setTitle]         = useState(page.title ?? '')
  const [pageType,      setPageType]      = useState<PageType>(page.page_type ?? 'normal')
  const [promptColumn,  setPromptColumn]  = useState(page.prompt_column ?? '')
  const [promptLabel,   setPromptLabel]   = useState(page.prompt_label ?? '')
  const [pageSize,      setPageSize]      = useState(page.page_size ?? '16:9')
  /** A picture the page's objects sit on. An object set to a transparent
   *  background then lets it through -- that pair is how a chart, a headline
   *  number and a line plot end up floating on a photograph. */
  const [backgroundUrl, setBackgroundUrl] = useState(page.background_url ?? '')
  const [interactionMode, setInteractionMode] = useState<'manual' | 'linked' | 'oneway' | 'twoway'>(
    page.mobile_layout?.interaction_mode ?? 'manual')

  const mounted = useRef(false)

  useEffect(() => {
    mounted.current = false
    setName(page.name)
    setTitle(page.title ?? '')
    setPageType(page.page_type ?? 'normal')
    setPromptColumn(page.prompt_column ?? '')
    setPromptLabel(page.prompt_label ?? '')
    setPageSize(page.page_size ?? '16:9')
    setBackgroundUrl(page.background_url ?? '')
    setInteractionMode(page.mobile_layout?.interaction_mode ?? 'manual')
  }, [page.id])

  useEffect(() => {
    if (!mounted.current) { mounted.current = true; return }
    const timer = setTimeout(() => onUpdate({
      name:          name || page.name,
      title:         title || undefined,
      page_type:     pageType,
      prompt_column: promptColumn || undefined,
      prompt_label:  promptLabel || undefined,
      page_size:     pageSize,
      // Sent even when empty: '' is how the page's backdrop is cleared, and
      // `undefined` would leave the old one in place.
      background_url: backgroundUrl.trim(),
      // mobile_layout doubles as the page's settings JSON (create_all never
      // ALTERs deployed tables, so no new column): interaction_mode rides
      // alongside the mobile order/hidden keys, all preserved.
      mobile_layout: { ...(page.mobile_layout ?? {}),
        ...(interactionMode === 'manual'
          ? { interaction_mode: undefined }
          : { interaction_mode: interactionMode }) },
    }), 500)
    return () => clearTimeout(timer)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [name, title, pageType, promptColumn, promptLabel, pageSize, interactionMode,
      backgroundUrl])

  /** A labelled field.
   *
   *  `htmlFor` is derived from the label and handed to the control, because a
   *  <label> that is not tied to its input is decoration: a screen reader
   *  announces "edit text" with nothing to say what it sets, and a test cannot
   *  find it by name either. Three controls in this panel were in that state.
   *
   *  Only a single form control is given the id -- where the field holds a group
   *  of buttons or radios, each of those carries its own accessible name and
   *  pointing the label at their wrapper would be worse than leaving it. */
  const fld = (lbl: string, el: React.ReactNode) => {
    const id = 'page-' + lbl.toLowerCase().replace(/[^a-z0-9]+/g, '-')
    const single = React.isValidElement(el)
      && typeof el.type === 'string'
      && ['input', 'select', 'textarea'].includes(el.type)
    return (
      <div style={{ marginBottom: 12 }}>
        <label htmlFor={single ? id : undefined}
          style={{ display: 'block', fontSize: 11, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 4 }}>{(() => { const k = `fld.${lbl}` as MessageKey; const v = tr(k); return v && v !== k ? v : lbl })()}</label>
        {single ? React.cloneElement(el as React.ReactElement, { id }) : el}
      </div>
    )
  }

  // "Actions on this page" — every widget on the active page whose config carries an
  // `action` (currently only buttons write one, but this reads any widget generically
  // so it keeps working if another widget type gains actions later).
  const actionWidgets = (page.widgets ?? []).filter(w => (w.config as Record<string, unknown>)?.action)

  const filterNeedle = filterText.trim().toLowerCase()
  const groupFilter = (title: string) => filterNeedle
    ? { hidden: !title.toLowerCase().includes(filterNeedle), forceOpen: title.toLowerCase().includes(filterNeedle) }
    : {}

  return (
    <div style={{ padding: '14px 14px 0', fontSize: 13 }}>
      {/* The panel's title, not a section label: sentence case at the section
          size, so it sits above the 10px caps labels inside it instead of
          being the loudest line in the panel. */}
      <div style={{ fontWeight: 650, marginBottom: 14, fontSize: 14, color: 'var(--text)' }}>
        {tr('page.props')}
      </div>

      <div style={{ marginBottom: 12 }}>
        <input type="search" value={filterText} onChange={e => setFilterText(e.target.value)}
          placeholder={tr('settings.filterPh')} aria-label={tr('settings.filter')} style={{ width: '100%' }} />
      </div>

      {/* Same mechanism the widget panel uses: a matching group is forced open
          and the rest hidden, and clearing the box leaves no trace because
          nothing here writes to a group's own open state. */}
      {(() => {
        const needle = filterText.trim().toLowerCase()
        if (!needle) return null
        const GROUPS = ['identity', 'layout', 'appearance', 'behaviour', 'prompt']
        return GROUPS.some(g => g.includes(needle)) ? null : (
          <p style={{ fontSize: 11, color: 'var(--muted)' }}>
            No setting matches “{filterText}”.
          </p>
        )
      })()}

      <ExpandableGroup id="page-identity" title="Identity" defaultOpen {...groupFilter("Identity")}>
        {fld('Tab name', (
          <input value={name} onChange={e => setName(e.target.value)} style={{ width: '100%' }} placeholder="Page name" />
        ))}

        {fld('Display title', (
          <input value={title} onChange={e => setTitle(e.target.value)} style={{ width: '100%' }} placeholder={tr('page.titlePh')} />
        ))}
      </ExpandableGroup>

      <ExpandableGroup id="page-layout" title="Layout" defaultOpen {...groupFilter("Layout")}>
        {fld('Page size', (
          <div className="dl-seg" style={{ display: 'flex' }}>
            {(['16:9', '4:3', 'custom'] as const).map(size => (
              <button key={size} type="button" onClick={() => setPageSize(size)} aria-pressed={pageSize === size}
                aria-label={size} className={`dl-seg__btn${pageSize === size ? ' dl-seg__btn--on' : ''}`}
                style={{ flex: 1, justifyContent: 'center' }}>
                {size === 'custom' ? 'Custom' : size}
              </button>
            ))}
          </div>
        ))}
        {/* One element, not a fragment: `fld` ties the label to the control by
            cloning it with an id, and a fragment swallows that silently. */}
        {fld('Background image', (
          <input value={backgroundUrl} onChange={e => setBackgroundUrl(e.target.value)}
            placeholder="https://… or /uploads/…" style={{ width: '100%' }} />
        ))}
        <div style={{ fontSize: 10.5, color: 'var(--muted)', margin: '-6px 0 10px' }}>
          Objects with a transparent background let it show through. Only http(s)
          URLs and paths on this server are accepted.
        </div>
      </ExpandableGroup>

      {palettes && palettes.length > 0 && onPalette && (
        <ExpandableGroup id="page-appearance" title="Appearance" defaultOpen {...groupFilter("Appearance")}>
          <div className="dl-field__label" style={{ marginBottom: 6 }}>{tr('page.palette')}</div>
          {/* A list rather than a row of dots: each palette shows its first
              four colours AND its name, so the choice is made by what the
              charts will look like, not by guessing from one swatch. */}
          <div className="dl-palettes">
            {palettes.map(p => {
              const on = (currentPalette ?? 'default') === p.key
              return (
                <button key={p.key} type="button" aria-label={p.name} aria-pressed={on}
                  className={`dl-palette${on ? ' dl-palette--on' : ''}`} onClick={() => onPalette(p.key)}>
                  <span aria-hidden className="dl-palette__swatch">
                    {p.colors.slice(0, 4).map((c, i) => <span key={i} style={{ background: c }} />)}
                  </span>
                  <span className="dl-palette__name">{p.name}</span>
                  {on && <Check size={15} aria-hidden className="dl-palette__check" />}
                </button>
              )
            })}
          </div>
        </ExpandableGroup>
      )}

      <ExpandableGroup id="page-behaviour" title="Behaviour" defaultOpen {...groupFilter("Behaviour")}>
        {fld('Interactions', (
          <>
            <select aria-label="Page interaction mode" value={interactionMode}
              onChange={e => setInteractionMode(e.target.value as 'manual' | 'linked' | 'oneway' | 'twoway')} style={{ width: '100%' }}>
              <option value="manual">Manual (per-widget settings)</option>
              <option value="linked">Linked selection (highlight everywhere)</option>
              <option value="oneway">One-way filter (single source)</option>
              <option value="twoway">Two-way filter (filters accumulate)</option>
            </select>
            <span style={{ fontSize: 11, color: 'var(--muted)' }}>
              An automatic mode overrides every widget's own interaction settings on this page.
            </span>
          </>
        ))}

        {fld('Page type', (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {PAGE_TYPES.map(pt => {
              // A report must keep one page a reader lands on. Said on the
              // option, not discovered as a report that opens to nothing.
              const lastVisible = pt.value !== 'normal' && (page.page_type ?? 'normal') === 'normal'
                && (pages ?? []).filter(p => (p.page_type ?? 'normal') === 'normal').length <= 1
              return (
              <label key={pt.value} title={lastVisible ? 'This is the only visible page. Readers need one page to open on — make another page Normal first.' : undefined}
                style={{ display: 'flex', alignItems: 'flex-start', gap: 8, cursor: lastVisible ? 'not-allowed' : 'pointer', opacity: lastVisible ? 0.55 : 1, padding: '7px 8px', borderRadius: 6, background: pageType === pt.value ? 'color-mix(in srgb, var(--accent) 12%, transparent)' : 'transparent', border: `1px solid ${pageType === pt.value ? 'var(--accent)' : 'var(--border)'}`, transition: 'all .15s' }}>
                <input type="radio" name="page_type" value={pt.value} checked={pageType === pt.value} disabled={lastVisible} title={lastVisible ? 'At least one page must stay visible' : undefined}
                  onChange={() => setPageType(pt.value)} style={{ marginTop: 2, accentColor: 'var(--accent)' }} />
                <div>
                  <div style={{ fontWeight: 600, fontSize: 12, color: pageType === pt.value ? 'var(--accent)' : 'var(--text)' }}>{pt.label}</div>
                  <div style={{ fontSize: 11, color: 'var(--muted)' }}>{lastVisible ? 'Not available: this is the only visible page' : pt.desc}</div>
                </div>
              </label>
              )
            })}
          </div>
        ))}
      </ExpandableGroup>

      <ExpandableGroup id="page-prompt" title="Prompt" defaultOpen {...groupFilter("Prompt")}>
        <p style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 12, lineHeight: 1.5 }}>
          A prompt lets viewers filter all widgets by entering a value. Select the column to filter on.
        </p>

        {fld('Filter column', (
          <select value={promptColumn} onChange={e => setPromptColumn(e.target.value)} style={{ width: '100%' }}>
            <option value="">— no prompt —</option>
            {columns.map(c => <option key={c.name} value={c.name}>{c.name} ({c.dtype})</option>)}
          </select>
        ))}

        {promptColumn && fld('Prompt label', (
          <input value={promptLabel} onChange={e => setPromptLabel(e.target.value)} style={{ width: '100%' }} placeholder={`Filter by ${promptColumn}`} />
        ))}
      </ExpandableGroup>

      {actionWidgets.length > 0 && pages && onSelectWidget && (
        <ExpandableGroup id="page-actions" title="Actions on this page" defaultOpen {...groupFilter("Actions on this page")}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {actionWidgets.map(w => (
              <button key={w.id} type="button" onClick={() => onSelectWidget(w)}
                style={{ textAlign: 'start', fontSize: 11, padding: '7px 8px', border: '1px solid var(--border)',
                  borderRadius: 6, background: 'var(--surface2)', color: 'var(--text)', cursor: 'pointer' }}>
                {actionSummary(w, pages, bookmarks ?? [])}
              </button>
            ))}
          </div>
        </ExpandableGroup>
      )}

      {reportId != null && orgRoles.length > 0 && (
        <ExpandableGroup id="page-visibility" title="Visibility" defaultOpen {...groupFilter("Visibility")}>
          <p style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 8, lineHeight: 1.5 }}>
            Restrict this page to specific roles. No selection means everyone sees it;
            org admins always do. Enforced on the server — a restricted page is never
            sent to an excluded viewer at all.
          </p>
          <div role="group" aria-label="Visible to roles" style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {orgRoles.map(r => (
              <label key={r.id} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12 }}>
                <input type="checkbox" checked={visibleRoleIds.includes(r.id)}
                  onChange={() => toggleRole(r.id)} />
                {r.name}
              </label>
            ))}
          </div>
        </ExpandableGroup>
      )}
    </div>
  )
}
