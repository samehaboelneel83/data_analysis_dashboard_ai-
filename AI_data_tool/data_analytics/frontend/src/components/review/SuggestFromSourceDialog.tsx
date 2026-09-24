import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useModalDialog } from '../ui/useModalDialog'
import {
  dataSourcesApi, reportsApi,
  type SimilarDataset, type SourceDashboardSuggestion,
} from '../../services/api'

/**
 * "I have connected a database and I do not know what to do with it."
 *
 * This is the step BEFORE a dataset exists. `/reports/{id}/suggest-widgets`
 * needs a dataset already; `/datasets/{id}/suggest-dashboards` needs one too.
 * `POST /data-sources/{id}/suggest-dashboard` answers from the CATALOG -- it
 * picks the tables, writes one query, proves the query runs against the real
 * database, and returns the tiles to put over it.
 *
 * That endpoint shipped complete and probe-validated, and nothing in the product
 * ever called it. This is its caller.
 *
 * NOTHING IS CREATED BY THE BACKEND. The contract is that it proposes; the
 * accept below composes three calls the person already has permission to make,
 * exactly as the chat's `DashboardProposals` does. Keeping creation on this side
 * is what keeps that contract true.
 */
export interface SuggestFromSourceDialogProps {
  sourceId: number
  sourceName: string
  /** Whether a catalog exists. The endpoint refuses without one, and saying so
   *  before the request is kinder than a 400 after a long wait. */
  synced: boolean
  onClose: () => void
}

const Z_OVERLAY = 1000

