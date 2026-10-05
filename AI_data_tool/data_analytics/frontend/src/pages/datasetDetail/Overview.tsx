import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Bell, Check, Database, FileText, LayoutGrid, Minus, Plug, Sparkles, X, AlertCircle } from 'lucide-react'
import { useDirection } from '../../contexts/DirectionContext'
import { formatTimeAgo, useT, type MessageKey } from '../../i18n'
import { localDigits } from '../../lib/arabicFormats'
import { certificationOf, isCertified } from '../../lib/cleanDatasets'
import { fmtStr } from '../../components/report/chartUtils'
import { nonAdditiveKind } from '../../lib/semanticGuard'
import { summary as checkSummary } from '../../components/dataset/ChecksPanel'
import {
  adminAuditApi, datasetsApi, lineageApi, monitoringApi,
  type CheckResult, type DataAlert, type DataCheck, type Dataset, type LineageGraph, type PipelineHealth,
} from '../../services/api'
import type { Tab } from './constants'
import { typeName } from '../datasetsList/classify'
import './overview.css'

/**
 * The dataset Overview (redesign step 3b, Phase 1): what it is, whether it can
 * be trusted, its columns at a glance, and what uses it. Every figure comes
 * from data that already exists -- the dataset, its saved profile (analysis),
 * its saved checks, its alerts, the lineage graph, and (admins only) the two
 * audit logs. Nothing is stubbed: a fact with no source is left out.
 */

type Analysis = {
  numeric?: { columns?: Record<string, Record<string, number | null>> }
  categorical?: { columns?: Record<string, { top_values?: { value: string; count: number; pct: number }[]; n_unique?: number; missing_pct?: number }> }
  datetime?: { columns?: Record<string, { min?: string; max?: string; monthly_counts?: { period: string; count: number }[]; missing_pct?: number }> }
  overview?: { missing_pct?: number }
} | null

const TYPE_TAG: Record<string, string> = { numeric: 'NUM', datetime: 'DATE', categorical: 'TXT', boolean: 'BOOL', text: 'TXT' }
const GLANCE_ROWS = 6
const ACTIVITY_ACTIONS = /^(dataset\.upload|dataset\.classify|dataset\.share_created|dataset\.share_revoked|dataset_share\.create|dataset_share\.revoke)$/

export interface OverviewProps {
  ds: Dataset
  analysis: Analysis
  profiling: boolean
  profileError: string | null
  onProfile: () => void
  isAdmin: boolean
  me: { id: number | null; email: string | null }
  pipelineHealth: PipelineHealth | null
  onCertify: () => void
  goTab: (t: Tab) => void
  insights: { findings: { title: string }[]; narrative: string } | null
  insightsBusy: boolean
  onGenerateInsights: () => void
  firstRun: boolean
  onBuild: () => void
  /** Saved alerts and checks, loaded by the page (they also count the tab). */
  alerts: DataAlert[]
  checks: DataCheck[] | null
}

