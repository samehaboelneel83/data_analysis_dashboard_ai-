/**
 * Guided setup, step 4: Dashboard (docs/guided-setup/PLAN_V2.md, part 4).
 *
 * Pages designed for what the person asked: each suggestion is one ANGLE on
 * their request, opens with the answer in words, and lists every chart with
 * what it shows. The person ticks one or more; ONE dashboard is made and each
 * ticked suggestion becomes a page of it (never several dashboards). Coming
 * back later, more suggestions can be added as pages of the same dashboard.
 * Change a suggestion by asking, or start blank.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import toast from 'react-hot-toast'
import { Check, LayoutDashboard, MessageSquare, Plus, RefreshCw, Sparkles } from 'lucide-react'
import WaitTime from './WaitTime'
import { answersCard } from '../../lib/answersCard'
import { useT } from '../../i18n'
import { useDirection } from '../../contexts/DirectionContext'
import { localDigits } from '../../lib/arabicFormats'
import { buildPages } from '../../lib/buildDashboard'
import { reportsApi, setupApi, type SetupDashboardStep, type SetupDesign } from '../../services/api'
import DemandCard from '../../components/setup/DemandCard'
import MiniChart from '../../components/setup/MiniChart'
import LoadError from '../../components/ui/LoadError'
import LoadingState from '../../components/ui/LoadingState'

const POLL_MS = 4000
const POLL_LIMIT = 90
const NAME_MAX = 80

export default function DashboardStep({ sourceId, flow, onBack, onNewFlow }: {
  sourceId: number; flow?: number; onBack: () => void
  /** Start another analysis of this connection (steps 2-4 again). */
  onNewFlow?: () => void
}) {
  const t = useT()
  const { language } = useDirection()
  const navigate = useNavigate()
  const [data, setData] = useState<SetupDashboardStep | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [answers, setAnswers] = useState(0)
  const [building, setBuilding] = useState<string | null>(null)
  const [picked, setPicked] = useState<Set<string> | null>(null)
  const [gaveUp, setGaveUp] = useState(false)
  const polls = useRef(0)

  const load = useCallback(async () => {
    try {
      setError(null)
      setData(await setupApi.dashboard(sourceId, language, flow))
      setAnswers(n => n + 1)
    } catch (e) { setError(e) }
  }, [sourceId, language, flow])
  useEffect(() => { polls.current = 0; load() }, [load])

  const waiting = !!data && (data.designs.pending || !!data.demand?.pending || data.designs.items.some(d => d.changing))
  useEffect(() => {
    if (!waiting) return
    if (polls.current >= POLL_LIMIT) { setGaveUp(true); return }
    const id = window.setTimeout(() => { polls.current += 1; load() }, POLL_MS)
    return () => window.clearTimeout(id)
  }, [waiting, answers, load])

  const used = new Set(data?.designs.used ?? [])
  const fresh = (data?.designs.items ?? []).filter(d => !used.has(d.id))
  // Every suggestion is ticked to begin with: each answers part of what was
  // asked, and the detail pages are what its charts open. Only the first was
  // ticked, so most people made a one-page dashboard (persona test 2026-10-12).
  // Adding to a dashboard already made, only the first is offered ticked.
  const chosen = picked ?? new Set((data?.designs.report_id ? fresh.slice(0, 1) : fresh).map(d => d.id))
  const selected = fresh.filter(d => chosen.has(d.id))

  function toggle(id: string) {
    const next = new Set(chosen)
    if (next.has(id)) next.delete(id); else next.add(id)
    setPicked(next)
  }

  async function create() {
    if (!data || !selected.length) return
    setBuilding('pages')
    try {
      const demand = data.demand
      const name = (demand?.subject || demand?.sentence || selected[0].proposal.title || '').slice(0, NAME_MAX)
        || t('setup.b.blankName', { name: selected[0].dataset_name })
      // "Your questions" heads the first page: every asked question, answered
      // from whichever chosen page holds it, or why not.
      const card = answersCard(selected, demand?.questions ?? [],
        { title: t('setup.b.answersTitle'), notOnPages: t('setup.b.notOnPages') })
      const id = await buildPages(
        selected.map((d, i) => ({
          datasetId: d.dataset_id,
          proposal: i === 0 && card ? { ...d.proposal, widgets: [card, ...(d.proposal.widgets ?? [])] } : d.proposal,
          scope: d.proposal.scope_filters ?? [],
          derived: { measures: d.derived.measures ?? [], calculated_columns: d.derived.calculated_columns ?? [] },
        })),
        name, demand?.sentence || selected[0].proposal.rationale || t('setup.b.madeBy'), data.designs.report_id)
      await setupApi.designsUsed(sourceId, id, selected.map(d => d.id), flow)
      navigate(`/reports/${id}`)
    } catch { toast.error(t('setup.b.createFailed')); setBuilding(null) }
  }

  async function blank() {
    if (!data?.datasets.length) return
    setBuilding('blank')
    try {
      const r = await reportsApi.create({ name: t('setup.b.blankName', { name: data.datasets[0].name }),
                                          dataset_id: data.datasets[0].id } as never)
      const id = (r as { id: number }).id
      await setupApi.designsUsed(sourceId, id, [], flow)
      navigate(`/reports/${id}`)
    } catch { toast.error(t('setup.b.createFailed')); setBuilding(null) }
  }

  async function again() {
    polls.current = 0; setGaveUp(false); setPicked(null)
    try { await setupApi.suggestDashboards(sourceId, language, flow); await load() }
    catch { toast.error(t('setup.d.suggestFailed')) }
  }

  async function change(d: SetupDesign, message: string) {
    polls.current = 0; setGaveUp(false)
    try { await setupApi.refineDashboard(sourceId, d.id, message, language, flow); await load() }
    catch { toast.error(t('setup.d.refineFailed')) }
  }

  if (error) return <LoadError what={t('setup.b.what')} error={error} onRetry={load} />
  if (!data) return <LoadingState />
  if (!data.has_data) {
    return (
      <section className="card setup-card">
        <p className="setup-card__lead">{t('setup.c.noDatasets')}</p>
        <div className="setup-footer setup-footer--start">
          <button type="button" className="btn btn-sm" onClick={onBack}>{t('setup.c.back')}</button>
        </div>
      </section>
    )
  }

  const { designs } = data
  const made = !!designs.report_id
  const n = localDigits(String(selected.length))
  return (
    <div className="setup-understand">
      {made && (
        <section className="card setup-card">
          <p className="setup-card__lead">{t('setup.a.made')}</p>
          <div className="setup-footer setup-footer--start">
            <button type="button" className="btn btn-primary btn-sm" onClick={() => navigate(`/reports/${designs.report_id}`)}>
              {t('setup.b.open')}</button>
            {onNewFlow && (
              <button type="button" className="btn btn-sm" onClick={onNewFlow}>
                <Plus size={13} aria-hidden="true" /> {t('setup.f.new')}
              </button>
            )}
          </div>
        </section>
      )}
      {data.demand && (
        <DemandCard sourceId={sourceId} flow={flow} demand={data.demand} onChooseData={onBack}
          onChanged={() => { polls.current = 0; setGaveUp(false); setPicked(null); load() }} />
      )}
      <section className="setup-section" aria-labelledby="setup-designs">
        <div className="setup-overview__head">
          <h2 id="setup-designs" className="setup-section__title">{made ? t('setup.a.morePages') : t('setup.a.pages')}</h2>
          {!designs.pending && (
            <button type="button" className="btn btn-ghost btn-sm" onClick={again}>
              <RefreshCw size={13} aria-hidden="true" /> {t('setup.d.suggestAgain')}
            </button>
          )}
        </div>
        <p className="setup-section__sub">{t('setup.a.sub')}</p>
        <div aria-live="polite">
          {designs.pending && !gaveUp && data.ai?.available === false && (
            <p className="setup-ai">{t('setup.ai.offDesign')}</p>
          )}
          {designs.pending && !gaveUp && (
            <p className="setup-ai setup-ai--pending"><Sparkles size={13} aria-hidden="true" /> {t('setup.a.designing')}<WaitTime since={designs.since} usual={data.usual?.designs} /></p>
          )}
          {designs.pending && gaveUp && (
            <p className="setup-ai">{t('setup.u.aiSlow')}{' '}
              <button type="button" className="btn btn-sm" onClick={() => { polls.current = 0; setGaveUp(false); load() }}>
                {t('setup.u.checkAgain')}</button></p>
          )}
          {!designs.pending && designs.items.length > 0 && designs.language && designs.language !== language && (
            <p className="setup-ai">{t('setup.langHint')}</p>
          )}
          {!designs.pending && designs.failed && !designs.items.length && (
            <p className="setup-ai">{t('setup.b.none')}</p>
          )}
        </div>
        <ul className="setup-tables">
          {designs.items.map(d => (
            <DesignCard key={d.id} d={d} busy={building} multi={data.datasets.length > 1}
              used={used.has(d.id)} checked={chosen.has(d.id)} onToggle={() => toggle(d.id)}
              onChange={m => change(d, m)} />
          ))}
        </ul>
      </section>
      {fresh.length > 0 && (
        <div className="setup-footer">
          <span className="setup-section__sub">
            {selected.length ? t('setup.a.onePer', { n }) : t('setup.a.pickOne')}
          </span>
          <button type="button" className="btn btn-primary" disabled={!selected.length || !!building || waiting}
            onClick={() => { void create() }}>
            {building === 'pages' ? t('setup.b.building')
              : made ? t('setup.a.addPages', { n }) : t('setup.a.create', { n })}
          </button>
        </div>
      )}
      <section className="card setup-card" aria-labelledby="setup-blank">
        <h2 id="setup-blank" className="setup-section__title">{t('setup.b.blank')}</h2>
        <p className="setup-section__sub">{t('setup.b.blankSub')}</p>
        <div className="setup-table__actions">
          <button type="button" className="btn btn-sm" disabled={!!building} onClick={blank}>{t('setup.b.blankButton')}</button>
        </div>
      </section>
    </div>
  )
}

