import { useCallback, useEffect, useRef, useState } from 'react'
import { isJobActive, jobsApi, type Job } from '../../services/api'

/** How often an active job is re-read. The server moves it, not this page. */
export const JOB_POLL_MS = 1500

/**
 * Follow one durable job until it finishes.
 *
 * Polls while the job is queued or running and stops at a terminal state. A
 * failed read is retried on the next tick rather than shown: the job keeps
 * running on the server whatever this page's network does. `onSettled` fires
 * once, when the job first reaches a terminal state.
 */
export function useJob(jobId: number | null, onSettled?: (job: Job) => void) {
  const [job, setJob] = useState<Job | null>(null)
  const settledRef = useRef<number | null>(null)
  const onSettledRef = useRef(onSettled)
  onSettledRef.current = onSettled

  const accept = useCallback((j: Job) => {
    setJob(j)
    if (!isJobActive(j) && settledRef.current !== j.id) {
      settledRef.current = j.id
      onSettledRef.current?.(j)
    }
  }, [])

  useEffect(() => {
    if (jobId == null) { setJob(null); return }
    let alive = true
    let timer: ReturnType<typeof setTimeout> | undefined
    const tick = async () => {
      try {
        const j = await jobsApi.get(jobId)
        if (!alive) return
        accept(j)
        if (!isJobActive(j)) return
      } catch { /* transient: try again next tick */ }
      if (alive) timer = setTimeout(tick, JOB_POLL_MS)
    }
    void tick()
    return () => { alive = false; if (timer) clearTimeout(timer) }
  }, [jobId, accept])

  return { job, setJob: accept }
}
