/**
 * The reader's analysis kit (MASTER_PLAN Phase 5 item 2): what a person
 * READING a dashboard can do with a widget without editing it.
 *
 *  - Explain this: which columns move the widget's measure, over the rows the
 *    widget shows (its filters and the page's selections).
 *  - View as…: the same data as another chart, the resolver's pick marked
 *    "(recommended)". Local to this reader; nothing is saved.
 *  - What if…: on a forecast, move the factors with sliders and see the
 *    projection change, with each factor's evidence and extrapolation named.
 *
 * Read-only and secured: every request goes through the same endpoints (row
 * security, column security) the widget itself does, and nothing persists.
 */
import { useEffect, useMemo, useState } from 'react'
import { describeSpec, parseSpec } from '../../lib/relativeDates'
import { analysisCatalogueApi, differenceApi, explainApi, type DatasetColumn, type DifferenceCheck } from '../../services/api'
import { chartForFields } from '../../lib/autoChart'
import { useModalDialog } from '../ui/useModalDialog'

/** Widget types that draw the plain dimension+measure series, so any one of
 *  them can show another's data with no new query. */
export const VIEW_AS_FAMILY = ['bar', 'line', 'area', 'pie', 'donut', 'treemap', 'funnel', 'step', 'dot_plot'] as const
const LABELS: Record<string, string> = {
  bar: 'Bar chart', line: 'Line chart', area: 'Area chart', pie: 'Pie chart', donut: 'Donut',
  treemap: 'Treemap', funnel: 'Funnel', step: 'Step plot', dot_plot: 'Dot plot',
}

export function viewAsOptions(widgetType: string, cfg: Record<string, unknown>, columns: DatasetColumn[],
                              rowCount: number): { type: string; label: string; recommended: boolean }[] {
  if (!(VIEW_AS_FAMILY as readonly string[]).includes(widgetType)) return []
  const dim = typeof cfg.dimension === 'string' ? cfg.dimension : null
  if (!dim || cfg.dimension2) return []
  const col = columns.find(c => c.name === dim)
  const measure = typeof cfg.measure === 'string' ? cfg.measure : null
  const pick = chartForFields([
    { name: dim, dtype: col?.dtype ?? 'categorical', numeric: false },
    ...(measure ? [{ name: measure, dtype: 'numeric', numeric: true }] : []),
  ])?.suggestion.widget_type ?? 'bar'
  const additive = !cfg.aggregation || ['sum', 'count'].includes(String(cfg.aggregation))
  return (VIEW_AS_FAMILY as readonly string[])
    // A pie of 40 slices, or of averages, is a chart that lies about parts
    // and wholes -- not offered, rather than offered and regretted.
    .filter(t => !['pie', 'donut', 'treemap', 'funnel'].includes(t) || (additive && rowCount <= 12))
    .filter(t => t !== widgetType)
    .map(t => ({ type: t, label: LABELS[t] ?? t, recommended: t === pick }))
    .sort((a, b) => Number(b.recommended) - Number(a.recommended))
}

