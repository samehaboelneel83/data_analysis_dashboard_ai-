import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { notificationsApi, type AppNotification } from '../services/api'
import { Bell, Clock, MessageSquare, RefreshCw, Zap } from 'lucide-react'
import { useT } from '../i18n'

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
    notificationsApi.list().then(r => { setUnread(r.unread); setItems(r.notifications) }).catch(() => {})

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

      {open && (
        <div role="menu" aria-label={t('bell.list')}
          style={{ position: 'absolute', insetInlineEnd: 0, top: '115%', width: 320, maxHeight: 380, overflowY: 'auto',
            background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10,
            boxShadow: '0 8px 28px rgba(0,0,0,.25)', zIndex: 900, padding: 6 }}>
          {items.length === 0 ? (
            <p style={{ fontSize: 12, color: 'var(--muted)', padding: 10 }}>{t('bell.empty')}</p>
          ) : items.map(n => (
            <button key={n.id} role="menuitem"
              onClick={() => { if (n.link) { navigate(n.link); setOpen(false) } }}
              style={{ display: 'flex', gap: 8, alignItems: 'flex-start', width: '100%', textAlign: 'start',
                background: 'none', border: 'none', borderBottom: '1px solid var(--border)',
                padding: '8px 6px', fontSize: 12, color: 'var(--text)',
                cursor: n.link ? 'pointer' : 'default', opacity: n.read ? 0.65 : 1 }}>
              <span aria-hidden style={{ flexShrink: 0, display: 'inline-flex', color: 'var(--muted)', marginTop: 1 }}>{KIND_ICON[n.kind] ?? <Bell size={13} />}</span>
              <span>
                {n.text}
                <span style={{ display: 'block', fontSize: 10, color: 'var(--muted)', marginTop: 2 }}>
                  {new Date(n.created_at).toLocaleString()}
                </span>
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
