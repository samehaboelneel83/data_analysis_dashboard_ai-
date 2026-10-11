/**
 * The result views two screens share.
 *
 * `ExplainDialog` drew the importance bars, the relationship plot and the
 * goal-seek answer inline, because it was the only thing that could reach
 * either analysis. Both are now in the catalogue and runnable from the generic
 * analysis panel, so the same numbers arrive at two screens — and two
 * hand-drawn copies of a chart are two charts that drift.
 *
 * These are presentation only: no fetching, no state. The dialog keeps its own
 * goal-seek FORM (target, bounds, Solve) because that form is the dialog's
 * interaction; the panel builds its inputs from the schema instead. What they
 * share is how an answer LOOKS.
 */
import type { KeyInfluencersResult as KeyInfluencersPayload, StatisticalTestResult } from '../../services/api'
import KeyInfluencersResult from './KeyInfluencersResult'
import { useDirection } from '../../contexts/DirectionContext'
import { majorityDir } from '../../lib/autoDir'
import { useT, type MessageKey, type TranslateFn } from '../../i18n'
import { sayText, type SaidI18n } from '../../lib/readbackText'
import SaidItems, { saidOf } from './SaidItems'
import { rich } from '../../i18n/pages/modelsMaps'

export interface Factor {
  column: string
  kind: string
  score: number
  relative: number
  direction?: string
}

export interface Relationship {
  kind: string
  column: string
  points?: { x: number; y: number }[]
  groups?: { name: string; mean: number }[]
}

export interface GoalSeekResult {
  required_x: number
  r2?: number | null
  within_observed_range?: boolean
  within_bounds?: boolean
  bound_x?: number
  achievable_y?: number
}

export function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      fontSize: 11, fontWeight: 700, color: 'var(--muted)',
      textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 6,
    }}>{children}</div>
  )
}

/**
 * Relative importance, on SAS's scale: the top factor is 1 and the rest are
 * proportional to it. Categorical factors are drawn at lower opacity because
 * they are scored a different way (√eta² rather than |Pearson r|) even though
 * the scale is comparable.
 */
export function FactorBars({ factors }: { factors: Factor[] }) {
  const t = useT()
  return (
    <ul style={{
      listStyle: 'none', display: 'flex', flexDirection: 'column',
      gap: 4, marginBottom: 14,
    }}>
      {factors.map(f => (
        <li key={f.column} style={{
          display: 'flex', alignItems: 'center', gap: 8, fontSize: 11,
        }}>
          <span style={{
            width: 130, flexShrink: 0, whiteSpace: 'nowrap',
            overflow: 'hidden', textOverflow: 'ellipsis',
          }}>
            {f.column}{f.direction === '-' ? ` ${t('res.fb.inverse')}` : ''}
          </span>
          <span data-testid={`bar-${f.column}`} style={{
            height: 10, borderRadius: 3, background: 'var(--accent)',
            width: `${Math.max(2, f.relative * 100)}%`,
            opacity: f.kind === 'category' ? 0.7 : 1,
          }} />
          <span style={{ color: 'var(--muted)', flexShrink: 0 }}>
            {f.relative.toFixed(2)}
          </span>
        </li>
      ))}
    </ul>
  )
}

/** The top factor's relationship: a scatter for numeric, group means for
 *  categorical. Hand-drawn SVG rather than a chart library — it is a hundred
 *  points with no axes, and pulling Recharts into a dialog for it would cost
 *  more than it explains. */
export function RelationshipPlot({ rel }: { rel: Relationship }) {
  if (rel.kind === 'scatter' && rel.points?.length) {
    const xs = rel.points.map(p => p.x), ys = rel.points.map(p => p.y)
    const [x0, x1] = [Math.min(...xs), Math.max(...xs)]
    const [y0, y1] = [Math.min(...ys), Math.max(...ys)]
    const sx = (x: number) => 6 + 488 * ((x - x0) / Math.max(x1 - x0, 1e-9))
    const sy = (y: number) => 154 - 148 * ((y - y0) / Math.max(y1 - y0, 1e-9))
    return (
      <svg data-testid="explain-scatter" viewBox="0 0 500 160" style={{
        width: '100%', border: '1px solid var(--border)', borderRadius: 6,
      }}>
        {rel.points.map((p, i) => (
          <circle key={i} cx={sx(p.x)} cy={sy(p.y)} r={2}
            fill="var(--accent)" fillOpacity={0.55} />
        ))}
      </svg>
    )
  }
  if (rel.kind === 'group_means' && rel.groups?.length) {
    const max = Math.max(...rel.groups.map(g => Math.abs(g.mean)), 1e-9)
    return (
      <ul data-testid="explain-groups" style={{
        listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 3,
      }}>
        {rel.groups.map(g => (
          <li key={g.name} style={{
            display: 'flex', alignItems: 'center', gap: 8, fontSize: 11,
          }}>
            <span style={{
              width: 130, flexShrink: 0, whiteSpace: 'nowrap',
              overflow: 'hidden', textOverflow: 'ellipsis',
            }}>{g.name}</span>
            <span style={{
              height: 9, borderRadius: 3, background: 'var(--accent)',
              opacity: 0.8,
              width: `${Math.max(2, Math.abs(g.mean) / max * 100)}%`,
            }} />
            <span style={{ color: 'var(--muted)', flexShrink: 0 }}>
              {g.mean.toLocaleString()}
            </span>
          </li>
        ))}
      </ul>
    )
  }
  return null
}

/**
 * The answer, and the two things that qualify it.
 *
 * A goal outside the observed data is an extrapolation and says so; a goal
 * outside the caller's own bounds is unreachable, and reports the best value
 * actually achievable at the binding bound — the number a constrained solver
 * optimises to. Both are the difference between an answer and a confident
 * number, so neither is optional.
 */
export function GoalSeekAnswer({ xName, yName, goal }: {
  xName: string; yName: string; goal: GoalSeekResult
}) {
  const t = useT()
  return (
    <p data-testid="goal-result" style={{ fontSize: 12, marginTop: 6 }}>
      {rich(t, 'res.gs.need', { x: xName, v: <strong>{goal.required_x.toLocaleString()}</strong> })}
      {goal.r2 != null && (
        <span style={{ color: 'var(--muted)' }}> {t('res.gs.fit', { r2: goal.r2.toFixed(2) })}</span>
      )}
      {goal.within_observed_range === false && (
        <span style={{ display: 'block', color: '#e6a03c', fontSize: 11 }}>
          {t('res.gs.outside', { x: xName })}
        </span>
      )}
      {goal.within_bounds === false && (
        <span data-testid="goal-infeasible" style={{
          display: 'block', color: 'var(--danger)', fontSize: 11,
        }}>
          {rich(t, 'res.gs.unreachable', { x: xName, bound: goal.bound_x?.toLocaleString() ?? '', y: yName,
            best: <strong>{goal.achievable_y?.toLocaleString()}</strong> })}
        </span>
      )}
    </p>
  )
}


/**
 * The right view for a result kind, and a real one for a kind nobody has
 * written a view for yet.
 *
 * The fallback is the load-bearing case. A catalogue-driven screen only pays
 * for itself if a newly registered analysis appears without frontend work; if
 * an unrecognised kind rendered blank, every new analysis would still need an
 * edit here — and the failure would be silent, a Run that succeeds and shows
 * nothing.
 */
