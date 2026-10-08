import { useEffect, useState } from 'react'
import { subscriptionApi, type Subscription } from '../../services/api'
import toast from 'react-hot-toast'
import { useModalDialog } from '../ui/useModalDialog'
import IconLabel from '../ui/IconLabel'
import { Bell, BellRing } from 'lucide-react'
import { useT } from '../../i18n'
import { formatDate } from '../../lib/dateFormat'

const CADENCES = ['daily', 'weekly', 'monthly'] as const
/** Monday first: the index is the weekday the server stores (0 = Monday). */
const DAYS = [0, 1, 2, 3, 4, 5, 6] as const

/**
 * Subscribe yourself to a recurring copy of this report.
 *
 * Deliberately lives beside the PDF button rather than in the editor toolbar:
 * subscribing needs only `view`, and that toolbar is gated on `editMode`, which
 * a view-only user can never enter. Putting it there would have hidden the
 * feature from exactly the people it exists for.
 *
 * The dialog states who the copy goes to and whose data it contains, because
 * both are non-obvious and both matter: the schedule is owned by the SUBSCRIBER,
 * so row-level security resolves as them. Joining someone else's schedule would
 * have delivered that person's slice of the data instead.
 */
export default function SubscribeButton({ reportId }: { reportId: number }) {
  const dialogRef = useModalDialog<HTMLDivElement>(() => setOpen(false))
  const [sub, setSub] = useState<Subscription | null>(null)
  const t = useT()
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)

  const [cadence, setCadence] = useState<'daily' | 'weekly' | 'monthly'>('daily')
  const [hour, setHour] = useState(8)
  const [weekday, setWeekday] = useState(0)
  const [monthday, setMonthday] = useState(1)
  const [format, setFormat] = useState<'xlsx' | 'pdf'>('xlsx')

  const load = () => {
    subscriptionApi.get(reportId)
      .then(s => {
        setSub(s)
        if (s.subscribed && s.calendar) {
          setCadence((s.calendar.kind as typeof cadence) ?? 'daily')
          setHour(s.calendar.hour ?? 8)
          if (s.calendar.weekday != null) setWeekday(s.calendar.weekday)
          if (s.calendar.monthday != null) setMonthday(s.calendar.monthday)
          setFormat(s.format ?? 'xlsx')
        }
      })
      // A failure here means only that we cannot show the current state; it
      // must not break the report the user came to read.
      .catch(() => setSub(null))
  }
  useEffect(load, [reportId])

  const save = async () => {
    setBusy(true)
    try {
      await subscriptionApi.subscribe(reportId, {
        cadence, hour, minute: 0, format,
        ...(cadence === 'weekly' ? { weekday } : {}),
        ...(cadence === 'monthly' ? { monthday } : {}),
        // The browser's zone, so "08:00" means 08:00 where the reader is.
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || null,
      })
      toast.success(t('pg.panelsA.sb.subscribedToast'))
      setOpen(false)
      load()
    } catch (e: unknown) {
      toast.error((e as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail ?? t('pg.panelsA.sb.failed'))
    } finally {
      setBusy(false)
    }
  }

  const cancel = async () => {
    setBusy(true)
    try {
      await subscriptionApi.unsubscribe(reportId)
      toast.success(t('pg.panelsA.sb.unsubscribed'))
      setOpen(false)
      load()
    } catch {
      toast.error(t('pg.panelsA.sb.unsubFailed'))
    } finally {
      setBusy(false)
    }
  }

  const subscribed = !!sub?.subscribed

  return (
    <>
      <button className="btn btn-ghost btn-sm"
        title={subscribed ? t('pg.panelsA.sb.titleOn') : t('pg.panelsA.sb.titleOff')}
        aria-pressed={subscribed}
        onClick={() => setOpen(true)}>
        <IconLabel icon={subscribed ? BellRing : Bell}>{subscribed ? t('subscribe.subscribed') : t('subscribe.subscribe')}</IconLabel>
      </button>

      {open && (
        <div
          style={{
            position: 'fixed', inset: 0, background: 'rgba(0,0,0,.4)', zIndex: 900,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
          <div ref={dialogRef} role="dialog" aria-modal="true"
            aria-label={t('pg.panelsA.sb.aria')} style={{
            background: 'var(--surface)', border: '1px solid var(--border)',
            borderRadius: 8, padding: 20, minWidth: 340, maxWidth: 420,
          }}>
            <h2 style={{ margin: '0 0 4px', fontSize: 16 }}>{t('pg.panelsA.sb.heading')}</h2>
            <p style={{ fontSize: 12, color: 'var(--muted)', marginTop: 0 }}>
              {t('pg.panelsA.sb.note')}
            </p>

            <label style={{ display: 'block', fontSize: 12, marginTop: 10 }}>
              {t('pg.panelsA.sb.howOften')}
              <select aria-label={t('pg.panelsA.sb.howOften')} value={cadence}
                onChange={e => setCadence(e.target.value as typeof cadence)}
                className="input" style={{ width: '100%', marginTop: 3 }}>
                {CADENCES.map(c => <option key={c} value={c}>{t(`pg.panelsA.sb.cad.${c}`)}</option>)}
              </select>
            </label>

            {cadence === 'weekly' && (
              <label style={{ display: 'block', fontSize: 12, marginTop: 8 }}>
                {t('pg.panelsA.sb.on')}
                <select aria-label={t('pg.panelsA.sb.dayOfWeek')} value={weekday}
                  onChange={e => setWeekday(Number(e.target.value))}
                  className="input" style={{ width: '100%', marginTop: 3 }}>
                  {DAYS.map(d => <option key={d} value={d}>{t(`pg.panelsA.sb.day${d}`)}</option>)}
                </select>
              </label>
            )}

            {cadence === 'monthly' && (
              <label style={{ display: 'block', fontSize: 12, marginTop: 8 }}>
                {t('pg.panelsA.sb.dayOfMonth')}
                {/* Capped at 28: the only day every month actually has. */}
                <select aria-label={t('pg.panelsA.sb.dayOfMonth')} value={monthday}
                  onChange={e => setMonthday(Number(e.target.value))}
                  className="input" style={{ width: '100%', marginTop: 3 }}>
                  {Array.from({ length: 28 }, (_, i) => i + 1).map(d =>
                    <option key={d} value={d}>{d}</option>)}
                </select>
              </label>
            )}

            <label style={{ display: 'block', fontSize: 12, marginTop: 8 }}>
              {t('pg.panelsA.sb.at')}
              <select aria-label={t('pg.panelsA.sb.hour')} value={hour}
                onChange={e => setHour(Number(e.target.value))}
                className="input" style={{ width: '100%', marginTop: 3 }}>
                {Array.from({ length: 24 }, (_, h) => h).map(h => (
                  <option key={h} value={h}>{String(h).padStart(2, '0')}:00</option>
                ))}
              </select>
            </label>

            <label style={{ display: 'block', fontSize: 12, marginTop: 8 }}>
              {t('pg.panelsA.sb.format')}
              <select aria-label={t('pg.panelsA.sb.format')} value={format}
                onChange={e => setFormat(e.target.value as 'xlsx' | 'pdf')}
                className="input" style={{ width: '100%', marginTop: 3 }}>
                <option value="xlsx">{ // i18n-ok: a product name and a file type
                  'Excel (.xlsx)'
                }</option>
                <option value="pdf">PDF</option>
              </select>
            </label>

            {subscribed && sub?.last_run_at && (
              <p style={{ fontSize: 11, color: 'var(--muted)', marginTop: 10 }}>
                {t('pg.panelsA.sb.lastSent', { date: formatDate(sub.last_run_at) })}
                {sub.last_status ? ` · ${sub.last_status}` : ''}
              </p>
            )}

            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 16 }}>
              {subscribed && (
                <button className="btn btn-ghost btn-sm" disabled={busy}
                  onClick={() => void cancel()}>{t('pg.panelsA.sb.unsubscribe')}</button>
              )}
              <button className="btn btn-ghost btn-sm" onClick={() => setOpen(false)}>
                {t('pg.panelsA.sb.cancel')}
              </button>
              <button className="btn btn-primary btn-sm" disabled={busy}
                onClick={() => void save()}>
                {busy ? t('pg.panelsA.sb.saving') : subscribed ? t('pg.panelsA.sb.update') : t('subscribe.subscribe')}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
