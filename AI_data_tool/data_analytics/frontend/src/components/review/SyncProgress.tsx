import { useT, type MessageKey, type TranslateFn } from '../../i18n'
import type { SyncRun } from '../../services/api'
import { useDirection } from '../../contexts/DirectionContext'
import { friendlyMessage } from '../../lib/friendlyError'

/**
 * Per-stage outcome of a metadata sync.
 *
 * Shows every stage rather than a single overall verdict, because the stages
 * fail independently by design: a source that blocks sampling still produced
 * statistics and a drift check, and "partial" on its own would misrepresent
 * that as a failure. The reader needs to know WHICH part did not run.
 */

const STAGE_LABELS: Record<string, MessageKey> = {
  discover: 'syp.stage.discover', profile: 'syp.stage.profile', sample: 'syp.stage.sample',
  infer_keys: 'syp.stage.inferKeys', infer_semantic: 'syp.stage.inferSemantic', drift: 'syp.stage.drift',
}
/** The server's status words (ok, failed, skipped, partial, running), in the reader's language. */
const STATUS_LABELS: Record<string, MessageKey> = {
  ok: 'syp.st.ok', failed: 'syp.st.failed', skipped: 'syp.st.skipped', partial: 'syp.st.partial',
  running: 'syp.st.running', pending: 'syp.st.pending',
}
const status = (t: TranslateFn, s: string) => (STATUS_LABELS[s] ? t(STATUS_LABELS[s]) : s)

const STATUS_COLOR: Record<string, string> = {
  ok: '#16785a',
  failed: '#b03a32',
  skipped: '#64748b',
}

function stageDetail(t: TranslateFn, name: string, detail?: Record<string, any>): string | null {
  if (!detail) return null
  if (name === 'infer_keys' && detail.proposed != null) {
    return t('syp.d.proposed', { n: detail.proposed, k: detail.high_confidence ?? 0 })
  }
  if (name === 'profile' && detail.columns_profiled != null) {
    return t('syp.d.columns', { n: detail.columns_profiled })
  }
  if (name === 'infer_semantic') {
    const parts: string[] = []
    if (detail.semantic_types) parts.push(t('syp.d.typed', { n: detail.semantic_types }))
    if (detail.descriptions) parts.push(t('syp.d.described', { n: detail.descriptions }))
    if (detail.llm_used === false) parts.push(t('syp.d.noModel'))
    return parts.join(', ') || null
  }
  if (name === 'drift') {
    if (detail.changed === false) return t('syp.d.noChange')
    return detail.summary ?? null
  }
  if (detail.reason) return detail.reason
  return null
}

export default function SyncProgress({ run }: { run: SyncRun | null }) {
  const t9 = useT()
  // The interface's language, not the browser's: "27م 4:07:09 2026/9/" on an
  // English page (live QA 2026-09-28).
  const { language } = useDirection()
  if (!run || run.status === 'never_run') {
    return (
      <p style={{ color: '#64748b', fontSize: 13 }}>
        {t9('syp.never')}
      </p>
    )
  }

  return (
    <div>
      <div style={{ fontSize: 13, marginBottom: 8 }}>
        {t9('syp.lastRun')} <strong>{status(t9, run.status)}</strong>
        {run.finished_at && <> · {new Date(run.finished_at).toLocaleString(language, { dateStyle: 'medium', timeStyle: 'medium' })}</>}
      </div>
      <ol style={{ listStyle: 'none', padding: 0, margin: 0, fontSize: 13 }}>
        {run.stages.map(stage => {
          const detail = stageDetail(t9, stage.name, stage.detail)
          return (
            <li key={stage.name} style={{ display: 'flex', gap: 10, padding: '4px 0' }}>
              <span style={{ color: STATUS_COLOR[stage.status] ?? '#64748b', fontWeight: 600, minWidth: 62 }}>
                {status(t9, stage.status)}
              </span>
              <span style={{ minWidth: 170 }}>{STAGE_LABELS[stage.name] ? t9(STAGE_LABELS[stage.name]) : stage.name}</span>
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
  const t9 = useT()
  const nice = friendlyMessage(text)
  if (nice === text) return <>{text}</>
  return (
    <span>
      {nice}
      <details className="dl-conn-test__raw" style={{ display: 'inline-block', marginInlineStart: 8, verticalAlign: 'top' }}>
        <summary>{t9('eb.details')}</summary>
        <pre>{text}</pre>
      </details>
    </span>
  )
}

