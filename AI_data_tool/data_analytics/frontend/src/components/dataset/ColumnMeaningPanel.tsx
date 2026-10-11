import { useEffect, useMemo, useState } from 'react'
import { ChevronDown, Pencil, Search } from 'lucide-react'
import toast from 'react-hot-toast'
import { columnMetaApi, datasetsApi, discoveryApi, type ColumnMeta, type ColumnProfileCard, type Dataset } from '../../services/api'
import { defaultSummary, nonAdditiveKind } from '../../lib/semanticGuard'
import { localDigits } from '../../lib/arabicFormats'
import { typeTag, useColumnProfile, type Analysis } from '../../pages/datasetDetail/columnProfile'
import '../../pages/datasetDetail/columns.css'
import { useT, type MessageKey } from '../../i18n'
import ColumnLineage from './ColumnLineage'

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
const ROLES: NonNullable<ColumnMeta['role']>[] = ['measure', 'category', 'temporal', 'geography', 'freetext', 'identifier']

/** How a measure rolls up when a chart, an insight or an alert does not say.
 *  "Average" for a salary is what keeps "M has 60% of salary" off the page. */
const SUMMARIES = ['sum', 'avg', 'median', 'min', 'max', 'countd']
/** What a number is, for every engine that reads it. Mirrors NUMBER_KINDS in
 *  services/semantic_guard.py. */
