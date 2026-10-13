import type { SyncRun } from '../../services/api'
import { useDirection } from '../../contexts/DirectionContext'
import { friendlyMessage } from '../../lib/friendlyError'
import { useT, type MessageKey, type TranslateFn } from '../../i18n'
import { localDigits } from '../../lib/arabicFormats'

/**
 * Per-stage outcome of a metadata sync.
 *
 * Shows every stage rather than a single overall verdict, because the stages
 * fail independently by design: a source that blocks sampling still produced
 * statistics and a drift check, and "partial" on its own would misrepresent
 * that as a failure. The reader needs to know WHICH part did not run.
 */

const STAGE_LABELS: Record<string, MessageKey> = {
  discover: 'i2c.sp.discover',
  profile: 'i2c.sp.profile',
  sample: 'i2c.sp.sample',
  infer_keys: 'i2c.sp.inferKeys',
  infer_semantic: 'i2c.sp.inferSemantic',
  drift: 'i2c.sp.drift',
}

/** The words for a status the server sends; an unknown one shows as sent. */
const STATUS_LABELS: Record<string, MessageKey> = {
  ok: 'i2c.sp.st.ok', failed: 'i2c.sp.st.failed', skipped: 'i2c.sp.st.skipped',
  partial: 'i2c.sp.st.partial', running: 'i2c.sp.st.running',
}

const STATUS_COLOR: Record<string, string> = {
  ok: '#16785a',
  failed: '#b03a32',
  skipped: '#64748b',
}

function stageDetail(name: string, t: TranslateFn, detail?: Record<string, any>): string | null {
  if (!detail) return null
  if (name === 'infer_keys' && detail.proposed != null) {
    return t('i2c.sp.proposed', { n: localDigits(String(detail.proposed)), h: localDigits(String(detail.high_confidence ?? 0)) })
  }
  if (name === 'profile' && detail.columns_profiled != null) {
    return t('i2c.sp.columns', { n: localDigits(String(detail.columns_profiled)) })
  }
  if (name === 'infer_semantic') {
    const parts: string[] = []
    if (detail.semantic_types) parts.push(t('i2c.sp.typed', { n: localDigits(String(detail.semantic_types)) }))
    if (detail.descriptions) parts.push(t('i2c.sp.described', { n: localDigits(String(detail.descriptions)) }))
    if (detail.llm_used === false) parts.push(t('i2c.sp.noModel'))
    return parts.join(t('i2c.sp.sep')) || null
  }
  if (name === 'drift') {
    if (detail.changed === false) return t('i2c.sp.noChange')
    return detail.summary ?? null
  }
  if (detail.reason) return detail.reason
  return null
}

export default function SyncProgress({ run }: { run: SyncRun | null }) {
  // The interface's language, not the browser's: "27م 4:07:09 2026/9/" on an
  // English page (live QA 2026-09-28).
  const { language } = useDirection()
  const t = useT()
  if (!run || run.status === 'never_run') {
    return (
      <p style={{ color: '#64748b', fontSize: 13 }}>
        {t('i2c.sp.never')}
      </p>
    )
  }

  return (
    <div>
      <div style={{ fontSize: 13, marginBottom: 8 }}>
        {t('i2c.sp.lastRun')} <strong>{STATUS_LABELS[run.status] ? t(STATUS_LABELS[run.status]) : run.status}</strong>
        {run.finished_at && <> · {new Date(run.finished_at).toLocaleString(language, { dateStyle: 'medium', timeStyle: 'medium' })}</>}
      </div>
      <ol style={{ listStyle: 'none', padding: 0, margin: 0, fontSize: 13 }}>
        {run.stages.map(stage => {
          const detail = stageDetail(stage.name, t, stage.detail)
          return (
            <li key={stage.name} style={{ display: 'flex', gap: 10, padding: '4px 0' }}>
              <span style={{ color: STATUS_COLOR[stage.status] ?? '#64748b', fontWeight: 600, minWidth: 62 }}>
                {STATUS_LABELS[stage.status] ? t(STATUS_LABELS[stage.status]) : stage.status}
              </span>
              <span style={{ minWidth: 170 }}>{STAGE_LABELS[stage.name] ? t(STAGE_LABELS[stage.name]) : stage.name}</span>
              <span style={{ color: '#64748b' }}>
                {stage.error ? <Friendly text={stage.error} /> : detail}
                {stage.ms != null && stage.status !== 'skipped' && ` · ${t('i2c.sp.ms', { n: localDigits(String(stage.ms)) })}`}
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
  const t = useT()
  const nice = friendlyMessage(text)
  if (nice === text) return <>{text}</>
  return (
    <span>
      {nice}
      <details className="dl-conn-test__raw" style={{ display: 'inline-block', marginInlineStart: 8, verticalAlign: 'top' }}>
        <summary>{t('sb.tech')}</summary>
        <pre>{text}</pre>
      </details>
    </span>
  )
}

