import { useCallback, useEffect, useState } from 'react'
import { useT } from '../../i18n'
import { isJobActive, jobsApi, type Job } from '../../services/api'
import ImportJobRow from './ImportJobRow'
import { JOB_POLL_MS } from './useJob'

/** How many recent imports the list keeps on screen. */
export const IMPORT_QUEUE_LIMIT = 8

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

  if (jobs.length === 0) return null
  return (
    <section className="card dl-jobs" aria-labelledby="import-queue-title">
      <h2 id="import-queue-title" className="dl-jobs__title">{t('importJobs.title')}</h2>
      <p className="dl-jobs__sub">{t('importJobs.sub')}</p>
      {jobs.map(j => (
        <ImportJobRow key={j.id} job={j} onChange={() => { void load() }} />
      ))}
    </section>
  )
}
