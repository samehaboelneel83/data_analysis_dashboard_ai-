/**
 * Models as widgets (MASTER_PLAN Phase 3): a header that says what was fitted,
 * how well, and on how many rows -- over tabs of diagnostics for ONE fit.
 *
 * SAS's statistics objects are its strongest work: event, fit statistic and
 * population in the header ("Observations: 646K of 2.3M"), sub-tabs for the
 * alternative views of the same model, and a Model comparison that colours the
 * verdict. The shaper (backend services/model_widgets.py) supplies every
 * number; this file only draws them, and draws the refusals in words.
 */
import { useState } from 'react'
import { seriesColor } from '../chartUtils'
import { useT, type MessageKey } from '../../../i18n'
import { useDirection, navArrows } from '../../../contexts/DirectionContext'
import type { ChartRendererProps } from './types'

type Tab = { key: string; label: string }

const fmt = (v: unknown, digits = 3) => {
  if (v === null || v === undefined || v === '') return '—'
  const n = Number(v)
  if (!Number.isFinite(n)) return String(v)
  const a = Math.abs(n)
  return a !== 0 && (a < 0.001 || a >= 1e6) ? n.toExponential(2) : n.toLocaleString(undefined, { maximumFractionDigits: digits })
}
/** An odds ratio per unit of a large-scale predictor (salary per dollar) sits
 *  a hair from 1; three decimals showed "1" and an interval of "1 – 1"
 *  (HR re-test 2026-10-01). Near 1, six decimals keep the effect visible. */
const ofmt = (v: unknown) => (Math.abs(Number(v) - 1) < 0.01 ? fmt(v, 6) : fmt(v))
const pfmt = (p: unknown) => (p == null ? '—' : Number(p) < 0.001 ? '< 0.001' : fmt(p, 3))

// Fixed text in the reader's language (HR re-test 2026-10-01: every model
// widget was English in Arabic mode). Sentences the statistics engine writes
// (the interpretation, caveats) still arrive in English from the server.
const MODEL_NAMES: Record<string, MessageKey> = {
  linear: 'mdl.linear', logistic: 'mdl.logistic', tree: 'mdl.tree',
  cluster: 'mdl.cluster', compare: 'mdl.compare', score: 'mdl.score', rules: 'mdl.rules',
}

function Population({ pop }: { pop: any }) {
  const tr = useT()
  if (!pop) return null
  const dropped = Object.entries(pop.dropped_by ?? {}) as [string, number][]
  return (
    <div data-testid="model-population" style={{ fontSize: 11, color: 'var(--muted)' }}>
      {tr('mdl.rowsUsed')} <b style={{ color: 'var(--text)' }}>{Number(pop.rows_used ?? 0).toLocaleString()}</b> {tr('mdl.of')} {Number(pop.rows_total ?? 0).toLocaleString()}
      {pop.rows_dropped > 0 && <> — {tr('mdl.dropped', { n: Number(pop.rows_dropped).toLocaleString() })}{dropped.length > 0 && <> ({tr('mdl.missing')} {dropped.map(([c, n]) => `${c} ${n.toLocaleString()}`).join(', ')})</>}</>}
      {pop.rows_before_filters != null && <> · {tr('mdl.refitted', { n: Number(pop.rows_before_filters).toLocaleString() })}</>}
      {pop.sampled_from && <> · {tr('mdl.sampleFrom', { n: Number(pop.sampled_from).toLocaleString() })}</>}
      {pop.sampled_of && <> · {tr('mdl.sampleOf', { n: Number(pop.sampled_of).toLocaleString() })}</>}
      {pop.partition
        ? <> · {tr('mdl.partition')} <b style={{ color: 'var(--text)' }}>{pop.partition.column}</b>: {tr('mdl.trainedValidated', { a: Number(pop.partition.train_rows).toLocaleString(), b: Number(pop.partition.validation_rows).toLocaleString() })}</>
        : pop.test_rows != null && <> · {tr('mdl.heldOut', { n: Number(pop.test_rows).toLocaleString() })}</>}
    </div>
  )
}

