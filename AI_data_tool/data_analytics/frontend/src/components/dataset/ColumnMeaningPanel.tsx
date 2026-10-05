import { useMemo, useState } from 'react'
import { ChevronDown, Pencil, Search } from 'lucide-react'
import toast from 'react-hot-toast'
import { columnMetaApi, datasetsApi, type ColumnMeta, type Dataset } from '../../services/api'
import { defaultSummary, nonAdditiveKind } from '../../lib/semanticGuard'
import { localDigits } from '../../lib/arabicFormats'
import { typeTag, useColumnProfile, type Analysis } from '../../pages/datasetDetail/columnProfile'
import '../../pages/datasetDetail/columns.css'
import { useT, type MessageKey } from '../../i18n'

/**
 * What a column IS, for every engine that reads it.
 *
 * `freetext` and `identifier` are the two that change what ANALYSES do, and
 * neither could be set through the API until now: the engine has read both
 * since it shipped while the only endpoint that writes them refused anything
 * outside {measure, category, geography}. A comments field detected as
 * `categorical` was charted as one bar per distinct comment; an id column was
 * summed into a total with no referent.
 */
const ROLES: { value: NonNullable<ColumnMeta['role']>; label: string; why: string }[] = [
  { value: 'measure',    label: 'Measure',    why: 'a number worth summing or averaging' },
  { value: 'category',   label: 'Category',   why: 'something to group or break down by' },
  { value: 'temporal',   label: 'Date/time',  why: 'can carry a trend or a forecast' },
  { value: 'geography',  label: 'Geography',  why: 'can be drawn on a map' },
  { value: 'freetext',   label: 'Free text',  why: 'prose - never a chart axis; topic analysis reads it' },
  { value: 'identifier', label: 'Identifier', why: 'counted, never summed' },
]

/** How a measure rolls up when a chart, an insight or an alert does not say.
 *  "Average" for a salary is what keeps "M has 60% of salary" off the page. */
const SUMMARIES: { value: string; label: string }[] = [
  { value: 'sum', label: 'Sum' },
  { value: 'avg', label: 'Average' },
  { value: 'median', label: 'Median' },
  { value: 'min', label: 'Minimum' },
  { value: 'max', label: 'Maximum' },
  { value: 'countd', label: 'Count distinct' },
]
const SUMMARY_LABEL: Record<string, string> = Object.fromEntries(SUMMARIES.map(x => [x.value, x.label]))

/** A short code that needs a gloss ("d001", "M", "CS") -- not a value already
 *  written in words. Mirrors `is_code_like` in services/insights.py. */
export function isCodeLike(v: string): boolean {
  const t = v.trim()
  if (!t || t.includes(' ')) return false
  if (/\d/.test(t)) return true
  if (t.length === 1) return true
  return t.length <= 4 && t === t.toUpperCase()
}


/**
 * What each column MEANS, and where that sentence lives.
 *
 * Every AI path in this product now reads these: the dashboard designer's prompt
 * carries them, the agent's context renders them, and the insights engine writes
 * its findings in their words. Until this panel there was nowhere in the product
 * to write one for a dataset — they could only be inferred by a sync, or typed
 * on the source review page by an admin who knew it existed.
 *
 * The important behaviour is the one the panel has to EXPLAIN, because it is not
 * what a person expects from an inline edit: a column that came from a connected
 * table is described on the SOURCE catalog, so the sentence is written once and
 * every dataset built from that table reads it. That is deliberate — copying the
 * text onto each dataset is what lets two datasets from one table disagree about
 * what `status` means — but a person who types into a box labelled with this
 * dataset's name deserves to be told their words travelled further than that.
 */
export interface ColumnMeaningPanelProps {
  dataset: Dataset
  /** Whether this viewer may author. The endpoint enforces it; hiding the
   *  controls keeps a reader from meeting a refusal they cannot act on. */
  canEdit: boolean
  /** Reload the dataset so the resolved descriptions come back fresh. */
  onSaved?: () => void
  /** The saved profile, for the Distribution and Summary columns (redesign 3c). */
  analysis?: Analysis
}

type Kind = 'all' | 'text' | 'number' | 'date'
const kindOf = (dtype: string): Exclude<Kind, 'all'> =>
  dtype === 'numeric' ? 'number' : dtype === 'datetime' ? 'date' : 'text'

