import type { CSSProperties } from 'react'
import ExpressionBuilder from '../../expr/ExpressionBuilder'
import type { PrepStep, DatasetColumn, Dataset } from '../../../services/api'
import { joinPairs, writeJoinPairs } from './join'
import { widgetDataApi } from '../../../services/api'
import { filterFuncCats, optLabel } from './model'
import { useT } from '../../../i18n'
import { navArrows, useDirection } from '../../../contexts/DirectionContext'

const selStyle: CSSProperties = {
  fontSize: 11, padding: '3px 6px', background: 'var(--surface)',
  border: '1px solid var(--border)', borderRadius: 4, color: 'var(--text)', minWidth: 0,
}
const inputStyle: CSSProperties = { ...selStyle, width: '100%' }
const rowStyle: CSSProperties = { display: 'flex', gap: 6, alignItems: 'center', marginTop: 6, flexWrap: 'wrap' }
const labelStyle: CSSProperties = { fontSize: 11, color: 'var(--muted)', minWidth: 60 }
//: Small square control for the per-key add/remove buttons, matching the
//: surrounding inputs rather than introducing a new button size.
const iconBtn: CSSProperties = { ...selStyle, cursor: 'pointer', lineHeight: 1, padding: '3px 6px' }

export function ColSelect({ value, onChange, columns, placeholder }:
  { value: string; onChange: (v: string) => void; columns: { name: string }[]; placeholder?: string }) {
  const t = useT()
  return (
    <select value={value} onChange={e => onChange(e.target.value)} style={selStyle}>
      <option value="">{placeholder ?? t('pg.panelsB.ed.column')}</option>
      {columns.map(c => <option key={c.name} value={c.name}>{c.name}</option>)}
    </select>
  )
}

export function MultiColCheckboxes({ value, onChange, columns }:
  { value: string[]; onChange: (v: string[]) => void; columns: DatasetColumn[] }) {
  const t = useT()
  const toggle = (name: string) => {
    onChange(value.includes(name) ? value.filter(c => c !== name) : [...value, name])
  }
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 4 }}>
      {columns.map(c => (
        <label key={c.name}
          style={{ fontSize: 11, display: 'flex', alignItems: 'center', gap: 3,
            padding: '1px 5px', border: '1px solid var(--border)', borderRadius: 4,
            background: value.includes(c.name) ? 'color-mix(in srgb, var(--accent) 15%, transparent)' : 'var(--surface)' }}>
          <input type="checkbox" checked={value.includes(c.name)} onChange={() => toggle(c.name)}
            style={{ margin: 0 }} />
          <bdi>{c.name}</bdi>
        </label>
      ))}
      {columns.length === 0 && <span style={{ fontSize: 11, color: 'var(--muted)' }}>{t('pg.panelsB.ed.noColumns')}</span>}
    </div>
  )
}

// ── Per-kind mini forms ──────────────────────────────────────────────────────

const numberIn = (value: unknown, fallback: number) => (typeof value === 'number' ? value : fallback)
const hint: CSSProperties = { fontSize: 11, color: 'var(--muted)', marginTop: 4 }

/** One-hot needs its categories up front; this fills them from the data (the
 *  column's values by frequency, under the viewer's own row security). */
function FillCategories({ datasetId, column, onFill }:
  { datasetId?: number; column: string; onFill: (cats: string[]) => void }) {
  const t = useT()
  if (!datasetId || !column) return null
  return (
    <button type="button" className="btn btn-ghost btn-sm" style={{ fontSize: 11 }}
      onClick={() => {
        void widgetDataApi.query(datasetId, { dimension: column, limit: 50 }, [], 'bar')
          .then(r => onFill(((r?.rows as { name?: unknown }[]) || [])
            .map(x => x.name).filter(v => v != null && v !== '').map(String)))
          .catch(() => {})
      }}>{t('pg.panelsB.ed.fillFromData')}</button>
  )
}

