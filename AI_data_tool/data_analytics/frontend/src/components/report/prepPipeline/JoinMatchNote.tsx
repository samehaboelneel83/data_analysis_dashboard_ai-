/**
 * How a join will land, shown while it is being configured -- the geography
 * check's pattern applied to joins: the share of rows that find a partner,
 * the key values that do not, and keys that repeat on the other side (the
 * silent row multiplier).
 */
import { useEffect, useState } from 'react'
import { prepApi, type JoinCheck, type PrepStep } from '../../../services/api'
import { formatDate } from '../../../lib/dateFormat'

/** A key list the backend will accept: at least one pair with both sides named. */
function hasKeyPair(step: PrepStep): boolean {
  if (step.left_on && step.right_on) return true
  const l = Array.isArray(step.left_ons) ? step.left_ons as unknown[] : []
  const r = Array.isArray(step.right_ons) ? step.right_ons as unknown[] : []
  return l.some((v, i) => typeof v === 'string' && v.trim() !== '' && typeof r[i] === 'string' && (r[i] as string).trim() !== '')
}

function ago(iso: string): string {
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000)
  return days <= 0 ? 'today' : days === 1 ? 'yesterday' : `${days.toLocaleString()} days ago`
}

export default function JoinMatchNote({ datasetId, steps, index, joined }: {
  datasetId: number; steps: PrepStep[]; index: number
  /** The dataset being joined in, for its freshness (E06). */
  joined?: { name: string; last_refreshed_at?: string | null } | null
}) {
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
    const t = setTimeout(() => {
      const sent = steps.slice(0, index + 1).map((s, i) => (i === index ? { ...s, dataset_id: Number(s.dataset_id) } : s))
      prepApi.joinCheck(datasetId, sent, index)
        .then(r => { if (live) setCheck(r) })
        .catch(e => { if (live) setErr(e?.response?.data?.detail ?? 'Could not check this join') })
    }, 400)
    return () => { live = false; clearTimeout(t) }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [datasetId, sig, index, ready, keyed])
  if (!ready || !keyed) return null
  if (err) return <div role="alert" style={{ fontSize: 10.5, color: 'var(--danger)', marginTop: 6 }}>{err}</div>
  if (!check) return <div style={{ fontSize: 10.5, color: 'var(--muted)', marginTop: 6 }}>Checking the keys…</div>
  if (check.error) return <div role="alert" style={{ fontSize: 10.5, color: 'var(--danger)', marginTop: 6 }}>{check.error}</div>
  const good = check.pct_rows === 100 && check.duplicate_right_keys === 0 && check.type_mismatch.length === 0
  return (
    <div data-testid="join-match" role="status" style={{ fontSize: 10.5, marginTop: 6, padding: '6px 8px', borderRadius: 6,
      border: `1px solid ${good ? 'var(--border)' : 'var(--warning, #d68910)'}` }}>
      <div><b style={{ fontSize: 13 }}>{check.pct_rows}%</b> of rows find a match ({check.matched_rows.toLocaleString()} of {check.rows.toLocaleString()})</div>
      {check.unmatched.length > 0 && (
        <div style={{ color: 'var(--muted)' }}>
          {check.unmatched_values.toLocaleString()} key value{check.unmatched_values === 1 ? '' : 's'} with no partner:{' '}
          {check.unmatched.slice(0, 4).map(u => `${u.key} (${u.rows.toLocaleString()})`).join(', ')}{check.unmatched_values > 4 ? '…' : ''}
        </div>
      )}
      {check.blank_keys > 0 && <div style={{ color: 'var(--muted)' }}>{check.blank_keys.toLocaleString()} rows have a blank key.</div>}
      {check.duplicate_right_keys > 0 && (
        <div style={{ color: 'var(--danger)' }}>
          ⚠ {check.duplicate_right_keys.toLocaleString()} key{check.duplicate_right_keys === 1 ? '' : 's'} appear more than once on the other side
          ({check.duplicate_examples.map(d => `${d.key} ×${d.count}`).join(', ')}) — joining repeats those rows
          {check.rows_after != null ? `: ${check.rows.toLocaleString()} rows become ${check.rows_after.toLocaleString()}` : ''}.
        </div>
      )}
      {check.type_mismatch.length > 0 && (
        <div style={{ color: 'var(--danger)' }}>⚠ A number is joined to text ({check.type_mismatch.join('; ')}): values that look equal will not match. Change one column’s type first.</div>
      )}
      {/* E06: fan-out as a plain figure, for every join type -- not only when a
          duplicate key happens to explain it. */}
      {check.rows_after != null && (
        <div data-testid="join-fanout" style={{ color: (check.multiplier ?? 1) > 1 ? 'var(--warning, #d68910)' : 'var(--muted)' }}>
          Rows after the join: {check.rows_after.toLocaleString()}
          {check.multiplier != null && check.multiplier !== 1 ? ` (×${check.multiplier.toLocaleString()})` : ' (one row each)'}
        </div>
      )}
      {(check.right_unmatched_rows ?? 0) > 0 && (
        <div style={{ color: 'var(--muted)' }}>
          {check.right_unmatched_rows!.toLocaleString()} of {check.right_rows?.toLocaleString()} rows of the joined data find no partner here
          {step.how === 'right' || step.how === 'full' ? ' and are kept with blank values.' : ' and are left out.'}
        </div>
      )}
      {joined && (
        <div data-testid="join-freshness" style={{ color: 'var(--muted)' }}>
          {joined.last_refreshed_at
            ? `“${joined.name}” was last loaded ${ago(joined.last_refreshed_at)} (${formatDate(joined.last_refreshed_at, 'date')}).`
            : `“${joined.name}” has no load time recorded.`}
        </div>
      )}
    </div>
  )
}
