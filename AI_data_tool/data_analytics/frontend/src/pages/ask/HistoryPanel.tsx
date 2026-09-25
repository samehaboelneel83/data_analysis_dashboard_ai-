import { useRef } from 'react'
import { MessageSquare, PanelLeftClose, PanelLeftOpen, Pencil, Plus, Trash2, X } from 'lucide-react'
import type { AgentConversation } from '../../services/api'
import { useT } from '../../i18n'
import { localDigits } from '../../lib/arabicFormats'
import { fmtDate, fmtTime } from './dates'

/**
 * The threads held about the current scope, grouped Today / Earlier, with
 * "New chat" on top. On a wide screen it can fold to a thin rail (the choice
 * is remembered); on a phone it is a drawer the page opens from a button.
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
  collapsed, onToggleCollapsed, mobileOpen, onCloseMobile,
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
          <span className="dl-hist__title">{t('ask.hist.title')}</span>
          <button type="button" className="dl-hist__icon dl-hist__fold"
            aria-label={collapsed ? t('ask.hist.expand') : t('ask.hist.collapse')}
            title={collapsed ? t('ask.hist.expand') : t('ask.hist.collapse')}
            aria-expanded={!collapsed} onClick={onToggleCollapsed}>
            {collapsed ? <PanelLeftOpen size={16} aria-hidden className="dl-flip" />
              : <PanelLeftClose size={16} aria-hidden className="dl-flip" />}
          </button>
          <button type="button" className="dl-hist__icon dl-hist__close" aria-label={t('ask.picker.close')}
            onClick={onCloseMobile}>
            <X size={16} aria-hidden />
          </button>
        </div>
        <button type="button" className="dl-hist__new" onClick={onNew} title={t('ask.newChat')}>
          <Plus size={15} aria-hidden /> <span className="dl-hist__new-text">{t('ask.newChat')}</span>
        </button>
        <ul aria-label={t('ask.conversations')} className="dl-hist__list">
          {conversations.length === 0 && (
            <li className="dl-hist__empty">{t('ask.noConversations')}</li>
          )}
          {groups.map(g => [
            <li key={`g-${g.label}`} role="presentation" className="dl-hist__group">{g.label}</li>,
            ...g.items.map(c => (
              <li key={c.id} className={`dl-hist__item${selected === c.id ? ' is-current' : ''}`}>
                {editing?.id === c.id ? (
                  <input aria-label="Title" autoFocus value={editing.title} className="dl-hist__input"
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
                    <MessageSquare size={14} aria-hidden className="dl-hist__pick-icon" />
                    <span className="dl-hist__pick-text">
                      <span className="dl-hist__pick-title" dir="auto">{c.title}</span>
                      {when(c.created_at) && <span className="dl-hist__pick-when">{localDigits(when(c.created_at))}</span>}
                    </span>
                  </button>
                )}
                <span className="dl-hist__tools">
                  <button type="button" aria-label={`Rename ${c.title}`} title={t('ask.rename')} className="dl-hist__icon"
                    onClick={() => onEdit({ id: c.id, title: c.title })}>
                    <Pencil size={13} aria-hidden />
                  </button>
                  <button type="button" aria-label={`Delete ${c.title}`} title={t('ask.delete')} className="dl-hist__icon"
                    onClick={() => onDelete(c)}>
                    <Trash2 size={13} aria-hidden />
                  </button>
                </span>
              </li>
            )),
          ])}
        </ul>
      </aside>
    </>
  )
}
