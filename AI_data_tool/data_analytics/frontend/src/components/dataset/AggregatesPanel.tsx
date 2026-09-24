import { useCallback, useEffect, useState } from 'react'
import { aggregatesApi } from '../../services/api'
import type { AggregateListItem, AggregatePreflight } from '../../services/api'

const AGGS = ['sum', 'count', 'min', 'max'] as const

/**
 * Aggregates of a DirectQuery dataset: a GROUP BY run where the data lives,
 * on a schedule, saved as a dataset dashboards can read in milliseconds.
 *
 * The governance rule is shown, not discovered. Every column a row-level
 * security rule reads arrives pre-selected and locked in the grain, with the
 * reason beside it -- the aggregate is governed by the source's rules at
 * read time, which only works if those columns are there.
 *
 * Measures are pre-aggregated, and only sum / count / min / max are offered:
 * a widget on the aggregate will aggregate again, and only those four survive
 * that. `row_count` is always included, so an average is sum / row_count.
 */
// A "filter expression" failure is NOT offered Rebuild: it means the SOURCE
// gained a report-level filter an aggregate would ignore, and rebuilding
// would just recompile the same wrong query. Only "query changed" -- the
// source's own query was edited -- is something Rebuild actually fixes.
const REBUILD_HINT = /query changed/

