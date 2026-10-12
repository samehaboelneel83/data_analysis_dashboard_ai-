import type { ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'
import { useT } from '../../i18n'
import AskIllustration from './AskIllustration'

/**
 * The centred hero (step 10 design: `.hero`): the picture, a headline whose
 * last word is in the accent, a subtitle, then the numbered step and whatever
 * the step holds (the picker, or the suggestion cards). `small` is the
 * dataset-picked version, with a smaller picture. Without a step it is just
 * the picture, the headline and the subtitle (the empty page's inline-end
 * column, where Step 1 sits with the data chooser).
 */
export default function AskHero({ id, title, sub, step, stepLabel, small, eyebrow, facts, children }: {
  id: string
  title: string
  sub: ReactNode
  step?: number
  stepLabel?: string
  small?: boolean
  /** A small line over the headline (the empty page: what this is, and how much data there is). */
  eyebrow?: ReactNode
  /** Short facts under the subtitle, each with its icon. */
  facts?: { icon: LucideIcon; text: string }[]
  children?: ReactNode
}) {
  const t = useT()
  const words = title.trim().split(/\s+/)
  const last = words.pop()
  return (
    <section className={`dl-hero${small ? ' dl-hero--sm' : ''}${facts ? ' dl-hero--lg' : ''}`} aria-labelledby={id}>
      <AskIllustration small={small} />
      {eyebrow && <p className="dl-hero__eyebrow">{eyebrow}</p>}
      <h1 id={id} className="dl-hero__title">
        {words.join(' ')}{words.length ? ' ' : ''}<span className="dl-hero__accent">{last}</span>
      </h1>
      <p className="dl-hero__sub">{sub}</p>
      {facts && facts.length > 0 && (
        <ul className="dl-hero__facts">
          {facts.map(({ icon: Icon, text }) => (
            <li key={text}><span className="dl-hero__fact-ic" aria-hidden><Icon size={15} /></span>{text}</li>
          ))}
        </ul>
      )}
      {step != null && (
        <div className="dl-hero__step">
          <span className="dl-hero__stn">{t('ask2.step', { n: step })}</span>{stepLabel}
        </div>
      )}
      {children}
    </section>
  )
}
