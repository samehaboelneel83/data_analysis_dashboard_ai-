import { useT, type MessageKey, type TranslateFn } from '../../i18n'
import { dtypeName } from '../../lib/dtypeName'
import { richT } from '../../i18n/builder/panes'
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

const PAGE_TYPES: { value: PageType; label: MessageKey; desc: MessageKey }[] = [
  { value: 'normal',       label: 'bc.panes.page.type.normal',       desc: 'bc.panes.page.type.normal.desc' },
  { value: 'hidden',       label: 'bc.panes.page.type.hidden',       desc: 'bc.panes.page.type.hidden.desc' },
  { value: 'popup',        label: 'bc.panes.page.type.popup',        desc: 'bc.panes.page.type.popup.desc' },
  { value: 'tooltip',      label: 'bc.panes.page.type.tooltip',      desc: 'bc.panes.page.type.tooltip.desc' },
  { value: 'drillthrough', label: 'bc.panes.page.type.drillthrough', desc: 'bc.panes.page.type.drillthrough.desc' },
]

/** The settings groups' English titles. They are ids as much as words:
 *  ExpandableGroup translates the heading it shows, and the search below
 *  matches the English and the translated title alike. */
const GROUP = {
  identity: 'Identity', layout: 'Layout', appearance: 'Appearance', behaviour: 'Behaviour',
  prompt: 'Prompt', actions: 'Actions on this page', visibility: 'Visibility',
} as const

/** The key each group's displayed heading is translated by. */
const GROUP_KEY: Record<string, MessageKey> = {
  'Identity': 'group.identity', 'Layout': 'group.layout', 'Appearance': 'group.appearance',
  'Behaviour': 'group.behaviour', 'Prompt': 'group.prompt',
  'Actions on this page': 'group.actions_on_this_page', 'Visibility': 'group.visibility',
}