export function ResultFor({ kind, result, params }: {
  kind: string; result: unknown; params: Record<string, unknown>
}) {
  const t = useT()
  if (kind === 'statistical_test') {
    return <ResultCard result={result as StatisticalTestResult} />
  }
  if (kind === 'explanation') {
    const r = result as {
      factors: Factor[]; relationship: Relationship | null; note: string | null
    }
    return (
      <div className="card" style={{ padding: 18 }}>
        {r.note && <p style={{ fontSize: 12, color: 'var(--muted)' }}>{r.note}</p>}
        {r.factors?.length > 0 && (
          <>
            <SectionLabel>{t('res.er.importance')}</SectionLabel>
            <FactorBars factors={r.factors} />
          </>
        )}
        {r.relationship && (
          <>
            <SectionLabel>{t('res.er.top', { c: r.relationship.column })}</SectionLabel>
            <RelationshipPlot rel={r.relationship} />
          </>
        )}
      </div>
    )
  }
  if (kind === 'goal_seek') {
    // The parameters are what name the two columns; the result carries the
    // numbers but not what they are about, and "would need to be ≈ 812" is
    // unreadable without knowing what would.
    return (
      <div className="card" style={{ padding: 18 }}>
        <SectionLabel>{t('res.gs.title')}</SectionLabel>
        <GoalSeekAnswer goal={result as GoalSeekResult}
          xName={String(params.x_column ?? t('res.gs.factor'))}
          yName={String(params.y_column ?? t('res.gs.outcome'))} />
      </div>
    )
  }
  if (kind === 'compare_scenarios' && Array.isArray((result as CompareScenariosResult | null)?.table)) {
    return <CompareScenarios result={result as CompareScenariosResult} />
  }
  if (kind === 'forecast_scenario') {
    return <ForecastScenario result={result as ScenarioResult} />
  }
  if (kind === 'text_topics') {
    return <TextTopics result={result as TextTopicsResult} />
  }
  if (kind === 'text_sentiment') {
    return <TextSentiment result={result as TextSentimentResult} />
  }
  if (kind === 'automated_prediction') {
    return <AutomatedPrediction result={result as PredictionResult} />
  }
  if (kind === 'cohort_retention' && (result as CohortRetentionPayload | null)?.meta?.curve) {
    return <CohortRetention result={result as CohortRetentionPayload} />
  }
  if (kind === 'simulate_scenarios' && Array.isArray((result as SimulateScenariosResult | null)?.table)) {
    return <SimulateScenarios result={result as SimulateScenariosResult} />
  }
  if (kind === 'stage_board' && (result as StageBoardPayload | null)?.meta?.stage_col) {
    return <StageBoard result={result as StageBoardPayload} />
  }
  if (kind === 'two_groups' && (result as TwoGroupsPayload | null)?.meta?.verdict) {
    return <TwoGroups result={result as TwoGroupsPayload} />
  }
  if (kind === 'change_drivers' && (result as ChangeDriversPayload | null)?.meta?.factors) {
    return <ChangeDrivers result={result as ChangeDriversPayload} />
  }
  if (kind === 'decision_tree') {
    return <DecisionTree result={result as DecisionTreeResult} />
  }
  if (kind === 'key_influencers' && Array.isArray((result as KeyInfluencersPayload | null)?.rows)
      && (result as KeyInfluencersPayload).meta) {
    return <KeyInfluencersResult result={result as KeyInfluencersPayload} />
  }
  return <GenericResult kind={kind} result={result} />
}

/**
 * Whatever came back, shown honestly.
 *
 * Scalars become a labelled stat, arrays of objects become a table, and
 * anything left over is pretty-printed rather than stringified into
 * "[object Object]".
 */
function GenericResult({ kind, result }: { kind: string; result: unknown }) {
  if (result == null || typeof result !== 'object') {
    return (
      <div className="card" style={{ padding: 18 }}>
        <p style={{ fontSize: 13, margin: 0 }}>{String(result)}</p>
      </div>
    )
  }
  const entries = Object.entries(result as Record<string, unknown>)
    // An empty list or object is the analysis saying "not applicable here" --
    // segment fills `columns` and `meta` and leaves `rows` empty. Printing
    // "ROWS []" spends a heading on the absence of an answer.
    .filter(([, v]) => !(Array.isArray(v) && v.length === 0))
    .filter(([, v]) => !(v != null && typeof v === 'object' && !Array.isArray(v)
                         && Object.keys(v as object).length === 0))
    // `kind` restates the heading directly above it.
    .filter(([k, v]) => !(k === 'kind' && v === kind))

  const scalars = entries.filter(([, v]) => v == null || typeof v !== 'object')
  const tables = entries.filter(([, v]) =>
    Array.isArray(v) && v.length > 0 && typeof v[0] === 'object' && v[0] !== null)
  const rest = entries.filter(
    ([k]) => !scalars.some(([s]) => s === k) && !tables.some(([t]) => t === k))

  return (
    <div className="card" style={{ padding: 18 }}>
      <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 6 }}>
        {kind.replace(/_/g, ' ')}
      </div>

      {scalars.length > 0 && (
        <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', margin: '14px 0' }}>
          {scalars.map(([k, v]) => (
            <div key={k}>
              <div style={{ fontSize: 11, color: 'var(--muted)' }}>
                {k.replace(/_/g, ' ')}
              </div>
              <div style={{
                fontFamily: 'var(--mono)', fontSize: 18,
                fontVariantNumeric: 'tabular-nums',
              }}>{v == null ? '—' : String(v)}</div>
            </div>
          ))}
        </div>
      )}

      {tables.map(([k, v]) => (
        <div key={k} style={{ margin: '12px 0' }}>
          <SectionLabel>{k.replace(/_/g, ' ')}</SectionLabel>
          <RowTable rows={v as Record<string, unknown>[]} />
        </div>
      ))}

      {rest.map(([k, v]) => (
        <div key={k} style={{ margin: '12px 0' }}>
          <SectionLabel>{k.replace(/_/g, ' ')}</SectionLabel>
          <pre style={{
            fontSize: 11, fontFamily: 'var(--mono)', overflowX: 'auto',
            background: 'var(--bg)', padding: 8, borderRadius: 4, margin: 0,
          }}>{JSON.stringify(v, null, 2)}</pre>
        </div>
      ))}
    </div>
  )
}

