import { useEffect, useState } from 'react'
import { subscriptionApi, type Subscription } from '../../services/api'
import toast from 'react-hot-toast'
import { useModalDialog } from '../ui/useModalDialog'

const CADENCES = ['daily', 'weekly', 'monthly'] as const
const DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

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
      toast.success('Subscribed — the first copy arrives on schedule')
      setOpen(false)
      load()
    } catch (e: unknown) {
      toast.error((e as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail ?? 'Could not subscribe')
    } finally {
      setBusy(false)
    }
  }

  const cancel = async () => {
    setBusy(true)
    try {
      await subscriptionApi.unsubscribe(reportId)
      toast.success('Unsubscribed')
      setOpen(false)
      load()
    } catch {
      toast.error('Could not unsubscribe')
    } finally {
      setBusy(false)
    }
  }

  const subscribed = !!sub?.subscribed

  return (
    <>
      <button className="btn btn-ghost btn-sm"
        title={subscribed ? 'You are subscribed to this report' : 'Get a recurring copy by email'}
        aria-pressed={subscribed}
        onClick={() => setOpen(true)}>
        {subscribed ? '🔔 Subscribed' : '🔔 Subscribe'}
      </button>

      {open && (
        <div
          style={{
            position: 'fixed', inset: 0, background: 'rgba(0,0,0,.4)', zIndex: 900,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
          <div ref={dialogRef} role="dialog" aria-modal="true"
            aria-label="Subscribe to this report" style={{
            background: 'var(--surface)', border: '1px solid var(--border)',
            borderRadius: 8, padding: 20, minWidth: 340, maxWidth: 420,
          }}>
            <h2 style={{ margin: '0 0 4px', fontSize: 16 }}>Email me this report</h2>
            <p style={{ fontSize: 12, color: 'var(--muted)', marginTop: 0 }}>
              Sent to your own address, containing the rows you can see — not
              anyone else’s.
            </p>

            <label style={{ display: 'block', fontSize: 12, marginTop: 10 }}>
              How often
              <select aria-label="How often" value={cadence}
                onChange={e => setCadence(e.target.value as typeof cadence)}
                className="input" style={{ width: '100%', marginTop: 3 }}>
                {CADENCES.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </label>

            {cadence === 'weekly' && (
              <label style={{ display: 'block', fontSize: 12, marginTop: 8 }}>
                On
                <select aria-label="Day of week" value={weekday}
                  onChange={e => setWeekday(Number(e.target.value))}
                  className="input" style={{ width: '100%', marginTop: 3 }}>
                  {DAYS.map((d, i) => <option key={d} value={i}>{d}</option>)}
                </select>
              </label>
            )}

            {cadence === 'monthly' && (
              <label style={{ display: 'block', fontSize: 12, marginTop: 8 }}>
                Day of month
                {/* Capped at 28: the only day every month actually has. */}
                <select aria-label="Day of month" value={monthday}
                  onChange={e => setMonthday(Number(e.target.value))}
                  className="input" style={{ width: '100%', marginTop: 3 }}>
                  {Array.from({ length: 28 }, (_, i) => i + 1).map(d =>
                    <option key={d} value={d}>{d}</option>)}
                </select>
              </label>
            )}

            <label style={{ display: 'block', fontSize: 12, marginTop: 8 }}>
              At
              <select aria-label="Hour" value={hour}
                onChange={e => setHour(Number(e.target.value))}
                className="input" style={{ width: '100%', marginTop: 3 }}>
                {Array.from({ length: 24 }, (_, h) => h).map(h => (
                  <option key={h} value={h}>{String(h).padStart(2, '0')}:00</option>
                ))}
              </select>
            </label>

            <label style={{ display: 'block', fontSize: 12, marginTop: 8 }}>
              Format
              <select aria-label="Format" value={format}
                onChange={e => setFormat(e.target.value as 'xlsx' | 'pdf')}
                className="input" style={{ width: '100%', marginTop: 3 }}>
                <option value="xlsx">Excel (.xlsx)</option>
                <option value="pdf">PDF</option>
              </select>
            </label>

            {subscribed && sub?.last_run_at && (
              <p style={{ fontSize: 11, color: 'var(--muted)', marginTop: 10 }}>
                Last sent {new Date(sub.last_run_at).toLocaleString()}
                {sub.last_status ? ` · ${sub.last_status}` : ''}
              </p>
            )}

            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 16 }}>
              {subscribed && (
                <button className="btn btn-ghost btn-sm" disabled={busy}
                  onClick={() => void cancel()}>Unsubscribe</button>
              )}
              <button className="btn btn-ghost btn-sm" onClick={() => setOpen(false)}>
                Cancel
              </button>
              <button className="btn btn-primary btn-sm" disabled={busy}
                onClick={() => void save()}>
                {busy ? 'Saving…' : subscribed ? 'Update' : 'Subscribe'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
