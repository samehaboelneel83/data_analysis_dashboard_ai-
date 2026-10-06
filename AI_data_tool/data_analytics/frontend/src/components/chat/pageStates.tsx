import { useState, type ReactNode } from 'react'
import { ArrowRight, Check, Pencil, Sparkles } from 'lucide-react'
import { useT } from '../../i18n'
import { localDigits } from '../../lib/arabicFormats'

/**
 * The Ask AI page's own states (redesign 4b): the first run of a thread and
 * the clarification card. The builder's copilot mount keeps v1's.
 */

/** "Ask Enrolments 2025 anything": four starters and how it works. */
export function FirstRun({ name, rows, starters, onAsk, busy }: {
  name?: string
  rows?: number | null
  starters: string[]
  onAsk: (q: string) => void
  busy: boolean
}) {
  const t = useT()
  return (
    <section className="dl-first" aria-labelledby="dl-first-title">
      {name && (
        <p className="dl-first__eyebrow" dir="auto">
          {rows != null ? t('first.eyebrow', { name, rows: localDigits(rows.toLocaleString('en-US')) }) : name}
        </p>
      )}
      <h2 id="dl-first-title" className="dl-first__title" dir="auto">
        {name ? t('first.title', { name }) : t('first.titlePlain')}
      </h2>
      <p className="dl-first__sub">{t('first.sub')}</p>
      {starters.length > 0 && (
        <>
          <p className="dl-first__label">{t('first.try')}</p>
          <div className="dl-first__starters" role="group" aria-label={t('ask.suggested')}>
            {starters.slice(0, 4).map(s => (
              <button key={s} type="button" className="dl-first__starter" disabled={busy} onClick={() => onAsk(s)}>
                <Sparkles size={14} aria-hidden /> <span dir="auto">{s}</span>
              </button>
            ))}
          </div>
        </>
      )}
      <ul className="dl-first__tiles">
        {(['words', 'see', 'keep'] as const).map(k => (
          <li key={k}><strong>{t(`first.tile.${k}`)}</strong><span>{t(`first.tile.${k}.sub`)}</span></li>
        ))}
      </ul>
    </section>
  )
}

/** Terms the reply sets apart -- **bold**, `code`, "quoted" -- that name one
 *  of the dataset's columns (AB3). Case and spaces/underscores are ignored;
 *  the dataset's own spelling is returned, in the reply's order, once each. */
export function columnsMentioned(text: string, columns: string[]): string[] {
  const norm = (s: string) => s.trim().toLowerCase().replace(/[\s_-]+/g, '_')
  const byNorm = new Map(columns.map(c => [norm(c), c]))
  const out: string[] = []
  const re = /\*\*([^*]+)\*\*|`([^`]+)`|"([^"]+)"|“([^”]+)”|«([^»]+)»|'([^']+)'/g
  for (const m of text.matchAll(re)) {
    const term = m.slice(1).find(Boolean)
    const col = term ? byNorm.get(norm(term)) : undefined
    if (col && !out.includes(col)) out.push(col)
  }
  return out
}

export interface ClarifyOption { send: string; label: ReactNode; sub?: string }

/** A question back, with ways to answer it: the columns it names, the
 *  server's own choices, or the person's words. Once answered it folds to
 *  one line: "Needs one detail · You chose …". */
export function ClarifyCard({ body, options, onChoose, busy, chosen, open }: {
  body: ReactNode
  options: ClarifyOption[]
  onChoose: (reply: string) => void
  busy: boolean
  /** What was picked, when the next question answered this one. */
  chosen?: ReactNode
  /** The latest turn: offers "Or type your answer". */
  open: boolean
}) {
  const t = useT()
  const [own, setOwn] = useState('')
  if (chosen) {
    return (
      <p className="dl-clar3__done" data-testid="clarify-resolved">
        <span className="dl-clar3__tick" aria-hidden><Check size={11} /></span>
        {t('clar3.needs')} · {t('clar3.chose')} {chosen}
      </p>
    )
  }
  return (
    <div className="dl-clar3" data-testid="clarify-card">
      <p className="dl-clar3__top">
        <span className="dl-clar3__tag"><Sparkles size={12} aria-hidden /> {t('clar3.needs')}</span>
        <span className="dl-clar3__how">{t('clar3.how')}</span>
      </p>
      {body}
      {options.length > 0 && (
        <div className="dl-clar3__options" role="group" aria-label={t('clar3.ways')}>
          {options.map((o, i) => (
            <button key={o.send} type="button" className="dl-clar3__option" disabled={busy} onClick={() => onChoose(o.send)}>
              <span className="dl-clar3__n" aria-hidden>{localDigits(String(i + 1))}</span>
              <span className="dl-clar3__text">
                <strong>{o.label}</strong>
                {o.sub && <span>{o.sub}</span>}
              </span>
              <ArrowRight size={15} aria-hidden className="dl-flip" />
            </button>
          ))}
        </div>
      )}
      {open && (
        <form className="dl-clar3__own" onSubmit={e => { e.preventDefault(); if (own.trim()) { onChoose(own.trim()); setOwn('') } }}>
          <Pencil size={13} aria-hidden />
          <input value={own} onChange={e => setOwn(e.target.value)} dir="auto" disabled={busy}
            placeholder={t('clar3.own')} aria-label={t('clar3.own')} />
        </form>
      )}
    </div>
  )
}
