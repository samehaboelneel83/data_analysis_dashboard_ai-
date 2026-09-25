import { useState } from 'react'
import toast from 'react-hot-toast'
import { useNavigate } from 'react-router-dom'
import { useT } from '../../i18n'
import { isJobActive, jobsApi, type Job } from '../../services/api'
import { jobStageLabel, jobStateLabel, jobTone } from './jobText'

/**
 * One import job: what it is doing, and the one or two things you can do
 * about it. Shared by the schema browser (the job you just started) and the
 * Connections page's Imports list (every recent one), so both say the same
 * thing about the same job.
 *
 * `onChange` receives the job as the server returns it after a cancel, or the
 * NEW job a retry creates -- the caller decides whether to follow it.
 */
export default function ImportJobRow({ job, onChange, compact = false }: {
  job: Job
  onChange?: (job: Job) => void
  compact?: boolean
}) {
  const t = useT()
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false)
  const tone = jobTone(job)
  const stage = jobStageLabel(job, t)
  const datasetId = job.result?.dataset_id

  const cancel = async () => {
    setBusy(true)
    try { onChange?.(await jobsApi.cancel(job.id)) }
    catch { toast.error(t('importJobs.cancelFailed')) }
    finally { setBusy(false) }
  }
  const retry = async () => {
    setBusy(true)
    try {
      const fresh = await jobsApi.retry(job.id)
      toast.success(t('importJobs.retried'))
      onChange?.(fresh)
    } catch { toast.error(t('importJobs.retryFailed')) }
    finally { setBusy(false) }
  }

  return (
    <div className="dl-job" role="group" aria-label={job.subject ?? t('importJobs.title')}>
      <div className="dl-job__body">
        {!compact && <div className="dl-job__subject">{job.subject}</div>}
        <div className="dl-job__line" aria-live="polite">
          <span className={`dl-job__state dl-job__state--${tone}`}>{jobStateLabel(job, t)}</span>
          {stage && <span>{stage}</span>}
          {job.state === 'succeeded' && job.result?.row_count != null && (
            <span>{t('importJobs.doneRows', { rows: job.result.row_count.toLocaleString() })}</span>
          )}
          {job.state === 'succeeded' && job.cancel_requested && (
            <span>{t('importJobs.finishedBeforeCancel')}</span>
          )}
          {isJobActive(job) && job.progress?.resumed && <span>{t('importJobs.resumed')}</span>}
          {isJobActive(job) && job.attempt > 1 && (
            <span>{t('importJobs.attempt', { n: job.attempt, max: job.max_attempts })}</span>
          )}
        </div>
        {job.state === 'failed' && job.error && (
          <div className="dl-job__error" role="alert">{job.error}</div>
        )}
      </div>
      <div className="dl-job__actions">
        {isJobActive(job) && !job.cancel_requested && (
          <button type="button" className="btn btn-ghost btn-sm" onClick={cancel} disabled={busy}>
            {t('importJobs.cancel')}
          </button>
        )}
        {(job.state === 'failed' || job.state === 'cancelled') && (
          <button type="button" className="btn btn-ghost btn-sm" onClick={retry} disabled={busy}>
            {t('importJobs.retry')}
          </button>
        )}
        {job.state === 'succeeded' && datasetId != null && (
          <button type="button" className="btn btn-ghost btn-sm"
            onClick={() => navigate(`/datasets/${datasetId}`)}>
            {t('importJobs.open')}
          </button>
        )}
      </div>
    </div>
  )
}
