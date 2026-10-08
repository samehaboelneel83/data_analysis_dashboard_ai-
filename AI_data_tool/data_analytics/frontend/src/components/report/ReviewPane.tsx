import { useEffect, useMemo, useState } from 'react'
import { reviewApi, type PerfEvaluation } from '../../services/api'
import { missingRequiredRoles } from './WidgetPlaceholder'
import { roleLabel } from './panelLabels'
import { translate, useT, type MessageKey } from '../../i18n'
import { richT } from '../../i18n/builder/panes'
import { useDirection } from '../../contexts/DirectionContext'

/** A page over this many widgets is heavy: every one queries on load. The
 *  builder's heavy-page banner (redesign 7e4) uses the same count. */
export const HEAVY_PAGE = 14
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
  /** The finding in English. Shown through `key`/`vars` instead, so a reader
   *  in Arabic gets it in Arabic with the names isolated (`richT`). */
  message: string
  key: MessageKey
  vars: Record<string, string | number>
  /** Missing role names, re-joined with the reader's list comma. */
  roles?: string[]
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

/** A finding as the review writes it: the English message is made from the
 *  same template the pane translates, so the two cannot drift apart. */
type Draft = Omit<Finding, 'message'>
const said = (f: Draft): Finding => ({ ...f, message: translate('en', f.key, f.vars) })

export function reviewReport(report: Report, perfStats: Record<number, PerfStat>, mapping?: MappingContext): Finding[] {
  const out: Finding[] = []
  const findings = { push: (f: Draft) => out.push(said(f)) }
  const DATA_TYPES_EXEMPT = new Set(['text', 'button', 'image', 'shape', 'container', 'slicer', 'web_content', 'custom_visual'])

  for (const page of report.pages) {
    const widgets: Widget[] = page.widgets ?? []

    for (const w of widgets) {
      const cfg = (w.config ?? {}) as Record<string, unknown>

      // Accessibility
      if (!w.title && !cfg.alt_text && !DATA_TYPES_EXEMPT.has(w.widget_type)) {
        findings.push({ severity: 'error', category: 'a11y', widgetId: w.id, pageId: page.id,
          key: 'bc.panes.review.untitledNoAlt', vars: { type: w.widget_type } })
      }
      // Unfinished: readers get a placeholder. Mirrors the server's check,
      // which is what the publish gate enforces (Phase 7.4).
      if (!DATA_TYPES_EXEMPT.has(w.widget_type) && w.widget_type !== 'text') {
        const missing = missingRequiredRoles(w)
        if (missing.length) {
          findings.push({ severity: 'error', category: 'wiring', widgetId: w.id, pageId: page.id,
            key: 'bc.panes.review.unfinished', vars: { name: w.title || w.widget_type, roles: missing.join(', ') }, roles: missing })
        }
      }
      if (w.widget_type === 'image' && !cfg.alt) {
        findings.push({ severity: 'error', category: 'a11y', widgetId: w.id, pageId: page.id,
          key: 'bc.panes.review.imageNoAlt', vars: {} })
      }

      // Construction
      const stat = perfStats[w.id]
      if (stat && stat.rowCount === 0 && !DATA_TYPES_EXEMPT.has(w.widget_type)) {
        findings.push({ severity: 'warning', widgetId: w.id, pageId: page.id,
          key: 'bc.panes.review.noRows', vars: { name: w.title || w.widget_type } })
      }
      if (stat?.ruleErrors?.length) {
        findings.push({ severity: 'warning', widgetId: w.id, pageId: page.id,
          key: 'bc.panes.review.brokenRules', vars: { name: w.title || w.widget_type, n: stat.ruleErrors.length } })
      }
      if (w.widget_type === 'container') {
        const children = widgets.filter(x =>
          (x.config as { container_id?: number })?.container_id === w.id)
        if (children.length === 0) {
          findings.push({ severity: 'info', widgetId: w.id, pageId: page.id,
            key: 'bc.panes.review.emptyContainer', vars: { name: String(w.title || w.id) } })
        }
      }

      // Performance
      if (stat && stat.durationMs > 2000) {
        findings.push({ severity: 'warning', widgetId: w.id, pageId: page.id,
          key: 'bc.panes.review.slow', vars: { name: w.title || w.widget_type, s: (stat.durationMs / 1000).toFixed(1) } })
      }
    }

    if (widgets.length > HEAVY_PAGE) {
      findings.push({ severity: 'info', pageId: page.id,
        key: 'bc.panes.review.heavyPage', vars: { page: page.name, n: widgets.length } })
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

  const MODE_KEY: Record<string, MessageKey> = {
    linked: 'bc.panes.review.autoMode.linked', oneway: 'bc.panes.review.autoMode.oneway',
    twoway: 'bc.panes.review.autoMode.twoway',
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
          key: MODE_KEY[mode] ?? 'bc.panes.review.autoMode.other',
          vars: { page: page.name, mode, n: actions.length, name: name(w) } })
        continue
      }

      for (const a of actions) {
        const target = pageOfWidget.get(a.targetId)
        if (!target) {
          findings.push({ severity: 'error', category: 'wiring', widgetId: w.id, pageId: page.id,
            key: 'bc.panes.review.deadTarget', vars: { name: name(w), id: a.targetId } })
          continue
        }
        // Page scoping: a filter survives only when its SOURCE page is the page
        // being drawn, or the source is marked to sync across pages.
        if (target.pageId !== page.id && !it.syncAllPages) {
          findings.push({ severity: 'error', category: 'wiring', widgetId: w.id, pageId: page.id,
            key: 'bc.panes.review.otherPage', vars: { name: name(w), target: name(target.w), page: target.pageName } })
          continue
        }
        if (interactionOf(target.w).receives === false) {
          findings.push({ severity: 'warning', category: 'wiring', widgetId: w.id, pageId: page.id,
            key: 'bc.panes.review.notReceiving', vars: { name: name(w), target: name(target.w) } })
        }
      }
    }

    // A page nothing can react on. Under an automatic mode every widget
    // receives, so this can only happen in manual mode.
    if (mode === 'manual') {
      const reactive = widgets.filter(w => !DATA_TYPES_EXEMPT.has(w.widget_type))
      if (reactive.length >= 2 && reactive.every(w => interactionOf(w).receives === false)) {
        findings.push({ severity: 'warning', category: 'wiring', pageId: page.id,
          key: 'bc.panes.review.deafPage', vars: { page: page.name } })
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
            ...(mapping.datasets[to]?.name
              ? { key: 'bc.panes.review.crossDataset' as const, vars: { name: src.title || src.widget_type, col, dataset: mapping.datasets[to]!.name!, target: dst.title || dst.widget_type } }
              : { key: 'bc.panes.review.crossDatasetUnnamed' as const, vars: { name: src.title || src.widget_type, col, id: to, target: dst.title || dst.widget_type } }) })
        }
      }
    }
  }

  const order = { error: 0, warning: 1, info: 2 }
  return out.sort((a, b) => order[a.severity] - order[b.severity])
}

