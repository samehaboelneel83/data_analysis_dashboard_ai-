/**
 * Guided setup: Understand -> Choose data -> Check & discover -> Dashboard
 * (docs/guided-setup/PLAN.md).
 *
 * One page per connection and person. The step reached is kept on the
 * server (a "journey"), so the reader can leave and come back; Home offers
 * to continue. Nothing here is a separate store: each step saves into the
 * ordinary objects (descriptions, datasets, a dashboard) the rest of the
 * app already shows.
 */
import { useCallback, useEffect, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { useT } from '../i18n'
import { localDigits } from '../lib/arabicFormats'
import { setupApi, type SetupJourney, type SetupStep } from '../services/api'
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

  const load = useCallback(async () => {
    try { setError(null); setJourney(await setupApi.get(sourceId)) } catch (e) { setError(e) }
  }, [sourceId])
  useEffect(() => { load() }, [load])

  if (error) return <LoadError what={t('setup.what')} error={error} onRetry={load} />
  if (!journey) return <LoadingState />

  const reached: SetupStep = journey.step
  const asked = params.get('step') as Shown | null
  const reachedIndex = reached === 'done' ? STEPS.length - 1 : STEPS.findIndex(s => s.key === reached)
  // ?step= opens a step already reached; anything else opens the furthest one.
  const shown: Shown = asked && STEPS.findIndex(s => s.key === asked) <= reachedIndex && STEPS.some(s => s.key === asked)
    ? asked : STEPS[reachedIndex].key

  function open(step: Shown) {
    setParams(step === STEPS[reachedIndex].key ? {} : { step }, { replace: true })
  }

  async function advance(from: Shown) {
    const i = STEPS.findIndex(s => s.key === from)
    const next: SetupStep = i + 1 < STEPS.length ? STEPS[i + 1].key : 'done'
    // Going forward from an earlier step never moves the journey back.
    const furthest = reached === 'done' ? STEPS.length : STEPS.findIndex(s => s.key === reached)
    if (i + 1 > furthest) setJourney(await setupApi.update(sourceId, { step: next }))
    setParams(next === 'done' ? {} : { step: next }, { replace: true })
  }

  const position = STEPS.findIndex(s => s.key === shown) + 1

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

      <SetupProgress reached={reached} current={shown} onOpen={open} />

      {shown === 'understand' && <UnderstandStep sourceId={sourceId} onNext={() => advance('understand')} />}
      {shown === 'data' && (
        <ChooseDataStep sourceId={sourceId} onDone={async ids => {
          setJourney(await setupApi.update(sourceId, { dataset_ids: ids }))
          await advance('data')
        }} />
      )}
      {shown === 'check' && <CheckStep sourceId={sourceId} onNext={() => advance('check')} onBack={() => open('data')} />}
      {shown === 'dashboard' && <DashboardStep sourceId={sourceId} onBack={() => open('data')} />}
    </div>
  )
}