export default function Overview(p: OverviewProps) {
  const { ds, analysis, isAdmin } = p
  const t = useT()
  const [graph, setGraph] = useState<LineageGraph | null>(null)
  const { alerts, checks } = p
  const [results, setResults] = useState<CheckResult[] | null>(null)
  const live = ds.mode === 'directquery'
  const empty = !live && ds.row_count === 0

  useEffect(() => {
    let on = true
    Promise.resolve().then(() => lineageApi?.graph?.()).then(g => { if (on) setGraph(g ?? null) }).catch(() => {})
    return () => { on = false }
  }, [ds.id])
  // The latest check outcome is not stored (P5), so the saved checks are tried
  // against the data as it is now -- the existing "try" call. Checks run before
  // a refreshed file is published: a live dataset has none.
  const anyEnabled = !!checks?.some(c => c.enabled)
  useEffect(() => {
    if (live || !anyEnabled) return
    let on = true
    Promise.resolve().then(() => datasetsApi?.tryChecks?.(ds.id))
      .then(r => { if (on && r) setResults(r.results) }).catch(() => {})
    return () => { on = false }
  }, [ds.id, live, anyEnabled])

  const dashboards = graph ? graph.reports.filter(r => r.dataset_ids.includes(ds.id)) : []
  const derived = graph ? graph.datasets.filter(d => d.derived_from?.includes(ds.id) || d.joins?.includes(ds.id)) : []
  const usedBy = [
    ...dashboards.map(r => ({ key: `r${r.id}`, name: r.name, to: `/reports/${r.id}`, kind: 'dashboard' as const })),
    ...derived.map(d => ({ key: `d${d.id}`, name: d.name, to: `/datasets/${d.id}`, kind: 'dataset' as const })),
    ...alerts.map(a => ({ key: `a${a.id}`, name: a.name, to: null, kind: 'alert' as const })),
  ]

  return (
    <div className="dl-ov">
      {p.firstRun && (
        <section className="dl-ov__firstrun" data-testid="overview-firstrun">
          <div>
            <h2>{t('ov3.first.title')}</h2>
            <p>{t('ov3.first.body', { rows: localDigits(ds.row_count.toLocaleString('en-US')), cols: localDigits(String(ds.col_count)) })}</p>
          </div>
          <button type="button" onClick={() => p.goTab('columns')}>
            <strong>{t('ov3.first.s1')}</strong><span>{t('ov3.first.s1b')}</span></button>
          <button type="button" onClick={() => p.goTab('columns')}>
            <strong>{t('ov3.first.s2')}</strong><span>{t('ov3.first.s2b')}</span></button>
          <button type="button" onClick={p.onBuild}>
            <strong>{t('ov3.first.s3')}</strong><span>{t('ov3.first.s3b')}</span></button>
        </section>
      )}

      <Facts ds={ds} />

      <div className="dl-ov__grid">
        <div className="dl-ov__main">
          <TrustCard {...p} empty={empty} live={live} checks={checks} results={results} />
          <ColumnsGlance ds={ds} analysis={analysis} empty={empty} profiling={p.profiling}
            profileError={p.profileError} onProfile={p.onProfile} goTab={p.goTab}
            failingColumns={new Set((results ?? []).filter(r => !r.passed && r.column).map(r => r.column!))} />
        </div>
        <aside className="dl-ov__side">
          <section className="dl-ov__card" data-testid="overview-used-by">
            <header className="dl-ov__card-head">
              <h3>{t('ov3.usedBy')}</h3><span className="dl-ov__muted">{localDigits(String(usedBy.length))}</span>
            </header>
            {usedBy.length === 0
              ? <p className="dl-ov__muted">{t('ov3.usedBy.none')}</p>
              : (
                <ul className="dl-ov__list">
                  {usedBy.slice(0, 8).map(u => (
                    <li key={u.key}>
                      {u.kind === 'dashboard' ? <LayoutGrid size={14} aria-hidden className="dl-ov__accent" />
                        : u.kind === 'dataset' ? <Database size={14} aria-hidden className="dl-ov__accent" />
                        : <Bell size={14} aria-hidden className="dl-ov__warn" />}
                      {u.to ? <Link to={u.to} dir="auto">{u.name}</Link> : <button type="button" className="dl-ov__linkish" onClick={() => p.goTab('rules')} dir="auto">{u.name}</button>}
                      <span className="dl-ov__muted dl-ov__end">{t(`ov3.kind.${u.kind}` as MessageKey)}</span>
                    </li>
                  ))}
                </ul>
              )}
          </section>

          <section className="dl-ov__card" data-testid="overview-lineage">
            <h3>{t('ov3.lineage')}</h3>
            <div className="dl-ov__flow">
              <span className="dl-ov__node">
                {live ? <Plug size={14} aria-hidden /> : ds.data_source_id ? <Database size={14} aria-hidden /> : <FileText size={14} aria-hidden />}
                {sourceNode(ds, graph, t)}
              </span>
              <span className="dl-ov__node dl-ov__node--self" dir="auto"><Database size={14} aria-hidden /> {ds.name}</span>
              <span className="dl-ov__node"><LayoutGrid size={14} aria-hidden />
                {graph ? (dashboards.length ? t('ov3.lineage.boards', { n: localDigits(String(dashboards.length)) }) : t('ov3.lineage.noBoards')) : '…'}</span>
            </div>
            <Link to="/lineage" className="dl-ov__link">{t('ov3.lineage.open')}</Link>
          </section>

          {!empty && (
            <section className="dl-ov__card" data-testid="overview-insights">
              <h3>{t('ov3.insights')}</h3>
              <p className="dl-ov__body">
                {p.insights
                  ? (p.insights.findings.length
                      ? t('ov3.insights.found', { n: localDigits(String(p.insights.findings.length)),
                          titles: p.insights.findings.slice(0, 2).map(f => f.title).join('; ') })
                      : t('ov3.insights.none'))
                  : t('ov3.insights.idle')}
              </p>
              <div className="dl-ov__row">
                <button type="button" className="btn btn-sm" disabled={p.insightsBusy} onClick={p.onGenerateInsights}>
                  <Sparkles size={13} aria-hidden /> {p.insightsBusy ? t('ov.scanning') : t('ov.genInsights')}
                </button>
                <button type="button" className="dl-ov__linkish" onClick={() => p.goTab('analysis')}>{t('ov3.insights.open')}</button>
              </div>
            </section>
          )}

          {isAdmin && <Activity ds={ds} me={p.me} />}
        </aside>
      </div>
    </div>
  )
}

