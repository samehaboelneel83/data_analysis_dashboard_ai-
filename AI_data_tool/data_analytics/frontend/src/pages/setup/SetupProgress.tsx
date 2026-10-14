import { Check } from 'lucide-react'
import { useT, type MessageKey } from '../../i18n'
import { localDigits } from '../../lib/arabicFormats'
import type { SetupStep } from '../../services/api'

export const STEPS: { key: Exclude<SetupStep, 'done'>; label: MessageKey }[] = [
  { key: 'understand', label: 'setup.step.understand' },
  { key: 'data', label: 'setup.step.data' },
  { key: 'check', label: 'setup.step.check' },
  { key: 'dashboard', label: 'setup.step.dashboard' },
]

/**
 * Where the reader is in the setup. A step already reached can be opened
 * again (going back to correct a description is normal); a step not reached
 * yet cannot, because it builds on the ones before it.
 */
export default function SetupProgress({ reached, current, onOpen }: {
  /** The furthest step reached; 'done' means all four. */
  reached: SetupStep
  /** The step on screen. */
  current: Exclude<SetupStep, 'done'>
  onOpen: (step: Exclude<SetupStep, 'done'>) => void
}) {
  const t = useT()
  const furthest = reached === 'done' ? STEPS.length : STEPS.findIndex(s => s.key === reached)
  return (
    <nav aria-label={t('setup.progress')} className="setup-progress">
      <ol>
        {STEPS.map((s, i) => {
          const isCurrent = s.key === current
          const done = i < furthest
          const open = i <= furthest
          return (
            <li key={s.key} className={`setup-progress__step${isCurrent ? ' is-current' : ''}${done ? ' is-done' : ''}`}>
              <button type="button" disabled={!open} aria-current={isCurrent ? 'step' : undefined}
                onClick={() => onOpen(s.key)}>
                <span className="setup-progress__dot" aria-hidden="true">
                  {done && !isCurrent ? <Check size={12} /> : localDigits(String(i + 1))}
                </span>
                <span className="setup-progress__label">{t(s.label)}</span>
              </button>
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
