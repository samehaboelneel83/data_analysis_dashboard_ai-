import { useEffect, useMemo, useState } from 'react'
import { reviewApi, type PerfEvaluation } from '../../services/api'
import { missingRequiredRoles } from './WidgetPlaceholder'
import type { Report, Widget } from '../../types/report'

export interface PerfStat { durationMs: number; rowCount: number; ruleErrors?: { message: string }[] }

/** A saved interaction, exactly as `CrossFilterContext` reads it back out of
 *  `config.interaction`. Absent fields mean the defaults, which broadcast and
 *  receive — an author who never opened the pane has nothing wrong. */
interface SavedInteraction {
  broadcasts?: boolean
  receives?: boolean
  syncAllPages?: boolean
  actions?: { targetId: number; mode: 'filter' | 'highlight' }[]
}

interface Finding {
  severity: 'error' | 'warning' | 'info'
  /** What KIND of problem it is, which is not the same question as how bad it
   *  is. The badge used to be keyed on severity alone, so every `error` read
   *  "A11Y" — fine while errors were only ever accessibility ones, and a lie
   *  the moment a broken action became an error too. */
  category?: 'a11y' | 'wiring'
  widgetId?: number
  pageId: number
  message: string
}

/**
 * Static review of the report: accessibility, performance and construction problems
 * an author can fix before a viewer hits them.
 *
 * Deliberately a checklist, not a score. A single number invites gaming and hides
 * which problem to fix first; a ranked list with the widget named is actionable.
 * Severity: `error` will visibly mislead or exclude a viewer; `warning` degrades the
 * experience; `info` is worth knowing.
 */
/** What the cross-dataset check needs: each dataset's columns and the org's
 *  column mappings (relationships). */
export interface MappingContext {
  datasets: Record<number, { name?: string; columns?: { name: string }[] } | undefined>
  relationships: { from_dataset_id: number; from_column: string; to_dataset_id: number; to_column: string }[]
}

