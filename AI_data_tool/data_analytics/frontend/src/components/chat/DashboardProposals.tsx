import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { dataSourcesApi, reportsApi } from '../../services/api'

/** One dashboard the agent proposed: the query that builds its data, and the
 *  tiles to put over it. Mirrors `services/suggest_dashboard.SUGGESTION_SCHEMA`. */
export interface DashboardProposal {
  title: string
  sql: string
  widgets: {
    widget_type: string
    title: string
    dimension: string
    measure: string
    aggregation: string
    /** Set by the attribute-review pass: why it chose this chart's settings.
     *  Shown to the reader, because a setting whose reason you cannot see is one
     *  you cannot disagree with — and this is a draft meant to be edited. */
    note?: string
    limit?: number
    sort?: string
    sort_by?: string
    dimension_granularity?: string
    running?: string
  }[]
}

export interface DashboardProposalsPresentation {
  kind: 'dashboard_proposals'
  source_id: number
  for_role: string
  proposals: DashboardProposal[]
}

/** Where each tile lands. Fixed rather than computed: a first draft the person is
 *  about to edit does not need a packing algorithm, and a predictable shape —
 *  headline numbers across the top, breakdowns beneath — is easier to rearrange
 *  than a clever one. Anything past the seventh falls into a column below. */
const SLOTS = [
  { x: 0, y: 0, w: 3, h: 2 }, { x: 3, y: 0, w: 3, h: 2 }, { x: 6, y: 0, w: 6, h: 2 },
  { x: 0, y: 2, w: 6, h: 4 }, { x: 6, y: 2, w: 6, h: 4 },
  { x: 0, y: 6, w: 6, h: 5 }, { x: 6, y: 6, w: 6, h: 5 },
]

const card: React.CSSProperties = {
  border: '1px solid var(--border)', borderRadius: 8, padding: 12,
  background: 'var(--surface)', marginTop: 8,
}
const linkish: React.CSSProperties = {
  background: 'none', border: 'none', padding: 0, cursor: 'pointer',
  color: 'var(--muted)', fontSize: 11, textDecoration: 'underline',
}

export default function DashboardProposals(
  { presentation }: { presentation: DashboardProposalsPresentation },
) {
  const navigate = useNavigate()
  const [busy, setBusy] = useState<number | null>(null)
  const [failed, setFailed] = useState<Record<number, string>>({})
  const [openSql, setOpenSql] = useState<Record<number, boolean>>({})

  // The chat renders whatever `presentation` holds; every other kind belongs to
  // somebody else's component.
  if (presentation?.kind !== 'dashboard_proposals') return null

  /** Build one proposal for real, with the three calls the person already has
   *  permission to make. Deliberately client-side: the backend's contract is
   *  that it proposes and never creates, and composing existing endpoints here
   *  keeps that true. */
  const create = async (proposal: DashboardProposal, index: number) => {
    setBusy(index)
    setFailed(prev => ({ ...prev, [index]: '' }))
    try {
      const dataset = await dataSourcesApi.import(
        presentation.source_id, proposal.title, undefined, proposal.sql, 'import')
      const report = await reportsApi.create({
        name: proposal.title,
        description: `Proposed by the AI for a ${presentation.for_role}.`,
        dataset_id: dataset.id,
      })
      const pageId = report.pages?.[0]?.id
      // Sequential, not Promise.all: widget order is the id order everywhere else
      // in this app (page templates serialise by it), and firing them together
      // would leave the tiles in whatever order the server happened to finish.
      for (let i = 0; i < proposal.widgets.length; i++) {
        const w = proposal.widgets[i]
        const config: Record<string, unknown> = {
          measure: w.measure, aggregation: w.aggregation,
        }
        if (w.dimension) config.dimension = w.dimension
        // The attributes the review pass chose. Without these the built chart is
        // the unreadable version the review existed to fix.
        if (w.limit) config.limit = w.limit
        if (w.sort) config.sort = w.sort
        if (w.sort_by) config.sort_by = w.sort_by
        if (w.dimension_granularity) config.dimension_granularity = w.dimension_granularity
        if (w.running) config.running = w.running
        // The reason the review pass gave for those settings, kept with the
        // widget. Without it the built dashboard carries a `limit: 15` nobody
        // can account for, on a chart nobody chose it for -- and the sentence
        // the person read before pressing Create is gone.
        if (w.note) config.note = w.note
        await reportsApi.addWidget(report.id, pageId as number, {
          widget_type: w.widget_type, title: w.title, config,
          layout: SLOTS[i] ?? { x: 0, y: 11 + i * 4, w: 6, h: 4 },
        } as never)
      }
      navigate(`/reports/${report.id}`)
    } catch (e) {
      // Named, not swallowed: the query ran once against the database when it was
      // proposed, so a failure here is worth reading rather than retrying.
      setFailed(prev => ({
        ...prev,
        [index]: (e as Error)?.message || 'something went wrong',
      }))
    } finally {
      setBusy(null)
    }
  }

  return (
    <div style={{ marginTop: 8 }}>
      {presentation.proposals.map((p, i) => (
        <div key={i} style={card}>
          <div style={{ fontWeight: 700, fontSize: 14 }}>{p.title}</div>
          <ul style={{ margin: '6px 0 10px', padding: 0, listStyle: 'none' }}>
            {p.widgets.map((w, wi) => (
              <li key={wi} style={{ fontSize: 12, color: 'var(--muted)', padding: '2px 0' }}>
                <span style={{ color: 'var(--text)' }}>{w.title}</span>
                {w.note && <span style={{ fontStyle: 'italic' }}> — {w.note}</span>}
              </li>
            ))}
          </ul>

          <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
            <button
              onClick={() => void create(p, i)}
              disabled={busy !== null}
              style={{
                padding: '6px 12px', borderRadius: 6, border: 'none', fontSize: 12,
                cursor: busy === null ? 'pointer' : 'default',
                background: 'var(--accent)', color: 'var(--mc-accent-fg)',
              }}>
              {busy === i ? 'Building…' : 'Create dashboard'}
            </button>
            <button style={linkish}
                    onClick={() => setOpenSql(s => ({ ...s, [i]: !s[i] }))}>
              {openSql[i] ? 'Hide SQL' : 'Show SQL'}
            </button>
            <span style={{ fontSize: 11, color: 'var(--muted)' }}>
              {p.widgets.length} widget{p.widgets.length === 1 ? '' : 's'}
            </span>
          </div>

          {openSql[i] && (
            <pre style={{
              marginTop: 8, padding: 8, fontSize: 11, overflowX: 'auto',
              background: 'var(--surface2)', borderRadius: 6,
            }}>{p.sql}</pre>
          )}

          {failed[i] && (
            <div style={{ marginTop: 8, fontSize: 12, color: 'var(--danger, #b4232a)' }}>
              Could not build this dashboard: {failed[i]}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}
