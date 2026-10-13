/**
 * "What you want", as the setup understood it (guided setup, PLAN_V2 3).
 *
 * One sentence the person can check at a glance, with "Change" to correct
 * it in their own words. The check and the dashboard are built for exactly
 * this, so a misunderstanding is fixed here once instead of in every chart.
 * A subject the data does not hold is said plainly, with what the data does
 * hold -- never silently replaced by everything. The questions and the
 * exact filters stay behind "Show details".
 */
import { useId, useState } from 'react'
import { AlertTriangle, ChevronDown, Pencil, Sparkles, Target } from 'lucide-react'
import toast from 'react-hot-toast'
import { useT } from '../../i18n'
import { useDirection } from '../../contexts/DirectionContext'
import { localDigits } from '../../lib/arabicFormats'
import { useAlwaysShowDetails } from '../../lib/detailsPreference'
import { setupApi, type SetupDemand, type SetupScope } from '../../services/api'

const num = (n: number) => localDigits(n.toLocaleString())
const SIGN: Record<string, string> = { gt: '>', gte: '≥', lt: '<', lte: '≤' }

function scopeText(s: SetupScope): string {
  const column = (s.column ?? '').replace(/_/g, ' ')
  // Narrowed by the dataset's own query: there is no column to name.
  if (!column) return s.said || s.values.slice(0, 6).join(', ')
  if (s.op === 'in') return `${column}: ${s.values.slice(0, 6).join(', ')}`
  if (s.op === 'between') return `${column}: ${s.values[0] ?? ''} – ${s.values[1] ?? ''}`
  return `${column} ${SIGN[s.op] ?? s.op} ${s.values[0] ?? ''}`
}

