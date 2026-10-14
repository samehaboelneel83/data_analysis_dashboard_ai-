import { useCallback, useEffect, useState } from 'react'
import { useT } from '../../i18n'
import { isJobActive, jobsApi, type Job } from '../../services/api'
import ImportJobRow from './ImportJobRow'
import { JOB_POLL_MS } from './useJob'

/** How many recent imports the list keeps on screen. */
export const IMPORT_QUEUE_LIMIT = 8
const DISMISS_KEY = 'datalytics:import-dismissed'

/**
 * The organisation's recent database imports (an admin sees everyone's; the
 * API decides), newest first. Re-read while any is still queued or running,
 * and whenever `refreshKey` changes -- the page bumps it after starting one.
 * Renders nothing until there is something to show.
 */
export default function ImportQueue({ refreshKey = 0 }: { refreshKey?: number }) {
  const t = useT()
  const [jobs, setJobs] = useState<Job[]>([])

  const load = useCallback(async () => {
    try { setJobs(await jobsApi.list({ kind: 'dataset.import', limit: IMPORT_QUEUE_LIMIT })) }
    catch { /* the list is a convenience; the page works without it */ }
  }, [])

  useEffect(() => { void load() }, [load, refreshKey])

  const anyActive = jobs.some(isJobActive)
  useEffect(() => {
    if (!anyActive) return
    const id = setInterval(() => { void load() }, JOB_POLL_MS * 2)
    return () => clearInterval(id)
  }, [anyActive, load])

  // 4.7 / 5.4: a finished import from yesterday -- above all a failed test
  // one -- is noise in front of a newcomer. Kept a click away, never deleted;
  // a dismissed row stays dismissed on this browser.
  const [showOld, setShowOld] = useState(false)
  const [dismissed, setDismissed] = useState<number[]>(() => {
    try { return JSON.parse(localStorage.getItem(DISMISS_KEY) ?? '[]') } catch { return [] }
  })
  const dismiss = (id: number) => setDismissed(d => {
    const next = [...d, id].slice(-200)
    try { localStorage.setItem(DISMISS_KEY, JSON.stringify(next)) } catch { /* not remembered */ }
    return next
  })
  const DAY = 24 * 3600_000
  const stale = (j: Job) => !isJobActive(j) && (dismissed.includes(j.id)
    || (!!j.created_at && Date.now() - Date.parse(j.created_at) > DAY))
  const oldFailed = jobs.filter(stale).length
  const shown = showOld ? jobs : jobs.filter(j => !stale(j))
  if (shown.length === 0 && oldFailed === 0) return null
  return (
    <section className="card dl-jobs" aria-labelledby="import-queue-title">
      <h2 id="import-queue-title" className="dl-jobs__title">{t('importJobs.title')}</h2>
      <p className="dl-jobs__sub">{t('importJobs.sub')}</p>
      {shown.map(j => (
        <div key={j.id} style={{ position: 'relative' }}>
          <ImportJobRow job={j} onChange={() => { void load() }} />
          {!isJobActive(j) && !dismissed.includes(j.id) && (
            <button type="button" className="btn btn-ghost btn-sm" aria-label={t('importJobs.dismiss', { name: j.subject ?? '' })}
              title={t('importJobs.dismissTitle')} onClick={() => dismiss(j.id)}
              style={{ position: 'absolute', top: 4, insetInlineEnd: 4, fontSize: 11, padding: '0 6px' }}>×</button>
          )}
        </div>
      ))}
      {oldFailed > 0 && (
        <button type="button" className="btn btn-ghost btn-sm" style={{ fontSize: 11.5 }}
          onClick={() => setShowOld(v => !v)}>
          {showOld ? t('importJobs.hideOldFailed') : t('importJobs.showOldFailed', { n: oldFailed })}
        </button>
      )}
    </section>
  )
}
