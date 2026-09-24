import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { embedApi } from '../services/api'
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

// Same sentinel SharedReport uses -- distinguishes "the server throttled this
// widget's request" from "the widget's own query genuinely returned nothing".
const RATE_LIMITED = Symbol('rate-limited')

/**
 * The embed view behind a host-signed JWT (Task E1): minimal chrome, no
 * login, no cross-filters -- mirrors SharedReport almost exactly, except the
 * credential is a `token` QUERY PARAM (the host application's own JWT, signed
 * with an embed config's secret) rather than a path segment, and every
 * widget's data is fetched with the short-lived `embed_session_token` the
 * report call returns -- never with the original host token, and never with
 * anything this page itself invents. Scope (which rows render) is entirely
 * the host's doing, server-side; this page has no say in it.
 */
export default function EmbeddedReport() {
  const [params] = useSearchParams()
  const token = params.get('token') ?? ''
  const [report, setReport] = useState<(Report & { column_formats?: Record<string, unknown> }) | null>(null)
  const [sessionToken, setSessionToken] = useState('')
  const [data, setData] = useState<Record<number, unknown> | null>(null)
  const [pageIdx, setPageIdx] = useState(0)
  const [error, setError] = useState('')

  function fetchWidget(sTok: string, w: Widget) {
    return embedApi.widgetData(sTok, w.id).catch(e => (
      e?.response?.status === 429 ? RATE_LIMITED : null
    ))
  }

  useEffect(() => {
    if (!token) { setError('This embed link is missing its token.'); return }
    embedApi.report(token).then(async r => {
      const sTok = r.embed_session_token as string
      const widgets: Widget[] = r.pages.flatMap((p: ReportPage) => p.widgets ?? [])
      const STATIC = new Set(['text', 'button', 'image', 'shape', 'container', 'web_content'])
      const results = await Promise.all(widgets.map(w =>
        STATIC.has(w.widget_type) ? Promise.resolve(null) : fetchWidget(sTok, w)))
      setReport(r)
      setSessionToken(sTok)
      setData(Object.fromEntries(widgets.map((w, i) => [w.id, results[i]])))
    }).catch(() => setError('This embed link is invalid, expired, or not allowed from this origin.'))
  }, [token])

  function retryWidget(w: Widget) {
    if (!sessionToken) return
    fetchWidget(sessionToken, w).then(result => setData(d => ({ ...(d ?? {}), [w.id]: result })))
  }

  if (error) return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', color: 'var(--muted)', fontSize: 14 }}>
      {error}
    </div>
  )
  if (!report || data === null) return <div style={{ padding: 40, color: 'var(--muted)' }}>Loading…</div>

  const pages = report.pages.filter(p => p.page_type === 'normal')
  if (pages.length === 0) return (
    <div style={{ padding: 40, color: 'var(--muted)' }}>This report has no page to show.</div>
  )
  const page = pages[Math.min(pageIdx, pages.length - 1)]
  const CELL = 62

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg, var(--surface2))', padding: '0 0 40px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 18px',
        borderBottom: '1px solid var(--border)', background: 'var(--surface)' }}>
        <strong style={{ fontSize: 14 }}>{report.name}</strong>
        <span style={{ fontSize: 11, color: 'var(--muted)' }}>Embedded view · read only</span>
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

      {/* `widgets` is what restores each widget's saved interaction. Without it
          the provider falls back to `broadcasts ?? true`, so a widget the
          author deliberately isolated broadcast anyway the moment the report
          left the builder -- the setting simply did not survive publication.
          No `onPersistInteraction`: nothing a viewer does is written down. */}
      <CrossFilterProvider widgets={page.widgets ?? []}
        pageMode={page.interaction_mode ?? 'manual'}>
        {/* A stranger with a link has no Actions pane to fall back on: this
            strip is their only way to see what a click filtered, and their
            only way to undo it. */}
        <div style={{ maxWidth: 1400, margin: '0 auto', padding: '0 6px' }}>
          <FilterBar keyboard />
        </div>
        {/* A reader of a shared link scrolls further than an author does, and
            has no other way back to the filters. */}
        <FloatingFilterWindow />
        <div style={{ position: 'relative', maxWidth: 1400, margin: '20px auto',
          height: Math.max(400, ...(page.widgets ?? []).map(w => ((w.layout?.y ?? 0) + (w.layout?.h ?? 4)) * CELL + 40)) }}>
          {(page.widgets ?? []).map(w => (
            <div key={w.id} style={{ position: 'absolute',
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
      </CrossFilterProvider>
    </div>
  )
}
