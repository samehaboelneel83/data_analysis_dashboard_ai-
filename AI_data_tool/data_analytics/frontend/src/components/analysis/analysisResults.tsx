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
import type { StatisticalTestResult } from '../../services/api'

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
            {f.column}{f.direction === '-' ? ' (inverse)' : ''}
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
  return (
    <p data-testid="goal-result" style={{ fontSize: 12, marginTop: 6 }}>
      {xName} would need to be ≈ <strong>{goal.required_x.toLocaleString()}</strong>
      {goal.r2 != null && (
        <span style={{ color: 'var(--muted)' }}> (linear fit, r² {goal.r2.toFixed(2)})</span>
      )}
      {goal.within_observed_range === false && (
        <span style={{ display: 'block', color: '#e6a03c', fontSize: 11 }}>
          ⚠ outside the observed range of {xName} — this is an extrapolation
        </span>
      )}
      {goal.within_bounds === false && (
        <span data-testid="goal-infeasible" style={{
          display: 'block', color: 'var(--danger)', fontSize: 11,
        }}>
          ✕ not reachable within the bounds — at {xName} = {goal.bound_x?.toLocaleString()},
          the best achievable {yName} ≈ <strong>{goal.achievable_y?.toLocaleString()}</strong>
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
            <SectionLabel>Relative importance</SectionLabel>
            <FactorBars factors={r.factors} />
          </>
        )}
        {r.relationship && (
          <>
            <SectionLabel>Top factor: {r.relationship.column}</SectionLabel>
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
        <SectionLabel>Goal seek</SectionLabel>
        <GoalSeekAnswer goal={result as GoalSeekResult}
          xName={String(params.x_column ?? 'the factor')}
          yName={String(params.y_column ?? 'the outcome')} />
      </div>
    )
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
  if (kind === 'decision_tree') {
    return <DecisionTree result={result as DecisionTreeResult} />
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

  return (
    <div className="card" style={{ padding: 18 }}>
      <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 6 }}>{test}</div>
      <p style={{ fontSize: 14, fontWeight: 500, marginTop: 0 }}>{result.interpretation}</p>

      <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', margin: '14px 0' }}>
        <Stat label={result.effect_name.replace(/_/g, ' ')}
          value={result.effect_size} suffix={` · ${result.effect_label}`} />
        <Stat label="p-value" value={result.p_value} />
        <Stat label="rows" value={result.n} />
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
          {result.caveats.map((c, i) => <li key={i}>{c}</li>)}
        </ul>
      )}
    </div>
  )
}

