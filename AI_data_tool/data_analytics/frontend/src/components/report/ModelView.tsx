import { useEffect, useState } from 'react'
import type { Report } from '../../types/report'
import type { Dataset, Relationship } from '../../services/api'
import { relationshipsApi, type MappingCheck } from '../../services/api'

export default function ModelView({ report, datasets }: { report: Report; datasets: Record<number, Dataset> }) {
  const datasetIds = [report.dataset_id, ...(report.additional_dataset_ids ?? [])].filter((id): id is number => id != null)
  const [relationships, setRelationships] = useState<Relationship[]>([])
  const [showForm, setShowForm] = useState(false)

  useEffect(() => {
    relationshipsApi.list().then(all =>
      setRelationships(all.filter(r => datasetIds.includes(r.from_dataset_id) && datasetIds.includes(r.to_dataset_id)))
    )
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [report.id])

  if (datasetIds.length < 2) {
    return (
      <div data-testid="model-view" style={{ padding: 16 }}>
        <p style={{ color: 'var(--muted)', fontSize: 13 }}>
          Add a second dataset to this report to define relationships between them.
        </p>
      </div>
    )
  }

  return (
    <div data-testid="model-view" style={{ padding: 16 }}>
      <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', marginBottom: 20 }}>
        {datasetIds.map(id => (
          <div key={id} style={{ border: '1px solid var(--border)', borderRadius: 8, padding: 10, minWidth: 160, background: 'var(--surface)' }}>
            <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 6 }}>{datasets[id]?.name ?? `Dataset ${id}`}</div>
            {(datasets[id]?.columns ?? []).map(c => (
              <div key={c.name} style={{ fontSize: 11, color: 'var(--muted)' }}>{c.name}</div>
            ))}
          </div>
        ))}
      </div>

      <div style={{ marginBottom: 12 }}>
        {relationships.map(r => (
          <div key={r.id} style={{ fontSize: 12, marginBottom: 4 }}>
            {datasets[r.from_dataset_id]?.name}.{r.from_column} ↔ {datasets[r.to_dataset_id]?.name}.{r.to_column}
          </div>
        ))}
      </div>

      <button className="btn btn-primary btn-sm" onClick={() => setShowForm(true)}>+ Add relationship</button>

      {showForm && (
        <RelationshipForm
          datasetIds={datasetIds}
          datasets={datasets}
          onCreated={rel => { setRelationships(prev => [...prev, rel]); setShowForm(false) }}
          onCancel={() => setShowForm(false)}
        />
      )}
    </div>
  )
}

function RelationshipForm({ datasetIds, datasets, onCreated, onCancel }: {
  datasetIds: number[]
  datasets: Record<number, Dataset>
  onCreated: (r: Relationship) => void
  onCancel: () => void
}) {
  const [fromDs, setFromDs] = useState(datasetIds[0])
  const [fromCol, setFromCol] = useState('')
  const [toDs, setToDs] = useState(datasetIds[1] ?? datasetIds[0])
  const [toCol, setToCol] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [check, setCheck] = useState<MappingCheck | null>(null)
  const [checkErr, setCheckErr] = useState<string | null>(null)
  // The geography/join pattern once more: before the mapping is saved, say
  // how many of the source's values the target actually has.
  useEffect(() => {
    setCheck(null); setCheckErr(null)
    if (!fromCol || !toCol) return
    let live = true
    const t = setTimeout(() => {
      relationshipsApi.check({ from_dataset_id: fromDs, from_column: fromCol, to_dataset_id: toDs, to_column: toCol })
        .then(r => { if (live) setCheck(r) })
        .catch(e => { if (live) setCheckErr(e?.response?.data?.detail ?? 'Could not check this mapping') })
    }, 350)
    return () => { live = false; clearTimeout(t) }
  }, [fromDs, fromCol, toDs, toCol])

  const submit = async () => {
    if (!fromCol || !toCol) { setError('Choose a column on both sides'); return }
    try {
      const rel = await relationshipsApi.create({ from_dataset_id: fromDs, from_column: fromCol, to_dataset_id: toDs, to_column: toCol })
      onCreated(rel)
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'Failed to create relationship')
    }
  }

  return (
    <div style={{ border: '1px solid var(--border)', borderRadius: 8, padding: 12, marginTop: 8, maxWidth: 420 }}>
      <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
        <select value={fromDs} onChange={e => setFromDs(Number(e.target.value))}>
          {datasetIds.map(id => <option key={id} value={id}>{datasets[id]?.name}</option>)}
        </select>
        <select value={fromCol} onChange={e => setFromCol(e.target.value)}>
          <option value="">Column…</option>
          {(datasets[fromDs]?.columns ?? []).map(c => <option key={c.name} value={c.name}>{c.name}</option>)}
        </select>
      </div>
      <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
        <select value={toDs} onChange={e => setToDs(Number(e.target.value))}>
          {datasetIds.map(id => <option key={id} value={id}>{datasets[id]?.name}</option>)}
        </select>
        <select value={toCol} onChange={e => setToCol(e.target.value)}>
          <option value="">Column…</option>
          {(datasets[toDs]?.columns ?? []).map(c => <option key={c.name} value={c.name}>{c.name}</option>)}
        </select>
      </div>
      {checkErr && <p role="alert" style={{ color: 'var(--danger)', fontSize: 11 }}>{checkErr}</p>}
      {check && <MappingMatch check={check} fromCol={fromCol} toCol={toCol} />}
      {error && <p style={{ color: 'var(--danger)', fontSize: 12 }}>{error}</p>}
      <div style={{ display: 'flex', gap: 8 }}>
        <button className="btn btn-primary btn-sm" onClick={submit}>Create</button>
        <button className="btn btn-ghost btn-sm" onClick={onCancel}>Cancel</button>
      </div>
    </div>
  )
}

/** What a mapping will do to a click, before it exists. */
export function MappingMatch({ check, fromCol, toCol }: { check: MappingCheck; fromCol: string; toCol: string }) {
  const good = check.pct_values === 100 && !check.type_mismatch
  return (
    <div data-testid="mapping-match" role="status" style={{ fontSize: 11, margin: '4px 0 8px', padding: '6px 8px', borderRadius: 6,
      border: `1px solid ${good ? 'var(--border)' : 'var(--warning, #d68910)'}` }}>
      <div><b style={{ fontSize: 13 }}>{check.pct_values}%</b> of {fromCol}’s values exist in {toCol}
        {' '}({check.matched_values.toLocaleString()} of {check.source_values.toLocaleString()}) — clicking one of those filters the other dataset; the rest filter it to nothing.</div>
      {check.unmatched_count > 0 && (
        <div style={{ color: 'var(--muted)' }} dir="auto">
          Not found: {check.unmatched.slice(0, 5).map(u => u.value).join(', ')}{check.unmatched_count > 5 ? ` and ${check.unmatched_count - 5} more` : ''}
        </div>
      )}
      {check.near_matches.length > 0 && (
        <div style={{ color: 'var(--danger)' }} dir="auto">
          ⚠ {check.near_matches.length} differ only in case or spacing ({check.near_matches.slice(0, 3).map(n => `“${n.source}” vs “${n.target}”`).join(', ')}) — a filter compares them exactly, so tidy one side (Prep → trim / change case) first.
        </div>
      )}
      {check.type_mismatch && <div style={{ color: 'var(--danger)' }}>⚠ {check.type_mismatch}: values that look equal will not match.</div>}
      <div style={{ color: 'var(--muted)' }}>{toCol} has {check.target_values.toLocaleString()} values; {check.pct_target_covered}% of them appear in {fromCol}.</div>
    </div>
  )
}
