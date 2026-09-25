import JoinMatchNote from './prepPipeline/JoinMatchNote'
import { useEffect, useRef, useState } from 'react'
import { prepApi, datasetsApi, relationshipsApi } from '../../services/api'
import type { PrepStep, DatasetColumn, Dataset, Relationship } from '../../services/api'
import toast from 'react-hot-toast'

import {
  type EditStep, KIND_LABELS, KIND_ICONS, ADD_MENU_KINDS,
  withKey, newStep,
} from './prepPipeline/model'
import { StepEditor } from './prepPipeline/StepEditor'
import { joinPairs, suggestJoinKeys } from './prepPipeline/join'
export { joinPairs, writeJoinPairs, suggestJoinKeys } from './prepPipeline/join'

// F2: the transform pipeline editor. Each step is a small card in order; the
// same shared machinery every other prep surface uses (prepApi) reads and
// writes the whole list wholesale, same contract as calculated columns.

interface Props {
  datasetId: number
  columns: DatasetColumn[]
}

function summaryOf(s: PrepStep): string {
  switch (s.kind) {
    case 'filter_rows':    return (s.expression as string) || '(no expression)'
    case 'sort': {
      const cols = (s.columns as { column: string; dir?: string }[]) || []
      return cols.length ? cols.map(c => `${c.column} ${c.dir === 'desc' ? '↓' : '↑'}`).join(', ') : '(no columns)'
    }
    case 'dedupe':
    case 'drop_duplicates': {
      const subset = (s.subset as string[]) || []
      return subset.length ? `by ${subset.join(', ')}` : 'across all columns'
    }
    case 'aggregate': {
      const gb = (s.group_by as string[]) || []
      const aggs = (s.aggregations as { column: string; agg: string; as?: string }[]) || []
      return `group by ${gb.join(', ') || '—'}; ${aggs.length} aggregation${aggs.length === 1 ? '' : 's'}`
    }
    case 'rename':         return `${s.column || '?'} → ${s.to || '?'}`
    case 'retype':         return `${s.column || '?'} → ${s.to}`
    case 'split':          return `${s.column || '?'} on "${s.delimiter || ''}" → ${((s.into as string[]) || []).join(', ') || '?'}`
    case 'trim':           return ((s.columns as string[]) || []).length ? (s.columns as string[]).join(', ') : 'all text columns'
    case 'case':           return `${s.column || '?'} → ${s.to}`
    case 'replace':        return `${s.column || '?'}: "${s.find ?? ''}" → "${s.replace ?? ''}"`
    case 'remove_columns': return ((s.columns as string[]) || []).join(', ') || '(none selected)'
    case 'drop_nulls':     return ((s.columns as string[]) || []).length ? (s.columns as string[]).join(', ') : 'any column'
    case 'fill_nulls':     return `${s.column || '?'} with ${s.method}`
    case 'partition':      return `${s.name || '?'}: ${s.train_pct ?? '?'}% training${s.key ? `, whole ${s.key} per side` : ''} (seed ${s.seed ?? 42})`
    case 'edit_cells': {
      const edits = (s.edits as { key: string }[]) || []
      return `${edits.length} correction${edits.length === 1 ? '' : 's'} to ${s.column || '?'}, by ${s.key_column || '?'}`
    }
    case 'join': {
      // Reads both shapes, so a composite key shows every pair rather than
      // silently reporting only the first.
      const keys = joinPairs(s).map(p => `${p.left || '?'} = ${p.right || '?'}`).join(' and ')
      return `dataset #${s.dataset_id ?? '?'} (${s.how}) on ${keys}`
    }
    default:                return ''
  }
}



/** The (left, right) key pairs a join step matches on.
 *
 *  Mirrors `join_key_pairs` in services/prep.py: the singular `left_on`/
 *  `right_on` came first and is what every pipeline saved before composite
 *  keys still carries, so it is read as a one-pair list rather than migrated.
 */
