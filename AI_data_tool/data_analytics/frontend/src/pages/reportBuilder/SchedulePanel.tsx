import { useCallback, useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import { schedulesApi, deliveriesApi, COMMON_TIMEZONES } from '../../services/api'
import { useConfirm } from '../../components/ui/ConfirmDialog'

export function SchedulePanel({ reportId }: { reportId: number }) {
  const confirm = useConfirm()
  const [rows, setRows] = useState<import('../../services/api').ReportScheduleRow[]>([])
  const [deliveries, setDeliveries] = useState<import('../../services/api').DeliveryRow[]>([])
  const [interval, setInterval_] = useState('1440')
  const [schedKind, setSchedKind] = useState<'interval' | 'daily' | 'weekly' | 'monthly'>('interval')
  const [schedTime, setSchedTime] = useState('09:00')
  const [schedWeekday, setSchedWeekday] = useState('0')
  const [schedMonthday, setSchedMonthday] = useState('1')
  const [schedTz, setSchedTz] = useState('')
  const [recipients, setRecipients] = useState('')
  const [subject, setSubject] = useState('')
  const [schedFormat, setSchedFormat] = useState<'xlsx' | 'pdf'>('xlsx')
  const reload = useCallback(() => { schedulesApi.list(reportId).then(setRows).catch(() => {}) }, [reportId])
  const reloadDeliveries = useCallback(() => { deliveriesApi.list(reportId).then(setDeliveries).catch(() => {}) }, [reportId])
  useEffect(() => { reload() }, [reload])
  useEffect(() => { reloadDeliveries() }, [reloadDeliveries])

  return (
    <div style={{ padding: 12 }}>
      <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 8 }}>
        Scheduled delivery
      </div>
      <p style={{ fontSize: 10, color: 'var(--muted)', marginBottom: 10 }}>
        Emails this report's data (one sheet per widget) plus a link, on an interval.
        Deliveries run with your data permissions.
      </p>

      {rows.map(r => (
        <div key={r.id} style={{ border: '1px solid var(--border)', borderRadius: 6, padding: 8, marginBottom: 8, fontSize: 11 }}>
          <div style={{ fontWeight: 600 }}>
            {r.calendar
              ? `${r.calendar.kind === 'daily' ? 'Daily' : r.calendar.kind === 'weekly'
                    ? `Weekly (${['Mon','Tue','Wed','Thu','Fri','Sat','Sun'][r.calendar.weekday ?? 0]})`
                    : `Monthly (day ${r.calendar.monthday ?? 1})`} at ${String(r.calendar.hour).padStart(2, '0')}:${String(r.calendar.minute).padStart(2, '0')} ${r.timezone || 'UTC'}`
              : `Every ${r.interval_minutes >= 1440 ? `${Math.round(r.interval_minutes / 1440)}d` : r.interval_minutes >= 60 ? `${Math.round(r.interval_minutes / 60)}h` : `${r.interval_minutes}m`}`}
            {' → '}{r.recipients.join(', ')}
            {r.format === 'pdf' && <span style={{ marginInlineStart: 6, fontSize: 9, color: 'var(--accent)' }}>PDF</span>}
          </div>
          {/* The status line is the whole observability story: it says whether the
              last run sent, and if not, why -- including "SMTP is not configured". */}
          {r.last_status && <div style={{ color: 'var(--muted)', marginTop: 3 }}>{r.last_status}</div>}
          <div style={{ display: 'flex', gap: 6, marginTop: 6 }}>
            <button className="btn btn-ghost btn-sm" style={{ fontSize: 10 }}
              onClick={() => schedulesApi.runNow(reportId, r.id)
                .then(res => { toast.success(res.last_status); reload(); reloadDeliveries() })
                .catch(() => toast.error('Run failed'))}>
              Run now
            </button>
            <button className="btn btn-ghost btn-sm" style={{ fontSize: 10, color: 'var(--danger)' }}
              onClick={async () => {
                // Sits immediately beside "Run now": two adjacent buttons, one
                // harmless and one that silently stops a recurring delivery
                // people downstream are expecting to arrive.
                if (!await confirm({
                  title: 'Delete this schedule?',
                  body: 'The report stops being sent on this schedule. Recipients are not told.',
                })) return
                await schedulesApi.delete(reportId, r.id)
                reload()
              }}>
              Delete
            </button>
          </div>
        </div>
      ))}

      {deliveries.length > 0 && (
        <div style={{ marginBottom: 10 }}>
          <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 6 }}>
            Delivery history
          </div>
          <div style={{ maxHeight: 160, overflowY: 'auto', border: '1px solid var(--border)', borderRadius: 6 }}>
            {deliveries.map(d => (
              <div key={d.id} style={{ padding: '6px 8px', fontSize: 10, borderBottom: '1px solid var(--border)', display: 'flex', gap: 6, alignItems: 'baseline' }}>
                <span style={{ color: d.status === 'ok' ? 'var(--success, #2a8)' : 'var(--danger)', fontWeight: 700 }}>
                  {d.status === 'ok' ? '✓' : '✕'}
                </span>
                <span style={{ color: 'var(--muted)' }}>{new Date(d.created_at).toLocaleString()}</span>
                {d.duration_ms != null && <span style={{ color: 'var(--muted)' }}>{d.duration_ms}ms</span>}
                {d.error && <span style={{ color: 'var(--danger)', flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={d.error}>{d.error}</span>}
              </div>
            ))}
          </div>
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 6, borderTop: rows.length ? '1px solid var(--border)' : 'none', paddingTop: rows.length ? 10 : 0 }}>
        <label style={{ fontSize: 10, color: 'var(--muted)' }}>When
          <select aria-label="Schedule type" value={schedKind}
            onChange={e => setSchedKind(e.target.value as typeof schedKind)} style={{ width: '100%', fontSize: 11 }}>
            <option value="interval">Every N minutes</option>
            <option value="daily">Daily at a time</option>
            <option value="weekly">Weekly at a time</option>
            <option value="monthly">Monthly at a time</option>
          </select>
        </label>
        {schedKind === 'interval' && (
          <label style={{ fontSize: 10, color: 'var(--muted)' }}>Interval
            <select value={interval} onChange={e => setInterval_(e.target.value)} style={{ width: '100%', fontSize: 11 }}>
              <option value="60">Hourly</option>
              <option value="1440">Daily</option>
              <option value="10080">Weekly</option>
            </select>
          </label>
        )}
        {schedKind !== 'interval' && (
          <div style={{ display: 'flex', gap: 6 }}>
            <label style={{ fontSize: 10, color: 'var(--muted)', flex: 1 }}>Time
              <input type="time" aria-label="Schedule time" value={schedTime}
                onChange={e => setSchedTime(e.target.value)} style={{ width: '100%', fontSize: 11 }} />
            </label>
            {schedKind === 'weekly' && (
              <label style={{ fontSize: 10, color: 'var(--muted)', flex: 1 }}>Day
                <select aria-label="Schedule weekday" value={schedWeekday}
                  onChange={e => setSchedWeekday(e.target.value)} style={{ width: '100%', fontSize: 11 }}>
                  {['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
                    .map((d, i) => <option key={i} value={String(i)}>{d}</option>)}
                </select>
              </label>
            )}
            {schedKind === 'monthly' && (
              <label style={{ fontSize: 10, color: 'var(--muted)', flex: 1 }}>Day of month
                <input type="number" min={1} max={28} aria-label="Schedule monthday" value={schedMonthday}
                  onChange={e => setSchedMonthday(e.target.value)} style={{ width: '100%', fontSize: 11 }} />
              </label>
            )}
          </div>
        )}
        {schedKind !== 'interval' && (
          <label style={{ fontSize: 10, color: 'var(--muted)' }}>Timezone (blank = UTC)
            <input list="tz-options" aria-label="Schedule timezone" value={schedTz}
              onChange={e => setSchedTz(e.target.value)} placeholder="UTC"
              style={{ width: '100%', fontSize: 11 }} />
            <datalist id="tz-options">
              {COMMON_TIMEZONES.map(tz => <option key={tz} value={tz} />)}
            </datalist>
          </label>
        )}
        <label style={{ fontSize: 10, color: 'var(--muted)' }}>Recipients (comma separated)
          <input value={recipients} onChange={e => setRecipients(e.target.value)}
            placeholder="a@example.com, b@example.com" style={{ width: '100%', fontSize: 11 }} />
        </label>
        <label style={{ fontSize: 10, color: 'var(--muted)' }}>Subject (optional)
          <input value={subject} onChange={e => setSubject(e.target.value)} style={{ width: '100%', fontSize: 11 }} />
        </label>
        <label style={{ fontSize: 10, color: 'var(--muted)' }}>Attachment
          <select aria-label="Attachment format" value={schedFormat}
            onChange={e => setSchedFormat(e.target.value as 'xlsx' | 'pdf')} style={{ width: '100%', fontSize: 11 }}>
            <option value="xlsx">Excel data (one sheet per widget)</option>
            <option value="pdf">PDF (rendered report)</option>
          </select>
        </label>
        <button className="btn btn-primary btn-sm" style={{ fontSize: 11, alignSelf: 'flex-start' }}
          onClick={() => schedulesApi.create(reportId, {
            recipients: recipients.split(',').map(r => r.trim()).filter(Boolean),
            subject: subject || undefined,
            format: schedFormat,
            ...(schedKind === 'interval'
              ? { interval_minutes: Number(interval) }
              : { calendar: {
                    kind: schedKind,
                    hour: Number(schedTime.split(':')[0] ?? 9),
                    minute: Number(schedTime.split(':')[1] ?? 0),
                    ...(schedKind === 'weekly' ? { weekday: Number(schedWeekday) } : {}),
                    ...(schedKind === 'monthly' ? { monthday: Number(schedMonthday) } : {}),
                  },
                  ...(schedTz.trim() ? { timezone: schedTz.trim() } : {}) }),
          }).then(() => { setRecipients(''); setSubject(''); setSchedFormat('xlsx'); setSchedTz(''); reload(); toast.success('Schedule created') })
            .catch(e => toast.error(e?.response?.data?.detail ?? 'Could not create the schedule'))}>
          Add schedule
        </button>
      </div>
    </div>
  )
}
