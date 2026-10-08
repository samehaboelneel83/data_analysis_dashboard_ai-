/**
 * Guided setup, step 3: Check & discover (docs/guided-setup/PLAN.md, 3d).
 *
 * For each chosen dataset: what is wrong with the data, why it matters and
 * what to do (with "Fix it"), then the strongest insights in plain words.
 * Checked once and kept; "Check again" after fixing. The full quality
 * report and checks stay one click away on the dataset's Rules & alerts tab.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import toast from 'react-hot-toast'
import { RefreshCw, Sparkles } from 'lucide-react'
import { useT } from '../../i18n'
import { useDirection } from '../../contexts/DirectionContext'
import { localDigits } from '../../lib/arabicFormats'
import { detailToText } from '../../lib/friendlyError'
import { setupApi, type SetupCheckStep, type SetupFindingItem } from '../../services/api'
import FindingsSummary from '../../components/setup/FindingsSummary'
import LoadError from '../../components/ui/LoadError'
import LoadingState from '../../components/ui/LoadingState'

const POLL_MS = 4000
const POLL_LIMIT = 60
const num = (n: number | null | undefined) => localDigits((n ?? 0).toLocaleString())

export default function CheckStep({ sourceId, onNext, onBack }: {
  sourceId: number; onNext: () => void; onBack: () => void
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
      setData(await setupApi.check(sourceId, language))
      setAnswers(n => n + 1)
    } catch (e) { setError(e) }
  }, [sourceId, language])
  useEffect(() => { polls.current = 0; load() }, [load])

  const waiting = !!data?.datasets.some(d => d.findings.pending)
  useEffect(() => {
    if (!waiting) return
    if (polls.current >= POLL_LIMIT) { setGaveUp(true); return }
    const id = window.setTimeout(() => { polls.current += 1; load() }, POLL_MS)
    return () => window.clearTimeout(id)
  }, [waiting, answers, load])

  async function fix(datasetId: number, item: SetupFindingItem, how: 'fix' | 'check') {
    setBusy(`${item.id}|${how}`)
    try {
      await setupApi.fix(sourceId, datasetId, item.id, how, language)
      toast.success(how === 'fix' ? t('setup.c.fixed') : t('setup.c.checkSaved'))
      await load()
    } catch (e) {
      const detail = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
      toast.error(detail ? detailToText(detail) : t('setup.c.fixFailed'))
    } finally { setBusy(null) }
  }

  async function again(datasetId: number) {
    polls.current = 0
    setGaveUp(false)
    try { await setupApi.runCheck(sourceId, datasetId, language); await load() }
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

  return (
    <div className="setup-understand">
      <p className="setup-section__sub">{t('setup.c.sub')}</p>
      {data.datasets.map(d => {
        const f = d.findings
        return (
          <section key={d.id} className="setup-section" aria-labelledby={`setup-ds-${d.id}`}>
            <div className="setup-overview__head">
              <h2 id={`setup-ds-${d.id}`} className="setup-section__title">{d.name}</h2>
              {f.rows != null && <span className="setup-section__sub">
                {t('setup.u.rowsN', { n: num(f.rows) })} · {t('setup.d.columnsN', { n: num(f.columns) })}</span>}
              {!f.pending && (
                <button type="button" className="btn btn-ghost btn-sm" onClick={() => again(d.id)}
                  title={t('setup.c.againHint')}>
                  <RefreshCw size={13} aria-hidden="true" /> {t('setup.c.again')}
                </button>
              )}
            </div>
            <div aria-live="polite">
              {f.pending && !gaveUp && (
                <p className="setup-ai setup-ai--pending"><Sparkles size={13} aria-hidden="true" /> {t('setup.c.checking')}</p>
              )}
              {f.pending && gaveUp && (
                <p className="setup-ai">{t('setup.u.aiSlow')}{' '}
                  <button type="button" className="btn btn-sm" onClick={() => { polls.current = 0; setGaveUp(false); load() }}>
                    {t('setup.u.checkAgain')}</button></p>
              )}
              {!f.pending && f.failed && <p className="setup-ai">{t('setup.c.failed')} {f.failed !== 'failed' ? f.failed : ''}</p>}
              {f.fixed.length > 0 && !f.pending && <p className="setup-ai">{t('setup.c.afterFix')}</p>}
              {!f.pending && f.language && f.language !== language && f.health.length > 0 && (
                <p className="setup-ai">{t('setup.langHintCheck')}</p>
              )}
            </div>
            {(f.health.length > 0 || f.insights.length > 0) && (
              <FindingsSummary findings={f} busy={busy} onFix={(item, how) => fix(d.id, item, how)}
                details={<Link to={`/datasets/${d.id}?tab=rules`}>{t('setup.c.details')}</Link>} />
            )}
            {!f.pending && f.checked && !f.failed && f.insights.length === 0 && (
              <p className="setup-ai">{t('setup.c.noInsights')}</p>
            )}
          </section>
        )
      })}
      <div className="setup-footer">
        <span className="setup-section__sub">{t('setup.c.footer')}</span>
        <button type="button" className="btn btn-primary" onClick={onNext} disabled={waiting && !gaveUp}>
          {t('setup.next', { step: t('setup.step.dashboard') })}
        </button>
      </div>
    </div>
  )
}