/** A small scatter drawn in SVG (≤ 400 points), with an optional reference line. */
function MiniScatter({ points, xLabel, yLabel, refLine }: {
  points: [number | null, number | null][]; xLabel: string; yLabel: string; refLine?: 'zero' | 'identity'
}) {
  const pts = points.filter(([x, y]) => x != null && y != null) as [number, number][]
  if (!pts.length) return <p style={{ fontSize: 12, color: 'var(--muted)' }}>Nothing to plot.</p>
  const xs = pts.map(p => p[0]), ys = pts.map(p => p[1])
  let [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)]
  if (refLine === 'identity') { x0 = y0 = Math.min(x0, y0); x1 = y1 = Math.max(x1, y1) }
  if (refLine === 'zero') { y0 = Math.min(y0, 0); y1 = Math.max(y1, 0) }
  const W = 300, H = 170, P = 30
  const sx = (v: number) => P + ((v - x0) / ((x1 - x0) || 1)) * (W - P - 6)
  const sy = (v: number) => H - P + 6 - ((v - y0) / ((y1 - y0) || 1)) * (H - P)
  return (
    <svg viewBox={`0 0 ${W} ${H + 12}`} role="img" aria-label={`${yLabel} against ${xLabel}, ${pts.length} points`}
      style={{ width: '100%', maxHeight: 220, color: seriesColor(0) }}>
      <line x1={P} y1={H - P + 6} x2={W - 6} y2={H - P + 6} stroke="var(--border)" />
      <line x1={P} y1={6} x2={P} y2={H - P + 6} stroke="var(--border)" />
      {refLine === 'zero' && <line x1={P} x2={W - 6} y1={sy(0)} y2={sy(0)} stroke="var(--muted)" strokeDasharray="4 3" />}
      {refLine === 'identity' && <line x1={sx(x0)} y1={sy(y0)} x2={sx(x1)} y2={sy(y1)} stroke="var(--muted)" strokeDasharray="4 3" />}
      {pts.map(([x, y], i) => <circle key={i} cx={sx(x)} cy={sy(y)} r={2.2} fill="currentColor" fillOpacity={0.55} />)}
      <text x={W / 2} y={H + 10} textAnchor="middle" fontSize="9" fill="var(--muted)">{xLabel}</text>
      <text x={8} y={H / 2} textAnchor="middle" fontSize="9" fill="var(--muted)" transform={`rotate(-90 8 ${H / 2})`}>{yLabel}</text>
      <text x={P} y={H - P + 16} fontSize="8" fill="var(--muted)">{fmt(x0, 2)}</text>
      <text x={W - 6} y={H - P + 16} fontSize="8" textAnchor="end" fill="var(--muted)">{fmt(x1, 2)}</text>
      <text x={P - 3} y={sy(y1) + 3} fontSize="8" textAnchor="end" fill="var(--muted)">{fmt(y1, 2)}</text>
      <text x={P - 3} y={sy(y0)} fontSize="8" textAnchor="end" fill="var(--muted)">{fmt(y0, 2)}</text>
    </svg>
  )
}


/** Every compared model's ROC on the same held-out rows, one line each, the
 *  winner drawn heavier, AUC in the legend beside its colour -- the overlay the
 *  verdict bars cannot show (two models can tie on AUC and differ where the
 *  threshold will actually be set). */
