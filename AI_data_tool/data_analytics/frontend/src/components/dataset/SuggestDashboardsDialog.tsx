import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Sparkles, X } from 'lucide-react'
import { useModalDialog } from '../ui/useModalDialog'
import {
  datasetsApi, reportsApi,
  type DashboardSuggestion, type DatasetProfile, type SuggestedWidget,
} from '../../services/api'

/**
 * "Suggest dashboards" for one dataset.
 *
 * The person describes their own job in their own words; the model reads a
 * profile of the data and proposes whole dashboards for that person. Everything
 * offered here has already been executed server-side, so a proposal is a thing
 * that draws, not a list of plausible chart titles.
 *
 * Two deliberate choices in this panel:
 *
 * It shows what the tool UNDERSTOOD before it shows what it suggests. A
 * suggestion you cannot check is one you cannot trust, and the profile is the
 * cheapest possible way to let someone see whether the tool read their data the
 * way they read it.
 *
 * It creates nothing until asked. The button says what it will do and where it
 * will land, and the page it builds is a draft meant to be edited.
 */
export interface SuggestDashboardsDialogProps {
  datasetId: number
  datasetName: string
  onClose: () => void
}

/** How much room a widget needs, by kind.
 *
 * Sized rather than slotted into a fixed grid. Ten hand-built dashboards in this
 * repository laid their top row out at h=2 — the height a single number wants —
 * and every chart and multi-value card in that row was clipped: axis labels
 * collided, and a three-figure card scrolled, showing its middle value and a
 * sliver of the one above. A generated page must not ship that.
 */
function sizeFor(widget: SuggestedWidget): { w: number; h: number } {
  const wt = widget.widget_type
  if (wt === 'kpi' || wt === 'gauge') return { w: 3, h: 2 }
  if (wt === 'card') {
    const measures = (widget.config?.measures as unknown[])?.length ?? 1
    return { w: 3, h: Math.max(3, 2 + measures) }
  }
  if (wt === 'table' || wt === 'crosstab' || wt === 'matrix' || wt === 'list')
    return { w: 12, h: 5 }
  if (wt === 'correlation_matrix' || wt === 'parallel_coordinates'
      || wt === 'sankey' || wt === 'network' || wt === 'org'
      || wt.startsWith('map_')) return { w: 12, h: 5 }
  return { w: 6, h: 4 }
}

/** Lay the widgets out left to right, wrapping at 12 columns. Small tiles
 *  naturally gather at the top because that is the order a proposal arrives in
 *  — headline numbers first — and nothing is ever placed shorter than it needs. */
function layout(widgets: SuggestedWidget[]) {
  const out: { x: number; y: number; w: number; h: number }[] = []
  let x = 0, y = 0, rowHeight = 0
  for (const widget of widgets) {
    const { w, h } = sizeFor(widget)
    if (x + w > 12) { x = 0; y += rowHeight; rowHeight = 0 }
    out.push({ x, y, w, h })
    x += w
    rowHeight = Math.max(rowHeight, h)
  }
  return out
}

const panel: React.CSSProperties = {
  position: 'fixed', inset: 0, background: 'rgba(0,0,0,.45)', zIndex: 60,
  display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16,
}
const sheet: React.CSSProperties = {
  background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12,
  width: 'min(860px, 100%)', maxHeight: '90vh', overflow: 'auto', padding: 20,
}
const card: React.CSSProperties = {
  border: '1px solid var(--border)', borderRadius: 10, padding: 14, marginTop: 12,
}
const muted: React.CSSProperties = { color: 'var(--muted)', fontSize: 12 }

/** The server's own explanation, preferred over axios's generic message.
 *
 *  A 400 from this endpoint always carries a `detail` saying WHY -- the dataset
 *  is DirectQuery, the model is not configured, the goal was too long. Printing
 *  "Request failed with status code 400" instead tells the person nothing they
 *  can act on, and sends them to the logs for a sentence the response already
 *  contained. */
