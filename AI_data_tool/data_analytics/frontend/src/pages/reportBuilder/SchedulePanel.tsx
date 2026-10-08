import { formatDate } from '../../lib/dateFormat'
import { Fragment, useCallback, useEffect, useState, type ReactNode } from 'react'
import toast from 'react-hot-toast'
import { schedulesApi, deliveriesApi, COMMON_TIMEZONES } from '../../services/api'
import { useConfirm } from '../../components/ui/ConfirmDialog'
import { useT, type TranslateFn, type MessageKey } from '../../i18n'
import { localDigits } from '../../lib/arabicFormats'

/** A translated sentence with some of its slots filled by elements (a <bdi>
 *  around a time or an e-mail list), so the whole template is translated as
 *  one and the data inside it is never reordered by the bidi algorithm. */
const SLOT = '\u0001'
function fill(text: string, nodes: Record<string, ReactNode>): ReactNode {
  return text.split(new RegExp(`${SLOT}(\\w+)${SLOT}`)).map((part, i) =>
    i % 2 ? <Fragment key={i}>{nodes[part]}</Fragment> : part)
}
const slot = (name: string) => `${SLOT}${name}${SLOT}`

const DAY = (i: number, form: 'Long' | 'Short') => `bc.rules.sched.day${form}${i}` as MessageKey

/** "Every day", "Every 3 days": the schedule list reads as a sentence, not "Every 1d". */
function every(t: TranslateFn, minutes: number): string {
  const [n, one, many] = minutes >= 1440
    ? [Math.round(minutes / 1440), 'bc.rules.sched.everyDay', 'bc.rules.sched.everyDays'] as const
    : minutes >= 60
      ? [Math.round(minutes / 60), 'bc.rules.sched.everyHour', 'bc.rules.sched.everyHours'] as const
      : [minutes, 'bc.rules.sched.everyMinute', 'bc.rules.sched.everyMinutes'] as const
  return n === 1 ? t(one) : t(many, { n: localDigits(String(n)) })
}

