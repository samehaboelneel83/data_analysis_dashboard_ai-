import JoinMatchNote from './prepPipeline/JoinMatchNote'
import { tNodes } from './prepPipeline/tNodes'
import { useEffect, useState } from 'react'
import { datasetsApi, prepApi, type Dataset, type PrepStep } from '../../services/api'
import { translate, useT, type TranslateFn } from '../../i18n'
import { optLabel } from './prepPipeline/model'

/**
 * Step-based data preparation editor: the ordered cleansing pipeline applied to
 * every read of an import dataset (widgets, exports, digests, profiling).
 *
 * Each mutation saves immediately (the app's autosave pattern) and reports the
 * pipeline's effect as "N rows → M rows", because the whole point of a step
 * editor is seeing what each step did. Server-side validation is the hard gate;
 * its message is surfaced verbatim so a refused step explains itself.
 */

// The kinds this editor offers, in menu order; names from the catalog.
const KINDS = [
  'drop_duplicates', 'drop_nulls', 'fill_nulls', 'trim', 'case', 'replace', 'rename', 'retype',
  'split', 'filter_rows', 'remove_columns', 'aggregate', 'join', 'sort', 'dedupe', 'partition',
] as const

const inEnglish: TranslateFn = (key, vars) => translate('en', key, vars)