function Dialog({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  const ref = useModalDialog<HTMLDivElement>(onClose)
  return (
    <div onClick={onClose} style={{ position: 'fixed', inset: 0, zIndex: 1000, background: 'rgba(0,0,0,.45)',
      display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div ref={ref} role="dialog" aria-modal="true" aria-label={title} onClick={e => e.stopPropagation()}
        style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)',
          padding: 18, width: 'min(520px, calc(100vw - 32px))', maxHeight: 'calc(100vh - 64px)', overflow: 'auto',
          display: 'flex', flexDirection: 'column', gap: 10, fontSize: 13 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <b>{title}</b>
          <button type="button" className="btn btn-sm" aria-label="Close" onClick={onClose}>×</button>
        </div>
        {children}
      </div>
    </div>
  )
}

interface ExplainResult {
  factors: { column: string; score: number; relative: number; direction?: string; kind?: string }[]
  narrative?: string | null
  narrative_source?: string | null
  note?: string | null
  rows?: number
  rows_before_filters?: number
}

export function ExplainDialog({ datasetId, measure, filters, onClose }: {
  datasetId: number; measure: string; filters: unknown[]; onClose: () => void
}) {
  const [res, setRes] = useState<ExplainResult | null>(null)
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => {
    let live = true
    explainApi.explain(datasetId, measure, filters)
      .then((r: ExplainResult) => { if (live) setRes(r) })
      .catch((e: { response?: { data?: { detail?: string } } }) => { if (live) setErr(e?.response?.data?.detail ?? 'Could not explain this') })
    return () => { live = false }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [datasetId, measure, JSON.stringify(filters)])
  return (
    <Dialog title={`What moves ${measure}`} onClose={onClose}>
      {err && <div role="alert" style={{ color: 'var(--danger)' }}>{err}</div>}
      {!res && !err && <div style={{ color: 'var(--muted)' }}>Looking at every column…</div>}
      {res && (
        <>
          {res.narrative && (
            <p style={{ margin: 0 }}>{res.narrative} {res.narrative_source === 'model' && <span style={{ fontSize: 10, color: 'var(--muted)' }}>(sentence written by the AI from the figures below)</span>}</p>
          )}
          {res.note && <p style={{ margin: 0, color: 'var(--muted)' }}>{res.note}</p>}
          <div data-testid="explain-factors" style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {res.factors.slice(0, 8).map(f => (
              <div key={f.column} style={{ display: 'grid', gridTemplateColumns: 'minmax(90px, 35%) 1fr 48px', gap: 6, alignItems: 'center', fontSize: 12 }}>
                <span>{f.column}{f.direction ? ` (${f.direction === '+' ? 'rises with' : 'falls as it rises'})` : ''}</span>
                <div style={{ background: 'var(--surface2)', borderRadius: 4, height: 10 }}>
                  <div style={{ width: `${Math.round(f.relative * 100)}%`, height: '100%', borderRadius: 4, background: 'var(--accent)' }} />
                </div>
                <span style={{ textAlign: 'end', fontVariantNumeric: 'tabular-nums' }}>{f.relative.toFixed(2)}</span>
              </div>
            ))}
          </div>
          <p style={{ margin: 0, fontSize: 11, color: 'var(--muted)' }}>
            Strength of each column's relationship with {measure}, the strongest set to 1. Relationship, not cause.
            {res.rows != null && ` Over the ${res.rows.toLocaleString()} rows this widget shows`}
            {res.rows != null && res.rows_before_filters != null && res.rows_before_filters > res.rows
              ? ` (of ${res.rows_before_filters.toLocaleString()} before its filters).` : res.rows != null ? '.' : ''}
          </p>
        </>
      )}
    </Dialog>
  )
}

interface ScenarioResult {
  factors: { column: string; coefficient: number; p_value: number; observed_min: number; observed_max: number; recent_level: number }[]
  history: { name: string; value: number }[]
  baseline: { name: string; value: number }[]
  scenario: { name: string; value: number }[]
  baseline_total: number
  scenario_total: number
  difference: number
  extrapolating: boolean
  caveats: string[]
}

function Spark({ series }: { series: { name: string; values: number[]; color: string; dashed?: boolean }[] }) {
  const W = 460, H = 120
  const all = series.flatMap(s => s.values)
  const lo = Math.min(...all), hi = Math.max(...all)
  const n = Math.max(...series.map(s => s.values.length))
  const x = (i: number) => (i / Math.max(1, n - 1)) * (W - 8) + 4
  const y = (v: number) => H - 6 - ((v - lo) / (hi - lo || 1)) * (H - 12)
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Projection" style={{ background: 'var(--surface2)', borderRadius: 6 }}>
      {series.map(s => (
        <polyline key={s.name} fill="none" stroke={s.color} strokeWidth={2} strokeDasharray={s.dashed ? '5 4' : undefined}
          points={s.values.map((v, i) => `${x(i + (n - s.values.length))},${y(v)}`).join(' ')} />
      ))}
    </svg>
  )
}

export function ScenarioDialog({ datasetId, dateColumn, measure, candidates, onClose }: {
  datasetId: number; dateColumn: string; measure: string; candidates: string[]; onClose: () => void
}) {
  const [factors, setFactors] = useState<string[]>(candidates.slice(0, 2))
  const [moves, setMoves] = useState<Record<string, number>>({})
  const [res, setRes] = useState<ScenarioResult | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const sig = JSON.stringify([factors, moves])
  useEffect(() => {
    if (!factors.length) { setRes(null); setErr(null); return }
    let live = true
    const t = setTimeout(() => {
      analysisCatalogueApi.run(datasetId, 'forecast_scenario', {
        date_column: dateColumn, measure, factors,
        adjustments: Object.fromEntries(factors.map(f => [f, (moves[f] ?? 0) / 100])),
      })
        .then(r => { if (live) { setRes(r.result as ScenarioResult); setErr(null) } })
        .catch((e: { response?: { data?: { detail?: string } } }) => { if (live) { setRes(null); setErr(e?.response?.data?.detail ?? 'Could not project this') } })
    }, 350)
    return () => { live = false; clearTimeout(t) }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [datasetId, dateColumn, measure, sig])
  const pct = (a: number, b: number) => (b ? `${a >= 0 ? '+' : ''}${((a / b) * 100).toFixed(1)}%` : '')
  return (
    <Dialog title={`What if… (${measure})`} onClose={onClose}>
      <div style={{ fontSize: 12 }}>
        <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', marginBottom: 4 }}>Factors</div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {candidates.map(c => (
            <label key={c} style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
              <input type="checkbox" checked={factors.includes(c)}
                onChange={() => setFactors(f => f.includes(c) ? f.filter(x => x !== c) : [...f, c].slice(0, 8))} /> {c}
            </label>
          ))}
        </div>
      </div>
      {factors.map(f => {
        const info = res?.factors.find(x => x.column === f)
        return (
          <label key={f} style={{ display: 'block', fontSize: 12 }}>
            <span style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span>{f}: <b>{(moves[f] ?? 0) >= 0 ? '+' : ''}{moves[f] ?? 0}%</b></span>
              {info && <span style={{ color: info.p_value > 0.05 ? 'var(--danger)' : 'var(--muted)', fontSize: 11 }}>
                p = {info.p_value < 0.001 ? '< 0.001' : info.p_value.toFixed(3)}{info.p_value > 0.05 ? ' — weak evidence' : ''}
              </span>}
            </span>
            <input type="range" min={-50} max={50} step={5} value={moves[f] ?? 0} aria-label={`Change ${f} by percent`}
              onChange={e => setMoves(m => ({ ...m, [f]: Number(e.target.value) }))} style={{ width: '100%' }} />
          </label>
        )
      })}
      {err && <div role="alert" style={{ color: 'var(--danger)', fontSize: 12 }}>{err}</div>}
      {res && (
        <>
          <Spark series={[
            { name: 'history', values: [...res.history.map(p => p.value)], color: 'var(--muted)' },
            { name: 'baseline', values: [...res.history.map(p => p.value), ...res.baseline.map(p => p.value)], color: 'var(--border)', dashed: true },
            { name: 'scenario', values: [...res.history.map(p => p.value), ...res.scenario.map(p => p.value)], color: 'var(--accent)' },
          ]} />
          <div data-testid="scenario-summary" style={{ fontSize: 12 }}>
            Next {res.scenario.length} periods: <b>{res.scenario_total.toLocaleString()}</b> vs {res.baseline_total.toLocaleString()} if nothing changes
            {' '}(<b style={{ color: res.difference >= 0 ? 'var(--success, #2e7d32)' : 'var(--danger)' }}>{pct(res.difference, res.baseline_total)}</b>).
          </div>
          {res.extrapolating && (
            <div role="alert" style={{ fontSize: 11.5, padding: '6px 8px', borderRadius: 6, border: '1px solid var(--warning, #d68910)' }}>
              ⚠ This scenario goes outside anything observed — the projection is an extrapolation, not evidence.
            </div>
          )}
          <ul style={{ margin: 0, paddingInlineStart: 18, fontSize: 11, color: 'var(--muted)' }}>
            {res.caveats.map((c, i) => <li key={i}>{c}</li>)}
          </ul>
        </>
      )}
    </Dialog>
  )
}

