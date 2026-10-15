/**
 * C-17: "this session just changed report N".
 *
 * Every write to a report bumps its revision on the server, and the builder's
 * poll reads a revision it did not know of as "changed in another session".
 * Each write path used to have to remember to re-sync the known revision
 * afterwards; the ones that did not (a classification, a panel's own write)
 * raised the banner on the author's own edit. Announced here once, from the
 * API client's response hook, for every successful write the session makes,
 * so the builder can sync after any of them.
 *
 * Its own module (not services/api) so the many tests that mock the API
 * client keep working without listing it.
 */
export const REPORT_WRITE_EVENT = 'datalytics:report-write'

export interface ReportWriteDetail { reportId: number }

const WRITES = new Set(['post', 'put', 'patch', 'delete'])

/** The report a successful request wrote to, or null. */
export function reportWritten(config: { method?: string; url?: string } | undefined): number | null {
  if (!config || !WRITES.has(String(config.method ?? 'get').toLowerCase())) return null
  const m = /^\/?reports\/(\d+)(?:[/?]|$)/.exec(config.url ?? '')
  return m ? Number(m[1]) : null
}

export function announceReportWrite(config: { method?: string; url?: string } | undefined): void {
  const reportId = reportWritten(config)
  if (reportId == null || typeof window === 'undefined') return
  window.dispatchEvent(new CustomEvent<ReportWriteDetail>(REPORT_WRITE_EVENT, { detail: { reportId } }))
}