function sourceNode(ds: Dataset, graph: LineageGraph | null, t: ReturnType<typeof useT>): string {
  if (!ds.data_source_id) {
    const from = (ds as { catalog?: { built_from?: string[] } }).catalog?.built_from
    return from?.length ? t('cat.derived', { sources: from.join(', ') }) : t('dsl.srcw.upload')
  }
  const src = graph?.sources.find(s => s.id === ds.data_source_id)
  if (!src) return t(ds.mode === 'directquery' ? 'cat.liveAnon' : 'cat.connectionAnon')
  return `${src.name} · ${typeName(src.type)}`
}

function Facts({ ds }: { ds: Dataset }) {
  const t = useT()
  const live = ds.mode === 'directquery'
  const kind = (ds as { catalog?: { kind?: string } }).catalog?.kind
  const when = new Date(ds.created_at)
  const lang = useDirection().language === 'ar' ? 'ar-u-nu-latn' : 'en-GB'
  return (
    <section className="dl-ov__facts" aria-label={t('ov3.facts')}>
      <div><span>{t('dsl.pv.rows')}</span><strong>{live && !ds.row_count ? '—' : localDigits(ds.row_count.toLocaleString('en-US'))}</strong></div>
      <div><span>{t('dsl.pv.columns')}</span><strong className="dl-ov__fact-big">{localDigits(String(ds.col_count))}</strong></div>
      <div><span>{kind === 'upload' || (!ds.data_source_id && !kind) ? t('dsl.pv.uploaded') : t('dsl.pv.created')}</span>
        <strong>{localDigits(when.toLocaleString(lang, { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }))}</strong></div>
      <div><span>{t('datasets.col.size')}</span><strong>{live ? '—' : fmtBytes(ds.file_size)}</strong></div>
    </section>
  )
}

export function fmtBytes(b: number) {
  const s = b < 1024 ? `${b} B` : b < 1024 ** 2 ? `${(b / 1024).toFixed(1)} KB` : `${(b / 1024 ** 2).toFixed(1)} MB`
  return `⁦${s}⁩`
}

type TrustLine = { key: string; state: 'ok' | 'warn' | 'bad' | 'none'; label: string; text: string; action?: { label: string; onClick: () => void } }