function DesignCard({ d, busy, multi, used, checked, onToggle, onChange }: {
  d: SetupDesign; busy: string | null; multi: boolean; used: boolean; checked: boolean
  onToggle: () => void; onChange: (m: string) => void
}) {
  const t = useT()
  const [chat, setChat] = useState(false)
  const [message, setMessage] = useState('')
  const charts = d.proposal.widgets.filter(w => w.widget_type !== 'slicer' && w.widget_type !== 'text' && w.widget_type !== 'button')
  const links = d.proposal.widgets.filter(w => w.widget_type === 'button').length
  const clicks = (d.proposal.relations ?? []).length > 0
  const drills = charts.filter(w => (w as { drill_to?: string }).drill_to === 'drill').length
  const marked = charts.filter(w => Array.isArray((w.config as { display_rules?: unknown[] } | undefined)?.display_rules)).length
  const history = charts.filter(w => !!(w.config as { sparkline_date?: string } | undefined)?.sparkline_date).length
  const filters = d.proposal.widgets.filter(w => w.widget_type === 'slicer').length
  const boxId = `setup-design-${d.id}`
  return (
    <li className={`card setup-table${checked && !used ? ' is-picked' : ''}`}>
      <div className="setup-table__head">
        {used
          ? <Check size={18} aria-hidden="true" />
          : <input id={boxId} type="checkbox" checked={checked} disabled={!!busy || !!d.changing} onChange={onToggle}
              aria-label={t('setup.a.pickLabel', { name: d.proposal.title })} />}
        <LayoutDashboard size={18} aria-hidden="true" />
        <div className="setup-table__names">
          <h3 className="setup-table__title"><label htmlFor={used ? undefined : boxId}>{d.proposal.title}</label></h3>
          {multi && <span className="setup-badge">{d.dataset_name}</span>}
          {used && <span className="setup-badge setup-badge--you">{t('setup.a.used')}</span>}
        </div>
      </div>
      {d.proposal.answer
        ? <p className="setup-design__answer">{d.proposal.answer}</p>
        : d.proposal.rationale && <p className="setup-table__what">{d.proposal.rationale}</p>}
      {d.proposal.note && <p className="setup-section__sub">{d.proposal.note}</p>}
      <ol className="setup-previews">
        {charts.map((w, i) => (
          <li key={i} className={`setup-preview setup-preview--${w.preview?.kind ?? 'text'}`}>
            <strong className="setup-preview__title">{w.title}</strong>
            {w.preview && <MiniChart preview={w.preview} title={w.title} />}
            {(w.finding || w.why || w.takeaway) && (
              <span className="setup-section__sub">{w.finding || w.why || w.takeaway}</span>
            )}
          </li>
        ))}
      </ol>
      {(d.proposal.unanswered ?? []).map((u, i) => <p key={i} className="setup-ai">{u}</p>)}
      <ul className="setup-facts">
        <li>{t('setup.b.chartsN', { n: localDigits(String(charts.length)) })}</li>
        {filters > 0 && <li>{t('setup.b.filtersN', { n: localDigits(String(filters)) })}</li>}
        {clicks && <li>{t('setup.b.clicks')}</li>}
        {marked > 0 && <li>{t('setup.b.marked', { n: localDigits(String(marked)) })}</li>}
        {history > 0 && <li>{t('setup.b.history', { n: localDigits(String(history)) })}</li>}
        {links > 0 && <li>{t('setup.b.links', { n: localDigits(String(links)) })}</li>}
        {drills > 0 && <li>{t('setup.b.drills', { n: localDigits(String(drills)) })}</li>}
        {d.proposal.page_type === 'drillthrough' && <li>{t('setup.b.drillPage')}</li>}
      </ul>
      {!used && (
        <div className="setup-table__actions">
          <button type="button" className="btn btn-ghost btn-sm" aria-expanded={chat} onClick={() => setChat(v => !v)}>
            <MessageSquare size={13} aria-hidden="true" /> {t('setup.d.change')}
          </button>
        </div>
      )}
      {chat && !used && (
        <div className="setup-chat">
          {d.history.length > 0 && (
            <ul className="setup-chat__log">
              {d.history.map((m, i) => <li key={i} className={`setup-chat__msg setup-chat__msg--${m.role}`}>{m.text}</li>)}
            </ul>
          )}
          {d.changing && <p className="setup-ai setup-ai--pending"><Sparkles size={13} aria-hidden="true" /> {t('setup.b.changing')}</p>}
          {d.change_failed && !d.changing && <p className="setup-ai">{t('setup.d.changeFailed')}</p>}
          <form className="setup-chat__form" onSubmit={e => {
            e.preventDefault()
            if (!message.trim()) return
            onChange(message.trim()); setMessage('')
          }}>
            <input value={message} onChange={e => setMessage(e.target.value)} disabled={!!d.changing}
              placeholder={t('setup.a.changePh')} aria-label={t('setup.d.changeLabel', { name: d.proposal.title })} />
            <button type="submit" className="btn btn-sm btn-primary" disabled={!!d.changing || !message.trim()}>
              {t('setup.d.send')}</button>
          </form>
        </div>
      )}
    </li>
  )
}
