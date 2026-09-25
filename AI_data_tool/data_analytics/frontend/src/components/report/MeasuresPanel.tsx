import { useState, useEffect } from 'react'
import { measuresApi } from '../../services/api'
import type { DatasetColumn, MeasureDef, MeasurePreviewResult } from '../../services/api'
import ExpressionBuilder from '../expr/ExpressionBuilder'
import { useConfirm } from '../ui/ConfirmDialog'

/**
 * Authoring surface for post-aggregation measures.
 *
 * Deliberately not a copy of CalcColumnsPanel: the palette here binds to the
 * *group-aware* namespace, so it offers TOTAL() and omits the row-level window and
 * group-by families, which have no meaning once data is already aggregated. The
 * preview takes an optional grouping column so the sample matches what a real visual
 * would render rather than a single whole-table scalar.
 */

interface FuncItem { label: string; snippet: string; back?: number; hint: string }
interface FuncCat { label: string; color: string; items: FuncItem[] }

const FUNC_CATS: FuncCat[] = [
  {
    label: 'Aggregation (within the visual’s group)', color: '#f472b6',
    items: [
      { label: 'SUM(col)',      snippet: 'SUM()',      back: 1, hint: 'Total per group in the current visual' },
      { label: 'AVG(col)',      snippet: 'AVG()',      back: 1, hint: 'Mean per group' },
      { label: 'MEDIAN(col)',   snippet: 'MEDIAN()',   back: 1, hint: 'Middle value per group' },
      { label: 'COUNT(col)',    snippet: 'COUNT()',    back: 1, hint: 'Non-null count per group' },
      { label: 'COUNTD(col)',   snippet: 'COUNTD()',   back: 1, hint: 'Distinct count per group' },
      { label: 'STDEV(col)',    snippet: 'STDEV()',    back: 1, hint: 'Standard deviation per group' },
      { label: 'VARIANCE(col)', snippet: 'VARIANCE()', back: 1, hint: 'Variance per group' },
    ],
  },
  {
    label: 'Grouping context', color: '#22d3ee',
    items: [
      { label: 'TOTAL(expr)', snippet: 'TOTAL()', back: 1,
        hint: 'Ignores the visual’s grouping — use it for the denominator of a percent-of-total' },
      { label: 'BYGROUP(expr, "col")', snippet: 'BYGROUP(, "")', back: 2,
        hint: 'Regroup by a named column regardless of the visual — e.g. SUM(sales) / BYGROUP(SUM(sales), "region") is each group’s share of its region' },
      // The engine has had this since the measures work landed and the palette
      // never mentioned it, so the only way to reach it was to already know the
      // name. TOTAL and BYGROUP change the GROUPING an aggregate is evaluated
      // at; this changes the ROWS — the third of the three, and the one the
      // capability audit called the modelling gap.
      { label: 'SCOPE(default, "level", expr…)', snippet: 'SCOPE(, "", )', back: 7,
        hint: 'A different formula per level: SCOPE(SUM(sales), "product", SUM(sales) / TOTAL(SUM(sales)), "", COUNT(sales)) shows a share on product rows and a count on the grand total. "" is the grand total, "a,b" two columns together; other levels use the default. Branches not chosen are never run.' },
      { label: 'ISINSCOPE("col")', snippet: 'ISINSCOPE("")', back: 2,
        hint: 'True when the value is grouped by this column — for IF(). Both IF branches still run; use SCOPE when one cannot run at every level.' },
      { label: 'CALC(expr, "filter")', snippet: 'CALC(, "")', back: 2,
        hint: 'Evaluate under a different row filter than the visual’s — e.g. SUM(sales) / CALC(SUM(sales), "`region` == \'EMEA\'") compares each group against EMEA. The filter uses the same grammar as a report filter or a row-security rule.' },
    ],
  },
  {
    label: 'Conditional', color: '#c084fc',
    items: [
      { label: 'IF(cond,yes,no)',           snippet: 'IF(, , )',       back: 5, hint: 'Return yes if condition true, else no' },
      { label: 'SWITCH(col,v1,r1,default)', snippet: 'SWITCH(, , , )', back: 7, hint: 'Map values: col==v1→r1, else default' },
      { label: 'isnull(x)',                 snippet: 'isnull()',       back: 1, hint: 'True if value is missing' },
    ],
  },
  {
    label: 'Numeric', color: '#60a5fa',
    items: [
      { label: 'abs(x)',     snippet: 'abs()',      back: 1, hint: 'Absolute value' },
      { label: 'round(x,n)', snippet: 'round(, 2)', back: 4, hint: 'Round to n decimals' },
      { label: 'sqrt(x)',    snippet: 'sqrt()',     back: 1, hint: 'Square root' },
      { label: 'floor(x)',   snippet: 'floor()',    back: 1, hint: 'Round down' },
      { label: 'ceil(x)',    snippet: 'ceil()',     back: 1, hint: 'Round up' },
      { label: 'log(x)',     snippet: 'log()',      back: 1, hint: 'Natural logarithm' },
    ],
  },
]