export default function SuggestFromSourceDialog(
  { sourceId, sourceName, synced, onClose }: SuggestFromSourceDialogProps,
) {
  const navigate = useNavigate()
  // The shared hook, not a hand-rolled key listener: it supplies Escape, the
  // focus trap and focus restoration together, and `overlayCoverage.test.ts`
  // structurally refuses any viewport overlay that does not use it. That pin
  // exists because the first pass at modal accessibility found its targets by
  // grepping for role="dialog" and so could not see the six modals that had no
  // role at all.
  const dialogRef = useModalDialog<HTMLDivElement>(onClose)
  const [role, setRole] = useState('')
  const [goal, setGoal] = useState('')
  const [busy, setBusy] = useState(false)
  const [reason, setReason] = useState('')
  const [suggestion, setSuggestion] = useState<SourceDashboardSuggestion | null>(null)
  const [similar, setSimilar] = useState<SimilarDataset[]>([])
  const [building, setBuilding] = useState(false)

  const ask = async () => {
    const who = role.trim()
    if (!who) { setReason('Say who the dashboard is for.'); return }
    setBusy(true)
    setReason('')
    setSuggestion(null)
    setSimilar([])
    try {
      const got = await dataSourcesApi.suggestDashboard(sourceId, {
        for_role: who, goal: goal.trim() || undefined,
      })
      if (!got.ok || !got.suggestion) {
        // 200 with a reason, not an error: "the model is off" and "nothing
        // safe could be proposed" are both normal answers to a request for a
        // suggestion, and the reason is more useful than a toast.
        setReason(got.reason || 'No dashboard could be designed from this data.')
        return
      }
      setSuggestion(got.suggestion)

      // Before offering to build: is there already a dataset that covers this?
      // Advisory only -- it is shown beside the Create button, never in place of
      // it. Failing this lookup must not cost the person their proposal.
      try {
        const cols = Array.from(new Set(got.suggestion.widgets.flatMap(
          w => [w.dimension, w.measure].filter(Boolean))))
        const { matches } = await dataSourcesApi.similarDatasets(sourceId, {
          columns: cols, query: got.suggestion.sql,
        })
        setSimilar(matches)
      } catch { /* the proposal stands on its own */ }
    } catch (e: any) {
      setReason(e?.response?.data?.detail ?? 'The suggestion could not be made.')
    } finally { setBusy(false) }
  }

  /** Build it for real: import the query as a dataset, create the report, add
   *  the tiles. The same three calls the chat's proposal card makes. */
  const create = async () => {
    if (!suggestion) return
    setBuilding(true)
    setReason('')
    try {
      const dataset = await dataSourcesApi.import(
        sourceId, suggestion.title, undefined, suggestion.sql, 'import')
      const report = await reportsApi.create({
        name: suggestion.title,
        description: `Proposed for ${role.trim()} from ${sourceName}.`,
        dataset_id: dataset.id,
      })
      const pageId = report.pages?.[0]?.id
      // Sequential, not Promise.all: widget order is id order everywhere else in
      // this app, and firing them together leaves the tiles in whatever order
      // the server happened to finish.
      const slots = [
        { x: 0, y: 0, w: 3, h: 2 }, { x: 3, y: 0, w: 3, h: 2 }, { x: 6, y: 0, w: 6, h: 2 },
        { x: 0, y: 2, w: 6, h: 4 }, { x: 6, y: 2, w: 6, h: 4 },
        { x: 0, y: 6, w: 6, h: 5 }, { x: 6, y: 6, w: 6, h: 5 },
      ]
      for (let i = 0; i < suggestion.widgets.length; i++) {
        const w = suggestion.widgets[i]
        const config: Record<string, unknown> = { measure: w.measure, aggregation: w.aggregation }
        if (w.dimension) config.dimension = w.dimension
        if (w.limit) config.limit = w.limit
        if (w.sort) config.sort = w.sort
        if (w.sort_by) config.sort_by = w.sort_by
        if (w.dimension_granularity) config.dimension_granularity = w.dimension_granularity
        if (w.running) config.running = w.running
        // The reason the review pass gave for those settings, kept with the
        // widget -- without it the built dashboard carries a `limit: 15` nobody
        // can account for.
        if (w.note) config.note = w.note
        await reportsApi.addWidget(report.id, pageId as number, {
          widget_type: w.widget_type, title: w.title, config,
          layout: slots[i] ?? { x: 0, y: 11 + i * 4, w: 6, h: 4 },
        } as never)
      }
      navigate(`/reports/${report.id}`)
    } catch (e: any) {
      // Named, not swallowed: the query already ran against the database when it
      // was proposed, so a failure here is worth reading rather than retrying.
      setReason(e?.response?.data?.detail ?? (e as Error)?.message
                ?? 'The dashboard could not be built.')
    } finally { setBuilding(false) }
  }

  const label: React.CSSProperties = { fontSize: 11, color: 'var(--muted)', display: 'block' }
  const input: React.CSSProperties = {
    width: '100%', fontSize: 12, padding: '6px 8px', boxSizing: 'border-box',
    background: 'var(--surface2)', border: '1px solid var(--border)',
    borderRadius: 4, color: 'var(--text)', marginTop: 3,
  }

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.5)', display: 'flex',
      alignItems: 'center', justifyContent: 'center', zIndex: Z_OVERLAY }}>
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-label="Suggest a dashboard"
        style={{ background: 'var(--surface)', border: '1px solid var(--border)',
          borderRadius: 12, padding: 24, width: 560, maxWidth: '92vw',
          maxHeight: '88vh', overflowY: 'auto' }}>

        <h2 style={{ fontSize: 16, fontWeight: 700, margin: '0 0 4px' }}>
          Suggest a dashboard
        </h2>
        <p style={{ fontSize: 12, color: 'var(--muted)', margin: '0 0 16px' }}>
          From {sourceName}&rsquo;s catalogue — no dataset needed. It picks the
          tables, writes the query, and runs it before offering anything.
        </p>

        {!synced && (
          <p style={{ fontSize: 12, color: 'var(--muted)', border: '1px solid var(--border)',
            borderRadius: 6, padding: 10, marginBottom: 12 }}>
            This connection has not been read yet. Run a sync first — there is no
            catalogue to design from until it finishes.
          </p>
        )}

        <label style={label}>
          Who is it for?
          <input style={input} value={role} autoFocus disabled={busy || building}
            placeholder="a ward sister, the head of sales, me"
            onChange={e => setRole(e.target.value)} />
        </label>
        <label style={{ ...label, marginTop: 10 }}>
          What do they need to know? (optional)
          <input style={input} value={goal} disabled={busy || building}
            placeholder="where the queue builds up on night shifts"
            onChange={e => setGoal(e.target.value)} />
        </label>

        {reason && (
          <p style={{ fontSize: 12, color: 'var(--muted)', marginTop: 12 }}>{reason}</p>
        )}

        {suggestion && (
          <div style={{ border: '1px solid var(--border)', borderRadius: 8, padding: 12,
            marginTop: 14 }}>
            <div style={{ fontWeight: 700, fontSize: 14 }}>{suggestion.title}</div>
            {/* The engine, named (Part IV criterion 10): the design is the AI
                model's; the query below is the evidence it rests on. */}
            <div data-testid="suggestion-source" style={{ fontSize: 10.5, color: 'var(--muted)', marginTop: 2 }}>
              ⓘ Designed by the AI model from this source's synced tables; the query below is exactly what it will run
            </div>
            <ul style={{ margin: '6px 0 0', padding: 0, listStyle: 'none' }}>
              {suggestion.widgets.map((w, i) => (
                <li key={i} style={{ fontSize: 12, color: 'var(--muted)', padding: '2px 0' }}>
                  <span style={{ color: 'var(--text)' }}>{w.title}</span>
                  {w.note && <span style={{ fontStyle: 'italic' }}> — {w.note}</span>}
                </li>
              ))}
            </ul>
            <details style={{ marginTop: 8 }}>
              <summary style={{ fontSize: 11, color: 'var(--muted)', cursor: 'pointer' }}>
                The query this runs
              </summary>
              <pre style={{ fontSize: 11, whiteSpace: 'pre-wrap', margin: '6px 0 0' }}>
                {suggestion.sql}
              </pre>
            </details>
          </div>
        )}

        {suggestion && similar.length > 0 && (
          <div style={{ border: '1px solid var(--border)', borderRadius: 8, padding: 12,
            marginTop: 10 }}>
            <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 4 }}>
              You may already have this
            </div>
            <p style={{ fontSize: 11, color: 'var(--muted)', margin: '0 0 6px' }}>
              Building anyway is fine — this is here so you are not left with two
              datasets that mean the same thing without knowing it.
            </p>
            <ul style={{ margin: 0, padding: 0, listStyle: 'none' }}>
              {similar.map(m => (
                <li key={m.dataset_id} style={{ fontSize: 12, padding: '3px 0' }}>
                  <button onClick={() => navigate(`/datasets/${m.dataset_id}`)}
                    style={{ background: 'none', border: 'none', padding: 0,
                      cursor: 'pointer', color: 'var(--accent, #2563eb)',
                      textDecoration: 'underline' }}>
                    {m.name}
                  </button>
                  <span style={{ color: 'var(--muted)' }}>
                    {' '}— covers {Math.round(m.coverage * 100)}% of these columns
                    {m.by_name && ' (matched by column name only)'}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}

        <div style={{ display: 'flex', gap: 8, marginTop: 18 }}>
          {!suggestion ? (
            <button onClick={() => void ask()} disabled={busy || !synced} title={!synced ? 'Sync the source first, so the design is based on its real tables' : undefined}
              style={{ fontSize: 12, padding: '6px 14px', borderRadius: 6, border: 'none',
                background: 'var(--accent, #2563eb)', color: 'var(--mc-accent-fg)',
                cursor: busy || !synced ? 'default' : 'pointer', opacity: busy || !synced ? .6 : 1 }}>
              {busy ? 'Designing…' : 'Suggest'}
            </button>
          ) : (
            <button onClick={() => void create()} disabled={building}
              style={{ fontSize: 12, padding: '6px 14px', borderRadius: 6, border: 'none',
                background: 'var(--accent, #2563eb)', color: 'var(--mc-accent-fg)',
                cursor: building ? 'default' : 'pointer', opacity: building ? .6 : 1 }}>
              {building ? 'Building…' : 'Create it'}
            </button>
          )}
          <button onClick={onClose} disabled={busy || building}
            style={{ fontSize: 12, padding: '6px 14px', borderRadius: 6,
              border: '1px solid var(--border)', background: 'var(--surface)',
              color: 'var(--text)', cursor: 'pointer' }}>
            {suggestion ? 'Not this one' : 'Cancel'}
          </button>
        </div>
      </div>
    </div>
  )
}
