/**
 * Guided setup, step 3: Check & discover (docs/guided-setup/PLAN_V2.md, part 2).
 *
 * Simple first: for each chosen dataset ONE summary -- "your data is ready",
 * what was fixed for you, the few things worth knowing -- then what the data
 * already shows. Everything else stays one click away under "Show details":
 * every automatic fix with its Undo, every other finding with "Fix it", and
 * the link to the full quality report. Checked once and kept; "Check again"
 * after a change. On top, what the setup understood the person wants, so a
 * misunderstanding is corrected before the dashboard is designed for it.
 */
import { useCallback, useEffect, useId, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import toast from 'react-hot-toast'
import { CheckCircle2, ChevronDown, Info, RefreshCw, Sparkles, Undo2 } from 'lucide-react'
import { useT } from '../../i18n'
import { useDirection } from '../../contexts/DirectionContext'
import { localDigits } from '../../lib/arabicFormats'
import { useAlwaysShowDetails } from '../../lib/detailsPreference'
import { detailToText } from '../../lib/friendlyError'
import { setupApi, type SetupCheckStep, type SetupFindingItem } from '../../services/api'
import DemandCard from '../../components/setup/DemandCard'
import FindingsSummary from '../../components/setup/FindingsSummary'
import PlainSummary from '../../components/ui/PlainSummary'
import LoadError from '../../components/ui/LoadError'
import LoadingState from '../../components/ui/LoadingState'

const POLL_MS = 4000
const POLL_LIMIT = 60
const num = (n: number | null | undefined) => localDigits((n ?? 0).toLocaleString())

type CheckedDataset = SetupCheckStep['datasets'][number]

export default function CheckStep({ sourceId, flow, onNext, onBack }: {
  sourceId: number; flow?: number; onNext: () => void; onBack: () => void
}) {
  const t = useT()
  const { language } = useDirection()
  const [data, setData] = useState<SetupCheckStep | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [answers, setAnswers] = useState(0)
  const [busy, setBusy] = useState<string | null>(null)
  const [gaveUp, setGaveUp] = useState(false)
  const polls = useRef(0)

  const load = useCallback(async () => {
    try {
      setError(null)
      setData(await setupApi.check(sourceId, language, flow))
      setAnswers(n => n + 1)
    } catch (e) { setError(e) }
  }, [sourceId, language, flow])
  useEffect(() => { polls.current = 0; load() }, [load])

  const checking = !!data?.datasets.some(d => d.findings.pending)
  const waiting = checking || !!data?.demand?.pending
  useEffect(() => {
    if (!waiting) return
    if (polls.current >= POLL_LIMIT) { setGaveUp(true); return }
    const id = window.setTimeout(() => { polls.current += 1; load() }, POLL_MS)
    return () => window.clearTimeout(id)
  }, [waiting, answers, load])

  const failure = (e: unknown, fallback: string) => {
    const detail = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
    toast.error(detail ? detailToText(detail) : fallback)
  }

  async function fix(datasetId: number, item: SetupFindingItem, how: 'fix' | 'check') {
    setBusy(`${item.id}|${how}`)
    try {
      await setupApi.fix(sourceId, datasetId, item.id, how, language, flow)
      toast.success(how === 'fix' ? t('setup.c.fixed') : t('setup.c.checkSaved'))
      await load()
    } catch (e) { failure(e, t('setup.c.fixFailed')) } finally { setBusy(null) }
  }

  async function undo(datasetId: number, actionId: string | null, redo = false) {
    setBusy(`undo|${actionId ?? 'all'}`)
    try {
      await setupApi.undoFix(sourceId, datasetId, actionId, redo, flow)
      toast.success(redo ? t('setup.k.redone') : t('setup.k.undone'))
      await load()
    } catch (e) { failure(e, t('setup.k.undoFailed')) } finally { setBusy(null) }
  }

  async function again(datasetId: number) {
    polls.current = 0
    setGaveUp(false)
    try { await setupApi.runCheck(sourceId, datasetId, language, flow); await load() }
    catch { toast.error(t('setup.c.runFailed')) }
  }

  if (error) return <LoadError what={t('setup.c.what')} error={error} onRetry={load} />
  if (!data) return <LoadingState />

  if (!data.datasets.length) {
    return (
      <section className="card setup-card">
        <p className="setup-card__lead">{t('setup.c.noDatasets')}</p>
        <div className="setup-footer setup-footer--start">
          <button type="button" className="btn btn-sm" onClick={onBack}>{t('setup.c.back')}</button>
        </div>
      </section>
    )
  }

  const retry = () => { polls.current = 0; setGaveUp(false); load() }
  return (
    <div className="setup-understand">
      {data.demand && (
        <DemandCard sourceId={sourceId} flow={flow} demand={data.demand} onChooseData={onBack}
          onChanged={() => { polls.current = 0; setGaveUp(false); load() }} />
      )}
      {data.datasets.map(d => (
        <DatasetCheck key={d.id} d={d} language={language} gaveUp={gaveUp} busy={busy}
          onRetry={retry} onAgain={() => again(d.id)}
          onFix={(item, how) => fix(d.id, item, how)}
          onUndo={(id, redo) => undo(d.id, id, redo)} />
      ))}
      <div className="setup-footer">
        <span className="setup-section__sub">{t('setup.k.footer')}</span>
        <button type="button" className="btn btn-primary" onClick={onNext} disabled={checking && !gaveUp}>
          {t('setup.next', { step: t('setup.step.dashboard') })}
        </button>
      </div>
    </div>
  )
}

function DatasetCheck({ d, language, gaveUp, busy, onRetry, onAgain, onFix, onUndo }: {
  d: CheckedDataset; language: string; gaveUp: boolean; busy: string | null
  onRetry: () => void; onAgain: () => void
  onFix: (item: SetupFindingItem, how: 'fix' | 'check') => void
  onUndo: (actionId: string | null, redo?: boolean) => void
}) {
  const t = useT()
  const [always] = useAlwaysShowDetails()
  const [open, setOpen] = useState<boolean | null>(null)
  const panelId = useId()
  const shown = open ?? always
  const f = d.findings
  const clean = f.cleaning
  const ready = !f.pending && f.checked && !f.failed
  const fixed = clean?.fixed ?? []
  const know = clean?.know ?? []
  const actions = clean?.actions ?? []
  const removed = (clean?.rows_before ?? 0) - (clean?.rows_after ?? 0)
  // After an undo the dataset has its rows back before the next check counts them.
  const rows = clean?.rows_after ?? f.rows
  const problems = f.health.filter(i => i.tone !== 'good')

  return (
    <section className="setup-section" aria-labelledby={`setup-ds-${d.id}`}>
      <div className="setup-overview__head">
        <h2 id={`setup-ds-${d.id}`} className="setup-section__title">{d.name}</h2>
        {f.rows != null && <span className="setup-section__sub">
          {t('setup.u.rowsN', { n: num(rows) })} · {t('setup.d.columnsN', { n: num(f.columns) })}</span>}
        {!f.pending && (
          <button type="button" className="btn btn-ghost btn-sm" onClick={onAgain} title={t('setup.c.againHint')}>
            <RefreshCw size={13} aria-hidden="true" /> {t('setup.c.again')}
          </button>
        )}
      </div>
      <div aria-live="polite">
        {f.pending && !gaveUp && (
          <p className="setup-ai setup-ai--pending"><Sparkles size={13} aria-hidden="true" /> {t('setup.k.checking')}</p>
        )}
        {f.pending && gaveUp && (
          <p className="setup-ai">{t('setup.u.aiSlow')}{' '}
            <button type="button" className="btn btn-sm" onClick={onRetry}>{t('setup.u.checkAgain')}</button></p>
        )}
        {!f.pending && f.failed && <p className="setup-ai">{t('setup.c.failed')} {f.failed !== 'failed' ? f.failed : ''}</p>}
        {!f.pending && f.language && f.language !== language && f.health.length > 0 && (
          <p className="setup-ai">{t('setup.langHintCheck')}</p>
        )}
      </div>

      {ready && (
        <div className="card setup-card setup-clean">
          <p className="setup-clean__lead">
            <CheckCircle2 size={18} aria-hidden="true" /> {t('setup.k.ready', { n: num(rows) })}
          </p>
          {fixed.length > 0 ? (
            <>
              <p className="setup-clean__head">{t('setup.k.fixedN', { n: fixed.length })}</p>
              <ul className="setup-clean__list">
                {fixed.map(a => <li key={a.id}>{a.said}{a.ai && <span className="setup-badge setup-badge--ai">{t('setup.k.byAi')}</span>}</li>)}
              </ul>
              {removed > 0 && <p className="setup-section__sub">{t('setup.k.rowsLeft', { before: num(clean?.rows_before), after: num(clean?.rows_after) })}</p>}
            </>
          ) : (
            <p className="setup-section__sub">{d.auto_clean ? t('setup.k.nothingFixed') : t('setup.k.notAuto')}</p>
          )}
          {know.length > 0 && (
            <>
              <p className="setup-clean__head"><Info size={14} aria-hidden="true" /> {t('setup.k.knowN', { n: know.length + (clean?.more ?? 0) })}</p>
              <ul className="setup-clean__list">
                {know.map(k => <li key={k.id}>{k.what}</li>)}
                {(clean?.more ?? 0) > 0 && <li className="setup-section__sub">{t('setup.k.more', { n: clean?.more ?? 0 })}</li>}
              </ul>
            </>
          )}
          <div className="setup-table__actions">
            <button type="button" className="plain-summary__toggle" aria-expanded={shown} aria-controls={panelId}
              onClick={() => setOpen(!shown)}>
              <ChevronDown size={14} aria-hidden="true"
                className={shown ? 'plain-summary__chevron plain-summary__chevron--open' : 'plain-summary__chevron'} />
              {shown ? t('plain.hideDetails') : t('setup.k.details')}
            </button>
            {fixed.length > 1 && (
              <button type="button" className="btn btn-ghost btn-sm" disabled={!!busy} onClick={() => onUndo(null)}>
                <Undo2 size={13} aria-hidden="true" /> {t('setup.k.undoAll')}
              </button>
            )}
          </div>
          {shown && (
            <div id={panelId} className="setup-clean__details">
              {actions.length > 0 && (
                <>
                  <p className="setup-split__title">{t('setup.k.autoTitle')}</p>
                  <p className="setup-section__sub">{t('setup.k.autoSub')}</p>
                  <ul className="setup-clean__actions">
                    {actions.map(a => (
                      <li key={a.id} className={a.state === 'undone' ? 'is-undone' : undefined}>
                        <span>{a.said}{a.state === 'undone' && <em> — {t('setup.k.undoneMark')}</em>}</span>
                        <button type="button" className="btn btn-sm" disabled={!!busy}
                          aria-label={`${a.state === 'undone' ? t('setup.k.redo') : t('setup.k.undo')}: ${a.said}`}
                          onClick={() => onUndo(a.id, a.state === 'undone')}>
                          {a.state === 'undone' ? t('setup.k.redo') : t('setup.k.undo')}
                        </button>
                      </li>
                    ))}
                  </ul>
                </>
              )}
              {problems.length > 0 && (
                <FindingsSummary findings={{ ...f, insights: [] }} busy={busy} onFix={onFix}
                  healthTitle={t('setup.k.restTitle')} />
              )}
              <p className="dl-health__more"><Link to={`/datasets/${d.id}?tab=rules`}>{t('setup.c.details')}</Link></p>
            </div>
          )}
        </div>
      )}

      {ready && f.insights.length > 0 && (
        <PlainSummary title={t('setup.c.insights')} items={f.insights.map(i => ({
          id: i.id, tone: i.tone, what: i.what, why: i.why || undefined, todo: i.todo ?? undefined }))} />
      )}
    </section>
  )
}
