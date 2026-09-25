import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { datasetsApi, reportsApi, type DatasetSummary, type RecentReport } from '../services/api'
import type { Report } from '../types/report'
import {
  ChevronDown, ChevronRight, Database, LayoutDashboard, type LucideIcon,
} from 'lucide-react'
import LoadError from '../components/ui/LoadError'
import { formatTimeAgo, useT } from '../i18n'

/**
 * The landing page: what you were working on, and the way back into it.
 *
 * Card SECTIONS rather than one dense table -- the previous Home was the
 * dataset list, which answered "what data exists" but not "what was I doing".
 * Datasets kept its table and moved to /datasets (still reachable from its own
 * rail entry); nothing was removed.
 *
 * Every section here is built from data the app actually serves. Recents is
 * real per-user view history (`/reports/recent`, added with the 0015
 * `recent_views` table) rather than the report list sorted by `updated_at` --
 * that older ordering answered "what changed", so a dashboard somebody else
 * edited jumped to the top of YOUR recents. Datasets order by `created_at`.
 *
 * Still deliberately absent: favourites and a saved-query section. Neither
 * exists in this backend, and a section that renders permanently empty makes
 * the page look richer while being worth less.
 */

const RECENT_LIMIT = 5

/** A collapsible section with a heading and a row of cards. */
function Section({ title, action, children, testId }: {
  title: string
  action?: React.ReactNode
  children: React.ReactNode
  testId?: string
}) {
  const KEY = `home.section.${title}`
  const [open, setOpen] = useState(() => {
    try { return localStorage.getItem(KEY) !== '0' } catch { return true }
  })
  const toggle = () => {
    setOpen(o => {
      try { localStorage.setItem(KEY, o ? '0' : '1') } catch { /* cosmetic */ }
      return !o
    })
  }

  return (
    <section aria-label={title} data-testid={testId} style={{ marginBottom: 26 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
        <button onClick={toggle} aria-expanded={open}
          style={{ display: 'inline-flex', alignItems: 'center', gap: 6, background: 'none',
            border: 'none', cursor: 'pointer', padding: 0, color: 'var(--text)',
            fontFamily: 'var(--sans)', fontSize: 14, fontWeight: 700 }}>
          <span aria-hidden style={{ display: 'inline-flex', color: 'var(--muted)' }}>
            {open ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
          </span>
          {title}
        </button>
        {action && <div style={{ marginInlineStart: 'auto' }}>{action}</div>}
      </div>
      {open && children}
    </section>
  )
}

const cardGrid: React.CSSProperties = {
  display: 'grid', gap: 12,
  gridTemplateColumns: 'repeat(auto-fill, minmax(230px, 1fr))',
}

/** One entity card: icon, name, a quiet subtitle, optional status chip. */
function EntityCard({ to, icon: Icon, name, subtitle, chip, testId }: {
  to: string
  icon: LucideIcon
  name: string
  subtitle: string | null
  chip?: React.ReactNode
  testId?: string
}) {
  return (
    <Link to={to} data-testid={testId} className="card"
      style={{ display: 'block', padding: 14, textDecoration: 'none', color: 'var(--text)' }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 9 }}>
        <span aria-hidden style={{ display: 'inline-flex', flexShrink: 0, color: 'var(--accent)',
          background: 'var(--accent-soft)', borderRadius: 8, padding: 6 }}>
          <Icon size={15} strokeWidth={1.9} />
        </span>
        {/* The full name on the element: the card cannot grow, so truncation is
            right, but two dashboards differing after the twentieth character
            are otherwise indistinguishable. */}
        <span title={name} style={{ flex: 1, minWidth: 0, fontSize: 13.5, fontWeight: 650,
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {name}
        </span>
        {chip}
      </div>
      {subtitle && (
        <div style={{ fontSize: 11.5, color: 'var(--muted)', marginTop: 8 }}>{subtitle}</div>
      )}
    </Link>
  )
}

function Empty({ text, cta }: { text: string; cta?: React.ReactNode }) {
  return (
    <div className="card" style={{ padding: '26px 20px', textAlign: 'center', color: 'var(--muted)' }}>
      <p style={{ fontSize: 13, margin: 0 }}>{text}</p>
      {cta && <div style={{ marginTop: 12 }}>{cta}</div>}
    </div>
  )
}

export default function Home() {
  const t = useT()
  const [reports, setReports] = useState<Report[]>([])
  const [datasets, setDatasets] = useState<DatasetSummary[]>([])
  const [recent, setRecent] = useState<RecentReport[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<unknown>(null)

  const load = () => {
    setLoadError(null)
    setLoading(true)
    Promise.all([reportsApi.list(), datasetsApi.list(), reportsApi.recent()])
      .then(([r, d, rec]) => { setReports(r); setDatasets(d); setRecent(rec) })
      .catch(e => setLoadError(e ?? new Error('failed')))
      .finally(() => setLoading(false))
  }
  useEffect(load, [])

  // Recents comes from the server as real per-user view history (0015).
  // It was previously the report list sorted by `updated_at`, which answered
  // "what changed" -- so a dashboard somebody else edited jumped to the top of
  // YOUR recents, and one you read daily without editing never appeared.
  const recentDatasets = useMemo(
    () => [...datasets]
      .sort((a, b) => new Date(b.created_at ?? 0).getTime() - new Date(a.created_at ?? 0).getTime())
      .slice(0, RECENT_LIMIT),
    [datasets],
  )
  const mine = useMemo(() => reports.filter(r => r.is_mine).slice(0, RECENT_LIMIT), [reports])

  const draftChip = (r: { created_by?: number | null; published?: boolean }) =>
    r.created_by != null && !r.published ? (
    <span title={t('home.draftTitle')}
      style={{ fontSize: 10.5, fontWeight: 700, color: 'var(--muted)', flexShrink: 0,
        border: '1px solid var(--border)', borderRadius: 99, padding: '1px 7px',
        textTransform: 'uppercase', letterSpacing: '.04em' }}>
      {t('common.draft')}
    </span>
  ) : undefined

  if (loadError) {
    return (
      <div>
        <h1 className="dl-page-title" style={{ marginBottom: 16 }}>{t('nav.home')}</h1>
        <LoadError what={t('home.workspace')} error={loadError} onRetry={load} />
      </div>
    )
  }

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 22, flexWrap: 'wrap' }}>
        <div>
          <h1 className="dl-page-title" style={{ marginBottom: 3 }}>{t('nav.home')}</h1>
          <p style={{ color: 'var(--muted)', fontSize: 13, margin: 0 }}>
            {t('home.subtitle')}
          </p>
        </div>
      </div>

      {loading && <p style={{ color: 'var(--muted)' }}>{t('common.loading')}</p>}

      {!loading && (
        <>
          <Section title={t('home.recents')} testId="home-recents">
            {recent.length === 0 ? (
              <Empty text={t('home.recentsEmpty')} />
            ) : (
              <div style={cardGrid}>
                {recent.map(r => (
                  <EntityCard key={r.id} to={`/reports/${r.id}`} icon={LayoutDashboard}
                    testId={`home-recent-${r.id}`}
                    name={r.name} chip={draftChip(r)}
                    subtitle={formatTimeAgo(r.viewed_at, t)
                      && t('home.opened', { when: formatTimeAgo(r.viewed_at, t)! })} />
                ))}
              </div>
            )}
          </Section>

          <Section title={t('nav.dashboards')} testId="home-dashboards"
            action={<Link to="/reports" style={{ fontSize: 12, color: 'var(--accent)',
              textDecoration: 'none' }}>{t('common.viewAll')}</Link>}>
            {reports.length === 0 ? (
              <Empty text={t('home.dashboardsEmpty')} />
            ) : (
              <div style={cardGrid}>
                {(mine.length > 0 ? mine : reports.slice(0, RECENT_LIMIT)).map(r => (
                  <EntityCard key={r.id} to={`/reports/${r.id}`} icon={LayoutDashboard}
                    name={r.name} chip={draftChip(r)}
                    subtitle={r.my_capability === 'view'
                      ? t('home.viewOnly')
                      : formatTimeAgo(r.updated_at, t)
                        && t('home.modified', { when: formatTimeAgo(r.updated_at, t)! })} />
                ))}
              </div>
            )}
          </Section>

          <Section title={t('nav.datasets')} testId="home-datasets"
            action={<Link to="/datasets" style={{ fontSize: 12, color: 'var(--accent)',
              textDecoration: 'none' }}>{t('common.viewAll')}</Link>}>
            {datasets.length === 0 ? (
              <Empty text={t('home.datasetsEmpty')} />
            ) : (
              <div style={cardGrid}>
                {recentDatasets.map(d => (
                  <EntityCard key={d.id} to={`/datasets/${d.id}`} icon={Database}
                    testId={`home-dataset-${d.id}`}
                    name={d.name}
                    chip={d.mode === 'directquery' ? (
                      <span title={t('home.liveTitle')} style={{ fontSize: 10.5, fontWeight: 700,
                        color: 'var(--accent)', flexShrink: 0, background: 'var(--accent-soft)',
                        borderRadius: 99, padding: '1px 7px', textTransform: 'uppercase' }}>{t('common.live')}</span>
                    ) : undefined}
                    subtitle={d.mode === 'directquery'
                      // A live dataset is queried at its source, so nobody has
                      // counted its rows -- `row_count` is absent, not zero, and
                      // "0 rows" states something false about the data.
                      ? t('home.colsOnly', { cols: (d.col_count ?? 0).toLocaleString() })
                      : t('home.rowsCols', {
                        rows: (d.row_count ?? 0).toLocaleString(),
                        cols: (d.col_count ?? 0).toLocaleString(),
                      })} />
                ))}
              </div>
            )}
          </Section>
        </>
      )}
    </div>
  )
}
