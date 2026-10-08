import JoinMatchNote from './prepPipeline/JoinMatchNote'
import { useEffect, useRef, useState } from 'react'
import { prepApi, datasetsApi, relationshipsApi, reportsApi } from '../../services/api'
import type { PrepStep, DatasetColumn, Dataset, Relationship } from '../../services/api'
import toast from 'react-hot-toast'

import {
  type EditStep, KIND_ICONS, ADD_MENU_KINDS,
  withKey, newStep, kindLabel, optLabel,
} from './prepPipeline/model'
import { useT, type TranslateFn } from '../../i18n'
import { tNodes } from './prepPipeline/tNodes'
import { StepEditor } from './prepPipeline/StepEditor'
import { joinPairs, suggestJoinKeys } from './prepPipeline/join'
export { joinPairs, writeJoinPairs, suggestJoinKeys } from './prepPipeline/join'

// F2: the transform pipeline editor. Each step is a small card in order; the
// same shared machinery every other prep surface uses (prepApi) reads and
// writes the whole list wholesale, same contract as calculated columns.

interface Props {
  datasetId: number
  columns: DatasetColumn[]
  /** For naming a dashboard built on the view. */
  datasetName?: string
  /** E12: a dataflow's recipe rather than the dataset's view. With these the
   *  panel edits the given steps (previewed over `datasetId`, the flow's
   *  source) and Save hands them to `onSave`; the dataset's own view is
   *  neither read nor written, and "Save as new dataset" is left to the
   *  dataflow's own Run. */
  initialSteps?: PrepStep[]
  onSave?: (steps: PrepStep[]) => Promise<void>
  saveLabel?: string
  readOnly?: boolean
}

