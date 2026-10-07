import type { ReactNode } from 'react'
import { Lightbulb, MessageCircle, WandSparkles, X } from 'lucide-react'
import AiMascot from '../../components/ai/AiMascot'
import { useT, type MessageKey } from '../../i18n'

/**
 * The reader's AI panel (redesign 7d): Ask, Insights and, for editors,
 * Suggest charts, beside the dashboard in view mode and in Present.
 *
 * A shell only: the builder hands in the panes it already has -- ChatPane on
 * the dashboard's datasets (one thread per dashboard, locked with one line
 * while the model server is unreachable), InsightsPane (its narrative falls
 * back to a template, so it works offline) and SuggestionsPane. Nothing here
 * reads the page's widgets: the agent takes datasets, not widgets, so "N
 * widgets read" and "Based on" chips are left out (PLAN.md).
 */

export type AssistTab = 'ask' | 'insights' | 'suggest'

export default function ViewAssist({ tab, onTab, onClose, context, ask, insights, suggest }: {
  tab: AssistTab
  onTab: (t: AssistTab) => void
  onClose: () => void
  /** "Dashboard · Page", under the title. */
  context: string
  ask: ReactNode
  insights: ReactNode
  /** Editors only: adding a chart changes the page. */
  suggest?: ReactNode
}) {
  const t = useT()
  const tabs: { k: AssistTab; icon: typeof MessageCircle; label: MessageKey }[] = [
    { k: 'ask', icon: MessageCircle, label: 'vw.ai.ask' },
    { k: 'insights', icon: Lightbulb, label: 'vw.ai.insights' },
    ...(suggest ? [{ k: 'suggest' as AssistTab, icon: WandSparkles, label: 'vw.ai.suggest' as MessageKey }] : []),
  ]
  const current = tab === 'suggest' && !suggest ? 'ask' : tab
  return (
    <aside className="dl-vw-ai" aria-labelledby="dl-vw-ai-t" data-testid="view-assist">
      <div className="dl-vw-ai__h">
        <span className="dl-vw-av lg" aria-hidden><AiMascot size={24} alive /></span>
        <div className="tt">
          <h2 id="dl-vw-ai-t">{t('nav.askAi')}</h2>
          <div className="dl-vw-ai__ctx" title={context}><bdi>{context}</bdi></div>
        </div>
        <button type="button" className="dl-vw-ai__x" onClick={onClose} aria-label={t('hm.close')} title={t('hm.close')}><X size={16} aria-hidden /></button>
      </div>
      <div className="dl-vw-ai__tabs" role="tablist" aria-label={t('nav.askAi')}>
        {tabs.map(x => (
          <button key={x.k} type="button" role="tab" aria-selected={current === x.k} onClick={() => onTab(x.k)}>
            <x.icon size={14} aria-hidden />{t(x.label)}
          </button>
        ))}
      </div>
      <div className="dl-vw-ai__b" role="tabpanel">
        {current === 'ask' && ask}
        {current === 'insights' && insights}
        {current === 'suggest' && suggest}
      </div>
    </aside>
  )
}
