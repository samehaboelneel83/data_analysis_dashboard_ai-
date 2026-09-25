import { useCallback, useEffect, useState } from 'react'
import { alertsApi, type DataAlert, type DatasetColumn } from '../../services/api'
import ExpressionBuilder from '../expr/ExpressionBuilder'
import LoadError from '../ui/LoadError'
import EmptyState from '../ui/EmptyState'
import { useT } from '../../i18n'
import { BellRing } from 'lucide-react'
import { useConfirm } from '../ui/ConfirmDialog'

/**
 * Watch a condition on this dataset and email someone when it becomes true.
 *
 * The machinery has been running for months and nothing could reach it. The
 * scheduler evaluates every alert on its interval, resolves row-level security
 * as the alert's CREATOR (an alert has no viewer, and no viewer must never mean
 * no RLS), and sends through the same delivery path as a scheduled report.
 * Three endpoints served all of it. No screen called them, so in practice the
 * platform had no alerts at all.
 *
 * Deliberately small — list, create, delete. There is no edit: an alert is four
 * fields, and re-creating one is less code here and less state to get wrong than
 * a PATCH endpoint that does not exist.
 *
 * Two things this has to say out loud, because getting them wrong makes a
 * working feature look broken:
 *   * it fires on the RISING edge, so a condition that is already true sends
 *     nothing until it clears and comes back;
 *   * an alert whose last evaluation failed is not a healthy alert, and saying
 *     nothing about it means nobody learns the condition stopped being watched.
 */

/** The same aggregate namespace measures use — the expression is evaluated by
 *  the widget sandbox, so the palette must not offer anything it would reject. */
const ALERT_FUNCS = [
  {
    label: 'Aggregation', color: '#f472b6',
    items: [
      { label: 'SUM(col)', snippet: 'SUM()', back: 1, hint: 'Total over the dataset' },
      { label: 'AVG(col)', snippet: 'AVG()', back: 1, hint: 'Mean over the dataset' },
      { label: 'COUNT(col)', snippet: 'COUNT()', back: 1, hint: 'Non-null count' },
      { label: 'COUNTD(col)', snippet: 'COUNTD()', back: 1, hint: 'Distinct count' },
      { label: 'MIN(col)', snippet: 'MIN()', back: 1, hint: 'Smallest value' },
      { label: 'MAX(col)', snippet: 'MAX()', back: 1, hint: 'Largest value' },
    ],
  },
]

const label = { display: 'block', fontSize: 11, fontWeight: 700,
                color: 'var(--muted)', marginBottom: 4 } as const

/** Split on commas, drop the blanks a trailing comma leaves behind. */
function splitEmails(text: string): string[] {
  return text.split(',').map(s => s.trim()).filter(Boolean)
}

/**
 * How often this alert runs, in words.
 *
 * An interval of 0 or less is how this codebase spells "inert" — the demo
 * seeder uses it deliberately, and `refresh_scheduler.is_due` returns false for
 * `<= 0` before it looks at anything else. Neither model has an enabled flag
 * and `interval_minutes` is NOT NULL, so zero is the only spelling available.
 *
 * Rendered arithmetically that came out as "every 0 minutes", which reads as
 * either a bug or an alert hammering the database on every tick — the opposite
 * of what it means. Caught by photographing the real page.
 */
function cadence(minutes: number): string {
  if (minutes <= 0) return 'not scheduled'
  if (minutes >= 1440) {
    const days = Math.round(minutes / 1440)
    return `every ${days} day${days === 1 ? '' : 's'}`
  }
  if (minutes >= 60) {
    const hours = Math.round(minutes / 60)
    return `every ${hours} hour${hours === 1 ? '' : 's'}`
  }
  return `every ${minutes} minutes`
}