/** An array of objects as a table, columns taken from the rows themselves. */
function RowTable({ rows }: { rows: Record<string, unknown>[] }) {
  const keys = Array.from(new Set(rows.flatMap(r => Object.keys(r))))
  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse' }}>
        <thead>
          <tr>
            {keys.map(k => (
              <th key={k} style={{
                textAlign: 'start', padding: '4px 8px',
                borderBottom: '1px solid var(--border)',
                fontSize: 11, color: 'var(--muted)', whiteSpace: 'nowrap',
              }}>{k.replace(/_/g, ' ')}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>
              {keys.map(k => (
                <td key={k} style={{
                  padding: '4px 8px', borderBottom: '1px solid var(--border)',
                  fontFamily: 'var(--mono)', fontVariantNumeric: 'tabular-nums',
                  whiteSpace: 'nowrap',
                }}>{row[k] == null ? '—' : String(row[k])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/**
 * The shared envelope, rendered once.
 *
 * The EFFECT SIZE is given at least the weight of the p-value, deliberately.
 * With a two-million-row import cap a p-value alone is nearly content-free —
 * at large n almost any difference reaches significance — so a card that led
 * with the asterisk would be a machine for manufacturing confident trivia.
 */
function ResultCard({ result }: { result: StatisticalTestResult }) {
  const coefficients = (result.detail?.coefficients as Record<string, unknown>[]) ?? null
  const test = (result.detail?.test as string) ?? result.kind
  const { direction } = useDirection()
  const tStat = useT()

  return (
    <div className="card" style={{ padding: 18 }}>
      <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 6 }}>{test}</div>
      <p dir={majorityDir(result.interpretation, direction)} style={{ fontSize: 14, fontWeight: 500, marginTop: 0 }}>{result.interpretation}</p>

      <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', margin: '14px 0' }}>
        <Stat label={result.effect_name.replace(/_/g, ' ')}
          value={result.effect_size} suffix={` · ${result.effect_label}`} />
        <Stat label={tStat('res.st.p')} value={pText(result.p_value)} />
        <Stat label={tStat('res.st.rows')} value={result.n} />
      </div>

      {coefficients && (
        <div style={{ margin: '12px 0' }}>
          <RowTable rows={coefficients} />
        </div>
      )}

      {/* Caveats are part of the answer, not a footnote: "correlation is not
          causation", "this assumes proportional hazards", "computed on a
          sample". A reader who acts on the number without them is misled. */}
      {result.caveats.length > 0 && (
        <ul style={{ fontSize: 11, color: 'var(--muted)', margin: '10px 0 0', paddingInlineStart: 18 }}>
          <SaidItems texts={result.caveats} i18n={saidOf(result)} />
        </ul>
      )}
    </div>
  )
}

/** A p-value is never exactly 0; "0" read as certainty. Below 0.001 it says so. */
export function pText(p: number | null): string | null {
  if (p == null) return null
  return p < 0.001 ? '< 0.001' : String(p)
}

function Stat({ label, value, suffix }: {
  label: string; value: number | string | null; suffix?: string
}) {
  return (
    <div>
      <div style={{ fontSize: 11, color: 'var(--muted)' }}>{label}</div>
      <div style={{
        fontFamily: 'var(--mono)', fontSize: 18, fontVariantNumeric: 'tabular-nums',
      }}>
        {value == null ? '—' : value}
        {suffix && <span style={{ fontSize: 12, color: 'var(--muted)' }}>{suffix}</span>}
      </div>
    </div>
  )
}


/** A fitted decision tree, as returned by `services/analysis/decision_tree.py`. */
export interface TreeNode {
  label: string | null
  feature: string | null
  samples: number
  prediction: string | number | null
  confidence: number | null
  children: TreeNode[]
}

export interface DecisionTreeResult {
  task: 'classification' | 'regression'
  target: string
  tree: TreeNode
  importance: { column: string; importance: number }[]
  predictors_used: string[]
  predictors_skipped: { column: string; reason: string }[]
  score: number
  score_name: string
  train_score: number
  n_train: number
  n_test: number
  max_depth: number
  caveats: string[]
}

/**
 * The branches as an indented list.
 *
 * A tree pretty-printed as JSON contains the same information and answers
 * nothing — the value of a tree over a coefficient is that a person can read a
 * branch aloud, and that only survives if the splits are laid out as splits.
 *
 * Indentation rather than a drawn diagram, deliberately: a depth-4 tree has up
 * to sixteen leaves, an SVG of that needs panning and zooming to read, and the
 * list degrades gracefully into a narrow widget where a diagram does not.
 */
function DecisionTree({ result }: { result: DecisionTreeResult }) {
  const t = useT()
  return (
    <div className="card" style={{ padding: 18 }}>
      <SectionLabel>
        {t(result.task === 'classification' ? 'res.dt.classifying' : 'res.dt.predicting', { t: result.target })}
      </SectionLabel>

      {/* Both scores, always. One of them alone is not an assessment: a tree
          deep enough reproduces its training rows exactly. */}
      <div data-testid="tree-score" style={{
        display: 'flex', gap: 20, flexWrap: 'wrap', margin: '4px 0 14px',
      }}>
        <Stat label={t('res.dt.heldOut', { score: result.score_name })} value={result.score}
          suffix={` · ${t('res.nRows', { n: result.n_test })}`} />
        <Stat label={t('res.dt.training')} value={result.train_score}
          suffix={` · ${t('res.nRows', { n: result.n_train })}`} />
      </div>

      <TreeBranch node={result.tree} depth={0} />

      {result.importance?.length > 0 && (
        <div style={{ marginTop: 14 }}>
          <SectionLabel>{t('res.dt.splits')}</SectionLabel>
          <FactorBars factors={result.importance.map(i => ({
            column: i.column, kind: 'numeric', score: i.importance,
            relative: result.importance[0].importance
              ? i.importance / result.importance[0].importance : 0,
          }))} />
        </div>
      )}

      {/* Named, not omitted: a column missing from the importance list above
          otherwise reads as "considered and found unimportant". */}
      {result.predictors_skipped?.length > 0 && (
        <div style={{ fontSize: 10.5, color: 'var(--muted)', marginTop: 6 }}>
          {t('res.dt.notUsed', { list: result.predictors_skipped.map(s => `${s.column} (${s.reason})`).join('; ') })}
        </div>
      )}

      {result.caveats?.length > 0 && (
        <ul style={{ fontSize: 11, color: 'var(--muted)', margin: '10px 0 0',
                     paddingInlineStart: 18 }}>
          <SaidItems texts={result.caveats} i18n={saidOf(result)} />
        </ul>
      )}
    </div>
  )
}

function TreeBranch({ node, depth }: { node: TreeNode; depth: number }) {
  const t = useT()
  const leaf = !node.children?.length
  return (
    <>
      <div data-testid="tree-node" style={{
        display: 'flex', alignItems: 'baseline', gap: 8, fontSize: 11.5,
        paddingInlineStart: depth * 16, lineHeight: 1.7,
        borderInlineStart: depth ? '1px solid var(--border)' : undefined,
      }}>
        <span style={{ fontFamily: 'var(--mono)' }}>
          {leaf ? '→' : '├'} {node.label ?? String(node.prediction)}
        </span>
        <span style={{ color: 'var(--muted)', fontSize: 10.5 }}>
          {t('res.nRows', { n: node.samples.toLocaleString() })}
          {leaf && node.confidence != null &&
            ` · ${Math.round(node.confidence * 100)}% ${node.prediction}`}
          {leaf && node.confidence == null && ` · ${node.prediction}`}
        </span>
      </div>
      {(node.children ?? []).map((child, i) => (
        <TreeBranch key={i} node={child} depth={depth + 1} />
      ))}
    </>
  )
}


export interface PredictionCandidate {
  model: string
  score: number | null
  train_score: number | null
  is_baseline: boolean
  error: string | null
}

export interface PredictionResult {
  task: 'classification' | 'regression'
  target: string
  score_name: string
  candidates: PredictionCandidate[]
  champion: PredictionCandidate
  baseline_score: number | null
  lift_over_baseline: number | null
  beats_baseline: boolean
  n_train: number
  n_test: number
  /** How the held-back rows were chosen: a random share, or a named partition column. */
  split?: { kind: 'random'; test_share: number } | { kind: 'partition'; column: string }
  predictors_skipped: { column: string; reason: string }[]
  /** What the winner leans on: the fall in score when a column is shuffled. */
  importance?: { column: string; drop: number; spread: number; matters: boolean }[]
  importance_of?: string | null
  importance_note?: string | null
  importance_note_i18n?: SaidI18n | null
  caveats: string[]
}

export interface CompareScenariosResult {
  measure: string; horizon: number; r2: number; series: string[]
  table: { scenario: string; baseline: boolean; total: number; vs_baseline: number; vs_baseline_pct: number | null; extrapolating: boolean }[]
  chart: Record<string, number | string>[]
  highest: string; lowest: string; gap: number; gap_pct: number | null; caveats: string[]; weak_fit?: boolean
  caveats_i18n?: (SaidI18n | null)[]
}

/** Scenarios side by side: totals against the projection with nothing moved, then period by period. */
function CompareScenarios({ result }: { result: CompareScenariosResult }) {
  const t = useT()
  const n = (v: number) => v.toLocaleString(undefined, { maximumFractionDigits: Math.abs(v) >= 100 ? 0 : 2 })
  const signed = (v: number) => `${v > 0 ? '+' : ''}${n(v)}`
  // The projection with nothing moved is named by the server in English.
  const name = (sc: string) => sc === 'Nothing moved' ? t('res.sc.none') : sc
  const caveat = (i: number) => sayText(t, result.caveats[i], result.caveats_i18n?.[i])
  return (
    <div className="card" style={{ padding: 18 }}>
      <SectionLabel>{t('res.sc.title', { m: result.measure })}</SectionLabel>
      {result.weak_fit && result.caveats?.[0] && (
        <div role="alert" data-testid="scenarios-weak" style={{ fontSize: 12, padding: '6px 10px', borderRadius: 6, margin: '4px 0 8px',
          background: 'var(--surface2)', color: 'var(--danger)' }}>{caveat(0)}</div>
      )}
      <div data-testid="scenarios-headline" style={{ fontSize: 13, margin: '4px 0 10px' }}>
        {t('res.sc.head', { n: result.horizon, hi: name(result.highest), lo: name(result.lowest), gap: n(result.gap),
          pct: result.gap_pct != null ? t('res.sc.headpct', { p: result.gap_pct.toFixed(1) }) : '' })}
      </div>
      <table style={{ fontSize: 12, borderCollapse: 'collapse', width: '100%' }}>
        <thead><tr style={{ color: 'var(--muted)', textAlign: 'start' }}>
          <th style={{ textAlign: 'start', padding: '2px 8px 2px 0' }}>{t('res.sc.scenario')}</th>
          <th style={{ textAlign: 'end', padding: '2px 8px' }}>{t('res.sc.total')}</th>
          <th style={{ textAlign: 'end', padding: '2px 8px' }}>{t('res.sc.vs')}</th>
        </tr></thead>
        <tbody>
          {result.table.map(r => (
            <tr key={r.scenario} data-testid="scenario-row" style={{ borderTop: '1px solid var(--border)' }}>
              <td style={{ padding: '3px 8px 3px 0' }}><bdi>{name(r.scenario)}</bdi>
                {r.extrapolating && <span title={t('res.sc.beyondTip')} style={{ color: 'var(--danger)' }}> · {t('res.sc.beyond')}</span>}</td>
              <td dir="ltr" style={{ textAlign: 'end', padding: '3px 8px', fontVariantNumeric: 'tabular-nums' }}>{n(r.total)}</td>
              <td dir="ltr" style={{ textAlign: 'end', padding: '3px 8px', fontVariantNumeric: 'tabular-nums' }}>
                {r.baseline ? '—' : `${signed(r.vs_baseline)}${r.vs_baseline_pct != null ? ` (${signed(r.vs_baseline_pct)}%)` : ''}`}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <details style={{ marginTop: 10 }}>
        <summary style={{ fontSize: 12, cursor: 'pointer' }}>{t('res.sc.details')}</summary>
        <table style={{ fontSize: 11.5, borderCollapse: 'collapse', marginTop: 6 }}>
          <thead><tr style={{ color: 'var(--muted)' }}>
            <th style={{ textAlign: 'start', padding: '2px 10px 2px 0' }}>{t('res.sc.period')}</th>
            {result.series.map(sc => <th key={sc} style={{ textAlign: 'end', padding: '2px 10px' }}>{name(sc)}</th>)}
          </tr></thead>
          <tbody>
            {result.chart.map(row => (
              <tr key={String(row.name)}>
                <td style={{ padding: '2px 10px 2px 0' }}>{String(row.name)}</td>
                {result.series.map(sc => (
                  <td key={sc} dir="ltr" style={{ textAlign: 'end', padding: '2px 10px', fontVariantNumeric: 'tabular-nums' }}>{n(Number(row[sc]))}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </details>
      {result.caveats?.length > 0 && (
        <ul style={{ fontSize: 11, color: 'var(--muted)', margin: '10px 0 0', paddingInlineStart: 18 }}>
          {result.caveats.map((_c, i) => <li key={i}>{caveat(i)}</li>)}
        </ul>
      )}
    </div>
  )
}

export interface CohortRetentionPayload {
  rows: ({ cohort: string; size: number } & Record<string, number | string | null>)[]
  warnings?: string[]
  meta: { entity: string; date_column: string; granularity: string; periods: number; entities: number
    once_only: number; cohorts: number; from: string; to: string
    curve: { period: number; retention: number | null; cohorts: number; entities: number }[]
    first_back: number; settled: number; settled_period: number
    headline: string; headline_i18n?: SaidI18n | null; warnings_i18n?: (SaidI18n | null)[] }
}

/** Who comes back: one row per cohort, one column per period since its first. Empty cells are periods not lived yet. */
function CohortRetention({ result }: { result: CohortRetentionPayload }) {
  const t = useT()
  const m = result.meta
  const ks = Array.from({ length: m.periods }, (_, i) => i + 1)
  const cell = (v: number | null | undefined) => v == null ? undefined
    : `color-mix(in srgb, var(--accent) ${Math.round(Math.min(100, Math.max(0, v)) * 0.7)}%, transparent)`
  const th = { textAlign: 'end' as const, padding: '2px 6px', fontWeight: 500 }
  const td = { textAlign: 'end' as const, padding: '3px 6px', fontVariantNumeric: 'tabular-nums' as const }
  return (
    <div className="card" style={{ padding: 18 }}>
      <SectionLabel>{t('res.co.title', { e: m.entity, g: t(`res.co.g.${m.granularity}` as MessageKey) })}</SectionLabel>
      <div data-testid="cohort-headline" style={{ fontSize: 13, margin: '4px 0 12px' }}>{sayText(t, m.headline, m.headline_i18n)}</div>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ fontSize: 12, borderCollapse: 'collapse' }}>
          <thead><tr style={{ color: 'var(--muted)' }}>
            <th style={{ textAlign: 'start', padding: '2px 8px 2px 0', fontWeight: 500 }}>{t('res.co.first')}</th>
            <th style={th}>{t('res.co.size')}</th>
            {ks.map(k => <th key={k} style={th}>+{k}</th>)}
          </tr></thead>
          <tbody>
            {result.rows.map(r => (
              <tr key={r.cohort} data-testid="cohort-row" style={{ borderTop: '1px solid var(--border)' }}>
                <td dir="ltr" style={{ padding: '3px 8px 3px 0', textAlign: 'start' }}>{r.cohort}</td>
                <td dir="ltr" style={td}>{Number(r.size).toLocaleString()}</td>
                {ks.map(k => { const v = r[`p${k}`] as number | null | undefined
                  return <td key={k} dir="ltr" style={{ ...td, background: cell(v) }}>{v == null ? '' : `${v}%`}</td> })}
              </tr>
            ))}
            <tr data-testid="cohort-typical" style={{ borderTop: '2px solid var(--border)', fontWeight: 600 }}>
              <td style={{ padding: '3px 8px 3px 0' }}>{t('res.co.typical')}</td>
              <td dir="ltr" style={td}>{m.entities.toLocaleString()}</td>
              {m.curve.map(c => <td key={c.period} dir="ltr" style={td}>{c.retention == null ? '' : `${c.retention}%`}</td>)}
            </tr>
          </tbody>
        </table>
      </div>
      <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 6 }}>{t('res.co.legend', { g: t(`res.co.g.${m.granularity}` as MessageKey) })}</div>
      {(result.warnings ?? []).length > 0 && (
        <ul style={{ fontSize: 11, color: 'var(--muted)', margin: '10px 0 0', paddingInlineStart: 18 }}>
          <SaidItems texts={result.warnings} i18n={m.warnings_i18n} />
        </ul>
      )}
    </div>
  )
}

interface SimulatedRow { scenario: string; expected: number; p05: number; p25: number; median: number; p75: number; p95: number
  chance_below_baseline?: number; chance_below_floor?: number; median_gain?: number; gain_p05?: number; gain_p95?: number
  extrapolating?: boolean }
export interface SimulateScenariosResult {
  measure: string; horizon: number; runs: number; r2: number; weak_fit?: boolean; floor: number | null
  baseline: SimulatedRow; table: SimulatedRow[]; series: string[]
  histogram: ({ from: number; to: number } & Record<string, number>)[]
  highest: string; caveats: string[]; caveats_i18n?: (SaidI18n | null)[]
}

/** Each what-if as a range of outcomes: the middle, where most runs fall, and the chance of ending below doing nothing. */
function SimulateScenarios({ result }: { result: SimulateScenariosResult }) {
  const t = useT()
  const n = (v: number) => v.toLocaleString(undefined, { maximumFractionDigits: Math.abs(v) >= 100 ? 0 : 2 })
  const pct = (v: number | undefined) => v == null ? '—' : `${Math.round(v * 100)}%`
  const name = (sc: string) => sc === 'Nothing moved' ? t('res.sc.none') : sc
  const rows = [result.baseline, ...result.table]
  const lo = Math.min(...rows.map(r => r.p05)), hi = Math.max(...rows.map(r => r.p95))
  const at = (v: number) => hi > lo ? ((v - lo) / (hi - lo)) * 100 : 50
  const th = { textAlign: 'end' as const, padding: '2px 8px', fontWeight: 500 }
  const td = { textAlign: 'end' as const, padding: '3px 8px', fontVariantNumeric: 'tabular-nums' as const }
  const best = result.table.find(r => r.scenario === result.highest) ?? result.table[0]
  return (
    <div className="card" style={{ padding: 18 }}>
      <SectionLabel>{t('res.sim.title', { m: result.measure })}</SectionLabel>
      {result.weak_fit && result.caveats?.[0] && (
        <div role="alert" data-testid="sim-weak" style={{ fontSize: 12, padding: '6px 10px', borderRadius: 6, margin: '4px 0 8px',
          background: 'var(--surface2)', color: 'var(--danger)' }}>{sayText(t, result.caveats[0], result.caveats_i18n?.[0])}</div>
      )}
      {best && (
        <div data-testid="sim-headline" style={{ fontSize: 13, margin: '4px 0 10px' }}>
          {t('res.sim.head', { sc: best.scenario, n: result.horizon, lo: n(best.p05), hi: n(best.p95), mid: n(best.median),
            chance: pct(best.chance_below_baseline) })}
        </div>
      )}
      <table style={{ fontSize: 12, borderCollapse: 'collapse', width: '100%' }}>
        <thead><tr style={{ color: 'var(--muted)' }}>
          <th style={{ textAlign: 'start', padding: '2px 8px 2px 0', fontWeight: 500 }}>{t('res.sc.scenario')}</th>
          <th style={th}>{t('res.sim.middle')}</th>
          <th style={th}>{t('res.sim.range')}</th>
          <th style={{ ...th, width: '28%' }} aria-hidden />
          <th style={th}>{t('res.sim.below')}</th>
          {result.floor != null && <th style={th}>{t('res.sim.belowFloor', { v: n(result.floor) })}</th>}
        </tr></thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r.scenario} data-testid="sim-row" style={{ borderTop: '1px solid var(--border)' }}>
              <td style={{ padding: '3px 8px 3px 0' }}><bdi>{name(r.scenario)}</bdi>
                {r.extrapolating && <span title={t('res.sc.beyondTip')} style={{ color: 'var(--danger)', marginInlineStart: 6 }}>{t('res.sc.beyond')}</span>}</td>
              <td dir="ltr" style={td}>{n(r.median)}</td>
              <td dir="ltr" style={td}>{n(r.p05)} – {n(r.p95)}</td>
              <td style={{ padding: '3px 8px' }}>
                <div dir="ltr" aria-hidden style={{ position: 'relative', height: 10, background: 'var(--surface2)', borderRadius: 5 }}>
                  <div style={{ position: 'absolute', top: 3, height: 4, left: `${at(r.p05)}%`, width: `${Math.max(1, at(r.p95) - at(r.p05))}%`,
                    background: 'var(--muted)', opacity: 0.5, borderRadius: 2 }} />
                  <div style={{ position: 'absolute', top: 1, height: 8, left: `${at(r.p25)}%`, width: `${Math.max(1, at(r.p75) - at(r.p25))}%`,
                    background: i === 0 ? 'var(--muted)' : 'var(--accent)', borderRadius: 3 }} />
                </div>
              </td>
              <td dir="ltr" style={td}>{i === 0 ? '—' : pct(r.chance_below_baseline)}</td>
              {result.floor != null && <td dir="ltr" style={td}>{pct(r.chance_below_floor)}</td>}
            </tr>
          ))}
        </tbody>
      </table>
      <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 6 }}>{t('res.sim.legend', { n: result.runs.toLocaleString() })}</div>
      {result.caveats?.length > 0 && (
        <ul style={{ fontSize: 11, color: 'var(--muted)', margin: '10px 0 0', paddingInlineStart: 18 }}>
          <SaidItems texts={result.caveats} i18n={result.caveats_i18n} />
        </ul>
      )}
    </div>
  )
}

export interface StageBoardPayload {
  rows: { stage: string; rows: number; share_pct: number; open: number; median_age_days?: number; oldest_days?: number
    overdue?: number; finished?: number; on_time_pct?: number }[]
  warnings?: string[]
  meta: { stage_col: string; as_of: string; rows: number; open: number | null
    finished?: number; on_time_pct?: number | null; overdue?: number; overdue_pct?: number | null
    warnings_i18n?: (SaidI18n | null)[] }
}

/** Where things stand: the headline counts, then one row per stage. */
function StageBoard({ result }: { result: StageBoardPayload }) {
  const t = useT()
  const m = result.meta
  const n = (v: number) => v.toLocaleString()
  const late = result.rows.some(r => r.overdue != null), timed = result.rows.some(r => r.on_time_pct != null)
  const Stat = ({ label, value, tone }: { label: string; value: string; tone?: string }) => (
    <div data-testid="stage-stat"><div style={{ fontSize: 11, color: 'var(--muted)' }}>{label}</div>
      <div dir="ltr" style={{ fontSize: 20, fontWeight: 650, color: tone, fontVariantNumeric: 'tabular-nums' }}>{value}</div></div>
  )
  const th = { textAlign: 'end' as const, padding: '2px 8px' }, td = { textAlign: 'end' as const, padding: '3px 8px', fontVariantNumeric: 'tabular-nums' as const }
  return (
    <div className="card" style={{ padding: 18 }}>
      <SectionLabel>{t('res.sb.title', { c: m.stage_col, d: m.as_of })}</SectionLabel>
      <div style={{ display: 'flex', gap: 28, flexWrap: 'wrap', margin: '6px 0 12px' }}>
        <Stat label={t('res.sb.rows')} value={n(m.rows)} />
        {m.open != null && <Stat label={t('res.sb.going')} value={n(m.open)} />}
        {m.overdue != null && <Stat label={t('res.sb.overdue')} value={`${n(m.overdue)}${m.overdue_pct != null ? ` (${m.overdue_pct}%)` : ''}`}
          tone={m.overdue ? 'var(--danger)' : undefined} />}
        {m.on_time_pct != null && <Stat label={t('res.sb.ontime')} value={`${m.on_time_pct}%`} />}
      </div>
      <table style={{ fontSize: 12, borderCollapse: 'collapse', width: '100%' }}>
        <thead><tr style={{ color: 'var(--muted)' }}>
          <th style={{ textAlign: 'start', padding: '2px 8px 2px 0' }}>{m.stage_col}</th>
          <th style={th}>{t('res.sb.rows')}</th>
          <th style={th}>{t('res.sb.going')}</th>
          <th style={th}>{t('res.sb.usual')}</th>
          {late && <th style={th}>{t('res.sb.overdue')}</th>}
          {timed && <th style={th}>{t('res.sb.ontimeShort')}</th>}
        </tr></thead>
        <tbody>
          {result.rows.map(r => (
            <tr key={r.stage} data-testid="stage-row" style={{ borderTop: '1px solid var(--border)' }}>
              <td style={{ padding: '3px 8px 3px 0' }}><bdi>{r.stage}</bdi> <span style={{ color: 'var(--muted)' }}>{r.share_pct}%</span></td>
              <td dir="ltr" style={td}>{n(r.rows)}</td>
              <td dir="ltr" style={td}>{r.open ? n(r.open) : '—'}</td>
              <td dir="ltr" style={td}>{r.median_age_days != null ? r.median_age_days : '—'}</td>
              {late && <td dir="ltr" style={{ ...td, color: r.overdue ? 'var(--danger)' : undefined }}>{r.overdue ? n(r.overdue) : '—'}</td>}
              {timed && <td dir="ltr" style={td}>{r.on_time_pct != null ? `${r.on_time_pct}%` : '—'}</td>}
            </tr>
          ))}
        </tbody>
      </table>
      {(result.warnings ?? []).length > 0 && (
        <ul style={{ fontSize: 11, color: 'var(--muted)', margin: '10px 0 0', paddingInlineStart: 18 }}>
          {(result.warnings ?? []).map((w, i) => <li key={i}>{sayText(t, w, m.warnings_i18n?.[i])}</li>)}
        </ul>
      )}
    </div>
  )
}

export interface TwoGroupsPayload {
  rows: { group: string; rows: number; baseline: boolean; rate?: number; mean?: number }[]
  warnings?: string[]
  meta: {
    group_col: string; outcome: string; outcome_value: string | null; measure: 'rate' | 'mean'
    baseline: string; other: string; difference: number; low: number; high: number; level: number
    lift_pct: number | null; chance_higher: number; p_value: number
    verdict: 'higher' | 'lower' | 'not_clear'; sentence: string; sentence_i18n?: SaidI18n | null
    warnings_i18n?: (SaidI18n | null)[]
    curves: Record<string, [number, number][]>
  }
}

/** Two groups, one outcome: the verdict first, then the numbers behind it. */
function TwoGroups({ result }: { result: TwoGroupsPayload }) {
  const t = useT()
  const m = result.meta
  const rate = m.measure === 'rate'
  const show = (v: number) => rate ? `${(v * 100).toFixed(1)}%` : v.toLocaleString(undefined, { maximumFractionDigits: 2 })
  const gap = (v: number) => rate ? t('res.tg.points', { v: `${v > 0 ? '+' : ''}${(v * 100).toFixed(1)}` })
    : `${v > 0 ? '+' : ''}${v.toLocaleString(undefined, { maximumFractionDigits: 2 })}`
  // Both curves on one axis: what each group's true value probably is.
  const all = Object.values(m.curves).flat()
  const x0 = Math.min(...all.map(p => p[0])), x1 = Math.max(...all.map(p => p[0]))
  const W = 320, H = 70
  const path = (pts: [number, number][]) => pts.map(([x, y], i) =>
    `${i ? 'L' : 'M'}${((x - x0) / (x1 - x0 || 1) * W).toFixed(1)},${(H - y * (H - 4)).toFixed(1)}`).join(' ')
  return (
    <div className="card" style={{ padding: 18 }}>
      <SectionLabel>{t('res.tg.title', { outcome: `${m.outcome}${m.outcome_value != null ? ` = ${m.outcome_value}` : ''}`, group: m.group_col })}</SectionLabel>
      <div data-testid="two-groups-verdict" style={{ fontSize: 14, fontWeight: 600, margin: '4px 0 10px',
        color: m.verdict === 'not_clear' ? 'var(--muted)' : 'var(--text)' }}>{sayText(t, m.sentence, m.sentence_i18n)}</div>
      <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', marginBottom: 10 }}>
        {result.rows.map(r => (
          <div key={r.group} data-testid="two-groups-group">
            <div style={{ fontSize: 11, color: 'var(--muted)' }}><bdi>{r.group}</bdi>{r.baseline ? ` ${t('res.tg.against')}` : ''}</div>
            <div dir="ltr" style={{ fontSize: 20, fontWeight: 650, fontVariantNumeric: 'tabular-nums' }}>{show((rate ? r.rate : r.mean) ?? 0)}</div>
            <div style={{ fontSize: 10.5, color: 'var(--muted)' }}>{t('res.tg.rows', { n: r.rows.toLocaleString() })}</div>
          </div>
        ))}
      </div>
      {all.length > 2 && (
        <svg width={W} height={H} role="img" aria-label={t('res.tg.curves')} style={{ display: 'block', maxWidth: '100%' }}>
          {Object.entries(m.curves).map(([g, pts], i) => (
            <path key={g} d={path(pts)} fill="none" strokeWidth={2}
              stroke={i === 0 ? 'var(--muted)' : 'var(--text)'} strokeDasharray={i === 0 ? '4 3' : undefined} />
          ))}
        </svg>
      )}
      <div style={{ fontSize: 12, marginTop: 8, display: 'grid', gridTemplateColumns: 'max-content 1fr', gap: '2px 12px' }}>
        <span style={{ color: 'var(--muted)' }}>{t('res.tg.diff')}</span>
        <span data-testid="two-groups-difference">{t('res.tg.range', { d: gap(m.difference), lo: gap(m.low), hi: gap(m.high) })}</span>
        {m.lift_pct != null && <><span style={{ color: 'var(--muted)' }}>{t('res.tg.lift')}</span><span dir="ltr">{m.lift_pct > 0 ? '+' : ''}{m.lift_pct.toFixed(1)}%</span></>}
        <span style={{ color: 'var(--muted)' }}>{t('res.tg.chance', { g: m.other })}</span>
        <span data-testid="two-groups-chance">{(m.chance_higher * 100).toFixed(0)}%</span>
      </div>
      {(result.warnings ?? []).length > 0 && (
        <ul style={{ fontSize: 11, color: 'var(--muted)', margin: '10px 0 0', paddingInlineStart: 18 }}>
          {(result.warnings ?? []).map((w, i) => <li key={i}>{sayText(t, w, m.warnings_i18n?.[i])}</li>)}
        </ul>
      )}
    </div>
  )
}

export interface ChangeDriversPayload {
  rows: unknown[]
  warnings?: string[]
  meta: {
    measure: string; period: string; baseline: string; now: number; then: number; change: number
    /** 'measures': one column against another (`reference`), not two periods. */
    mode?: 'measures'; reference?: string
    change_pct: number | null; additive: boolean; warnings_i18n?: (SaidI18n | null)[]
    factors: { column: string; top: string; concentration: number; levels: number; offsetting?: boolean
      values: { value: string; now: number; then: number; delta: number; share_of_change_pct?: number; rows_share_pct?: number }[] }[]
  }
}

/** Why did it change: where the difference between two periods sits. */
function ChangeDrivers({ result }: { result: ChangeDriversPayload }) {
  const t = useT()
  const m = result.meta
  const n = (v: number) => v.toLocaleString(undefined, { maximumFractionDigits: Math.abs(v) >= 100 ? 0 : 2 })
  const signed = (v: number) => `${v > 0 ? '+' : ''}${n(v)}`
  const two = m.mode === 'measures'
  const pct = m.change_pct != null ? `, ${signed(m.change_pct)}%` : ''
  return (
    <div className="card" style={{ padding: 18 }}>
      <SectionLabel>{two ? t('res.cd.titleVs', { m: m.measure, ref: m.reference ?? '' }) : t('res.cd.titleChange', { m: m.measure })}</SectionLabel>
      <div data-testid="change-headline" style={{ fontSize: 13, margin: '4px 0 12px' }}>
        {two
          ? t('res.cd.headVs', { m: m.measure, now: n(m.now), then: n(m.then), ref: m.reference ?? '', delta: signed(m.change), pct })
          : t('res.cd.headChange', { m: m.measure, then: n(m.then), base: m.baseline, now: n(m.now), period: m.period, delta: signed(m.change), pct })}
      </div>
      {m.factors.length === 0 && <p style={{ fontSize: 12, color: 'var(--muted)' }}>{t('res.cd.none')}</p>}
      {m.factors.map(f => (
        <div key={f.column} data-testid="change-factor" style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 12, fontWeight: 600 }}>
            {t('res.cd.by', { c: f.column })}
            <span style={{ fontWeight: 400, color: 'var(--muted)' }}>
              {' '}· {f.offsetting ? t('res.cd.offset')
                : f.concentration >= 0.6 ? t('res.cd.mostly', { v: f.top }) : t('res.cd.spread')}
            </span>
          </div>
          {f.values.map(v => (
            <div key={v.value} style={{ display: 'flex', gap: 8, fontSize: 11.5, alignItems: 'baseline' }}>
              <span style={{ flex: 1 }}><bdi>{v.value}</bdi></span>
              <span dir="ltr" style={{ fontFamily: 'var(--mono)', fontVariantNumeric: 'tabular-nums' }}>{signed(v.delta)}</span>
              <span style={{ color: 'var(--muted)', fontSize: 11, minWidth: 120, textAlign: 'end' }}>
                {v.share_of_change_pct != null ? t('res.cd.ofChange', { p: v.share_of_change_pct.toFixed(1) })
                  : v.rows_share_pct != null ? t('res.cd.ofRows', { p: v.rows_share_pct.toFixed(1) }) : ''}
              </span>
            </div>
          ))}
        </div>
      ))}
      {(result.warnings ?? []).length > 0 && (
        <ul style={{ fontSize: 11, color: 'var(--muted)', margin: '10px 0 0', paddingInlineStart: 18 }}>
          {(result.warnings ?? []).map((w, i) => <li key={i}>{sayText(t, w, m.warnings_i18n?.[i])}</li>)}
        </ul>
      )}
    </div>
  )
}

/**
 * Which model won, and whether winning meant anything.
 *
 * The verdict against the baseline is given its own line and its own words,
 * because the failure this guards is subtle: 82% accuracy reads as a success
 * until you notice that guessing the most common answer scores 79%. Leaving
 * the reader to find both numbers among a list and subtract them is how a
 * dashboard ends up trusted for a decision it cannot support.
 */
function AutomatedPrediction({ result }: { result: PredictionResult }) {
  const tImp = useT()
  const pct = (v: number | null) => v == null ? '—' : String(v)
  return (
    <div className="card" style={{ padding: 18 }}>
      <SectionLabel>{tImp('res.dt.predicting', { t: result.target })}</SectionLabel>

      <div data-testid="prediction-champion" style={{ margin: '4px 0 10px' }}>
        <div style={{ fontSize: 15, fontWeight: 600 }}>{result.champion.model}</div>
        <div style={{ fontSize: 11, color: 'var(--muted)' }}>
          {tImp('res.ap.champion', { score: result.score_name, v: pct(result.champion.score), n: result.n_test })}
          {result.split?.kind === 'partition'
            ? <span data-testid="prediction-split"> · {rich(tImp, 'res.ap.split', { c: <b>{result.split.column}</b>, n: result.n_train })}</span>
            : null}
        </div>
      </div>

      {/* The line that decides whether any of the above matters. */}
      <div data-testid="prediction-verdict" style={{
        fontSize: 12, padding: '7px 10px', borderRadius: 6, marginBottom: 12,
        background: 'var(--surface2)',
        color: result.beats_baseline ? 'var(--text)' : 'var(--danger)',
      }}>
        {result.beats_baseline
          ? rich(tImp, 'res.ap.better', { lift: <strong>{pct(result.lift_over_baseline)}</strong>, base: pct(result.baseline_score) })
          : rich(tImp, 'res.ap.noBetter', { base: pct(result.baseline_score), none: <strong>{tImp('res.ap.noBetterStrong')}</strong> })}
      </div>

      <SectionLabel>{tImp('res.ap.tried')}</SectionLabel>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
        {result.candidates.map((c, i) => (
          <div key={i} data-testid="prediction-candidate" style={{
            display: 'flex', alignItems: 'baseline', gap: 8, fontSize: 11.5,
            opacity: c.is_baseline ? 0.75 : 1,
          }}>
            <span style={{ flex: 1 }}>
              {c.model}
              {c.is_baseline && (
                <span style={{ color: 'var(--muted)' }}> — {tImp('res.ap.guess')}</span>
              )}
            </span>
            <span style={{ fontFamily: 'var(--mono)', fontVariantNumeric: 'tabular-nums' }}>
              {c.error ? c.error : pct(c.score)}
            </span>
            {/* Its training score beside it, so a candidate that memorised is
                visible as one rather than hidden behind a respectable number. */}
            {c.train_score != null && !c.error && (
              <span style={{ color: 'var(--muted)', fontSize: 11,
                             fontFamily: 'var(--mono)' }}>
                ({tImp('res.ap.fitted', { v: pct(c.train_score) })})
              </span>
            )}
          </div>
        ))}
      </div>

      {(result.importance ?? []).length > 0 && (
        <div data-testid="prediction-importance" style={{ marginTop: 12 }}>
          <SectionLabel>{tImp('res.imp.title', { model: result.importance_of ?? '' })}</SectionLabel>
          {(() => {
            const rows = result.importance ?? []
            const top = Math.max(...rows.map(r => r.drop), 0) || 1
            return rows.map(r => (
              <div key={r.column} style={{ display: 'grid', gridTemplateColumns: 'minmax(90px, 30%) 1fr 64px', gap: 6,
                alignItems: 'center', fontSize: 11.5, opacity: r.matters ? 1 : 0.55 }}>
                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.column}</span>
                <div style={{ background: 'var(--surface2)', borderRadius: 4, height: 10 }}>
                  <div style={{ width: `${Math.max(0, r.drop) / top * 100}%`, height: '100%', borderRadius: 4,
                    background: 'color-mix(in srgb, var(--muted) 55%, transparent)' }} />
                </div>
                <span style={{ textAlign: 'end', fontFamily: 'var(--mono)', fontVariantNumeric: 'tabular-nums' }}>
                  {r.matters ? `−${r.drop.toFixed(3)}` : '≈ 0'}
                </span>
              </div>
            ))
          })()}
          {result.importance_note && (
            <div style={{ fontSize: 10.5, color: 'var(--muted)', marginTop: 4 }}>{sayText(tImp, result.importance_note, result.importance_note_i18n)}</div>
          )}
        </div>
      )}

      {result.predictors_skipped?.length > 0 && (
        <div style={{ fontSize: 10.5, color: 'var(--muted)', marginTop: 10 }}>
          {tImp('res.ap.notUsed', { list: result.predictors_skipped.map(s => s.column).join(', ') })}
        </div>
      )}

      {result.caveats?.length > 0 && (
        <ul style={{ fontSize: 11, color: 'var(--muted)', margin: '10px 0 0',
                     paddingInlineStart: 18 }}>
          <SaidItems texts={result.caveats} i18n={saidOf(result)} />
        </ul>
      )}
    </div>
  )
}


export interface TextTopicsResult {
  column: string
  topics: {
    rank: number
    documents: number
    terms: { term: string; weight: number }[]
    examples: string[]
    sentiment?: { average: number | null; scored: number }
  }[]
  documents_used: number
  documents_skipped: number
  vocabulary: number
  languages?: string[]
  caveats: string[]
}

const LANGUAGE_NAMES: Record<string, string> = { ar: 'Arabic', en: 'English', fr: 'French', es: 'Spanish', de: 'German' }

/** A tone as a word and a colour -- never a colour alone. */
export function toneOf(avg: number | null | undefined, t?: TranslateFn): { word: string; color: string } {
  // With a translator the word is in the reader's language; without one, English (as callers outside a view expect).
  const say = (key: 'res.tone.none' | 'res.tone.positive' | 'res.tone.negative' | 'res.tone.neutral', english: string) =>
    t ? t(key, { v: avg == null ? '' : avg.toFixed(2) }) : english
  if (avg == null) return { word: say('res.tone.none', 'no scored words'), color: 'var(--muted)' }
  if (avg >= 0.05) return { word: say('res.tone.positive', `positive (${avg.toFixed(2)})`), color: 'var(--success)' }
  if (avg <= -0.05) return { word: say('res.tone.negative', `negative (${avg.toFixed(2)})`), color: 'var(--danger)' }
  return { word: say('res.tone.neutral', `neutral (${avg.toFixed(2)})`), color: 'var(--muted)' }
}

/** A language's name in the reader's language; its code when it is not one of the five named. */
function languageNames(t: TranslateFn, codes: string[]): string {
  return codes.map(l => (l in LANGUAGE_NAMES ? t(`res.lang.${l}` as MessageKey) : l)).join(' + ')
}

/**
 * Topics as their words, their size, and one real comment each.
 *
 * The quote is the part that earns its space. A list of terms reads like a
 * taxonomy the machine assigned, and a reader will name it and move on; a
 * comment underneath lets them check whether the cluster means what its words
 * suggest. That is also why the caveats stay on screen rather than folding
 * away — "not a name" is the single most important thing this view says.
 */
function TextTopics({ result }: { result: TextTopicsResult }) {
  const tr = useT()
  return (
    <div className="card" style={{ padding: 18 }}>
      <SectionLabel>{tr('res.tt.title', { c: result.column })}</SectionLabel>

      <div data-testid="topics-summary" style={{ fontSize: 11, color: 'var(--muted)',
                                                 marginBottom: 12 }}>
        {tr('res.tt.summary', { n: result.documents_used.toLocaleString(), w: result.vocabulary.toLocaleString() })}
        {result.documents_skipped > 0 &&
          ` · ${tr('res.tt.short', { n: result.documents_skipped.toLocaleString() })}`}
        {result.languages?.length ? ` · ${tr('res.tt.removed', { langs: languageNames(tr, result.languages) })}` : ''}
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {result.topics.map(topic => (
          <div key={topic.rank} data-testid="topic" style={{
            borderInlineStart: '2px solid var(--accent)', paddingInlineStart: 10,
          }}>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5,
                          alignItems: 'baseline' }}>
              {topic.terms.map(t => (
                <span key={t.term} dir="auto" style={{
                  fontSize: 11.5, padding: '1px 7px', borderRadius: 10,
                  background: 'var(--surface2)', border: '1px solid var(--border)',
                }}>{t.term}</span>
              ))}
              <span style={{ fontSize: 10.5, color: 'var(--muted)', marginInlineStart: 4 }}>
                {tr('res.comments', { n: topic.documents.toLocaleString() })}
              </span>
              {topic.sentiment && (
                <span data-testid="topic-tone" style={{ fontSize: 10.5, color: toneOf(topic.sentiment.average).color }}
                  title={tr('res.tt.toneTip', { n: topic.sentiment.scored })}>
                  · {toneOf(topic.sentiment.average, tr).word}
                </span>
              )}
            </div>
            {topic.examples?.[0] && (
              <div dir="auto" style={{ fontSize: 11.5, color: 'var(--muted)', marginTop: 4,
                            fontStyle: 'italic' }}>
                “{topic.examples[0]}”
              </div>
            )}
          </div>
        ))}
      </div>

      {result.caveats?.length > 0 && (
        <ul style={{ fontSize: 11, color: 'var(--muted)', margin: '14px 0 0',
                     paddingInlineStart: 18 }}>
          <SaidItems texts={result.caveats} i18n={saidOf(result)} />
        </ul>
      )}
    </div>
  )
}


