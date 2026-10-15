import { useEffect, useState } from 'react'
import { useT, type MessageKey, type TranslateFn } from '../../i18n'
import { Link } from 'react-router-dom'
import { monitoringApi } from '../../services/api'
import type { MonitoringAutomationRunRow, MonitoringJobRow, RefreshRunRow } from '../../services/api'
import { useListFilter } from '../../components/ui/ListFilter'
import { RefreshCw, GitBranch, Mail, Bell, CalendarClock, type LucideIcon } from 'lucide-react'
import EmptyState from '../../components/ui/EmptyState'
import LoadError from '../../components/ui/LoadError'
import LoadingState from '../../components/ui/LoadingState'
import { formatDate } from '../../lib/dateFormat'

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
    // E12: the Dataflows page is back, opened on this dataflow.
    case 'dataflow': return `/dataflows?flow=${j.id}`
    case 'report_schedule': return j.report_id != null ? `/reports/${j.report_id}` : '/reports'
    case 'alert': return j.dataset_id != null ? `/datasets/${j.dataset_id}` : '/'
  }
}

const WEEKDAY: MessageKey[] = [
  'pg.dataPages.jobs.wd0', 'pg.dataPages.jobs.wd1', 'pg.dataPages.jobs.wd2', 'pg.dataPages.jobs.wd3',
  'pg.dataPages.jobs.wd4', 'pg.dataPages.jobs.wd5', 'pg.dataPages.jobs.wd6',
]
/** The job's schedule in words -- a calendar spec when there is one. */
function schedule(j: MonitoringJobRow, t: TranslateFn): string {
  const c = j.calendar
  if (c) {
    const at = `${String(c.hour).padStart(2, '0')}:${String(c.minute).padStart(2, '0')} ${j.timezone || 'UTC'}`
    const when = c.kind === 'weekly' ? t('pg.dataPages.jobs.weeklyAt', { day: t(WEEKDAY[c.weekday ?? 0]), at })
      : c.kind === 'monthly' ? t('pg.dataPages.jobs.monthlyAt', { day: c.monthday ?? 1, at })
      : t('pg.dataPages.jobs.dailyAt', { at })
    // AD-16: a calendar kept but switched off says so.
    return c.paused ? `${when} ${t('pg.dataPages.jobs.pausedSuffix')}` : when
  }
  return interval(j.interval_minutes, t)
}