export function reviewReport(report: Report, perfStats: Record<number, PerfStat>, mapping?: MappingContext): Finding[] {
  const findings: Finding[] = []
  const DATA_TYPES_EXEMPT = new Set(['text', 'button', 'image', 'shape', 'container', 'slicer', 'web_content', 'custom_visual'])

  for (const page of report.pages) {
    const widgets: Widget[] = page.widgets ?? []

    for (const w of widgets) {
      const cfg = (w.config ?? {}) as Record<string, unknown>

      // Accessibility
      if (!w.title && !cfg.alt_text && !DATA_TYPES_EXEMPT.has(w.widget_type)) {
        findings.push({ severity: 'error', category: 'a11y', widgetId: w.id, pageId: page.id,
          message: `Untitled ${w.widget_type} has no alt text — a screen reader announces nothing useful` })
      }
      // Unfinished: readers get a placeholder. Mirrors the server's check,
      // which is what the publish gate enforces (Phase 7.4).
      if (!DATA_TYPES_EXEMPT.has(w.widget_type) && w.widget_type !== 'text') {
        const missing = missingRequiredRoles(w)
        if (missing.length) {
          findings.push({ severity: 'error', category: 'wiring', widgetId: w.id, pageId: page.id,
            message: `"${w.title || w.widget_type}" is unfinished — readers see a placeholder until ${missing.join(', ')} is set` })
        }
      }
      if (w.widget_type === 'image' && !cfg.alt) {
        findings.push({ severity: 'error', category: 'a11y', widgetId: w.id, pageId: page.id,
          message: 'Image has no alt text' })
      }

      // Construction
      const stat = perfStats[w.id]
      if (stat && stat.rowCount === 0 && !DATA_TYPES_EXEMPT.has(w.widget_type)) {
        findings.push({ severity: 'warning', widgetId: w.id, pageId: page.id,
          message: `"${w.title || w.widget_type}" returned no rows — check its roles and filters` })
      }
      if (stat?.ruleErrors?.length) {
        findings.push({ severity: 'warning', widgetId: w.id, pageId: page.id,
          message: `"${w.title || w.widget_type}" has ${stat.ruleErrors.length} broken display rule(s) — rules fail open, so they silently stop applying` })
      }
      if (w.widget_type === 'container') {
        const children = widgets.filter(x =>
          (x.config as { container_id?: number })?.container_id === w.id)
        if (children.length === 0) {
          findings.push({ severity: 'info', widgetId: w.id, pageId: page.id,
            message: `Container "${w.title || w.id}" is empty` })
        }
      }

      // Performance
      if (stat && stat.durationMs > 2000) {
        findings.push({ severity: 'warning', widgetId: w.id, pageId: page.id,
          message: `"${w.title || w.widget_type}" took ${(stat.durationMs / 1000).toFixed(1)}s to load` })
      }
    }

    if (widgets.length > 14) {
      findings.push({ severity: 'info', pageId: page.id,
        message: `Page "${page.name}" has ${widgets.length} widgets — every one queries on load` })
    }
  }

  // ── Interaction wiring: what the READER gets, not what the author sees
  //
  // Every branch below is one of `getFiltersFor`'s early returns. They have a
  // failure mode the checks above do not: a dead edge throws nothing, logs
  // nothing and looks right in the builder, because the author clicks the one
  // path they wired and it works. It is wrong only for the person who opens the
  // link, and only on the paths the author never tried.
  const pageOfWidget = new Map<number, { pageId: number; pageName: string; w: Widget }>()
  for (const page of report.pages) {
    for (const w of page.widgets ?? []) {
      pageOfWidget.set(w.id, { pageId: page.id, pageName: page.name, w })
    }
  }
  const interactionOf = (w: Widget): SavedInteraction =>
    ((w.config ?? {}) as { interaction?: SavedInteraction }).interaction ?? {}

  const MODE_LABEL: Record<string, string> = {
    linked: 'linked selection', oneway: 'one-way', twoway: 'two-way',
  }

  for (const page of report.pages) {
    const widgets: Widget[] = page.widgets ?? []
    const mode = page.mobile_layout?.interaction_mode ?? 'manual'
    const name = (w: Widget) => w.title || w.widget_type

    for (const w of widgets) {
      const it = interactionOf(w)
      const actions = it.actions ?? []
      if (actions.length === 0) continue

      // An automatic page mode and manual per-pair actions are mutually
      // exclusive — SAS documents it, and `getFiltersFor` agrees: its `acts`
      // branch is guarded by `pageMode === 'manual'`. Under an automatic mode
      // the wiring is not consulted at all, so say so rather than let the
      // author believe both are in force.
      if (mode !== 'manual') {
        findings.push({ severity: 'warning', category: 'wiring', widgetId: w.id, pageId: page.id,
          message: `Page "${page.name}" is in ${MODE_LABEL[mode] ?? mode} mode, which ignores the ${actions.length} per-pair action(s) on "${name(w)}" — automatic modes replace manual actions` })
        continue
      }

      for (const a of actions) {
        const target = pageOfWidget.get(a.targetId)
        if (!target) {
          findings.push({ severity: 'error', category: 'wiring', widgetId: w.id, pageId: page.id,
            message: `"${name(w)}" has an action pointing at a widget that no longer exists (#${a.targetId}) — the target was deleted and the action can never fire` })
          continue
        }
        // Page scoping: a filter survives only when its SOURCE page is the page
        // being drawn, or the source is marked to sync across pages.
        if (target.pageId !== page.id && !it.syncAllPages) {
          findings.push({ severity: 'error', category: 'wiring', widgetId: w.id, pageId: page.id,
            message: `"${name(w)}" has an action on "${name(target.w)}", which is on another page ("${target.pageName}") — filters are scoped to their own page unless the source syncs across pages, so this never arrives` })
          continue
        }
        if (interactionOf(target.w).receives === false) {
          findings.push({ severity: 'warning', category: 'wiring', widgetId: w.id, pageId: page.id,
            message: `"${name(w)}" has an action on "${name(target.w)}", which is set not to receive — the selection is dropped before the action is consulted` })
        }
      }
    }

    // A page nothing can react on. Under an automatic mode every widget
    // receives, so this can only happen in manual mode.
    if (mode === 'manual') {
      const reactive = widgets.filter(w => !DATA_TYPES_EXEMPT.has(w.widget_type))
      if (reactive.length >= 2 && reactive.every(w => interactionOf(w).receives === false)) {
        findings.push({ severity: 'warning', category: 'wiring', pageId: page.id,
          message: `Nothing on this page will react to a selection — every widget on "${page.name}" is set not to receive, so a reader's clicks change nothing` })
      }
    }
  }

  // ── Cross-dataset clicks with nowhere to land (Phase 6.1)
  //
  // A click carries its column's VALUE to every receiving widget on the page.
  // A widget on another dataset reacts only if that dataset has the same
  // column or a mapping renames it; otherwise the click silently does nothing
  // there. Informational: sometimes that is exactly what the author wants.
  if (mapping) {
    const dsOf = (w: Widget): number | null =>
      ((w.config ?? {}) as { dataset_id?: number }).dataset_id ?? report.dataset_id ?? null
    const colsOf = (id: number) => new Set((mapping.datasets[id]?.columns ?? []).map(c => c.name))
    const mapped = (col: string, from: number, to: number) => mapping.relationships.some(r =>
      (r.from_dataset_id === from && r.to_dataset_id === to && r.from_column === col && colsOf(to).has(r.to_column)) ||
      (r.to_dataset_id === from && r.from_dataset_id === to && r.to_column === col && colsOf(to).has(r.from_column)))
    for (const page of report.pages) {
      const widgets: Widget[] = (page.widgets ?? []).filter(w => !DATA_TYPES_EXEMPT.has(w.widget_type))
      for (const src of widgets) {
        const col = ((src.config ?? {}) as { dimension?: unknown }).dimension
        const from = dsOf(src)
        if (typeof col !== 'string' || from == null || interactionOf(src).broadcasts === false) continue
        const reported = new Set<number>()
        for (const dst of widgets) {
          const to = dsOf(dst)
          if (dst.id === src.id || to == null || to === from || reported.has(to)) continue
          if (interactionOf(dst).receives === false) continue
          const toCols = colsOf(to)
          if (toCols.size === 0 || toCols.has(col) || mapped(col, from, to)) continue
          reported.add(to)
          findings.push({ severity: 'info', category: 'wiring', widgetId: src.id, pageId: page.id,
            message: `Clicks on "${src.title || src.widget_type}" (${col}) will not filter widgets on ${mapping.datasets[to]?.name ?? `dataset ${to}`} such as "${dst.title || dst.widget_type}" — that dataset has no ${col} and no mapping to it. Add one in Model → relationships if they should connect.` })
        }
      }
    }
  }

  const order = { error: 0, warning: 1, info: 2 }
  return findings.sort((a, b) => order[a.severity] - order[b.severity])
}

