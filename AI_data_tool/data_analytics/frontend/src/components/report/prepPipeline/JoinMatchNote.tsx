/**
 * How a join will land, shown while it is being configured -- the geography
 * check's pattern applied to joins: the share of rows that find a partner,
 * the key values that do not, and keys that repeat on the other side (the
 * silent row multiplier).
 */
import { useEffect, useState } from 'react'
import { prepApi, type JoinCheck, type PrepStep } from '../../../services/api'
import { formatDate } from '../../../lib/dateFormat'
import { useT, type TranslateFn } from '../../../i18n'
import { tNodes } from './tNodes'

/** A key list the backend will accept: at least one pair with both sides named. */
function hasKeyPair(step: PrepStep): boolean {
  if (step.left_on && step.right_on) return true
  const l = Array.isArray(step.left_ons) ? step.left_ons as unknown[] : []
  const r = Array.isArray(step.right_ons) ? step.right_ons as unknown[] : []
  return l.some((v, i) => typeof v === 'string' && v.trim() !== '' && typeof r[i] === 'string' && (r[i] as string).trim() !== '')
}

function ago(iso: string, t: TranslateFn): string {
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000)
  return days <= 0 ? t('pg.panelsB.join.today') : days === 1 ? t('pg.panelsB.join.yesterday')
    : t('pg.panelsB.join.daysAgo', { n: days.toLocaleString() })
}

export default function JoinMatchNote({ datasetId, steps, index, joined }: {
  datasetId: number; steps: PrepStep[]; index: number
  /** The dataset being joined in, for its freshness (E06). */
  joined?: { name: string; last_refreshed_at?: string | null } | null
}) {
  const t = useT()
  const step = steps[index] ?? {}
  const ready = typeof step.dataset_id === 'number' || (typeof step.dataset_id === 'string' && step.dataset_id !== '')
  // `left_ons: ['']` is the editor mid-edit, not a key: checking it answered
  // with a red "needs a key column" while the author was still choosing.
  const keyed = hasKeyPair(step)
  const sig = JSON.stringify(steps.slice(0, index + 1))
  const [check, setCheck] = useState<JoinCheck | null>(null)
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => {
    setCheck(null); setErr(null)
    if (!ready || !keyed) return
    let live = true
    const timer = setTimeout(() => {
      const sent = steps.slice(0, index + 1).map((s, i) => (i === index ? { ...s, dataset_id: Number(s.dataset_id) } : s))
      prepApi.joinCheck(datasetId, sent, index)
        .then(r => { if (live) setCheck(r) })
        .catch(e => { if (live) setErr(e?.response?.data?.detail ?? t('pg.panelsB.join.checkFailed')) })
    }, 400)
    return () => { live = false; clearTimeout(timer) }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [datasetId, sig, index, ready, keyed])
  if (!ready || !keyed) return null
  if (err) return <div role="alert" style={{ fontSize: 10.5, color: 'var(--danger)', marginTop: 6 }}>{err}</div>
  if (!check) return <div style={{ fontSize: 10.5, color: 'var(--muted)', marginTop: 6 }}>{t('pg.panelsB.join.checking')}</div>
  if (check.error) return <div role="alert" style={{ fontSize: 10.5, color: 'var(--danger)', marginTop: 6 }}>{check.error}</div>
  const good = check.pct_rows === 100 && check.duplicate_right_keys === 0 && check.type_mismatch.length === 0
  return (
    <div data-testid="join-match" role="status" style={{ fontSize: 10.5, marginTop: 6, padding: '6px 8px', borderRadius: 6,
      border: `1px solid ${good ? 'var(--border)' : 'var(--warning, #d68910)'}` }}>
      <div>{tNodes(t, 'pg.panelsB.join.match', { matched: check.matched_rows.toLocaleString(), rows: check.rows.toLocaleString() },
        { pct: <b style={{ fontSize: 13 }}>{check.pct_rows}%</b> })}</div>
      {check.unmatched.length > 0 && (
        <div style={{ color: 'var(--muted)' }}>
          {tNodes(t, 'pg.panelsB.join.unmatched', { n: check.unmatched_values.toLocaleString() }, {
            list: <><bdi>{check.unmatched.slice(0, 4).map(u => `${u.key} (${u.rows.toLocaleString()})`).join(t('pg.panelsB.listSep'))}</bdi>{check.unmatched_values > 4 ? '…' : ''}</>,
          })}
        </div>
      )}
      {check.blank_keys > 0 && <div style={{ color: 'var(--muted)' }}>{t('pg.panelsB.join.blank', { n: check.blank_keys.toLocaleString() })}</div>}
      {check.duplicate_right_keys > 0 && (
        <div style={{ color: 'var(--danger)' }}>
          {tNodes(t, check.rows_after != null ? 'pg.panelsB.join.dupGrow' : 'pg.panelsB.join.dup', {
            n: check.duplicate_right_keys.toLocaleString(), rows: check.rows.toLocaleString(),
            after: (check.rows_after ?? 0).toLocaleString(),
          }, { examples: <bdi>{check.duplicate_examples.map(d => `${d.key} ×${d.count}`).join(t('pg.panelsB.listSep'))}</bdi> })}
        </div>
      )}
      {check.type_mismatch.length > 0 && (
        <div style={{ color: 'var(--danger)' }}>{tNodes(t, 'pg.panelsB.join.typeMismatch', {}, { cols: <bdi>{check.type_mismatch.join('; ')}</bdi> })}</div>
      )}
      {/* E06: fan-out as a plain figure, for every join type -- not only when a
          duplicate key happens to explain it. */}
      {check.rows_after != null && (
        <div data-testid="join-fanout" style={{ color: (check.multiplier ?? 1) > 1 ? 'var(--warning, #d68910)' : 'var(--muted)' }}>
          {check.multiplier != null && check.multiplier !== 1
            ? t('pg.panelsB.join.after', { n: check.rows_after.toLocaleString(), m: check.multiplier.toLocaleString() })
            : t('pg.panelsB.join.afterOne', { n: check.rows_after.toLocaleString() })}
        </div>
      )}
      {(check.right_unmatched_rows ?? 0) > 0 && (
        <div style={{ color: 'var(--muted)' }}>
          {t(step.how === 'right' || step.how === 'full' ? 'pg.panelsB.join.rightKept' : 'pg.panelsB.join.rightLeft',
            { n: check.right_unmatched_rows!.toLocaleString(), total: check.right_rows?.toLocaleString() ?? '' })}
        </div>
      )}
      {joined && (
        <div data-testid="join-freshness" style={{ color: 'var(--muted)' }}>
          {joined.last_refreshed_at
            ? t('pg.panelsB.join.loaded', { name: joined.name, ago: ago(joined.last_refreshed_at, t), date: formatDate(joined.last_refreshed_at, 'date') })
            : t('pg.panelsB.join.noLoad', { name: joined.name })}
        </div>
      )}
    </div>
  )
}