/** A step as a sentence. `t` defaults to English, for callers outside React. */
export function describeStep(s: PrepStep, t: TranslateFn = inEnglish): string {
  const sep = t('pg.panelsB.listSep')
  const has = (v: unknown) => Array.isArray(v) && v.length > 0
  const join = (v: unknown) => (v as unknown[]).join(sep)
  switch (s.kind) {
    case 'drop_duplicates':
    case 'dedupe':          return has(s.subset) ? t('pg.panelsB.desc.dedupeCols', { cols: join(s.subset) }) : t('pg.panelsB.desc.dedupe')
    case 'drop_nulls':      return has(s.columns) ? t('pg.panelsB.desc.dropNullsCols', { cols: join(s.columns) }) : t('pg.panelsB.desc.dropNulls')
    case 'fill_nulls':      return t('pg.panelsB.desc.fill', { col: String(s.column),
      how: s.method === 'value' ? String(JSON.stringify(s.value)) : optLabel(t, 'fill', s.method) })
    case 'trim':            return has(s.columns) ? t('pg.panelsB.desc.trimCols', { cols: join(s.columns) }) : t('pg.panelsB.desc.trim')
    case 'case': {
      if (s.to === 'upper' || s.to === 'lower' || s.to === 'title') return t(`pg.panelsB.desc.case.${s.to}`, { col: String(s.column) })
      return `${String(s.to)[0].toUpperCase()}${String(s.to).slice(1)}-case ${s.column}`
    }
    case 'replace':         return t(s.match === 'contains' ? 'pg.panelsB.desc.replaceSub' : 'pg.panelsB.desc.replace',
      { find: String(JSON.stringify(s.find)), replace: String(JSON.stringify(s.replace)), col: String(s.column) })
    case 'rename':          return t('pg.panelsB.desc.rename', { from: String(s.column), to: String(s.to) })
    case 'retype':          return t('pg.panelsB.desc.retype', { col: String(s.column), type: optLabel(t, 'type', s.to) })
    case 'split':           return t('pg.panelsB.desc.split', { col: String(s.column), delim: String(JSON.stringify(s.delimiter)),
      into: String((s.into as string[] | undefined)?.join(sep)) })
    case 'filter_rows':     return t('pg.panelsB.desc.filter', { expr: String(s.expression) })
    case 'remove_columns':  return t('pg.panelsB.desc.remove', { cols: String((s.columns as string[] | undefined)?.join(sep)) })
    case 'join': {
      // Reads the composite shape too. This editor only writes single keys,
      // but a step authored in the pipeline panel can carry several -- and
      // showing `undefined = undefined` for one would be worse than useless.
      const ls = (s.left_ons as string[] | undefined) ?? [s.left_on as string]
      const rs = (s.right_ons as string[] | undefined) ?? [s.right_on as string]
      const keys = ls.map((l, i) => `${l ?? '?'} = ${rs[i] ?? '?'}`).join(t('pg.panelsB.andSep'))
      if (s.how === 'left' || s.how === 'right' || s.how === 'inner' || s.how === 'full')
        return t(`pg.panelsB.desc.join.${s.how}`, { id: String(s.dataset_id), keys })
      return `${String(s.how)[0].toUpperCase()}${String(s.how).slice(1)} join dataset #${s.dataset_id} on ${keys}`
    }
    case 'aggregate':       return t('pg.panelsB.desc.aggregate', { cols: String((s.group_by as string[] | undefined)?.join(sep)),
      aggs: ((s.aggregations as { agg?: string; column?: string }[] | undefined) ?? []).map(a => `${a.agg}(${a.column})`).join(sep) })
    case 'sort':            return t('pg.panelsB.desc.sort', { cols: ((s.columns as { column: string; dir?: string }[] | undefined) ?? [])
      .map(c => `${c.column} ${c.dir === 'desc' ? '↓' : '↑'}`).join(sep) })
    case 'partition':       return t(s.key ? 'pg.panelsB.desc.partitionKey' : 'pg.panelsB.desc.partition',
      { name: String(s.name), pct: String(s.train_pct), key: String(s.key ?? ''), seed: String(s.seed ?? 42) })
    // Written by the data grid's cell editor, never by this panel -- but it
    // lands in the same list, and falling through to the default would print
    // "edit_cells" where every other step reads as a sentence.
    case 'edit_cells': {
      const n = ((s.edits as unknown[] | undefined) ?? []).length
      return t('pg.panelsB.desc.editCells', { n, col: String(s.column), key: String(s.key_column) })
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
  const t = useT()
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
      setError(detail || t('pg.panelsB.steps.saveFailed'))
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

  const choose = t('pg.panelsB.steps.choose')
  const colSelect = (key: string, title: string) => (
    <div key={key}>
      <label htmlFor={`prep-${key}`} style={label}>{title}</label>
      <select id={`prep-${key}`} value={draft[key] ?? ''} onChange={e => setDraft(p => ({ ...p, [key]: e.target.value }))} style={{ width: '100%' }}>
        <option value="">{choose}</option>
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
  const choice = (key: string, title: string, options: string[], group: string) => (
    <div key={key}>
      <label htmlFor={`prep-${key}`} style={label}>{title}</label>
      <select id={`prep-${key}`} value={draft[key] ?? ''} onChange={e => setDraft(p => ({ ...p, [key]: e.target.value }))} style={{ width: '100%' }}>
        <option value="">{choose}</option>
        {options.map(o => <option key={o} value={o}>{optLabel(t, group, o)}</option>)}
      </select>
    </div>
  )

  const paramFields = (): React.ReactNode[] => {
    switch (kind) {
      case 'drop_duplicates': return [textInput('subset', t('pg.panelsB.steps.compareCols'))]
      case 'dedupe':          return [textInput('subset', t('pg.panelsB.steps.compareCols'))]
      case 'sort':            return [textInput('sort_columns', t('pg.panelsB.steps.sortCols')),
        choice('sort_dir', t('pg.panelsB.steps.direction'), ['asc', 'desc'], 'dir')]
      case 'drop_nulls':      return [textInput('columns', t('pg.panelsB.steps.checkCols'))]
      case 'fill_nulls':      return [colSelect('column', t('pg.panelsB.steps.column')),
        choice('method', t('pg.panelsB.steps.fillWith'), ['value', 'zero', 'mean', 'median', 'mode', 'ffill'], 'fill'),
        ...(draft.method === 'value' ? [textInput('value', t('pg.panelsB.steps.value'))] : [])]
      case 'trim':            return [textInput('columns', t('pg.panelsB.steps.trimCols'))]
      case 'case':            return [colSelect('column', t('pg.panelsB.steps.column')), choice('to', t('pg.panelsB.steps.case'), ['upper', 'lower', 'title'], 'case')]
      case 'replace':         return [colSelect('column', t('pg.panelsB.steps.column')), textInput('find', t('pg.panelsB.steps.find')), textInput('replace', t('pg.panelsB.steps.replaceWith')),
        choice('match', t('pg.panelsB.steps.match'), ['exact', 'contains'], 'match')]
      case 'rename':          return [colSelect('column', t('pg.panelsB.steps.column')), textInput('to', t('pg.panelsB.steps.newName'))]
      case 'retype':          return [colSelect('column', t('pg.panelsB.steps.column')), choice('to', t('pg.panelsB.steps.newType'), ['numeric', 'text', 'datetime'], 'type')]
      case 'split':           return [colSelect('column', t('pg.panelsB.steps.column')), textInput('delimiter', t('pg.panelsB.steps.delimiter'), t('pg.panelsB.ed.eg', { v: '-' })),
        textInput('into', t('pg.panelsB.steps.newCols'))]
      case 'filter_rows':     return [textInput('expression', t('pg.panelsB.steps.expression'), '`amount` > 0')] // i18n-ok
      case 'remove_columns':  return [textInput('columns', t('pg.panelsB.steps.columns'))]
      case 'join':            return [
        <div key="dataset_id">
          <label htmlFor="prep-dataset_id" style={label}>{t('pg.panelsB.steps.joinDataset')}</label>
          <select id="prep-dataset_id" value={draft.dataset_id ?? ''} onChange={e => setDraft(p => ({ ...p, dataset_id: e.target.value, right_on: '' }))} style={{ width: '100%' }}>
            <option value="">{choose}</option>
            {orgDatasets.map(ds => <option key={ds.id} value={ds.id}>{ds.name}</option>)}
          </select>
        </div>,
        choice('how', t('pg.panelsB.steps.joinType'), ['left', 'inner', 'right', 'full'], 'how'),
        colSelect('left_on', t('pg.panelsB.steps.thisKey')),
        <div key="right_on">
          <label htmlFor="prep-right_on" style={label}>{t('pg.panelsB.steps.joinedKey')}</label>
          <select id="prep-right_on" value={draft.right_on ?? ''} onChange={e => setDraft(p => ({ ...p, right_on: e.target.value }))} style={{ width: '100%' }} disabled={!joinCols.length} title={!joinCols.length ? t('pg.panelsB.steps.noShared') : undefined}>
            <option value="">{choose}</option>
            {joinCols.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>,
      ]
      case 'partition':       return [textInput('name', t('pg.panelsB.steps.newColName'), '_Partition_'),
        textInput('train_pct', t('pg.panelsB.steps.trainingPct'), '70'), textInput('seed', t('pg.panelsB.steps.seed'), '42'),
        colSelect('key', t('pg.panelsB.steps.keepTogether')),
        <p key="partition-note" style={{ fontSize: 10.5, color: 'var(--muted)', margin: 0 }}>
          {t('pg.panelsB.steps.partNote')}
        </p>]
      case 'aggregate':       return [textInput('group_by', t('pg.panelsB.steps.groupBy')), colSelect('agg_column', t('pg.panelsB.steps.summarise')),
        choice('agg', t('pg.panelsB.steps.aggregation'), ['sum', 'avg', 'min', 'max', 'count', 'median', 'nunique'], 'agg'),
        textInput('agg_as', t('pg.panelsB.steps.outputName'))]
      default: return []
    }
  }

  return (
    <div style={{ padding: 12, width: 300, flexShrink: 0, borderInlineStart: '1px solid var(--border)', overflowY: 'auto' }}>
      <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 4 }}>
        {t('pg.panelsB.steps.title')}
      </div>
      <p style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 10 }}>
        {t('pg.panelsB.steps.intro')}
      </p>

      {effect && (
        <div data-testid="prep-effect" style={{ fontSize: 11, marginBottom: 8, color: 'var(--text)' }}>
          {tNodes(t, 'pg.panelsB.steps.effect', { before: effect.before.toLocaleString() }, { after: <strong>{effect.after.toLocaleString()}</strong> })}
        </div>
      )}
      {error && <div role="alert" style={{ fontSize: 11, color: 'var(--danger)', marginBottom: 8 }}>{error}</div>}

      {steps.length === 0 && !adding && (
        <p style={{ fontSize: 11, color: 'var(--muted)' }}>{t('pg.panelsB.steps.none')}</p>
      )}

      <ol style={{ listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 10 }}>
        {steps.map((s, i) => (
          <li key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 6, border: '1px solid var(--border)',
            borderRadius: 6, padding: '6px 8px', fontSize: 11 }}>
            <span style={{ color: 'var(--muted)', flexShrink: 0 }}>{i + 1}.</span>
            <span style={{ flex: 1 }}>{describeStep(s, t)}</span>
            <button aria-label={t('pg.panelsB.steps.moveUp', { n: i + 1 })} onClick={() => move(i, -1)} disabled={i === 0}
              style={{ border: 'none', background: 'none', cursor: 'pointer', color: 'var(--muted)', padding: 0 }}>↑</button>
            <button aria-label={t('pg.panelsB.steps.moveDown', { n: i + 1 })} onClick={() => move(i, 1)} disabled={i === steps.length - 1}
              style={{ border: 'none', background: 'none', cursor: 'pointer', color: 'var(--muted)', padding: 0 }}>↓</button>
            <button aria-label={t('pg.panelsB.steps.delete', { n: i + 1 })} onClick={() => void persist(steps.filter((_, j) => j !== i))}
              style={{ border: 'none', background: 'none', cursor: 'pointer', color: 'var(--danger)', padding: 0 }}>✕</button>
          </li>
        ))}
      </ol>

      {adding ? (
        <div style={{ border: '1px solid var(--border)', borderRadius: 6, padding: 8 }}>
          <label htmlFor="prep-kind" style={{ ...label, marginTop: 0 }}>{t('pg.panelsB.steps.step')}</label>
          <select id="prep-kind" value={kind} onChange={e => { setKind(e.target.value); setDraft({}) }} style={{ width: '100%' }}>
            {KINDS.map(k => <option key={k} value={k}>{t(`pg.panelsB.steps.kind.${k}`)}</option>)}
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
                if (!s) { setError(t('pg.panelsB.steps.required')); return }
                void persist([...steps, s]).then(() => { setAdding(false); setDraft({}) })
              }}>{t('pg.panelsB.steps.add')}</button>
            <button className="btn" style={{ fontSize: 11 }} onClick={() => { setAdding(false); setDraft({}); setError('') }}>{t('common.cancel')}</button>
          </div>
        </div>
      ) : (
        <button className="btn" style={{ fontSize: 11 }} onClick={() => setAdding(true)}>{t('pg.panelsB.steps.addStep')}</button>
      )}
    </div>
  )
}