const SEVERITY_COLOR: Record<Finding['severity'], string> = {
  error: 'var(--danger)', warning: '#f59e0b', info: 'var(--muted)',
}

/** Colour carries severity; the word carries the kind. An author scanning the
 *  list needs to know where to go looking, and "A11Y" on a broken action sends
 *  them to the wrong pane. */
function badgeOf(f: Finding): { label: string; color: string } {
  const color = SEVERITY_COLOR[f.severity]
  if (f.category === 'wiring') return { label: 'WIRING', color }
  if (f.category === 'a11y') return { label: 'A11Y', color }
  // An untagged finding says only how bad it is, so the badge says only that.
  return { label: f.severity === 'error' ? 'ERROR' : f.severity === 'warning' ? 'WARN' : 'INFO', color }
}

export default function ReviewPane({ report, perfStats, onSelectWidget, mapping, canEdit, isAdmin }: {
  report: Report
  perfStats: Record<number, PerfStat>
  onSelectWidget: (widgetId: number, pageId: number) => void
  mapping?: MappingContext
  /** Evaluate Performance runs every widget uncached: an author's tool. */
  canEdit?: boolean
  /** The org's publish gate is an admin setting. */
  isAdmin?: boolean
}) {
  const findings = useMemo(() => reviewReport(report, perfStats, mapping), [report, perfStats, mapping])
  const [perf, setPerf] = useState<PerfEvaluation | null>(null)
  const [perfBusy, setPerfBusy] = useState(false)
  const [perfErr, setPerfErr] = useState<string | null>(null)
  const [gate, setGate] = useState<boolean | null>(null)
  useEffect(() => {
    let live = true
    reviewApi.settings().then(r => { if (live) setGate(r.publish_gate) }).catch(() => { if (live) setGate(null) })
    return () => { live = false }
  }, [])
  const errors = findings.filter(f => f.severity === 'error').length
  const evaluate = async () => {
    setPerfBusy(true); setPerfErr(null)
    try { setPerf(await reviewApi.evaluate(report.id)) }
    catch (e) { setPerfErr((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Could not evaluate') }
    finally { setPerfBusy(false) }
  }
  const qualityCi = (
    <div data-testid="review-ci" style={{ borderTop: '1px solid var(--border)', marginTop: 12, paddingTop: 10, display: 'flex', flexDirection: 'column', gap: 8 }}>
      {gate != null && (
        <div data-testid="publish-gate" style={{ fontSize: 11.5 }}>
          <b>Publish gate:</b> {gate
            ? (errors ? `on — publishing is blocked until the ${errors} error${errors === 1 ? '' : 's'} above ${errors === 1 ? 'is' : 'are'} fixed.` : 'on — no errors open, this report can be published.')
            : 'off — review errors are advice only.'}
          {isAdmin && (
            <button className="btn btn-sm" style={{ marginInlineStart: 6, fontSize: 10.5 }}
              onClick={() => reviewApi.setGate(!gate).then(r => setGate(r.publish_gate)).catch(() => {})}>
              {gate ? 'Turn off for the organisation' : 'Block publishing while errors are open'}
            </button>
          )}
        </div>
      )}
      {canEdit && (
        <div>
          <button className="btn btn-sm" onClick={() => void evaluate()} disabled={perfBusy} style={{ fontSize: 11 }}>
            {perfBusy ? 'Measuring every widget…' : '⏱ Evaluate performance'}
          </button>
          {perfErr && <div role="alert" style={{ fontSize: 11, color: 'var(--danger)', marginTop: 4 }}>{perfErr}</div>}
          {perf && (
            <div data-testid="perf-eval" style={{ marginTop: 6, fontSize: 11 }}>
              <div style={{ color: 'var(--muted)', marginBottom: 4 }}>
                {perf.widgets.length} widgets, {(perf.total_ms / 1000).toFixed(1)}s in total, run now without cache as you
                {perf.slow ? ` · ${perf.slow} slower than ${perf.slow_ms / 1000}s` : ''}
              </div>
              <ol style={{ margin: 0, paddingInlineStart: 18, display: 'flex', flexDirection: 'column', gap: 4 }}>
                {perf.widgets.slice(0, 12).map(w => {
                  const h = perf.history[String(w.dataset_id)]
                  return (
                    <li key={w.widget_id}>
                      <button type="button" onClick={() => onSelectWidget(w.widget_id, report.pages.find(p => p.name === w.page)?.id ?? report.pages[0]?.id)}
                        style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer', color: 'var(--text)', font: 'inherit', textAlign: 'start' }}>
                        <b style={{ color: w.ms > perf.slow_ms ? 'var(--danger)' : 'var(--text)' }}>{w.ms.toLocaleString()} ms</b> — {w.title}
                        <span style={{ color: 'var(--muted)' }}> ({w.page}{w.rows != null ? `, ${w.rows.toLocaleString()} marks` : ''})</span>
                      </button>
                      {w.error && <div style={{ color: 'var(--danger)' }}>{w.error}</div>}
                      {w.advice.map((a, i) => <div key={i} style={{ color: 'var(--muted)' }}>→ {a}</div>)}
                      {h && h.runs > 0 && (
                        <div style={{ color: 'var(--faint, var(--muted))' }}>
                          its dataset, last 7 days: {h.runs.toLocaleString()} queries, median {h.median_ms} ms, p95 {h.p95_ms} ms
                          {h.cache_hit_share != null ? `, ${Math.round(h.cache_hit_share * 100)}% from cache` : ''}
                        </div>
                      )}
                    </li>
                  )
                })}
              </ol>
            </div>
          )}
        </div>
      )}
    </div>
  )

  return (
    <div style={{ padding: 12 }}>
      <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 8 }}>
        Review
      </div>
      {findings.length === 0 ? (
        <p style={{ fontSize: 12, color: 'var(--success)' }}>
          No problems found — titles, alt text, data, display rules and the
          interaction wiring all check out.
        </p>
      ) : (
        <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 6 }}>
          {findings.map((f, i) => (
            <li key={i}>
              <button
                onClick={f.widgetId != null ? () => onSelectWidget(f.widgetId!, f.pageId) : undefined}
                style={{ display: 'flex', gap: 8, alignItems: 'flex-start', width: '100%',
                  textAlign: 'start', background: 'none', border: '1px solid var(--border)',
                  borderRadius: 6, padding: '6px 8px', fontSize: 11, color: 'var(--text)',
                  cursor: f.widgetId != null ? 'pointer' : 'default' }}>
                <span style={{ color: badgeOf(f).color, fontWeight: 700, fontSize: 10.5, flexShrink: 0, paddingTop: 1 }}>
                  {badgeOf(f).label}
                </span>
                <span>{f.message}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {qualityCi}
    </div>
  )
}