function Stat({ label, value, suffix }: {
  label: string; value: number | null; suffix?: string
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
  return (
    <div className="card" style={{ padding: 18 }}>
      <SectionLabel>
        {result.task === 'classification' ? 'Classifying' : 'Predicting'}{' '}
        {result.target}
      </SectionLabel>

      {/* Both scores, always. One of them alone is not an assessment: a tree
          deep enough reproduces its training rows exactly. */}
      <div data-testid="tree-score" style={{
        display: 'flex', gap: 20, flexWrap: 'wrap', margin: '4px 0 14px',
      }}>
        <Stat label={`${result.score_name} (held out)`} value={result.score}
          suffix={` · ${result.n_test} rows`} />
        <Stat label="on training rows" value={result.train_score}
          suffix={` · ${result.n_train} rows`} />
      </div>

      <TreeBranch node={result.tree} depth={0} />

      {result.importance?.length > 0 && (
        <div style={{ marginTop: 14 }}>
          <SectionLabel>What the splits use</SectionLabel>
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
          Not used as predictors:{' '}
          {result.predictors_skipped.map(s => `${s.column} (${s.reason})`).join('; ')}
        </div>
      )}

      {result.caveats?.length > 0 && (
        <ul style={{ fontSize: 11, color: 'var(--muted)', margin: '10px 0 0',
                     paddingInlineStart: 18 }}>
          {result.caveats.map((c, i) => <li key={i}>{c}</li>)}
        </ul>
      )}
    </div>
  )
}

function TreeBranch({ node, depth }: { node: TreeNode; depth: number }) {
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
          {node.samples.toLocaleString()} rows
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
  caveats: string[]
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
  const pct = (v: number | null) => v == null ? '—' : String(v)
  return (
    <div className="card" style={{ padding: 18 }}>
      <SectionLabel>Predicting {result.target}</SectionLabel>

      <div data-testid="prediction-champion" style={{ margin: '4px 0 10px' }}>
        <div style={{ fontSize: 15, fontWeight: 600 }}>{result.champion.model}</div>
        <div style={{ fontSize: 11, color: 'var(--muted)' }}>
          {result.score_name} {pct(result.champion.score)} on {result.n_test} rows
          held back from every candidate
          {result.split?.kind === 'partition'
            ? <span data-testid="prediction-split"> · split by the partition column <b>{result.split.column}</b> ({result.n_train} training rows)</span>
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
          ? <>That is <strong>{pct(result.lift_over_baseline)}</strong> better than
              simply guessing, which scores {pct(result.baseline_score)}.</>
          : <>Simply guessing scores {pct(result.baseline_score)} — the best model is
              <strong> no better than no model at all</strong> on this data.</>}
      </div>

      <SectionLabel>Everything it tried</SectionLabel>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
        {result.candidates.map((c, i) => (
          <div key={i} data-testid="prediction-candidate" style={{
            display: 'flex', alignItems: 'baseline', gap: 8, fontSize: 11.5,
            opacity: c.is_baseline ? 0.75 : 1,
          }}>
            <span style={{ flex: 1 }}>
              {c.model}
              {c.is_baseline && (
                <span style={{ color: 'var(--muted)' }}> — the guess to beat</span>
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
                ({pct(c.train_score)} fitted)
              </span>
            )}
          </div>
        ))}
      </div>

      {result.predictors_skipped?.length > 0 && (
        <div style={{ fontSize: 10.5, color: 'var(--muted)', marginTop: 10 }}>
          Not used: {result.predictors_skipped.map(s => s.column).join(', ')}
        </div>
      )}

      {result.caveats?.length > 0 && (
        <ul style={{ fontSize: 11, color: 'var(--muted)', margin: '10px 0 0',
                     paddingInlineStart: 18 }}>
          {result.caveats.map((c, i) => <li key={i}>{c}</li>)}
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
export function toneOf(avg: number | null | undefined): { word: string; color: string } {
  if (avg == null) return { word: 'no scored words', color: 'var(--muted)' }
  if (avg >= 0.05) return { word: `positive (${avg.toFixed(2)})`, color: 'var(--success)' }
  if (avg <= -0.05) return { word: `negative (${avg.toFixed(2)})`, color: 'var(--danger)' }
  return { word: `neutral (${avg.toFixed(2)})`, color: 'var(--muted)' }
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
  return (
    <div className="card" style={{ padding: 18 }}>
      <SectionLabel>What “{result.column}” is about</SectionLabel>

      <div data-testid="topics-summary" style={{ fontSize: 11, color: 'var(--muted)',
                                                 marginBottom: 12 }}>
        {result.documents_used.toLocaleString()} comments,{' '}
        {result.vocabulary.toLocaleString()} distinct words
        {result.documents_skipped > 0 &&
          ` · ${result.documents_skipped.toLocaleString()} too short to use`}
        {result.languages?.length ? ` · ${result.languages.map(l => LANGUAGE_NAMES[l] ?? l).join(' + ')} common words removed` : ''}
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
                {topic.documents.toLocaleString()} comments
              </span>
              {topic.sentiment && (
                <span data-testid="topic-tone" style={{ fontSize: 10.5, color: toneOf(topic.sentiment.average).color }}
                  title={`Average lexicon tone of the ${topic.sentiment.scored} comments it could score`}>
                  · {toneOf(topic.sentiment.average).word}
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
          {result.caveats.map((c, i) => <li key={i}>{c}</li>)}
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
  const up = result.difference >= 0
  const adjusted = Object.entries(result.adjustments ?? {})
  return (
    <div className="card" style={{ padding: 18 }}>
      <SectionLabel>
        {result.measure} over the next {result.horizon} periods
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
          ⚠ This scenario goes outside anything the data has ever shown — the
          projection is an extrapolation, not evidence.
        </div>
      )}

      <SectionLabel>The factors it rests on</SectionLabel>
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
                  <span style={{ color: 'var(--danger)' }}> — no evidence it moves this</span>
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
        Fitted over {result.periods_fitted} periods · explains{' '}
        {Math.round(result.r2 * 100)}% of the variation
      </div>

      {result.caveats?.length > 0 && (
        <ul style={{ fontSize: 11, color: 'var(--muted)', margin: '10px 0 0',
                     paddingInlineStart: 18 }}>
          {result.caveats.map((c, i) => <li key={i}>{c}</li>)}
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
  const segs: { key: keyof TextSentimentResult['split']; label: string; color: string }[] = [
    { key: 'positive', label: 'Positive', color: 'var(--success)' },
    { key: 'neutral', label: 'Neutral', color: '#9ca3af' },
    { key: 'negative', label: 'Negative', color: 'var(--danger)' },
    { key: 'unscored', label: 'Unscored', color: 'var(--border)' },
  ]
  const total = segs.reduce((a, s) => a + result.split[s.key], 0) || 1
  const words = (list: { word: string; count: number }[], color: string) => (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
      {list.map(w => (
        <span key={w.word} dir="auto" style={{ fontSize: 11.5, padding: '1px 7px', borderRadius: 10,
          border: `1px solid ${color}`, color }}>{w.word} ×{w.count}</span>
      ))}
      {list.length === 0 && <span style={{ fontSize: 11, color: 'var(--muted)' }}>none</span>}
    </div>
  )
  return (
    <div className="card" style={{ padding: 18 }}>
      <SectionLabel>How people feel in “{result.column}”</SectionLabel>
      <div data-testid="sentiment-summary" style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 10 }}>
        {result.documents_used.toLocaleString()} comments · {(result.coverage * 100).toFixed(0)}% scored ·
        average {result.average.toFixed(2)} · {result.languages.languages.map(l => LANGUAGE_NAMES[l] ?? l).join(' + ') || 'language unknown'}
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
            ? <>Agrees with <b>{result.agreement.column}</b> on {(result.agreement.agreement * 100).toFixed(0)}% of {result.agreement.compared.toLocaleString()} comments
                {result.agreement.polar_agreement != null && ` (${(result.agreement.polar_agreement * 100).toFixed(0)}% where the label is clearly positive or negative)`}.</>
            : <>Could not compare with <b>{result.agreement.column}</b>: {result.agreement.note}</>}
        </div>
      )}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12, marginBottom: 12 }}>
        <div><div style={{ fontSize: 11, fontWeight: 700, color: 'var(--muted)', marginBottom: 4 }}>WORDS READ AS POSITIVE</div>
          {words(result.top_positive_words, 'var(--success)')}</div>
        <div><div style={{ fontSize: 11, fontWeight: 700, color: 'var(--muted)', marginBottom: 4 }}>WORDS READ AS NEGATIVE</div>
          {words(result.top_negative_words, 'var(--danger)')}</div>
      </div>
      {result.groups && result.groups.rows.length > 0 && (
        <table data-testid="sentiment-groups" style={{ width: '100%', fontSize: 11.5, borderCollapse: 'collapse', marginBottom: 12 }}>
          <thead><tr style={{ color: 'var(--muted)', textAlign: 'start' }}>
            <th style={{ textAlign: 'start' }}>{result.groups.column}</th><th>comments</th><th>average</th><th>negative</th></tr></thead>
          <tbody>{result.groups.rows.map(r => (
            <tr key={r.group} style={{ borderTop: '1px solid var(--border)' }}>
              <td dir="auto">{r.group}</td><td style={{ textAlign: 'center' }}>{r.comments}</td>
              <td style={{ textAlign: 'center', color: toneOf(r.average).color }}>{r.average == null ? '—' : r.average.toFixed(2)}</td>
              <td style={{ textAlign: 'center' }}>{r.negative_share == null ? '—' : `${(r.negative_share * 100).toFixed(0)}%`}</td>
            </tr>))}</tbody>
        </table>
      )}
      {[['Most positive', result.most_positive], ['Most negative', result.most_negative]].map(([label, list]) => (
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
          {result.caveats.map((c, i) => <li key={i}>{c}</li>)}
        </ul>
      )}
    </div>
  )
}
