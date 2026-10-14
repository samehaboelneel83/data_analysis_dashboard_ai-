import type { ActivityRow, DatasetSummary, RefreshRunRow } from '../../services/api'
import type { Report } from '../../types/report'
import type { MessageKey } from '../../i18n'

/**
 * What Home's two admin cards say, from the org's general activity log and the
 * refresh-run history. Both endpoints are org-admin only; Home does not call
 * them for anyone else.
 */

/** The audit actions Home can put in a sentence. The log records many more
 *  (logins, migration steps, embed configs …); those stay on the Activity page
 *  rather than appearing here as raw action codes. */
const SENTENCE: Record<string, MessageKey> = {
  'dataset.upload': 'hm.act.upload',
  'dataset.refresh': 'hm.act.refresh',
  'dataset.share_created': 'hm.act.share',
  'report.create': 'hm.act.create',
  'report.publish': 'hm.act.publish',
  'report.unpublish': 'hm.act.unpublish',
  'report.share': 'hm.act.share',
  'report.release': 'hm.act.release',
  'report.restore_version': 'hm.act.restore',
  'report.delete': 'hm.act.delete',
}

export interface FeedItem {
  id: number
  who: string
  mine: boolean
  key: MessageKey
  name: string
  at: string
}

/** The person's name as the app shows it everywhere else: the email's local part. */
export const handle = (email: string | null | undefined) => (email ?? '').split('@')[0] || '?'

export function feedItems(rows: ActivityRow[], me: string | null | undefined,
  reports: Report[], datasets: DatasetSummary[], max = 5): FeedItem[] {
  const out: FeedItem[] = []
  for (const r of rows) {
    const key = SENTENCE[r.action]
    if (!key) continue
    const byId = r.entity === 'dataset'
      ? datasets.find(d => d.id === r.entity_id)?.name
      : r.entity === 'report' ? reports.find(x => x.id === r.entity_id)?.name : undefined
    // An upload's detail reads "file.csv -> 300 rows, 3 columns"; a deleted
    // report's detail is its name. Prefer the live name when it still exists.
    const name = byId ?? (r.detail ?? '').split(' -> ')[0]
    if (!name) continue
    out.push({ id: r.id, who: handle(r.user_email), mine: !!me && r.user_email === me, key, name, at: r.created_at })
    if (out.length >= max) break
  }
  return out
}

const DAY = 24 * 3600_000

export interface JobsDigest {
  ok: number
  running: number
  failed: number
  /** The runs worth naming: failures first, then what is running, then the latest success. */
  shown: RefreshRunRow[]
  /** Runs in the window at all. */
  total: number
  /** Any run in the history at all ("No jobs yet" vs "none in 24 hours"). */
  any: boolean
}

export function jobsDigest(runs: RefreshRunRow[], now = Date.now()): JobsDigest {
  const recent = runs.filter(r => r.started_at && now - new Date(r.started_at).getTime() <= DAY)
  const failedish = (r: RefreshRunRow) => r.status === 'failed' || r.status === 'blocked'
  const byTime = (a: RefreshRunRow, b: RefreshRunRow) =>
    new Date(b.started_at ?? 0).getTime() - new Date(a.started_at ?? 0).getTime()
  // One line per dataset or dataflow: its latest run decides how it reads.
  const latest = new Map<string, RefreshRunRow>()
  for (const r of [...recent].sort(byTime)) {
    const k = `${r.kind}:${r.item_id}`
    if (!latest.has(k)) latest.set(k, r)
  }
  const items = [...latest.values()]
  const shown = [
    ...items.filter(failedish),
    ...items.filter(r => r.status === 'running'),
    ...items.filter(r => r.status === 'ok').slice(0, 1),
  ].slice(0, 3)
  return {
    ok: recent.filter(r => r.status === 'ok').length,
    running: recent.filter(r => r.status === 'running').length,
    failed: recent.filter(failedish).length,
    shown,
    total: recent.length,
    any: runs.length > 0,
  }
}