export interface ScenarioResult {
  measure: string
  factors: {
    column: string
    coefficient: number
    p_value: number
    observed_min: number
    observed_max: number
    recent_level: number
  }[]
  adjustments: Record<string, number>
  baseline_total: number
  scenario_total: number
  difference: number
  r2: number
  periods_fitted: number
  horizon: number
  extrapolating: boolean
  caveats: string[]
}

/** Above this p-value there is no real evidence the factor moves anything, and
 *  a scenario resting on it is a guess wearing a number. */
const NO_EVIDENCE_ABOVE = 0.05

/**
 * What the scenario changes, and how much of it to believe.
 *
 * The difference leads because it is the number somebody takes to a meeting.
 * The p-value sits beside its factor rather than in a footnote for the opposite
 * reason: seen on real data, a +10% adjustment to a factor with p = 0.48
 * produced a confident-looking -19,309, and nothing about that figure hints
 * that the coefficient behind it is indistinguishable from zero.
 */
function ForecastScenario({ result }: { result: ScenarioResult }) {
  const tr = useT()
  const up = result.difference >= 0
  const adjusted = Object.entries(result.adjustments ?? {})
  return (
    <div className="card" style={{ padding: 18 }}>
      <SectionLabel>
        {tr('res.fs.title', { m: result.measure, n: result.horizon })}
      </SectionLabel>

      <div data-testid="scenario-difference" style={{ margin: '4px 0 12px' }}>
        <div style={{ fontSize: 20, fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>
          {up ? '+' : ''}{result.difference.toLocaleString()}
        </div>
        <div style={{ fontSize: 11, color: 'var(--muted)' }}>
          {result.baseline_total.toLocaleString()} → {result.scenario_total.toLocaleString()}
          {adjusted.length > 0 && (
            <> · {adjusted.map(([f, v]) =>
              `${f} ${v >= 0 ? '+' : ''}${Math.round(v * 100)}%`).join(', ')}</>
          )}
        </div>
      </div>

      {result.extrapolating && (
        <div data-testid="scenario-extrapolation" role="alert" style={{
          fontSize: 11.5, padding: '7px 10px', borderRadius: 6, marginBottom: 12,
          background: 'var(--surface2)', color: '#e6a03c',
        }}>
          {tr('res.fs.outside')}
        </div>
      )}

      <SectionLabel>{tr('res.fs.factors')}</SectionLabel>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        {result.factors.map(f => {
          const weak = f.p_value > NO_EVIDENCE_ABOVE
          return (
            <div key={f.column} data-testid="scenario-factor" style={{
              display: 'flex', alignItems: 'baseline', gap: 8, fontSize: 11.5,
            }}>
              <span style={{ flex: 1 }}>
                {f.column}
                {/* Beside the factor, not in a footnote: this is the difference
                    between a finding and a coincidence. */}
                {weak && (
                  <span style={{ color: 'var(--danger)' }}> — {tr('res.fs.noEvidence')}</span>
                )}
              </span>
              <span style={{ fontFamily: 'var(--mono)', fontVariantNumeric: 'tabular-nums' }}>
                {f.coefficient.toLocaleString()}
              </span>
              <span style={{ fontFamily: 'var(--mono)', fontSize: 11,
                             color: weak ? 'var(--danger)' : 'var(--muted)' }}>
                p {f.p_value.toFixed(3)}
              </span>
            </div>
          )
        })}
      </div>

      <div style={{ fontSize: 10.5, color: 'var(--muted)', marginTop: 8 }}>
        {tr('res.fs.fitted', { n: result.periods_fitted, p: Math.round(result.r2 * 100) })}
      </div>

      {result.caveats?.length > 0 && (
        <ul style={{ fontSize: 11, color: 'var(--muted)', margin: '10px 0 0',
                     paddingInlineStart: 18 }}>
          <SaidItems texts={result.caveats} i18n={saidOf(result)} />
        </ul>
      )}
    </div>
  )
}


export interface TextSentimentResult {
  column: string
  documents_used: number
  documents_skipped: number
  languages: { primary: string; languages: string[] }
  split: { positive: number; neutral: number; negative: number; unscored: number }
  coverage: number
  average: number
  top_positive_words: { word: string; count: number }[]
  top_negative_words: { word: string; count: number }[]
  most_positive: { text: string; score: number }[]
  most_negative: { text: string; score: number }[]
  groups: { column: string; rows: { group: string; comments: number; scored: number; average: number | null;
    positive_share: number | null; negative_share: number | null }[]; omitted: number } | null
  agreement: { column: string; compared: number; agreement: number | null; polar_agreement?: number | null; note?: string } | null
  caveats: string[]
}

/**
 * The split as one stacked bar with its counts written out, the words that
 * drove it, and the real comments at each end. Unscored comments get their own
 * grey segment -- folding them into "neutral" would claim an opinion the
 * lexicon never read.
 */
function TextSentiment({ result }: { result: TextSentimentResult }) {
  const tr = useT()
  const segs: { key: keyof TextSentimentResult['split']; label: string; color: string }[] = [
    { key: 'positive', label: tr('res.ts.positive'), color: 'var(--success)' },
    { key: 'neutral', label: tr('res.ts.neutral'), color: '#9ca3af' },
    { key: 'negative', label: tr('res.ts.negative'), color: 'var(--danger)' },
    { key: 'unscored', label: tr('res.ts.unscored'), color: 'var(--border)' },
  ]
  const total = segs.reduce((a, s) => a + result.split[s.key], 0) || 1
  const words = (list: { word: string; count: number }[], color: string) => (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
      {list.map(w => (
        <span key={w.word} dir="auto" style={{ fontSize: 11.5, padding: '1px 7px', borderRadius: 10,
          border: `1px solid ${color}`, color }}>{w.word} ×{w.count}</span>
      ))}
      {list.length === 0 && <span style={{ fontSize: 11, color: 'var(--muted)' }}>{tr('res.ts.none')}</span>}
    </div>
  )
  return (
    <div className="card" style={{ padding: 18 }}>
      <SectionLabel>{tr('res.ts.title', { c: result.column })}</SectionLabel>
      <div data-testid="sentiment-summary" style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 10 }}>
        {tr('res.ts.summary', { n: result.documents_used.toLocaleString(), p: (result.coverage * 100).toFixed(0),
          avg: result.average.toFixed(2), langs: languageNames(tr, result.languages.languages) || tr('res.ts.langUnknown') })}
      </div>
      <div role="img" aria-label={segs.map(s => `${s.label} ${result.split[s.key]}`).join(', ')}
        style={{ display: 'flex', height: 14, borderRadius: 4, overflow: 'hidden', marginBottom: 6 }}>
        {segs.map(s => result.split[s.key] > 0 && (
          <div key={s.key} style={{ width: `${(result.split[s.key] / total) * 100}%`, background: s.color }} />
        ))}
      </div>
      <div data-testid="sentiment-split" style={{ display: 'flex', gap: 14, flexWrap: 'wrap', fontSize: 11.5, marginBottom: 14 }}>
        {segs.map(s => (
          <span key={s.key}><span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: 2,
            background: s.color, marginInlineEnd: 4 }} />{s.label} {result.split[s.key].toLocaleString()}
            {' '}({((result.split[s.key] / total) * 100).toFixed(0)}%)</span>
        ))}
      </div>
      {result.agreement && (
        <div data-testid="sentiment-agreement" style={{ fontSize: 12, marginBottom: 12 }}>
          {result.agreement.agreement != null
            ? <>{rich(tr, 'res.ts.agrees', { c: <b>{result.agreement.column}</b>, p: (result.agreement.agreement * 100).toFixed(0),
                n: result.agreement.compared.toLocaleString() })}
                {result.agreement.polar_agreement != null && ` ${tr('res.ts.polar', { p: (result.agreement.polar_agreement * 100).toFixed(0) })}`}.</>
            : rich(tr, 'res.ts.noCompare', { c: <b>{result.agreement.column}</b>, note: result.agreement.note ?? '' })}
        </div>
      )}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12, marginBottom: 12 }}>
        <div><div style={{ fontSize: 11, fontWeight: 700, color: 'var(--muted)', marginBottom: 4 }}>{tr('res.ts.wordsPositive')}</div>
          {words(result.top_positive_words, 'var(--success)')}</div>
        <div><div style={{ fontSize: 11, fontWeight: 700, color: 'var(--muted)', marginBottom: 4 }}>{tr('res.ts.wordsNegative')}</div>
          {words(result.top_negative_words, 'var(--danger)')}</div>
      </div>
      {result.groups && result.groups.rows.length > 0 && (
        <table data-testid="sentiment-groups" style={{ width: '100%', fontSize: 11.5, borderCollapse: 'collapse', marginBottom: 12 }}>
          <thead><tr style={{ color: 'var(--muted)', textAlign: 'start' }}>
            <th style={{ textAlign: 'start' }}>{result.groups.column}</th><th>{tr('res.ts.thComments')}</th><th>{tr('res.ts.thAverage')}</th><th>{tr('res.ts.thNegative')}</th></tr></thead>
          <tbody>{result.groups.rows.map(r => (
            <tr key={r.group} style={{ borderTop: '1px solid var(--border)' }}>
              <td dir="auto">{r.group}</td><td style={{ textAlign: 'center' }}>{r.comments}</td>
              <td style={{ textAlign: 'center', color: toneOf(r.average).color }}>{r.average == null ? '—' : r.average.toFixed(2)}</td>
              <td style={{ textAlign: 'center' }}>{r.negative_share == null ? '—' : `${(r.negative_share * 100).toFixed(0)}%`}</td>
            </tr>))}</tbody>
        </table>
      )}
      {[[tr('res.ts.mostPositive'), result.most_positive], [tr('res.ts.mostNegative'), result.most_negative]].map(([label, list]) => (
        (list as TextSentimentResult['most_positive']).length > 0 && (
          <div key={label as string} style={{ marginBottom: 8 }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--muted)' }}>{(label as string).toUpperCase()}</div>
            {(list as TextSentimentResult['most_positive']).map((e, i) => (
              <div key={i} dir="auto" style={{ fontSize: 11.5, fontStyle: 'italic', color: 'var(--muted)' }}>“{e.text}” ({e.score.toFixed(2)})</div>
            ))}
          </div>
        )
      ))}
      {result.caveats?.length > 0 && (
        <ul style={{ fontSize: 11, color: 'var(--muted)', margin: '10px 0 0', paddingInlineStart: 18 }}>
          <SaidItems texts={result.caveats} i18n={saidOf(result)} />
        </ul>
      )}
    </div>
  )
}