function TrustCard(p: OverviewProps & { empty: boolean; live: boolean; checks: DataCheck[] | null; results: CheckResult[] | null }) {
  const t = useT()
  const { ds } = p
  const lines: TrustLine[] = []
  let title = t('ov3.trust.ready')
  let badge: { text: string; tone: 'warn' | 'bad' } | null = null

  if (p.empty) {
    title = t('ov3.trust.notYet')
    badge = { text: t('ov3.trust.noRows'), tone: 'warn' }
    lines.push({ key: 'cols', state: 'ok', label: t('dsl.pv.columns'), text: t('ov3.trust.headerCols', { n: localDigits(String(ds.col_count)) }) })
    lines.push({ key: 'rows', state: 'warn', label: t('dsl.pv.rows'), text: t('ov3.trust.noRowsText') })
    lines.push({ key: 'cert', state: 'none', label: t('ov3.trust.certified'), text: t('ov3.trust.cantCertify') })
  } else {
    // Fresh
    const ago = formatTimeAgo(ds.last_refreshed_at ?? ds.created_at, t) ?? t('fresh.never')
    if (p.live) {
      lines.push({ key: 'fresh', state: 'ok', label: t('ov3.trust.fresh'), text: t('ov3.trust.live') })
    } else if (!ds.data_source_id) {
      lines.push({ key: 'fresh', state: 'ok', label: t('ov3.trust.fresh'), text: t('ov3.trust.uploaded', { ago }) })
    } else if (p.pipelineHealth?.state === 'failing') {
      lines.push({ key: 'fresh', state: 'bad', label: t('ov3.trust.fresh'), text: t('ov3.trust.failing', { ago }) })
      badge = badge ?? { text: t('dsl.st.failing'), tone: 'bad' }
    } else if (p.pipelineHealth?.state === 'stale') {
      lines.push({ key: 'fresh', state: 'warn', label: t('ov3.trust.fresh'), text: t('ov3.trust.stale', { ago }) })
      badge = badge ?? { text: t('dsl.st.stale'), tone: 'warn' }
    } else {
      lines.push({ key: 'fresh', state: 'ok', label: t('ov3.trust.fresh'), text: t('ov3.trust.refreshed', { ago }) })
    }
    // Complete
    const cols = ds.columns ?? []
    const missing = p.analysis?.overview?.missing_pct
      ?? (cols.length ? cols.reduce((n, c) => n + (c.missing_pct ?? 0), 0) / cols.length : 0)
    const cells = (ds.row_count ?? 0) * (ds.col_count ?? 0)
    lines.push({ key: 'complete', state: missing < 5 ? 'ok' : 'warn', label: t('ov3.trust.complete'),
      text: cells ? t('ov3.trust.empty', { pct: localDigits(missing.toFixed(1)), n: localDigits(cells.toLocaleString('en-US')) })
        : t('ov3.trust.emptyPct', { pct: localDigits(missing.toFixed(1)) }) })
    // Checks (none for live)
    if (!p.live && p.checks) {
      const enabled = p.checks.filter(c => c.enabled)
      const res = (p.results ?? []).filter(r => r.kind !== 'schema')
      const failing = res.filter(r => !r.passed)
      if (enabled.length === 0) {
        lines.push({ key: 'checks', state: 'none', label: t('ov3.trust.checks'), text: t('ov3.trust.noChecks'),
          action: { label: t('ov3.trust.addCheck'), onClick: () => p.goTab('rules') } })
      } else if (!p.results) {
        lines.push({ key: 'checks', state: 'none', label: t('ov3.trust.checks'), text: t('ov3.trust.checking') })
      } else if (failing.length === 0) {
        lines.push({ key: 'checks', state: 'ok', label: t('ov3.trust.checks'), text: t('ov3.trust.allPass', { n: localDigits(String(res.length)) }) })
      } else {
        const first = failing[0]
        const check = p.checks.find(c => c.id === first.id)
        const what = check ? checkSummary(check, t) : (first.detail ?? first.column ?? '')
        lines.push({ key: 'checks', state: failing.some(f => f.severity === 'block') ? 'bad' : 'warn', label: t('ov3.trust.checks'),
          text: t('ov3.trust.someFail', { pass: localDigits(String(res.length - failing.length)), n: localDigits(String(res.length)),
            what, rows: localDigits(String(first.failing ?? 0)) }),
          action: { label: t('ov3.trust.viewChecks'), onClick: () => p.goTab('rules') } })
        badge = { text: t('ov3.trust.failBadge', { n: localDigits(String(failing.length)) }), tone: 'warn' }
      }
    }
    // Certified
    const cert = certificationOf(ds)
    lines.push(isCertified(ds)
      ? { key: 'cert', state: 'ok', label: t('ov3.trust.certified'), text: cert?.by_email ? t('ov3.trust.certBy', { who: cert.by_email }) : t('dsl.pv.certified') }
      : { key: 'cert', state: 'none', label: t('ov3.trust.certified'), text: t('ov3.trust.notCertified'),
          action: p.isAdmin ? { label: t('dsf.certify'), onClick: p.onCertify } : undefined })
  }

  return (
    <section className="dl-ov__card dl-ov__trust" data-testid="overview-trust">
      <header className="dl-ov__card-head dl-ov__card-head--start">
        <h2>{title}</h2>
        {badge && <span className={`dl-ov__badge dl-ov__badge--${badge.tone}`}>{badge.text}</span>}
      </header>
      <ul>
        {lines.map(l => (
          <li key={l.key} data-testid={`trust-${l.key}`}>
            <span className={`dl-ov__state dl-ov__state--${l.state}`} aria-hidden>
              {l.state === 'ok' ? <Check size={12} /> : l.state === 'none' ? <Minus size={12} /> : l.state === 'bad' ? <X size={12} /> : '!'}
            </span>
            <strong>{l.label}</strong>
            <span className="dl-ov__trust-text">{l.text}</span>
            {l.action && <button type="button" className="dl-ov__linkish" onClick={l.action.onClick}>{l.action.label}</button>}
          </li>
        ))}
      </ul>
    </section>
  )
}