export default function AlertsPanel({ datasetId, columns }: {
  datasetId: number
  columns: DatasetColumn[]
}) {
  const confirm = useConfirm()
  const t = useT()
  const [alerts, setAlerts] = useState<DataAlert[] | null>(null)
  const [loadError, setLoadError] = useState<unknown>(null)
  const [adding, setAdding] = useState(false)
  const [name, setName] = useState('')
  const [expression, setExpression] = useState('')
  const [emails, setEmails] = useState('')
  const [interval, setInterval] = useState(60)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const load = useCallback(() => {
    setLoadError(null)
    alertsApi.list(datasetId)
      .then(setAlerts)
      .catch(e => setLoadError(e ?? new Error('failed')))
  }, [datasetId])
  useEffect(() => { load() }, [load])

  const complete = !!name.trim() && !!expression.trim() && splitEmails(emails).length > 0

  const create = async () => {
    if (!complete) return
    setSaving(true); setSaveError(null)
    try {
      await alertsApi.create(datasetId, {
        name: name.trim(), expression: expression.trim(),
        interval_minutes: interval, recipients: splitEmails(emails),
      })
      setAdding(false); setName(''); setExpression(''); setEmails('')
      load()
    } catch (e: unknown) {
      // The endpoint validates the expression through the same sandbox gate the
      // widgets use, and its refusal names the actual problem ("expression
      // rejected: name 'os' is not defined"). Anything generic would leave the
      // user editing at random.
      setSaveError((e as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail ?? 'The alert could not be created')
    } finally {
      setSaving(false)
    }
  }

  const remove = async (alert: DataAlert) => {
    if (!await confirm({
      title: `Delete the alert "${alert.name}"?`,
      body: 'It stops being checked immediately. This cannot be undone.',
    })) return
    await alertsApi.remove(datasetId, alert.id)
    load()
  }

  if (loadError) {
    return <LoadError what="the alerts on this dataset" error={loadError} onRetry={load} />
  }
  if (!alerts) return <p style={{ color: 'var(--muted)' }}>Loading…</p>

  return (
    <div style={{ maxWidth: 760 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    marginBottom: 12 }}>
        <div>
          <div style={{ fontSize: 13, fontWeight: 600 }}>{t('alerts.title')}</div>
          <div style={{ fontSize: 11, color: 'var(--muted)' }}>
            {t('alerts.desc')}
          </div>
        </div>
        {!adding && (
          <button className="btn btn-primary btn-sm" onClick={() => setAdding(true)}>
            {t('alerts.new')}
          </button>
        )}
      </div>

      {adding && (
        <div className="card" style={{ padding: 16, marginBottom: 16 }}>
          <div style={{ marginBottom: 10 }}>
            <label htmlFor="alert-name" style={label}>{t('alerts.name')}</label>
            <input id="alert-name" value={name} style={{ width: '100%' }}
              onChange={e => setName(e.target.value)}
              placeholder="Revenue fell below target" />
          </div>

          <div style={{ marginBottom: 10 }}>
            <label htmlFor="alert-expr" style={label}>{t('alerts.condition')}</label>
            <ExpressionBuilder
              columns={columns} functionsCatalog={ALERT_FUNCS}
              value={expression} onChange={setExpression}
              layout="flat" rows={2} textareaId="alert-expr"
              placeholder="SUM(revenue) < 100000" />
          </div>

          <div style={{ display: 'flex', gap: 12, marginBottom: 10, flexWrap: 'wrap' }}>
            <div style={{ flex: '1 1 260px' }}>
              <label htmlFor="alert-emails" style={label}>{t('alerts.email')}</label>
              <input id="alert-emails" value={emails} style={{ width: '100%' }}
                onChange={e => setEmails(e.target.value)}
                placeholder="ops@example.com, lead@example.com" />
              <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 2 }}>
                {t('alerts.comma')}
              </div>
            </div>
            <div style={{ width: 150 }}>
              <label htmlFor="alert-interval" style={label}>{t('alerts.every')}</label>
              <select id="alert-interval" value={interval} style={{ width: '100%' }}
                onChange={e => setInterval(Number(e.target.value))}>
                {/* 15 is the floor the endpoint clamps to; offering 5 here would
                    silently become 15 on save. */}
                <option value={15}>15 minutes</option>
                <option value={30}>30 minutes</option>
                <option value={60}>hour</option>
                <option value={360}>6 hours</option>
                <option value={1440}>day</option>
              </select>
            </div>
          </div>

          {saveError && (
            <div role="alert" style={{ fontSize: 12, color: 'var(--danger)',
                                       marginBottom: 8 }}>{saveError}</div>
          )}

          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn btn-primary btn-sm" disabled={!complete || saving} title={!complete ? 'Give the alert a name, a condition and an email first' : undefined}
              onClick={() => void create()}>
              {saving ? 'Creating…' : 'Create'}
            </button>
            <button className="btn btn-sm" onClick={() => {
              setAdding(false); setSaveError(null)
            }}>Cancel</button>
          </div>
        </div>
      )}

      {alerts.length === 0 && !adding && (
        <EmptyState icon={BellRing} title={t('alerts.empty')}
          description={t('alerts.emptyBody')}
          action={<button className="btn btn-primary btn-sm" onClick={() => setAdding(true)}>{t('alerts.create')}</button>} />
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {alerts.map(a => <AlertRow key={a.id} alert={a} onDelete={() => void remove(a)} />)}
      </div>
    </div>
  )
}

function AlertRow({ alert, onDelete }: { alert: DataAlert; onDelete: () => void }) {
  const failed = !!alert.last_status && alert.last_status !== 'ok'
  return (
    <div className="card" style={{ padding: 12, display: 'flex', gap: 12,
                                   alignItems: 'flex-start' }}>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 13, fontWeight: 600 }}>{alert.name}</div>
        <div style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--muted)',
                      overflowX: 'auto', whiteSpace: 'nowrap' }}>
          {alert.expression}
        </div>
        <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 4 }}>
          {alert.recipients.join(', ')} · {cadence(alert.interval_minutes)}
        </div>
        {/* A broken alert that looks fine is worse than no alert: nobody learns
            the condition stopped being watched. */}
        {failed ? (
          <div style={{ fontSize: 11, color: 'var(--danger)', marginTop: 4 }}>
            Last check failed — {alert.last_status}
          </div>
        ) : alert.last_checked_at ? (
          <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 4 }}>
            Checked {new Date(alert.last_checked_at).toLocaleString()}
            {alert.last_state ? ' · currently true, so the email has already gone' : ''}
          </div>
        ) : (
          <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 4 }}>
            Not yet checked.
          </div>
        )}
      </div>
      <button className="btn btn-sm" aria-label={`Delete ${alert.name}`}
        onClick={onDelete}>Delete</button>
    </div>
  )
}