export default function PrepPipelinePanel({ datasetId, columns }: Props) {
  const [steps, setSteps]     = useState<EditStep[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving]   = useState(false)
  const [selected, setSelected] = useState<number | null>(null) // index into steps
  const [addMenuOpen, setAddMenuOpen] = useState(false)
  const [preview, setPreview] = useState<Awaited<ReturnType<typeof prepApi.preview>> | null>(null)
  const [previewErr, setPreviewErr] = useState<string | null>(null)
  const [otherDatasets, setOtherDatasets] = useState<Dataset[]>([])
  // Columns of each dataset a join step targets, so the key can be picked
  // rather than typed. Keyed by dataset id and fetched once per target.
  const [joinCols, setJoinCols] = useState<Record<number, string[]>>({})
  const [rels, setRels] = useState<Relationship[]>([])
  const [saveOpen, setSaveOpen] = useState(false)
  const [saveName, setSaveName] = useState('')
  const [saveDesc, setSaveDesc] = useState('')
  const [savingAs, setSavingAs] = useState(false)
  const [saveErr, setSaveErr] = useState<string | null>(null)
  const [saved, setSaved] = useState<Dataset | null>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // The joined dataset already carries its column list on the standard read,
  // so no new endpoint is needed -- only a cache so switching between steps
  // does not refetch.
  useEffect(() => {
    const wanted = steps
      .filter(s => s.kind === 'join' && typeof s.dataset_id === 'number')
      .map(s => s.dataset_id as number)
    const missing = [...new Set(wanted)].filter(id => !(id in joinCols))
    if (!missing.length) return
    let cancelled = false
    Promise.all(missing.map(id =>
      datasetsApi.get(id)
        .then(d => [id, (d.columns ?? []).map(c => c.name)] as const)
        .catch(() => [id, [] as string[]] as const),
    )).then(pairs => {
      if (cancelled) return
      setJoinCols(prev => ({ ...prev, ...Object.fromEntries(pairs) }))
    })
    return () => { cancelled = true }
  }, [steps, joinCols])

  useEffect(() => {
    let cancelled = false
    prepApi.get(datasetId).then(saved => {
      if (!cancelled) setSteps(saved.map(withKey))
    }).finally(() => !cancelled && setLoading(false))
    datasetsApi.list().then(list => !cancelled && setOtherDatasets(list.filter(d => d.id !== datasetId)))
    // Key detection already exists (name -> type -> value overlap -> cardinality);
    // this is the first thing that reads its output at join time.
    relationshipsApi.list().then(r => !cancelled && setRels(r)).catch(() => {})
    return () => { cancelled = true }
  }, [datasetId])

  // The full pipeline, disabled steps included -- this is what gets saved AND
  // what gets sent to preview (the backend skips disabled steps when it runs
  // them, and marks their per-step entry "skipped" so the card can say so).
  const apiSteps = (): PrepStep[] => steps.map(({ _key, ...rest }) => rest)

  // Live preview: re-run on every change to the pipeline, debounced.
  useEffect(() => {
    if (loading) return
    if (debounceRef.current) clearTimeout(debounceRef.current)
    const toSend = apiSteps()
    if (toSend.length === 0) { setPreview(null); setPreviewErr(null); return }
    debounceRef.current = setTimeout(() => {
      prepApi.preview(datasetId, toSend)
        .then(r => { setPreview(r); setPreviewErr(null) })
        .catch(e => setPreviewErr(e?.response?.data?.detail || 'Preview failed'))
    }, 350)
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [steps, loading, datasetId])

  const save = async () => {
    setSaving(true)
    try {
      await prepApi.set(datasetId, apiSteps())
      toast.success('Pipeline saved')
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  const saveAsDataset = async () => {
    const name = saveName.trim()
    if (!name) return
    setSavingAs(true)
    setSaveErr(null)
    try {
      const ds = await prepApi.materialize(datasetId, {
        name, description: saveDesc.trim() || undefined, steps: apiSteps(),
      })
      setSaved(ds)
      setSaveOpen(false)
      toast.success(`Created "${ds.name}"`)
    } catch (e: any) {
      // The refusals (governed data, exports disabled) are written to be read
      // by a person -- show the server's own words rather than a generic one.
      setSaveErr(e?.response?.data?.detail || 'Could not create the dataset')
    } finally {
      setSavingAs(false)
    }
  }

  const joinedNames = steps
    .filter(st => st.kind === 'join' && typeof st.dataset_id === 'number')
    .map(st => otherDatasets.find(d => d.id === st.dataset_id)?.name)
    .filter(Boolean) as string[]

  const addStep = (kind: string) => {
    setSteps(s => [...s, withKey(newStep(kind))])
    setAddMenuOpen(false)
    setSelected(steps.length)
  }

  const updateStep = (idx: number, patch: Partial<PrepStep>) => {
    setSteps(s => s.map((st, i) => i === idx ? { ...st, ...patch } : st))
  }

  const removeStep = (idx: number) => {
    setSteps(s => s.filter((_, i) => i !== idx))
    setSelected(sel => sel === idx ? null : sel && sel > idx ? sel - 1 : sel)
  }

  const moveStep = (idx: number, dir: -1 | 1) => {
    const to = idx + dir
    if (to < 0 || to >= steps.length) return
    setSteps(s => {
      const next = [...s]
      const [item] = next.splice(idx, 1)
      next.splice(to, 0, item)
      return next
    })
    setSelected(sel => sel === idx ? to : sel === to ? idx : sel)
  }

  const toggleDisabled = (idx: number) => {
    setSteps(s => s.map((st, i) => i === idx ? { ...st, disabled: !st.disabled } : st))
  }

  if (loading) return <p style={{ fontSize: 11, color: 'var(--muted)' }}>Loading pipeline…</p>

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10, position: 'relative' }}>
        <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.06em' }}>
          Pipeline
        </span>
        <div style={{ position: 'relative' }}>
          <button className="btn btn-ghost btn-sm" style={{ fontSize: 11, padding: '2px 7px' }}
            onClick={() => setAddMenuOpen(o => !o)}>
            + Add step
          </button>
          {addMenuOpen && (
            <div style={{ position: 'absolute', insetInlineEnd: 0, top: '100%', zIndex: 20, marginTop: 2,
              background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 6,
              boxShadow: '0 4px 12px rgba(0,0,0,.25)', minWidth: 170, maxHeight: 260, overflowY: 'auto' }}>
              {ADD_MENU_KINDS.map(k => (
                <div key={k} onClick={() => addStep(k)}
                  style={{ fontSize: 11, padding: '6px 10px', cursor: 'pointer', display: 'flex', gap: 6, alignItems: 'center' }}
                  onMouseEnter={e => (e.currentTarget.style.background = 'var(--surface2)')}
                  onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}>
                  <span>{KIND_ICONS[k]}</span>{KIND_LABELS[k]}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {steps.length === 0 && (
        <p data-testid="prep-empty" style={{ fontSize: 11, color: 'var(--muted)', textAlign: 'center', padding: '10px 0' }}>
          No transform steps yet
        </p>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {steps.map((s, idx) => {
          // Preview entries are 1:1 with the sent steps array (disabled ones
          // included, marked "skipped"), so the index lines up directly.
          const stepPreview = preview?.steps?.[idx]
          const isSelected = selected === idx
          return (
            <div key={s._key} data-testid="prep-step-card"
              onClick={() => setSelected(isSelected ? null : idx)}
              style={{ background: 'var(--surface2)', border: `1px solid ${isSelected ? 'var(--accent)' : 'var(--border)'}`,
                borderRadius: 6, padding: 8, opacity: s.disabled ? 0.5 : 1, cursor: 'pointer' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{ fontSize: 12 }}>{KIND_ICONS[s.kind] ?? '•'}</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 11, fontWeight: 600 }}>{KIND_LABELS[s.kind] ?? s.kind}</div>
                  <div style={{ fontSize: 11, color: 'var(--muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {summaryOf(s)}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 2 }} onClick={e => e.stopPropagation()}>
                  <button aria-label="move up" className="btn btn-ghost btn-sm" style={{ fontSize: 11, padding: '1px 5px' }}
                    disabled={idx === 0} onClick={() => moveStep(idx, -1)}>↑</button>
                  <button aria-label="move down" className="btn btn-ghost btn-sm" style={{ fontSize: 11, padding: '1px 5px' }}
                    disabled={idx === steps.length - 1} onClick={() => moveStep(idx, 1)}>↓</button>
                  <button aria-label={s.disabled ? 'enable' : 'disable'} className="btn btn-ghost btn-sm"
                    style={{ fontSize: 11, padding: '1px 5px' }} onClick={() => toggleDisabled(idx)}>
                    {s.disabled ? '○' : '●'}
                  </button>
                  <button aria-label="delete" className="btn btn-ghost btn-sm"
                    style={{ fontSize: 11, padding: '1px 5px', color: 'var(--danger)' }} onClick={() => removeStep(idx)}>✕</button>
                </div>
              </div>

              {s.disabled ? (
                <div data-testid="prep-step-skipped" style={{ fontSize: 11, color: 'var(--muted)', fontStyle: 'italic', marginTop: 4 }}>
                  skipped (paused)
                </div>
              ) : stepPreview && (
                <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 4 }}>
                  {stepPreview.rows_in.toLocaleString()} → {stepPreview.rows_out.toLocaleString()} rows
                  {/* A join on a non-unique key multiplies rows instead of
                      adding columns, and it does so silently -- the numbers are
                      simply wrong afterwards. A relationship says how two
                      tables link, never that the match is one-to-one, so even a
                      suggested key can fan out. Naming it is the only warning
                      the author gets. */}
                  {s.kind === 'join' && stepPreview.rows_out > stepPreview.rows_in * 1.5 && (
                    <span data-testid="prep-join-fanout" style={{ color: 'var(--warning, #b26b00)' }}>
                      {' '}· this join multiplied rows — check the key is unique on the other side
                    </span>
                  )}
                </div>
              )}

              {isSelected && (
                <div onClick={e => e.stopPropagation()} style={{ marginTop: 6, borderTop: '1px solid var(--border)', paddingTop: 6 }}>
                  <StepEditor step={s} columns={columns} otherDatasets={otherDatasets}
                        joinColumns={typeof s.dataset_id === 'number' ? (joinCols[s.dataset_id] ?? []) : []}
                        suggestKeys={(targetId) => suggestJoinKeys(rels, datasetId, targetId)}
                    onChange={patch => updateStep(idx, patch)} />
                  {s.kind === 'join' && <JoinMatchNote datasetId={datasetId} steps={apiSteps()} index={idx} />}
                </div>
              )}
            </div>
          )
        })}
      </div>

      {steps.length > 0 && (
        <button className="btn btn-primary btn-sm" style={{ width: '100%', fontSize: 11, marginTop: 10 }}
          onClick={save} disabled={saving}>
          {saving ? 'Saving…' : 'Save pipeline'}
        </button>
      )}

      {previewErr && (
        <div style={{ fontSize: 11, color: 'var(--danger)', marginTop: 8 }}>{previewErr}</div>
      )}

      {preview && (
        <div data-testid="prep-final-preview" style={{ marginTop: 10, fontSize: 11 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
            <span style={{ color: 'var(--muted)' }}>
              {preview.before.rows.toLocaleString()} rows in → {preview.after.rows.toLocaleString()} rows out
            </span>
            {/* Offered here, beside the result it would keep: this is the moment
                the author knows the output is what they want. */}
            <button className="btn btn-ghost" style={{ fontSize: 11, padding: '2px 8px' }}
              disabled={savingAs}
              onClick={() => {
                setSaveErr(null)
                setSaveName(n => n || 'Joined dataset')
                setSaveOpen(true)
              }}>
              Save as new dataset…
            </button>
          </div>

          {saved && (
            <div style={{ marginBottom: 6, color: 'var(--muted)' }}>
              Created <a href={`/datasets/${saved.id}`}>{saved.name}</a>.
            </div>
          )}

          {saveOpen && (
            <div role="dialog" aria-label="Save as new dataset"
              style={{ border: '1px solid var(--border)', borderRadius: 6, padding: 10, marginBottom: 8 }}>
              <div style={{ fontWeight: 600, marginBottom: 6 }}>Save as new dataset</div>
              <input value={saveName} onChange={e => setSaveName(e.target.value)}
                aria-label="Dataset name" placeholder="Name" style={{ width: '100%', marginBottom: 6 }} />
              <input value={saveDesc} onChange={e => setSaveDesc(e.target.value)}
                aria-label="Description" placeholder="Description (optional)"
                style={{ width: '100%', marginBottom: 6 }} />
              <div style={{ color: 'var(--muted)', marginBottom: 6 }}>
                {preview.after.rows.toLocaleString()} rows × {preview.after.columns.length} columns
                {joinedNames.length > 0 && <> · joined with {joinedNames.join(', ')}</>}
              </div>
              <div style={{ color: 'var(--muted)', marginBottom: 8 }}>
                This creates a fixed copy of the result above. It will not update
                when the source datasets change — rebuild it when you want it
                caught up.
              </div>
              {saveErr && (
                <div style={{ color: 'var(--danger)', marginBottom: 6 }}>{saveErr}</div>
              )}
              <div style={{ display: 'flex', gap: 6 }}>
                <button className="btn btn-primary" style={{ fontSize: 11, padding: '2px 8px' }}
                  disabled={savingAs || !saveName.trim()} title={!saveName.trim() ? 'Name the new dataset first' : undefined} onClick={saveAsDataset}>
                  {savingAs ? 'Creating…' : 'Create'}
                </button>
                <button className="btn btn-ghost" style={{ fontSize: 11, padding: '2px 8px' }}
                  disabled={savingAs} onClick={() => setSaveOpen(false)}>Cancel</button>
              </div>
            </div>
          )}
          <div style={{ overflowX: 'auto', border: '1px solid var(--border)', borderRadius: 6 }}>
            <table style={{ fontSize: 11, borderCollapse: 'collapse', width: '100%' }}>
              <thead>
                <tr>{preview.sample.columns.map(c => (
                  <th key={c} style={{ textAlign: 'start', padding: '3px 6px', borderBottom: '1px solid var(--border)' }}>{c}</th>
                ))}</tr>
              </thead>
              <tbody>
                {preview.sample.rows.slice(0, 5).map((row, i) => (
                  <tr key={i}>{row.map((v, j) => (
                    <td key={j} style={{ padding: '3px 6px', borderBottom: '1px solid var(--border)' }}>{String(v ?? '')}</td>
                  ))}</tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