function RocOverlay({ models, winner }: { models: any[]; winner?: unknown }) {
  const W = 300, H = 180, P = 30
  const sx = (v: number) => P + v * (W - P - 6)
  const sy = (v: number) => H - P + 6 - v * (H - P)
  return (
    <div data-testid="roc-overlay">
      <svg viewBox={`0 0 ${W} ${H + 12}`} role="img"
        aria-label={`ROC curves: ${models.map(m => `${m.title} AUC ${fmt(m.score, 3)}`).join('; ')}`}
        style={{ width: '100%', maxHeight: 230 }}>
        <line x1={P} y1={H - P + 6} x2={W - 6} y2={H - P + 6} stroke="var(--border)" />
        <line x1={P} y1={6} x2={P} y2={H - P + 6} stroke="var(--border)" />
        <line x1={sx(0)} y1={sy(0)} x2={sx(1)} y2={sy(1)} stroke="var(--muted)" strokeDasharray="4 3" />
        {models.map((m, i) => (
          <polyline key={m.id ?? i} fill="none" stroke={seriesColor(i)}
            strokeWidth={m.id === winner ? 2.4 : 1.4}
            points={(m.roc as [number, number][]).filter(p => p[0] != null && p[1] != null)
              .map(([x, y]) => `${sx(x)},${sy(y)}`).join(' ')} />
        ))}
        <text x={W / 2} y={H + 10} textAnchor="middle" fontSize="9" fill="var(--muted)">false positive rate</text>
        <text x={8} y={H / 2} textAnchor="middle" fontSize="9" fill="var(--muted)" transform={`rotate(-90 8 ${H / 2})`}>true positive rate</text>
      </svg>
      <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexWrap: 'wrap', gap: 10, fontSize: 11 }}>
        {models.map((m, i) => (
          <li key={m.id ?? i} style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontWeight: m.id === winner ? 700 : 400 }}>
            <span aria-hidden style={{ width: 14, height: 3, background: seriesColor(i), display: 'inline-block' }} />
            {m.title} — AUC {fmt(m.score, 3)}
          </li>
        ))}
      </ul>
      <p style={{ fontSize: 10, color: 'var(--muted)', margin: '4px 0 0' }}>Same held-out rows for every curve; the dashed diagonal is a coin toss (AUC 0.5).</p>
    </div>
  )
}

const th: React.CSSProperties = { textAlign: 'start', padding: '4px 6px', fontSize: 11, color: 'var(--muted)', fontWeight: 600, borderBottom: '1px solid var(--border)' }
const td: React.CSSProperties = { padding: '3px 6px', fontSize: 12, borderBottom: '1px solid var(--border)' }
const tdn: React.CSSProperties = { ...td, textAlign: 'end', fontVariantNumeric: 'tabular-nums' }

function Coefficients({ coefs, odds }: { coefs: any[]; odds?: boolean }) {
  const tr = useT()
  return (
    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
      <thead><tr>
        <th style={th}>{tr('mdl.term')}</th>
        <th style={{ ...th, textAlign: 'end' }}>{odds ? tr('mdl.oddsRatio') : tr('mdl.coefficient')}</th>
        <th style={{ ...th, textAlign: 'end' }}>95% CI</th>
        <th style={{ ...th, textAlign: 'end' }}>p</th>
      </tr></thead>
      <tbody>
        {coefs.map(c => (
          <tr key={c.term} style={{ fontWeight: c.significant && c.term !== 'const' ? 600 : 400 }}>
            <td style={td}>{c.term === 'const' ? tr('mdl.intercept') : c.term}{c.significant && c.term !== 'const' ? ' ✱' : ''}</td>
            <td style={tdn}>{odds ? ofmt(c.odds_ratio) : fmt(c.coefficient)}</td>
            <td style={tdn}>{odds ? `${ofmt(c.or_ci_low)} – ${ofmt(c.or_ci_high)}` : `${fmt(c.ci_low)} – ${fmt(c.ci_high)}`}</td>
            <td style={tdn}>{pfmt(c.p_value)}</td>
          </tr>
        ))}
      </tbody>
      <caption style={{ captionSide: 'bottom', textAlign: 'start', fontSize: 10, color: 'var(--muted)', paddingTop: 4 }}>
        {tr('mdl.sig5')}{odds ? ' ' + tr('mdl.oddsHint') : ''}
      </caption>
    </table>
  )
}

function Confusion({ c }: { c: any }) {
  const cell = (label: string, n: number, good: boolean) => (
    <div style={{ padding: 8, borderRadius: 6, textAlign: 'center',
      background: good ? 'color-mix(in srgb, var(--accent) 18%, transparent)' : 'var(--surface2)' }}>
      <div style={{ fontSize: 18, fontWeight: 700 }}>{n.toLocaleString()}</div>
      <div style={{ fontSize: 10, color: 'var(--muted)' }}>{label}</div>
    </div>
  )
  return (
    <div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, maxWidth: 320 }}>
        {cell('predicted event, was event', c.tp, true)}{cell('predicted event, was not', c.fp, false)}
        {cell('predicted not, was event', c.fn, false)}{cell('predicted not, was not', c.tn, true)}
      </div>
      <p style={{ fontSize: 10, color: 'var(--muted)', marginTop: 6 }}>Rows classified at a probability threshold of {c.threshold}.</p>
    </div>
  )
}

