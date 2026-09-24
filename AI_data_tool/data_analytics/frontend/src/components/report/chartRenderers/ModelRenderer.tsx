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
import type { ChartRendererProps } from './types'

type Tab = { key: string; label: string }

const fmt = (v: unknown, digits = 3) => {
  if (v === null || v === undefined || v === '') return '—'
  const n = Number(v)
  if (!Number.isFinite(n)) return String(v)
  const a = Math.abs(n)
  return a !== 0 && (a < 0.001 || a >= 1e6) ? n.toExponential(2) : n.toLocaleString(undefined, { maximumFractionDigits: digits })
}
const pfmt = (p: unknown) => (p == null ? '—' : Number(p) < 0.001 ? '< 0.001' : fmt(p, 3))

const MODEL_NAMES: Record<string, string> = {
  linear: 'Linear regression', logistic: 'Logistic regression', tree: 'Decision tree',
  cluster: 'Clustering', compare: 'Model comparison', score: 'Scoring',
}

function Population({ pop }: { pop: any }) {
  if (!pop) return null
  const dropped = Object.entries(pop.dropped_by ?? {}) as [string, number][]
  return (
    <div data-testid="model-population" style={{ fontSize: 11, color: 'var(--muted)' }}>
      Rows used: <b style={{ color: 'var(--text)' }}>{Number(pop.rows_used ?? 0).toLocaleString()}</b> of {Number(pop.rows_total ?? 0).toLocaleString()}
      {pop.rows_dropped > 0 && <> — {Number(pop.rows_dropped).toLocaleString()} dropped{dropped.length > 0 && <> (missing: {dropped.map(([c, n]) => `${c} ${n.toLocaleString()}`).join(', ')})</>}</>}
      {pop.rows_before_filters != null && <> · re-fitted on the filtered rows ({Number(pop.rows_before_filters).toLocaleString()} before filters)</>}
      {pop.sampled_from && <> · clustered a sample of {Number(pop.sampled_from).toLocaleString()} rows</>}
      {pop.partition
        ? <> · partition <b style={{ color: 'var(--text)' }}>{pop.partition.column}</b>: trained on {Number(pop.partition.train_rows).toLocaleString()}, validated on {Number(pop.partition.validation_rows).toLocaleString()}</>
        : pop.test_rows != null && <> · scored on {Number(pop.test_rows).toLocaleString()} held-out rows</>}
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
      style={{ width: '100%', maxHeight: 220, color: 'var(--accent)' }}>
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

const ROC_COLORS = ['var(--accent)', '#e67e22', '#8e44ad', '#16a085', '#c0392b', '#2c3e50']

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
          <polyline key={m.id ?? i} fill="none" stroke={ROC_COLORS[i % ROC_COLORS.length]}
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
            <span aria-hidden style={{ width: 14, height: 3, background: ROC_COLORS[i % ROC_COLORS.length], display: 'inline-block' }} />
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
  return (
    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
      <thead><tr>
        <th style={th}>Term</th>
        <th style={{ ...th, textAlign: 'end' }}>{odds ? 'Odds ratio' : 'Coefficient'}</th>
        <th style={{ ...th, textAlign: 'end' }}>95% CI</th>
        <th style={{ ...th, textAlign: 'end' }}>p</th>
      </tr></thead>
      <tbody>
        {coefs.map(c => (
          <tr key={c.term} style={{ fontWeight: c.significant && c.term !== 'const' ? 600 : 400 }}>
            <td style={td}>{c.term === 'const' ? '(intercept)' : c.term}{c.significant && c.term !== 'const' ? ' ✱' : ''}</td>
            <td style={tdn}>{fmt(odds ? c.odds_ratio : c.coefficient)}</td>
            <td style={tdn}>{odds ? `${fmt(c.or_ci_low)} – ${fmt(c.or_ci_high)}` : `${fmt(c.ci_low)} – ${fmt(c.ci_high)}`}</td>
            <td style={tdn}>{pfmt(c.p_value)}</td>
          </tr>
        ))}
      </tbody>
      <caption style={{ captionSide: 'bottom', textAlign: 'start', fontSize: 10, color: 'var(--muted)', paddingTop: 4 }}>
        ✱ significant at 5%.{odds ? ' An odds ratio of 1.4 means 40% higher odds of the event per unit.' : ''}
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
  const show = (v: number | null) => percent && v != null ? `${(v * 100).toFixed(1)}%` : fmt(v)
  const vals = rows.map(r => r.value ?? 0).concat(baseline ? [baseline.value] : [])
  const max = Math.max(...vals, 0) || 1
  const min = Math.min(...vals, 0)
  const span = max - min || 1
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      {rows.map((r, i) => (
        <div key={i} style={{ display: 'grid', gridTemplateColumns: 'minmax(80px, 30%) 1fr 56px', gap: 6, alignItems: 'center', fontSize: 12 }}>
          <span title={r.name} style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.name}</span>
          <div style={{ background: 'var(--surface2)', borderRadius: 4, height: 14, position: 'relative' }}>
            <div style={{ position: 'absolute', insetInlineStart: `${((Math.min(0, r.value ?? 0) - min) / span) * 100}%`, width: `${(Math.abs(r.value ?? 0) / span) * 100}%`, height: '100%', borderRadius: 4,
              background: accentId !== undefined && r.id === accentId ? 'var(--accent)' : 'color-mix(in srgb, var(--muted) 45%, transparent)' }} />
          </div>
          <span style={{ textAlign: 'end', fontVariantNumeric: 'tabular-nums' }}>{show(r.value)}</span>
        </div>
      ))}
      {baseline && (
        <div style={{ fontSize: 11, color: 'var(--muted)' }}>Baseline — {baseline.label}: {fmt(baseline.value)}</div>
      )}
    </div>
  )
}

