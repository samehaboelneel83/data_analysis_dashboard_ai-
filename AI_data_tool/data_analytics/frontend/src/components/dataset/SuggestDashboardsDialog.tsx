import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Sparkles, X } from 'lucide-react'
import { useModalDialog } from '../ui/useModalDialog'
import { useT } from '../../i18n'
import { takeawayText } from '../../lib/readbackText'
import {
  calcColumnsApi, datasetsApi, jobsApi, measuresApi, reportsApi,
  type CalcColumn, type MeasureDef, type DashboardSuggestion, type PanelRefusal, type SuggestDashboardsAnswer, type DatasetProfile, type PanelStats, type SuggestedWidget,
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
  // A filter control: the server puts these first, in one band.
  if (wt === 'slicer') return { w: 4, h: 3 }
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

/** Where an analyst-panel job for a dataset is remembered, so closing the
 *  dialog does not lose it: reopening finds the job and picks up its progress
 *  or its result. Per browser, best-effort -- the job itself is on the server. */
const jobKey = (datasetId: number) => `dl.suggestPanelJob.${datasetId}`
/** The job id, with what was asked, so a reopened dialog shows the question
 *  that is being answered. An older bare id still reads. */
type Remembered = { id: number; goal?: string; size?: number; at?: number }
function rememberedRun(datasetId: number): Remembered | null {
  try {
    const raw = localStorage.getItem(jobKey(datasetId))
    if (!raw) return null
    const v = raw.startsWith('{') ? JSON.parse(raw) as Remembered : { id: Number(raw) }
    return v.id > 0 ? v : null
  } catch { return null }
}
function rememberedJob(datasetId: number): number | null {
  return rememberedRun(datasetId)?.id ?? null
}
function rememberJob(datasetId: number, jobId: number | null, asked?: { goal: string; size: number }) {
  try {
    if (jobId) localStorage.setItem(jobKey(datasetId), JSON.stringify({ id: jobId, ...asked, at: Date.now() }))
    else localStorage.removeItem(jobKey(datasetId))
  } catch { /* storage unavailable: the dialog just will not resume */ }
}
const POLL_MS = 3000
const LEFT_OUT = ['units', 'meaning', 'repeat', 'promise', 'identifier', 'axis', 'empty', 'error', 'invalid'] as const
const isLeftOut = (c?: string): c is typeof LEFT_OUT[number] => !!c && (LEFT_OUT as readonly string[]).includes(c)
/** The panel's sections, named in the reader's language. The server's English
 *  title is the fallback for anything else (the quick designer's own titles). */
const SECTIONS = ['summary', 'composition', 'measures', 'equity', 'time', 'exceptions', 'relationships', 'detail', 'drill'] as const
type SectionKey = typeof SECTIONS[number]
const isSection = (s?: string): s is SectionKey => !!s && (SECTIONS as readonly string[]).includes(s)
const STAGES = ['queued', 'reading', 'facts', 'proposing', 'drawing', 'selecting'] as const

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
  const tr = useT()
  const navigate = useNavigate()
  // Escape, the focus trap and focus restoration, from the shared hook every
  // overlay in this app uses. `overlayCoverage.test.ts` pins that: a modal a
  // keyboard user cannot leave is the failure it exists to prevent.
  const dialogRef = useModalDialog<HTMLDivElement>(onClose)
  const [goal, setGoal] = useState(() => rememberedRun(datasetId)?.goal ?? '')
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
  const [source, setSource] = useState<'insights' | 'model' | 'panel' | null>(null)
  /** Quick: one designer call, three ideas. Panel: several analyst lenses,
   *  every idea drawn, the `size` best kept by what the data shows. */
  const [mode, setMode] = useState<'quick' | 'panel'>('quick')
  const [size, setSize] = useState(() => rememberedRun(datasetId)?.size ?? 24)
  const [stats, setStats] = useState<PanelStats | null>(null)
  const [facts, setFacts] = useState<string[]>([])
  const [derived, setDerived] = useState<{ measures: MeasureDef[]; calculated_columns: CalcColumn[] }>(
    { measures: [], calculated_columns: [] })
  /** Ideas the panel left out, so a reader can see what was considered. */
  const [refused, setRefused] = useState<PanelRefusal[]>([])
  /** The background panel job being watched, and the stage it reported. */
  const [jobId, setJobId] = useState<number | null>(() => rememberedJob(datasetId))
  const [stage, setStage] = useState<{ stage?: string; ideas?: number } | null>(null)
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
    // A resumed panel counts from when it was asked, not from reopening.
    const since = rememberedRun(datasetId)?.at
    const start = since ?? Date.now()
    setSeconds(Math.max(0, Math.round((Date.now() - start) / 1000)))
    const t = setInterval(() => setSeconds(Math.max(0, Math.round((Date.now() - start) / 1000))), 1000)
    return () => clearInterval(t)
  }, [busy, datasetId])

  const titleOf = (p: DashboardSuggestion) => isSection(p.section) ? tr(`sug.section.${p.section}`) : p.title
  const whyOf = (p: DashboardSuggestion) => isSection(p.section) ? tr(`sug.sectionWhy.${p.section}`) : p.rationale

  const show = (got: SuggestDashboardsAnswer) => {
    setProposals(got.proposals ?? [])
    setProfile(got.profile ?? null)
    setSource(got.source ?? got.proposals?.[0]?.source ?? null)
    setReason(got.reason ?? '')
    setQuestion(got.question ?? '')
    setStats(got.panel ?? null)
    setFacts(got.facts ?? [])
    setRefused(got.refused ?? [])
    setDerived({ measures: got.derived?.measures ?? [], calculated_columns: got.derived?.calculated_columns ?? [] })
  }

  // Watch the panel job: on open when one is remembered for this dataset, and
  // after asking. The dialog can be closed meanwhile; the job keeps running.
  useEffect(() => {
    if (!jobId) return
    setMode('panel'); setBusy(true)
    let stopped = false
    const tick = async () => {
      try {
        const job = await jobsApi.get(jobId)
        if (stopped || !alive.current) return
        setStage(job.progress as never)
        if (job.state === 'succeeded') {
          show(job.result as unknown as SuggestDashboardsAnswer)
        } else if (job.state === 'failed') {
          setError(job.error || tr('sug.jobFailed'))
        } else if (job.state !== 'cancelled') {
          return
        }
        rememberJob(datasetId, null); setJobId(null); setBusy(false)
      } catch (e) {
        if (stopped || !alive.current) return
        // A job that is gone (deleted, another account) is forgotten, not retried forever.
        rememberJob(datasetId, null); setJobId(null); setBusy(false)
        setError(reasonFrom(e, tr('sug.jobFailed')))
      }
    }
    void tick()
    const t = setInterval(() => void tick(), POLL_MS)
    return () => { stopped = true; clearInterval(t) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId, datasetId])

  const ask = async () => {
    setBusy(true); setError(''); setReason(''); setProposals(null); setSource(null)
    setQuestion(''); setStats(null); setFacts([]); setStage(null)
    try {
      abortRef.current = new AbortController()
      const body = mode === 'panel' ? { goal, mode, size, background: true } : { goal, count: 3 }
      const got = await datasetsApi.suggestDashboards(datasetId, body, abortRef.current.signal)
      if (!alive.current) return
      if (got.job_id) {
        rememberJob(datasetId, got.job_id, { goal, size })
        setJobId(got.job_id)
        return
      }
      show(got)
    } catch (e: any) {
      if (e?.code === 'ERR_CANCELED' || e?.name === 'CanceledError') return
      if (alive.current) setError(reasonFrom(e, 'the request failed'))
    } finally {
      abortRef.current = null
      if (alive.current && !rememberedJob(datasetId)) setBusy(false)
    }
  }

  const stopWatching = async () => {
    if (jobId) {
      try { await jobsApi.cancel(jobId) } catch { /* already finished */ }
      rememberJob(datasetId, null); setJobId(null); setBusy(false)
    } else abortRef.current?.abort()
  }

  /** The fields the proposals draw that the dataset lacks (a rate of totals,
   *  a duration) are created first, with the same calls the field editor
   *  makes. Returns the names that could NOT be created -- the person may
   *  not edit this dataset -- so the widgets that need them are left out
   *  rather than shown broken. */
  const createDerived = async (): Promise<Set<string>> => {
    const failed = new Set<string>()
    for (const col of derived.calculated_columns) {
      try { await calcColumnsApi.save(datasetId, col) } catch { failed.add(col.name) }
    }
    for (const m of derived.measures) {
      try { await measuresApi.save(datasetId, m) } catch { failed.add(m.name) }
    }
    return failed
  }
  const withoutFields = (p: DashboardSuggestion, missing: Set<string>): DashboardSuggestion => {
    if (missing.size === 0) return p
    const names = (w: SuggestedWidget) => JSON.stringify(w.config ?? {})
    const keep = p.widgets.filter(w => ![...missing].some(n => names(w).includes(`"${n}"`)))
    // Relations index the widgets: drop any that pointed at a removed one.
    const index = new Map(p.widgets.map((w, i) => [i, keep.indexOf(w)]))
    const relations = (p.relations ?? [])
      .map(r => ({ ...r, from: index.get(r.from) ?? -1, to: index.get(r.to) ?? -1 }))
      .filter(r => r.from >= 0 && r.to >= 0)
    return { ...p, widgets: keep, relations }
  }

  /** Build one proposal with the same calls the person could make by hand. The
   *  server proposes and never creates; composing it here keeps that true. */
  const fillPage = async (reportId: number, pageId: number, proposal: DashboardSuggestion) => {
      // The panel lays each section out on the server; the quick designer's
      // proposals are sized here.
      const slots = proposal.widgets.every(w => w.layout)
        ? proposal.widgets.map(w => w.layout!)
        : layout(proposal.widgets)
      // Saved as a packed page: a page with no mode is re-flowed by the
      // builder's default recipe on first open, which squeezed a four-figure
      // card into a two-row tile on the HR panel's first dashboard.
      await reportsApi.updatePage(reportId, pageId, { layout_mode: 'packed' } as never)
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
      const configs = proposal.widgets.map(w => ({ ...(w.config ?? {}) }) as Record<string, unknown>)
      for (const [widgetId, actions] of bySource) {
        const index = createdIds.indexOf(widgetId)
        configs[index] = { ...configs[index], interaction: { broadcasts: true, receives: true, actions } }
        await reportsApi.updateWidget(reportId, pageId as number, widgetId, {
          config: configs[index],
        } as never)
      }
      return { ids: createdIds, configs }
  }

  const newReport = async (name: string) => {
    const report = await reportsApi.create({
      name,
      description: goal ? `Suggested for: ${goal}` : 'Suggested from the data',
      dataset_id: datasetId,
    } as never)
    return { reportId: (report as { id: number }).id,
             pageId: (report as { pages?: { id: number }[] }).pages?.[0]?.id as number }
  }

  const create = async (proposal: DashboardSuggestion, index: number) => {
    setBuilding(index); setError('')
    try {
      const missing = await createDerived()
      const { reportId, pageId } = await newReport(titleOf(proposal))
      await fillPage(reportId, pageId, withoutFields(proposal, missing))
      navigate(`/reports/${reportId}`)
    } catch (e) {
      setError(reasonFrom(e, 'could not build that dashboard'))
    } finally {
      setBuilding(null)
    }
  }

  /** Panel mode: the sections are one dashboard's pages, not rival dashboards.
   *  The first page is the one a new report comes with, renamed. */
  const createAll = async () => {
    if (!proposals?.length) return
    setBuilding(-1); setError('')
    try {
      const missing = await createDerived()
      const pages = proposals.map(p => withoutFields(p, missing)).filter(p => p.widgets.length > 0)
      const { reportId, pageId } = await newReport(goal.trim() ? goal.trim().slice(0, 80) : datasetName)
      const built: { pid: number; page: DashboardSuggestion; ids: number[]; configs: Record<string, unknown>[] }[] = []
      for (let i = 0; i < pages.length; i++) {
        let pid = pageId
        const p = pages[i]
        if (i === 0) await reportsApi.updatePage(reportId, pageId, { name: titleOf(p) } as never)
        else pid = (await reportsApi.addPage(reportId, {
          name: titleOf(p), position: i, layout_mode: 'packed',
          // A drill-through page: hidden from the tabs, opened from a chart
          // with the clicked value as its filter (prompt_column).
          ...(p.page_type ? { page_type: p.page_type, prompt_column: p.prompt_column,
                              prompt_label: p.prompt_label } : {}),
        } as never)).id
        built.push({ pid, page: p, ...(await fillPage(reportId, pid, p)) })
      }
      // Charts split by the drill page's category open it on double-click.
      // Its id exists only now, so this is a pass after every page is built.
      const drill = built.find(b => b.page.page_type === 'drillthrough')
      if (drill) {
        for (const b of built) {
          for (let k = 0; k < b.page.widgets.length; k++) {
            if (b.page.widgets[k].drill_to !== 'drill' || !b.ids[k]) continue
            await reportsApi.updateWidget(reportId, b.pid, b.ids[k], {
              config: { ...b.configs[k], drillthroughPageId: drill.pid },
            } as never)
          }
        }
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
           aria-label={`${tr('datasets.suggest')} ${tr('sdd.for')} ${datasetName}`}>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
          <div style={{ flex: 1 }}>
            <h2 style={{ margin: 0, fontSize: 18 }}>
              <Sparkles size={16} style={{ verticalAlign: -2, marginRight: 6 }} />
              {tr('datasets.suggest')}
            </h2>
            <div style={{ ...muted, marginTop: 4 }}>
              {tr('sdd.for')} <strong>{datasetName}</strong>
            </div>
          </div>
          <button className="btn btn-ghost btn-sm" onClick={onClose} aria-label={tr('sdd.close')}>
            <X size={15} />
          </button>
        </div>

        <div style={{ marginTop: 16 }}>
          <label htmlFor="suggest-goal"
                 style={{ display: 'block', fontSize: 12, fontWeight: 600, marginBottom: 6 }}>
            {tr('sdd.goalLabel')}
          </label>
          <textarea
            id="suggest-goal" rows={3} value={goal} disabled={busy}
            onChange={e => setGoal(e.target.value)}
            placeholder={tr('sdd.placeholder')} dir="auto"
            style={{ width: '100%', resize: 'vertical' }} />
          <div style={{ ...muted, marginTop: 4 }}>
            {tr('sdd.help1')} <strong>{tr('sdd.helpBlank')}</strong> {tr('sdd.help2')}
          </div>
          <fieldset disabled={busy} style={{ border: 0, padding: 0, margin: '10px 0 0' }}>
            <legend style={{ fontSize: 12, fontWeight: 600, marginBottom: 4 }}>{tr('sug.mode.label')}</legend>
            {(['quick', 'panel'] as const).map(m => (
              <label key={m} style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 13 }}>
                <input type="radio" name="suggest-mode" value={m} checked={mode === m}
                       onChange={() => setMode(m)} />
                {tr(`sug.mode.${m}`)}
              </label>
            ))}
            {mode === 'panel' && (
              <label style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 13, marginTop: 6 }}>
                {tr('sug.size')}
                <select value={size} onChange={e => setSize(Number(e.target.value))}
                        aria-label={tr('sug.size')}>
                  {[12, 24, 50].map(n => <option key={n} value={n}>{n}</option>)}
                </select>
              </label>
            )}
          </fieldset>
          <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
            <button className="btn btn-primary btn-sm" onClick={ask} disabled={busy}>
              {proposals ? tr('sdd.again') : tr('datasets.suggest')}
            </button>
          </div>
        </div>

        {busy && (
          <div role="status" aria-live="polite" style={{ ...card, ...muted }}>
            {mode === 'panel' ? <>
              {tr('sug.panelBusy', { s: seconds })}
              {stage?.stage && (STAGES as readonly string[]).includes(stage.stage) && (
                <div data-testid="panel-stage" style={{ marginTop: 4, color: 'var(--text)' }}>
                  {tr(`sug.stage.${stage.stage as typeof STAGES[number]}`, { ideas: stage.ideas ?? '' })}
                </div>
              )}
              <div style={{ marginTop: 4 }}>{tr('sug.panelSlow')}</div>
              <div style={{ marginTop: 4 }}>{tr('sug.canLeave')}</div>
            </> : <>
            {tr('sdd.busy', { s: seconds })}
            </>}
            {mode !== 'panel' && seconds > 25 && <div style={{ marginTop: 4 }}>
              {tr('sdd.slow')}
            </div>}
            <div style={{ marginTop: 8 }}>
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => void stopWatching()}>{tr('sdd.cancel')}</button>
            </div>
          </div>
        )}

        {error && <div style={{ ...card, color: 'var(--danger)' }}>{error}</div>}

        {profile && (
          <details style={card}>
            <summary style={{ cursor: 'pointer', fontWeight: 600, fontSize: 13 }}>
              {tr('sdd.understood')}
            </summary>
            <div style={{ ...muted, marginTop: 8 }}>
              <span>{tr('sdd.rows', { n: profile.row_count.toLocaleString() })}</span>
              {profile.structure.date_range && <> {tr('sdd.timeCol', {
                col: profile.structure.date_range.column,
                days: profile.structure.date_range.days,
                grain: profile.structure.date_range.granularity })}</>}
            </div>
            <ul style={{ ...muted, marginTop: 8, paddingLeft: 18 }}>
              {profile.columns.map(c => (
                <li key={c.name}>
                  <code>{c.name}</code> — {c.role}
                  {c.distinct ? `, ${tr('sdd.distinct', { n: c.distinct.toLocaleString() })}` : ''}
                  {c.is_identifier && ` · ${tr('sdd.identifier')}`}
                  {c.is_personal && ` · ${tr('sdd.personal')}`}
                </li>
              ))}
            </ul>
          </details>
        )}

        {proposals?.length === 0 && !busy && (
          <div style={{ ...card, ...muted }}>
            {tr('sdd.none')}{reason ? `: ${reason}` : '.'}
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
                  {tr('sdd.answer')}
                </button>
              </div>
            )}
          </div>
        )}

        {source && (proposals?.length ?? 0) > 0 && (
          <div style={{ ...card, ...muted }}>
            {source === 'panel' ? tr('sug.panelSource')
              : source === 'insights'
              ? tr('sdd.srcInsights')
              : tr('sdd.srcModel')}
            {stats && <div data-testid="panel-stats" style={{ marginTop: 4 }}>
              {tr('sug.panelStats', { candidates: stats.candidates, model: stats.from_model,
                stats: stats.from_statistics, drawn: stats.drawn,
                merged: stats.duplicates_merged, kept: stats.selected })}
            </div>}
            {stats && (stats.rejected > 0 || (stats.not_picked ?? 0) > 0) && (
              <details data-testid="panel-left-out" style={{ marginTop: 6 }}>
                <summary style={{ cursor: 'pointer' }}>{tr('sug.leftOut', { n: stats.rejected })}</summary>
                <ul style={{ margin: '4px 0 0', paddingInlineStart: 18 }}>
                  {Object.entries(stats.left_out ?? {}).sort((a, b) => b[1] - a[1]).map(([code, n]) => (
                    <li key={code}>{n} · {tr(isLeftOut(code) ? `sug.left.${code}` : 'sug.left.invalid')}</li>
                  ))}
                  {(stats.not_picked ?? 0) > 0 && <li>{tr('sug.notPicked', { n: stats.not_picked ?? 0 })}</li>}
                </ul>
                {refused.length > 0 && (
                  <ul dir="auto" style={{ margin: '6px 0 0', paddingInlineStart: 18, opacity: 0.85 }}>
                    {refused.filter(r => r.source === 'model').slice(0, 20).map((r, k) => (
                      <li key={k}><strong>{r.title}</strong> — {tr(isLeftOut(r.code) ? `sug.left.${r.code}` : 'sug.left.invalid')}</li>
                    ))}
                  </ul>
                )}
              </details>
            )}
            {derived.measures.length + derived.calculated_columns.length > 0 && (
              <div dir="auto" style={{ ...muted, marginTop: 6 }}>
                {tr('sdd.derived', { n: derived.measures.length + derived.calculated_columns.length,
                                     names: [...derived.calculated_columns, ...derived.measures].map(f => f.name).join(', ') })}
              </div>
            )}
            {facts.length > 0 && (
              <details style={{ marginTop: 6 }}>
                <summary style={{ cursor: 'pointer' }}>{tr('sug.factsTitle')}</summary>
                <ul dir="auto" style={{ margin: '4px 0 0', paddingInlineStart: 18 }}>
                  {facts.map((f, k) => <li key={k}>{f}</li>)}
                </ul>
              </details>
            )}
            {(source === 'panel' || proposals?.some(p => p.section)) && (
              <div style={{ marginTop: 8 }}>
                <button className="btn btn-primary btn-sm" disabled={building !== null} onClick={createAll}>
                  {building === -1 ? tr('sdd.building')
                    : tr('sug.createAll', { n: proposals!.reduce((a, p) => a + p.widgets.length, 0) })}
                </button>
              </div>
            )}
          </div>
        )}

        {proposals?.map((proposal, i) => (
          <div key={i} style={card}>
            <div style={{ fontWeight: 700 }}>{titleOf(proposal)}</div>
            <div style={{ ...muted, marginTop: 2 }}>{whyOf(proposal)}</div>
            <ul style={{ marginTop: 10, paddingLeft: 18, fontSize: 13 }}>
              {proposal.widgets.map((w, j) => (
                <li key={j} style={{ marginBottom: 4 }}>
                  <strong>{w.title}</strong>{' '}
                  <span style={muted}>{w.widget_type}</span>{' · '}
                  <span style={muted}>{w.row_count === 1
                    ? tr('sdd.row1') : tr('sdd.rows', { n: w.row_count.toLocaleString() })}</span>
                  {typeof w.evidence === 'number' && (
                    <span data-testid="proposal-evidence" style={muted}>{' · '}{tr(
                      w.evidence >= 0.3 ? 'sug.evidence.strong'
                        : w.evidence >= 0.1 ? 'sug.evidence.some' : 'sug.evidence.flat')}</span>
                  )}
                  {w.question && w.question !== w.title && (
                    <div dir="auto" style={muted}>{tr('sug.question')} {w.question}</div>
                  )}
                  {w.why && <div style={muted}>{w.why}</div>}
                  {/* What it actually drew -- beside the idea it was proposed
                      with, so a reader sees when the data disagreed. */}
                  {takeawayText(tr, w) && (
                    <div data-testid="proposal-takeaway" dir="auto" style={{ fontSize: 12.5, marginTop: 2 }}>
                      <span style={{ color: 'var(--accent)', fontWeight: 600 }}>{tr('sug.dataShows')}</span> {takeawayText(tr, w)}
                    </div>
                  )}
                </li>
              ))}
            </ul>
            {(proposal.relations?.length ?? 0) > 0 && (
              <div style={{ ...muted, marginTop: 8 }}>
                <strong style={{ color: 'var(--fg)' }}>{tr('sdd.connect')}</strong>
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
              {building === i ? tr('sdd.building') : tr('sdd.create')}
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}
