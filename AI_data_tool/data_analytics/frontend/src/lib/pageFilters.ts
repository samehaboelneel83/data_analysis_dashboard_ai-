import { useCallback, useEffect, useMemo, useState } from 'react'

/**
 * Page filters: the reader's own filters for a whole dashboard page, set from
 * the filter bar above the page ("customer_id from 1 to 20", "order_status is
 * delivered or shipped", "purchased in Jan 2018").
 *
 * They are the reader's, not the report's: kept per viewer, per page, in this
 * browser (a convenience -- storage can be absent or throw, and then they last
 * this visit). The author's permanent filters stay where they were
 * (report.common_filters, widget filters); these ride on top of them.
 *
 * Each one becomes plain query filters ({column, op, value}) that every chart
 * on the page already understands -- gte/lte for ranges, in for picked values,
 * like for "contains" -- so nothing new is needed on the server.
 */

export type ColumnKind = 'number' | 'date' | 'text'

export type PageFilter =
  | { id: string; column: string; kind: 'range'; from?: number | null; to?: number | null }
  | { id: string; column: string; kind: 'dates'; from?: string | null; to?: string | null }
  | { id: string; column: string; kind: 'values'; values: string[] }
  | { id: string; column: string; kind: 'contains'; text: string }

export interface QueryFilter { column: string; op: string; value: unknown }

/** What kind of control a column gets, from its stored type. */
export function columnKind(dtype?: string | null, semantic?: string | null): ColumnKind {
  const d = (dtype ?? '').toLowerCase()
  const s = (semantic ?? '').toLowerCase()
  if (/date|time/.test(d) || /date|time/.test(s)) return 'date'
  if (/numeric|int|float|double|decimal|number|real/.test(d)) return 'number'
  return 'text'
}

/** The last moment of a picked "to" day, so a whole day is kept, not just midnight. */
function endOfDay(day: string): string {
  return /^\d{4}-\d{2}-\d{2}$/.test(day) ? `${day}T23:59:59` : day
}

/** A filter with nothing set (an empty range, no values) filters nothing. */
export function isActive(f: PageFilter): boolean {
  switch (f.kind) {
    case 'range': return f.from != null || f.to != null
    case 'dates': return !!f.from || !!f.to
    case 'values': return f.values.length > 0
    case 'contains': return f.text.trim().length > 0
  }
}

export function toQueryFilters(filters: PageFilter[]): QueryFilter[] {
  const out: QueryFilter[] = []
  for (const f of filters) {
    if (!isActive(f)) continue
    if (f.kind === 'range') {
      if (f.from != null) out.push({ column: f.column, op: 'gte', value: f.from })
      if (f.to != null) out.push({ column: f.column, op: 'lte', value: f.to })
    } else if (f.kind === 'dates') {
      if (f.from) out.push({ column: f.column, op: 'gte', value: f.from })
      if (f.to) out.push({ column: f.column, op: 'lte', value: endOfDay(f.to) })
    } else if (f.kind === 'values') {
      out.push({ column: f.column, op: 'in', value: f.values })
    } else {
      out.push({ column: f.column, op: 'like', value: f.text.trim() })
    }
  }
  return out
}

const num = (n: number) => n.toLocaleString('en-US', { maximumFractionDigits: 6 })

/** The chip's words: "price: 10 – 20", "order_status: delivered, shipped +1". */
export function describePageFilter(f: PageFilter, t?: (k: string, v?: Record<string, string | number>) => string): string {
  const w = (k: string, fallback: string, v?: Record<string, string | number>) => {
    const got = t?.(k, v)
    return got && got !== k ? got : fallback
  }
  switch (f.kind) {
    case 'range':
      if (f.from != null && f.to != null) return `${f.column}: ${num(f.from)} – ${num(f.to)}`
      if (f.from != null) return `${f.column} ≥ ${num(f.from)}`
      if (f.to != null) return `${f.column} ≤ ${num(f.to)}`
      return f.column
    case 'dates':
      if (f.from && f.to) return `${f.column}: ${f.from} – ${f.to}`
      if (f.from) return `${f.column} ${w('pf.fromDate', 'from')} ${f.from}`
      if (f.to) return `${f.column} ${w('pf.toDate', 'until')} ${f.to}`
      return f.column
    case 'values': {
      const shown = f.values.slice(0, 2).join(', ')
      const more = f.values.length - 2
      return `${f.column}: ${shown}${more > 0 ? ` +${more}` : ''}`
    }
    case 'contains':
      return `${f.column} ${w('pf.containsWord', 'contains')} “${f.text.trim()}”`
  }
}

const KEY = (reportId: number, pageId: number) => `datalytics:page-filters:${reportId}:${pageId}`

function read(reportId: number, pageId: number | null | undefined): PageFilter[] {
  if (pageId == null) return []
  try {
    const v = JSON.parse(localStorage.getItem(KEY(reportId, pageId)) || '[]')
    return Array.isArray(v) ? v.filter(x => x && typeof x.column === 'string' && typeof x.kind === 'string') : []
  } catch { return [] }
}

/** The page's filters for this viewer, remembered across visits. */
export function usePageFilters(reportId: number, pageId: number | null | undefined) {
  const [filters, setFilters] = useState<PageFilter[]>(() => read(reportId, pageId))
  // Another page (or report) has its own set.
  useEffect(() => { setFilters(read(reportId, pageId)) }, [reportId, pageId])
  const save = useCallback((next: PageFilter[]) => {
    setFilters(next)
    if (pageId == null) return
    try { localStorage.setItem(KEY(reportId, pageId), JSON.stringify(next)) } catch { /* this visit only */ }
  }, [reportId, pageId])
  // Stable identity while the content is the same: every chart is memoised
  // on its props, and a fresh array would refetch the whole page.
  const serial = JSON.stringify(filters)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const query = useMemo(() => toQueryFilters(filters), [serial])
  return { filters, setFilters: save, query }
}

export const newFilterId = () => Math.random().toString(36).slice(2, 10)