function interval(minutes: number, t: TranslateFn): string {
  // Some rows carry 0 -- not scheduled, not "every 0 minutes" (AD-16: said, not "—").
  if (minutes <= 0) return t('pg.dataPages.jobs.paused')
  if (minutes % 1440 === 0) return minutes === 1440 ? t('pg.dataPages.jobs.daily') : t('pg.dataPages.jobs.everyDays', { n: minutes / 1440 })
  if (minutes % 60 === 0) return minutes === 60 ? t('pg.dataPages.jobs.hourly') : t('pg.dataPages.jobs.everyHours', { n: minutes / 60 })
  return t('pg.dataPages.jobs.everyMinutes', { n: minutes })
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

function duration(ms: number | null, t: TranslateFn): string {
  if (ms == null) return '—'
  if (ms < 1000) return t('pg.dataPages.jobs.ms', { n: ms })
  const s = ms / 1000
  return s < 60 ? t('pg.dataPages.jobs.seconds', { n: s.toFixed(1) })
    : t('pg.dataPages.jobs.minSec', { m: Math.floor(s / 60), s: Math.round(s % 60) })
}

/** AD-17: "pass 2 · warn 1" for a run's checks; '—' when none ran. */
function checksText(c: RefreshRunRow['checks_summary'], t: TranslateFn): string {
  if (!c) return '—'
  const parts = (['pass', 'warn', 'fail'] as const).filter(k => c[k] > 0)
    .map(k => t(`jobs.checks.${k}` as MessageKey, { n: c[k] }))
  return parts.length ? parts.join(' · ') : '—'
}

/** AD-17: automated analyses run too; "Everything that runs" lists them. */
function AutomationRuns() {
  const t = useT()
  const [runs, setRuns] = useState<MonitoringAutomationRunRow[] | null>(null)
  useEffect(() => {
    let live = true
    Promise.resolve().then(() => monitoringApi.automationRuns())
      .then(r => { if (live) setRuns(r ?? []) }).catch(() => { if (live) setRuns([]) })
    return () => { live = false }
  }, [])
  if (!runs || runs.length === 0) return null
  return (
    <section style={{ marginTop: 28 }} aria-labelledby="automation-runs-title" data-testid="automation-runs">
      <h2 id="automation-runs-title" style={{ margin: '0 0 8px', fontSize: 16 }}>{t('jobs.auto.title')}</h2>
      <div className="card dl-table-card"><table className="dl-table">
        <thead>
          <tr>
            <th>{t('jobs.history.started')}</th>
            <th>{t('col.name')}</th>
            <th>{t('col.status')}</th>
            <th>{t('jobs.auto.step')}</th>
          </tr>
        </thead>
        <tbody>
          {runs.map(r => {
            const tone = r.status === 'failed' ? 'bad' : r.status === 'done' ? 'ok' : 'info'
            return (
              <tr key={r.id}>
                <td style={{ whiteSpace: 'nowrap' }}>{r.started_at ? formatDate(r.started_at) : '—'}</td>
                <td style={{ fontWeight: 600 }}>
                  <Link to={`/automation?run=${r.id}`} className="row-name" style={{ color: 'var(--text)' }}>
                    {t('jobs.auto.run', { id: r.id })}
                  </Link>
                  {r.dataset_name && <span style={{ color: 'var(--muted)', fontWeight: 400 }}> · {r.dataset_name}</span>}
                </td>
                <td style={{ color: TONE_COLOR[tone] }}>{t(`auto.status.${r.status}` as MessageKey)}</td>
                <td>
                  {r.step ?? '—'}
                  {r.error && (
                    <div style={{ fontSize: 11.5, color: 'var(--muted)', marginTop: 2, whiteSpace: 'normal' }}>{r.error}</div>
                  )}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table></div>
    </section>
  )
}

/** Pipeline plan, phase 1: every refresh and dataflow run, newest first, so
 *  "why did Tuesday's refresh fail, and how long do they take?" has an answer
 *  on one page. "Failed only" is the question most visits ask. */
function RefreshHistory() {
  const t = useT()
  const [runs, setRuns] = useState<RefreshRunRow[]>([])
  const [failedOnly, setFailedOnly] = useState(false)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<unknown>(null)
  const load = () => {
    setLoading(true)
    setLoadError(null)
    return monitoringApi.refreshRuns(failedOnly ? { status: 'failed' } : {})
      .then(setRuns).catch(setLoadError).finally(() => setLoading(false))
  }
  useEffect(() => { load() }, [failedOnly])
  const statusText = (st: string) => { const k = `jobs.status.${st}` as MessageKey; const v = t(k); return v && v !== k ? v : st }
  const link = (r: RefreshRunRow) => r.kind === 'dataset' ? `/datasets/${r.item_id}` : `/dataflows?flow=${r.item_id}`

  return (
    <section style={{ marginTop: 28 }} aria-labelledby="refresh-history-title">
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 16, marginBottom: 8 }}>
        <h2 id="refresh-history-title" style={{ margin: 0, fontSize: 16 }}>{t('jobs.history.title')}</h2>
        <label style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 13 }}>
          <input type="checkbox" checked={failedOnly} onChange={e => setFailedOnly(e.target.checked)} />
          {t('jobs.history.failedOnly')}
        </label>
      </div>
      {loading && <LoadingState />}
      {!loading && loadError != null && <LoadError what="refresh history" title={t('pg.dataPages.jobs.historyLoadError')} error={loadError} onRetry={load} />}
      {!loading && loadError == null && runs.length === 0 && (
        <p style={{ color: 'var(--muted)' }}>{failedOnly ? t('jobs.history.noFailures') : t('jobs.history.empty')}</p>
      )}
      {!loading && loadError == null && runs.length > 0 && (
        <div className="card dl-table-card"><table className="dl-table" data-testid="refresh-history">
          <thead>
            <tr>
              <th>{t('jobs.history.started')}</th>
              <th>{t('col.name')}</th>
              <th>{t('jobs.history.trigger')}</th>
              <th>{t('col.status')}</th>
              <th style={{ textAlign: 'end' }}>{t('jobs.history.rows')}</th>
              <th style={{ textAlign: 'end' }}>{t('jobs.history.duration')}</th>
              <th>{t('jobs.history.checks')}</th>
            </tr>
          </thead>
          <tbody>
            {runs.map(r => {
              const tone = statusTone(r.status)
              return (
                <tr key={r.id}>
                  <td style={{ whiteSpace: 'nowrap' }}>{r.started_at ? formatDate(r.started_at) : '—'}</td>
                  <td style={{ fontWeight: 600 }}>
                    {r.name != null
                      ? <Link to={link(r)} className="row-name" style={{ color: 'var(--text)' }}>{r.name}</Link>
                      : <span style={{ color: 'var(--muted)' }}>{t('jobs.history.deleted')}</span>}
                  </td>
                  <td>{t(r.trigger === 'manual' ? 'jobs.history.manual' : 'jobs.history.schedule')}</td>
                  <td style={{ color: tone ? TONE_COLOR[tone] : 'var(--muted)' }}>
                    {statusText(r.status)}
                    {r.error && r.status !== 'ok' && (
                      <div style={{ fontSize: 11.5, color: 'var(--muted)', marginTop: 2, whiteSpace: 'normal' }}>{r.error}</div>
                    )}
                  </td>
                  <td style={{ textAlign: 'end', fontVariantNumeric: 'tabular-nums' }}>{r.rows != null ? r.rows.toLocaleString() : '—'}</td>
                  <td style={{ textAlign: 'end', whiteSpace: 'nowrap' }}>{duration(r.duration_ms, t)}</td>
                  <td style={{ whiteSpace: 'nowrap', color: r.checks_summary?.fail ? TONE_COLOR.bad
                    : r.checks_summary?.warn ? TONE_COLOR.info : undefined }}>{checksText(r.checks_summary, t)}</td>
                </tr>
              )
            })}
          </tbody>
        </table></div>
      )}
    </section>
  )
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
  // The server's reason, in the reader's words where it is a known one.
  const skipReason = (e: string) => {
    if (/no outputs yet/i.test(e)) return t('jobs.reason.noOutputs')
    if (/source dataset or creator is gone/i.test(e)) return t('jobs.reason.sourceGone')
    return e
  }
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
        <LoadError what="jobs" title={t('pg.dataPages.jobs.loadError')} error={loadError} onRetry={load} />
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
                  <td style={{ whiteSpace: 'nowrap' }}>{schedule(j, t)}</td>
                  <td style={{ whiteSpace: 'nowrap' }}>
                    {j.last_run_at ? formatDate(j.last_run_at) : t('jobs.never')}
                  </td>
                  <td style={{ color: tone ? TONE_COLOR[tone] : 'var(--muted)' }}
                    title={j.error ?? undefined}>
                    {j.status ? statusText(j.status) : '—'}
                    {/* 5.19: "skipped" alone left the reader guessing why. */}
                    {j.error && j.status && !/^(ok|clear)$/i.test(j.status) && (
                      <div data-testid={`job-reason-${j.kind}-${j.id}`} style={{ fontSize: 11.5, color: 'var(--muted)', marginTop: 2, whiteSpace: 'normal' }}>
                        {skipReason(j.error)}
                      </div>
                    )}
                    {j.next_retry_at && (
                      <div style={{ fontSize: 11.5, color: 'var(--muted)', marginTop: 2 }}>
                        {t('jobs.nextRetry', { when: formatDate(j.next_retry_at) })}
                      </div>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table></div>
      )}

      {!loading && loadError == null && <AutomationRuns />}
      {!loading && loadError == null && <RefreshHistory />}
    </div>
  )
}
