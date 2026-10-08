/**
 * Guided setup, step 4: Dashboard (docs/guided-setup/PLAN.md, 4b).
 *
 * The app's dashboard designer, told who the person is and what Check &
 * discover found, proposes up to three dashboards; every chart was drawn
 * before it is offered and says why it is there. Change one by asking, or
 * start blank. Either way the dashboard opens in the builder, where the
 * suggestion pane and the copilot keep helping.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import toast from 'react-hot-toast'
import { LayoutDashboard, MessageSquare, RefreshCw, Sparkles } from 'lucide-react'
import { useT } from '../../i18n'
import { useDirection } from '../../contexts/DirectionContext'
import { localDigits } from '../../lib/arabicFormats'
import { buildDashboard } from '../../lib/buildDashboard'
import { reportsApi, setupApi, type SetupDashboardStep, type SetupDesign } from '../../services/api'
import LoadError from '../../components/ui/LoadError'
import LoadingState from '../../components/ui/LoadingState'

const POLL_MS = 4000
const POLL_LIMIT = 75

export default function DashboardStep({ sourceId, onBack }: { sourceId: number; onBack: () => void }) {
  const t = useT()
  const { language } = useDirection()
  const navigate = useNavigate()
  const [data, setData] = useState<SetupDashboardStep | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [answers, setAnswers] = useState(0)
  const [building, setBuilding] = useState<string | null>(null)
  const [gaveUp, setGaveUp] = useState(false)
  const polls = useRef(0)

  const load = useCallback(async () => {
    try {
      setError(null)
      setData(await setupApi.dashboard(sourceId, language))
      setAnswers(n => n + 1)
    } catch (e) { setError(e) }
  }, [sourceId, language])
  useEffect(() => { polls.current = 0; load() }, [load])

  const waiting = !!data && (data.designs.pending || data.designs.items.some(d => d.changing))
  useEffect(() => {
    if (!waiting) return
    if (polls.current >= POLL_LIMIT) { setGaveUp(true); return }
    const id = window.setTimeout(() => { polls.current += 1; load() }, POLL_MS)
    return () => window.clearTimeout(id)
  }, [waiting, answers, load])

  async function finish(reportId: number) {
    await setupApi.update(sourceId, { report_id: reportId, step: 'done' })
    navigate(`/reports/${reportId}`)
  }

  async function create(d: SetupDesign) {
    setBuilding(d.id)
    try {
      const id = await buildDashboard(d.dataset_id, d.proposal,
        { measures: d.derived.measures ?? [], calculated_columns: d.derived.calculated_columns ?? [] },
        d.proposal.title, d.proposal.rationale || t('setup.b.madeBy'))
      await finish(id)
    } catch { toast.error(t('setup.b.createFailed')); setBuilding(null) }
  }

  async function blank() {
    if (!data?.datasets.length) return
    setBuilding('blank')
    try {
      const r = await reportsApi.create({ name: t('setup.b.blankName', { name: data.datasets[0].name }),
                                          dataset_id: data.datasets[0].id } as never)
      await finish((r as { id: number }).id)
    } catch { toast.error(t('setup.b.createFailed')); setBuilding(null) }
  }

  async function again() {
    polls.current = 0; setGaveUp(false)
    try { await setupApi.suggestDashboards(sourceId, language); await load() }
    catch { toast.error(t('setup.d.suggestFailed')) }
  }

  async function change(d: SetupDesign, message: string) {
    polls.current = 0; setGaveUp(false)
    try { await setupApi.refineDashboard(sourceId, d.id, message, language); await load() }
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
  return (
    <div className="setup-understand">
      {designs.report_id && (
        <section className="card setup-card">
          <p className="setup-card__lead">{t('setup.b.alreadyMade')}</p>
          <div className="setup-footer setup-footer--start">
            <button type="button" className="btn btn-primary btn-sm" onClick={() => navigate(`/reports/${designs.report_id}`)}>
              {t('setup.b.open')}</button>
          </div>
        </section>
      )}
      <section className="setup-section" aria-labelledby="setup-designs">
        <div className="setup-overview__head">
          <h2 id="setup-designs" className="setup-section__title">{t('setup.b.proposals')}</h2>
          {!designs.pending && (
            <button type="button" className="btn btn-ghost btn-sm" onClick={again}>
              <RefreshCw size={13} aria-hidden="true" /> {t('setup.d.suggestAgain')}
            </button>
          )}
        </div>
        <p className="setup-section__sub">{t('setup.b.sub')}</p>
        <div aria-live="polite">
          {designs.pending && !gaveUp && (
            <p className="setup-ai setup-ai--pending"><Sparkles size={13} aria-hidden="true" /> {t('setup.b.designing')}</p>
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
              onCreate={() => create(d)} onChange={m => change(d, m)} />
          ))}
        </ul>
      </section>
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

function DesignCard({ d, busy, multi, onCreate, onChange }: {
  d: SetupDesign; busy: string | null; multi: boolean; onCreate: () => void; onChange: (m: string) => void
}) {
  const t = useT()
  const [chat, setChat] = useState(false)
  const [message, setMessage] = useState('')
  const charts = d.proposal.widgets.filter(w => w.widget_type !== 'slicer')
  const filters = d.proposal.widgets.length - charts.length
  return (
    <li className="card setup-table">
      <div className="setup-table__head">
        <LayoutDashboard size={18} aria-hidden="true" />
        <div className="setup-table__names">
          <h3 className="setup-table__title">{d.proposal.title}</h3>
          {multi && <span className="setup-badge">{d.dataset_name}</span>}
        </div>
      </div>
      {d.proposal.rationale && <p className="setup-table__what">{d.proposal.rationale}</p>}
      <ol className="setup-charts">
        {charts.map((w, i) => (
          <li key={i}>
            <strong>{w.title}</strong>
            {(w.why || w.takeaway) && <span className="setup-section__sub"> — {w.why || w.takeaway}</span>}
          </li>
        ))}
      </ol>
      <ul className="setup-facts">
        <li>{t('setup.b.chartsN', { n: localDigits(String(charts.length)) })}</li>
        {filters > 0 && <li>{t('setup.b.filtersN', { n: localDigits(String(filters)) })}</li>}
      </ul>
      <div className="setup-table__actions">
        <button type="button" className="btn btn-primary btn-sm" disabled={!!busy || !!d.changing} onClick={onCreate}>
          {busy === d.id ? t('setup.b.building') : t('setup.b.create')}
        </button>
        <button type="button" className="btn btn-ghost btn-sm" aria-expanded={chat} onClick={() => setChat(v => !v)}>
          <MessageSquare size={13} aria-hidden="true" /> {t('setup.d.change')}
        </button>
      </div>
      {chat && (
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
              placeholder={t('setup.b.changePh')} aria-label={t('setup.d.changeLabel', { name: d.proposal.title })} />
            <button type="submit" className="btn btn-sm btn-primary" disabled={!!d.changing || !message.trim()}>
              {t('setup.d.send')}</button>
          </form>
        </div>
      )}
    </li>
  )
}
