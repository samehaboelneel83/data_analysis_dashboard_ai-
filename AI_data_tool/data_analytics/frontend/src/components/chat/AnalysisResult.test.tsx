import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import AnalysisResult, { isAnalysisResult } from './AnalysisResult'

/**
 * The agent answers some questions with an analysis instead of SQL.
 *
 * "Is revenue really different between regions?" used to come back as a GROUP
 * BY returning four averages — the arithmetic, not the answer. The agent now
 * runs `compare_groups` and puts the result on the same `presentation` channel
 * the dashboard proposals ride.
 *
 * It renders through `ResultFor`, the SAME component the analysis panel uses.
 * That is the whole point: a statistic shown two ways on two screens is two
 * chances to show it wrong, and the effect-size-over-p-value discipline lives
 * in exactly one place.
 */

const compareGroups = {
  kind: 'analysis_result' as const,
  analysis: 'compare_groups',
  result_kind: 'statistical_test',
  params: { value_col: 'revenue', group_col: 'region' },
  result: {
    kind: 'compare_groups', statistic: 41.2, p_value: 0.0000001,
    effect_size: 2.9, effect_name: 'cohens_d', effect_label: 'large',
    significant: true, alpha: 0.05, n: 24,
    detail: { test: "Welch's t-test" },
    interpretation: 'A statistically significant difference, with a large effect.',
    caveats: ['Welch’s t-test does not assume equal variances'],
  },
}

describe('recognising the presentation', () => {
  it('accepts an analysis result', () => {
    expect(isAnalysisResult(compareGroups)).toBe(true)
  })

  it('rejects the other things that ride this channel', () => {
    expect(isAnalysisResult({ kind: 'dashboard_proposals' })).toBe(false)
    expect(isAnalysisResult({ kind: 'table' })).toBe(false)
    expect(isAnalysisResult(null)).toBe(false)
    expect(isAnalysisResult(undefined)).toBe(false)
  })
})

describe('what the reader sees', () => {
  it('leads with the effect size, not the p-value', () => {
    // The property the panel enforces, enforced here by construction: it is
    // the same component. At scale a p-value alone is nearly content-free.
    render(<AnalysisResult presentation={compareGroups} />)
    expect(screen.getByText(/cohens d/i)).toBeInTheDocument()
    expect(screen.getByText('2.9')).toBeInTheDocument()
    expect(screen.getByText(/· large/)).toBeInTheDocument()
  })

  it('shows the caveats, which are part of the answer', () => {
    render(<AnalysisResult presentation={compareGroups} />)
    expect(screen.getByText(/does not assume equal variances/i)).toBeInTheDocument()
  })

  it('names the analysis that was run', () => {
    // The person asked a question in English and got a statistic back. Which
    // test produced it is not a detail they should have to ask for.
    render(<AnalysisResult presentation={compareGroups} />)
    expect(screen.getByText(/compare groups/i)).toBeInTheDocument()
  })

  it('draws the importance bars for an explanation', () => {
    render(<AnalysisResult presentation={{
      kind: 'analysis_result', analysis: 'explain_response',
      result_kind: 'explanation', params: { response: 'revenue' },
      result: {
        response: 'revenue', note: null, relationship: null,
        factors: [{ column: 'units', kind: 'numeric', score: 0.9, relative: 1 }],
      },
    }} />)
    expect(screen.getByTestId('bar-units')).toBeInTheDocument()
  })

  it('names the columns in a goal-seek answer', () => {
    // `result` carries the numbers but not what they are about; `params` is
    // what makes "would need to be ≈ 812" a sentence.
    render(<AnalysisResult presentation={{
      kind: 'analysis_result', analysis: 'goal_seek', result_kind: 'goal_seek',
      params: { x_column: 'units', y_column: 'revenue', target_y: 9000 },
      result: { required_x: 812, r2: 0.9, within_observed_range: true },
    }} />)
    expect(screen.getByTestId('goal-result')).toHaveTextContent(/units/)
  })

  it('renders a kind it has never seen rather than nothing', () => {
    // A new analysis registered on the backend must appear in chat without a
    // frontend change; rendering blank would be a silent failure.
    render(<AnalysisResult presentation={{
      kind: 'analysis_result', analysis: 'whatever',
      result_kind: 'brand_new', params: {},
      result: { silhouette: 0.61 },
    }} />)
    expect(screen.getByText('silhouette')).toBeInTheDocument()
    expect(screen.getByText('0.61')).toBeInTheDocument()
  })

  it('renders nothing for a presentation of another kind', () => {
    const { container } = render(
      <AnalysisResult presentation={{ kind: 'dashboard_proposals' }} />)
    expect(container).toBeEmptyDOMElement()
  })
})
