import type { ReactNode } from 'react'
import {
  ArrowDownUp, Bookmark, CheckCheck, Clock, Gauge, History, Languages, Layers, Link2, ListChecks, ListTree,
  MessageSquare, Pin, PinOff, SlidersHorizontal, Smartphone, Variable, type LucideIcon,
} from 'lucide-react'
import AiMascot from '../../components/ai/AiMascot'
import { useT, type MessageKey } from '../../i18n'

/** Every panel the builder's right side can show (v1's RightPanelMode). */
export type RailMode = 'default' | 'mobile' | 'selection' | 'sync' | 'bookmarks' | 'taborder' | 'performance' | 'reportrules'
  | 'parameters' | 'schedule' | 'review' | 'comments' | 'outline' | 'suggestions' | 'translations' | 'insights' | 'ask' | 'history'

export const AI_MODES: RailMode[] = ['ask', 'insights', 'suggestions']

type Item = { mode: RailMode; label: MessageKey; icon: LucideIcon | 'ai' }
/** The prototype's rail: Properties, then Build, AI, Collaborate, Quality and
 *  Publish. Every v1 panel has a place; the three AI panes share one button
 *  and switch by tabs inside. */
const RAIL: (Item | MessageKey)[] = [
  { mode: 'default', label: 'bd.rail.properties', icon: SlidersHorizontal },
  'bd.rail.build',
  { mode: 'outline', label: 'builder.pane.outline', icon: ListTree },
  { mode: 'selection', label: 'builder.pane.selection', icon: Layers },
  { mode: 'parameters', label: 'builder.pane.parameters', icon: Variable },
  { mode: 'bookmarks', label: 'builder.pane.bookmarks', icon: Bookmark },
  { mode: 'sync', label: 'builder.pane.sync', icon: Link2 },
  'bd.rail.ai',
  { mode: 'ask', label: 'bd.rail.aiBtn', icon: 'ai' },
  'bd.rail.collab',
  { mode: 'comments', label: 'builder.pane.comments', icon: MessageSquare },
  { mode: 'history', label: 'builder.pane.history', icon: History },
  'bd.rail.quality',
  { mode: 'review', label: 'builder.pane.review', icon: CheckCheck },
  { mode: 'performance', label: 'builder.pane.performance', icon: Gauge },
  { mode: 'taborder', label: 'builder.pane.taborder', icon: ArrowDownUp },
  { mode: 'reportrules', label: 'builder.pane.reportrules', icon: ListChecks },
  'bd.rail.publish',
  { mode: 'schedule', label: 'builder.pane.schedule', icon: Clock },
  { mode: 'translations', label: 'builder.pane.translations', icon: Languages },
  { mode: 'mobile', label: 'builder.pane.mobile', icon: Smartphone },
]

export const railLabel = (mode: RailMode): MessageKey => {
  if (AI_MODES.includes(mode)) return 'bd.rail.aiBtn'
  const it = RAIL.find((x): x is Item => typeof x !== 'string' && x.mode === mode)
  return it?.label ?? 'bd.rail.properties'
}
export const railIcon = (mode: RailMode): LucideIcon | 'ai' =>
  AI_MODES.includes(mode) ? 'ai' : (RAIL.find((x): x is Item => typeof x !== 'string' && x.mode === mode)?.icon ?? SlidersHorizontal)

/**
 * The builder's right rail (redesign 7e3): one icon per panel, grouped as
 * the prototype. v1 kept eight of these as words in a toolbar and the rest
 * behind "More panels". A press opens the panel; the open one is pressed.
 */
export function RightRail({ mode, pinned, onPick }: { mode: RailMode; pinned: boolean; onPick: (m: RailMode) => void }) {
  const t = useT()
  const on = (m: RailMode) => m === 'ask' ? AI_MODES.includes(mode) : m === 'default' ? mode === 'default' || pinned : mode === m
  return (
    <nav className="dl-bd-rail" aria-label={t('bd.rail.aria')}>
      {RAIL.map((x, i) => typeof x === 'string'
        ? <span key={i} className="gl" role="separator" aria-label={t(x)} />
        : (
          <button key={x.mode} type="button" className="dl-bd-ri" aria-pressed={on(x.mode)} aria-label={t(x.label)} title={t(x.label)}
            onClick={() => onPick(x.mode)}>
            {x.icon === 'ai' ? <span className="av" aria-hidden><AiMascot size={18} /></span> : <x.icon size={18} aria-hidden />}
          </button>
        ))}
    </nav>
  )
}

/** A rail panel's head: its icon and name, and on Properties the pin that
 *  keeps it open beside the next panel. */
export function PanelHead({ mode, pinned, onPin, extra }: { mode: RailMode; pinned?: boolean; onPin?: () => void; extra?: ReactNode }) {
  const t = useT()
  const Icon = railIcon(mode)
  return (
    <div className="dl-bd-ph">
      {Icon === 'ai' ? <span className="av" aria-hidden><AiMascot size={15} /></span> : <Icon size={16} aria-hidden />}
      <h2>{t(railLabel(mode))}</h2>
      {extra}
      {onPin && (
        <button type="button" className="dl-bd-ib" aria-pressed={!!pinned} onClick={onPin}
          aria-label={t(pinned ? 'bd.rail.unpin' : 'bd.rail.pin')} title={t(pinned ? 'bd.rail.unpin' : 'bd.rail.pin')}>
          {pinned ? <PinOff size={15} aria-hidden /> : <Pin size={15} aria-hidden />}
        </button>
      )}
    </div>
  )
}

/** Ask / Insights / Suggest inside the one AI panel. */
export function AiTabs({ mode, onPick }: { mode: RailMode; onPick: (m: RailMode) => void }) {
  const t = useT()
  return (
    <div className="dl-bd-aitabs" role="tablist" aria-label={t('bd.rail.aiBtn')}>
      {AI_MODES.map(m => (
        <button key={m} type="button" role="tab" aria-selected={mode === m} onClick={() => onPick(m)}>
          {t(`builder.pane.${m}` as MessageKey)}
        </button>
      ))}
    </div>
  )
}
