import { formatTimeAgo, type TranslateFn } from '../../i18n'
import { TYPE_LABEL } from '../connections/typeMaps'
import type { DatasetSummary, LineageGraph } from '../../services/api'

/**
 * What the Datasets list says about each dataset (redesign step 3a), from data
 * the client already has: the list's own `catalog`, and the lineage graph's
 * `health`, source types and dashboards. Nothing here needs a new endpoint.
 */

export type SourceKind = 'upload' | 'import' | 'live' | 'derived'
export type Status = 'fresh' | 'stale' | 'failing'
/** One bar segment per dataset: a bad status wins over the kind. */
export type Bucket = SourceKind | 'stale' | 'failing'

type LineageDataset = LineageGraph['datasets'][number]

/** Connector types the Connections page names once it has loaded its specs;
 *  this list covers the list page, which does not load them. */
const KNOWN: Record<string, string> = {
  postgresql: 'PostgreSQL', postgres: 'PostgreSQL', mysql: 'MySQL', mariadb: 'MariaDB',
  mssql: 'SQL Server', sqlserver: 'SQL Server', sqlite: 'SQLite', oracle: 'Oracle',
  snowflake: 'Snowflake', bigquery: 'BigQuery', redshift: 'Redshift', clickhouse: 'ClickHouse',
  duckdb: 'DuckDB', db2: 'Db2',
}
export const typeName = (type?: string | null) =>
  !type ? '' : TYPE_LABEL[type] ?? KNOWN[type.toLowerCase()] ?? type

export function sourceKind(d: DatasetSummary): SourceKind {
  if (d.mode === 'directquery' || d.catalog?.kind === 'live') return 'live'
  const k = d.catalog?.kind
  if (k === 'connection') return 'import'
  if (k === 'derived' || k === 'aggregate') return 'derived'
  if (k === 'upload') return 'upload'
  return d.data_source_id ? 'import' : 'upload'
}

/** Failing and stale come from the lineage graph's pipeline health; with no
 *  graph, an overdue or due catalog refresh still reads as stale. */
export function statusOf(d: DatasetSummary, lin?: LineageDataset): Status {
  if (sourceKind(d) === 'live') return 'fresh'
  if (lin?.health === 'failing') return 'failing'
  if (lin?.health === 'stale') return 'stale'
  const f = d.catalog?.freshness
  return f === 'overdue' || f === 'due' ? 'stale' : 'fresh'
}

export const bucketOf = (d: DatasetSummary, lin?: LineageDataset): Bucket => {
  const s = statusOf(d, lin)
  return s === 'fresh' ? sourceKind(d) : s
}

/** "Uploaded file", "Import · PostgreSQL", "Live · SQLite", "Built from sales". */
export function sourceWords(d: DatasetSummary, graph: LineageGraph | null, t: TranslateFn): string {
  const kind = sourceKind(d)
  if (kind === 'upload') return t('dsl.srcw.upload')
  if (kind === 'derived') {
    const from = d.catalog?.built_from ?? []
    return from.length ? t('cat.derived', { sources: from.join(', ') }) : t('cat.derivedAnon')
  }
  const type = typeName(graph?.sources.find(s => s.id === d.data_source_id)?.type)
  if (kind === 'live') return type ? t('dsl.srcw.live', { type }) : d.catalog?.source ? t('cat.live', { source: d.catalog.source }) : t('cat.liveAnon')
  return type ? t('dsl.srcw.import', { type }) : d.catalog?.source ? t('cat.connection', { source: d.catalog.source }) : t('cat.connectionAnon')
}

/** How current, in words, with the tone its dot takes. */
export function freshnessWords(d: DatasetSummary, lin: LineageDataset | undefined, t: TranslateFn):
  { text: string; tone: 'ok' | 'warn' | 'bad' | 'live' } {
  const ago = formatTimeAgo(lin?.load.last_refreshed_at ?? d.catalog?.as_of ?? d.last_refreshed_at ?? d.created_at, t)
    ?? t('fresh.never')
  const status = statusOf(d, lin)
  if (status === 'failing') return { text: t('dsl.fresh.failing', { ago }), tone: 'bad' }
  if (lin?.health === 'stale') return { text: t('dsl.fresh.stale', { ago }), tone: 'warn' }
  const c = d.catalog
  if (!c) return { text: '', tone: 'ok' }
  const catAgo = formatTimeAgo(c.as_of ?? undefined, t) ?? t('fresh.never')
  switch (c.freshness) {
    case 'live': return { text: t('fresh.live'), tone: 'live' }
    case 'on_schedule': return { text: t('fresh.onSchedule', { ago: catAgo }), tone: 'ok' }
    case 'due': return { text: t('fresh.due', { ago: catAgo }), tone: 'warn' }
    case 'overdue': return { text: t('fresh.overdue', { ago: catAgo }), tone: 'bad' }
    case 'manual': return { text: t('fresh.manual', { ago: catAgo }), tone: 'ok' }
    default: return { text: t('fresh.fixed', { ago: catAgo }), tone: 'ok' }
  }
}

/** Dashboards built on a dataset, from the lineage graph. */
export const dashboardsOf = (id: number, graph: LineageGraph | null) =>
  graph ? graph.reports.filter(r => r.dataset_ids.includes(id)) : null