export default function ModelRenderer({ data }: ChartRendererProps) {
  const [tab, setTab] = useState<string | null>(null)
  if (!data || data.type !== 'model') return null
  if (data.status === 'refused') {
    return (
      <div role="note" style={{ padding: 12, fontSize: 13, display: 'flex', flexDirection: 'column', gap: 8 }}>
        <b>This model could not be fitted</b>
        <span>{data.reason}</span>
        <Population pop={data.population} />
      </div>
    )
  }
  if (data.status !== 'ok') return null

  const r = data.result ?? {}
  const kind: string = data.model
  const tabs: Tab[] = kind === 'linear' ? [{ key: 'coef', label: 'Coefficients' }, { key: 'resid', label: 'Residuals' }, { key: 'ap', label: 'Actual vs predicted' }, { key: 'fit', label: 'Fit' }]
    : kind === 'logistic' ? [{ key: 'coef', label: 'Odds ratios' }, { key: 'cm', label: 'Confusion matrix' }, { key: 'roc', label: 'ROC' }, { key: 'fit', label: 'Fit' }]
    : kind === 'tree' ? [{ key: 'imp', label: 'Importance' }, { key: 'rules', label: 'Rules' }, { key: 'fit', label: 'Fit' }]
    : kind === 'cluster' ? [{ key: 'seg', label: 'Segments' }, { key: 'fit', label: 'Fit' }]
    : kind === 'score' ? [{ key: 'pred', label: 'Predictions' }, { key: 'fit', label: 'Check' }]
    : (data.models ?? []).some((m: any) => Array.isArray(m.roc))
      ? [{ key: 'verdict', label: 'Verdict' }, { key: 'rocs', label: 'ROC' }]
      : [{ key: 'verdict', label: 'Verdict' }]
  const active = tab && tabs.some(t => t.key === tab) ? tab : tabs[0].key
  const formula = kind === 'cluster' ? (data.variables ?? []).join(', ')
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
          <b>{MODEL_NAMES[kind] ?? 'Model'}</b> <span style={{ color: 'var(--muted)' }}>· {formula}</span>
        </div>
        {fit && kind !== 'compare' && (
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
              ? <>Winner: <b style={{ color: 'var(--accent)' }}>{(data.models ?? []).find((m: any) => m.id === data.winner)?.title}</b>
                  {data.winner_beats_baseline ? '' : <span style={{ color: 'var(--danger, #c0392b)' }}> — but it does not beat just guessing</span>}</>
              : 'No model could be scored.'}
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

      <div role="tabpanel" style={{ flex: 1, minHeight: 0, overflow: 'auto' }}>
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
