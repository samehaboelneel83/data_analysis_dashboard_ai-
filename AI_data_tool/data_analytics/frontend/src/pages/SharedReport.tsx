import { useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { sharedApi } from '../services/api'
import WidgetRenderer from '../components/report/WidgetRenderer'
import { CrossFilterProvider } from '../components/report/CrossFilterContext'
import FilterBar from '../components/report/FilterBar'
import FloatingFilterWindow from '../components/report/FloatingFilterWindow'

/** Cross-source mappings the server publishes with a report (Phase 6.1): the
 *  relationships among its datasets and, per dataset, only the column names
 *  those relationships use -- enough to translate a cross-filter, nothing more. */
type PublishedMappings = {
  relationships?: { from_dataset_id: number; from_column: string; to_dataset_id: number; to_column: string }[]
  datasets?: Record<string, { columns: { name: string }[] }>
}
import type { Report, ReportPage, Widget } from '../types/report'

// Sentinel distinguishing "the server throttled this widget's request" from
// "the widget's own query genuinely returned nothing" -- both look like a
// falsy dataOverride otherwise, and silently rendering the first as the
// second (a blank widget, no explanation) is exactly what six colleagues
// hitting one link's guest rate-limit bucket used to see.
const RATE_LIMITED = Symbol('rate-limited')

/**
 * The guest view behind a share link: read-only, no login, every widget's data
 * resolved server-side AS THE LINK'S CREATOR from its saved config. Static on
 * purpose — no cross-filters, no editing — because the anonymous session holds
 * no credentials to re-query with.
 */
export default function SharedReport() {
  const { token } = useParams()
  const [report, setReport] = useState<(Report & { column_formats?: Record<string, unknown>; pinned?: boolean }) | null>(null)
  const [data, setData] = useState<Record<number, unknown> | null>(null)
  const [pageIdx, setPageIdx] = useState(0)
  // The mobile read-only viewer: a phone gets a stacked, swipeable reading
  // layout instead of the 12-column canvas, which is unreadable at 375px.
  const [narrow, setNarrow] = useState(() => typeof window !== 'undefined' && !!window.matchMedia?.('(max-width: 700px)').matches)
  useEffect(() => {
    const mq = typeof window !== 'undefined' ? window.matchMedia?.('(max-width: 700px)') : undefined
    if (!mq) return
    const on = () => setNarrow(mq.matches)
    mq.addEventListener?.('change', on)
    return () => mq.removeEventListener?.('change', on)
  }, [])
  const touchX = useRef<number | null>(null)
  const [error, setError] = useState('')

  function fetchWidget(tok: string, w: Widget) {
    return sharedApi.widgetData(tok, w.id).catch(e => (
      e?.response?.status === 429 ? RATE_LIMITED : null
    ))
  }

  // Each GET of the share route is recorded as a VIEW for the link's owner,
  // so fetching twice for one visit inflates a number somebody reads. React
  // StrictMode double-invokes effects in development, and a remount would do
  // the same in any build, so the token already loaded is remembered here.
  // (The server also drops an identical repeat inside a few seconds, so a
  // client that does fetch twice cannot skew the count either.)
  const loadedToken = useRef<string | null>(null)

  useEffect(() => {
    if (!token || loadedToken.current === token) return
    loadedToken.current = token
    sharedApi.report(token).then(async r => {
      // Widgets render only after every override is resolved: a WidgetRenderer
      // mounted without its override would fetch through the authed API, and
      // the anonymous 401 would bounce this whole page to /login -- exactly
      // what the first drive of this view did.
      const widgets: Widget[] = r.pages.flatMap((p: ReportPage) => p.widgets ?? [])
      const STATIC = new Set(['text', 'button', 'image', 'shape', 'container', 'web_content'])
      const results = await Promise.all(widgets.map(w =>
        STATIC.has(w.widget_type) ? Promise.resolve(null) : fetchWidget(token, w)))
      setReport(r)
      setData(Object.fromEntries(widgets.map((w, i) => [w.id, results[i]])))
    }).catch(() => setError('This link does not exist or has expired.'))
  }, [token])

  function retryWidget(w: Widget) {
    if (!token) return
    fetchWidget(token, w).then(result => setData(d => ({ ...(d ?? {}), [w.id]: result })))
  }

  if (error) return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', color: 'var(--muted)', fontSize: 14 }}>
      {error}
    </div>
  )
  if (!report || data === null) return <div style={{ padding: 40, color: 'var(--muted)' }}>Loading…</div>

  // The server already omits non-normal pages for guest links; this filter is
  // defense-in-depth (never trust the client's data shape blindly) and keeps
  // this component correct on its own if the payload shape ever changes.
  // Hidden pages hold working notes by convention, and popup/tooltip/
  // drillthrough pages are reached by button/hover navigation this read-only
  // guest view does not wire up (no onNavigateToPage) -- so none of them
  // belong in the tab strip here.
  const pages = report.pages.filter(p => p.page_type === 'normal')
  if (pages.length === 0) return (
    <div style={{ padding: 40, color: 'var(--muted)' }}>This report has no page to show.</div>
  )
  const page = pages[Math.min(pageIdx, pages.length - 1)]
  const CELL = 62

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg, var(--surface2))', padding: '0 0 40px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 18px', flexWrap: 'wrap',
        borderBottom: '1px solid var(--border)', background: 'var(--surface)' }}>
        <strong style={{ fontSize: 14 }}>{report.name}</strong>
        {report.classification && (
          <span title="Sensitivity label" style={{
            fontSize: 11, fontWeight: 800, letterSpacing: '.06em', textTransform: 'uppercase',
            color: '#fff', padding: '2px 7px', borderRadius: 4,
            background: ({ Public: '#2e7d32', Internal: '#1565c0', Confidential: '#e65100', Restricted: '#c62828' } as Record<string, string>)[report.classification] ?? '#666' }}>
            {report.classification}
          </span>
        )}
        <span style={{ fontSize: 11, color: 'var(--muted)' }}>Shared view · read only</span>
        {report.pinned && (
          <span title="This link's pages and widget layout were frozen when it was created; the numbers still update live."
            style={{ fontSize: 11, fontWeight: 700, color: 'var(--muted)', border: '1px solid var(--border)',
              borderRadius: 4, padding: '2px 6px' }}>
            Layout pinned at share time
          </span>
        )}
        {pages.length > 1 && (
          <div style={{ marginInlineStart: 'auto', display: 'flex', gap: 4 }}>
            {pages.map((p, i) => (
              <button key={p.id} onClick={() => setPageIdx(i)}
                style={{ padding: '4px 10px', fontSize: 11, borderRadius: 6, border: '1px solid var(--border)',
                  cursor: 'pointer', background: i === pageIdx ? 'var(--accent)' : 'var(--surface)',
                  color: i === pageIdx ? 'var(--mc-accent-fg)' : 'var(--text)' }}>
                {p.name}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* `widgets` restores each widget's saved interaction: without it the
          provider falls back to `broadcasts ?? true`, and a widget the author
          deliberately isolated broadcast anyway the moment the link was
          shared. No `onPersistInteraction` -- a recipient changes nothing. */}
      <CrossFilterProvider widgets={page.widgets ?? []}
        pageMode={page.interaction_mode ?? 'manual'}>
        {/* The recipient's only view of what a click filtered, and their only
            way to undo it. They have no Actions pane. */}
        <div style={{ maxWidth: 1400, margin: '0 auto', padding: '0 6px' }}>
          <FilterBar keyboard />
        </div>
        {/* A reader of a shared link scrolls further than an author does, and
            has no other way back to the filters. */}
        <FloatingFilterWindow />
        <div data-testid="shared-page"
          onTouchStart={e => { touchX.current = e.touches[0]?.clientX ?? null }}
          onTouchEnd={e => {
            // Page per screen on a phone: a horizontal swipe turns the page.
            const start = touchX.current; touchX.current = null
            const end = e.changedTouches[0]?.clientX
            if (!narrow || start == null || end == null || Math.abs(end - start) < 60) return
            setPageIdx(i => Math.max(0, Math.min(pages.length - 1, i + (end < start ? 1 : -1))))
          }}
          style={narrow
            ? { display: 'flex', flexDirection: 'column', gap: 10, padding: '12px 10px 40px' }
            : { position: 'relative', maxWidth: 1400, margin: '20px auto',
                height: Math.max(400, ...(page.widgets ?? []).map(w => ((w.layout?.y ?? 0) + (w.layout?.h ?? 4)) * CELL + 40)) }}>
          {/* On a phone the dashboard is read top to bottom, in the author's
              reading order (row, then column), each widget full width. */}
          {(narrow ? [...(page.widgets ?? [])].sort((a, b) =>
              ((a.layout?.y ?? 0) - (b.layout?.y ?? 0)) || ((a.layout?.x ?? 0) - (b.layout?.x ?? 0)))
            : (page.widgets ?? [])).map(w => (
            <div key={w.id} style={narrow
              ? { height: Math.min(420, Math.max(220, (w.layout?.h ?? 4) * CELL)), padding: 0 }
              : { position: 'absolute',
              left: `${((w.layout?.x ?? 0) / 12) * 100}%`,
              top: (w.layout?.y ?? 0) * CELL,
              width: `${((w.layout?.w ?? 6) / 12) * 100}%`,
              height: (w.layout?.h ?? 4) * CELL, padding: 6 }}>
              {data[w.id] === RATE_LIMITED ? (
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center',
                  justifyContent: 'center', gap: 8, height: '100%', border: '1px dashed var(--border)',
                  borderRadius: 8, background: 'var(--surface)', color: 'var(--muted)', fontSize: 12,
                  textAlign: 'center', padding: 10 }}>
                  <span>Temporarily rate-limited — retrying may help</span>
                  <button onClick={() => retryWidget(w)}
                    style={{ padding: '3px 10px', fontSize: 11, borderRadius: 6, border: '1px solid var(--border)',
                      background: 'var(--surface2)', color: 'var(--text)', cursor: 'pointer' }}>
                    Try again
                  </button>
                </div>
              ) : (
                <WidgetRenderer widget={w} datasetId={report.dataset_id ?? 0}
                  columnFormats={report.column_formats as never}
                  geography={(report as { geography?: Record<string, number> }).geography}
                  relationships={(report as PublishedMappings).relationships}
                  datasets={(report as PublishedMappings).datasets as never}
                  dataOverride={data[w.id]} editMode={false} allowExport={false}
                  onSelect={() => {}} selected={false} />
              )}
            </div>
          ))}
        </div>
        {narrow && pages.length > 1 && (
          <div role="tablist" aria-label="Pages" style={{ position: 'fixed', bottom: 10, left: 0, right: 0,
            display: 'flex', justifyContent: 'center', gap: 6 }}>
            {pages.map((p, i) => (
              <button key={p.id} role="tab" aria-selected={i === pageIdx} aria-label={p.name} onClick={() => setPageIdx(i)}
                style={{ width: 9, height: 9, borderRadius: 9, padding: 0, border: 'none', cursor: 'pointer',
                  background: i === pageIdx ? 'var(--accent)' : 'var(--border)' }} />
            ))}
          </div>
        )}
      </CrossFilterProvider>
    </div>
  )
}