const NUMBER_KIND_OPTIONS: NonNullable<ColumnMeta['number']>[] = ['amount', 'count', 'level', 'duration', 'score', 'share', 'code']
/** Mirrors GEO_LEVELS in services/semantic_guard.py. */
const GEO_LEVEL_OPTIONS: { value: NonNullable<ColumnMeta['geo_level']>; numeric: boolean }[] = [
  { value: 'country', numeric: false }, { value: 'region', numeric: false }, { value: 'city', numeric: false },
  { value: 'postcode', numeric: false }, { value: 'latitude', numeric: true }, { value: 'longitude', numeric: true },
]
const SUMMARY_LABEL: Record<string, string> = Object.fromEntries(SUMMARIES.map(x => [x, x]))

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
function useAs(name: string, dtype: string, meta: ColumnMeta | undefined, t: ReturnType<typeof useT>): { label: string; measure: boolean } {
  const role = meta?.role
  // What the column IS is its stored classification first (the server's
  // reading of its values, the AI's, or the author's); the name only after.
  const classed = meta ? { [name]: meta } : undefined
  if (role === 'measure' || (!role && dtype === 'numeric' && nonAdditiveKind(name, classed) === null)) {
    const agg = meta?.aggregation ?? defaultSummary(name, classed)
    const aggWord = SUMMARY_LABEL[agg] ? t(`cols3.agg.${agg}` as MessageKey) : agg
    return { label: t('cols3.use.measure', { agg: aggWord }), measure: true }
  }
  if (role === 'temporal' || (!role && dtype === 'datetime')) return { label: t('cols3.use.time'), measure: false }
  if (role === 'identifier' || (!role && nonAdditiveKind(name, classed) === 'identifier')) return { label: t('cols3.use.id'), measure: false }
  if (role === 'freetext') return { label: t('cols3.use.text'), measure: false }
  if (role === 'geography') return { label: t('cols3.use.geo'), measure: false }
  return { label: t('cols3.use.dim'), measure: false }
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
  // Each column's profile card, measured once per version of the data and
  // served as this reader may see it (server: services/discovery/profile.py).
  const [profile, setProfile] = useState<Record<string, ColumnProfileCard>>({})
  useEffect(() => {
    let live = true
    discoveryApi?.profile?.(dataset.id)
      ?.then(r => { if (live) setProfile(Object.fromEntries(r.columns.map(c => [c.column, c]))) })
      ?.catch(() => { /* the profile is an extra: the tab works without it */ })
    return () => { live = false }
  }, [dataset.id])
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
        ? t('cm.savedShared', { object: String(r.object), column: String(r.column) })
        : t('cm.savedHere'))
      setEditing(null)
      onSaved?.()
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? t('cm.saveFailed'))
    } finally { setBusy(false) }
  }

  return (
    <section className="dl-cols" aria-label={t('cm.sectionLabel')}>
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
        <button type="button" className="btn btn-sm" disabled={busy}
          title={t('cm.askAgainTip')}
          onClick={async () => {
            setBusy(true)
            try {
              const got = await columnMetaApi.classifyAgain(dataset.id)
              toast.success(got.asked ? t('cm.askedAgain', { n: got.classified, total: got.asked }) : t('cm.aiUnavailable'))
              onSaved?.()
            } catch (e: any) {
              toast.error(e?.response?.data?.detail ?? t('cm.askFailed'))
            } finally { setBusy(false) }
          }}>
          {t('cm.askAgain')}
        </button>
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
                target={targets[c.name]} eligible={!ineligible.has(c.name)} patchMeta={patchMeta} profile={profile[c.name]} />
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

/** A column's profile in a line of plain facts: how much of it is usable,
 *  what is wrong with the rest, and what its values look like. Value-level
 *  facts are simply absent for a reader who may not see every row. */
function ColumnProfileFacts({ card }: { card: ColumnProfileCard }) {
  const t = useT()
  const n = (v: number) => v.toLocaleString()
  const facts: [string, string][] = [
    [t('cm.pf.valid'), `${n(card.valid.count)} (${card.valid.pct}%)`],
    [t('cm.pf.missing'), `${n(card.missing.count)} (${card.missing.pct}%)`],
  ]
  if (card.mistyped.count) {
    facts.push([t(card.mistyped.holds === 'number' ? 'cm.pf.notNumber' : 'cm.pf.numbersInText'), `${n(card.mistyped.count)} (${card.mistyped.pct}%)`])
  }
  facts.push([t('cm.pf.distinct'), n(card.distinct)], [t('cm.pf.once'), `${n(card.unique.count)} (${card.unique.pct}%)`])
  if (card.most_common) facts.push([t('cm.pf.most'), `${card.most_common[0]} (${n(card.most_common[1])})`])
  if (card.least) facts.push([t('cm.pf.least'), `${card.least[0]} (${n(card.least[1])})`])
  if (card.len_max != null) {
    facts.push([t('cm.pf.length'), card.len_min === card.len_max ? t('cm.pf.chars', { n: card.len_max })
      : t('cm.pf.charsRange', { a: card.len_min ?? 0, b: card.len_max })])
  }
  if (card.pattern) facts.push([t('cm.pf.shape'), card.pattern])
  if (card.kind === 'date' && card.delay_hours != null) {
    const days = card.delay_hours / 24
    facts.push([t('cm.pf.newest'), days < 2 ? t('cm.pf.hoursAgo', { n: Math.round(card.delay_hours) })
      : t('cm.pf.daysAgo', { n: Math.round(days).toLocaleString() })])
  }
  return (
    <dl data-testid="column-profile-facts" style={{ display: 'flex', flexWrap: 'wrap', gap: '4px 18px', margin: 0, fontSize: 12 }}>
      {facts.map(([k, v]) => (
        <div key={k} style={{ display: 'inline-flex', gap: 5 }}>
          <dt style={{ color: 'var(--muted)' }}>{k}</dt><dd style={{ margin: 0, fontVariantNumeric: 'tabular-nums' }}><bdi>{v}</bdi></dd>
        </div>
      ))}
    </dl>
  )
}

function ColumnRow(p: {
  dataset: Dataset; name: string; dtype: string; missing: number; analysis: Analysis; meta?: ColumnMeta
  description?: string; values?: Record<string, string>; canEdit: boolean; busy: boolean
  editing: boolean; draft: string; setDraft: (v: string) => void; onStart: () => void; onSave: () => void; onCancel: () => void
  open: boolean; onToggle: () => void; target?: number; eligible: boolean
  patchMeta: (column: string, change: Partial<ColumnMeta>, note: string) => Promise<void>
  profile?: ColumnProfileCard
}) {
  const t = useT()
  const { dist, sum } = useColumnProfile(p.dataset, p.name, p.analysis)
  const use = useAs(p.name, p.dtype, p.meta, t)
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
          <span className="dl-ov__tag">{typeTag(t, p.dtype)}</span>
        </td>
        <td className="dl-cols__means">
          {p.editing ? (
            <div className="dl-cols__edit">
              <input value={p.draft} autoFocus disabled={p.busy} placeholder={t('cm.whatFor')}
                onChange={e => p.setDraft(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') p.onSave(); if (e.key === 'Escape') p.onCancel() }} />
              <button type="button" className="btn btn-primary btn-sm" onClick={p.onSave} disabled={p.busy}>
                {p.busy ? t('cm.saving') : t('cm.save')}
              </button>
              <button type="button" className="btn btn-sm" onClick={p.onCancel} disabled={p.busy}>{t('cm.cancel')}</button>
            </div>
          ) : p.canEdit ? (
            <button type="button" className={`dl-cols__desc${p.description ? '' : ' dl-cols__desc--empty'}`}
              aria-label={t('cm.describe', { c: p.name })} onClick={p.onStart} dir="auto">
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
      {p.open && p.profile && (
        <tr className="dl-cols__settings">
          <td colSpan={6}><ColumnProfileFacts card={p.profile} /></td>
        </tr>
      )}
      {p.open && p.canEdit && (
        <tr className="dl-cols__settings">
          <td colSpan={6}>
            <div>
              <label>
                {t('cm.treatAs')}
                <select disabled={p.busy} value={p.meta?.role ?? ''} aria-label={t('cm.roleFor', { c: c.name })}
                  onChange={e => void p.patchMeta(c.name, { role: (e.target.value || undefined) as ColumnMeta['role'] },
                    e.target.value ? t(`meaning.now.${e.target.value}` as MessageKey, { col: c.name }) : t('meaning.now.detected', { col: c.name }))}>
                  <option value="">{t('cm.detected')}</option>
                  {ROLES.map(r => <option key={r} value={r} title={t(`cm.roleWhy.${r}` as MessageKey)}>{t(`cm.role.${r}` as MessageKey)}</option>)}
                </select>
              </label>
              {(c.dtype === 'numeric' || p.meta?.role === 'measure') && p.meta?.role !== 'identifier' && p.meta?.role !== 'category' && (
                <label title={t('cm.summariseTip')}>
                  {t('cm.summariseAs')}
                  <select disabled={p.busy} value={p.meta?.aggregation ?? ''} aria-label={t('cm.summaryFor', { c: c.name })}
                    onChange={e => void p.patchMeta(c.name, { aggregation: e.target.value || undefined },
                      e.target.value
                        ? t('meaning.summaryNow', { col: c.name, how: SUMMARY_LABEL[e.target.value] ? t(`cols3.agg.${e.target.value}` as MessageKey) : e.target.value })
                        : t('meaning.summaryAuto', { col: c.name }))}>
                    <option value="">{t('cm.auto', { how: t(`cols3.agg.${SUMMARY_LABEL[defaultSummary(c.name, p.meta ? { [c.name]: { ...p.meta, aggregation: undefined } } : undefined)] ?? 'sum'}` as MessageKey) })}</option>
                    {SUMMARIES.map(x => <option key={x} value={x}>{t(`cm.sum.${x}` as MessageKey)}</option>)}
                  </select>
                </label>
              )}
              {/* The stored classification (docs/suggestions/PLAN.md): decided
                  once by the platform, corrected here, read by every engine --
                  insights, suggestions, the dashboard designers, the data
                  check. A correction is marked the author's and is never
                  overwritten by a later measurement. */}
              {c.dtype === 'numeric' && p.meta?.role !== 'category' && (
                <>
                  <label title={t('cm.numberTip')}>
                    {t('cm.numberIs')}
                    <select disabled={p.busy} value={p.meta?.number ?? ''} aria-label={t('cm.numberFor', { c: c.name })}
                      onChange={e => void p.patchMeta(c.name,
                        { number: (e.target.value || undefined) as ColumnMeta['number'], class_source: 'confirmed' },
                        e.target.value ? t('cm.nowReadAs', { c: c.name, kind: t(`cm.numShort.${e.target.value}` as MessageKey) }) : t('cm.nowDetected', { c: c.name }))}>
                      <option value="">{t('cm.notClassified')}</option>
                      {NUMBER_KIND_OPTIONS.map(k => <option key={k} value={k}>{t(`cm.num.${k}` as MessageKey)}</option>)}
                    </select>
                  </label>
                  <label title={t('cm.directionTip')}>
                    {t('cm.higherIs')}
                    <select disabled={p.busy} value={p.meta?.direction ?? 'neither'} aria-label={t('cm.directionFor', { c: c.name })}
                      onChange={e => void p.patchMeta(c.name,
                        { direction: e.target.value as ColumnMeta['direction'], class_source: 'confirmed' },
                        t('cm.savedFor', { c: c.name }))}>
                      <option value="higher_better">{t('cm.better')}</option>
                      <option value="higher_worse">{t('cm.worse')}</option>
                      <option value="neither">{t('cm.neither')}</option>
                    </select>
                  </label>
                  <label title={t('cm.targetTip')}>
                    {t('cm.target')}
                    <input type="number" step="any" disabled={p.busy} aria-label={t('cm.targetFor', { c: c.name })}
                      defaultValue={p.meta?.target ?? ''} key={`t${p.meta?.target ?? ''}`} style={{ width: 110 }}
                      onBlur={e => {
                        const raw = e.target.value.trim()
                        const next = raw === '' ? null : Number(raw)
                        if (next !== null && !Number.isFinite(next)) return
                        if ((p.meta?.target ?? null) === next) return
                        void p.patchMeta(c.name, { target: next }, next === null ? t('cm.targetRemoved', { c: c.name }) : t('cm.targetSaved', { c: c.name }))
                      }} />
                  </label>
                  {p.meta?.target != null && (
                    <label title={t('cm.targetPeriodTip')}>
                      {t('cm.targetForWhat')}
                      <select disabled={p.busy} value={p.meta?.target_period ?? ''} aria-label={t('cm.targetPeriodFor', { c: c.name })}
                        onChange={e => void p.patchMeta(c.name,
                          { target_period: (e.target.value || null) as ColumnMeta['target_period'] }, t('cm.savedFor', { c: c.name }))}>
                        <option value="">{t('cm.tp.all')}</option>
                        <option value="month">{t('cm.tp.month')}</option>
                        <option value="quarter">{t('cm.tp.quarter')}</option>
                        <option value="year">{t('cm.tp.year')}</option>
                      </select>
                    </label>
                  )}
                </>
              )}
              {c.dtype !== 'numeric' && c.dtype !== 'datetime' && (
                <>
                  <label title={t('cm.orderTip')}>
                    {t('cm.order')}
                    <input type="text" disabled={p.busy} defaultValue={(p.meta?.order ?? []).join(', ')}
                      aria-label={t('cm.orderFor', { c: c.name })} placeholder={t('cm.orderExample')}
                      onBlur={e => {
                        const order = e.target.value.split(',').map(x => x.trim()).filter(Boolean)
                        if (order.join('|') === (p.meta?.order ?? []).join('|')) return
                        void p.patchMeta(c.name, order.length >= 2
                          ? { level: 'ordinal', order, class_source: 'confirmed' }
                          : { level: 'nominal', order: undefined, class_source: 'confirmed' },
                          order.length >= 2 ? t('cm.orderSet', { c: c.name }) : t('cm.orderNone', { c: c.name }))
                      }} />
                  </label>
                  <label title={t('cm.outcomeTip')}>
                    <input type="checkbox" disabled={p.busy} aria-label={t('cm.outcomeFor', { c: c.name })} checked={!!p.meta?.outcome}
                      onChange={e => void p.patchMeta(c.name,
                        { outcome: e.target.checked ? true : undefined, class_source: 'confirmed' },
                        e.target.checked ? t('cm.outcomeOn', { c: c.name }) : t('cm.outcomeOff', { c: c.name }))} />
                    {t('cm.outcome')}
                  </label>
                </>
              )}
              {/* A place. Country names get a map; a region or a city gets its
                  place in a hierarchy (country > region > city) and is never
                  mistaken for an ordinary measure or code. */}
              {c.dtype !== 'datetime' && (
                <label title={t('cm.placeTip')}>
                  {t('cm.place')}
                  <select disabled={p.busy} value={p.meta?.geo_level ?? ''} aria-label={t('cm.placeFor', { c: c.name })}
                    onChange={e => void p.patchMeta(c.name,
                      { geo_level: (e.target.value || undefined) as ColumnMeta['geo_level'], class_source: 'confirmed' },
                      e.target.value ? t('cm.placeSet', { c: c.name, kind: t(`cm.geo.${e.target.value}` as MessageKey) }) : t('cm.placeNone', { c: c.name }))}>
                    <option value="">{t('cm.notPlace')}</option>
                    {GEO_LEVEL_OPTIONS.filter(g => (c.dtype === 'numeric') === g.numeric || g.value === 'postcode')
                      .map(g => <option key={g.value} value={g.value}>{t(`cm.geo.${g.value}` as MessageKey)}</option>)}
                  </select>
                </label>
              )}
              {/* An OUTCOME worth explaining: what lets the "what drives X"
                  analyses run without being told what X is. */}
              <label>
                <input type="checkbox" disabled={p.busy} aria-label={t('cm.explainFor', { c: c.name })} checked={p.target !== undefined}
                  onChange={e => void p.patchMeta(c.name, { target_candidate_priority: e.target.checked ? 10 : undefined },
                    e.target.checked ? t('meaning.outcomeOn', { col: c.name }) : t('meaning.outcomeOff', { col: c.name }))} />
                {t('cm.worthExplaining')}{p.target !== undefined && <span className="dl-cols__muted"> ({p.target})</span>}
              </label>
              {/* Not the same as hiding it, and the tooltip has to say so or
                  the two controls read as duplicates. */}
              <label title={t('cm.suggestTip')}>
                <input type="checkbox" disabled={p.busy} aria-label={t('cm.suggestFor', { c: c.name })} checked={p.eligible}
                  onChange={e => void p.patchMeta(c.name, { eligible_for_suggestion: e.target.checked ? undefined : false },
                    e.target.checked ? t('meaning.suggestOn', { col: c.name }) : t('meaning.suggestOff', { col: c.name }))} />
                {t('cm.maySuggest')}
              </label>
              <label title={t('cols3.hideTitle')}>
                <input type="checkbox" disabled={p.busy} aria-label={t('cm.hideFor', { c: c.name })} checked={!!p.meta?.hidden}
                  onChange={e => void p.patchMeta(c.name, { hidden: e.target.checked ? true : undefined },
                    e.target.checked ? t('cols3.hiddenNow', { col: c.name }) : t('cols3.shownNow', { col: c.name }))} />
                {t('cols3.hide')}
              </label>
              {/* Where it comes from and what uses it (docs/pipeline/PLAN.md, P5). */}
              <ColumnLineage datasetId={p.dataset.id} name={c.name} />
            </div>
          </td>
        </tr>
      )}
    </>
  )
}
