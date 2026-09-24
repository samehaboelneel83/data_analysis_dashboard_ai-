/**
 * How a join will land, shown while it is being configured -- the geography
 * check's pattern applied to joins: the share of rows that find a partner,
 * the key values that do not, and keys that repeat on the other side (the
 * silent row multiplier).
 */
import { useEffect, useState } from 'react'
import { prepApi, type JoinCheck, type PrepStep } from '../../../services/api'

export default function JoinMatchNote({ datasetId, steps, index }: {
  datasetId: number; steps: PrepStep[]; index: number
}) {
  const step = steps[index] ?? {}
  const ready = typeof step.dataset_id === 'number' || (typeof step.dataset_id === 'string' && step.dataset_id !== '')
  const keyed = !!(step.left_on && step.right_on) || (Array.isArray(step.left_ons) && (step.left_ons as unknown[]).length > 0)
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
    </div>
  )
}
