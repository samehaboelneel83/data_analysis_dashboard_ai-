import { useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import { datasetsApi, type PipelineHealth } from '../../services/api'
import { useT } from '../../i18n'

/**
 * Pipeline plan, phase 2, on the dataset page: whether its refresh is working,
 * and the health alerts its editors set (a freshness target, extra
 * recipients). The owner is always told in the app; this only adds to that.
 */

/** Loads the dataset's pipeline health; reloads when `refreshKey` changes
 *  (pass the dataset's last_refreshed_at, so a finished refresh re-reads it). */
export function usePipelineHealth(datasetId: number | null, refreshKey?: unknown) {
  const [health, setHealth] = useState<PipelineHealth | null>(null)
  useEffect(() => {
    if (datasetId == null) return
    let live = true
    // A missing health is not an error worth a banner: the page works without it.
    Promise.resolve().then(() => datasetsApi.pipelineHealth(datasetId))
      .then(h => { if (live && h) setHealth(h) }).catch(() => {})
    return () => { live = false }
  }, [datasetId, refreshKey])
  return [health, setHealth] as const
}

const BAD = 'color-mix(in oklab, var(--negative, #e2606c) 75%, var(--text))'
const WARN = 'color-mix(in oklab, #d9a441 60%, var(--text))'

/** One quiet line under "Last refreshed": shown only when something is wrong. */
export function PipelineHealthLine({ health }: { health: PipelineHealth | null }) {
  const t = useT()
  if (!health || (health.state !== 'failing' && health.state !== 'stale')) return null
  const failing = health.state === 'failing'
  return (
    <div data-testid="pipeline-health" role="status"
      style={{ fontSize: 11, textAlign: 'end', marginBottom: 2, color: failing ? BAD : WARN, maxWidth: 360,
        marginInlineStart: 'auto' }}>
      <strong>{failing ? t('health.failing') : t('health.stale', { hours: health.freshness_hours ?? '' })}</strong>
      {failing && health.last_run?.error && (
        <span style={{ color: 'var(--muted)' }}> · {health.last_run.error.split('\n')[0].slice(0, 160)}</span>
      )}
      {failing && health.next_retry_at && (
        <span style={{ color: 'var(--muted)' }}> · {t('health.nextTry', { when: new Date(health.next_retry_at).toLocaleString() })}</span>
      )}
    </div>
  )
}

/** The freshness target and recipients, inside the refresh menu (editors only). */
export function PipelineAlertsForm({ datasetId, health, onSaved }: {
  datasetId: number; health: PipelineHealth; onSaved: (h: PipelineHealth) => void
}) {
  const t = useT()
  const [hours, setHours] = useState<number | null>(health.freshness_hours)
  const [recipients, setRecipients] = useState(health.recipients.join(', '))
  const [saving, setSaving] = useState(false)
  useEffect(() => {
    setHours(health.freshness_hours)
    setRecipients(health.recipients.join(', '))
  }, [health.freshness_hours, health.recipients.join(',')])

  const label = (h: number) => (h % 24 === 0 && h >= 72 ? t('health.days', { n: h / 24 }) : t('health.hours', { n: h }))
  const save = async () => {
    setSaving(true)
    try {
      const list = recipients.split(/[,\s]+/).map(s => s.trim()).filter(Boolean)
      onSaved(await datasetsApi.setPipelineWatch(datasetId, { freshness_hours: hours, recipients: list }))
      toast.success(t('health.saved'))
    } catch (e) {
      toast.error((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? String(e))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div style={{ borderTop: '1px solid var(--border)', marginTop: 12, paddingTop: 10 }}>
      <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6 }}>{t('health.title')}</div>
      <label style={{ display: 'block', fontSize: 11.5, color: 'var(--muted)', marginBottom: 3 }} htmlFor="health-target">
        {t('health.staleAfter')}
      </label>
      <select id="health-target" className="input" style={{ width: '100%', fontSize: 12, marginBottom: 8 }}
        value={hours ?? ''} onChange={e => setHours(e.target.value ? Number(e.target.value) : null)}>
        <option value="">{t('health.off')}</option>
        {health.freshness_choices.map(h => <option key={h} value={h}>{label(h)}</option>)}
      </select>
      <label style={{ display: 'block', fontSize: 11.5, color: 'var(--muted)', marginBottom: 3 }} htmlFor="health-recipients">
        {t('health.recipients')}
      </label>
      <input id="health-recipients" className="input" dir="ltr" style={{ width: '100%', fontSize: 12, marginBottom: 6 }}
        value={recipients} onChange={e => setRecipients(e.target.value)} placeholder="ops@example.com" />
      <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 8 }}>
        {health.owners?.length
          ? t('health.ownerNamed', { who: health.owners.join(', ') })
          : t('health.ownerNote')}
      </div>
      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
        <button type="button" className="btn btn-primary btn-sm" disabled={saving} onClick={() => void save()}>
          {t('health.save')}
        </button>
      </div>
    </div>
  )
}