const SEVERITY_COLOR: Record<Finding['severity'], string> = {
  error: 'var(--danger)', warning: '#f59e0b', info: 'var(--muted)',
}

/** Colour carries severity; the word carries the kind. An author scanning the
 *  list needs to know where to go looking, and "A11Y" on a broken action sends
 *  them to the wrong pane. */
function badgeOf(f: Finding): { key: MessageKey; color: string } {
  const color = SEVERITY_COLOR[f.severity]
  if (f.category === 'wiring') return { key: 'bc.panes.review.badge.wiring', color }
  if (f.category === 'a11y') return { key: 'bc.panes.review.badge.a11y', color }
  // An untagged finding says only how bad it is, so the badge says only that.
  const key: MessageKey = f.severity === 'error' ? 'bc.panes.review.badge.error'
    : f.severity === 'warning' ? 'bc.panes.review.badge.warn' : 'bc.panes.review.badge.info'
  return { key, color }
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
  const t = useT()
  const { rtl, language } = useDirection()
  const findings = useMemo(() => reviewReport(report, perfStats, mapping), [report, perfStats, mapping])
  /** The finding in the reader's language; a list of role names takes the
   *  reader's list comma. */
  // QA4 T1: the role names themselves in the reader's language too ("Measure").
  const say = (f: Finding) => richT(t, f.key, f.roles && language === 'ar'
    ? { ...f.vars, roles: f.roles.map(r => roleLabel(language, r)).join('، ') } : f.vars)
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
    catch (e) { setPerfErr((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? t('bc.panes.review.evaluateFailed')) }
    finally { setPerfBusy(false) }
  }
  const qualityCi = (
    <div data-testid="review-ci" style={{ borderTop: '1px solid var(--border)', marginTop: 12, paddingTop: 10, display: 'flex', flexDirection: 'column', gap: 8 }}>
      {gate != null && (
        <div data-testid="publish-gate" style={{ fontSize: 11.5 }}>
          <b>{t('bc.panes.review.gate')}</b> {gate
            ? (errors ? t('bc.panes.review.gateBlocked', { n: errors }) : t('bc.panes.review.gateClear'))
            : t('bc.panes.review.gateOff')}
          {isAdmin && (
            <button className="btn btn-sm" style={{ marginInlineStart: 6, fontSize: 10.5 }}
              onClick={() => reviewApi.setGate(!gate).then(r => setGate(r.publish_gate)).catch(() => {})}>
              {gate ? t('bc.panes.review.gateTurnOff') : t('bc.panes.review.gateTurnOn')}
            </button>
          )}
        </div>
      )}
      {canEdit && (
        <div>
          <button className="btn btn-sm" onClick={() => void evaluate()} disabled={perfBusy} style={{ fontSize: 11 }}>
            {perfBusy ? t('bc.panes.review.measuring') : t('bc.panes.review.evaluate')}
          </button>
          {perfErr && <div role="alert" style={{ fontSize: 11, color: 'var(--danger)', marginTop: 4 }}>{perfErr}</div>}
          {perf && (
            <div data-testid="perf-eval" style={{ marginTop: 6, fontSize: 11 }}>
              <div style={{ color: 'var(--muted)', marginBottom: 4 }}>
                {t('bc.panes.review.perf.summary', { n: perf.widgets.length, s: (perf.total_ms / 1000).toFixed(1) })}
                {perf.slow ? t('bc.panes.review.perf.slow', { n: perf.slow, s: perf.slow_ms / 1000 }) : ''}
              </div>
              <ol style={{ margin: 0, paddingInlineStart: 18, display: 'flex', flexDirection: 'column', gap: 4 }}>
                {perf.widgets.slice(0, 12).map(w => {
                  const h = perf.history[String(w.dataset_id)]
                  return (
                    <li key={w.widget_id}>
                      <button type="button" onClick={() => onSelectWidget(w.widget_id, report.pages.find(p => p.name === w.page)?.id ?? report.pages[0]?.id)}
                        style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer', color: 'var(--text)', font: 'inherit', textAlign: 'start' }}>
                        <b style={{ color: w.ms > perf.slow_ms ? 'var(--danger)' : 'var(--text)' }}>{t('bc.panes.review.perf.ms', { ms: w.ms.toLocaleString() })}</b> — <bdi>{w.title}</bdi>
                        <span style={{ color: 'var(--muted)' }}> ({w.rows != null
                          ? richT(t, 'bc.panes.review.perf.where', { page: w.page, rows: w.rows.toLocaleString() })
                          : <bdi>{w.page}</bdi>})</span>
                      </button>
                      {w.error && <div style={{ color: 'var(--danger)' }}>{w.error}</div>}
                      {w.advice.map((a, i) => <div key={i} style={{ color: 'var(--muted)' }}>{rtl ? '←' : '→'} {a}</div>)}
                      {h && h.runs > 0 && (
                        <div style={{ color: 'var(--faint, var(--muted))' }}>
                          {t('bc.panes.review.perf.history', { runs: h.runs.toLocaleString(), median: h.median_ms ?? '', p95: h.p95_ms ?? '' })}
                          {h.cache_hit_share != null ? t('bc.panes.review.perf.cache', { pct: Math.round(h.cache_hit_share * 100) }) : ''}
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
        {t('builder.pane.review')}
      </div>
      {findings.length === 0 ? (
        <p style={{ fontSize: 12, color: 'var(--success)' }}>
          {t('bc.panes.review.none')}
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
                  {t(badgeOf(f).key)}
                </span>
                <span>{say(f)}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {qualityCi}
    </div>
  )
}
