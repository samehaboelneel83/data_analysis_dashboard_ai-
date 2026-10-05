import { useCallback, useEffect, useState } from 'react'
import { Info, Lock, Plus } from 'lucide-react'
import { aggregatesApi } from '../../services/api'
import { useT } from '../../i18n'
import '../../pages/datasetDetail/aggregates.css'
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
  const t = useT()
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
  const label: React.CSSProperties = { display: 'block', fontSize: 11, fontWeight: 700, color: 'var(--muted)' }

  const lock = (c: string) => pre.rls_columns.includes(c)
  return (
    <div className="dl-aggs">
      <header className="dl-aggs__head">
        <div>
          <h3>{t('agg3.title')}</h3>
          <p>{t('agg3.copy')}</p>
        </div>
        <button type="button" className="btn btn-primary btn-sm"
          onClick={() => { resetForm(); document.getElementById('agg-name')?.focus() }}>
          <Plus size={14} aria-hidden /> {t('agg3.new')}
        </button>
      </header>

      {items.length > 0 && (
        <div className="dl-aggs__card dl-aggs__table-card">
          <table className="dl-aggs__table">
            <thead><tr>
              <th>{t('agg3.col.name')}</th><th>{t('agg3.col.grain')}</th><th>{t('agg3.col.measures')}</th><th className="dl-ov__num">{t('agg3.col.rows')}</th>
              <th>{t('agg3.col.refresh')}</th><th>{t('agg3.col.status')}</th><th aria-label="Actions" />
            </tr></thead>
            <tbody>
              {items.map(it => {
                const spec = it.dataset.aggregate_spec
                return (
                  <tr key={it.dataset.id}>
                    <td><strong dir="auto">{it.dataset.name}</strong></td>
                    <td className="dl-aggs__grain">
                      {(spec?.grain ?? []).map((g, k) => (
                        <span key={g}>{k > 0 && <span className="dl-aggs__x"> × </span>}
                          <code className={lock(g) ? 'dl-aggs__locked' : undefined}>{lock(g) && <Lock size={10} aria-hidden />}{g}</code></span>
                      ))}
                    </td>
                    <td className="dl-aggs__mono">{[...(spec?.measures ?? []).map(m => `${m.agg}(${m.column})`), 'row_count'].join(', ')}</td>
                    <td className="dl-ov__num">{it.dataset.row_count.toLocaleString()}</td>
                    <td>{it.dataset.refresh_interval_minutes ? t('agg3.every', { n: it.dataset.refresh_interval_minutes }) : t('agg3.notScheduled')}</td>
                    <td>
                      {it.last_error
                        ? <span className="dl-aggs__status dl-aggs__status--bad">{t('agg3.failed', { why: it.last_error })}</span>
                        : <span className="dl-aggs__status">{it.dataset.last_refreshed_at
                            ? t('agg3.refreshed', { when: new Date(it.dataset.last_refreshed_at).toLocaleString() }) : t('agg3.notRefreshed')}</span>}
                    </td>
                    <td className="dl-aggs__row-actions">
                      <button type="button" className="btn btn-sm" onClick={() => editItem(it)} disabled={busy}>Edit</button>
                      {REBUILD_HINT.test(it.last_error ?? '') && (
                        <button type="button" className="btn btn-sm" onClick={() => void rebuild(it)} disabled={busy}>Rebuild</button>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      <p className="dl-aggs__info">
        <Info size={14} aria-hidden />
        <span><strong>{t('agg3.noteTitle')}</strong> {t('agg3.noteBody')}</span>
      </p>

      <section className="dl-aggs__card">
        <h4>{editing ? t('agg3.edit', { name }) : t('agg3.new')}</h4>
        <p className="dl-aggs__sub">{t('agg3.formSub')}</p>
        <fieldset className="dl-aggs__set">
          <legend>Grain</legend>
          <div className="dl-aggs__checks">
            {pre.grain_candidates.map(c => (
              <label key={c} className={grain.includes(c) ? 'dl-aggs__chip dl-aggs__chip--on' : 'dl-aggs__chip'}>
                <input type="checkbox" aria-label={c} checked={grain.includes(c)}
                  disabled={lock(c)} title={lock(c) ? 'Always kept: row-level security filters on this column' : undefined} onChange={() => toggle(c)} />
                {lock(c) && <Lock size={10} aria-hidden />}{c}
              </label>
            ))}
          </div>
          {pre.rls_columns.length > 0 && (
            <p className="dl-aggs__sub">
              <Lock size={11} aria-hidden /> {pre.rls_columns.join(', ')} {pre.rls_columns.length === 1 ? 'is' : 'are'} locked in: a
              row-level security rule reads {pre.rls_columns.length === 1 ? 'it' : 'them'}, and the aggregate
              is governed by the source's rules at read time.
            </p>
          )}
        </fieldset>

        <fieldset className="dl-aggs__set">
          <legend>Measures</legend>
          <div className="dl-aggs__row">
            <div>
              <label htmlFor="agg-mcol" style={label}>Measure column</label>
              <select id="agg-mcol" value={mCol} onChange={e => setMCol(e.target.value)}>
                <option value="">Choose…</option>
                {pre.measure_candidates.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <div>
              <label htmlFor="agg-magg" style={label}>Aggregation</label>
              <select id="agg-magg" value={mAgg} onChange={e => setMAgg(e.target.value)}>
                {AGGS.map(a => <option key={a} value={a}>{a}</option>)}
              </select>
            </div>
            <button type="button" className="btn btn-sm" disabled={!mCol} title={!mCol ? 'Choose a column to aggregate first' : undefined}
              onClick={() => { setMeasures(m => [...m, { column: mCol, agg: mAgg }]); setMCol('') }}>
              Add measure
            </button>
          </div>
          <div className="dl-aggs__checks">
            {measures.map((m, i) => (
              <span key={i} className="dl-aggs__chip dl-aggs__chip--on">
                {m.agg}({m.column}) → <code>{m.name ?? `${m.column}_${m.agg}`}</code>
                <button type="button" className="dl-ov__linkish" aria-label={`remove ${m.agg}(${m.column})`}
                  onClick={() => setMeasures(ms => ms.filter((_, j) => j !== i))}>remove</button>
              </span>
            ))}
            <span className="dl-aggs__chip">row_count</span>
          </div>
        </fieldset>

        <div className="dl-aggs__row">
          <div>
            <label htmlFor="agg-name" style={label}>Name</label>
            <input id="agg-name" value={name} onChange={e => setName(e.target.value)}
              disabled={!!editing} title={editing ? 'The name is fixed once an aggregate exists' : undefined} />
          </div>
          <div>
            <label htmlFor="agg-every" style={label}>Refresh every (minutes)</label>
            <input id="agg-every" type="number" min={5} value={every} onChange={e => setEvery(e.target.value)}
              placeholder="never" style={{ inlineSize: 110 }} />
          </div>
          <button type="button" className="btn btn-primary btn-sm" onClick={submit}
            disabled={busy || !name.trim() || grain.length === 0 || measures.length === 0} title={!name.trim() ? 'Name the aggregate first' : grain.length === 0 ? 'Choose at least one column to group by' : measures.length === 0 ? 'Add at least one measure' : undefined}>
            {busy ? (editing ? 'Saving…' : 'Creating…') : (editing ? 'Save changes' : 'Create aggregate')}
          </button>
          {editing && (
            <button type="button" className="btn btn-sm" onClick={resetForm} disabled={busy}>Cancel</button>
          )}
        </div>
        {error && <p className="dl-aggs__error">{error}</p>}
      </section>
    </div>
  )
}