function TreeOutline({ node, depth = 0 }: { node: any; depth?: number }) {
  if (!node) return null
  const pad = { paddingInlineStart: depth * 14, fontSize: 12, lineHeight: 1.6 }
  if (!node.children?.length) {
    return <div style={{ ...pad, color: 'var(--accent)' }}>→ {String(node.prediction)} <span style={{ color: 'var(--muted)' }}>({Number(node.samples).toLocaleString()} rows{node.confidence != null ? `, ${Math.round(node.confidence * 100)}%` : ''})</span></div>
  }
  return (
    <div>
      <div style={pad}>If <b>{node.label}</b>:</div>
      <TreeOutline node={node.children[0]} depth={depth + 1} />
      <div style={pad}>Otherwise:</div>
      <TreeOutline node={node.children[1]} depth={depth + 1} />
    </div>
  )
}

function Bars({ rows, accentId, baseline, percent }: { rows: { id?: unknown; name: string; value: number | null }[]; accentId?: unknown; baseline?: { label: string; value: number }; percent?: boolean }) {
  const tr = useT()
  // Whole units from 100 up: a predicted salary read "88,851.211" -- and the
  // fixed 56px column then cut it to ",851.211" (HR re-test 2026-10-01).
  const show = (v: number | null) => percent && v != null ? `${(v * 100).toFixed(1)}%`
    : fmt(v, v != null && Math.abs(v) >= 100 ? 0 : 3)
  const vals = rows.map(r => r.value ?? 0).concat(baseline ? [baseline.value] : [])
  const max = Math.max(...vals, 0) || 1
  const min = Math.min(...vals, 0)
  const span = max - min || 1
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      {rows.map((r, i) => (
        <div key={i} style={{ display: 'grid', gridTemplateColumns: 'minmax(80px, 30%) 1fr minmax(56px, max-content)', gap: 6, alignItems: 'center', fontSize: 12 }}>
          <span title={r.name} style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.name}</span>
          <div style={{ background: 'var(--surface2)', borderRadius: 4, height: 14, position: 'relative' }}>
            <div style={{ position: 'absolute', insetInlineStart: `${((Math.min(0, r.value ?? 0) - min) / span) * 100}%`, width: `${(Math.abs(r.value ?? 0) / span) * 100}%`, height: '100%', borderRadius: 4,
              background: accentId !== undefined && r.id === accentId ? 'var(--accent)' : 'color-mix(in srgb, var(--muted) 45%, transparent)' }} />
          </div>
          <span style={{ textAlign: 'end', fontVariantNumeric: 'tabular-nums' }}>{show(r.value)}</span>
        </div>
      ))}
      {baseline && (
        <div style={{ fontSize: 11, color: 'var(--muted)' }}>{tr('mdl.baseline')} — {baseline.label}: {fmt(baseline.value)}</div>
      )}
    </div>
  )
}

type Item = [string, string]
const sideText = (items: Item[] | undefined, fallback: string) =>
  items?.length ? items.map(([c, v]) => `${c} = ${v}`).join(', ') : fallback

/** One side of a rule: each value as "column = value", the column muted so the
 *  values read first. `dir="auto"` keeps an English value whole in Arabic. */
function Side({ items, fallback }: { items?: Item[]; fallback: string }) {
  if (!items?.length) return <span dir="auto">{fallback}</span>
  return (
    <span style={{ display: 'inline-flex', flexWrap: 'wrap', gap: 4 }}>
      {items.map(([c, v], i) => (
        <span key={i} dir="auto" style={{ padding: '1px 6px', borderRadius: 10, background: 'var(--surface2)', whiteSpace: 'nowrap' }}>
          <span style={{ color: 'var(--muted)' }}>{c}</span> = <b style={{ fontWeight: 600 }}>{v}</b>
        </span>
      ))}
    </span>
  )
}

/** Association rules: If / Then / Lift, with the base rate beside every
 *  confidence -- "90% confident" means nothing for a conclusion true of 90%
 *  of rows anyway. */
