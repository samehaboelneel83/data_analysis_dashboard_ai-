import { ResultFor } from '../analysis/analysisResults'

/**
 * An analysis the agent ran instead of writing SQL.
 *
 * "Is revenue really different between regions?" used to come back as a GROUP
 * BY returning four averages. Those four numbers are the arithmetic; whether
 * they differ by more than chance is a t-test, and the platform has had one for
 * months — reachable from every surface except the one where people ask the
 * question in English.
 *
 * Like a dashboard proposal, this has no rows to draw, so it rides the same
 * `presentation` channel and is dispatched by kind rather than pushed through
 * `ResultView`, which exists to draw query results.
 *
 * The body is `ResultFor` — the SAME component the analysis panel renders. That
 * is deliberate and it is the point: a statistic shown two ways on two screens
 * is two chances to show it wrong, and the discipline that keeps the effect
 * size beside the p-value lives in exactly one place.
 */

export interface AnalysisResultPresentation {
  kind: 'analysis_result'
  analysis: string
  result_kind: string
  params: Record<string, unknown>
  result: unknown
}

export function isAnalysisResult(p: unknown): p is AnalysisResultPresentation {
  return !!p && (p as { kind?: string }).kind === 'analysis_result'
}

export default function AnalysisResult({ presentation }: { presentation: unknown }) {
  if (!isAnalysisResult(presentation)) return null
  return (
    <div style={{ marginTop: 10 }}>
      {/* Which analysis produced the number. The person asked a question in
          English; that the answer came from a Welch's t-test rather than an
          average is not a detail they should have to ask for. */}
      <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--muted)',
                    textTransform: 'uppercase', letterSpacing: '.06em',
                    marginBottom: 6 }}>
        {presentation.analysis.replace(/_/g, ' ')}
      </div>
      <ResultFor kind={presentation.result_kind}
        result={presentation.result} params={presentation.params} />
    </div>
  )
}