const AGG_OPTIONS = ['sum', 'avg', 'min', 'max', 'count']

const BLANK: MeasureDef = { name: '', expression: '', default_aggregation: 'sum' }

interface Props {
  datasetId: number
  columns: DatasetColumn[]
  onChanged: (measures: MeasureDef[]) => void
}

export default function MeasuresPanel({ datasetId, columns, onChanged }: Props) {
  const confirm = useConfirm()
  const [measures, setMeasures] = useState<MeasureDef[]>([])
  const [editing, setEditing] = useState<MeasureDef | null>(null)
  const [groupBy, setGroupBy] = useState('')
  const [preview, setPreview] = useState<MeasurePreviewResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [loadFailed, setLoadFailed] = useState(false)

  useEffect(() => {
    let alive = true
    // The swallowed catch showed "No measures yet" on a failed load -- an
    // author could then define a measure that already exists and collide.
    measuresApi.list(datasetId)
      .then(m => { if (alive) { setMeasures(m); setLoadFailed(false) } })
      .catch(() => { if (alive) setLoadFailed(true) })
    return () => { alive = false }
  }, [datasetId])

  const runPreview = async () => {
    if (!editing?.expression.trim()) return
    setBusy(true)
    try {
      const body: { expression: string; group_by?: string } = { expression: editing.expression }
      if (groupBy) body.group_by = groupBy
      setPreview(await measuresApi.preview(datasetId, body))
    } finally {
      setBusy(false)
    }
  }

  const save = async () => {
    if (!editing?.name.trim() || !editing.expression.trim()) {
      setError('A measure needs both a name and an expression')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const next = await measuresApi.save(datasetId, editing)
      setMeasures(next)
      onChanged(next)
      setEditing(null)
      setPreview(null)
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'Could not save this measure')
    } finally {
      setBusy(false)
    }
  }

  const remove = async (name: string) => {
    // A measure is referenced by name. Deleting one does not just remove a row
    // here -- every widget across every report that uses it stops resolving,
    // and nothing in this panel can show which those are.
    if (!await confirm({
      title: `Delete the measure "${name}"?`,
      body: 'Any widget using it stops working, in this report and every other one. This cannot be undone.',
    })) return
    let next: MeasureDef[]
    try {
      next = await measuresApi.delete(datasetId, name)
    } catch (e: any) {
      // E05: something still names it, so the server refused with the list.
      // This used to reject unhandled -- the person confirmed and nothing happened.
      if (e?.response?.status !== 409) throw e
      if (!await confirm({
        title: `"${name}" is still in use`,
        body: `${e.response.data?.detail ?? ''} Deleting it breaks those.`.replace(/ Delete anyway with \?force=true\./, ''),
        confirmLabel: 'Delete anyway', destructive: true,
      })) return
      next = await measuresApi.delete(datasetId, name, true)
    }
    setMeasures(next)
    onChanged(next)
  }

  const dimensionCols = columns.filter(c => c.dtype !== 'numeric')

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <div style={{ flex: 1, fontSize: 11, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.06em' }}>
          ƒx Measures
        </div>
        <button className="btn btn-ghost btn-sm" style={{ fontSize: 11 }}
          onClick={() => { setEditing({ ...BLANK }); setPreview(null); setError(null) }}>
          + Add measure
        </button>
      </div>

      <p style={{ fontSize: 10.5, color: 'var(--muted)', margin: '0 0 8px', lineHeight: 1.45 }}>
        Evaluated after filters, at the grouping of whichever visual uses it — so a
        percent-of-total re-bases when a cross-filter narrows the data.
      </p>

      {measures.length === 0 && !editing && (
        <p style={{ fontSize: 11, color: 'var(--muted)', textAlign: 'center', padding: '8px 0' }}>
          No measures yet
        </p>
      )}

      {measures.map(m => (
        <div key={m.name} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '5px 7px',
          background: 'var(--surface2)', borderRadius: 5, marginBottom: 3, fontSize: 11 }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontWeight: 600 }}>{m.name}</div>
            <div style={{ fontFamily: 'var(--mono)', fontSize: 10.5, color: 'var(--muted)',
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {m.expression}
            </div>
          </div>
          <button title={`Edit ${m.name}`} aria-label={`Edit ${m.name}`}
            onClick={() => { setEditing({ ...m }); setPreview(null); setError(null) }}
            style={{ background: 'none', border: 'none', color: 'var(--muted)', cursor: 'pointer', fontSize: 11 }}>✎</button>
          <button title={`Delete ${m.name}`} aria-label={`Delete ${m.name}`}
            onClick={() => remove(m.name)}
            style={{ background: 'none', border: 'none', color: 'var(--muted)', cursor: 'pointer', fontSize: 13, lineHeight: 1 }}>×</button>
        </div>
      ))}

      {editing && (
        <div style={{ marginTop: 8, border: '1px solid var(--border)', borderRadius: 6, padding: 10 }}>
          <input value={editing.name} placeholder="Measure name (e.g. Sales % of Total)"
            onChange={e => setEditing({ ...editing, name: e.target.value })}
            style={{ width: '100%', marginBottom: 6, fontSize: 12 }} />

          <div style={{ marginBottom: 6 }}>
            <ExpressionBuilder
              layout="flat"
              columns={columns}
              functionsCatalog={FUNC_CATS}
              value={editing.expression}
              onChange={next => setEditing(e => (e ? { ...e, expression: next } : e))}
              placeholder="SUM(sales) / TOTAL(SUM(sales)) * 100"
              rows={3}
            />
          </div>

          {/* Preview grain + default aggregation */}
          <div style={{ display: 'flex', gap: 8, marginBottom: 8, flexWrap: 'wrap' }}>
            <label style={{ display: 'flex', flexDirection: 'column', gap: 2, flex: 1, minWidth: 120 }}>
              <span style={{ fontSize: 10.5, color: 'var(--muted)' }}>Group by (preview only)</span>
              <select aria-label="Group by" value={groupBy} onChange={e => setGroupBy(e.target.value)}
                style={{ fontSize: 11, width: '100%' }}>
                <option value="">— whole table —</option>
                {dimensionCols.map(c => <option key={c.name} value={c.name}>{c.name}</option>)}
              </select>
            </label>
            <label style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 96 }}>
              <span style={{ fontSize: 10.5, color: 'var(--muted)' }}>Default agg</span>
              <select value={editing.default_aggregation ?? 'sum'}
                onChange={e => setEditing({ ...editing, default_aggregation: e.target.value })}
                style={{ fontSize: 11 }}>
                {AGG_OPTIONS.map(a => <option key={a} value={a}>{a}</option>)}
              </select>
            </label>
          </div>

          {preview && (
            <div style={{ marginBottom: 8, fontSize: 10.5, padding: '6px 8px', borderRadius: 5,
              background: preview.ok ? 'rgba(52,211,153,.12)' : 'rgba(248,113,113,.12)',
              color: preview.ok ? 'var(--text)' : '#f87171' }}>
              {preview.ok ? (
                <>
                  <div style={{ color: 'var(--muted)', marginBottom: 3 }}>Preview ({preview.dtype})</div>
                  {(preview.sample ?? []).map((s, i) => (
                    <div key={i} style={{ fontFamily: 'var(--mono)' }}>
                      {s.group !== null && s.group !== undefined ? `${s.group}: ` : ''}{String(s.value)}
                    </div>
                  ))}
                </>
              ) : preview.error}
            </div>
          )}

          {error && (
            <div style={{ marginBottom: 8, fontSize: 10.5, color: '#f87171' }}>{error}</div>
          )}

          <div style={{ display: 'flex', gap: 6 }}>
            <button className="btn btn-ghost btn-sm" style={{ fontSize: 11 }} disabled={busy} onClick={runPreview}>
              Test
            </button>
            <button className="btn btn-primary btn-sm" style={{ fontSize: 11, marginInlineStart: 'auto' }} disabled={busy} onClick={save}>
              Save
            </button>
            <button className="btn btn-ghost btn-sm" style={{ fontSize: 11 }}
              onClick={() => { setEditing(null); setPreview(null); setError(null) }}>
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