export default function DemandCard({ sourceId, flow, demand, onChanged, onChooseData }: {
  sourceId: number
  flow?: number
  /** Go back to Choose data: offered when the data lacks the base its events are counted against. */
  onChooseData?: () => void
  demand: SetupDemand
  /** Called after a correction was sent, so the step reloads and waits for it. */
  onChanged: () => void
}) {
  const t = useT()
  const { language } = useDirection()
  const [always] = useAlwaysShowDetails()
  const [open, setOpen] = useState<boolean | null>(null)
  const [editing, setEditing] = useState(false)
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const panelId = useId()
  const shown = open ?? always

  async function send(text: string) {
    if (!text.trim()) return
    setBusy(true)
    try {
      await setupApi.changeDemand(sourceId, text.trim(), language, flow)
      setMessage(''); setEditing(false)
      onChanged()
    } catch { toast.error(t('setup.w.changeFailed')) } finally { setBusy(false) }
  }

  if (demand.pending && !demand.written) {
    return (
      <section className="card setup-card setup-demand" aria-live="polite">
        <p className="setup-ai setup-ai--pending"><Sparkles size={13} aria-hidden="true" /> {t('setup.w.writing')}</p>
      </section>
    )
  }
  if (!demand.written) return null

  const unmatched = demand.scope.filter(s => s.status === 'unmatched')
  // One line per restriction: the same range on three datasets is said once.
  const applied = demand.scope.filter(s => s.status !== 'unmatched')
    .filter((s, i, all) => all.findIndex(o => scopeText(o) === scopeText(s)) === i)
  const hasDetails = demand.questions.length > 0 || applied.length > 0 || demand.exclude.length > 0

  return (
    <section className="card setup-card setup-demand" aria-labelledby="setup-demand">
      <div className="setup-overview__head">
        <h2 id="setup-demand" className="setup-section__title">
          <Target size={15} aria-hidden="true" /> {t('setup.w.title')}
        </h2>
        {!demand.pending && (
          <button type="button" className="btn btn-ghost btn-sm" aria-expanded={editing}
            onClick={() => setEditing(v => !v)}>
            <Pencil size={13} aria-hidden="true" /> {t('setup.w.change')}
          </button>
        )}
      </div>
      <p className="setup-demand__sentence">{demand.sentence}</p>
      <div aria-live="polite">
        {demand.pending && (
          <p className="setup-ai setup-ai--pending"><Sparkles size={13} aria-hidden="true" /> {t('setup.w.rewriting')}</p>
        )}
      </div>

      {applied.length > 0 && (
        <ul className="setup-facts">
          {applied.map((s, i) => (
            <li key={i}>{t('setup.w.only', { what: scopeText(s) })}</li>
          ))}
        </ul>
      )}

      {unmatched.map((s, i) => (
        <div key={i} className="setup-demand__warn" role="alert">
          <p><AlertTriangle size={14} aria-hidden="true" /> {t('setup.w.unmatched', { said: s.said })}</p>
          {(s.candidates ?? []).length > 0 && (
            <>
              <p className="setup-section__sub">{t('setup.w.unmatchedPick')}</p>
              {(s.candidates ?? []).map(c => (
                <div key={c.column} className="setup-demand__pick">
                  <span className="setup-section__sub">{c.column.replace(/_/g, ' ')}:</span>
                  {c.values.map(v => (
                    <button key={v} type="button" className="btn btn-sm" disabled={busy || demand.pending}
                      onClick={() => send(t('setup.w.pickMessage', { said: s.said, value: v, column: c.column }))}>
                      {v}
                    </button>
                  ))}
                </div>
              ))}
            </>
          )}
          <button type="button" className="btn btn-ghost btn-sm" disabled={busy || demand.pending}
            onClick={() => send(t('setup.w.dropMessage', { said: s.said }))}>
            {t('setup.w.dropScope')}
          </button>
        </div>
      ))}

      {(demand.base_missing ?? []).slice(0, 1).map(b => (
        <div key={b.events} className="setup-demand__warn" role="note">
          <p><AlertTriangle size={14} aria-hidden="true" /> {t('setup.w.baseMissing', {
            events: b.events.replace(/_/g, ' '), base: b.base.replace(/_/g, ' ') })}</p>
          {onChooseData && (
            <button type="button" className="btn btn-sm" onClick={onChooseData}>{t('setup.w.baseMissingDo')}</button>
          )}
        </div>
      ))}

      {editing && (
        <form className="setup-chat__form" onSubmit={e => { e.preventDefault(); void send(message) }}>
          <input value={message} onChange={e => setMessage(e.target.value)} disabled={busy} autoFocus
            placeholder={t('setup.w.changePh')} aria-label={t('setup.w.changeLabel')} />
          <button type="submit" className="btn btn-sm btn-primary" disabled={busy || !message.trim()}>
            {t('setup.d.send')}</button>
        </form>
      )}

      {hasDetails && (
        <>
          <button type="button" className="plain-summary__toggle" aria-expanded={shown} aria-controls={panelId}
            onClick={() => setOpen(!shown)}>
            <ChevronDown size={14} aria-hidden="true"
              className={shown ? 'plain-summary__chevron plain-summary__chevron--open' : 'plain-summary__chevron'} />
            {shown ? t('plain.hideDetails') : t('plain.showDetails')}
          </button>
          {shown && (
            <div id={panelId} className="setup-demand__details">
              {demand.questions.length > 0 && (
                <>
                  <p className="setup-split__title">{t('setup.w.questions')}</p>
                  <ol className="setup-questions">
                    {demand.questions.map(q => <li key={q.id}>{q.text}</li>)}
                  </ol>
                </>
              )}
              {applied.length > 0 && (
                <>
                  <p className="setup-split__title">{t('setup.w.scope')}</p>
                  <ul className="setup-questions">
                    {applied.map((s, i) => (
                      <li key={i}>
                        {scopeText(s)} — {s.status === 'in_data'
                          ? t('setup.w.inData', { n: num(s.of_rows) })
                          : t('setup.w.inDashboard', { n: num(s.matched_rows), total: num(s.of_rows) })}
                      </li>
                    ))}
                  </ul>
                </>
              )}
              {demand.exclude.length > 0 && (
                <>
                  <p className="setup-split__title">{t('setup.w.exclude')}</p>
                  <ul className="setup-questions">{demand.exclude.map((x, i) => <li key={i}>{x}</li>)}</ul>
                </>
              )}
            </div>
          )}
        </>
      )}
    </section>
  )
}
