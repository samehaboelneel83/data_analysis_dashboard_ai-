import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Database, LayoutDashboard, Plug, RefreshCw } from 'lucide-react'
import {
  agentApi, dataSourcesApi, datasetsApi, lineageApi, monitoringApi, reportsApi,
  type ActivityRow, type DataSource, type DatasetSummary, type LineageGraph, type RecentReport, type RefreshRunRow,
} from '../services/api'
import type { Report } from '../types/report'
import { useOptionalAuth } from '../contexts/AuthContext'
import LoadError from '../components/ui/LoadError'
import Loader from '../components/ui/Loader'
import { formatTimeAgo, useT } from '../i18n'
import { localDigits } from '../lib/arabicFormats'
import { useAiOffline } from './ask/useAiOffline'
import { datasetSuggestions } from './ask/suggestions'
import { typeName } from './datasetsList/classify'
import { Continue, Hero, Onboarding, Quick, Stats, type HeroChips, type Tile } from './home/parts'
import DashboardsSection from './home/DashboardsSection'
import DatasetsSection, { askable, recentDatasets } from './home/DatasetsSection'
import { ActivityCard, JobsCard } from './home/AdminCards'
import { feedItems, handle, jobsDigest } from './home/feeds'
import { firstPageWidgets } from './home/Thumb'
import './home/home.css'

/**
 * The landing page (redesign 7a): a greeting with the question box, the
 * workspace at a glance, the way back into recent work, and -- for org admins --
 * what changed and what is refreshing.
 *
 * Every number and list here comes from an endpoint that already exists.
 * What the design shows but the backend cannot answer is left out, not
 * stubbed: favourites, owner names, Duplicate, connection health, recently
 * opened datasets (PLAN.md, Backend follow-ups).
 *
 * Failure is per section. Only the two calls everything else hangs off
 * (dashboards, datasets) blank the page, and they still never render as an
 * empty workspace: an outage shown as "nothing yet" invites someone to
 * rebuild work that exists.
 */

interface Slot<T> { data: T | null; error: boolean; loading: boolean }

/** One independent request with its own loading and error state. */
function useSlot<T>(fn: () => Promise<T>, enabled = true): Slot<T> & { reload: () => void } {
  const [s, setS] = useState<Slot<T>>({ data: null, error: false, loading: enabled })
  const fnRef = useRef(fn)
  fnRef.current = fn
  const reload = useCallback(() => {
    if (!enabled) return
    setS(p => ({ ...p, error: false, loading: true }))
    Promise.resolve().then(() => fnRef.current())
      .then(data => setS({ data, error: false, loading: false }))
      .catch(() => setS({ data: null, error: true, loading: false }))
  }, [enabled])
  useEffect(reload, [reload])
  return { ...s, reload }
}

const RECENT = 4

