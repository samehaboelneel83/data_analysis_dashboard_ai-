import JoinMatchNote from './prepPipeline/JoinMatchNote'
import { useEffect, useState } from 'react'
import { datasetsApi, prepApi, type Dataset, type PrepStep } from '../../services/api'

/**
 * Step-based data preparation editor: the ordered cleansing pipeline applied to
 * every read of an import dataset (widgets, exports, digests, profiling).
 *
 * Each mutation saves immediately (the app's autosave pattern) and reports the
 * pipeline's effect as "N rows → M rows", because the whole point of a step
 * editor is seeing what each step did. Server-side validation is the hard gate;
 * its message is surfaced verbatim so a refused step explains itself.
 */

const KIND_LABELS: Record<string, string> = {
  drop_duplicates: 'Remove duplicate rows',
  drop_nulls: 'Remove rows with missing values',
  fill_nulls: 'Fill missing values',
  trim: 'Trim whitespace',
  case: 'Change text case',
  replace: 'Replace values',
  rename: 'Rename column',
  retype: 'Change column type',
  split: 'Split column',
  filter_rows: 'Filter rows',
  remove_columns: 'Remove columns',
  aggregate: 'Group & summarise',
  join: 'Join another dataset',
  sort: 'Sort rows',
  dedupe: 'Remove duplicate rows (subset)',
  partition: 'Partition (train / validation)',
}

export function describeStep(s: PrepStep): string {
  const list = (v: unknown) => (Array.isArray(v) && v.length ? ` (${v.join(', ')})` : '')
  switch (s.kind) {
    case 'drop_duplicates': return `Remove duplicates${list(s.subset)}`
    case 'drop_nulls':      return `Drop rows with missing values${list(s.columns)}`
    case 'fill_nulls':      return `Fill missing ${s.column} with ${s.method === 'value' ? JSON.stringify(s.value) : s.method}`
    case 'trim':            return `Trim whitespace${list(s.columns) || ' (all text columns)'}`
    case 'case':            return `${String(s.to)[0].toUpperCase()}${String(s.to).slice(1)}-case ${s.column}`
    case 'replace':         return `Replace ${JSON.stringify(s.find)} with ${JSON.stringify(s.replace)} in ${s.column}${s.match === 'contains' ? ' (substring)' : ''}`
    case 'rename':          return `Rename ${s.column} → ${s.to}`
    case 'retype':          return `Convert ${s.column} to ${s.to}`
    case 'split':           return `Split ${s.column} on ${JSON.stringify(s.delimiter)} into ${(s.into as string[] | undefined)?.join(', ')}`
    case 'filter_rows':     return `Keep rows where ${s.expression}`
    case 'remove_columns':  return `Remove ${(s.columns as string[] | undefined)?.join(', ')}`
    case 'join': {
      // Reads the composite shape too. This editor only writes single keys,
      // but a step authored in the pipeline panel can carry several -- and
      // showing `undefined = undefined` for one would be worse than useless.
      const ls = (s.left_ons as string[] | undefined) ?? [s.left_on as string]
      const rs = (s.right_ons as string[] | undefined) ?? [s.right_on as string]
      const keys = ls.map((l, i) => `${l ?? '?'} = ${rs[i] ?? '?'}`).join(' and ')
      return `${String(s.how)[0].toUpperCase()}${String(s.how).slice(1)} join dataset #${s.dataset_id} on ${keys}`
    }
    case 'aggregate':       return `Group by ${(s.group_by as string[] | undefined)?.join(', ')} — ${((s.aggregations as { agg?: string; column?: string }[] | undefined) ?? []).map(a => `${a.agg}(${a.column})`).join(', ')}`
    case 'sort':            return `Sort by ${((s.columns as { column: string; dir?: string }[] | undefined) ?? []).map(c => `${c.column} ${c.dir === 'desc' ? '↓' : '↑'}`).join(', ')}`
    case 'dedupe':          return `Remove duplicates${list(s.subset)}`
    case 'partition':       return `Partition ${s.name}: ${s.train_pct}% Training${s.key ? `, whole ${s.key} per side` : ''} (seed ${s.seed ?? 42})`
    // Written by the data grid's cell editor, never by this panel -- but it
    // lands in the same list, and falling through to the default would print
    // "edit_cells" where every other step reads as a sentence.
    case 'edit_cells': {
      const n = ((s.edits as unknown[] | undefined) ?? []).length
      return `Correct ${n} cell${n === 1 ? '' : 's'} in ${s.column}, matched on ${s.key_column}`
    }
    default:                return s.kind
  }
}

