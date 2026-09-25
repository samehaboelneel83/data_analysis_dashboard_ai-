import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { notificationsApi, type AppNotification } from '../services/api'
import { Bell, Clock, MessageSquare, RefreshCw, Zap } from 'lucide-react'
import { formatTimeAgo, useT } from '../i18n'

const KIND_ICON: Record<string, React.ReactNode> = {
  alert: <Zap size={13} />, schedule: <Clock size={13} />,
  refresh: <RefreshCw size={13} />, comment: <MessageSquare size={13} />,
}

/**
 * The in-app bell: alerts firing, scheduled deliveries failing, comments on
 * reports you've participated in. Polls every 60s — failures produced by the
 * background loop must reach a user who never configured email.
 */
export default function NotificationsBell() {
  const t = useT()
  const [unread, setUnread] = useState(0)
  const [items, setItems] = useState<AppNotification[]>([])
  const [open, setOpen] = useState(false)
  const navigate = useNavigate()
  const rootRef = useRef<HTMLDivElement>(null)

  const refresh = () =>
    notificationsApi.list().then(r => { setUnread(r?.unread ?? 0); setItems(Array.isArray(r?.notifications) ? r.notifications : []) }).catch(() => {})

  useEffect(() => {
    refresh()
    const t = setInterval(refresh, 60_000)
    return () => clearInterval(t)
  }, [])

  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [open])

  const newCount = items.filter(n => !n.read).length

  const toggle = () => {
    const next = !open
    setOpen(next)
    if (next && unread > 0) {
      // Opening the bell is reading it: clear the counter, keep the list.
      notificationsApi.markRead().then(() => setUnread(0)).catch(() => {})
    }
  }

  return (
    <div ref={rootRef} style={{ position: 'relative' }}>
      <button onClick={toggle} aria-label={unread ? t('bell.unread', { n: unread }) : t('bell.title')}
        title={t('bell.title')}
        style={{ position: 'relative', width: 40, height: 40, borderRadius: 8, border: 'none',
          background: open ? 'color-mix(in srgb, var(--accent) 10%, transparent)' : 'transparent', cursor: 'pointer',
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          color: open ? 'var(--accent)' : 'var(--muted)' }}>
        <Bell size={17} strokeWidth={1.9} aria-hidden />
        {unread > 0 && (
          <span data-testid="bell-unread" style={{ position: 'absolute', top: 5, insetInlineEnd: 5, minWidth: 14, height: 14,
            borderRadius: 7, background: 'var(--danger)', color: 'var(--mc-danger-fg, #fff)', fontSize: 9, fontWeight: 700,
            display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '0 3px' }}>
            {unread > 9 ? '9+' : unread}
          </span>
        )}
      </button>

      {/* A panel with a head, not a bare list: what this is, and how many
          of the items are new. Opening the bell still marks them read on the
          server, but the items that WERE new keep their marker for as long
          as the panel is open -- fading read ones to 65% made the old ones
          hard to read and the new ones no easier to find. */}
      {open && (
        <div className="dl-bell">
          <div className="dl-bell__head">
            <span className="dl-bell__title">{t('bell.title')}</span>
            <span className="dl-bell__count">
              {newCount > 0 ? t('bell.new', { n: newCount }) : items.length > 0 ? t('bell.allRead') : null}
            </span>
          </div>
          <div role="menu" aria-label={t('bell.list')} className="dl-bell__list">
            {items.length === 0 ? (
              <div className="dl-bell__empty">
                <Bell size={22} aria-hidden />
                <p>{t('bell.empty')}</p>
              </div>
            ) : items.map(n => (
              <button key={n.id} role="menuitem" type="button"
                className={`dl-bell__item${n.read ? '' : ' dl-bell__item--new'}`}
                onClick={() => { if (n.link) { navigate(n.link); setOpen(false) } }}
                style={{ cursor: n.link ? 'pointer' : 'default' }}>
                <span aria-hidden className="dl-bell__icon">{KIND_ICON[n.kind] ?? <Bell size={13} />}</span>
                <span className="dl-bell__body">
                  {n.text}
                  <span className="dl-bell__time" title={new Date(n.created_at).toLocaleString()}>
                    {formatTimeAgo(n.created_at, t) ?? new Date(n.created_at).toLocaleString()}
                  </span>
                </span>
                {!n.read && <span className="dl-bell__dot" aria-label="new" />}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
