import { useState, useEffect } from 'react'
import { measuresApi } from '../../services/api'
import type { DatasetColumn, MeasureDef, MeasurePreviewResult } from '../../services/api'
import ExpressionBuilder from '../expr/ExpressionBuilder'
import MeasureTemplatePicker from './MeasureTemplatePicker'
import { problemText } from './calcColumns/TestResult'
import type { MeasureTemplateKey } from '../../lib/measureTemplates'
import { useConfirm } from '../ui/ConfirmDialog'
import { useT, type TranslateFn } from '../../i18n'

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

/** The palette, in the reader's language. Function signatures stay as typed. */
const funcCats = (t: TranslateFn): FuncCat[] => [
  {
    label: t('pg.panelsA.ms.cat.agg'), color: '#f472b6',
    items: [
      { label: 'SUM(col)',      snippet: 'SUM()',      back: 1, hint: t('pg.panelsA.ms.hint.sum') }, // i18n-ok
      { label: 'AVG(col)',      snippet: 'AVG()',      back: 1, hint: t('pg.panelsA.ms.hint.avg') }, // i18n-ok
      { label: 'MEDIAN(col)',   snippet: 'MEDIAN()',   back: 1, hint: t('pg.panelsA.ms.hint.median') }, // i18n-ok
      { label: 'COUNT(col)',    snippet: 'COUNT()',    back: 1, hint: t('pg.panelsA.ms.hint.count') }, // i18n-ok
      { label: 'COUNTD(col)',   snippet: 'COUNTD()',   back: 1, hint: t('pg.panelsA.ms.hint.countd') }, // i18n-ok
      { label: 'STDEV(col)',    snippet: 'STDEV()',    back: 1, hint: t('pg.panelsA.ms.hint.stdev') }, // i18n-ok
      { label: 'VARIANCE(col)', snippet: 'VARIANCE()', back: 1, hint: t('pg.panelsA.ms.hint.variance') }, // i18n-ok
    ],
  },
  {
    label: t('pg.panelsA.ms.cat.grouping'), color: '#22d3ee',
    items: [
      { label: 'TOTAL(expr)', snippet: 'TOTAL()', back: 1, // i18n-ok
        hint: t('pg.panelsA.ms.hint.total') },
      { label: 'BYGROUP(expr, "col")', snippet: 'BYGROUP(, "")', back: 2, // i18n-ok
        hint: t('pg.panelsA.ms.hint.bygroup') },
      // The engine has had this since the measures work landed and the palette
      // never mentioned it, so the only way to reach it was to already know the
      // name. TOTAL and BYGROUP change the GROUPING an aggregate is evaluated
      // at; this changes the ROWS — the third of the three, and the one the
      // capability audit called the modelling gap.
      { label: 'SCOPE(default, "level", expr…)', snippet: 'SCOPE(, "", )', back: 7, // i18n-ok
        hint: t('pg.panelsA.ms.hint.scope') },
      { label: 'ISINSCOPE("col")', snippet: 'ISINSCOPE("")', back: 2, // i18n-ok
        hint: t('pg.panelsA.ms.hint.isinscope') },
      { label: 'CALC(expr, "filter")', snippet: 'CALC(, "")', back: 2, // i18n-ok
        hint: t('pg.panelsA.ms.hint.calc') },
    ],
  },
  {
    label: t('pg.panelsA.ms.cat.conditional'), color: '#c084fc',
    items: [
      { label: 'IF(cond,yes,no)',           snippet: 'IF(, , )',       back: 5, hint: t('pg.panelsA.ms.hint.if') }, // i18n-ok
      { label: 'SWITCH(col,v1,r1,default)', snippet: 'SWITCH(, , , )', back: 7, hint: t('pg.panelsA.ms.hint.switch') }, // i18n-ok
      { label: 'isnull(x)',                 snippet: 'isnull()',       back: 1, hint: t('pg.panelsA.ms.hint.isnull') }, // i18n-ok
    ],
  },
  {
    label: t('pg.panelsA.ms.cat.numeric'), color: '#60a5fa',
    items: [
      { label: 'abs(x)',     snippet: 'abs()',      back: 1, hint: t('pg.panelsA.ms.hint.abs') }, // i18n-ok
      { label: 'round(x,n)', snippet: 'round(, 2)', back: 4, hint: t('pg.panelsA.ms.hint.round') }, // i18n-ok
      { label: 'sqrt(x)',    snippet: 'sqrt()',     back: 1, hint: t('pg.panelsA.ms.hint.sqrt') }, // i18n-ok
      { label: 'floor(x)',   snippet: 'floor()',    back: 1, hint: t('pg.panelsA.ms.hint.floor') }, // i18n-ok
      { label: 'ceil(x)',    snippet: 'ceil()',     back: 1, hint: t('pg.panelsA.ms.hint.ceil') }, // i18n-ok
      { label: 'log(x)',     snippet: 'log()',      back: 1, hint: t('pg.panelsA.ms.hint.log') }, // i18n-ok
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
  const t = useT()
  const [measures, setMeasures] = useState<MeasureDef[]>([])
  const [editing, setEditing] = useState<MeasureDef | null>(null)
  const [groupBy, setGroupBy] = useState('')
  const [preview, setPreview] = useState<MeasurePreviewResult | null>(null)
  // A NEW measure starts from "What do you want to measure?"; one being edited
  // opens as its formula. A name the person typed is never replaced.
  const [mode, setMode] = useState<'pick' | 'formula'>('formula')
  const [template, setTemplate] = useState<MeasureTemplateKey | null>(null)
  const [nameTouched, setNameTouched] = useState(false)
  const [showDetails, setShowDetails] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  /** Which measure's earlier formulas are open (E05 metric versions). */
  const [historyOf, setHistoryOf] = useState<string | null>(null)

  const restore = async (name: string, version: number) => {
    try {
      const next = await measuresApi.restore(datasetId, name, version)
      setMeasures(next)
      onChanged(next)
      setHistoryOf(null)
    } catch (e: any) {
      // A restored formula is re-validated: a column it used may since have gone.
      setError(e?.response?.data?.detail ?? t('pg.panelsA.ms.restoreFailed'))
    }
  }

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
      setError(t('pg.panelsA.ms.needBoth'))
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
      setError(e?.response?.data?.detail ?? t('pg.panelsA.ms.saveFailed'))
    } finally {
      setBusy(false)
    }
  }

  const remove = async (name: string) => {
    // A measure is referenced by name. Deleting one does not just remove a row
    // here -- every widget across every report that uses it stops resolving,
    // and nothing in this panel can show which those are.
    if (!await confirm({
      title: t('pg.panelsA.ms.deleteTitle', { name }),
      body: t('pg.panelsA.ms.deleteBody'),
    })) return
    let next: MeasureDef[]
    try {
      next = await measuresApi.delete(datasetId, name)
    } catch (e: any) {
      // E05: something still names it, so the server refused with the list.
      // This used to reject unhandled -- the person confirmed and nothing happened.
      if (e?.response?.status !== 409) throw e
      if (!await confirm({
        title: t('pg.panelsA.inUse', { name }),
        body: t('pg.panelsA.inUseBody', { detail: String(e.response.data?.detail ?? '').replace(/ Delete anyway with \?force=true\./, '') }),
        confirmLabel: t('pg.panelsA.deleteAnyway'), destructive: true,
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
          {t('pg.panelsA.ms.title')}
        </div>
        <button className="btn btn-ghost btn-sm" style={{ fontSize: 11 }}
          onClick={() => { setEditing({ ...BLANK }); setPreview(null); setError(null); setMode('pick'); setTemplate(null); setNameTouched(false) }}>
          {t('pg.panelsA.ms.add')}
        </button>
      </div>

      <p style={{ fontSize: 10.5, color: 'var(--muted)', margin: '0 0 8px', lineHeight: 1.45 }}>
        {t('pg.panelsA.ms.intro')}
      </p>

      {measures.length === 0 && !editing && (
        <p style={{ fontSize: 11, color: 'var(--muted)', textAlign: 'center', padding: '8px 0' }}>
          {t('pg.panelsA.ms.none')}
        </p>
      )}

      {measures.map(m => (
        <div key={m.name} style={{ marginBottom: 3 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '5px 7px',
          background: 'var(--surface2)', borderRadius: 5, fontSize: 11 }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6 }}>
              <bdi>{m.name}</bdi>
              {/* E05: a formula that has changed says so -- every chart, export
                  and AI answer on it changed with it. */}
              {(m.history?.length ?? 0) > 0 && (
                <button type="button" aria-expanded={historyOf === m.name}
                  aria-label={t('pg.panelsA.ms.versionAria', { v: m.version ?? 1, name: m.name })}
                  onClick={() => setHistoryOf(historyOf === m.name ? null : m.name)}
                  style={{ background: 'none', border: '1px solid var(--border)', borderRadius: 99, cursor: 'pointer',
                    fontSize: 10, padding: '0 6px', color: 'var(--muted)', fontWeight: 500 }}>
                  v{m.version ?? 1}
                </button>
              )}
            </div>
            <div style={{ fontFamily: 'var(--mono)', fontSize: 10.5, color: 'var(--muted)',
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              <bdi dir="ltr">{m.expression}</bdi>
            </div>
          </div>
          <button title={t('pg.panelsA.editNamed', { name: m.name })} aria-label={t('pg.panelsA.editNamed', { name: m.name })}
            onClick={() => { setEditing({ ...m }); setPreview(null); setError(null); setMode('formula'); setNameTouched(true) }}
            style={{ background: 'none', border: 'none', color: 'var(--muted)', cursor: 'pointer', fontSize: 11 }}>✎</button>
          <button title={t('pg.panelsA.deleteNamed', { name: m.name })} aria-label={t('pg.panelsA.deleteNamed', { name: m.name })}
            onClick={() => remove(m.name)}
            style={{ background: 'none', border: 'none', color: 'var(--muted)', cursor: 'pointer', fontSize: 13, lineHeight: 1 }}>×</button>
        </div>
        {historyOf === m.name && (
          <ul aria-label={t('pg.panelsA.ms.historyAria', { name: m.name })}
            style={{ listStyle: 'none', margin: '2px 0 4px 10px', padding: 0, fontSize: 10.5 }}>
            {[...(m.history ?? [])].reverse().map(h => (
              <li key={h.version} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '2px 0' }}>
                <span style={{ color: 'var(--muted)', minWidth: 22 }}>v{h.version}</span>
                <span style={{ flex: 1, minWidth: 0, fontFamily: 'var(--mono)', overflow: 'hidden',
                  textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={h.expression} dir="ltr">{h.expression}</span>
                {h.saved_at && <span style={{ color: 'var(--muted)' }}>{h.saved_at.slice(0, 10)}</span>}
                <button type="button" className="btn btn-ghost btn-sm" style={{ fontSize: 10, padding: '0 6px' }}
                  aria-label={t('pg.panelsA.ms.restoreAria', { v: h.version, name: m.name })}
                  onClick={() => void restore(m.name, h.version)}>{t('pg.panelsA.ms.restore')}</button>
              </li>
            ))}
          </ul>
        )}
        </div>
      ))}

      {editing && (
        <div style={{ marginTop: 8, border: '1px solid var(--border)', borderRadius: 6, padding: 10 }}>
          <input value={editing.name} placeholder={t('pg.panelsA.ms.namePh')}
            onChange={e => { setEditing({ ...editing, name: e.target.value }); setNameTouched(true) }}
            aria-label={t('pg.panelsA.mt.name')}
            style={{ width: '100%', marginBottom: 6, fontSize: 12 }} />

          {mode === 'pick' ? (
            <div style={{ marginBottom: 8 }}>
              <MeasureTemplatePicker columns={columns} template={template} onTemplate={setTemplate}
                onWriteFormula={() => setMode('formula')}
                onBuilt={built => {
                  const next = built?.expression ?? ''
                  if (next === editing.expression) return
                  setEditing(e => e ? { ...e, expression: next, ...(built && !nameTouched ? { name: built.name } : {}) } : e)
                  setPreview(null)
                }} />
              {template && (
                <div style={{ marginTop: 8, fontSize: 11 }}>
                  <div style={{ color: 'var(--muted)', marginBottom: 2 }}>{t('pg.panelsA.tpl.written')}</div>
                  <code data-testid="measure-written-formula" dir={editing.expression ? 'ltr' : undefined}
                    style={{ display: 'block', padding: '5px 7px', background: 'var(--surface2)', border: '1px solid var(--border)',
                      borderRadius: 5, wordBreak: 'break-word' }}>
                    {editing.expression || t('pg.panelsA.tpl.notYet')}
                  </code>
                  {editing.expression && (
                    <button type="button" onClick={() => setMode('formula')}
                      style={{ border: 'none', background: 'none', color: 'var(--accent)', cursor: 'pointer', fontSize: 11, padding: 0, marginTop: 3 }}>
                      {t('pg.panelsA.tpl.editFormula')}
                    </button>
                  )}
                </div>
              )}
            </div>
          ) : (
          <div style={{ marginBottom: 6 }}>
            <ExpressionBuilder
              layout="flat"
              columns={columns}
              functionsCatalog={funcCats(t)}
              value={editing.expression}
              onChange={next => setEditing(e => (e ? { ...e, expression: next } : e))}
              placeholder="SUM(sales) / TOTAL(SUM(sales)) * 100" // i18n-ok
              rows={3}
            />
          </div>
          )}

          {/* Preview grain + default aggregation */}
          <div style={{ display: 'flex', gap: 8, marginBottom: 8, flexWrap: 'wrap' }}>
            <label style={{ display: 'flex', flexDirection: 'column', gap: 2, flex: 1, minWidth: 120 }}>
              <span style={{ fontSize: 10.5, color: 'var(--muted)' }}>{t('pg.panelsA.ms.groupByPreview')}</span>
              <select aria-label={t('pg.panelsA.ms.groupBy')} value={groupBy} onChange={e => setGroupBy(e.target.value)}
                style={{ fontSize: 11, width: '100%' }}>
                <option value="">{t('pg.panelsA.ms.wholeTable')}</option>
                {dimensionCols.map(c => <option key={c.name} value={c.name}>{c.name}</option>)}
              </select>
            </label>
            <label style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 96 }}>
              <span style={{ fontSize: 10.5, color: 'var(--muted)' }}>{t('pg.panelsA.ms.defaultAgg')}</span>
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
                  <div style={{ color: 'var(--muted)', marginBottom: 3 }}>{t('pg.panelsA.ms.preview', { dtype: String(preview.dtype ?? '') })}</div>
                  {(preview.sample ?? []).map((s, i) => (
                    <div key={i} style={{ fontFamily: 'var(--mono)' }}>
                      {s.group !== null && s.group !== undefined ? `${s.group}: ` : ''}{String(s.value)}
                    </div>
                  ))}
                </>
              ) : (<>
                {/* Plain words first; the raw error behind "Show details". */}
                <div>{problemText(t, { ok: false, error: preview.error ?? undefined, problem: preview.problem })}</div>
                {preview.error && preview.problem && preview.problem.code !== 'other' && (<>
                  <button type="button" onClick={() => setShowDetails(d => !d)}
                    style={{ border: 'none', background: 'none', color: 'var(--muted)', cursor: 'pointer', fontSize: 10.5, padding: 0, textDecoration: 'underline' }}>
                    {showDetails ? t('pg.panelsA.res.hideDetails') : t('pg.panelsA.res.showDetails')}
                  </button>
                  {showDetails && <pre dir="ltr" style={{ margin: '3px 0 0', whiteSpace: 'pre-wrap', color: 'var(--muted)' }}>{preview.error}</pre>}
                </>)}
              </>)}
            </div>
          )}

          {error && (
            <div style={{ marginBottom: 8, fontSize: 10.5, color: '#f87171' }}>{error}</div>
          )}

          <div style={{ display: 'flex', gap: 6 }}>
            <button className="btn btn-ghost btn-sm" style={{ fontSize: 11 }} disabled={busy} onClick={runPreview}>
              {t('pg.panelsA.test')}
            </button>
            <button className="btn btn-primary btn-sm" style={{ fontSize: 11, marginInlineStart: 'auto' }} disabled={busy} onClick={save}>
              {t('pg.panelsA.save')}
            </button>
            <button className="btn btn-ghost btn-sm" style={{ fontSize: 11 }}
              onClick={() => { setEditing(null); setPreview(null); setError(null) }}>
              {t('pg.panelsA.ms.cancel')}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