// One-line summary of a button's action, e.g. "Button 'Go' → navigate: Page 2".
// Mirrors the action kinds WidgetConfigPanel's Actions group can write. The
// names are the author's, each kept in its own <bdi> by richT.
function actionSummary(tr: TranslateFn, w: Widget, pages: ReportPage[], bookmarks: Bookmark[]): React.ReactNode {
  const cfg = w.config as Record<string, unknown>
  const label = w.title || tr('bc.panes.page.action.button')
  const action = cfg.action as string
  switch (action) {
    case 'navigate': {
      const target = pages.find(p => p.id === cfg.actionPageId)
      return richT(tr, 'bc.panes.page.action.navigate', { label, target: target?.name ?? '—' })
    }
    case 'bookmark': {
      const bm = bookmarks.find(b => b.id === cfg.actionBookmarkId)
      return richT(tr, 'bc.panes.page.action.bookmark', { label, target: bm?.name ?? '—' })
    }
    case 'url':
      return richT(tr, 'bc.panes.page.action.url', { label, target: (cfg.actionUrl as string) ?? '—' })
    case 'report':
      return richT(tr, 'bc.panes.page.action.report', { label, target: String(cfg.actionReportId ?? '—') })
    case 'set_param':
      return richT(tr, 'bc.panes.page.action.setParam', { label,
        param: (cfg.actionParamName as string) ?? '?', value: (cfg.actionParamValue as string) ?? '' })
    default:
      return richT(tr, 'bc.panes.page.action.other', { label, action: String(action) })
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
      .catch(() => toast.error(tr('bc.panes.page.rolesLoadFailed')))
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
      toast.error(tr('bc.panes.page.visibilitySaveFailed'))
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
  // QA3 A5: a rename made elsewhere (the page tab) shows here at once. The
  // name this panel itself just sent is skipped, so a save landing while the
  // author keeps typing never rolls the field back; the sync is not a change
  // of its own, so it saves nothing.
  const sentName = useRef(page.name)
  useEffect(() => {
    if (page.name === sentName.current) return
    sentName.current = page.name
    mounted.current = false
    setName(page.name)
  }, [page.name])

  useEffect(() => {
    if (!mounted.current) { mounted.current = true; return }
    const timer = setTimeout(() => { sentName.current = name || page.name; onUpdate({
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
    }) }, 500)
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
  const groupMatches = (title: string) => title.toLowerCase().includes(filterNeedle)
    || (GROUP_KEY[title] != null && tr(GROUP_KEY[title]).toLowerCase().includes(filterNeedle))
  const groupFilter = (title: string) => filterNeedle
    ? { hidden: !groupMatches(title), forceOpen: groupMatches(title) }
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
        const GROUPS = [GROUP.identity, GROUP.layout, GROUP.appearance, GROUP.behaviour, GROUP.prompt]
        return GROUPS.some(groupMatches) ? null : (
          <p style={{ fontSize: 11, color: 'var(--muted)' }}>
            {richT(tr, 'settings.noMatch', { q: filterText })}
          </p>
        )
      })()}

      <ExpandableGroup id="page-identity" title={GROUP.identity} defaultOpen {...groupFilter(GROUP.identity)}>
        {fld('Tab name', (
          <input value={name} onChange={e => setName(e.target.value)} style={{ width: '100%' }} placeholder={tr('bc.panes.page.namePh')} />
        ))}

        {fld('Display title', (
          <input value={title} onChange={e => setTitle(e.target.value)} style={{ width: '100%' }} placeholder={tr('page.titlePh')} />
        ))}
      </ExpandableGroup>

      <ExpandableGroup id="page-layout" title={GROUP.layout} defaultOpen {...groupFilter(GROUP.layout)}>
        {fld('Page size', (
          <div className="dl-seg" style={{ display: 'flex' }}>
            {(['16:9', '4:3', 'custom'] as const).map(size => (
              <button key={size} type="button" onClick={() => setPageSize(size)} aria-pressed={pageSize === size}
                aria-label={size === 'custom' ? tr('bc.panes.page.size.customAria') : size} className={`dl-seg__btn${pageSize === size ? ' dl-seg__btn--on' : ''}`}
                style={{ flex: 1, justifyContent: 'center' }}>
                {size === 'custom' ? tr('bc.panes.page.size.custom') : size}
              </button>
            ))}
          </div>
        ))}
        {/* One element, not a fragment: `fld` ties the label to the control by
            cloning it with an id, and a fragment swallows that silently. */}
        {fld('Background image', (
          <input value={backgroundUrl} onChange={e => setBackgroundUrl(e.target.value)}
            placeholder={tr('bc.panes.page.backgroundPh')} style={{ width: '100%' }} />
        ))}
        <div style={{ fontSize: 10.5, color: 'var(--muted)', margin: '-6px 0 10px' }}>
          {tr('bc.panes.page.backgroundHelp')}
        </div>
      </ExpandableGroup>

      {palettes && palettes.length > 0 && onPalette && (
        <ExpandableGroup id="page-appearance" title={GROUP.appearance} defaultOpen {...groupFilter(GROUP.appearance)}>
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

      <ExpandableGroup id="page-behaviour" title={GROUP.behaviour} defaultOpen {...groupFilter(GROUP.behaviour)}>
        {fld('Interactions', (
          <>
            <select aria-label={tr('bc.panes.page.interactionMode')} value={interactionMode}
              onChange={e => setInteractionMode(e.target.value as 'manual' | 'linked' | 'oneway' | 'twoway')} style={{ width: '100%' }}>
              <option value="manual">{tr('bc.panes.page.mode.manual')}</option>
              <option value="linked">{tr('bc.panes.page.mode.linked')}</option>
              <option value="oneway">{tr('bc.panes.page.mode.oneway')}</option>
              <option value="twoway">{tr('bc.panes.page.mode.twoway')}</option>
            </select>
            <span style={{ fontSize: 11, color: 'var(--muted)' }}>
              {tr('bc.panes.page.modeHelp')}
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
              <label key={pt.value} title={lastVisible ? tr('bc.panes.page.lastVisibleTitle') : undefined}
                style={{ display: 'flex', alignItems: 'flex-start', gap: 8, cursor: lastVisible ? 'not-allowed' : 'pointer', opacity: lastVisible ? 0.55 : 1, padding: '7px 8px', borderRadius: 6, background: pageType === pt.value ? 'color-mix(in srgb, var(--accent) 12%, transparent)' : 'transparent', border: `1px solid ${pageType === pt.value ? 'var(--accent)' : 'var(--border)'}`, transition: 'all .15s' }}>
                <input type="radio" name="page_type" value={pt.value} checked={pageType === pt.value} disabled={lastVisible} title={lastVisible ? tr('bc.panes.page.lastVisibleRadio') : undefined}
                  onChange={() => setPageType(pt.value)} style={{ marginTop: 2, accentColor: 'var(--accent)' }} />
                <div>
                  <div style={{ fontWeight: 600, fontSize: 12, color: pageType === pt.value ? 'var(--accent)' : 'var(--text)' }}>{tr(pt.label)}</div>
                  <div style={{ fontSize: 11, color: 'var(--muted)' }}>{lastVisible ? tr('bc.panes.page.lastVisibleDesc') : tr(pt.desc)}</div>
                </div>
              </label>
              )
            })}
          </div>
        ))}
      </ExpandableGroup>

      <ExpandableGroup id="page-prompt" title={GROUP.prompt} defaultOpen {...groupFilter(GROUP.prompt)}>
        <p style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 12, lineHeight: 1.5 }}>
          {tr('bc.panes.page.promptIntro')}
        </p>

        {fld('Filter column', (
          <select value={promptColumn} onChange={e => setPromptColumn(e.target.value)} style={{ width: '100%' }}>
            <option value="">{tr('bc.panes.page.noPrompt')}</option>
            {columns.map(c => <option key={c.name} value={c.name}>{c.name} ({dtypeName(tr, c.dtype)})</option>)}
          </select>
        ))}

        {promptColumn && fld('Prompt label', (
          <input value={promptLabel} onChange={e => setPromptLabel(e.target.value)} style={{ width: '100%' }} placeholder={tr('bc.panes.page.promptLabelPh', { column: promptColumn })} />
        ))}
      </ExpandableGroup>

      {actionWidgets.length > 0 && pages && onSelectWidget && (
        <ExpandableGroup id="page-actions" title={GROUP.actions} defaultOpen {...groupFilter(GROUP.actions)}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {actionWidgets.map(w => (
              <button key={w.id} type="button" onClick={() => onSelectWidget(w)}
                style={{ textAlign: 'start', fontSize: 11, padding: '7px 8px', border: '1px solid var(--border)',
                  borderRadius: 6, background: 'var(--surface2)', color: 'var(--text)', cursor: 'pointer' }}>
                {actionSummary(tr, w, pages, bookmarks ?? [])}
              </button>
            ))}
          </div>
        </ExpandableGroup>
      )}

      {reportId != null && orgRoles.length > 0 && (
        <ExpandableGroup id="page-visibility" title={GROUP.visibility} defaultOpen {...groupFilter(GROUP.visibility)}>
          <p style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 8, lineHeight: 1.5 }}>
            {tr('bc.panes.page.visibilityIntro')}
          </p>
          <div role="group" aria-label={tr('bc.panes.page.visibleToRoles')} style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
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