function reasonFrom(e: unknown, fallback: string): string {
  const detail = (e as { response?: { data?: { detail?: unknown } } })
    ?.response?.data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  return (e as Error)?.message || fallback
}

export default function SuggestDashboardsDialog(
  { datasetId, datasetName, onClose }: SuggestDashboardsDialogProps,
) {
  const navigate = useNavigate()
  // Escape, the focus trap and focus restoration, from the shared hook every
  // overlay in this app uses. `overlayCoverage.test.ts` pins that: a modal a
  // keyboard user cannot leave is the failure it exists to prevent.
  const dialogRef = useModalDialog<HTMLDivElement>(onClose)
  const [goal, setGoal] = useState('')
  const [busy, setBusy] = useState(false)
  const [building, setBuilding] = useState<number | null>(null)
  const [error, setError] = useState('')
  const [reason, setReason] = useState('')
  /** One short question the designer asked back when it could not design
   *  anything. A reason is a dead end -- the person is left rereading their
   *  own sentence wondering which part of it was wrong -- and this is the
   *  agent's D4.3 "ask, do not guess" applied to the same problem here. */
  const [question, setQuestion] = useState('')
  const [proposals, setProposals] = useState<DashboardSuggestion[] | null>(null)
  const [profile, setProfile] = useState<DatasetProfile | null>(null)
  const [source, setSource] = useState<'insights' | 'model' | null>(null)
  const [seconds, setSeconds] = useState(0)
  const alive = useRef(true)
  // Cancel: this can take 20-30s, and the only way out used to be closing
  // the whole dialog and losing the description typed into it.
  const abortRef = useRef<AbortController | null>(null)

  // Set true on EVERY mount, not just the first. React StrictMode mounts,
  // unmounts and re-mounts every component in development; without the
  // re-arming line the flag stayed false after that simulated unmount, and the
  // answer arrived to a component that believed it was gone. The panel then
  // spun forever while the request behind it had finished in 28 seconds.
  useEffect(() => {
    alive.current = true
    return () => { alive.current = false }
  }, [])

  // A visible count, because this genuinely takes a while: it profiles the data,
  // asks a model, then runs every widget it proposed. A spinner with no number
  // reads as "stuck" after about fifteen seconds.
  useEffect(() => {
    if (!busy) return
    setSeconds(0)
    const t = setInterval(() => setSeconds(s => s + 1), 1000)
    return () => clearInterval(t)
  }, [busy])

  const ask = async () => {
    setBusy(true); setError(''); setReason(''); setProposals(null); setSource(null)
    setQuestion('')
    try {
      abortRef.current = new AbortController()
      const got = await datasetsApi.suggestDashboards(datasetId, { goal, count: 3 }, abortRef.current.signal)
      if (!alive.current) return
      setProposals(got.proposals)
      setProfile(got.profile)
      setSource(got.source ?? got.proposals?.[0]?.source ?? null)
      setReason(got.reason)
      setQuestion(got.question ?? '')
    } catch (e: any) {
      if (e?.code === 'ERR_CANCELED' || e?.name === 'CanceledError') return
      if (alive.current) setError(reasonFrom(e, 'the request failed'))
    } finally {
      abortRef.current = null
      if (alive.current) setBusy(false)
    }
  }

  /** Build one proposal with the same calls the person could make by hand. The
   *  server proposes and never creates; composing it here keeps that true. */
  const create = async (proposal: DashboardSuggestion, index: number) => {
    setBuilding(index); setError('')
    try {
      const report = await reportsApi.create({
        name: proposal.title,
        description: goal ? `Suggested for: ${goal}` : 'Suggested from the data',
        dataset_id: datasetId,
      } as never)
      const reportId = (report as { id: number }).id
      const pageId = (report as { pages?: { id: number }[] }).pages?.[0]?.id
      const slots = layout(proposal.widgets)
      // Sequential: widget order is id order everywhere else in this app, and
      // firing them together would leave the tiles in whatever order the server
      // happened to finish.
      const createdIds: number[] = []
      for (let i = 0; i < proposal.widgets.length; i++) {
        const widget = proposal.widgets[i]
        const made = await reportsApi.addWidget(
          reportId, pageId as number,
          { widget_type: widget.widget_type, title: widget.title,
            config: widget.config, layout: slots[i] } as never)
        createdIds.push((made as { id: number })?.id)
      }

      // SECOND PASS, and it has to be: a relation is stored as an action against
      // a real widget id, and those ids do not exist until every widget above
      // has been created. Writing the proposal's own indices here would point
      // each action at whatever widget happens to hold that id — a different
      // chart, quite possibly on someone else's dashboard.
      const bySource = new Map<number, { targetId: number; mode: 'filter' | 'highlight' }[]>()
      for (const rel of proposal.relations ?? []) {
        const from = createdIds[rel.from]
        const to = createdIds[rel.to]
        if (!from || !to) continue
        bySource.set(from, [...(bySource.get(from) ?? []), { targetId: to, mode: rel.mode }])
      }
      for (const [widgetId, actions] of bySource) {
        const index = createdIds.indexOf(widgetId)
        await reportsApi.updateWidget(reportId, pageId as number, widgetId, {
          config: {
            ...proposal.widgets[index].config,
            interaction: { broadcasts: true, receives: true, actions },
          },
        } as never)
      }
      navigate(`/reports/${reportId}`)
    } catch (e) {
      setError(reasonFrom(e, 'could not build that dashboard'))
    } finally {
      setBuilding(null)
    }
  }

  return (
    <div style={panel}>
      {/* The role goes on the PANEL, not the scrim: the backdrop is not the
          dialog, and marking it would put the whole page inside the dialog's
          boundary. */}
      <div ref={dialogRef} style={sheet} role="dialog" aria-modal="true"
           aria-label={`Suggest dashboards for ${datasetName}`}>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
          <div style={{ flex: 1 }}>
            <h2 style={{ margin: 0, fontSize: 18 }}>
              <Sparkles size={16} style={{ verticalAlign: -2, marginRight: 6 }} />
              Suggest dashboards
            </h2>
            <div style={{ ...muted, marginTop: 4 }}>
              for <strong>{datasetName}</strong>
            </div>
          </div>
          <button className="btn btn-ghost btn-sm" onClick={onClose} aria-label="Close">
            <X size={15} />
          </button>
        </div>

        <div style={{ marginTop: 16 }}>
          <label htmlFor="suggest-goal"
                 style={{ display: 'block', fontSize: 12, fontWeight: 600, marginBottom: 6 }}>
            What do you do, and what are you trying to find out?
          </label>
          <textarea
            id="suggest-goal" rows={3} value={goal} disabled={busy}
            onChange={e => setGoal(e.target.value)}
            placeholder="I am an instructor and I want to spot students falling behind early"
            style={{ width: '100%', resize: 'vertical' }} />
          <div style={{ ...muted, marginTop: 4 }}>
            Optional, but it is what makes the answer yours. Say it however you
            would say it to a colleague. <strong>Leave it blank</strong> and the
            charts are picked from your data&rsquo;s own statistics instead, with
            no AI involved.
          </div>
          <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
            <button className="btn btn-primary btn-sm" onClick={ask} disabled={busy}>
              {proposals ? 'Suggest again' : 'Suggest dashboards'}
            </button>
          </div>
        </div>

        {busy && (
          <div role="status" aria-live="polite" style={{ ...card, ...muted }}>
            Reading the data, choosing charts, and running every one of them to
            check it draws… {seconds}s
            {seconds > 25 && <div style={{ marginTop: 4 }}>
              Still going. Large datasets take longer, because each proposed
              widget is executed before it is offered.
            </div>}
            <div style={{ marginTop: 8 }}>
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => abortRef.current?.abort()}>Cancel</button>
            </div>
          </div>
        )}

        {error && <div style={{ ...card, color: 'var(--danger)' }}>{error}</div>}

        {profile && (
          <details style={card}>
            <summary style={{ cursor: 'pointer', fontWeight: 600, fontSize: 13 }}>
              What it understood about your data
            </summary>
            <div style={{ ...muted, marginTop: 8 }}>
              <span>{`${profile.row_count.toLocaleString()} rows`}</span>
              {profile.structure.date_range && <> Time column{' '}
                <code>{profile.structure.date_range.column}</code>, spanning{' '}
                {profile.structure.date_range.days} days, bucketed by{' '}
                {profile.structure.date_range.granularity}.</>}
            </div>
            <ul style={{ ...muted, marginTop: 8, paddingLeft: 18 }}>
              {profile.columns.map(c => (
                <li key={c.name}>
                  <code>{c.name}</code> — {c.role}
                  {c.distinct ? `, ${c.distinct.toLocaleString()} distinct` : ''}
                  {c.is_identifier && ' · identifier, never summed'}
                  {c.is_personal && ' · personal, never used as a dimension'}
                </li>
              ))}
            </ul>
          </details>
        )}

        {proposals?.length === 0 && !busy && (
          <div style={{ ...card, ...muted }}>
            No dashboard could be proposed{reason ? `: ${reason}` : '.'}
            {/* The refusal, then the way forward. Answering edits the goal in
                place and asks again, so the person never retypes what they
                already said. */}
            {question && (
              <div style={{ marginTop: 10, color: 'var(--text)' }}>
                {question}
                <button onClick={() => { setProposals(null); setQuestion('') }}
                  style={{ display: 'block', marginTop: 6, fontSize: 12,
                    padding: '4px 10px', borderRadius: 6,
                    border: '1px solid var(--border)', background: 'var(--surface)',
                    color: 'var(--text)', cursor: 'pointer' }}>
                  Answer this
                </button>
              </div>
            )}
          </div>
        )}

        {source && (proposals?.length ?? 0) > 0 && (
          <div style={{ ...card, ...muted }}>
            {source === 'insights'
              ? 'Chosen from what stands out in your data — no AI was used, and '
                + 'the same data will always give the same charts.'
              : 'Chosen for what you described, by the AI model.'}
          </div>
        )}

        {proposals?.map((proposal, i) => (
          <div key={i} style={card}>
            <div style={{ fontWeight: 700 }}>{proposal.title}</div>
            <div style={{ ...muted, marginTop: 2 }}>{proposal.rationale}</div>
            <ul style={{ marginTop: 10, paddingLeft: 18, fontSize: 13 }}>
              {proposal.widgets.map((w, j) => (
                <li key={j} style={{ marginBottom: 4 }}>
                  <strong>{w.title}</strong>{' '}
                  <span style={muted}>{w.widget_type}</span>{' · '}
                  <span style={muted}>{w.row_count === 1
                    ? '1 row' : `${w.row_count.toLocaleString()} rows`}</span>
                  {w.why && <div style={muted}>{w.why}</div>}
                </li>
              ))}
            </ul>
            {(proposal.relations?.length ?? 0) > 0 && (
              <div style={{ ...muted, marginTop: 8 }}>
                <strong style={{ color: 'var(--fg)' }}>How these connect</strong>
                <ul style={{ margin: '4px 0 0', paddingLeft: 18 }}>
                  {/* One direction per pair: the reverse edge is wired too, but
                      saying it twice reads as two different facts. */}
                  {(proposal.relations ?? [])
                    .filter(r => r.from < r.to)
                    .map((r, k) => <li key={k}>{r.note}</li>)}
                </ul>
              </div>
            )}
            <button className="btn btn-primary btn-sm" disabled={building !== null}
                    onClick={() => create(proposal, i)}>
              {building === i ? 'Building…' : 'Create this dashboard'}
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}
