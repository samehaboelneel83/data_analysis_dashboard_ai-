/**
 * Guided setup: Understand -> Choose data -> Check & discover -> Dashboard
 * (docs/guided-setup/PLAN.md, PLAN_V2.md).
 *
 * One page per connection and person. Understand is done once; steps 2-4 are
 * an ANALYSIS (a "flow"), and a person can run several on the same
 * connection -- each with its own request, datasets and dashboard -- side
 * by side (`?flow=`). The step reached is kept on the server, so the reader
 * can leave and come back; Home offers to continue. Nothing here is a
 * separate store: each step saves into the ordinary objects (descriptions,
 * datasets, a dashboard) the rest of the app already shows.
 */
import { useCallback, useEffect, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import toast from 'react-hot-toast'
import { Check, Plus } from 'lucide-react'
import { useT } from '../i18n'
import { localDigits } from '../lib/arabicFormats'
import { setupApi, type SetupFlow, type SetupJourney, type SetupStep } from '../services/api'
import LoadError from '../components/ui/LoadError'
import LoadingState from '../components/ui/LoadingState'
import SetupProgress, { STEPS } from './setup/SetupProgress'
import UnderstandStep from './setup/UnderstandStep'
import ChooseDataStep from './setup/ChooseDataStep'
import CheckStep from './setup/CheckStep'
import DashboardStep from './setup/DashboardStep'
import './setup/setup.css'

type Shown = Exclude<SetupStep, 'done'>

export default function Setup() {
  const t = useT()
  const { id } = useParams()
  const sourceId = Number(id)
  const [params, setParams] = useSearchParams()
  const [journey, setJourney] = useState<SetupJourney | null>(null)
  const [error, setError] = useState<unknown>(null)
  const asked = params.get('flow')
  const askedFlow = asked && Number.isFinite(Number(asked)) ? Number(asked) : undefined

  const load = useCallback(async () => {
    try { setError(null); setJourney(await setupApi.get(sourceId, askedFlow)) } catch (e) { setError(e) }
  }, [sourceId, askedFlow])
  useEffect(() => { load() }, [load])

  if (error) return <LoadError what={t('setup.what')} error={error} onRetry={load} />
  if (!journey) return <LoadingState />

  const flow = journey.flow_id ?? undefined
  const flows = journey.flows ?? []
  const reached: SetupStep = journey.step
  const askedStep = params.get('step') as Shown | null
  const reachedIndex = reached === 'done' ? STEPS.length - 1 : STEPS.findIndex(s => s.key === reached)
  // ?step= opens a step already reached; anything else opens the furthest one.
  const shown: Shown = askedStep && STEPS.findIndex(s => s.key === askedStep) <= reachedIndex && STEPS.some(s => s.key === askedStep)
    ? askedStep : STEPS[reachedIndex].key

  /** The address of a step of an analysis: only what differs from the default is written. */
  function go(step: Shown | null, flowId: number | undefined = flow) {
    const next: Record<string, string> = {}
    if (flowId != null && flows.length > 1) next.flow = String(flowId)
    if (step) next.step = step
    setParams(next, { replace: true })
  }

  function open(step: Shown) {
    go(step === STEPS[reachedIndex].key ? null : step)
  }

  async function advance(from: Shown) {
    const i = STEPS.findIndex(s => s.key === from)
    const next: SetupStep = i + 1 < STEPS.length ? STEPS[i + 1].key : 'done'
    // Going forward from an earlier step never moves the journey back.
    const furthest = reached === 'done' ? STEPS.length : STEPS.findIndex(s => s.key === reached)
    if (i + 1 > furthest) setJourney(await setupApi.update(sourceId, { step: next }, flow))
    go(next === 'done' ? null : next)
  }

  async function newFlow() {
    try {
      const j = await setupApi.startFlow(sourceId)
      setJourney(j)
      setParams(j.flow_id != null ? { flow: String(j.flow_id) } : {}, { replace: true })
    } catch { toast.error(t('setup.f.newFailed')) }
  }

  function openFlow(f: SetupFlow) {
    setJourney(null)
    setParams({ flow: String(f.id) }, { replace: true })
  }

  const position = STEPS.findIndex(s => s.key === shown) + 1
  const pastUnderstand = reached !== 'understand'

  return (
    <div className="setup-page">
      <header className="dl-page-head">
        <div>
          <h1 className="dl-page-head__title">{t('setup.heading', { name: journey.source.name })}</h1>
          <p className="dl-page-head__sub">
            {t('setup.stepOf', { n: localDigits(String(position)), total: localDigits(String(STEPS.length)) })}
            {' · '}{t('setup.sub')}
          </p>
        </div>
      </header>

      {pastUnderstand && (
        <nav className="setup-flows" aria-label={t('setup.f.label')}>
          <span className="setup-section__sub">{t('setup.f.title')}</span>
          <ul>
            {flows.map((f, i) => {
              const name = f.name || t('setup.f.unnamed', { n: localDigits(String(i + 1)) })
              const done = f.step === 'done'
              return (
                <li key={f.id}>
                  <button type="button" className={`setup-flow${f.id === flow ? ' is-current' : ''}`}
                    aria-current={f.id === flow ? 'true' : undefined} title={name}
                    onClick={() => { if (f.id !== flow) openFlow(f) }}>
                    {done && <Check size={12} aria-hidden="true" />}
                    <span className="setup-flow__name">{name}</span>
                    <span className="setup-flow__step">
                      {done ? t('setup.f.done')
                        : t('setup.f.stepOf', { n: localDigits(String(f.position)), total: localDigits(String(STEPS.length)) })}
                    </span>
                  </button>
                </li>
              )
            })}
            <li>
              <button type="button" className="setup-flow setup-flow--new" onClick={newFlow} title={t('setup.f.newHint')}>
                <Plus size={13} aria-hidden="true" /> {t('setup.f.new')}
              </button>
            </li>
          </ul>
        </nav>
      )}

      <SetupProgress reached={reached} current={shown} onOpen={open} />

      {shown === 'understand' && <UnderstandStep sourceId={sourceId} onNext={() => advance('understand')} />}
      {shown === 'data' && (
        <ChooseDataStep key={flow} sourceId={sourceId} flow={flow} onDone={async (ids, created) => {
          setJourney(await setupApi.update(sourceId, { dataset_ids: ids, created_ids: created }, flow))
          await advance('data')
        }} />
      )}
      {shown === 'check' && (
        <CheckStep key={flow} sourceId={sourceId} flow={flow} onNext={() => advance('check')} onBack={() => open('data')} />
      )}
      {shown === 'dashboard' && (
        <DashboardStep key={flow} sourceId={sourceId} flow={flow} onBack={() => open('data')} onNewFlow={newFlow} />
      )}
    </div>
  )
}
