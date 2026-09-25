import type { TranslateFn } from '../../i18n'
import type { Job } from '../../services/api'

/** One short status line for a job, in the reader's language. */
export function jobStateLabel(job: Job, t: TranslateFn): string {
  if (job.state === 'running' && job.cancel_requested) return t('importJobs.state.stopping')
  return t(`importJobs.state.${job.state}` as Parameters<TranslateFn>[0])
}

/** What a running job is doing now; null when there is nothing to add. */
export function jobStageLabel(job: Job, t: TranslateFn): string | null {
  if (job.state !== 'running' || job.cancel_requested) return null
  const stage = job.progress?.stage
  if (stage === 'querying') return t('importJobs.stage.querying')
  if (stage === 'writing') return t('importJobs.stage.writing', { rows: (job.progress?.rows ?? 0).toLocaleString() })
  if (stage === 'saving') return t('importJobs.stage.saving')
  return t('importJobs.stage.starting')
}

/** The chip modifier for a state: success, failure, or neutral. */
export function jobTone(job: Job): 'ok' | 'fail' | 'neutral' {
  if (job.state === 'succeeded') return 'ok'
  if (job.state === 'failed') return 'fail'
  return 'neutral'
}
