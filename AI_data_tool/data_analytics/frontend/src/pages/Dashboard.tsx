import { useContext, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { datasetsApi, lineageApi, DatasetSummary, type DatasetCatalog, type LineageGraph } from '../services/api'
import {
  AlertCircle, ArrowDownUp, ChevronLeft, ChevronRight, Database, FileText, Link2, Plug, Search,
  ShieldCheck, Sparkles, Trash2, Upload, User, X,
} from 'lucide-react'
import toast from 'react-hot-toast'
import { useConfirm } from '../components/ui/ConfirmDialog'
import SuggestDashboardsDialog from '../components/dataset/SuggestDashboardsDialog'
import ActionMenu from '../components/ActionMenu'
import { useListFilter } from '../components/ui/ListFilter'
import IconLabel from '../components/ui/IconLabel'
import { formatTimeAgo, useT, type MessageKey, type TranslateFn } from '../i18n'
import BulkBar from '../components/ui/BulkBar'
import { useBulkSelection } from '../lib/useBulkSelection'
import { looksLikeTestData } from '../lib/testData'
import { certificationOf, isCertified } from '../lib/cleanDatasets'
import { localDigits } from '../lib/arabicFormats'
import { AuthContext } from '../contexts/AuthContext'
import DatasetPreview from './datasetsList/DatasetPreview'
import {
  bucketOf, dashboardsOf, freshnessWords, sourceKind, sourceWords, statusOf,
  type Bucket, type SourceKind, type Status,
} from './datasetsList/classify'
import './datasetsList/datasetsList.css'

/**
 * The dataset inventory (redesign step 3a, Phase 1).
 *
 * The page's whole job is scanning: find one dataset among dozens, judge its
 * shape and age, act on it. A health strip says how many are fresh, stale or
 * failing and links to the ones that need attention; facets narrow the table;
 * selecting a row previews it beside the table.
 *
 * Everything shown comes from data the client already has: the list itself,
 * its `catalog`, and the lineage graph (health, source types, dashboards).
 * There is no Owner facet and no owner name for someone else's dataset: the
 * list does not return owners yet (P1).
 *
 * Deliberately absent: the demo seeder (a setup chore, not data management --
 * the first-run state links admins to Settings instead of seeding here) and
 * the personal pinned-tile dashboard (this is an inventory of your data, not a
 * second dashboard). Dashboard.test.tsx pins both absences.
 */

/**
 * A file size, kept in reading order in RTL too.
 *
 * "25.0 KB" is a number followed by a Latin unit. Dropped into an RTL
 * paragraph, the bidi algorithm reorders that run and it renders as "KB 25.0"
 * -- which is what the Arabic Datasets table was showing. U+2066 LEFT-TO-RIGHT
 * ISOLATE (…U+2069 POP) wraps the pair as one neutral-directional chunk, so it
 * stays "25.0 KB" while the CELL still aligns to the right of an RTL table.
 * Same treatment every mixed number+unit string on this page needs.
 */
const ltr = (s: string) => `⁦${s}⁩`

function fmtBytes(b: number) {
  if (b < 1024) return ltr(`${b} B`)
  if (b < 1024 ** 2) return ltr(`${(b / 1024).toFixed(1)} KB`)
  return ltr(`${(b / 1024 ** 2).toFixed(1)} MB`)
}

function fmtDate(s: string) {
  return new Date(s).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

/**
 * A DirectQuery dataset keeps its rows in the connection: the platform stores
 * none of them and measures no bytes. Printing "0" and "0 B" states something
 * false about the data, so those two figures read as an em dash instead.
 *
 * Only for DirectQuery. An imported file with no rows genuinely has none, and
 * dashing that would hide a failed upload behind tidy punctuation.
 */
const NOT_APPLICABLE = '—'

/**
 * E06: what a dataset is and how current it is, in words (services/catalog.py
 * decides; this only says it). Names come from the server, which names only
 * what this reader may see.
 */
export function catalogWords(c: DatasetCatalog, t: TranslateFn): { what: string; when: string; tone: 'ok' | 'warn' | 'bad' } {
  const list = (xs?: string[]) => (xs ?? []).join(', ')
  const what =
    c.kind === 'upload' ? t('cat.upload')
    : c.kind === 'connection' ? (c.source ? t('cat.connection', { source: c.source }) : t('cat.connectionAnon'))
    : c.kind === 'live' ? (c.source ? t('cat.live', { source: c.source }) : t('cat.liveAnon'))
    : c.kind === 'aggregate' ? t('cat.aggregate', { sources: list(c.built_from) })
    : c.built_from?.length ? t('cat.derived', { sources: list(c.built_from) }) : t('cat.derivedAnon')
  const ago = formatTimeAgo(c.as_of ?? undefined, t) ?? t('fresh.never')
  const when =
    c.freshness === 'live' ? t('fresh.live')
    : c.freshness === 'on_schedule' ? t('fresh.onSchedule', { ago })
    : c.freshness === 'due' ? t('fresh.due', { ago })
    : c.freshness === 'overdue' ? t('fresh.overdue', { ago })
    : c.freshness === 'manual' ? t('fresh.manual', { ago })
    : t('fresh.fixed', { ago })
  return { what, when, tone: c.freshness === 'overdue' ? 'bad' : c.freshness === 'due' ? 'warn' : 'ok' }
}
const storesItsOwnRows = (d: DatasetSummary) => d.mode !== 'directquery'
/** When a live dataset's rows were last counted (4.5), or null. */
export const liveCountedAt = (d: DatasetSummary): string | null => {
  const v = (d.column_meta as unknown as Record<string, unknown> | undefined)?.['__live_count_at__']
  return typeof v === 'string' ? v : null
}

/**
 * Rows per page.
 *
 * CLIENT-SIDE, and it has to be: `GET /datasets` accepts no page, page_size,
 * limit or offset, and answers with a bare array carrying no total (see
 * `routers/datasets.py::list_datasets`). It also filters by readability in
 * Python AFTER the query, so a SQL LIMIT would page the wrong set. Until the
 * endpoint grows those parameters and a count, the browser already holds every
 * row and slices what it shows.
 */
const PAGE_SIZES = [8, 25, 50] as const
const DEFAULT_PAGE_SIZE = PAGE_SIZES[0]
// Per-viewer, per-browser: a convenience, not a setting anyone else sees.
const PAGE_SIZE_KEY = 'datalytics:datasets-page-size'
function storedPageSize(): number {
  try {
    const n = Number(localStorage.getItem(PAGE_SIZE_KEY))
    return (PAGE_SIZES as readonly number[]).includes(n) ? n : DEFAULT_PAGE_SIZE
  } catch { return DEFAULT_PAGE_SIZE }
}

/** The server writes "Imported from X (postgresql)" / "DirectQuery from X
 *  (postgresql)" as a placeholder description. The provenance line under the
 *  name already says it, translated -- so in Arabic the row read the same fact
 *  twice, once in English (HR re-test 2026-10-01). A description a person
 *  wrote is always shown. */
export function isAutoDescription(text: string): boolean {
  return /^(Imported|DirectQuery) from .+ \([\w-]+\)$/.test(text.trim())
}

const SORTS = ['updated', 'name', 'rows'] as const
type Sort = typeof SORTS[number]
const BUCKETS: Bucket[] = ['upload', 'import', 'live', 'derived', 'stale', 'failing']

export default function Dashboard() {
  const t = useT()
  const user = useContext(AuthContext)?.user ?? null
  const meId = user?.id ?? null
  const isAdmin = !!(user?.role?.is_org_admin || user?.is_super_admin)
  const [datasets, setDatasets] = useState<DatasetSummary[]>([])
  const [graph, setGraph] = useState<LineageGraph | null>(null)
  // Which dataset the suggestion panel is open for, if any. Held here rather
  // than in the row so the panel survives the list re-rendering underneath it.
  const [suggestFor, setSuggestFor] = useState<{ id: number; name: string } | null>(null)
  const dsFilter = useListFilter(datasets,
    d => [d.name, d.description], t('search.datasets'))
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<unknown>(null)
  const [page, setPage] = useState(1)
  // 8 by default (BUG-031 asked for more; the default stays so the list reads
  // the same for everyone until they choose otherwise).
  const [pageSize, setPageSizeState] = useState(storedPageSize)
  const setPageSize = (n: number) => {
    setPageSizeState(n)
    setPage(1)
    try { localStorage.setItem(PAGE_SIZE_KEY, String(n)) } catch { /* private window */ }
  }
  const [source, setSource] = useState<SourceKind | 'all'>('all')
  const [status, setStatus] = useState<Status | 'all'>('all')
  const [mineOnly, setMineOnly] = useState(false)
  const [certifiedOnly, setCertifiedOnly] = useState(false)
  const [sort, setSort] = useState<Sort>('updated')
  const [selectedId, setSelectedId] = useState<number | null>(null)

  // This is the landing page, and it had no `.catch` at all: an outage left an
  // unhandled rejection and rendered "No datasets yet" -- telling a user with a
  // full workspace that they have nothing, and inviting them to re-import data
  // that already exists.
  const load = () => {
    setLoadError(null)
    setLoading(true)
    datasetsApi.list()
      .then(list => {
        setDatasets(list)
        // 4.5: live datasets with no count (or an hour-old one) are counted
        // in the background; each row fills in as its answer arrives.
        const hour = 3600_000
        for (const d of list) {
          if (d.mode !== 'directquery') continue
          const at = liveCountedAt(d)
          if (at && Date.now() - Date.parse(at) < hour) continue
          datasetsApi.liveCount?.(d.id)?.then(r => {
            if (r.counted_at && r.row_count != null) setDatasets(ds => ds.map(x => x.id === d.id
              ? { ...x, row_count: r.row_count as number,
                  column_meta: { ...(x.column_meta ?? {}), __live_count_at__: r.counted_at } as typeof x.column_meta }
              : x))
          }).catch(() => {})
        }
      })
      .catch(e => setLoadError(e ?? new Error('failed')))
      .finally(() => setLoading(false))
    // Health, source types and dashboards. Optional: without it the list
    // still works, with the catalog's own words and no dashboard counts.
    Promise.resolve().then(() => lineageApi?.graph?.())
      .then(g => setGraph(g ?? null)).catch(() => setGraph(null))
  }
  useEffect(load, [])

  const confirm = useConfirm()

  const handleDelete = async (id: number, name: string) => {
    if (!await confirm({ title: `Delete "${name}"?`, body: 'This cannot be undone.' })) return
    await datasetsApi.delete(id)
    setDatasets(d => d.filter(x => x.id !== id))
    toast.success('Dataset deleted')
  }

  // Several at once: clearing out a batch of test uploads used to be one
  // menu, one dialog, one toast per dataset.
  const bulk = useBulkSelection<DatasetSummary>({
    remove: id => datasetsApi.delete(id),
    onRemoved: ids => setDatasets(d => d.filter(x => !ids.includes(x.id))),
    noun: t('noun.datasets'),
  })
  const testLike = datasets.filter(d => looksLikeTestData(d.name))

  const lineageOf = useMemo(() => {
    const m = new Map<number, LineageGraph['datasets'][number]>()
    for (const d of graph?.datasets ?? []) m.set(d.id, d)
    return m
  }, [graph])
  const facetsOn = source !== 'all' || status !== 'all' || mineOnly || certifiedOnly
  const matchesFacets = (d: DatasetSummary) =>
    (source === 'all' || sourceKind(d) === source)
    && (status === 'all' || statusOf(d, lineageOf.get(d.id)) === status)
    && (!mineOnly || (meId != null && d.created_by === meId))
    && (!certifiedOnly || isCertified(d))
  const byUpdated = (d: DatasetSummary) => Date.parse(d.last_refreshed_at ?? d.updated_at ?? d.created_at) || 0
  const compare = (a: DatasetSummary, b: DatasetSummary) =>
    sort === 'name' ? a.name.localeCompare(b.name)
      : sort === 'rows' ? (b.row_count ?? 0) - (a.row_count ?? 0)
      : byUpdated(b) - byUpdated(a)

  const rows = dsFilter.filtered.filter(matchesFacets).sort(compare)
  const pageCount = Math.max(1, Math.ceil(rows.length / pageSize))
  // Narrowing the search must not strand you on page 5 of a two-page result,
  // looking at an empty table. Clamping here rather than in an effect keeps it
  // a pure function of the current query -- an effect would render the empty
  // page once before correcting it.
  const current = Math.min(page, pageCount)
  const start = (current - 1) * pageSize
  const visible = rows.slice(start, start + pageSize)
  // Deliberately NOT in the URL: this route documents no query parameters and
  // the deep links into it (from Home, from the rail) depend on that.
  useEffect(() => { setPage(1) }, [dsFilter.query, source, status, mineOnly, certifiedOnly, sort])

  const pageNumbers = useMemo(
    () => Array.from({ length: pageCount }, (_, i) => i + 1),
    [pageCount],
  )

  // The preview follows the selection, and falls back to the first visible
  // row so the panel is never empty beside a full table.
  const selected = visible.find(d => d.id === selectedId) ?? visible[0] ?? null
  const noMatch = dsFilter.noMatches || (datasets.length > 0 && rows.length === 0)

  const counts = useMemo(() => {
    const c: Record<Bucket, DatasetSummary[]> = { upload: [], import: [], live: [], derived: [], stale: [], failing: [] }
    for (const d of datasets) c[bucketOf(d, lineageOf.get(d.id))].push(d)
    return c
  }, [datasets, lineageOf])
  const totalRows = datasets.reduce((n, d) => n + (d.row_count ?? 0), 0)
  const totalBytes = datasets.reduce((n, d) => n + (d.file_size ?? 0), 0)
  const num = (n: number) => n.toLocaleString()

  const clearAll = () => {
    dsFilter.setQuery(''); setSource('all'); setStatus('all'); setMineOnly(false); setCertifiedOnly(false)
  }
  const listed = loading || loadError != null || datasets.length > 0

  return (
    <div className="dl-dsl">
      <header className="dl-page-head">
        <div>
          <h1 className="dl-page-head__title">{t('nav.datasets')}</h1>
          <p className="dl-page-head__sub">{t('dsl.subtitle')}</p>
        </div>
        <div className="dl-dsl__head-actions">
          <Link to="/connections" className="btn"><Plug size={15} aria-hidden /> {t('dsl.connect')}</Link>
          <Link to="/upload" className="btn btn-primary"><Upload size={15} aria-hidden /> {t('dsl.upload')}</Link>
        </div>
      </header>

      {/* At-a-glance totals and health, derived from what is already in
          memory -- nothing here can disagree with the table below it. Hidden
          while loading, on failure and when there is nothing: totals of
          nothing would be noise, or a lie. */}
      {!loading && !loadError && datasets.length > 0 && (
        <section aria-label={t('datasets.summary')} className="card dl-dsl__health">
          <div data-testid="stat-datasets" className="dl-dsl__health-count">
            <span data-figure className="dl-dsl__big">{num(datasets.length)}</span>
            <span className="dl-dsl__muted">{t('dsl.health.datasets')}</span>
          </div>
          <div className="dl-dsl__health-mid">
            <div className="dl-dsl__bar" aria-hidden>
              {BUCKETS.filter(b => counts[b].length).map(b => (
                <span key={b} className={`dl-dsl__seg dl-dsl__seg--${b}`} style={{ flexGrow: counts[b].length }} />
              ))}
            </div>
            <ul className="dl-dsl__legend">
              {BUCKETS.filter(b => counts[b].length).map(b => {
                const list = counts[b]
                const bad = b === 'stale' || b === 'failing'
                return (
                  <li key={b} data-testid={`health-${b}`}>
                    <span className={`dl-dsl__dot dl-dsl__dot--${b}`} aria-hidden />
                    {t(`dsl.health.${b}` as MessageKey, { n: num(list.length) })}
                    {bad && list.length === 1 && (
                      <> — <Link to={`/datasets/${list[0].id}`} className="dl-dsl__health-link">{list[0].name}</Link></>
                    )}
                    {bad && list.length > 1 && (
                      <> — <button type="button" className="dl-dsl__health-link" onClick={() => setStatus(b)}>
                        {t('dsl.health.show')}</button></>
                    )}
                  </li>
                )
              })}
            </ul>
          </div>
          <div className="dl-dsl__health-end">
            <div data-testid="stat-rows"><span data-figure className="dl-dsl__strong">{num(totalRows)}</span> {t('dsl.health.rows')}</div>
            <div data-testid="stat-stored" className="dl-dsl__muted">{t('dsl.health.stored', { size: fmtBytes(totalBytes) })}</div>
          </div>
        </section>
      )}

      {listed && (
        <div className="dl-dsl__toolbar">
          {dsFilter.input && (
            <div className="dl-dsl__search">
              <Search size={14} aria-hidden className="dl-dsl__search-icon" />
              {dsFilter.input}
              {dsFilter.query && (
                <button type="button" className="dl-dsl__search-clear" aria-label={t('dsl.nomatch.clear')}
                  onClick={() => dsFilter.setQuery('')}><X size={14} aria-hidden /></button>
              )}
            </div>
          )}
          <label className="dl-dsl__facet">
            {t('dsl.f.source')}:
            <select value={source} onChange={e => setSource(e.target.value as SourceKind | 'all')}>
              <option value="all">{t('dsl.f.all')}</option>
              {(['upload', 'import', 'live', 'derived'] as SourceKind[]).map(k =>
                <option key={k} value={k}>{t(`dsl.src.${k}` as MessageKey)}</option>)}
            </select>
          </label>
          <label className="dl-dsl__facet">
            {t('dsl.f.status')}:
            <select value={status} onChange={e => setStatus(e.target.value as Status | 'all')}>
              <option value="all">{t('dsl.f.all')}</option>
              {(['fresh', 'stale', 'failing'] as Status[]).map(k =>
                <option key={k} value={k}>{t(`dsl.st.${k}` as MessageKey)}</option>)}
            </select>
          </label>
          <button type="button" className="dl-dsl__toggle" aria-pressed={mineOnly} disabled={meId == null}
            onClick={() => setMineOnly(v => !v)}><User size={14} aria-hidden /> {t('dsl.f.mine')}</button>
          <button type="button" className="dl-dsl__toggle" aria-pressed={certifiedOnly}
            onClick={() => setCertifiedOnly(v => !v)}><ShieldCheck size={14} aria-hidden /> {t('dsl.f.certified')}</button>
          <span className="dl-dsl__toolbar-end">
            {testLike.length > 0 && (
              <button type="button" className="dl-select-hint"
                onClick={() => bulk.setMany(testLike.map(d => d.id), true)}>
                <Trash2 size={13} aria-hidden /> {t('bulk.selectTest', { n: testLike.length })}
              </button>
            )}
            {!loading && loadError == null && (
              <span className="dl-toolbar__count">
                {rows.length !== datasets.length
                  ? t('common.countOf', { n: num(rows.length), total: num(datasets.length) })
                  : t('dsl.count', { n: num(datasets.length) })}
              </span>
            )}
            <label className="dl-dsl__facet">
              <ArrowDownUp size={14} aria-hidden />
              <select aria-label={t('dsl.sort.label')} value={sort} onChange={e => setSort(e.target.value as Sort)}>
                {SORTS.map(k => <option key={k} value={k}>{t(`dsl.sort.${k}` as MessageKey)}</option>)}
              </select>
            </label>
          </span>
        </div>
      )}
      <BulkBar count={bulk.selected.size} busy={bulk.busy} noun={t('noun.datasets')}
        onClear={bulk.clear} onDelete={() => void bulk.deleteSelected(datasets)} />

      {!loading && loadError == null && datasets.length === 0 && <FirstRun isAdmin={isAdmin} />}

      {listed && (
        <div className="dl-dsl__body">
          <div className="card dl-table-card dl-dsl__main">
            {loading && <Skeleton />}
            {!loading && loadError != null && <ListError error={loadError} onRetry={load} />}
            {!loading && loadError == null && noMatch && (
              <div className="dl-dsl__nomatch dl-nomatch">
                <Search size={28} aria-hidden className="dl-dsl__muted" />
                <p className="dl-dsl__nomatch-title">
                  {dsFilter.noMatches ? t('dsl.nomatch.title', { q: dsFilter.query }) : t('dsl.nomatch.facets')}
                </p>
                {dsFilter.noMatches && <p className="dl-dsl__muted">{t('dsl.nomatch.body')}</p>}
                <div className="dl-dsl__row-gap">
                  {dsFilter.query && (
                    <button type="button" className="btn btn-sm" onClick={() => dsFilter.setQuery('')}>{t('dsl.nomatch.clear')}</button>
                  )}
                  {(dsFilter.query || facetsOn) && (
                    <button type="button" className="btn btn-sm" onClick={clearAll}>
                      {t('dsl.nomatch.showAll', { n: num(datasets.length) })}</button>
                  )}
                </div>
              </div>
            )}
            {!loading && loadError == null && !noMatch && datasets.length > 0 && (
              <>
                <table className="dl-table dl-dsl__table">
                  <colgroup>
                    <col className="dl-dsl__c-check" /><col /><col className="dl-dsl__c-source" />
                    <col className="dl-dsl__c-num" /><col className="dl-dsl__c-num" /><col className="dl-dsl__c-size" />
                    <col className="dl-dsl__c-fresh" /><col className="dl-dsl__c-boards" /><col className="dl-dsl__c-act" />
                  </colgroup>
                  <thead>
                    <tr>
                      <th className="dl-table__check">
                        <input type="checkbox" aria-label={t('bulk.selectAll')}
                          checked={visible.length > 0 && visible.every(d => bulk.selected.has(d.id))}
                          ref={el => { if (el) el.indeterminate = visible.some(d => bulk.selected.has(d.id)) && !visible.every(d => bulk.selected.has(d.id)) }}
                          onChange={e => bulk.setMany(visible.map(d => d.id), e.target.checked)} />
                      </th>
                      <th>{t('datasets.col.name')}</th>
                      <th>{t('dsl.col.source')}</th>
                      {/* Numbers align end-ward so digits line up in a column; the
                          logical property keeps that correct in RTL, where "end" is
                          the left. */}
                      <th className="dl-table__num">{t('datasets.col.rows')}</th>
                      <th className="dl-table__num">{t('datasets.col.columns')}</th>
                      <th className="dl-table__num">{t('datasets.col.size')}</th>
                      <th>{t('dsl.col.freshness')}</th>
                      <th className="dl-table__num">{t('dsl.col.dashboards')}</th>
                      <th className="dl-table__actions" aria-label="Actions" />
                    </tr>
                  </thead>
                  <tbody>
                    {visible.map(ds => {
                      const lin = lineageOf.get(ds.id)
                      const fresh = freshnessWords(ds, lin, t)
                      const boards = dashboardsOf(ds.id, graph)
                      const kind = sourceKind(ds)
                      return (
                        <tr key={ds.id} data-selected={bulk.selected.has(ds.id) || undefined}
                          data-previewed={selected?.id === ds.id || undefined} className="dl-dsl__row"
                          onClick={e => { if (!(e.target as HTMLElement).closest('a,button,input,select,[role=menu]')) setSelectedId(ds.id) }}>
                          <td className="dl-table__check">
                            <input type="checkbox" aria-label={t('bulk.selectRow', { name: ds.name })}
                              checked={bulk.selected.has(ds.id)} onChange={() => bulk.toggle(ds.id)} />
                          </td>
                          <td>
                            <div className="dl-cell-name">
                              <Link to={`/datasets/${ds.id}`} className="row-name" dir="auto" title={ds.name} onFocus={() => setSelectedId(ds.id)}>{ds.name}</Link>
                              {isCertified(ds) && (
                                <span className="dl-chip dl-chip--certified" style={{ color: 'var(--success, #15803d)' }}
                                  title={t('dsf.certifiedBy', { who: certificationOf(ds)?.by_email ?? '' })}>
                                  ✓ {t('dsf.badge')}
                                </span>
                              )}
                              {ds.shared && (
                                <span className="dl-chip dl-chip--shared"
                                  title="Shared with you by an org admin">
                                  <IconLabel icon={Link2} size={12}>{t('datasets.shared')}</IconLabel>
                                </span>
                              )}
                            </div>
                            <div className="dl-cell-sub" dir="auto">
                              {ds.description && !isAutoDescription(ds.description) ? ds.description : t('dsl.noDescription')}
                            </div>
                          </td>
                          <td data-testid={`source-${ds.id}`} className="dl-dsl__source">
                            {kind === 'upload' ? <FileText size={14} aria-hidden />
                              : kind === 'live' ? <Plug size={14} aria-hidden /> : <Database size={14} aria-hidden />}
                            <span>{sourceWords(ds, graph, t)}</span>
                          </td>
                          <td className="dl-table__num">
                            {storesItsOwnRows(ds) ? ds.row_count.toLocaleString()
                              : liveCountedAt(ds)
                                ? <span title={t('datasets.liveCountAt', { when: new Date(liveCountedAt(ds)!).toLocaleString() })}>
                                    {ds.row_count.toLocaleString()}</span>
                                : NOT_APPLICABLE}
                          </td>
                          <td className="dl-table__num">{ds.col_count.toLocaleString()}</td>
                          <td className="dl-table__num dl-dsl__nowrap">
                            {storesItsOwnRows(ds) ? fmtBytes(ds.file_size) : NOT_APPLICABLE}
                          </td>
                          <td data-testid={`catalog-${ds.id}`}
                            title={`${t('datasets.col.created')}: ${fmtDate(ds.created_at)}`}>
                            {fresh.text
                              ? <span className={`dl-fresh dl-fresh--${fresh.tone} dl-dsl__fresh`}>
                                  <span className={`dl-dsl__dot dl-dsl__dot--${fresh.tone}`} aria-hidden />{fresh.text}</span>
                              : <span className="dl-table__date">{fmtDate(ds.created_at)}</span>}
                          </td>
                          <td className="dl-table__num" data-testid={`dashboards-${ds.id}`}>
                            {boards ? localDigits(String(boards.length)) : NOT_APPLICABLE}
                          </td>
                          <td className="dl-table__actions">
                            {/* One way in. A red trash icon repeated down every row
                                is an alarm the page rings at itself; delete already
                                lived in this menu, and lives there alone now. */}
                            <ActionMenu
                              label={`More actions for dataset ${ds.name}`}
                              items={[
                                { key: 'suggest', label: t('datasets.suggest'), icon: <Sparkles size={16} />, onSelect: () => setSuggestFor({ id: ds.id, name: ds.name }) },
                                { key: 'delete', label: t('datasets.delete'), danger: true, icon: <Trash2 size={16} />, onSelect: () => handleDelete(ds.id, ds.name) },
                              ]}
                            />
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>

                {/* Inside the table card, because it describes the table rather
                    than the page. Previous and Next are DISABLED at the ends
                    rather than removed: a control that vanishes moves everything
                    beside it, and the reader has to work out whether they ran
                    out of pages or lost a button. */}
                <nav className="dl-pager" aria-label={t('pager.aria')}>
                  <span className="dl-pager__info">
                    {t('pager.showing', { from: (start + 1).toLocaleString(),
                      to: Math.min(start + pageSize, rows.length).toLocaleString(),
                      total: rows.length.toLocaleString() })}
                  </span>
                  <label className="dl-pager__info" style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                    {t('pager.perPage')}
                    <select value={pageSize} onChange={e => setPageSize(Number(e.target.value))}
                      style={{ width: 'auto', padding: '2px 6px' }}>
                      {PAGE_SIZES.map(n => <option key={n} value={n}>{n.toLocaleString()}</option>)}
                    </select>
                  </label>
                  <div className="dl-pager__controls">
                    <button type="button" className="dl-pager__btn"
                      onClick={() => setPage(current - 1)} disabled={current === 1}>
                      <ChevronLeft size={16} className="dl-pager__icon" aria-hidden />
                      {t('pager.previous')}
                    </button>
                    {pageNumbers.map(n => (
                      <button key={n} type="button" className="dl-pager__btn"
                        aria-current={n === current ? 'page' : undefined}
                        aria-label={t('pager.page', { n })}
                        onClick={() => setPage(n)}>
                        {n.toLocaleString()}
                      </button>
                    ))}
                    <button type="button" className="dl-pager__btn"
                      onClick={() => setPage(current + 1)} disabled={current === pageCount}>
                      {t('pager.next')}
                      <ChevronRight size={16} className="dl-pager__icon" aria-hidden />
                    </button>
                  </div>
                </nav>
              </>
            )}
          </div>
          {loading
            ? <aside className="dl-dsl__preview dl-dsl__preview--empty" aria-label={t('dsl.pv.aria')}>{t('common.loading')}</aside>
            : <DatasetPreview ds={loadError == null && !noMatch ? selected : null} graph={graph} meId={meId} fmtBytes={fmtBytes} />}
        </div>
      )}

      {suggestFor && (
        <SuggestDashboardsDialog
          datasetId={suggestFor.id} datasetName={suggestFor.name}
          onClose={() => setSuggestFor(null)} />
      )}
    </div>
  )
}

/** First run: nothing to list yet, so the page is the way in. */
function FirstRun({ isAdmin }: { isAdmin: boolean }) {
  const t = useT()
  return (
    <div className="card dl-dsl__firstrun" data-testid="datasets-firstrun">
      <span className="dl-dsl__firstrun-icon" aria-hidden><Upload size={20} /></span>
      <h2 className="dl-dsl__firstrun-title">{t('dsl.first.title')}</h2>
      <p className="dl-dsl__muted dl-dsl__firstrun-body">{t('dsl.first.body')}</p>
      <div className="dl-dsl__row-gap">
        <Link to="/upload" className="btn btn-primary">{t('dsl.first.choose')}</Link>
        <Link to="/connections" className="btn">{t('dsl.connect')}</Link>
      </div>
      <div className="dl-dsl__options">
        <Link to="/upload" className="dl-dsl__option">
          <strong>{t('dsl.first.files')}</strong><span>{t('dsl.first.filesBody')}</span>
        </Link>
        <Link to="/connections" className="dl-dsl__option">
          <strong>{t('dsl.first.db')}</strong><span>{t('dsl.first.dbBody')}</span>
        </Link>
        {/* Sample content is loaded from Settings, which only admins can open;
            nobody else is offered a door they cannot go through. */}
        {isAdmin && (
          <Link to="/admin/settings" className="dl-dsl__option">
            <strong>{t('dsl.first.sample')}</strong><span>{t('dsl.first.sampleBody')}</span>
          </Link>
        )}
      </div>
    </div>
  )
}

function Skeleton() {
  const t = useT()
  return (
    <div className="dl-dsl__skeleton" aria-busy="true" aria-label={t('common.loading')}>
      {Array.from({ length: 9 }, (_, i) => (
        <div key={i} className="dl-dsl__sk-row">
          <span className="dl-dsl__sk dl-dsl__sk--dot" />
          <span className="dl-dsl__sk-name">
            <span className="dl-dsl__sk" style={{ width: `${40 + (i * 13) % 25}%` }} />
            <span className="dl-dsl__sk dl-dsl__sk--sub" />
          </span>
          <span className="dl-dsl__sk dl-dsl__sk--num" />
          <span className="dl-dsl__sk dl-dsl__sk--num" />
          <span className="dl-dsl__sk dl-dsl__sk--wide" />
        </div>
      ))}
    </div>
  )
}

/** "We could not ask" -- an interruption with a retry, never the empty state. */
function ListError({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  const t = useT()
  const raw = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  const detail = typeof raw === 'string' ? raw : null
  return (
    <div role="alert" className="dl-dsl__error">
      <AlertCircle size={18} aria-hidden className="dl-dsl__error-icon" />
      <div>
        <p className="dl-dsl__error-title">{t('dsl.err.title')}</p>
        <p className="dl-dsl__error-body">{detail ?? t('dsl.err.body')}</p>
        <button type="button" className="btn btn-primary btn-sm" onClick={onRetry}>{t('dsl.err.retry')}</button>
      </div>
    </div>
  )
}
