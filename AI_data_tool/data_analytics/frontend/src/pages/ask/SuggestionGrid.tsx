import { BarChart3, Columns3, Hash, LineChart, List, Rows3, Sigma, Table2, TrendingUp, Trophy, type LucideIcon } from 'lucide-react'
import { useT } from '../../i18n'
import type { SuggestionCard, SuggestionIcon } from './suggestions'

const ICON: Record<SuggestionIcon, LucideIcon> = {
  total: BarChart3, top: Trophy, trend: LineChart, average: Sigma, highest: TrendingUp,
  count: Hash, rows: Rows3, summary: List, columns: Columns3, tables: Table2,
}

/**
 * Step 2's suggestion cards (step 10 design: `.sug` / `.sg`): the question,
 * a picture of the kind of answer, and the dataset's own columns it uses, in
 * mono and left to right. A card is sent exactly like a typed question.
 */
export default function SuggestionGrid({ cards, onAsk, disabled, disabledReason }: {
  cards: SuggestionCard[]
  onAsk: (question: string) => void
  disabled?: boolean
  /** Why the cards are disabled (e.g. new questions are paused), shown where the user clicks. */
  disabledReason?: string
}) {
  const t = useT()
  if (!cards.length) return null
  return (
    <div className="dl-sug" role="group" aria-label={t('ask2.sug.aria')}>
      {cards.map(c => {
        const Icon = ICON[c.icon]
        return (
          <button key={c.text} type="button" className="dl-sug__card" disabled={disabled}
            title={disabled ? disabledReason : undefined} onClick={() => onAsk(c.text)}>
            <span className="dl-sug__icon" aria-hidden><Icon size={16} /></span>
            <b dir="auto">{c.text}</b>
            {c.columns.length > 0 && <small dir="ltr">{c.columns.join(' · ')}</small>}
          </button>
        )
      })}
    </div>
  )
}