export function SchedulePanel({ reportId }: { reportId: number }) {
  const confirm = useConfirm()
  const t = useT()
  const [rows, setRows] = useState<import('../../services/api').ReportScheduleRow[]>([])
  const [deliveries, setDeliveries] = useState<import('../../services/api').DeliveryRow[]>([])
  const [interval, setInterval_] = useState('1440')
  const [schedKind, setSchedKind] = useState<'interval' | 'daily' | 'weekly' | 'monthly'>('interval')
  const [schedTime, setSchedTime] = useState('09:00')
  const [schedWeekday, setSchedWeekday] = useState('0')
  const [schedMonthday, setSchedMonthday] = useState('1')
  const [schedTz, setSchedTz] = useState('')
  const [recipients, setRecipients] = useState('')
  const [perRecipient, setPerRecipient] = useState(false)
  const [onlyIfChanged, setOnlyIfChanged] = useState(false)
  const [subject, setSubject] = useState('')
  const [schedFormat, setSchedFormat] = useState<'xlsx' | 'pdf'>('xlsx')
  const reload = useCallback(() => { schedulesApi.list(reportId).then(setRows).catch(() => {}) }, [reportId])
  const reloadDeliveries = useCallback(() => { deliveriesApi.list(reportId).then(setDeliveries).catch(() => {}) }, [reportId])
  useEffect(() => { reload() }, [reload])
  useEffect(() => { reloadDeliveries() }, [reloadDeliveries])

  return (
    <div style={{ padding: 12 }}>
      <div style={{ fontSize: 13, fontWeight: 650, marginBottom: 4 }}>
        {t('bc.rules.sched.title')}
      </div>
      <p style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 12, lineHeight: 1.45 }}>
        {t('bc.rules.sched.intro')}
      </p>

      {rows.map(r => (
        <div key={r.id} style={{ border: '1px solid var(--border)', borderRadius: 8, padding: 10, marginBottom: 8, fontSize: 12 }}>
          <div style={{ fontWeight: 600 }}>
            {fill(t('bc.rules.sched.line', { when: slot('when'), to: slot('to') }), {
              when: r.calendar
                ? fill(t(r.calendar.kind === 'daily' ? 'bc.rules.sched.daily'
                    : r.calendar.kind === 'weekly' ? 'bc.rules.sched.weekly' : 'bc.rules.sched.monthly', {
                    day: t(DAY(r.calendar.weekday ?? 0, 'Short')),
                    n: localDigits(String(r.calendar.monthday ?? 1)),
                    time: slot('time'), tz: slot('tz'),
                  }), {
                    time: <bdi>{localDigits(`${String(r.calendar.hour).padStart(2, '0')}:${String(r.calendar.minute).padStart(2, '0')}`)}</bdi>,
                    tz: <bdi>{r.timezone || 'UTC'}</bdi>,
                  })
                : every(t, r.interval_minutes),
              to: <bdi>{r.recipients.join(', ')}</bdi>,
            })}
            {r.format === 'pdf' && <span style={{ marginInlineStart: 6, fontSize: 10.5, color: 'var(--accent)' }}>PDF</span>}
            {r.per_recipient && <span style={{ marginInlineStart: 6, fontSize: 10.5, color: 'var(--accent)' }}>{t('bc.rules.sched.ownView')}</span>}
            {r.only_if_changed && <span style={{ marginInlineStart: 6, fontSize: 10.5, color: 'var(--muted)' }}>{t('bc.rules.sched.onlyChanged')}</span>}
          </div>
          {/* The status line is the whole observability story: it says whether the
              last run sent, and if not, why -- including "SMTP is not configured". */}
          {r.last_status && <div style={{ color: 'var(--muted)', marginTop: 3 }}>{r.last_status}</div>}
          <div style={{ display: 'flex', gap: 6, marginTop: 6 }}>
            <button className="btn btn-ghost btn-sm"
              onClick={() => schedulesApi.runNow(reportId, r.id)
                .then(res => { toast.success(res.last_status); reload(); reloadDeliveries() })
                .catch(() => toast.error(t('bc.rules.sched.runFailed')))}>
              {t('bc.rules.sched.runNow')}
            </button>
            <button className="btn btn-ghost btn-sm" style={{ color: 'var(--danger)' }}
              onClick={async () => {
                // Sits immediately beside "Run now": two adjacent buttons, one
                // harmless and one that silently stops a recurring delivery
                // people downstream are expecting to arrive.
                if (!await confirm({
                  title: t('bc.rules.sched.deleteTitle'),
                  body: t('bc.rules.sched.deleteBody'),
                  confirmLabel: t('bc.rules.delete'), cancelLabel: t('bc.rules.cancel'),
                })) return
                await schedulesApi.delete(reportId, r.id)
                reload()
              }}>
              {t('bc.rules.delete')}
            </button>
          </div>
        </div>
      ))}

      {deliveries.length > 0 && (
        <div style={{ marginBottom: 10 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--muted)', marginBottom: 6 }}>
            {t('bc.rules.sched.history')}
          </div>
          <div style={{ maxHeight: 160, overflowY: 'auto', border: '1px solid var(--border)', borderRadius: 6 }}>
            {deliveries.map(d => (
              <div key={d.id} style={{ padding: '6px 8px', fontSize: 11.5, borderBottom: '1px solid var(--border)', display: 'flex', gap: 6, alignItems: 'baseline' }}>
                <span style={{ color: d.status === 'ok' ? 'var(--success, #2a8)' : 'var(--danger)', fontWeight: 700 }}>
                  {d.status === 'ok' ? '✓' : '✕'}
                </span>
                <span style={{ color: 'var(--muted)' }}>{formatDate(d.created_at)}</span>
                {d.duration_ms != null && <span style={{ color: 'var(--muted)' }}>{t('bc.rules.sched.ms', { n: localDigits(String(d.duration_ms)) })}</span>}
                {d.error && <span style={{ color: 'var(--danger)', flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={d.error}>{d.error}</span>}
              </div>
            ))}
          </div>
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 10, borderTop: rows.length ? '1px solid var(--border)' : 'none', paddingTop: rows.length ? 10 : 0 }}>
        <label style={{ fontSize: 12, color: 'var(--muted)', display: 'grid', gap: 4 }}>{t('bc.rules.sched.send')}
          <select aria-label={t('bc.rules.sched.typeAria')} value={schedKind}
            onChange={e => setSchedKind(e.target.value as typeof schedKind)} className="input" style={{ width: '100%', fontSize: 12.5 }}>
            <option value="interval">{t('bc.rules.sched.kindInterval')}</option>
            <option value="daily">{t('bc.rules.sched.kindDaily')}</option>
            <option value="weekly">{t('bc.rules.sched.kindWeekly')}</option>
            <option value="monthly">{t('bc.rules.sched.kindMonthly')}</option>
          </select>
        </label>
        {schedKind === 'interval' && (
          <label style={{ fontSize: 12, color: 'var(--muted)', display: 'grid', gap: 4 }}>{t('bc.rules.sched.repeatEvery')}
            <select aria-label={t('bc.rules.sched.repeatEvery')} value={interval} onChange={e => setInterval_(e.target.value)} className="input" style={{ width: '100%', fontSize: 12.5 }}>
              <option value="60">{t('bc.rules.sched.hour')}</option>
              <option value="1440">{t('bc.rules.sched.day')}</option>
              <option value="10080">{t('bc.rules.sched.week')}</option>
            </select>
          </label>
        )}
        {schedKind !== 'interval' && (
          <div style={{ display: 'flex', gap: 6 }}>
            <label style={{ fontSize: 12, color: 'var(--muted)', flex: 1, display: 'grid', gap: 4 }}>{t('bc.rules.sched.time')}
              <input type="time" aria-label={t('bc.rules.sched.timeAria')} value={schedTime}
                onChange={e => setSchedTime(e.target.value)} className="input" style={{ width: '100%', fontSize: 12.5 }} />
            </label>
            {schedKind === 'weekly' && (
              <label style={{ fontSize: 12, color: 'var(--muted)', flex: 1, display: 'grid', gap: 4 }}>{t('bc.rules.sched.day')}
                <select aria-label={t('bc.rules.sched.weekdayAria')} value={schedWeekday}
                  onChange={e => setSchedWeekday(e.target.value)} className="input" style={{ width: '100%', fontSize: 12.5 }}>
                  {[0, 1, 2, 3, 4, 5, 6]
                    .map(i => <option key={i} value={String(i)}>{t(DAY(i, 'Long'))}</option>)}
                </select>
              </label>
            )}
            {schedKind === 'monthly' && (
              <label style={{ fontSize: 12, color: 'var(--muted)', flex: 1, display: 'grid', gap: 4 }}>{t('bc.rules.sched.monthday')}
                <input type="number" min={1} max={28} aria-label={t('bc.rules.sched.monthdayAria')} value={schedMonthday}
                  onChange={e => setSchedMonthday(e.target.value)} className="input" style={{ width: '100%', fontSize: 12.5 }} />
              </label>
            )}
          </div>
        )}
        {schedKind !== 'interval' && (
          <label style={{ fontSize: 12, color: 'var(--muted)', display: 'grid', gap: 4 }}>{t('bc.rules.sched.tz')}
            <input list="tz-options" aria-label={t('bc.rules.sched.tzAria')} value={schedTz}
              onChange={e => setSchedTz(e.target.value)} placeholder="UTC" dir="ltr" // i18n-ok: a timezone id
              className="input" style={{ width: '100%', fontSize: 12.5 }} />
            <datalist id="tz-options">
              {COMMON_TIMEZONES.map(tz => <option key={tz} value={tz} />)}
            </datalist>
          </label>
        )}
        <label style={{ fontSize: 12, color: 'var(--muted)', display: 'grid', gap: 4 }}>{t('bc.rules.sched.recipients')}
          <input value={recipients} onChange={e => setRecipients(e.target.value)} dir="ltr"
            placeholder="a@example.com, b@example.com" // i18n-ok: e-mail addresses
            className="input" style={{ width: '100%', fontSize: 12.5 }} />
        </label>
        <label style={{ fontSize: 12, color: 'var(--muted)', display: 'grid', gap: 4 }}>{t('bc.rules.sched.subject')}
          <input value={subject} onChange={e => setSubject(e.target.value)} dir="auto" className="input" style={{ width: '100%', fontSize: 12.5 }} />
        </label>
        <label style={{ fontSize: 12, color: 'var(--muted)', display: 'grid', gap: 4 }}>{t('bc.rules.sched.attachment')}
          <select aria-label={t('bc.rules.sched.attachmentAria')} value={schedFormat}
            onChange={e => setSchedFormat(e.target.value as 'xlsx' | 'pdf')} className="input" style={{ width: '100%', fontSize: 12.5 }}>
            <option value="xlsx">{t('bc.rules.sched.xlsx')}</option>
            <option value="pdf">{t('bc.rules.sched.pdf')}</option>
          </select>
        </label>
        {/* HR evaluation, item 3.3: "each manager gets their own department". */}
        <label style={{ fontSize: 12, display: 'flex', gap: 6, alignItems: 'flex-start' }}>
          <input type="checkbox" checked={perRecipient} aria-label={t('bc.rules.sched.perRecipientAria')}
            onChange={e => setPerRecipient(e.target.checked)} />
          <span>{t('bc.rules.sched.perRecipient')}
            <span style={{ display: 'block', color: 'var(--muted)', fontSize: 11 }}>
              {t('bc.rules.sched.perRecipientHint')}
            </span></span>
        </label>
        <label style={{ fontSize: 12, display: 'flex', gap: 6, alignItems: 'center' }}>
          <input type="checkbox" checked={onlyIfChanged} aria-label={t('bc.rules.sched.onlyChangedAria')}
            onChange={e => setOnlyIfChanged(e.target.checked)} />
          {t('bc.rules.sched.onlyChangedLabel')}
        </label>
        <button className="btn btn-primary btn-sm" style={{ alignSelf: 'flex-start' }}
          onClick={() => schedulesApi.create(reportId, {
            ...(perRecipient ? { per_recipient: true } : {}),
            ...(onlyIfChanged ? { only_if_changed: true } : {}),
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
          }).then(() => { setRecipients(''); setSubject(''); setSchedFormat('xlsx'); setSchedTz(''); setPerRecipient(false); setOnlyIfChanged(false); reload(); toast.success(t('bc.rules.sched.created')) })
            .catch(e => toast.error(e?.response?.data?.detail ?? t('bc.rules.sched.createFailed')))}>
          {t('bc.rules.sched.add')}
        </button>
      </div>
    </div>
  )
}