function ColumnsGlance({ ds, analysis, empty, profiling, profileError, onProfile, goTab, failingColumns }: {
  ds: Dataset; analysis: Analysis; empty: boolean; profiling: boolean; profileError: string | null
  onProfile: () => void; goTab: (t: Tab) => void; failingColumns: Set<string>
}) {
  const t = useT()
  const cols = ds.columns ?? []
  const head = (
    <header className="dl-ov__card-head">
      <h3>{t('ov3.glance')}</h3>
      <button type="button" className="dl-ov__linkish" onClick={() => goTab('columns')}>
        {t('ov3.glance.all', { n: localDigits(String(cols.length)) })}</button>
    </header>
  )
  let body: React.ReactNode
  if (empty) {
    body = (
      <div className="dl-ov__center">
        <p className="dl-ov__strong">{t('ov3.glance.noRows')}</p>
        <p className="dl-ov__muted">{t('ov3.glance.noRowsBody')}</p>
        <div className="dl-ov__tags">{cols.map(c => <code key={c.name} dir="ltr">{c.name}</code>)}</div>
      </div>
    )
  } else if (profiling) {
    body = (
      <div className="dl-ov__skeleton" aria-busy="true">
        {Array.from({ length: 6 }, (_, i) => <div key={i}><span /><span /><span /><span /></div>)}
        <p className="dl-ov__muted">{t('ov3.glance.profiling', { n: localDigits(String(cols.length)) })}</p>
      </div>
    )
  } else if (profileError) {
    body = (
      <div className="dl-ov__error" role="alert">
        <AlertCircle size={18} aria-hidden />
        <div>
          <p className="dl-ov__strong">{t('ov3.glance.errTitle')}</p>
          <p>{t('ov3.glance.errBody', { why: profileError })}</p>
          <div className="dl-ov__row">
            <button type="button" className="btn btn-primary btn-sm" onClick={onProfile}>{t('ov3.glance.retry')}</button>
            <button type="button" className="btn btn-sm" onClick={() => goTab('data')}>{t('ov3.glance.openData')}</button>
          </div>
        </div>
      </div>
    )
  } else if (!analysis) {
    // A normal visit does not run a full scan (only a fresh import does);
    // the reader starts it here.
    body = (
      <div className="dl-ov__center">
        <p className="dl-ov__muted">{t('ov3.glance.noProfile')}</p>
        <button type="button" className="btn btn-sm" onClick={onProfile}>{t('ov3.glance.profile')}</button>
      </div>
    )
  } else {
    body = (
      <table className="dl-ov__glance">
        <thead>
          <tr><th>{t('ov3.glance.column')}</th><th>{t('ov3.glance.dist')}</th>
            <th className="dl-ov__num">{t('ov3.glance.empty')}</th><th>{t('ov3.glance.summary')}</th></tr>
        </thead>
        <tbody>
          {cols.slice(0, GLANCE_ROWS).map(c => (
            <GlanceRow key={c.name} ds={ds} name={c.name} dtype={c.dtype} missing={c.missing_pct ?? 0}
              analysis={analysis} flagged={failingColumns.has(c.name)} />
          ))}
        </tbody>
      </table>
    )
  }
  return <section className="dl-ov__card dl-ov__card--flush" data-testid="overview-glance">{head}{body}</section>
}