export function useViewAs(widgetId: number) {
  const [viewAs, setViewAs] = useState<string | null>(null)
  useEffect(() => { setViewAs(null) }, [widgetId])
  return useMemo(() => ({ viewAs, setViewAs }), [viewAs])
}

// ── "Why am I seeing this?" ─────────────────────────────────────────────────

export interface FilterLike { column: string; op?: string; value: unknown; granularity?: string }

const OP_WORDS: Record<string, string> = {
  eq: 'is', neq: 'is not', gt: '>', lt: '<', gte: '≥', lte: '≤', in: 'is one of', like: 'contains',
}

/** One filter as a sentence fragment: "region is North". */
export function describeFilter(f: FilterLike): string {
  if (f.op === 'relative') return `${f.column}: ${describeSpec(parseSpec(f.value))}`
  const v = Array.isArray(f.value) ? f.value.map(String).join(', ') : String(f.value)
  return `${f.column} ${OP_WORDS[f.op ?? 'eq'] ?? f.op} ${v}${f.granularity ? ` (${f.granularity})` : ''}`
}

export interface WhySection { title: string; items: string[]; empty: string }

/**
 * Every layer that decides what a widget shows, in the order they apply --
 * the author's permanent filters, the report's, the reader's own selections,
 * drill steps, ranking and limits, display rules -- in one inspectable list.
 * SAS never assembled this; a reader who cannot see it cannot trust a number.
 */