function summaryOf(s: PrepStep, t: TranslateFn): string {
  const sep = t('pg.panelsB.listSep')
  const list = (v: unknown) => ((v as string[]) || []).join(sep)
  const arrow = (from: unknown, to: unknown) => t('pg.panelsB.sum.arrow', { from: String(from), to: String(to) })
  switch (s.kind) {
    case 'filter_rows':    return (s.expression as string) || t('pg.panelsB.sum.noExpression')
    case 'sort': {
      const cols = (s.columns as { column: string; dir?: string }[]) || []
      return cols.length ? cols.map(c => `${c.column} ${c.dir === 'desc' ? '↓' : '↑'}`).join(sep) : t('pg.panelsB.sum.noColumns')
    }
    case 'dedupe':
    case 'drop_duplicates': {
      const subset = (s.subset as string[]) || []
      return subset.length ? t('pg.panelsB.sum.by', { cols: list(subset) }) : t('pg.panelsB.sum.allColumns')
    }
    case 'aggregate': {
      const gb = (s.group_by as string[]) || []
      const aggs = (s.aggregations as { column: string; agg: string; as?: string }[]) || []
      return t('pg.panelsB.sum.aggregate', { cols: list(gb) || '—', n: aggs.length })
    }
    case 'rename':         return arrow(s.column || '?', s.to || '?')
    case 'retype':         return arrow(s.column || '?', optLabel(t, 'type', s.to))
    case 'split':          return t('pg.panelsB.sum.split', { col: String(s.column || '?'), delim: String(s.delimiter || ''), into: list(s.into) || '?' })
    case 'trim':           return ((s.columns as string[]) || []).length ? list(s.columns) : t('pg.panelsB.sum.allText')
    case 'case':           return arrow(s.column || '?', optLabel(t, 'case', s.to))
    case 'replace':        return t('pg.panelsB.sum.replace', { col: String(s.column || '?'), find: String(s.find ?? ''), replace: String(s.replace ?? '') })
    case 'remove_columns': return list(s.columns) || t('pg.panelsB.sum.noneSelected')
    case 'drop_nulls':     return ((s.columns as string[]) || []).length ? list(s.columns) : t('pg.panelsB.sum.anyColumn')
    case 'fill_nulls':     return t('pg.panelsB.sum.fill', { col: String(s.column || '?'), method: optLabel(t, 'fill', s.method) })
    case 'partition': {
      const extra = (s.test_pct ? t('pg.panelsB.sum.partitionTest', { pct: String(s.test_pct) }) : '')
        + (s.stratify ? t('pg.panelsB.sum.partitionStrat', { col: String(s.stratify) }) : '')
        + (s.key ? t('pg.panelsB.sum.partitionKey', { col: String(s.key) }) : '')
      return t('pg.panelsB.sum.partition', { name: String(s.name || '?'), train: String(s.train_pct ?? '?'), extra, seed: String(s.seed ?? 42) })
    }
    case 'edit_cells': {
      const edits = (s.edits as { key: string }[]) || []
      return t('pg.panelsB.sum.editCells', { n: edits.length, col: String(s.column || '?'), key: String(s.key_column || '?') })
    }
    case 'join': {
      // Reads both shapes, so a composite key shows every pair rather than
      // silently reporting only the first.
      const keys = joinPairs(s).map(p => `${p.left || '?'} = ${p.right || '?'}`).join(t('pg.panelsB.andSep'))
      return t('pg.panelsB.sum.join', { id: String(s.dataset_id ?? '?'), how: optLabel(t, 'how', s.how), keys })
    }
    case 'append':         return s.source_column
      ? t('pg.panelsB.sum.appendLabelled', { id: String(s.dataset_id ?? '?'), col: String(s.source_column) })
      : t('pg.panelsB.sum.append', { id: String(s.dataset_id ?? '?') })
    case 'outliers': {
      const cols = list(s.columns) || '?'
      const act = (s.action as string) || 'flag'
      const actText = act === 'flag' ? t('pg.panelsB.sum.outFlag', { name: String(s.name || '_Outlier_') })
        : act === 'remove' ? t('pg.panelsB.sum.outRemove') : act === 'cap' ? t('pg.panelsB.sum.outCap') : 'undefined'
      const rule = s.method === 'zscore' ? `z > ${s.k ?? 3}` : `IQR × ${s.k ?? 1.5}`
      return t('pg.panelsB.sum.outliers', { cols, rule, act: actText })
    }
    case 'normalize':      return s.suffix
      ? t('pg.panelsB.sum.normalizeInto', { cols: list(s.columns) || '?', method: String(s.method), suffix: String(s.suffix) })
      : arrow(list(s.columns) || '?', s.method)
    case 'encode':         return s.method === 'label'
      ? arrow(s.column || '?', `${s.column || '?'}_code`)
      : t('pg.panelsB.sum.oneHot', { col: String(s.column || '?'), n: ((s.categories as string[]) || []).length })
    case 'date_parts':     return arrow(s.column || '?', ((s.parts as string[]) || []).map(p => optLabel(t, 'part', p)).join(sep) || '?')
    case 'feature_select': return [s.max_missing_pct != null && t('pg.panelsB.sum.fsEmpty', { v: String(s.max_missing_pct) }),
      s.min_variance != null && t('pg.panelsB.sum.fsVariance', { v: String(s.min_variance) }), s.max_correlation != null && `|r| > ${s.max_correlation}`]
      .filter(Boolean).join(sep) || t('pg.panelsB.sum.noRule')
    case 'pca':            return t('pg.panelsB.sum.pca', { n: ((s.columns as string[]) || []).length, k: String(s.n ?? 2), prefix: String(s.prefix || 'PC') })
    case 'balance':        return s.only_column
      ? t('pg.panelsB.sum.balanceOnly', { col: String(s.column || '?'), method: optLabel(t, 'balance', s.method), oc: String(s.only_column), ov: String(s.only_value) })
      : t('pg.panelsB.sum.balance', { col: String(s.column || '?'), method: optLabel(t, 'balance', s.method) })
    default:                return ''
  }
}



/** The (left, right) key pairs a join step matches on.
 *
 *  Mirrors `join_key_pairs` in services/prep.py: the singular `left_on`/
 *  `right_on` came first and is what every pipeline saved before composite
 *  keys still carries, so it is read as a one-pair list rather than migrated.
 */