const label = { display: 'block', fontSize: 11, fontWeight: 700, color: 'var(--muted)',
  textTransform: 'uppercase' as const, letterSpacing: '.06em', margin: '8px 0 4px' }

export default function PrepStepsPanel({ datasetId, columns, onPipelineChange }: {
  datasetId: number
  columns: string[]
  onPipelineChange?: () => void
}) {
  const [steps, setSteps] = useState<PrepStep[]>([])
  const [effect, setEffect] = useState<{ before: number; after: number } | null>(null)
  const [error, setError] = useState('')
  const [adding, setAdding] = useState(false)
  const [kind, setKind] = useState('drop_duplicates')
  const [orgDatasets, setOrgDatasets] = useState<Dataset[]>([])
  const [joinCols, setJoinCols] = useState<string[]>([])
  const [draft, setDraft] = useState<Record<string, string>>({})

  useEffect(() => {
    setSteps([]); setEffect(null); setError('')
    prepApi.get(datasetId).then(setSteps).catch(() => setSteps([]))
  }, [datasetId])

  useEffect(() => {
    if (kind !== 'join' || orgDatasets.length) return
    datasetsApi.list().then(all =>
      setOrgDatasets(all.filter(d => d.mode !== 'directquery' && d.id !== datasetId)))
      .catch(() => setOrgDatasets([]))
  }, [kind, orgDatasets.length, datasetId])

  useEffect(() => {
    const id = Number(draft.dataset_id)
    if (kind !== 'join' || !id) { setJoinCols([]); return }
    datasetsApi.get(id).then(d => setJoinCols((d.columns ?? []).map(c => c.name)))
      .catch(() => setJoinCols([]))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kind, draft.dataset_id])

  const persist = async (next: PrepStep[]) => {
    setError('')
    try {
      await prepApi.set(datasetId, next)
      setSteps(next)
      const p = await prepApi.preview(datasetId, next)
      setEffect({ before: p.before.rows, after: p.after.rows })
      onPipelineChange?.()
    } catch (e) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(detail || 'Could not save the pipeline')
    }
  }

  const buildStep = (): PrepStep | null => {
    const d = draft
    const cols = (v?: string) => (v ?? '').split(',').map(x => x.trim()).filter(Boolean)
    switch (kind) {
      case 'drop_duplicates': return { kind, ...(cols(d.subset).length ? { subset: cols(d.subset) } : {}) }
      case 'dedupe':          return { kind, ...(cols(d.subset).length ? { subset: cols(d.subset) } : {}) }
      case 'sort': {
        const by = cols(d.sort_columns)
        if (!by.length) return null
        return { kind, columns: by.map(c => ({ column: c, dir: d.sort_dir === 'desc' ? 'desc' : 'asc' })) }
      }
      case 'drop_nulls':      return { kind, ...(cols(d.columns).length ? { columns: cols(d.columns) } : {}) }
      case 'fill_nulls':
        if (!d.column || !d.method) return null
        return { kind, column: d.column, method: d.method, ...(d.method === 'value' ? { value: d.value ?? '' } : {}) }
      case 'trim':            return { kind, ...(cols(d.columns).length ? { columns: cols(d.columns) } : {}) }
      case 'case':            return d.column && d.to ? { kind, column: d.column, to: d.to } : null
      case 'replace':
        if (!d.column) return null
        return { kind, column: d.column, find: d.find ?? '', replace: d.replace ?? '', match: d.match === 'contains' ? 'contains' : 'exact' }
      case 'rename':          return d.column && d.to ? { kind, column: d.column, to: d.to } : null
      case 'retype':          return d.column && d.to ? { kind, column: d.column, to: d.to } : null
      case 'split':
        if (!d.column || !d.delimiter || !cols(d.into).length) return null
        return { kind, column: d.column, delimiter: d.delimiter, into: cols(d.into) }
      case 'filter_rows':     return d.expression ? { kind, expression: d.expression } : null
      case 'remove_columns':  return cols(d.columns).length ? { kind, columns: cols(d.columns) } : null
      case 'join': {
        const id = Number(d.dataset_id)
        if (!id || !d.how || !d.left_on || !d.right_on) return null
        return { kind, dataset_id: id, how: d.how, left_on: d.left_on, right_on: d.right_on }
      }
      case 'partition': {
        const pct = Number(d.train_pct || 70)
        const seed = d.seed === undefined || d.seed === '' ? 42 : Number(d.seed)
        if (!Number.isFinite(pct) || !Number.isInteger(seed)) return null
        return { kind, name: (d.name || '_Partition_').trim(), train_pct: pct, seed, ...(d.key ? { key: d.key } : {}) }
      }
      case 'aggregate': {
        const gb = cols(d.group_by)
        if (!gb.length || !d.agg_column || !d.agg) return null
        return { kind, group_by: gb,
          aggregations: [{ column: d.agg_column, agg: d.agg, ...(d.agg_as ? { as: d.agg_as } : {}) }] }
      }
      default: return null
    }
  }

  const move = (i: number, delta: number) => {
    const j = i + delta
    if (j < 0 || j >= steps.length) return
    const next = [...steps]
    ;[next[i], next[j]] = [next[j], next[i]]
    void persist(next)
  }

  const colSelect = (key: string, title: string) => (
    <div key={key}>
      <label htmlFor={`prep-${key}`} style={label}>{title}</label>
      <select id={`prep-${key}`} value={draft[key] ?? ''} onChange={e => setDraft(p => ({ ...p, [key]: e.target.value }))} style={{ width: '100%' }}>
        <option value="">— choose —</option>
        {columns.map(c => <option key={c} value={c}>{c}</option>)}
      </select>
    </div>
  )
  const textInput = (key: string, title: string, placeholder = '') => (
    <div key={key}>
      <label htmlFor={`prep-${key}`} style={label}>{title}</label>
      <input id={`prep-${key}`} value={draft[key] ?? ''} placeholder={placeholder}
        onChange={e => setDraft(p => ({ ...p, [key]: e.target.value }))} style={{ width: '100%' }} />
    </div>
  )
  const choice = (key: string, title: string, options: string[]) => (
    <div key={key}>
      <label htmlFor={`prep-${key}`} style={label}>{title}</label>
      <select id={`prep-${key}`} value={draft[key] ?? ''} onChange={e => setDraft(p => ({ ...p, [key]: e.target.value }))} style={{ width: '100%' }}>
        <option value="">— choose —</option>
        {options.map(o => <option key={o} value={o}>{o}</option>)}
      </select>
    </div>
  )

  const paramFields = (): React.ReactNode[] => {
    switch (kind) {
      case 'drop_duplicates': return [textInput('subset', 'Columns to compare (comma-separated, empty = all)')]
      case 'dedupe':          return [textInput('subset', 'Columns to compare (comma-separated, empty = all)')]
      case 'sort':            return [textInput('sort_columns', 'Columns to sort by (comma-separated)'),
        choice('sort_dir', 'Direction', ['asc', 'desc'])]
      case 'drop_nulls':      return [textInput('columns', 'Columns to check (comma-separated, empty = any)')]
      case 'fill_nulls':      return [colSelect('column', 'Column'),
        choice('method', 'Fill with', ['value', 'zero', 'mean', 'median', 'mode', 'ffill']),
        ...(draft.method === 'value' ? [textInput('value', 'Value')] : [])]
      case 'trim':            return [textInput('columns', 'Columns (comma-separated, empty = all text)')]
      case 'case':            return [colSelect('column', 'Column'), choice('to', 'Case', ['upper', 'lower', 'title'])]
      case 'replace':         return [colSelect('column', 'Column'), textInput('find', 'Find'), textInput('replace', 'Replace with'),
        choice('match', 'Match', ['exact', 'contains'])]
      case 'rename':          return [colSelect('column', 'Column'), textInput('to', 'New name')]
      case 'retype':          return [colSelect('column', 'Column'), choice('to', 'New type', ['numeric', 'text', 'datetime'])]
      case 'split':           return [colSelect('column', 'Column'), textInput('delimiter', 'Delimiter', 'e.g. -'),
        textInput('into', 'New column names (comma-separated)')]
      case 'filter_rows':     return [textInput('expression', 'Expression', '`amount` > 0')]
      case 'remove_columns':  return [textInput('columns', 'Columns (comma-separated)')]
      case 'join':            return [
        <div key="dataset_id">
          <label htmlFor="prep-dataset_id" style={label}>Dataset to join</label>
          <select id="prep-dataset_id" value={draft.dataset_id ?? ''} onChange={e => setDraft(p => ({ ...p, dataset_id: e.target.value, right_on: '' }))} style={{ width: '100%' }}>
            <option value="">— choose —</option>
            {orgDatasets.map(ds => <option key={ds.id} value={ds.id}>{ds.name}</option>)}
          </select>
        </div>,
        choice('how', 'Join type', ['left', 'inner', 'right', 'full']),
        colSelect('left_on', 'This dataset’s key'),
        <div key="right_on">
          <label htmlFor="prep-right_on" style={label}>Joined dataset&apos;s key</label>
          <select id="prep-right_on" value={draft.right_on ?? ''} onChange={e => setDraft(p => ({ ...p, right_on: e.target.value }))} style={{ width: '100%' }} disabled={!joinCols.length} title={!joinCols.length ? 'The two datasets share no column to join on' : undefined}>
            <option value="">— choose —</option>
            {joinCols.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>,
      ]
      case 'partition':       return [textInput('name', 'New column name', '_Partition_'),
        textInput('train_pct', 'Training % (rest is Validation)', '70'), textInput('seed', 'Seed', '42'),
        colSelect('key', 'Keep rows with the same value together (optional)'),
        <p key="partition-note" style={{ fontSize: 10.5, color: 'var(--muted)', margin: 0 }}>
          Each row is labelled Training or Validation by a seeded hash, so it keeps its side under any
          filter or security rule. Model widgets take the column as their Partition.
        </p>]
      case 'aggregate':       return [textInput('group_by', 'Group by (comma-separated)'), colSelect('agg_column', 'Summarise column'),
        choice('agg', 'Aggregation', ['sum', 'avg', 'min', 'max', 'count', 'median', 'nunique']),
        textInput('agg_as', 'Output name (optional)')]
      default: return []
    }
  }

  return (
    <div style={{ padding: 12, width: 300, flexShrink: 0, borderInlineStart: '1px solid var(--border)', overflowY: 'auto' }}>
      <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 4 }}>
        Prep steps
      </div>
      <p style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 10 }}>
        Cleansing applied, in order, to every read of this dataset. The file itself is never changed — remove a step to undo it.
      </p>

      {effect && (
        <div data-testid="prep-effect" style={{ fontSize: 11, marginBottom: 8, color: 'var(--text)' }}>
          {effect.before.toLocaleString()} rows → <strong>{effect.after.toLocaleString()}</strong> rows
        </div>
      )}
      {error && <div role="alert" style={{ fontSize: 11, color: 'var(--danger)', marginBottom: 8 }}>{error}</div>}

      {steps.length === 0 && !adding && (
        <p style={{ fontSize: 11, color: 'var(--muted)' }}>No steps yet.</p>
      )}

      <ol style={{ listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 10 }}>
        {steps.map((s, i) => (
          <li key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 6, border: '1px solid var(--border)',
            borderRadius: 6, padding: '6px 8px', fontSize: 11 }}>
            <span style={{ color: 'var(--muted)', flexShrink: 0 }}>{i + 1}.</span>
            <span style={{ flex: 1 }}>{describeStep(s)}</span>
            <button aria-label={`Move step ${i + 1} up`} onClick={() => move(i, -1)} disabled={i === 0}
              style={{ border: 'none', background: 'none', cursor: 'pointer', color: 'var(--muted)', padding: 0 }}>↑</button>
            <button aria-label={`Move step ${i + 1} down`} onClick={() => move(i, 1)} disabled={i === steps.length - 1}
              style={{ border: 'none', background: 'none', cursor: 'pointer', color: 'var(--muted)', padding: 0 }}>↓</button>
            <button aria-label={`Delete step ${i + 1}`} onClick={() => void persist(steps.filter((_, j) => j !== i))}
              style={{ border: 'none', background: 'none', cursor: 'pointer', color: 'var(--danger)', padding: 0 }}>✕</button>
          </li>
        ))}
      </ol>

      {adding ? (
        <div style={{ border: '1px solid var(--border)', borderRadius: 6, padding: 8 }}>
          <label htmlFor="prep-kind" style={{ ...label, marginTop: 0 }}>Step</label>
          <select id="prep-kind" value={kind} onChange={e => { setKind(e.target.value); setDraft({}) }} style={{ width: '100%' }}>
            {Object.entries(KIND_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          {paramFields()}
          {kind === 'join' && draft.dataset_id && draft.left_on && draft.right_on && (
            <JoinMatchNote datasetId={datasetId} index={steps.length}
              steps={[...steps, { kind: 'join', dataset_id: Number(draft.dataset_id), how: draft.how || 'left',
                                  left_on: draft.left_on, right_on: draft.right_on }]} />
          )}
          <div style={{ display: 'flex', gap: 6, marginTop: 10 }}>
            <button className="btn btn-primary" style={{ fontSize: 11 }}
              onClick={() => {
                const s = buildStep()
                if (!s) { setError('Fill in the required fields for this step'); return }
                void persist([...steps, s]).then(() => { setAdding(false); setDraft({}) })
              }}>Add</button>
            <button className="btn" style={{ fontSize: 11 }} onClick={() => { setAdding(false); setDraft({}); setError('') }}>Cancel</button>
          </div>
        </div>
      ) : (
        <button className="btn" style={{ fontSize: 11 }} onClick={() => setAdding(true)}>+ Add step</button>
      )}
    </div>
  )
}