function GlanceRow({ ds, name, dtype, missing, analysis, flagged }: {
  ds: Dataset; name: string; dtype: string; missing: number; analysis: NonNullable<Analysis>; flagged: boolean
}) {
  const t = useT()
  const fmt = ds.column_formats?.[name]
  const num = analysis.numeric?.columns?.[name]
  const cat = analysis.categorical?.columns?.[name]
  const dt = analysis.datetime?.columns?.[name]
  // A year or an id is a label, not a quantity: "2024", never "2,024".
  const plain = !fmt && (nonAdditiveKind(name) === 'year' || nonAdditiveKind(name) === 'identifier')
  const f = (v: number | null | undefined) => (v == null ? '—' : plain ? localDigits(String(Math.round(v))) : fmtStr(v, fmt))
  let dist: React.ReactNode = null
  let sum = ''
  if (num) {
    dist = <RangeBar s={num} />
    sum = t('ov3.glance.numSum', { min: f(num.min), max: f(num.max), median: f(num.median) })
  } else if (dt) {
    const months = (dt.monthly_counts ?? []).slice(-21)
    const max = Math.max(1, ...months.map(m => m.count))
    dist = <span className="dl-ov__months">{months.map(m => <i key={m.period} title={`${m.period}: ${m.count}`} style={{ blockSize: `${Math.max(12, (m.count / max) * 100)}%` }} />)}</span>
    const d = (s?: string) => (s ? new Date(s).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : '—')
    sum = `${localDigits(d(dt.min))} – ${localDigits(d(dt.max))}`
  } else if (cat) {
    const top = (cat.top_values ?? []).slice(0, 3)
    dist = (
      <span className="dl-ov__tops">
        {top.map(v => (
          <span key={v.value}><em dir="auto">{v.value}</em><b style={{ inlineSize: `${Math.max(4, v.pct * 0.4)}px` }} /><small>{localDigits(String(Math.round(v.pct)))}%</small></span>
        ))}
      </span>
    )
    sum = t('ov3.glance.values', { n: localDigits(String(cat.n_unique ?? top.length)) })
  }
  return (
    <tr data-flagged={flagged || undefined}>
      <td><span className="dl-ov__colname" dir="auto">{name}</span><span className="dl-ov__tag">{TYPE_TAG[dtype] ?? dtype.slice(0, 4).toUpperCase()}</span></td>
      <td>{dist}</td>
      <td className="dl-ov__num">{localDigits(`${Math.round(missing)}%`)}</td>
      <td className="dl-ov__sum">{sum}</td>
    </tr>
  )
}

