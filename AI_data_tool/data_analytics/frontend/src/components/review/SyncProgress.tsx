import type { SyncRun } from '../../services/api'
import { friendlyMessage } from '../../lib/friendlyError'

/**
 * Per-stage outcome of a metadata sync.
 *
 * Shows every stage rather than a single overall verdict, because the stages
 * fail independently by design: a source that blocks sampling still produced
 * statistics and a drift check, and "partial" on its own would misrepresent
 * that as a failure. The reader needs to know WHICH part did not run.
 */

const STAGE_LABELS: Record<string, string> = {
  discover: 'Discover tables',
  profile: 'Profile columns',
  sample: 'Sample rows',
  infer_keys: 'Infer relationships',
  infer_semantic: 'Infer meaning',
  drift: 'Check for schema drift',
}

const STATUS_COLOR: Record<string, string> = {
  ok: '#16785a',
  failed: '#b03a32',
  skipped: '#64748b',
}

function stageDetail(name: string, detail?: Record<string, any>): string | null {
  if (!detail) return null
  if (name === 'infer_keys' && detail.proposed != null) {
    return `${detail.proposed} proposed (${detail.high_confidence ?? 0} high confidence)`
  }
  if (name === 'profile' && detail.columns_profiled != null) {
    return `${detail.columns_profiled} columns`
  }
  if (name === 'infer_semantic') {
    const parts: string[] = []
    if (detail.semantic_types) parts.push(`${detail.semantic_types} typed`)
    if (detail.descriptions) parts.push(`${detail.descriptions} described`)
    if (detail.llm_used === false) parts.push('model not used')
    return parts.join(', ') || null
  }
  if (name === 'drift') {
    if (detail.changed === false) return 'no change'
    return detail.summary ?? null
  }
  if (detail.reason) return detail.reason
  return null
}

export default function SyncProgress({ run }: { run: SyncRun | null }) {
  if (!run || run.status === 'never_run') {
    return (
      <p style={{ color: '#64748b', fontSize: 13 }}>
        This source has not been synced yet. Run a sync to build its metadata.
      </p>
    )
  }

  return (
    <div>
      <div style={{ fontSize: 13, marginBottom: 8 }}>
        Last run: <strong>{run.status}</strong>
        {run.finished_at && <> · {new Date(run.finished_at).toLocaleString()}</>}
      </div>
      <ol style={{ listStyle: 'none', padding: 0, margin: 0, fontSize: 13 }}>
        {run.stages.map(stage => {
          const detail = stageDetail(stage.name, stage.detail)
          return (
            <li key={stage.name} style={{ display: 'flex', gap: 10, padding: '4px 0' }}>
              <span style={{ color: STATUS_COLOR[stage.status] ?? '#64748b', fontWeight: 600, minWidth: 62 }}>
                {stage.status}
              </span>
              <span style={{ minWidth: 170 }}>{STAGE_LABELS[stage.name] ?? stage.name}</span>
              <span style={{ color: '#64748b' }}>
                {stage.error ? <Friendly text={stage.error} /> : detail}
                {stage.ms != null && stage.status !== 'skipped' && ` · ${stage.ms}ms`}
              </span>
            </li>
          )
        })}
      </ol>
      {/* The same run error usually repeats on the failed stage; a driver
          message is rewritten once, here, and the raw text stays a click away. */}
      {run.error && !run.stages.some(s => s.error === run.error) && (
        <p style={{ color: '#b03a32', fontSize: 13, marginTop: 8 }}><Friendly text={run.error} /></p>
      )}
    </div>
  )
}

/** A driver error in plain words, with the original behind "Technical details". */
function Friendly({ text }: { text: string }) {
  const nice = friendlyMessage(text)
  if (nice === text) return <>{text}</>
  return (
    <span>
      {nice}
      <details className="dl-conn-test__raw" style={{ display: 'inline-block', marginInlineStart: 8, verticalAlign: 'top' }}>
        <summary>Technical details</summary>
        <pre>{text}</pre>
      </details>
    </span>
  )
}