export default function Home() {
  const t = useT()
  const user = useOptionalAuth()?.user ?? null
  const isAdmin = !!user?.role?.is_org_admin
  const { offline } = useAiOffline()
  const askRef = useRef<HTMLInputElement>(null)
  const navigate = useNavigate()

  const [reports, setReports] = useState<Report[]>([])
  const [datasets, setDatasets] = useState<DatasetSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<unknown>(null)
  // Router 7 navigates inside a transition, so the route's Suspense loader
  // never shows while the next page loads; Home shows it itself.
  const [opening, setOpening] = useState(false)
  const open = () => setOpening(true)

  const load = () => {
    setLoadError(null)
    setLoading(true)
    Promise.all([reportsApi.list(), datasetsApi.list()])
      .then(([r, d]) => { setReports(r); setDatasets(d) })
      .catch(e => setLoadError(e ?? new Error('failed')))
      .finally(() => setLoading(false))
  }
  useEffect(load, [])

  const recent = useSlot<RecentReport[]>(() => reportsApi.recent(RECENT))
  const graph = useSlot<LineageGraph>(() => lineageApi.graph())
  const sources = useSlot<DataSource[]>(() => dataSourcesApi.list())
  const convs = useSlot(() => agentApi.listConversations())
  const runs = useSlot<RefreshRunRow[]>(() => monitoringApi.refreshRuns({ limit: 200 }), isAdmin)
  const activity = useSlot<ActivityRow[]>(() => monitoringApi.activity(200), isAdmin)

  const digest = useMemo(() => runs.data ? jobsDigest(runs.data) : null, [runs.data])
  const feed = useMemo(() => activity.data ? feedItems(activity.data, user?.email, reports, datasets) : [],
    [activity.data, user?.email, reports, datasets])

  const chips = useMemo<HeroChips | null>(() => {
    const d = recentDatasets(datasets).filter(askable).find(x => Array.isArray(x.columns) && x.columns.length)
    return d ? { datasetId: d.id, datasetName: d.name, questions: datasetSuggestions(d.columns, t).slice(0, 4) } : null
  }, [datasets, t])

  if (opening) return <Loader label={t('common.loading')} />

  if (loadError) {
    return (
      <div>
        <h1 className="dl-page-title" style={{ marginBottom: 16 }}>{t('nav.home')}</h1>
        <LoadError what={t('home.workspace')} error={loadError} onRetry={load} />
      </div>
    )
  }

  const n = (v: number) => localDigits(v.toLocaleString('en-US'))
  const firstRun = !loading && !datasets.length && !reports.length
  const setUp = loading || (datasets.length > 0 && reports.length > 0)
  const noData = !loading && !datasets.length && !(sources.data?.length)
  const askLocked = noData || offline
  const focusAsk = () => askRef.current?.focus()
  const name = (() => { const h = handle(user?.email); return h === '?' ? '' : h[0].toUpperCase() + h.slice(1) })()

  // ── tiles ──
  const published = reports.filter(r => r.published).length
  const rows = datasets.reduce((s, d) => s + (d.mode === 'directquery' ? 0 : d.row_count ?? 0), 0)
  const types = [...new Set((sources.data ?? []).map(s => typeName(s.type)).filter(Boolean))]
  const lastRefresh = datasets.map(d => d.last_refreshed_at).filter(Boolean).sort().pop() ?? null
  const failing = graph.data?.datasets.filter(d => d.health === 'failing').length ?? 0
  const refreshSub = (): Pick<Tile, 'sub' | 'tone' | 'onRetry'> => {
    if (isAdmin) {
      if (runs.error) return { sub: t('hm.tile.failed'), onRetry: runs.reload }
      if (!digest || runs.loading) return { sub: '…' }
      if (!digest.total) return { sub: t(runs.data?.length ? 'hm.tile.noJobs24' : 'hm.tile.noJobs') }
      return digest.failed
        ? { sub: t('hm.tile.jobsFailed', { n: n(digest.failed), of: n(digest.total) }), tone: 'warn' }
        : { sub: t('hm.tile.jobsOk', { of: n(digest.total) }), tone: 'ok' }
    }
    if (graph.error) return { sub: t('hm.tile.failed'), onRetry: graph.reload }
    if (!graph.data) return { sub: '…' }
    return failing ? { sub: t('hm.tile.failing', { n: n(failing) }), tone: 'err' } : { sub: t('hm.tile.noneFailing'), tone: 'ok' }
  }
  const tiles: Tile[] = [
    { key: 'dashboards', icon: LayoutDashboard, label: t('nav.dashboards'), value: n(reports.length), to: '/reports',
      sub: reports.length ? t('hm.tile.published', { n: n(published) }) : t('hm.tile.none') },
    { key: 'datasets', icon: Database, label: t('nav.datasets'), value: n(datasets.length), to: '/datasets',
      sub: datasets.length ? t('hm.tile.rows', { n: n(rows) }) : t('hm.tile.none') },
    sources.error
      ? { key: 'connections', icon: Plug, label: t('nav.connections'), value: '—', to: '/connections', sub: t('hm.tile.failed'), onRetry: sources.reload }
      : { key: 'connections', icon: Plug, label: t('nav.connections'), value: sources.data ? n(sources.data.length) : '…', to: '/connections',
          sub: sources.data?.length ? types.join(' · ') : t('hm.tile.none') },
    { key: 'refresh', icon: RefreshCw, label: t('hm.tile.lastRefresh'), textual: true, to: isAdmin ? '/monitoring/jobs' : '/datasets',
      value: lastRefresh ? formatTimeAgo(lastRefresh, t) ?? '—' : '—',
      ...(lastRefresh || isAdmin ? refreshSub() : { sub: t('hm.tile.noRefreshes') }) },
  ]

  const byId = new Map(reports.map(r => [r.id, r]))
  const continueItems = (recent.data ?? []).map(r => ({
    id: r.id, name: r.name, when: formatTimeAgo(r.viewed_at, t), widgets: byId.has(r.id) ? firstPageWidgets(byId.get(r.id)) : null,
  }))

  const main = <>
    <DashboardsSection reports={reports} isAdmin={isAdmin} loading={loading} onOpen={open}
      onRename={(id, nm) => setReports(rs => rs.map(r => r.id === id ? { ...r, name: nm } : r))}
      onDelete={id => setReports(rs => rs.filter(r => r.id !== id))} />
    <DatasetsSection datasets={datasets} graph={graph.data} graphFailed={graph.error} onRetryGraph={graph.reload}
      loading={loading} meId={user?.id ?? null} onOpen={open} />
  </>

  return (
    <div className="dl-hm" aria-busy={loading || undefined}>
      <div className="hm-toprow">
        <Hero ref={askRef} name={name} firstRun={firstRun} noData={noData} offline={offline} loading={loading} chips={chips} />
        <Stats tiles={tiles} loading={loading} />
      </div>
      {setUp
        ? <Quick onAsk={askLocked ? undefined : focusAsk} askTo={askLocked ? '/ask' : undefined} />
        : <Onboarding done={[datasets.length > 0, reports.length > 0, (convs.data?.length ?? 0) > 0]}
            onAsk={askLocked ? () => navigate('/ask') : focusAsk} />}
      <Continue items={continueItems.slice(0, RECENT)} loading={loading || recent.loading} error={recent.error}
        onRetry={recent.reload} onOpen={open} />
      {isAdmin ? (
        <div className="hm-bot">
          <div className="hm-colm">{main}</div>
          <div className="hm-cola">
            <ActivityCard items={feed} loading={loading || activity.loading} error={activity.error} onRetry={activity.reload} />
            <JobsCard digest={digest} loading={runs.loading} error={runs.error} onRetry={runs.reload} />
          </div>
        </div>
      ) : <div className="hm-colm">{main}</div>}
    </div>
  )
}