/** p5–p95 line, p25–p75 box, median tick, on the column's min–max scale. */
function RangeBar({ s }: { s: Record<string, number | null> }) {
  const lo = s.min ?? 0, hi = s.max ?? 0
  const span = hi - lo || 1
  const x = (v: number | null | undefined) => `${(((v ?? lo) - lo) / span) * 100}%`
  return (
    <svg className="dl-ov__range" viewBox="0 0 120 14" preserveAspectRatio="none" aria-hidden>
      <line x1="0" x2="120" y1="7" y2="7" className="dl-ov__range-axis" />
      <line x1={x(s.p5)} x2={x(s.p95)} y1="7" y2="7" className="dl-ov__range-whisker" />
      <rect x={x(s.p25)} y="3" width={`${Math.max(1, (((s.p75 ?? lo) - (s.p25 ?? lo)) / span) * 100)}%`} height="8" rx="1.5" className="dl-ov__range-box" />
      <line x1={x(s.median)} x2={x(s.median)} y1="1" y2="13" className="dl-ov__range-median" />
    </svg>
  )
}

/** Recent activity, admins only: one call to each audit log, filtered here to
 *  THIS dataset (the admin log's `q` matches substrings, so `dataset:1` would
 *  also match `dataset:12` -- the target is checked exactly). */
function Activity({ ds, me }: { ds: Dataset; me: { id: number | null; email: string | null } }) {
  const t = useT()
  const [rows, setRows] = useState<{ key: string; who: string | null; action: string; detail: string | null; at: string }[] | null>(null)
  useEffect(() => {
    let on = true
    const target = `dataset:${ds.id}`
    Promise.all([
      Promise.resolve().then(() => monitoringApi?.activity?.(200)).catch(() => []),
      Promise.resolve().then(() => adminAuditApi?.list?.({ limit: 200, q: target })).catch(() => []),
    ]).then(([general, admin]) => {
      if (!on) return
      const a = (general ?? []).filter(r => r.entity === 'dataset' && r.entity_id === ds.id)
        .map(r => ({ key: `g${r.id}`, who: r.user_email, action: r.action, detail: r.detail, at: r.created_at }))
      const b = (admin ?? []).filter(r => r.target === target)
        .map(r => ({ key: `a${r.id}`, who: r.actor_email, action: r.action, detail: r.detail, at: r.created_at }))
      setRows([...a, ...b].filter(r => ACTIVITY_ACTIONS.test(r.action))
        .sort((x, y) => Date.parse(y.at) - Date.parse(x.at)).slice(0, 5))
    })
    return () => { on = false }
  }, [ds.id])
  const words = useMemo(() => (r: { who: string | null; action: string; detail: string | null }) => {
    const you = r.who != null && r.who === me.email
    const who = you ? t('ov3.act.you') : (r.who ?? t('ov3.act.someone'))
    const verb = /upload/.test(r.action) ? 'upload' : /classify/.test(r.action) ? 'label'
      : /revoke/.test(r.action) ? 'unshare' : 'share'
    return t(`ov3.act.${verb}` as MessageKey, { who, detail: r.detail ?? '' })
  }, [me.email, t])
  return (
    <section className="dl-ov__card" data-testid="overview-activity">
      <header className="dl-ov__card-head">
        <h3>{t('ov3.act.title')}</h3><span className="dl-ov__muted dl-ov__small">{t('ov3.act.note')}</span>
      </header>
      {rows == null ? <p className="dl-ov__muted">…</p>
        : rows.length === 0 ? <p className="dl-ov__muted">{t('ov3.act.none')}</p>
        : (
          <ul className="dl-ov__list dl-ov__list--dots">
            {rows.map(r => (
              <li key={r.key}><span dir="auto">{words(r)}</span>
                <span className="dl-ov__muted dl-ov__end dl-ov__small">{formatTimeAgo(r.at, t)}</span></li>
            ))}
          </ul>
        )}
      <Link to="/admin/audit" className="dl-ov__link">{t('ov3.act.view')}</Link>
    </section>
  )
}
