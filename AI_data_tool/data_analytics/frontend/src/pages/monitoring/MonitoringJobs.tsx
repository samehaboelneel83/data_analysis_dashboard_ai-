import { useEffect, useState } from 'react'
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

const TONE_COLOR = { ok: 'var(--positive, #4caf82)', bad: 'var(--negative, #e2606c)', info: '#d9a441' }

export default function MonitoringJobs() {
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
    jobs, j => [j.name, KIND_LABEL[j.kind], j.status], 'Search jobs…')

  return (
    <div style={{ padding: 24, maxWidth: 1000 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, marginBottom: 4 }}>
        <h1 style={{ fontSize: 18, fontWeight: 700, margin: 0 }}>Refresh &amp; jobs</h1>
        {input}
      </div>
      <p style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 16 }}>
        Everything that runs on a schedule, and when it last ran. Configure a job where it
        lives — each row links there.
      </p>

      {loading && <LoadingState />}

      {!loading && loadError != null && (
        <LoadError what="jobs" error={loadError} onRetry={load} />
      )}

      {!loading && loadError == null && jobs.length === 0 && (
        <EmptyState icon={CalendarClock} title="Nothing is scheduled yet."
          description="Set a refresh interval on a dataset or dataflow, or add a schedule or alert from a report, and it appears here." />
      )}
      {noMatches && <p style={{ color: 'var(--muted)' }}>No jobs match.</p>}

      {!loading && loadError == null && filtered.length > 0 && (
        <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ textAlign: 'start', color: 'var(--muted)' }}>
              <th style={{ padding: '6px 8px' }}>Kind</th>
              <th style={{ padding: '6px 8px' }}>Name</th>
              <th style={{ padding: '6px 8px' }}>Schedule</th>
              <th style={{ padding: '6px 8px' }}>Last run</th>
              <th style={{ padding: '6px 8px' }}>Status</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map(j => {
              const tone = statusTone(j.status)
              return (
                <tr key={`${j.kind}-${j.id}`} style={{ borderTop: '1px solid var(--border)' }}>
                  <td style={{ padding: '6px 8px', whiteSpace: 'nowrap' }}>
                    <span aria-hidden style={{ display: 'inline-flex', verticalAlign: -2,
                      marginInlineEnd: 6, color: 'var(--muted)' }}>
                      {(() => { const I = KIND_ICON[j.kind]; return <I size={13} /> })()}
                    </span>
                    {KIND_LABEL[j.kind]}
                  </td>
                  <td style={{ padding: '6px 8px', fontWeight: 600 }}>
                    {jobLink(j) != null
                      ? <Link to={jobLink(j)!} style={{ color: 'var(--text)' }}>{j.name}</Link>
                      : j.name}
                  </td>
                  <td style={{ padding: '6px 8px', whiteSpace: 'nowrap' }}>{interval(j.interval_minutes)}</td>
                  <td style={{ padding: '6px 8px', whiteSpace: 'nowrap' }}>
                    {j.last_run_at ? new Date(j.last_run_at).toLocaleString() : 'never'}
                  </td>
                  <td style={{ padding: '6px 8px', color: tone ? TONE_COLOR[tone] : 'var(--muted)' }}
                    title={j.error ?? undefined}>
                    {j.status ?? '—'}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
    </div>
  )
}
