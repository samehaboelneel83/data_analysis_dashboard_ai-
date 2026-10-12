import { useRef } from 'react'
import { Info, MessageSquare, PanelRightClose, PanelRightOpen, Pencil, SquarePen, Trash2, X } from 'lucide-react'
import type { AgentConversation } from '../../services/api'
import { useT } from '../../i18n'
import { localDigits } from '../../lib/arabicFormats'
import { fmtDate, fmtTime } from './dates'

/**
 * History (step 10, Part D; design `.hist`): the threads held about the
 * chosen data, grouped Today / Earlier, with "New chat" on top and a line at
 * the foot saying how they are kept. It stands on the inline end, 288px; the
 * page folds it away (the choice is remembered) and, below 1180px, shows it
 * as an overlay.
 *
 * Each thread shows its title and when it was created -- the time today, the
 * date before. The list has no last-activity time and no failed flag (backend
 * rows), so neither is shown. Rename and Delete appear on the row in hand.
 *
 * `scope` is what is being asked about: nothing yet (the empty page: "Pick a
 * dataset…", and New chat is off), a dataset or a connection.
 */

function sameDay(a: Date, b: Date) {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate()
}
function when(iso?: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (isNaN(d.getTime())) return ''
  return sameDay(d, new Date())
    ? fmtTime(d)
    : fmtDate(d, { month: 'short', day: 'numeric' })
}

export default function HistoryPanel({
  conversations, selected, onSelect, onNew, editing, onEdit, onSave, onCancelEdit, onDelete,
  collapsed, onToggleCollapsed, mobileOpen, onCloseMobile, scope = 'dataset',
}: {
  conversations: AgentConversation[]
  selected: number | null | undefined
  onSelect: (id: number) => void
  onNew: () => void
  editing: { id: number; title: string } | null
  onEdit: (e: { id: number; title: string } | null) => void
  onSave: () => void
  onCancelEdit: () => void
  onDelete: (c: AgentConversation) => void
  collapsed: boolean
  onToggleCollapsed: () => void
  mobileOpen: boolean
  onCloseMobile: () => void
  scope?: 'none' | 'dataset' | 'source'
}) {
  const t = useT()
  const panelRef = useRef<HTMLElement>(null)
  const today = new Date()
  const groups: { label: string; items: AgentConversation[] }[] = []
  const todays = conversations.filter(c => c.created_at && sameDay(new Date(c.created_at), today))
  const earlier = conversations.filter(c => !todays.includes(c))
  if (todays.length) groups.push({ label: t('ask.hist.today'), items: todays })
  if (earlier.length) groups.push({ label: t('ask.hist.earlier'), items: earlier })

  const cls = ['dl-hist']
  if (collapsed) cls.push('dl-hist--collapsed')
  if (mobileOpen) cls.push('dl-hist--open')

  return (
    <>
      {mobileOpen && <div className="dl-hist__scrim" onClick={onCloseMobile} aria-hidden />}
      <aside ref={panelRef} className={cls.join(' ')} aria-label={t('ask.hist.title')}
        onKeyDown={e => { if (e.key === 'Escape' && mobileOpen) onCloseMobile() }}>
        <div className="dl-hist__head">
          <h2 className="dl-hist__title">{t('ask.hist.title')}</h2>
          <button type="button" className="dl-hist__icon dl-hist__fold"
            aria-label={collapsed ? t('ask.hist.expand') : t('ask.hist.collapse')}
            title={collapsed ? t('ask.hist.expand') : t('ask.hist.collapse')}
            aria-expanded={!collapsed} onClick={onToggleCollapsed}>
            {collapsed ? <PanelRightOpen size={16} aria-hidden className="dl-flip" />
              : <PanelRightClose size={16} aria-hidden className="dl-flip" />}
          </button>
          <button type="button" className="dl-hist__icon dl-hist__close" aria-label={t('ask2.hist.hide')} title={t('ask2.hist.hide')}
            onClick={onCloseMobile}>
            <X size={16} aria-hidden />
          </button>
        </div>
        <div className="dl-hist__new-wrap">
          <button type="button" className="dl-hist__new" onClick={onNew} title={t('ask.newChat')} disabled={scope === 'none'}>
            <SquarePen size={15} aria-hidden /> <span className="dl-hist__new-text">{t('ask.newChat')}</span>
          </button>
        </div>
        <ul aria-label={t('ask.conversations')} className="dl-hist__list">
          {conversations.length === 0 && (
            <li className="dl-hist__empty">
              {t(scope === 'none' ? 'ask2.hist.pick' : scope === 'source' ? 'ask2.hist.noneSource' : 'ask2.hist.none')}
            </li>
          )}
          {groups.map(g => [
            <li key={`g-${g.label}`} role="presentation" className="dl-hist__group">{g.label}</li>,
            ...g.items.map(c => (
              <li key={c.id} className={`dl-hist__item${selected === c.id ? ' is-current' : ''}`}>
                {editing?.id === c.id ? (
                  <input aria-label={t('ask2.hist.titleField')} autoFocus value={editing.title} className="dl-hist__input" dir="auto"
                    onChange={e => onEdit({ id: c.id, title: e.target.value })}
                    onKeyDown={e => {
                      if (e.key === 'Enter') onSave()
                      if (e.key === 'Escape') { e.stopPropagation(); onCancelEdit() }
                    }}
                    onBlur={onSave} />
                ) : (
                  <button type="button" className="dl-hist__pick" title={c.title}
                    aria-current={selected === c.id ? 'true' : undefined}
                    onClick={() => onSelect(c.id)}>
                    <MessageSquare size={15} aria-hidden className="dl-hist__pick-icon" />
                    <span className="dl-hist__pick-title" dir="auto">{c.title}</span>
                    {when(c.created_at) && <span className="dl-hist__pick-when" dir="ltr">{localDigits(when(c.created_at))}</span>}
                  </button>
                )}
                <span className="dl-hist__tools">
                  <button type="button" aria-label={t('ask2.hist.rename', { title: c.title })} title={t('ask.rename')} className="dl-hist__icon"
                    onClick={() => onEdit({ id: c.id, title: c.title })}>
                    <Pencil size={13} aria-hidden />
                  </button>
                  <button type="button" aria-label={t('ask2.hist.delete', { title: c.title })} title={t('ask.delete')} className="dl-hist__icon"
                    onClick={() => onDelete(c)}>
                    <Trash2 size={13} aria-hidden />
                  </button>
                </span>
              </li>
            )),
          ])}
        </ul>
        <p className="dl-hist__foot">
          <Info size={14} aria-hidden /> {t(scope === 'source' ? 'ask2.hist.footSource' : 'ask2.hist.foot')}
        </p>
      </aside>
    </>
  )
}