export function StepEditor({ step, columns, otherDatasets, joinColumns = [], suggestKeys, onChange, datasetId }: {
  step: PrepStep; columns: DatasetColumn[]; otherDatasets: Dataset[]
  /** Column names of the dataset this step joins to, when it is a join and
      that dataset's columns have loaded. Empty means "not known yet". */
  joinColumns?: string[]
  /** Best known key pair for a candidate target, from the org's relationships. */
  suggestKeys?: (targetId: number) => { left_on: string; right_on: string; source: string } | null
  onChange: (patch: Partial<PrepStep>) => void
  /** The dataset being prepared, for steps that read its values (one-hot). */
  datasetId?: number
}) {
  const t = useT()
  const arrow = navArrows(useDirection().rtl).forward
  switch (step.kind) {
    case 'outliers': {
      const cols = (step.columns as string[]) || []
      return (
        <div>
          <div style={labelStyle}>{t('pg.panelsB.ed.numericColumns')}</div>
          <MultiColCheckboxes value={cols} columns={columns} onChange={v => onChange({ columns: v })} />
          <div style={rowStyle}>
            <select aria-label={t('pg.panelsB.ed.outlierMethod')} value={(step.method as string) || 'iqr'} style={selStyle}
              onChange={e => onChange({ method: e.target.value, k: e.target.value === 'zscore' ? 3 : 1.5 })}>
              <option value="iqr">{t('pg.panelsB.ed.iqr')}</option>
              <option value="zscore">{t('pg.panelsB.ed.zscore')}</option>
            </select>
            <span style={labelStyle}>{t('pg.panelsB.ed.threshold')}</span>
            <input type="number" step="0.1" min={0.1} aria-label={t('pg.panelsB.ed.outlierThreshold')} style={{ ...selStyle, width: 64 }}
              value={numberIn(step.k, step.method === 'zscore' ? 3 : 1.5)}
              onChange={e => onChange({ k: Number(e.target.value) })} />
            <select aria-label={t('pg.panelsB.ed.outlierAction')} value={(step.action as string) || 'flag'} style={selStyle}
              onChange={e => onChange({ action: e.target.value })}>
              <option value="flag">{t('pg.panelsB.ed.actFlag')}</option>
              <option value="remove">{t('pg.panelsB.ed.actRemove')}</option>
              <option value="cap">{t('pg.panelsB.ed.actCap')}</option>
            </select>
          </div>
          {(step.action ?? 'flag') === 'flag' && (
            <div style={rowStyle}>
              <span style={labelStyle}>{t('pg.panelsB.ed.flagColumn')}</span>
              <input value={(step.name as string) ?? '_Outlier_'} style={{ ...selStyle, flex: 1 }}
                aria-label={t('pg.panelsB.ed.flagColumnName')} onChange={e => onChange({ name: e.target.value })} />
            </div>
          )}
          <div style={hint}>
            {step.method === 'zscore'
              ? t('pg.panelsB.ed.zHint', { k: numberIn(step.k, 3) })
              : t('pg.panelsB.ed.iqrHint', { k: numberIn(step.k, 1.5) })}
          </div>
        </div>
      )
    }
    case 'normalize':
      return (
        <div>
          <div style={labelStyle}>{t('pg.panelsB.ed.numericColumns')}</div>
          <MultiColCheckboxes value={(step.columns as string[]) || []} columns={columns}
            onChange={v => onChange({ columns: v })} />
          <div style={rowStyle}>
            <select aria-label={t('pg.panelsB.ed.normMethod')} value={(step.method as string) || 'minmax'} style={selStyle}
              onChange={e => onChange({ method: e.target.value })}>
              <option value="minmax">{t('pg.panelsB.ed.minmax')}</option>
              <option value="zscore">{t('pg.panelsB.ed.zscoreNorm')}</option>
              <option value="log">{t('pg.panelsB.ed.log')}</option>
            </select>
            <span style={labelStyle}>{t('pg.panelsB.ed.suffix')}</span>
            <input value={(step.suffix as string) ?? ''} placeholder={t('pg.panelsB.ed.suffixPh')} style={{ ...selStyle, width: 110 }}
              aria-label={t('pg.panelsB.ed.suffix')} onChange={e => onChange({ suffix: e.target.value })} />
          </div>
        </div>
      )
    case 'encode': {
      const cats = (step.categories as string[]) || []
      return (
        <div>
          <div style={rowStyle}>
            <ColSelect value={(step.column as string) || ''} columns={columns} onChange={v => onChange({ column: v })} />
            <select aria-label={t('pg.panelsB.ed.encMethod')} value={(step.method as string) || 'onehot'} style={selStyle}
              onChange={e => onChange({ method: e.target.value })}>
              <option value="onehot">{t('pg.panelsB.ed.onehot')}</option>
              <option value="label">{t('pg.panelsB.ed.labelCode')}</option>
            </select>
          </div>
          <div style={rowStyle}>
            <input value={cats.join(', ')} style={{ ...selStyle, flex: 1 }} aria-label={t('pg.panelsB.ed.categories')}
              placeholder={step.method === 'label' ? t('pg.panelsB.ed.orderPh') : t('pg.panelsB.ed.categoriesPh')}
              onChange={e => onChange({ categories: e.target.value.split(',').map(s => s.trim()).filter(Boolean) })} />
            <FillCategories datasetId={datasetId} column={(step.column as string) || ''}
              onFill={v => onChange({ categories: v })} />
          </div>
          <label style={{ ...rowStyle, fontSize: 11 }}>
            <input type="checkbox" checked={!!step.drop_original} style={{ margin: 0 }}
              onChange={e => onChange({ drop_original: e.target.checked })} />
            {t('pg.panelsB.ed.dropOriginal')}
          </label>
        </div>
      )
    }
    case 'date_parts': {
      const parts = (step.parts as string[]) || []
      const all = ['year', 'quarter', 'month', 'day', 'weekday', 'hour', 'dayofyear', 'week']
      return (
        <div>
          <ColSelect value={(step.column as string) || ''} columns={columns} placeholder={t('pg.panelsB.ed.dateColumn')}
            onChange={v => onChange({ column: v })} />
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 4 }}>
            {all.map(p => (
              <label key={p} style={{ fontSize: 11, display: 'flex', gap: 3, alignItems: 'center' }}>
                <input type="checkbox" checked={parts.includes(p)} style={{ margin: 0 }}
                  onChange={() => onChange({ parts: parts.includes(p) ? parts.filter(x => x !== p) : [...parts, p] })} />
                {optLabel(t, 'part', p)}
              </label>
            ))}
          </div>
        </div>
      )
    }
    case 'feature_select': {
      const rule = (key: string, label: string, placeholder: string) => (
        <div style={rowStyle}>
          <span style={{ ...labelStyle, minWidth: 150 }}>{label}</span>
          <input type="number" step="any" aria-label={label} placeholder={placeholder} style={{ ...selStyle, width: 80 }}
            value={typeof step[key] === 'number' ? (step[key] as number) : ''}
            onChange={e => onChange({ [key]: e.target.value === '' ? undefined : Number(e.target.value) })} />
        </div>
      )
      return (
        <div>
          {rule('max_missing_pct', t('pg.panelsB.ed.fsMissing'), t('pg.panelsB.ed.eg', { v: 50 }))}
          {rule('min_variance', t('pg.panelsB.ed.fsVariance'), t('pg.panelsB.ed.eg', { v: 0 }))}
          {rule('max_correlation', t('pg.panelsB.ed.fsCorrelation'), t('pg.panelsB.ed.eg', { v: 0.95 }))}
          <div style={{ ...labelStyle, marginTop: 6 }}>{t('pg.panelsB.ed.alwaysKeep')}</div>
          <MultiColCheckboxes value={(step.keep as string[]) || []} columns={columns}
            onChange={v => onChange({ keep: v })} />
          <div style={hint}>{t('pg.panelsB.ed.fsHint')}</div>
        </div>
      )
    }
    case 'pca': {
      const cols = (step.columns as string[]) || []
      return (
        <div>
          <div style={labelStyle}>{t('pg.panelsB.ed.pcaColumns')}</div>
          <MultiColCheckboxes value={cols} columns={columns} onChange={v => onChange({ columns: v })} />
          <div style={rowStyle}>
            <span style={labelStyle}>{t('pg.panelsB.ed.components')}</span>
            <input type="number" min={1} max={Math.max(1, Math.min(cols.length, 10))} aria-label={t('pg.panelsB.ed.components')}
              value={numberIn(step.n, 2)} style={{ ...selStyle, width: 60 }}
              onChange={e => onChange({ n: Math.round(Number(e.target.value)) })} />
            <span style={labelStyle}>{t('pg.panelsB.ed.prefix')}</span>
            <input value={(step.prefix as string) ?? 'PC'} style={{ ...selStyle, width: 60 }} aria-label={t('pg.panelsB.ed.prefix')}
              onChange={e => onChange({ prefix: e.target.value })} />
          </div>
          <div style={hint}>{t('pg.panelsB.ed.pcaHint')}</div>
        </div>
      )
    }
    case 'balance':
      return (
        <div>
          <div style={rowStyle}>
            <ColSelect value={(step.column as string) || ''} columns={columns} placeholder={t('pg.panelsB.ed.classColumn')}
              onChange={v => onChange({ column: v })} />
            <select aria-label={t('pg.panelsB.ed.balMethod')} value={(step.method as string) || 'undersample'} style={selStyle}
              onChange={e => onChange({ method: e.target.value })}>
              <option value="undersample">{t('pg.panelsB.ed.undersample')}</option>
              <option value="oversample">{t('pg.panelsB.ed.oversample')}</option>
            </select>
            <span style={labelStyle}>{t('pg.panelsB.ed.seed')}</span>
            <input type="number" value={numberIn(step.seed, 42)} style={{ ...selStyle, width: 64 }} aria-label={t('pg.panelsB.ed.seed')}
              onChange={e => onChange({ seed: Math.round(Number(e.target.value)) })} />
          </div>
          <div style={rowStyle}>
            <span style={labelStyle}>{t('pg.panelsB.ed.onlyRowsWhere')}</span>
            <ColSelect value={(step.only_column as string) || ''} columns={columns} placeholder={t('pg.panelsB.ed.allRows')}
              onChange={v => onChange({ only_column: v || undefined, only_value: v ? (step.only_value ?? 'Training') : undefined })} />
            {!!step.only_column && (
              <>
                <span style={{ fontSize: 11 }}>=</span>
                <input value={String(step.only_value ?? '')} style={{ ...selStyle, width: 100 }} aria-label={t('pg.panelsB.ed.onlyValue')}
                  onChange={e => onChange({ only_value: e.target.value })} />
              </>
            )}
          </div>
          <div style={hint}>{t('pg.panelsB.ed.balHint')}</div>
        </div>
      )
    case 'append':
      return (
        <div>
          <div style={rowStyle}>
            <select aria-label={t('pg.panelsB.ed.appendDataset')} value={(step.dataset_id as number) ?? ''} style={selStyle}
              onChange={e => onChange({ dataset_id: e.target.value ? Number(e.target.value) : null })}>
              <option value="">{t('pg.panelsB.ed.dataset')}</option>
              {otherDatasets.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>
          </div>
          <div style={rowStyle}>
            <span style={labelStyle}>{t('pg.panelsB.ed.sourceColumn')}</span>
            <input value={(step.source_column as string) ?? ''} placeholder={t('pg.panelsB.ed.sourcePh')}
              style={{ ...selStyle, width: 120 }} aria-label={t('pg.panelsB.ed.sourceColumn')}
              onChange={e => onChange({ source_column: e.target.value || undefined })} />
          </div>
          {!!step.source_column && (
            <div style={rowStyle}>
              <input value={(step.base_label as string) ?? ''} placeholder={t('pg.panelsB.ed.baseLabelPh')} style={{ ...selStyle, flex: 1 }}
                aria-label={t('pg.panelsB.ed.baseLabel')} onChange={e => onChange({ base_label: e.target.value })} />
              <input value={(step.label as string) ?? ''} placeholder={t('pg.panelsB.ed.appLabelPh')} style={{ ...selStyle, flex: 1 }}
                aria-label={t('pg.panelsB.ed.appLabel')} onChange={e => onChange({ label: e.target.value })} />
            </div>
          )}
          <div style={hint}>{t('pg.panelsB.ed.appendHint')}</div>
        </div>
      )
    case 'filter_rows':
      return (
        <ExpressionBuilder
          layout="flat" defaultMode="simple" columns={columns}
          functionsCatalog={filterFuncCats(t)}
          value={(step.expression as string) || ''}
          onChange={v => onChange({ expression: v })}
          placeholder="`amount` > 100" // i18n-ok
          rows={2}
        />
      )
    case 'sort': {
      const cols = (step.columns as { column: string; dir?: string }[]) || []
      return (
        <div>
          {cols.map((c, i) => (
            <div key={i} style={rowStyle}>
              <ColSelect value={c.column} columns={columns}
                onChange={v => onChange({ columns: cols.map((x, j) => j === i ? { ...x, column: v } : x) })} />
              <select value={c.dir ?? 'asc'} style={selStyle}
                onChange={e => onChange({ columns: cols.map((x, j) => j === i ? { ...x, dir: e.target.value } : x) })}>
                <option value="asc">{t('pg.panelsB.ed.ascending')}</option>
                <option value="desc">{t('pg.panelsB.ed.descending')}</option>
              </select>
              <button className="btn btn-ghost btn-sm" style={{ fontSize: 11 }}
                onClick={() => onChange({ columns: cols.filter((_, j) => j !== i) })}>✕</button>
            </div>
          ))}
          <button className="btn btn-ghost btn-sm" style={{ fontSize: 11, marginTop: 4 }}
            onClick={() => onChange({ columns: [...cols, { column: '', dir: 'asc' }] })}>{t('pg.panelsB.ed.addColumn')}</button>
        </div>
      )
    }
    case 'dedupe':
    case 'drop_duplicates':
      return (
        <div>
          <div style={labelStyle}>{t('pg.panelsB.ed.matchOn')}</div>
          <MultiColCheckboxes value={(step.subset as string[]) || []} columns={columns}
            onChange={v => onChange({ subset: v })} />
          {step.kind === 'dedupe' && (
            <div style={rowStyle}>
              <span style={labelStyle}>{t('pg.panelsB.ed.keep')}</span>
              <select aria-label={t('pg.panelsB.ed.whichCopy')} value={(step.keep as string) || 'first'} style={selStyle}
                onChange={e => onChange({ keep: e.target.value })}>
                <option value="first">{t('pg.panelsB.ed.keepFirst')}</option>
                <option value="last">{t('pg.panelsB.ed.keepLast')}</option>
                <option value="none">{t('pg.panelsB.ed.keepNone')}</option>
              </select>
            </div>
          )}
        </div>
      )
    case 'aggregate': {
      const gb = (step.group_by as string[]) || []
      const aggs = (step.aggregations as { column: string; agg: string; as?: string }[]) || []
      return (
        <div>
          <div style={labelStyle}>{t('pg.panelsB.ed.groupBy')}</div>
          <MultiColCheckboxes value={gb} columns={columns} onChange={v => onChange({ group_by: v })} />
          <div style={{ ...labelStyle, marginTop: 6 }}>{t('pg.panelsB.ed.aggregations')}</div>
          {aggs.map((a, i) => (
            <div key={i} style={rowStyle}>
              <ColSelect value={a.column} columns={columns}
                onChange={v => onChange({ aggregations: aggs.map((x, j) => j === i ? { ...x, column: v } : x) })} />
              <select value={a.agg} style={selStyle}
                onChange={e => onChange({ aggregations: aggs.map((x, j) => j === i ? { ...x, agg: e.target.value } : x) })}>
                {['sum', 'avg', 'min', 'max', 'count', 'median', 'nunique'].map(a2 => <option key={a2} value={a2}>{optLabel(t, 'agg', a2)}</option>)}
              </select>
              <input value={a.as ?? ''} placeholder={t('pg.panelsB.ed.as')} style={{ ...selStyle, width: 80 }}
                onChange={e => onChange({ aggregations: aggs.map((x, j) => j === i ? { ...x, as: e.target.value } : x) })} />
              <button className="btn btn-ghost btn-sm" style={{ fontSize: 11 }}
                onClick={() => onChange({ aggregations: aggs.filter((_, j) => j !== i) })}>✕</button>
            </div>
          ))}
          <button className="btn btn-ghost btn-sm" style={{ fontSize: 11, marginTop: 4 }}
            onClick={() => onChange({ aggregations: [...aggs, { column: '', agg: 'sum', as: '' }] })}>{t('pg.panelsB.ed.addAgg')}</button>
        </div>
      )
    }
    case 'rename':
      return (
        <div style={rowStyle}>
          <ColSelect value={(step.column as string) || ''} columns={columns} onChange={v => onChange({ column: v })} />
          <span style={{ fontSize: 11 }}>{arrow}</span>
          <input value={(step.to as string) || ''} placeholder={t('pg.panelsB.ed.newName')} style={{ ...selStyle, flex: 1 }}
            onChange={e => onChange({ to: e.target.value })} />
        </div>
      )
    case 'retype':
      return (
        <div style={rowStyle}>
          <ColSelect value={(step.column as string) || ''} columns={columns} onChange={v => onChange({ column: v })} />
          <select value={(step.to as string) || 'text'} style={selStyle} onChange={e => onChange({ to: e.target.value })}>
            {['numeric', 'text', 'datetime'].map(ty => <option key={ty} value={ty}>{optLabel(t, 'type', ty)}</option>)}
          </select>
        </div>
      )
    case 'split':
      return (
        <div>
          <div style={rowStyle}>
            <ColSelect value={(step.column as string) || ''} columns={columns} onChange={v => onChange({ column: v })} />
            <input value={(step.delimiter as string) || ''} placeholder={t('pg.panelsB.ed.delimiter')} style={{ ...selStyle, width: 70 }}
              onChange={e => onChange({ delimiter: e.target.value })} />
          </div>
          <input value={((step.into as string[]) || []).join(', ')} placeholder={t('pg.panelsB.ed.newNames')}
            style={{ ...inputStyle, marginTop: 4 }}
            onChange={e => onChange({ into: e.target.value.split(',').map(s => s.trim()).filter(Boolean) })} />
        </div>
      )
    case 'trim':
      return (
        <div>
          <div style={labelStyle}>{t('pg.panelsB.ed.trimCols')}</div>
          <MultiColCheckboxes value={(step.columns as string[]) || []} columns={columns}
            onChange={v => onChange({ columns: v })} />
        </div>
      )
    case 'case':
      return (
        <div style={rowStyle}>
          <ColSelect value={(step.column as string) || ''} columns={columns} onChange={v => onChange({ column: v })} />
          <select value={(step.to as string) || 'upper'} style={selStyle} onChange={e => onChange({ to: e.target.value })}>
            {['upper', 'lower', 'title'].map(c => <option key={c} value={c}>{optLabel(t, 'case', c)}</option>)}
          </select>
        </div>
      )
    case 'replace':
      return (
        <div>
          <div style={rowStyle}>
            <ColSelect value={(step.column as string) || ''} columns={columns} onChange={v => onChange({ column: v })} />
            <select value={(step.match as string) || 'exact'} style={selStyle} onChange={e => onChange({ match: e.target.value })}>
              <option value="exact">{optLabel(t, 'match', 'exact')}</option>
              <option value="contains">{optLabel(t, 'match', 'contains')}</option>
            </select>
          </div>
          <div style={rowStyle}>
            <input value={(step.find as string) ?? ''} placeholder={t('pg.panelsB.ed.find')} style={{ ...selStyle, flex: 1 }}
              onChange={e => onChange({ find: e.target.value })} />
            <span style={{ fontSize: 11 }}>{arrow}</span>
            <input value={(step.replace as string) ?? ''} placeholder={t('pg.panelsB.ed.replaceWith')} style={{ ...selStyle, flex: 1 }}
              onChange={e => onChange({ replace: e.target.value })} />
          </div>
        </div>
      )
    case 'remove_columns':
      return <MultiColCheckboxes value={(step.columns as string[]) || []} columns={columns}
        onChange={v => onChange({ columns: v })} />
    case 'drop_nulls':
      return (
        <div>
          <div style={labelStyle}>{t('pg.panelsB.ed.nullCols')}</div>
          <MultiColCheckboxes value={(step.columns as string[]) || []} columns={columns}
            onChange={v => onChange({ columns: v })} />
        </div>
      )
    case 'partition':
      return (
        <div>
          <div style={rowStyle}>
            <span style={labelStyle}>{t('pg.panelsB.ed.column1')}</span>
            <input value={(step.name as string) ?? ''} placeholder="_Partition_" // i18n-ok style={{ ...selStyle, flex: 1 }}
              aria-label={t('pg.panelsB.ed.partitionName')} onChange={e => onChange({ name: e.target.value })} />
          </div>
          <div style={rowStyle}>
            <span style={labelStyle}>{t('pg.panelsB.ed.trainingPct')}</span>
            <input type="number" min={1} max={99} value={(step.train_pct as number) ?? 70} style={{ ...selStyle, width: 64 }}
              aria-label={t('pg.panelsB.ed.trainingPercent')} onChange={e => onChange({ train_pct: Number(e.target.value) })} />
            <span style={labelStyle}>{t('pg.panelsB.ed.testPct')}</span>
            <input type="number" min={0} max={98} value={(step.test_pct as number) ?? 0} style={{ ...selStyle, width: 64 }}
              aria-label={t('pg.panelsB.ed.testPercent')} onChange={e => onChange({ test_pct: Number(e.target.value) || undefined })} />
            <span style={labelStyle}>{t('pg.panelsB.ed.seed')}</span>
            <input type="number" value={(step.seed as number) ?? 42} style={{ ...selStyle, width: 64 }}
              aria-label={t('pg.panelsB.ed.seed')} onChange={e => onChange({ seed: Math.round(Number(e.target.value)) })} />
          </div>
          <div style={rowStyle}>
            <span style={labelStyle}>{t('pg.panelsB.ed.keepTogether')}</span>
            <ColSelect value={(step.key as string) || ''} columns={columns} placeholder={t('pg.panelsB.ed.eachRow')}
              onChange={v => onChange({ key: v || undefined })} />
          </div>
          <div style={rowStyle}>
            <span style={labelStyle}>{t('pg.panelsB.ed.stratifyBy')}</span>
            <ColSelect value={(step.stratify as string) || ''} columns={columns} placeholder={t('pg.panelsB.ed.noStrat')}
              onChange={v => onChange({ stratify: v || undefined })} />
          </div>
          <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 4 }}>
            {t((step.test_pct as number) ? 'pg.panelsB.ed.partHintTest' : 'pg.panelsB.ed.partHint')}
          </div>
        </div>
      )
    case 'fill_nulls':
      return (
        <div>
          <div style={rowStyle}>
            <ColSelect value={(step.column as string) || ''} columns={columns} onChange={v => onChange({ column: v })} />
            <select value={(step.method as string) || 'value'} style={selStyle} onChange={e => onChange({ method: e.target.value })}>
              {['value', 'zero', 'mean', 'median', 'mode', 'ffill', 'bfill', 'interpolate'].map(m => <option key={m} value={m}>{optLabel(t, 'fill', m)}</option>)}
            </select>
          </div>
          {step.method === 'value' && (
            <input value={(step.value as string) ?? ''} placeholder={t('pg.panelsB.ed.fillValue')} style={{ ...inputStyle, marginTop: 4 }}
              onChange={e => onChange({ value: e.target.value })} />
          )}
        </div>
      )
    case 'join': {
      const pairs = joinPairs(step)
      const hit = typeof step.dataset_id === 'number' ? suggestKeys?.(step.dataset_id) : null
      // Only claim provenance when the keys on screen ARE the suggested ones --
      // an author who overrode them must not be told they came from a model.
      const matched = hit && pairs.length === 1
        && hit.left_on === pairs[0].left && hit.right_on === pairs[0].right ? hit : null
      const setPair = (i: number, patch: Partial<{ left: string; right: string }>) =>
        onChange(writeJoinPairs(pairs.map((p, j) => (j === i ? { ...p, ...patch } : p))))
      return (
        <div>
          <div style={rowStyle}>
            <select value={(step.dataset_id as number) ?? ''} style={selStyle}
              onChange={e => {
                const id = e.target.value ? Number(e.target.value) : null
                // A modelled or inferred relationship already knows how these
                // two tables connect; typing it again is busywork and a chance
                // to get it wrong. Still fully editable afterwards.
                const s2 = id !== null ? suggestKeys?.(id) : null
                onChange({
                  dataset_id: id,
                  ...writeJoinPairs(s2 ? [{ left: s2.left_on, right: s2.right_on }]
                                       : [{ left: '', right: '' }]),
                })
              }}>
              <option value="">{t('pg.panelsB.ed.dataset')}</option>
              {otherDatasets.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>
            <select value={(step.how as string) || 'left'} style={selStyle} onChange={e => onChange({ how: e.target.value })}>
              {['left', 'right', 'inner', 'full'].map(h => <option key={h} value={h}>{optLabel(t, 'how', h)}</option>)}
            </select>
          </div>
          {pairs.map((p, i) => (
            <div key={i} style={rowStyle}>
              <ColSelect value={p.left} columns={columns} placeholder={t('pg.panelsB.ed.thisColumn')}
                onChange={v => setPair(i, { left: v })} />
              <span style={{ fontSize: 11 }}>=</span>
              {joinColumns.length ? (
                <ColSelect value={p.right} columns={joinColumns.map(name => ({ name }))}
                  placeholder={t('pg.panelsB.ed.theirColumnSel')} onChange={v => setPair(i, { right: v })} />
              ) : (
                // No target chosen yet, or its columns are still loading: stay
                // typable rather than presenting an empty, unusable dropdown.
                <input value={p.right} placeholder={t('pg.panelsB.ed.theirColumn')} style={{ ...selStyle, flex: 1 }}
                  onChange={e => setPair(i, { right: e.target.value })} />
              )}
              {pairs.length > 1 && (
                <button type="button" aria-label={t('pg.panelsB.ed.removeKey', { n: i + 1 })} style={iconBtn}
                  onClick={() => onChange(writeJoinPairs(pairs.filter((_, j) => j !== i)))}>×</button>
              )}
            </div>
          ))}
          {/* Only offered, never imposed: a one-column join -- the common case --
              looks exactly as it did before. A second key is what keeps the
              grain when one column alone matches too many rows. */}
          <button type="button" style={{ ...iconBtn, width: 'auto', padding: '0 6px', fontSize: 11 }}
            onClick={() => onChange(writeJoinPairs([...pairs, { left: '', right: '' }]))}>
            {t('pg.panelsB.ed.addKey')}
          </button>
          {matched && (
            <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 2 }}>
              {matched.source === 'inferred'
                ? t('pg.panelsB.ed.keysDetected')
                : t('pg.panelsB.ed.keysFrom', { source: optLabel(t, 'relSource', matched.source) })}
            </div>
          )}
        </div>
      )
    }
    default:
      return null
  }
}