export function WhyDialog({ title, sections, footnote, onClose }: {
  title: string; sections: WhySection[]; footnote?: string; onClose: () => void
}) {
  return (
    <Dialog title={`Why am I seeing this? — ${title}`} onClose={onClose}>
      <div data-testid="why-sections" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {sections.map(s => (
          <div key={s.title}>
            <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.06em' }}>{s.title}</div>
            {s.items.length === 0
              ? <div style={{ fontSize: 12, color: 'var(--muted)' }}>{s.empty}</div>
              : <ul style={{ margin: '2px 0 0', paddingInlineStart: 18, fontSize: 12.5 }}>{s.items.map((it, i) => <li key={i}>{it}</li>)}</ul>}
          </div>
        ))}
      </div>
      {footnote && <p style={{ margin: 0, fontSize: 11, color: 'var(--muted)' }}>{footnote}</p>}
    </Dialog>
  )
}


const EFFECT_WORD: Record<string, string> = { cohens_d: "Cohen's d", cohens_h: "Cohen's h", rank_biserial: 'rank-biserial r' }

/** The evidence chip: test, p, effect size and its label -- never p alone. */
export function EvidenceChip({ test, p_text, effect_name, effect_size, effect_label, significant }: {
  test: string; p_text: string; effect_name: string; effect_size: number; effect_label: string; significant: boolean
}) {
  return (
    <span data-testid="evidence-chip" title={`${test}; ${p_text}; ${EFFECT_WORD[effect_name] ?? effect_name} = ${effect_size} (${effect_label})`}
      style={{ display: 'inline-flex', gap: 6, alignItems: 'center', fontSize: 10.5, padding: '1px 8px', borderRadius: 99,
        border: `1px solid ${significant && effect_label !== 'negligible' ? 'var(--accent)' : 'var(--border)'}`,
        color: 'var(--muted)', whiteSpace: 'nowrap' }}>
      {test} · {p_text} · {effect_label} effect ({EFFECT_WORD[effect_name] ?? effect_name} {effect_size})
    </span>
  )
}