const num: React.CSSProperties = { textAlign: 'end', whiteSpace: 'nowrap', width: '1%', verticalAlign: 'top' }
const lead: React.CSSProperties = { display: 'inline-block', minWidth: 34, color: 'var(--muted)', fontSize: 11 }

function RuleTable({ rules }: { rules: any[] }) {
  const tr = useT()
  const pct = (v: unknown) => (v == null ? '—' : `${(Number(v) * 100).toFixed(1)}%`)
  return (
    <table data-testid="rule-table" style={{ width: '100%', borderCollapse: 'collapse' }}>
      <thead><tr>
        <th style={th}>{tr('mdl.r.rule')}</th>
        <th style={{ ...th, ...num }}>{tr('mdl.r.lift')}</th>
        <th style={{ ...th, ...num }}>{tr('mdl.r.conf')}</th>
        <th style={{ ...th, ...num }}>{tr('mdl.r.base')}</th>
        <th style={{ ...th, ...num }}>{tr('mdl.r.rows')}</th>
      </tr></thead>
      <tbody>
        {rules.map((x, i) => (
          <tr key={i}>
            {/* If over Then in ONE cell: as two columns the numbers were
                pushed out of an ordinary-width widget. */}
            <td style={{ ...td, lineHeight: 1.9 }}>
              <div><span style={lead}>{tr('mdl.r.if')}</span><Side items={x.if_items} fallback={x.if} /></div>
              <div><span style={lead}>{tr('mdl.r.then')}</span><Side items={x.then_items} fallback={x.then} /></div>
            </td>
            <td style={{ ...tdn, ...num, fontWeight: 700 }}>{fmt(x.lift, 2)}×</td>
            <td style={{ ...tdn, ...num }}>{pct(x.confidence)}</td>
            <td style={{ ...tdn, ...num, color: 'var(--muted)' }}>{pct(x.base_rate)}</td>
            <td style={{ ...tdn, ...num }}>{Number(x.support_rows).toLocaleString()}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export default function ModelRenderer({ data }: ChartRendererProps) {
  const [tab, setTab] = useState<string | null>(null)
  const tr = useT()
  const { rtl } = useDirection()
  if (!data || data.type !== 'model') return null
  if (data.status === 'refused') {
    // A widget that is simply not set up yet (a comparison with no models to
    // compare) is a next step, not a failure -- headlining it "could not be
    // fitted" the moment it was dropped on the page read as an error.
    const notSetUp = /needs at least|choose|pick|select .* first|no models?/i.test(String(data.reason ?? ''))
    return (
      <div role="note" style={{ padding: 12, fontSize: 13, display: 'flex', flexDirection: 'column', gap: 8 }}>
        <b>{notSetUp ? tr('mdl.notSetUp') : tr('mdl.notFitted')}</b>
        <span>{data.reason}</span>
        <Population pop={data.population} />
      </div>
    )
  }
  if (data.status !== 'ok') return null

  const r = data.result ?? {}
  const kind: string = data.model
  const tabs: Tab[] = kind === 'linear' ? [{ key: 'coef', label: tr('mdl.tab.coef') }, { key: 'resid', label: tr('mdl.tab.resid') }, { key: 'ap', label: tr('mdl.tab.ap') }, { key: 'fit', label: tr('mdl.tab.fit') }]
    : kind === 'logistic' ? [{ key: 'coef', label: tr('mdl.tab.odds') }, { key: 'cm', label: tr('mdl.tab.cm') }, { key: 'roc', label: 'ROC' }, { key: 'fit', label: tr('mdl.tab.fit') }]
    : kind === 'tree' ? [{ key: 'imp', label: tr('mdl.tab.imp') }, { key: 'rules', label: tr('mdl.tab.rules') }, { key: 'fit', label: tr('mdl.tab.fit') }]
    : kind === 'cluster' ? [{ key: 'seg', label: tr('mdl.tab.seg') }, { key: 'fit', label: tr('mdl.tab.fit') }]
    : kind === 'score' ? [{ key: 'pred', label: tr('mdl.tab.pred') }, { key: 'fit', label: tr('mdl.tab.check') }]
    : kind === 'rules' ? [{ key: 'rlist', label: tr('mdl.tab.rules') }, { key: 'lift', label: tr('mdl.tab.lift') }, { key: 'rfit', label: tr('mdl.tab.fit') }]
    : (data.models ?? []).some((m: any) => Array.isArray(m.roc))
      ? [{ key: 'verdict', label: tr('mdl.tab.verdict') }, { key: 'rocs', label: 'ROC' }]
      : [{ key: 'verdict', label: tr('mdl.tab.verdict') }]
  const active = tab && tabs.some(t => t.key === tab) ? tab : tabs[0].key
  const formula = kind === 'cluster' ? (data.variables ?? []).join(', ')
    : kind === 'rules' ? <>
        {data.focus && <>{tr('mdl.r.about')} <bdi><b>{data.focus}</b></bdi> · </>}
        <bdi>{(data.variables ?? []).filter((v: string) => v !== data.focus).join(', ') || tr('mdl.r.all')}</bdi>
      </>
    : kind === 'compare' ? `${(data.models ?? []).length} models of ${data.target}`
    : kind === 'score' ? `saved model “${data.saved?.name}” (${data.saved?.family}) predicts ${data.target}`
    : `${data.target}${data.event != null ? ` = ${data.event}` : ''} ~ ${(data.predictors ?? []).join(' + ') || 'all usable columns'}`
  const fit = data.fit
  const effect = r.effect_label ? ` (${r.effect_label})` : ''
  const held = !!data.population?.partition
  const caveats: string[] = r.caveats ?? r.warnings ?? []
  // Shaper-level warnings are the ones that change what the model means
  // (a leaked answer column) -- shown in the header, not buried in a tab.
  const warnings: string[] = Array.isArray(data.warnings) ? data.warnings : []

  return (
    <div data-testid="model-widget" style={{ height: '100%', display: 'flex', flexDirection: 'column', gap: 6, padding: '2px 4px', overflow: 'hidden' }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        <div style={{ fontSize: 12 }}>
          <b>{MODEL_NAMES[kind] ? tr(MODEL_NAMES[kind]) : tr('mdl.model')}</b> <span style={{ color: 'var(--muted)' }}>· {formula}</span>
        </div>
        {kind === 'rules' && (
          <div style={{ fontSize: 12 }}>
            {(data.rules ?? []).length > 0
              ? <>{tr('mdl.r.strongest')}: <b style={{ color: 'var(--accent)' }}>{fmt(fit?.value, 2)}×</b>
                  <span style={{ color: 'var(--muted)' }}> · {tr('mdl.r.found', { n: (data.rules ?? []).length })}</span></>
              : <span style={{ color: 'var(--muted)' }}>{tr('mdl.r.none')}</span>}
          </div>
        )}
        {fit && kind !== 'compare' && kind !== 'rules' && (
          <div style={{ fontSize: 12 }}>
            {fit.name}: <b style={{ color: 'var(--accent)' }}>{fmt(fit.value)}</b>{held ? '' : effect}
            {/* With a partition the headline is the held-out score; the
                registry's sentence describes the TRAINING fit, so it says so. */}
            {r.interpretation && <span style={{ color: 'var(--muted)' }}> — {held ? `On the training rows: ${r.interpretation}` : r.interpretation}</span>}
          </div>
        )}
        {kind === 'compare' && (
          <div style={{ fontSize: 12 }}>
            {data.winner != null
              ? <>{tr('mdl.winner')} <b style={{ color: 'var(--accent)' }}>{(data.models ?? []).find((m: any) => m.id === data.winner)?.title}</b>
                  {data.winner_beats_baseline ? '' : <span style={{ color: 'var(--danger, #c0392b)' }}> — {tr('mdl.notBeatGuess')}</span>}</>
              : tr('mdl.noneScored')}
            <span style={{ color: 'var(--muted)' }}> · {data.metric}</span>
          </div>
        )}
        <Population pop={data.population} />
        {warnings.map((w, i) => (
          <div key={i} role="alert" style={{ fontSize: 11, padding: '4px 8px', borderRadius: 6,
            border: '1px solid var(--warning, #d68910)', background: 'color-mix(in srgb, var(--warning, #d68910) 10%, transparent)' }}>
            ⚠ {w}
          </div>
        ))}
      </div>

      {tabs.length > 1 && (
        <div role="tablist" aria-label="Model views" style={{ display: 'flex', gap: 2, flexWrap: 'wrap', borderBottom: '1px solid var(--border)' }}>
          {tabs.map(t => (
            <button key={t.key} type="button" role="tab" aria-selected={active === t.key}
              onMouseDown={e => e.stopPropagation()}
              onClick={e => { e.stopPropagation(); setTab(t.key) }}
              style={{ font: 'inherit', fontSize: 11, padding: '3px 8px', cursor: 'pointer', background: 'none', border: 'none',
                borderBottom: `2px solid ${active === t.key ? 'var(--accent)' : 'transparent'}`,
                color: active === t.key ? 'var(--text)' : 'var(--muted)' }}>
              {t.label}
            </button>
          ))}
        </div>
      )}

      {/* Focusable: it scrolls, and a keyboard user must be able to (E10). */}
      <div role="tabpanel" tabIndex={0} style={{ flex: 1, minHeight: 0, overflow: 'auto' }}>
        {active === 'coef' && <Coefficients coefs={r.detail?.coefficients ?? []} odds={kind === 'logistic'} />}
        {active === 'coef' && data.encodings && Object.keys(data.encodings).length > 0 && (
          <p style={{ fontSize: 10, color: 'var(--muted)', margin: '4px 0 0' }}>
            {Object.entries(data.encodings as Record<string, { reference: string }>).map(([col, e]) =>
              `Each ${col}= row is compared with ${col} = ${e.reference}`).join('. ')}.
          </p>
        )}
        {active === 'resid' && <MiniScatter points={data.diagnostics?.residuals ?? []} xLabel="fitted" yLabel="residual" refLine="zero" />}
        {active === 'ap' && <MiniScatter points={data.diagnostics?.actual_predicted ?? []} xLabel={`actual ${data.target}`} yLabel="predicted" refLine="identity" />}
        {active === 'cm' && data.diagnostics?.confusion && <Confusion c={data.diagnostics.confusion} />}
        {active === 'roc' && <>
          <MiniScatter points={data.diagnostics?.roc ?? []} xLabel="false positive rate" yLabel="true positive rate" refLine="identity" />
          <p style={{ fontSize: 10, color: 'var(--muted)' }}>The dashed diagonal is a coin toss (AUC 0.5).</p>
        </>}
        {active === 'rocs' && <RocOverlay models={(data.models ?? []).filter((m: any) => Array.isArray(m.roc))} winner={data.winner} />}
        {active === 'imp' && <Bars rows={(data.rows ?? []).map((x: any) => ({ name: x.name, value: x.value }))} />}
        {active === 'rules' && <TreeOutline node={r.tree} />}
        {active === 'pred' && <>
          <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>
            {data.measure}{data.breakdown ? ` by ${data.breakdown}` : ''}
          </div>
          <Bars rows={(data.rows ?? []).map((x: any) => ({ name: x.name, value: x.value }))} percent={data.value_format === 'percent'} />
          {data.unseen_values && Object.keys(data.unseen_values).length > 0 && (
            <p role="note" style={{ fontSize: 10.5, color: 'var(--muted)', margin: '6px 0 0' }}>
              Values the model never saw in training (scored as if absent): {Object.entries(data.unseen_values as Record<string, string[]>)
                .map(([c, v]) => `${c}: ${v.slice(0, 5).join(', ')}${v.length > 5 ? '…' : ''}`).join('; ')}
            </p>
          )}
        </>}
        {active === 'seg' && (
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead><tr><th style={th}>Segment</th><th style={{ ...th, textAlign: 'end' }}>Rows</th>
              {(data.variables ?? []).map((v: string) => <th key={v} style={{ ...th, textAlign: 'end' }}>avg {v}</th>)}</tr></thead>
            <tbody>
              {(r.meta?.centroids ?? []).map((c: any) => (
                <tr key={c.cluster}><td style={td}>Segment {c.cluster + 1}</td><td style={tdn}>{Number(c.size).toLocaleString()}</td>
                  {(data.variables ?? []).map((v: string) => <td key={v} style={tdn}>{fmt(c[v])}</td>)}</tr>
              ))}
            </tbody>
          </table>
        )}
        {active === 'verdict' && (
          <Bars rows={(data.models ?? []).map((m: any) => ({ id: m.id, name: m.title, value: m.score }))}
            accentId={data.winner}
            baseline={data.baseline ? { label: data.baseline.note, value: data.baseline.score } : undefined} />
        )}
        {active === 'verdict' && (data.models ?? []).some((m: any) => m.note) && (
          <ul style={{ margin: '6px 0 0', paddingInlineStart: 18, color: 'var(--muted)', fontSize: 11 }}>
            {(data.models ?? []).filter((m: any) => m.note).map((m: any, i: number) => <li key={i}>{m.title}: {m.note}</li>)}
          </ul>
        )}
        {active === 'verdict' && data.population?.test_rows != null && (
          <p style={{ fontSize: 10, color: 'var(--muted)', margin: '6px 0 0' }}>
            Every model refitted on the same {Number(data.population.train_rows).toLocaleString()} rows and scored on the
            same {Number(data.population.test_rows).toLocaleString()} rows it never saw.
          </p>
        )}
        {active === 'rlist' && ((data.rules ?? []).length
          ? <RuleTable rules={data.rules} />
          : <p style={{ fontSize: 12, color: 'var(--muted)' }}>{tr('mdl.r.none')}</p>)}
        {active === 'lift' && (
          <div data-testid="lift-chart" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {(() => {
              const rules: any[] = data.rules ?? []
              const max = Math.max(...rules.map(x => Number(x.lift) || 0), 1)
              // The rule on its own line above its bar: beside it, a third of
              // the width cut every rule to "…rketing ← title = Staff".
              return rules.map((x, i) => (
                <div key={i} style={{ fontSize: 11.5 }}>
                  {/* Three pieces in the PAGE's direction, each side isolated:
                      as one dir="auto" string an English rule ran left to
                      right and the RTL arrow pointed from Then back to If. */}
                  <div style={{ marginBottom: 2, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                    <bdi>{sideText(x.if_items, x.if)}</bdi>
                    <b aria-hidden>{navArrows(rtl).forward}</b>
                    <bdi>{sideText(x.then_items, x.then)}</bdi>
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr max-content', gap: 6, alignItems: 'center' }}>
                    <div style={{ background: 'var(--surface2)', borderRadius: 4, height: 10 }}>
                      <div style={{ width: `${(Number(x.lift) / max) * 100}%`, height: '100%', borderRadius: 4,
                        background: 'color-mix(in srgb, var(--muted) 45%, transparent)' }} />
                    </div>
                    <span style={{ fontVariantNumeric: 'tabular-nums', fontWeight: 600 }}>{fmt(x.lift, 2)}×</span>
                  </div>
                </div>
              ))
            })()}
          </div>
        )}
        {active === 'rfit' && (
          <div style={{ fontSize: 12, display: 'flex', flexDirection: 'column', gap: 6 }}>
            <div>{tr('mdl.r.strongest')}: <b>{fit?.value != null ? `${fmt(fit.value, 2)}×` : '—'}</b> · {tr('mdl.r.found', { n: (data.rules ?? []).length })}</div>
            {data.banded && Object.keys(data.banded).length > 0 && (
              <div>{tr('mdl.r.bands')} {Object.keys(data.banded).join(', ')}</div>
            )}
            <div style={{ color: 'var(--muted)', fontSize: 11 }}>
              {tr('mdl.r.limits', { s: String(r.meta?.params?.min_support_rows ?? 20), l: String(r.meta?.params?.min_lift ?? 1.2) })}
            </div>
            <div style={{ color: 'var(--muted)', fontSize: 11 }}>{tr('mdl.r.hint')}</div>
          </div>
        )}
        {active === 'fit' && fit && (
          <div style={{ fontSize: 12, display: 'flex', flexDirection: 'column', gap: 4 }}>
            <div>{fit.name}: <b>{fmt(fit.value)}</b>{effect}</div>
            {Object.entries(fit.secondary ?? {}).map(([k, v]) => <div key={k}>{k}: <b>{fmt(v)}</b></div>)}
            {caveats.length > 0 && (
              <ul style={{ margin: '6px 0 0', paddingInlineStart: 18, color: 'var(--muted)', fontSize: 11 }}>
                {caveats.map((c, i) => <li key={i}>{c}</li>)}
              </ul>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