/** What the column is used as, in the words of the board's pill. */
function useAs(name: string, dtype: string, meta: ColumnMeta | undefined): { label: string; measure: boolean } {
  const role = meta?.role
  if (role === 'measure' || (!role && dtype === 'numeric' && nonAdditiveKind(name) === null)) {
    const agg = meta?.aggregation ?? defaultSummary(name)
    return { label: `Measure · ${(SUMMARY_LABEL[agg] ?? agg).toLowerCase()}`, measure: true }
  }
  if (role === 'temporal' || (!role && dtype === 'datetime')) return { label: 'Time', measure: false }
  if (role === 'identifier' || (!role && nonAdditiveKind(name) === 'identifier')) return { label: 'Identifier', measure: false }
  if (role === 'freetext') return { label: 'Free text', measure: false }
  if (role === 'geography') return { label: 'Geography', measure: false }
  return { label: 'Dimension', measure: false }
}

/**
 * The Columns tab (redesign step 3c): one row per column -- name and type,
 * what it means (the description editor), its distribution, how much is empty,
 * a summary, and what it is used as. The role, summary, outcome, suggestion
 * and hidden settings open under the row from its "Use as" pill. Hidden
 * columns are listed apart, behind "Hidden columns (n)".
 */
export default function ColumnMeaningPanel(
  { dataset, canEdit, onSaved, analysis = null }: ColumnMeaningPanelProps,
) {
  const t = useT()
  const [editing, setEditing] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [query, setQuery] = useState('')
  const [kind, setKind] = useState<Kind>('all')
  const [open, setOpen] = useState<string | null>(null)
  const [showHidden, setShowHidden] = useState(false)

  const described = dataset.column_descriptions ?? {}
  const labels = dataset.value_labels ?? {}
  const targets = dataset.column_targets ?? {}
  const ineligible = new Set(dataset.ineligible_columns ?? [])
  const meta = dataset.column_meta ?? {}
  const cols = dataset.columns ?? []
  const hidden = cols.filter(c => meta[c.name]?.hidden)
  const visible = cols.filter(c => !meta[c.name]?.hidden)
  const counts = useMemo(() => ({
    all: visible.length,
    text: visible.filter(c => kindOf(c.dtype) === 'text').length,
    number: visible.filter(c => kindOf(c.dtype) === 'number').length,
    date: visible.filter(c => kindOf(c.dtype) === 'date').length,
  }), [visible])
  const shown = (showHidden ? hidden : visible)
    .filter(c => kind === 'all' || kindOf(c.dtype) === kind)
    .filter(c => !query.trim() || `${c.name} ${described[c.name] ?? ''}`.toLowerCase().includes(query.trim().toLowerCase()))
  const describedCount = cols.filter(c => described[c.name]).length

  /** Merge one column's change into the WHOLE map and send it back.
   *
   *  `PUT /column-meta` replaces the map wholesale - that is deliberate, and it
   *  is what makes a bulk edit one request - so a panel that sent only its own
   *  column would silently delete every role, format and label set anywhere
   *  else. The map arrives on the dataset payload, so merging is both possible
   *  and required. */
  const patchMeta = async (column: string, change: Partial<ColumnMeta>, note: string) => {
    setBusy(true)
    try {
      const next: Record<string, ColumnMeta> = { ...meta }
      next[column] = { ...(next[column] ?? {}), ...change }
      await columnMetaApi.set(dataset.id, next)
      toast.success(note)
      onSaved?.()
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Could not save')
    } finally { setBusy(false) }
  }

  const start = (name: string) => {
    setEditing(name)
    setDraft(described[name] ?? '')
  }

  const save = async (name: string) => {
    setBusy(true)
    try {
      const r = await datasetsApi.setColumnDescription(dataset.id, name, draft.trim())
      // Said plainly, because it is the surprising half: the sentence just
      // became the answer for every dataset built from that table.
      toast.success(r.shared
        ? `Saved. ${r.object}.${r.column} now reads this way in every dataset built from it.`
        : 'Saved for this dataset.')
      setEditing(null)
      onSaved?.()
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Could not save the description')
    } finally { setBusy(false) }
  }

  return (
    <section className="dl-cols" aria-label="What the columns mean">
      {dataset.grain && (
        <p className="dl-cols__grain">
          <strong>{dataset.business_name || dataset.name}</strong>{' — '}{dataset.grain}
        </p>
      )}
      <div className="dl-cols__toolbar">
        <label className="dl-cols__search">
          <Search size={14} aria-hidden />
          <input type="search" value={query} onChange={e => setQuery(e.target.value)}
            placeholder={t('cols3.find')} aria-label={t('cols3.find')} />
        </label>
        <span className="dl-cols__seg" role="radiogroup" aria-label={t('cols3.kind')}>
          {(['all', 'text', 'number', 'date'] as Kind[]).map(k => (
            <button key={k} type="button" role="radio" aria-checked={kind === k} onClick={() => setKind(k)}>
              {t(`cols3.kind.${k}` as MessageKey)} <span>{localDigits(String(counts[k]))}</span>
            </button>
          ))}
        </span>
        <span className="dl-cols__muted">{t('cols3.described', { n: localDigits(String(describedCount)), total: localDigits(String(cols.length)) })}</span>
        <button type="button" className="btn btn-sm dl-cols__hidden-btn" aria-pressed={showHidden}
          onClick={() => setShowHidden(v => !v)}>
          {showHidden ? t('cols3.showVisible') : t('cols3.hidden', { n: localDigits(String(hidden.length)) })}
        </button>
      </div>

      <div className="dl-cols__card">
        <table className="dl-cols__table">
          <thead>
            <tr>
              <th>{t('ov3.glance.column')}</th><th>{t('cols3.means')}</th><th>{t('ov3.glance.dist')}</th>
              <th className="dl-ov__num">{t('ov3.glance.empty')}</th><th>{t('ov3.glance.summary')}</th><th>{t('cols3.useAs')}</th>
            </tr>
          </thead>
          <tbody>
            {shown.length === 0 && (
              <tr><td colSpan={6} className="dl-cols__none">{showHidden ? t('cols3.noHidden') : t('cols3.noMatch')}</td></tr>
            )}
            {shown.map(c => (
              <ColumnRow key={c.name} dataset={dataset} name={c.name} dtype={c.dtype} missing={c.missing_pct ?? 0}
                analysis={analysis} meta={meta[c.name]} description={described[c.name]} values={labels[c.name]}
                canEdit={canEdit} busy={busy} editing={editing === c.name} draft={draft} setDraft={setDraft}
                onStart={() => start(c.name)} onSave={() => void save(c.name)} onCancel={() => setEditing(null)}
                open={open === c.name} onToggle={() => setOpen(o => (o === c.name ? null : c.name))}
                target={targets[c.name]} eligible={!ineligible.has(c.name)} patchMeta={patchMeta} />
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function ColumnRow(p: {
  dataset: Dataset; name: string; dtype: string; missing: number; analysis: Analysis; meta?: ColumnMeta
  description?: string; values?: Record<string, string>; canEdit: boolean; busy: boolean
  editing: boolean; draft: string; setDraft: (v: string) => void; onStart: () => void; onSave: () => void; onCancel: () => void
  open: boolean; onToggle: () => void; target?: number; eligible: boolean
  patchMeta: (column: string, change: Partial<ColumnMeta>, note: string) => Promise<void>
}) {
  const t = useT()
  const { dist, sum } = useColumnProfile(p.dataset, p.name, p.analysis)
  const use = useAs(p.name, p.dtype, p.meta)
  const c = { name: p.name, dtype: p.dtype }
  // Only glosses that SAY something: "d001 = Marketing", never
  // "Marketing = Marketing" (HR evaluation).
  const useful = Object.entries(p.values ?? {})
    .filter(([raw, label]) => isCodeLike(raw) && String(label).trim().toLowerCase() !== raw.trim().toLowerCase())
  return (
    <>
      <tr data-open={p.open || undefined}>
        <td className="dl-cols__name">
          <span className="dl-ov__colname" dir="auto">{p.name}</span>
          <span className="dl-ov__tag">{typeTag(p.dtype)}</span>
        </td>
        <td className="dl-cols__means">
          {p.editing ? (
            <div className="dl-cols__edit">
              <input value={p.draft} autoFocus disabled={p.busy} placeholder="What is this column for?"
                onChange={e => p.setDraft(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') p.onSave(); if (e.key === 'Escape') p.onCancel() }} />
              <button type="button" className="btn btn-primary btn-sm" onClick={p.onSave} disabled={p.busy}>
                {p.busy ? 'Saving…' : 'Save'}
              </button>
              <button type="button" className="btn btn-sm" onClick={p.onCancel} disabled={p.busy}>Cancel</button>
            </div>
          ) : p.canEdit ? (
            <button type="button" className={`dl-cols__desc${p.description ? '' : ' dl-cols__desc--empty'}`}
              aria-label={`Describe ${p.name}`} onClick={p.onStart} dir="auto">
              {p.description || t('cols3.addDescription')} <Pencil size={11} aria-hidden />
            </button>
          ) : (
            <span className={p.description ? '' : 'dl-cols__muted'} dir="auto">{p.description || 'Not described yet'}</span>
          )}
          {useful.length > 0 && (
            <div className="dl-cols__gloss">{useful.slice(0, 8).map(([raw, label]) => `${raw} = ${label}`).join(', ')}</div>
          )}
        </td>
        <td>{dist}</td>
        <td className="dl-ov__num">{localDigits(`${Math.round(p.missing)}%`)}</td>
        <td className="dl-ov__sum">{sum}</td>
        <td>
          {p.canEdit ? (
            <button type="button" className={`dl-cols__use${use.measure ? ' dl-cols__use--measure' : ''}`}
              aria-expanded={p.open} aria-label={t('cols3.editUse', { col: p.name })} onClick={p.onToggle}>
              {use.label} <ChevronDown size={11} aria-hidden />
            </button>
          ) : (
            <span className={`dl-cols__use${use.measure ? ' dl-cols__use--measure' : ''}`}>{use.label}</span>
          )}
        </td>
      </tr>
      {p.open && p.canEdit && (
        <tr className="dl-cols__settings">
          <td colSpan={6}>
            <div>
              <label>
                Treat as
                <select disabled={p.busy} value={p.meta?.role ?? ''} aria-label={`Role for ${c.name}`}
                  onChange={e => void p.patchMeta(c.name, { role: (e.target.value || undefined) as ColumnMeta['role'] },
                    e.target.value ? t(`meaning.now.${e.target.value}` as MessageKey, { col: c.name }) : t('meaning.now.detected', { col: c.name }))}>
                  <option value="">detected</option>
                  {ROLES.map(r => <option key={r.value} value={r.value} title={r.why}>{r.label}</option>)}
                </select>
              </label>
              {(c.dtype === 'numeric' || p.meta?.role === 'measure') && p.meta?.role !== 'identifier' && p.meta?.role !== 'category' && (
                <label title="How this number is rolled up when a chart, an insight or an alert does not say. Salaries, prices and rates read best as an average.">
                  Summarise as
                  <select disabled={p.busy} value={p.meta?.aggregation ?? ''} aria-label={`Summary for ${c.name}`}
                    onChange={e => void p.patchMeta(c.name, { aggregation: e.target.value || undefined },
                      e.target.value
                        ? t('meaning.summaryNow', { col: c.name, how: (SUMMARY_LABEL[e.target.value] ?? e.target.value).toLowerCase() })
                        : t('meaning.summaryAuto', { col: c.name }))}>
                    <option value="">auto ({(SUMMARY_LABEL[defaultSummary(c.name)] ?? 'Sum').toLowerCase()})</option>
                    {SUMMARIES.map(x => <option key={x.value} value={x.value}>{x.label}</option>)}
                  </select>
                </label>
              )}
              {/* An OUTCOME worth explaining: what lets the "what drives X"
                  analyses run without being told what X is. */}
              <label>
                <input type="checkbox" disabled={p.busy} aria-label={`Explain ${c.name}`} checked={p.target !== undefined}
                  onChange={e => void p.patchMeta(c.name, { target_candidate_priority: e.target.checked ? 10 : undefined },
                    e.target.checked ? t('meaning.outcomeOn', { col: c.name }) : t('meaning.outcomeOff', { col: c.name }))} />
                Worth explaining{p.target !== undefined && <span className="dl-cols__muted"> ({p.target})</span>}
              </label>
              {/* Not the same as hiding it, and the tooltip has to say so or
                  the two controls read as duplicates. */}
              <label title="Still usable by anyone who asks for it. This only stops the platform offering charts of it unprompted.">
                <input type="checkbox" disabled={p.busy} aria-label={`Suggest ${c.name}`} checked={p.eligible}
                  onChange={e => void p.patchMeta(c.name, { eligible_for_suggestion: e.target.checked ? undefined : false },
                    e.target.checked ? t('meaning.suggestOn', { col: c.name }) : t('meaning.suggestOff', { col: c.name }))} />
                May be suggested
              </label>
              <label title={t('cols3.hideTitle')}>
                <input type="checkbox" disabled={p.busy} aria-label={`Hide ${c.name}`} checked={!!p.meta?.hidden}
                  onChange={e => void p.patchMeta(c.name, { hidden: e.target.checked ? true : undefined },
                    e.target.checked ? t('cols3.hiddenNow', { col: c.name }) : t('cols3.shownNow', { col: c.name }))} />
                {t('cols3.hide')}
              </label>
            </div>
          </td>
        </tr>
      )}
    </>
  )
}