/**
 * "Is this difference real?" -- two bars, the rows behind them, and a test
 * chosen by what the bars aggregate (count -> row split, average -> Welch,
 * median -> Mann-Whitney, sum -> both drivers). Every number arrives with its
 * test, effect size and population.
 */
export function DifferenceDialog({ datasetId, dimension, measure, aggregation, granularity, filters, names, initial, onClose }: {
  datasetId: number; dimension: string; measure: string | null; aggregation: string
  granularity?: string | null; filters: unknown[]; names: string[]; initial: [string, string]; onClose: () => void
}) {
  const [a, setA] = useState(initial[0])
  const [b, setB] = useState(initial[1])
  const [res, setRes] = useState<DifferenceCheck | null>(null)
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => {
    setRes(null); setErr(null)
    if (!a || !b || a === b) { setErr('Pick two different bars'); return }
    let live = true
    differenceApi.check(datasetId, { dimension, groups: [a, b], measure, aggregation, granularity, filters })
      .then(r => { if (live) setRes(r) })
      .catch((e: { response?: { data?: { detail?: string } } }) => { if (live) setErr(e?.response?.data?.detail ?? 'Could not test this') })
    return () => { live = false }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [datasetId, a, b, dimension, measure, aggregation, granularity, JSON.stringify(filters)])
  const pick = (v: string, set: (x: string) => void, label: string) => (
    <select aria-label={label} value={v} onChange={e => set(e.target.value)} style={{ fontSize: 12, maxWidth: 200 }}>
      {names.map(n => <option key={n} value={n}>{n}</option>)}
    </select>
  )
  return (
    <Dialog title="Is this difference real?" onClose={onClose}>
      <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
        {pick(a, setA, 'First bar')} <span style={{ color: 'var(--muted)' }}>vs</span> {pick(b, setB, 'Second bar')}
        <span style={{ fontSize: 11, color: 'var(--muted)' }}>· {aggregation}{measure ? ` of ${measure}` : ' of rows'} by {dimension}</span>
      </div>
      {err && <div role="alert" style={{ color: 'var(--danger)' }}>{err}</div>}
      {!res && !err && <div style={{ color: 'var(--muted)' }}>Testing the rows behind both bars…</div>}
      {res && (
        <div data-testid="difference-result" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div style={{ fontWeight: 600 }}>{res.summary}</div>
          {res.tests.map((t, i) => (
            <div key={i} style={{ borderInlineStart: '2px solid var(--border)', paddingInlineStart: 8 }}>
              <div style={{ fontSize: 11, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.04em' }}>{t.question}</div>
              <div style={{ fontSize: 12.5 }}>{t.sentence}</div>
              <div style={{ fontSize: 12, margin: '2px 0' }} dir="auto">
                {Object.entries(t.values).map(([k, v]) => `${k}: ${v.toLocaleString()}`).join(' · ')}
                {t.question === 'typical row' ? ` (${res.population.aggregation === 'median' ? 'median' : 'mean'} per row)` : ' rows'}
              </div>
              <EvidenceChip {...t} />
            </div>
          ))}
          <div style={{ fontSize: 11, color: 'var(--muted)' }}>
            Population: {res.population.rows_a.toLocaleString()} rows of {res.population.group_a} and {res.population.rows_b.toLocaleString()} of {res.population.group_b}.
          </div>
          <ul style={{ margin: 0, paddingInlineStart: 18, fontSize: 11, color: 'var(--muted)' }}>
            {res.caveats.map((c, i) => <li key={i}>{c}</li>)}
          </ul>
        </div>
      )}
    </Dialog>
  )
}
