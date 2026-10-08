import { Link } from 'react-router-dom'
import { Compass } from 'lucide-react'
import { useT } from '../../i18n'
import { localDigits } from '../../lib/arabicFormats'
import type { SetupJourney } from '../../services/api'
import { STEPS } from '../setup/SetupProgress'

/**
 * "Continue: cars database, step 2 of 4" (guided setup, plan 1c).
 *
 * Shown only while a setup is unfinished. Optional by nature: when the list
 * cannot be read the section stays away rather than claiming there is
 * nothing to continue.
 */
export default function SetupContinue({ journeys }: { journeys: SetupJourney[] | null }) {
  const t = useT()
  if (!journeys?.length) return null
  return (
    <section className="hm-sec" aria-labelledby="hm-setup">
      <h2 id="hm-setup" className="hm-setup__title">{t('setup.home.title')}</h2>
      <ul className="hm-setup">
        {journeys.slice(0, 3).map(j => {
          const step = STEPS.find(s => s.key === j.step)
          return (
            <li key={j.id} className="hm-setup__item">
              <Compass size={16} aria-hidden="true" />
              <span className="hm-setup__text">
                {t('setup.home.item', {
                  name: j.source.name, n: localDigits(String(j.position)), total: localDigits(String(j.total)),
                  step: step ? t(step.label) : '',
                })}
              </span>
              <Link className="btn btn-sm btn-primary" to={`/setup/${j.source.id}`}
                aria-label={`${t('setup.home.continue')}: ${j.source.name}`}>
                {t('setup.home.continue')}
              </Link>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
