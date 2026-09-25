import { useEffect, useState } from 'react'
import { useT, type MessageKey } from '../../i18n'
import { Link } from 'react-router-dom'
import { monitoringApi } from '../../services/api'
import type { MonitoringJobRow } from '../../services/api'
import { useListFilter } from '../../components/ui/ListFilter'
import { RefreshCw, GitBranch, Mail, Bell, CalendarClock, type LucideIcon } from 'lucide-react'
import EmptyState from '../../components/ui/EmptyState'
import LoadError from '../../components/ui/LoadError'
import LoadingState from '../../components/ui/LoadingState'

/**
 * Every scheduled thing in the org, in one list: dataset refreshes, dataflow
 * runs, report schedules, data alerts. Each of those already records its own
 * last-run state -- this page exists because answering "did last night's
 * refresh work?" previously meant opening every report and dataset in turn.
 * Read-only: fixing a broken job happens where the job is configured, and
 * each row links there.
 */

const KIND_LABEL: Record<MonitoringJobRow['kind'], string> = {
  dataset_refresh: 'Dataset refresh',
  dataflow: 'Dataflow',
  report_schedule: 'Report schedule',
  alert: 'Data alert',
}

const KIND_ICON: Record<MonitoringJobRow['kind'], LucideIcon> = {
  dataset_refresh: RefreshCw, dataflow: GitBranch, report_schedule: Mail, alert: Bell,
}

/** Where a job is configured, or null when it has no page to open. */
function jobLink(j: MonitoringJobRow): string | null {
  switch (j.kind) {
    case 'dataset_refresh': return `/datasets/${j.id}`
    // Dataflows still run, and still belong in this list. The page that
    // configured them is gone, so the row names the job and stops there
    // rather than linking into a route that would 404.
    case 'dataflow': return null
    case 'report_schedule': return j.report_id != null ? `/reports/${j.report_id}` : '/reports'
    case 'alert': return j.dataset_id != null ? `/datasets/${j.dataset_id}` : '/'
  }
}

const WEEKDAY = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
/** The job's schedule in words -- a calendar spec when there is one. */
function schedule(j: MonitoringJobRow): string {
  const c = j.calendar
  if (c) {
    const at = `${String(c.hour).padStart(2, '0')}:${String(c.minute).padStart(2, '0')}${j.timezone ? ` ${j.timezone}` : ' UTC'}`
    if (c.kind === 'weekly') return `weekly (${WEEKDAY[c.weekday ?? 0]}) ${at}`
    if (c.kind === 'monthly') return `monthly (day ${c.monthday ?? 1}) ${at}`
    return `daily ${at}`
  }
  return interval(j.interval_minutes)
}

function interval(minutes: number): string {
  // Some seeded rows carry 0 -- "runs on demand", not "every 0 minutes".
  if (minutes <= 0) return '—'
  if (minutes % 1440 === 0) return minutes === 1440 ? 'daily' : `every ${minutes / 1440} days`
  if (minutes % 60 === 0) return minutes === 60 ? 'hourly' : `every ${minutes / 60} h`
  return `every ${minutes} min`
}

/** ok/clear read as healthy, anything with "fail"/"error" as broken; the rest
 * (e.g. an alert's "firing") is informational -- shown as-is, amber. */
function statusTone(status: string | null): 'ok' | 'bad' | 'info' | null {
  if (!status) return null
  const s = status.toLowerCase()
  if (s === 'ok' || s === 'clear' || s.startsWith('sent')) return 'ok'
  if (s.includes('fail') || s.includes('error')) return 'bad'
  return 'info'
}

// Mixed with the text colour so the words pass 4.5:1 on the table: the pure
// amber/green/red failed WCAG contrast (axe: color-contrast, serious).
const TONE_COLOR = {
  ok: 'color-mix(in oklab, var(--positive, #4caf82) 65%, var(--text))',
  bad: 'color-mix(in oklab, var(--negative, #e2606c) 70%, var(--text))',
  info: 'color-mix(in oklab, #d9a441 55%, var(--text))',
}

export default function MonitoringJobs() {
  const t = useT()
  const [jobs, setJobs] = useState<MonitoringJobRow[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<unknown>(null)

  // A load failure gets the persistent inline banner below, not a toast: it is
  // this page's whole content going missing, not a transient action result.
  const load = () => {
    setLoading(true)
    setLoadError(null)
    return monitoringApi.jobs().then(setJobs).catch(setLoadError).finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const { filtered, input, noMatches } = useListFilter(
    jobs, j => [j.name, KIND_LABEL[j.kind], t(`jobs.kind.${j.kind}` as MessageKey), j.status], t('search.jobs'))
  // Known status words in the reader's language; anything else (an error
  // sentence, a delivery summary) is shown as the server wrote it.
  const statusText = (st: string) => { const k = `jobs.status.${st.toLowerCase()}` as MessageKey; const v = t(k); return v && v !== k ? v : st }

  return (
    <div style={{ maxWidth: 1200 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, marginBottom: 4 }}>
        <h1 className="dl-page-title" style={{ margin: 0 }}>{t('nav.jobs')}</h1>
        {input}
      </div>
      <p className="dl-page-head__sub" style={{ marginBottom: 16, marginTop: 4 }}>
        {t('jobs.subtitle')}
      </p>

      {loading && <LoadingState />}

      {!loading && loadError != null && (
        <LoadError what="jobs" error={loadError} onRetry={load} />
      )}

      {!loading && loadError == null && jobs.length === 0 && (
        <EmptyState icon={CalendarClock} title={t('jobs.empty')}
          description={t('jobs.emptyBody')} />
      )}
      {noMatches && <p style={{ color: 'var(--muted)' }}>{t('jobs.noMatch')}</p>}

      {!loading && loadError == null && filtered.length > 0 && (
        <div className="card dl-table-card"><table className="dl-table">
          <thead>
            <tr>
              <th>{t('col.kind')}</th>
              <th>{t('col.name')}</th>
              <th>{t('col.schedule')}</th>
              <th>{t('col.lastRun')}</th>
              <th>{t('col.status')}</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map(j => {
              const tone = statusTone(j.status)
              return (
                <tr key={`${j.kind}-${j.id}`}>
                  <td style={{ whiteSpace: 'nowrap' }}>
                    <span aria-hidden style={{ display: 'inline-flex', verticalAlign: -2,
                      marginInlineEnd: 6, color: 'var(--muted)' }}>
                      {(() => { const I = KIND_ICON[j.kind]; return <I size={13} /> })()}
                    </span>
                    {t(`jobs.kind.${j.kind}` as MessageKey)}
                  </td>
                  <td style={{ fontWeight: 600 }}>
                    {jobLink(j) != null
                      ? <Link to={jobLink(j)!} className="row-name" style={{ color: 'var(--text)' }}>{j.name}</Link>
                      : j.name}
                  </td>
                  <td style={{ whiteSpace: 'nowrap' }}>{schedule(j)}</td>
                  <td style={{ whiteSpace: 'nowrap' }}>
                    {j.last_run_at ? new Date(j.last_run_at).toLocaleString() : t('jobs.never')}
                  </td>
                  <td style={{ color: tone ? TONE_COLOR[tone] : 'var(--muted)' }}
                    title={j.error ?? undefined}>
                    {j.status ? statusText(j.status) : '—'}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table></div>
      )}
    </div>
  )
}
