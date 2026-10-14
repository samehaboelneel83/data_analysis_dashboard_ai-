/**
 * Plain first, details behind a button, never removed (guided setup, D6).
 *
 * The quality report used to say `nan 73%`, "1,567 outliers" and "-1 looks
 * like a code for unknown": correct, and of no use to someone who does not
 * already know what to do about it. Each line here answers three questions in
 * order -- what is wrong, why it matters, what to do -- and the full report
 * the line was drawn from stays one click away in `details`.
 */
import { useId, useState, type ReactNode } from 'react'
import { AlertCircle, AlertTriangle, CheckCircle2, Lightbulb, Info, ChevronDown } from 'lucide-react'
import { useT } from '../../i18n'
import { useAlwaysShowDetails } from '../../lib/detailsPreference'
import './plainSummary.css'

export type PlainTone = 'problem' | 'warning' | 'good' | 'insight' | 'info'

export interface PlainItem {
  id: string
  tone: PlainTone
  /** What is true, in one short sentence. */
  what: string
  /** Why it matters for the reader's work. */
  why?: string
  /** What to do about it. */
  todo?: string
  action?: { label: string; onClick: () => void; busy?: boolean; done?: boolean }
  /** A second, quieter choice (e.g. "Warn me on every refresh"). */
  secondary?: { label: string; onClick: () => void; busy?: boolean; done?: boolean }
}

const ICON = {
  problem: AlertCircle,
  warning: AlertTriangle,
  good: CheckCircle2,
  insight: Lightbulb,
  info: Info,
} as const

export default function PlainSummary({ title, lead, items, details, detailsLabel, empty }: {
  title?: string
  /** One sentence above the lines: the summary of the summary. */
  lead?: string
  items: PlainItem[]
  /** The full report. Rendered only when opened, so a heavy table costs nothing until asked for. */
  details?: ReactNode
  detailsLabel?: string
  /** Shown instead of the list when there is nothing to say. */
  empty?: string
}) {
  const t = useT()
  const [always] = useAlwaysShowDetails()
  const [open, setOpen] = useState<boolean | null>(null)
  const shown = open ?? always
  const panelId = useId()

  return (
    <section className="plain-summary card">
      {title && <h3 className="plain-summary__title">{title}</h3>}
      {lead && <p className="plain-summary__lead">{lead}</p>}
      {items.length === 0 && empty && <p className="plain-summary__empty">{empty}</p>}
      {items.length > 0 && (
        <ul className="plain-summary__list">
          {items.map(item => {
            const Icon = ICON[item.tone]
            return (
              <li key={item.id} className={`plain-summary__item plain-summary__item--${item.tone}`}>
                <Icon size={16} className="plain-summary__icon" aria-hidden="true" />
                <div className="plain-summary__body">
                  <p className="plain-summary__what">{item.what}</p>
                  {item.why && <p className="plain-summary__why">{item.why}</p>}
                  {item.todo && (
                    <p className="plain-summary__todo">
                      <span className="plain-summary__todo-label">{t('plain.todo')}</span> {item.todo}
                    </p>
                  )}
                </div>
                {(item.action || item.secondary) && (
                  <div className="plain-summary__actions">
                    {item.action && (
                      <button type="button" className="btn btn-primary btn-sm plain-summary__action"
                        onClick={item.action.onClick}
                        disabled={item.action.busy || item.action.done}>
                        {item.action.done ? t('plain.done') : item.action.label}
                      </button>
                    )}
                    {item.secondary && (
                      <button type="button" className="btn btn-ghost btn-sm plain-summary__action"
                        onClick={item.secondary.onClick}
                        disabled={item.secondary.busy || item.secondary.done}>
                        {item.secondary.done ? t('plain.done') : item.secondary.label}
                      </button>
                    )}
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      )}
      {details && (
        <>
          <button type="button" className="plain-summary__toggle"
            aria-expanded={shown} aria-controls={panelId}
            onClick={() => setOpen(!shown)}>
            <ChevronDown size={14} aria-hidden="true"
              className={shown ? 'plain-summary__chevron plain-summary__chevron--open' : 'plain-summary__chevron'} />
            {shown ? t('plain.hideDetails') : (detailsLabel ?? t('plain.showDetails'))}
          </button>
          {shown && <div id={panelId} className="plain-summary__details">{details}</div>}
        </>
      )}
    </section>
  )
}