export default function AggregatesPanel({ datasetId, mode }: { datasetId: number; mode?: string }) {
  const [pre, setPre] = useState<AggregatePreflight | null>(null)
  const [items, setItems] = useState<AggregateListItem[]>([])
  const [name, setName] = useState('')
  const [grain, setGrain] = useState<string[]>([])
  // `name` is only ever present when it was loaded FROM an existing measure
  // (editItem below) -- a freshly added one has none, and the backend derives
  // its default (`${column}_${agg}`) exactly as it does on create.
  const [measures, setMeasures] = useState<{ column: string; agg: string; name?: string }[]>([])
  const [mCol, setMCol] = useState('')
  const [mAgg, setMAgg] = useState<string>('sum')
  const [every, setEvery] = useState('')
  const [editing, setEditing] = useState<AggregateListItem | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoadError(null)
    try {
      const [p, l] = await Promise.all([aggregatesApi.preflight(datasetId), aggregatesApi.list(datasetId)])
      setPre(p)
      setItems(l)
      setGrain(g => Array.from(new Set([...p.rls_columns, ...g])))
    } catch (e) {
      setLoadError((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        ?? 'Could not load aggregates')
    }
  }, [datasetId])

  useEffect(() => { if (mode === 'directquery') void load() }, [load, mode])

  if (mode !== 'directquery') {
    return (
      <p style={{ padding: 12, fontSize: 12, color: 'var(--muted)' }}>
        Aggregates are built from <strong>DirectQuery</strong> datasets, which query their source on
        every render. This dataset is already a file; a dashboard on it reads that file directly.
      </p>
    )
  }
  if (!pre) {
    if (loadError) {
      return (
        <div style={{ padding: 12, display: 'flex', flexDirection: 'column', gap: 8, alignItems: 'flex-start' }}>
          <p style={{ fontSize: 12, color: 'var(--danger)', margin: 0 }}>{loadError}</p>
          <button type="button" className="btn btn-sm" onClick={() => void load()}>Try again</button>
        </div>
      )
    }
    return <p style={{ padding: 12, fontSize: 12, color: 'var(--muted)' }}>Loading…</p>
  }

  const toggle = (c: string) => setGrain(g => g.includes(c) ? g.filter(x => x !== c) : [...g, c])
  const resetForm = () => {
    setEditing(null); setName(''); setMeasures([]); setEvery('')
    setGrain(pre?.rls_columns ?? [])
  }
  const editItem = (it: AggregateListItem) => {
    setEditing(it)
    setName(it.dataset.name)
    setGrain(Array.from(new Set([...(pre?.rls_columns ?? []), ...(it.dataset.aggregate_spec?.grain ?? [])])))
    // Carries the stored NAME through, not just column+agg -- dropping it
    // here used to silently rename a custom measure (e.g. `revenue`) back to
    // the default `amount_sum` the moment the form was saved, since a
    // measure with no name sent gets the backend's default derived name.
    setMeasures((it.dataset.aggregate_spec?.measures ?? []).map(m => ({ column: m.column, agg: m.agg, name: m.name })))
    setEvery(it.dataset.refresh_interval_minutes != null ? String(it.dataset.refresh_interval_minutes) : '')
    setError(null)
  }
  const submit = async () => {
    setBusy(true); setError(null)
    try {
      if (editing) {
        await aggregatesApi.update(datasetId, editing.dataset.id, {
          grain, measures, refresh_interval_minutes: every ? Number(every) : null,
        })
      } else {
        await aggregatesApi.create(datasetId, {
          name: name.trim(), grain, measures,
          refresh_interval_minutes: every ? Number(every) : null,
        })
      }
      resetForm()
      await load()
    } catch (e) {
      setError((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        ?? (editing ? 'Could not update the aggregate' : 'Could not create the aggregate'))
    } finally { setBusy(false) }
  }
  const rebuild = async (it: AggregateListItem) => {
    setBusy(true); setError(null)
    try {
      await aggregatesApi.update(datasetId, it.dataset.id, {})
      await load()
    } catch (e) {
      setError((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        ?? 'Could not rebuild the aggregate')
    } finally { setBusy(false) }
  }
  const label: React.CSSProperties = { display: 'block', fontSize: 10, fontWeight: 700, color: 'var(--muted)' }

  return (
    <div style={{ padding: 12, display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div>
        <h3 style={{ fontSize: 13, margin: '0 0 4px' }}>Aggregates</h3>
        <p style={{ fontSize: 11, color: 'var(--muted)', margin: 0, maxWidth: 640 }}>
          A GROUP BY run in the source database on a schedule and saved as a dataset, so a dashboard
          reads thousands of pre-summed rows instead of scanning millions. Measures are pre-aggregated;
          <code> row_count</code> is always included, so an average is <code>sum / row_count</code>.
        </p>
      </div>

      <fieldset style={{ border: '1px solid var(--border)', borderRadius: 8, padding: 10 }}>
        <legend style={{ fontSize: 11, fontWeight: 700 }}>Grain</legend>
        {pre.rls_columns.length > 0 && (
          <p style={{ fontSize: 11, color: 'var(--muted)', margin: '0 0 6px' }}>
            {pre.rls_columns.join(', ')} {pre.rls_columns.length === 1 ? 'is' : 'are'} locked in: a
            row-level security rule reads {pre.rls_columns.length === 1 ? 'it' : 'them'}, and the aggregate
            is governed by the source's rules at read time.
          </p>
        )}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {pre.grain_candidates.map(c => (
            <label key={c} style={{ fontSize: 12, display: 'flex', alignItems: 'center', gap: 4 }}>
              <input type="checkbox" aria-label={c} checked={grain.includes(c)}
                disabled={pre.rls_columns.includes(c)} title={pre.rls_columns.includes(c) ? 'Always kept: row-level security filters on this column' : undefined} onChange={() => toggle(c)} />
              {c}
            </label>
          ))}
        </div>
      </fieldset>

      <fieldset style={{ border: '1px solid var(--border)', borderRadius: 8, padding: 10 }}>
        <legend style={{ fontSize: 11, fontWeight: 700 }}>Measures</legend>
        <div style={{ display: 'flex', gap: 6, alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <div>
            <label htmlFor="agg-mcol" style={label}>Measure column</label>
            <select id="agg-mcol" value={mCol} onChange={e => setMCol(e.target.value)} style={{ fontSize: 12 }}>
              <option value="">Choose…</option>
              {pre.measure_candidates.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <div>
            <label htmlFor="agg-magg" style={label}>Aggregation</label>
            <select id="agg-magg" value={mAgg} onChange={e => setMAgg(e.target.value)} style={{ fontSize: 12 }}>
              {AGGS.map(a => <option key={a} value={a}>{a}</option>)}
            </select>
          </div>
          <button type="button" className="btn btn-ghost btn-sm" disabled={!mCol} title={!mCol ? 'Choose a column to aggregate first' : undefined}
            onClick={() => { setMeasures(m => [...m, { column: mCol, agg: mAgg }]); setMCol('') }}>
            Add measure
          </button>
        </div>
        <ul style={{ fontSize: 12, margin: '8px 0 0', paddingLeft: 18 }}>
          {measures.map((m, i) => (
            <li key={i}>{m.agg}({m.column}) → <code>{m.name ?? `${m.column}_${m.agg}`}</code>{' '}
              <button type="button" className="btn btn-ghost btn-sm" style={{ fontSize: 10 }}
                onClick={() => setMeasures(ms => ms.filter((_, j) => j !== i))}>remove</button>
            </li>
          ))}
        </ul>
      </fieldset>

      <div style={{ display: 'flex', gap: 6, alignItems: 'flex-end', flexWrap: 'wrap' }}>
        <div>
          <label htmlFor="agg-name" style={label}>Name</label>
          <input id="agg-name" value={name} onChange={e => setName(e.target.value)}
            disabled={!!editing} title={editing ? 'The name is fixed once an aggregate exists' : undefined} style={{ fontSize: 12 }} />
        </div>
        <div>
          <label htmlFor="agg-every" style={label}>Refresh every (minutes)</label>
          <input id="agg-every" type="number" min={5} value={every} onChange={e => setEvery(e.target.value)}
            placeholder="never" style={{ fontSize: 12, width: 90 }} />
        </div>
        <button type="button" className="btn btn-sm" onClick={submit}
          disabled={busy || !name.trim() || grain.length === 0 || measures.length === 0} title={!name.trim() ? 'Name the aggregate first' : grain.length === 0 ? 'Choose at least one column to group by' : measures.length === 0 ? 'Add at least one measure' : undefined}>
          {busy ? (editing ? 'Saving…' : 'Creating…') : (editing ? 'Save changes' : 'Create aggregate')}
        </button>
        {editing && (
          <button type="button" className="btn btn-ghost btn-sm" onClick={resetForm} disabled={busy}>
            Cancel
          </button>
        )}
      </div>
      {error && <p style={{ fontSize: 11, color: 'var(--danger)', margin: 0 }}>{error}</p>}

      {items.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {items.map(it => (
            <div key={it.dataset.id} style={{ border: '1px solid var(--border)', borderRadius: 8, padding: 10 }}>
              <div style={{ display: 'flex', gap: 8, alignItems: 'baseline', flexWrap: 'wrap' }}>
                <strong style={{ fontSize: 12 }}>{it.dataset.name}</strong>
                <span style={{ fontSize: 11, color: 'var(--muted)' }}>
                  {(it.dataset.aggregate_spec?.grain ?? []).join(' × ')} ·{' '}
                  {it.dataset.row_count.toLocaleString()} rows ·{' '}
                  {it.dataset.refresh_interval_minutes ? `every ${it.dataset.refresh_interval_minutes} min` : 'not scheduled'}
                </span>
                <button type="button" className="btn btn-ghost btn-sm" style={{ fontSize: 10 }}
                  onClick={() => editItem(it)} disabled={busy}>
                  Edit
                </button>
                {REBUILD_HINT.test(it.last_error ?? '') && (
                  <button type="button" className="btn btn-ghost btn-sm" style={{ fontSize: 10 }}
                    onClick={() => void rebuild(it)} disabled={busy}>
                    Rebuild
                  </button>
                )}
              </div>
              {it.last_error && (
                <p style={{ fontSize: 11, color: 'var(--danger)', margin: '6px 0 0' }}>{it.last_error}</p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
