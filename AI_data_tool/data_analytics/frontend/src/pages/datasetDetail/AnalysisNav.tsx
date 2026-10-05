import { useEffect, useState } from 'react'
import { useT, type MessageKey } from '../../i18n'
import { localDigits } from '../../lib/arabicFormats'
import { analysisCatalogueApi } from '../../services/api'

/**
 * The Analysis tab's question list (redesign step 3c): the registry's
 * analyses offered as the questions people ask, grouped the way the board
 * groups them. Built-in questions open the automatic panels (key influencers,
 * segments, patterns, insights, anomalies); the rest open the registry runner
 * limited to their analyses; "All N analyses" opens the full runner.
 */

export type AnalysisPick =
  | 'drives' | 'inputs' | 'groups' | 'related' | 'alike' | 'together'
  | 'insights' | 'unusual' | 'predict' | 'goal' | 'text' | 'all'

type Question = { pick: AnalysisPick; analyses?: string[]; importOnly?: boolean; needsNumeric?: boolean }

export const QUESTION_GROUPS: { key: string; items: Question[] }[] = [
  { key: 'explain', items: [{ pick: 'drives' }, { pick: 'inputs', analyses: ['explain_response'] }] },
  { key: 'compare', items: [
    { pick: 'groups', analyses: ['compare_groups', 'pairwise_comparisons'] },
    { pick: 'related', analyses: ['correlation_test', 'test_independence'] },
  ] },
  { key: 'patterns', items: [
    { pick: 'alike', importOnly: true }, { pick: 'together' },
    // v1's automatic insights and anomaly inspection: not on the board's
    // list, kept so nothing v1 offered disappears.
    { pick: 'insights' }, { pick: 'unusual', importOnly: true, needsNumeric: true },
  ] },
  { key: 'predict', items: [
    { pick: 'predict', analyses: ['regression', 'glm_logistic', 'decision_tree', 'automated_prediction', 'mixed_model', 'survival'] },
    { pick: 'goal', analyses: ['forecast_goal', 'goal_seek', 'forecast_scenario'] },
  ] },
  { key: 'text', items: [{ pick: 'text', analyses: ['text_topics', 'text_sentiment'] }] },
]

/** The registry analyses a question runs, or undefined for a built-in panel. */
export const analysesFor = (pick: AnalysisPick): string[] | undefined =>
  QUESTION_GROUPS.flatMap(g => g.items).find(q => q.pick === pick)?.analyses

/** Deep-link anchors (from the Insights hub) and the question they open. */
export const HASH_PICK: Record<string, AnalysisPick> = {
  influencers: 'drives', segment: 'alike', associations: 'together', insights: 'insights', anomalies: 'unusual',
}

export default function AnalysisNav({ pick, onPick, live, hasNumeric }: {
  pick: AnalysisPick
  onPick: (p: AnalysisPick) => void
  live: boolean
  hasNumeric: boolean
}) {
  const t = useT()
  const [count, setCount] = useState<number | null>(null)
  useEffect(() => {
    let on = true
    Promise.resolve().then(() => analysisCatalogueApi?.registry?.())
      .then(all => { if (on && all) setCount(all.filter(a => a.runnable).length) }).catch(() => {})
    return () => { on = false }
  }, [])
  return (
    <nav className="dl-an3__nav" aria-label={t('an3.title')}>
      <h2>{t('an3.title')}</h2>
      {QUESTION_GROUPS.map(g => {
        const items = g.items.filter(q => !(q.importOnly && live) && !(q.needsNumeric && !hasNumeric))
        if (!items.length) return null
        return (
          <div key={g.key} className="dl-an3__group">
            <h3>{t(`an3.g.${g.key}` as MessageKey)}</h3>
            {items.map(q => (
              <button key={q.pick} type="button" aria-current={pick === q.pick || undefined}
                className="dl-an3__q" onClick={() => onPick(q.pick)}>
                <strong>{t(`an3.q.${q.pick}` as MessageKey)}</strong>
                <span>{t(`an3.s.${q.pick}` as MessageKey)}</span>
              </button>
            ))}
          </div>
        )
      })}
      <button type="button" className="dl-an3__all" aria-current={pick === 'all' || undefined} onClick={() => onPick('all')}>
        {count != null ? t('an3.all', { n: localDigits(String(count)) }) : t('an3.allPlain')}
      </button>
    </nav>
  )
}