export default function PrepPipelinePanel({ datasetId, columns, datasetName, initialSteps, onSave, saveLabel, readOnly }: Props) {
  const t = useT()
  const controlled = onSave !== undefined
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
  const [viewSaved, setViewSaved] = useState(false)
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
    if (controlled) {
      setSteps((initialSteps ?? []).map(withKey))
      setLoading(false)
    } else {
      prepApi.get(datasetId).then(saved => {
        if (!cancelled) setSteps(saved.map(withKey))
      }).finally(() => !cancelled && setLoading(false))
    }
    // Import datasets only: a join or append runs over loaded data, and a
    // DirectQuery dataset was listed here only to be refused on save.
    datasetsApi.list().then(list => !cancelled && setOtherDatasets(list.filter(d => d.id !== datasetId && d.mode !== 'directquery')))
    // Key detection already exists (name -> type -> value overlap -> cardinality);
    // this is the first thing that reads its output at join time.
    relationshipsApi.list().then(r => !cancelled && setRels(r)).catch(() => {})
    return () => { cancelled = true }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- a new recipe arrives as a remount (key)
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
        .catch(e => setPreviewErr(e?.response?.data?.detail || t('pg.panelsB.pipe.previewFailed')))
    }, 350)
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [steps, loading, datasetId])

  const save = async () => {
    setSaving(true)
    if (onSave) {
      try { await onSave(apiSteps()) } finally { setSaving(false) }
      return
    }
    try {
      await prepApi.set(datasetId, apiSteps())
      toast.success(t('pg.panelsB.pipe.viewSaved'))
      setViewSaved(true)
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || t('pg.panelsB.pipe.saveFailed'))
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
      toast.success(t('pg.panelsB.pipe.createdToast', { name: ds.name }))
    } catch (e: any) {
      // The refusals (governed data, exports disabled) are written to be read
      // by a person -- show the server's own words rather than a generic one.
      setSaveErr(e?.response?.data?.detail || t('pg.panelsB.pipe.createFailed'))
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

  if (loading) return <p style={{ fontSize: 11, color: 'var(--muted)' }}>{t('pg.panelsB.pipe.loading')}</p>

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10, position: 'relative' }}>
        <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.06em' }}>
          {t('pg.panelsB.pipe.title')}
        </span>
        <div style={{ position: 'relative' }}>
          <button className="btn btn-ghost btn-sm" style={{ fontSize: 11, padding: '2px 7px' }}
            hidden={readOnly} onClick={() => setAddMenuOpen(o => !o)}>
            {t('pg.panelsB.pipe.addStep')}
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
                  <span>{KIND_ICONS[k]}</span>{kindLabel(t, k)}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {steps.length === 0 && (
        <p data-testid="prep-empty" style={{ fontSize: 11, color: 'var(--muted)', textAlign: 'center', padding: '10px 0' }}>
          {t('pg.panelsB.pipe.empty')}
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
                  <div style={{ fontSize: 11, fontWeight: 600 }}>{kindLabel(t, s.kind)}</div>
                  <div style={{ fontSize: 11, color: 'var(--muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {/* QA5 R1: an expression is code, laid out left-to-right in any language. */}
                    {s.kind === 'filter_rows' && s.expression ? <bdi dir="ltr">{summaryOf(s, t)}</bdi> : summaryOf(s, t)}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 2 }} onClick={e => e.stopPropagation()}>
                  <button aria-label={t('pg.panelsB.pipe.moveUp')} className="btn btn-ghost btn-sm" style={{ fontSize: 11, padding: '1px 5px' }}
                    disabled={idx === 0} onClick={() => moveStep(idx, -1)}>↑</button>
                  <button aria-label={t('pg.panelsB.pipe.moveDown')} className="btn btn-ghost btn-sm" style={{ fontSize: 11, padding: '1px 5px' }}
                    disabled={idx === steps.length - 1} onClick={() => moveStep(idx, 1)}>↓</button>
                  <button aria-label={s.disabled ? t('pg.panelsB.pipe.enable') : t('pg.panelsB.pipe.disable')} className="btn btn-ghost btn-sm"
                    style={{ fontSize: 11, padding: '1px 5px' }} onClick={() => toggleDisabled(idx)}>
                    {s.disabled ? '○' : '●'}
                  </button>
                  <button aria-label={t('pg.panelsB.pipe.delete')} className="btn btn-ghost btn-sm"
                    style={{ fontSize: 11, padding: '1px 5px', color: 'var(--danger)' }} onClick={() => removeStep(idx)}>✕</button>
                </div>
              </div>

              {s.disabled ? (
                <div data-testid="prep-step-skipped" style={{ fontSize: 11, color: 'var(--muted)', fontStyle: 'italic', marginTop: 4 }}>
                  {t('pg.panelsB.pipe.skipped')}
                </div>
              ) : stepPreview && (
                <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 4 }}>
                  {t('pg.panelsB.pipe.rowsStep', { in: stepPreview.rows_in.toLocaleString(), out: stepPreview.rows_out.toLocaleString() })}
                  {/* A join on a non-unique key multiplies rows instead of
                      adding columns, and it does so silently -- the numbers are
                      simply wrong afterwards. A relationship says how two
                      tables link, never that the match is one-to-one, so even a
                      suggested key can fan out. Naming it is the only warning
                      the author gets. */}
                  {s.kind === 'join' && stepPreview.rows_out > stepPreview.rows_in && (
                    <span data-testid="prep-join-fanout" style={{ color: 'var(--warning, #b26b00)' }}>
                      {t('pg.panelsB.pipe.fanout', { x: (stepPreview.rows_out / Math.max(1, stepPreview.rows_in)).toFixed(2) })}
                    </span>
                  )}
                </div>
              )}

              {isSelected && (
                <div onClick={e => e.stopPropagation()} style={{ marginTop: 6, borderTop: '1px solid var(--border)', paddingTop: 6 }}>
                  <StepEditor step={s} columns={columns} otherDatasets={otherDatasets} datasetId={datasetId}
                        joinColumns={typeof s.dataset_id === 'number' ? (joinCols[s.dataset_id] ?? []) : []}
                        suggestKeys={(targetId) => suggestJoinKeys(rels, datasetId, targetId)}
                    onChange={patch => updateStep(idx, patch)} />
                  {s.kind === 'join' && <JoinMatchNote datasetId={datasetId} steps={apiSteps()} index={idx}
                    joined={otherDatasets.find(d => d.id === Number(s.dataset_id)) ?? null} />}
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* E06: the saved pipeline IS the dataset's view (decided 2026-09-25).
          It is applied on every read -- widgets, exports, AI, the quality
          report -- with each viewer's own row and column security, which a
          stored snapshot could not honour. Saying so is most of the feature. */}
      {(steps.length > 0 || controlled) && !readOnly && (
        <button className="btn btn-primary btn-sm" style={{ width: '100%', fontSize: 11, marginTop: 10 }}
          onClick={save} disabled={saving}>
          {saving ? t('pg.panelsB.pipe.saving') : (saveLabel ?? t('pg.panelsB.pipe.saveView'))}
        </button>
      )}
      {viewSaved && (
        <div data-testid="view-saved" role="status"
          style={{ fontSize: 11, color: 'var(--muted)', marginTop: 6, display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <span>{t('pg.panelsB.pipe.savedNote')}</span>
          <button type="button" className="btn btn-ghost btn-sm" style={{ fontSize: 11 }}
            onClick={() => {
              reportsApi.create({ name: datasetName ? `${datasetName} dashboard` : 'New dashboard', dataset_id: datasetId })
                .then(r => window.location.assign(`/reports/${(r as { id: number }).id}`))
                .catch(e => toast.error(e?.response?.data?.detail ?? t('pg.panelsB.pipe.dashFailed')))
            }}>{t('pg.panelsB.pipe.buildOnView')}</button>
        </div>
      )}

      {previewErr && (
        <div style={{ fontSize: 11, color: 'var(--danger)', marginTop: 8 }}>{previewErr}</div>
      )}

      {preview && (
        <div data-testid="prep-final-preview" style={{ marginTop: 10, fontSize: 11 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
            <span style={{ color: 'var(--muted)' }}>
              {t('pg.panelsB.pipe.rowsInOut', { in: preview.before.rows.toLocaleString(), out: preview.after.rows.toLocaleString() })}
            </span>
            {/* Offered here, beside the result it would keep: this is the moment
                the author knows the output is what they want. */}
            {!controlled && <button className="btn btn-ghost" style={{ fontSize: 11, padding: '2px 8px' }}
              disabled={savingAs}
              onClick={() => {
                setSaveErr(null)
                setSaveName(n => n || 'Joined dataset')
                setSaveOpen(true)
              }}>
              {t('pg.panelsB.pipe.saveAsNewMenu')}
            </button>}
          </div>

          {saved && (
            <div style={{ marginBottom: 6, color: 'var(--muted)', display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              <span>{tNodes(t, 'pg.panelsB.pipe.created', {}, { name: <a href={`/datasets/${saved.id}`}><bdi>{saved.name}</bdi></a> })}</span>
              {/* E06: the journey's next step, from where it ends -- the new
                  dataset used to be a link and a dead end. */}
              <button type="button" className="btn btn-primary btn-sm"
                onClick={() => {
                  reportsApi.create({ name: saved.name, dataset_id: saved.id })
                    .then(r => window.location.assign(`/reports/${(r as { id: number }).id}`))
                    .catch(e => toast.error(e?.response?.data?.detail ?? t('pg.panelsB.pipe.dashFailed')))
                }}>{t('pg.panelsB.pipe.buildFromIt')}</button>
            </div>
          )}

          {saveOpen && (
            <div role="dialog" aria-label={t('pg.panelsB.pipe.saveAsNew')}
              style={{ border: '1px solid var(--border)', borderRadius: 6, padding: 10, marginBottom: 8 }}>
              <div style={{ fontWeight: 600, marginBottom: 6 }}>{t('pg.panelsB.pipe.saveAsNew')}</div>
              <input value={saveName} onChange={e => setSaveName(e.target.value)}
                aria-label={t('pg.panelsB.pipe.datasetName')} placeholder={t('pg.panelsB.pipe.name')} style={{ width: '100%', marginBottom: 6 }} />
              <input value={saveDesc} onChange={e => setSaveDesc(e.target.value)}
                aria-label={t('pg.panelsB.pipe.description')} placeholder={t('pg.panelsB.pipe.descriptionOpt')}
                style={{ width: '100%', marginBottom: 6 }} />
              <div style={{ color: 'var(--muted)', marginBottom: 6 }}>
                {t('pg.panelsB.pipe.shape', { rows: preview.after.rows.toLocaleString(), cols: preview.after.columns.length })}
                {joinedNames.length > 0 && tNodes(t, 'pg.panelsB.pipe.joinedWith', {}, { names: <bdi>{joinedNames.join(t('pg.panelsB.listSep'))}</bdi> })}
              </div>
              <div style={{ color: 'var(--muted)', marginBottom: 8 }}>
                {t('pg.panelsB.pipe.fixedCopy')}
              </div>
              {saveErr && (
                <div style={{ color: 'var(--danger)', marginBottom: 6 }}>{saveErr}</div>
              )}
              <div style={{ display: 'flex', gap: 6 }}>
                <button className="btn btn-primary" style={{ fontSize: 11, padding: '2px 8px' }}
                  disabled={savingAs || !saveName.trim()} title={!saveName.trim() ? t('pg.panelsB.pipe.nameFirst') : undefined} onClick={saveAsDataset}>
                  {savingAs ? t('pg.panelsB.pipe.creating') : t('pg.panelsB.pipe.create')}
                </button>
                <button className="btn btn-ghost" style={{ fontSize: 11, padding: '2px 8px' }}
                  disabled={savingAs} onClick={() => setSaveOpen(false)}>{t('common.cancel')}</button>
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
