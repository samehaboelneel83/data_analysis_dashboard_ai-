import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { DifferenceDialog, ExplainDialog, ScenarioDialog, viewAsOptions } from './ViewerKit'
import { analysisCatalogueApi, differenceApi, explainApi } from '../../services/api'

vi.mock('../../services/api', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  explainApi: { explain: vi.fn() },
  analysisCatalogueApi: { run: vi.fn(), registry: vi.fn() },
  differenceApi: { check: vi.fn() },
}))

const cols = [
  { id: 1, name: 'month', dtype: 'datetime', missing_pct: 0, stats: {} },
  { id: 2, name: 'region', dtype: 'categorical', missing_pct: 0, stats: {} },
]

describe('viewAsOptions', () => {
  it('recommends a line for a date axis and a bar for categories', () => {
    const byMonth = viewAsOptions('bar', { dimension: 'month', measure: 'revenue', aggregation: 'sum' }, cols as never, 12)
    expect(byMonth[0]).toMatchObject({ type: 'line', recommended: true })
    const byRegion = viewAsOptions('line', { dimension: 'region', measure: 'revenue', aggregation: 'sum' }, cols as never, 4)
    expect(byRegion[0]).toMatchObject({ type: 'bar', recommended: true })
  })
  it('never offers a pie of averages or of many slices', () => {
    const avg = viewAsOptions('bar', { dimension: 'region', measure: 'revenue', aggregation: 'avg' }, cols as never, 4)
    expect(avg.map(o => o.type)).not.toContain('pie')
    const many = viewAsOptions('bar', { dimension: 'region', aggregation: 'count' }, cols as never, 40)
    expect(many.map(o => o.type)).not.toContain('pie')
  })
  it('offers nothing for widgets outside the series family', () => {
    expect(viewAsOptions('scatter', { dimension: 'region' }, cols as never, 4)).toEqual([])
  })
})

describe('ExplainDialog', () => {
  it('ranks the factors over the widget’s own rows', async () => {
    vi.mocked(explainApi.explain).mockResolvedValue({
      factors: [{ column: 'spend', score: 0.9, relative: 1, direction: '+' }, { column: 'region', score: 0.3, relative: 0.33 }],
      narrative: null, rows: 120, rows_before_filters: 2000,
    })
    render(<ExplainDialog datasetId={1} measure="revenue" filters={[{ column: 'region', op: 'eq', value: 'N' }]} onClose={() => {}} />)
    const factors = await screen.findByTestId('explain-factors')
    expect(factors.textContent).toContain('spend')
    expect(screen.getByText(/Over the 120 rows this widget shows \(of 2,000 before its filters\)/)).toBeTruthy()
    expect(explainApi.explain).toHaveBeenCalledWith(1, 'revenue', [{ column: 'region', op: 'eq', value: 'N' }])
  })
})

describe('ScenarioDialog', () => {
  it('moves a factor and shows the projected difference, naming an extrapolation', async () => {
    vi.mocked(analysisCatalogueApi.run).mockResolvedValue({
      analysis: 'forecast_scenario', result_kind: 'forecast_scenario', params: {},
      result: {
        factors: [{ column: 'spend', coefficient: 2, p_value: 0.001, observed_min: 1, observed_max: 5, recent_level: 3 }],
        history: [{ name: '2025-01', value: 10 }, { name: '2025-02', value: 12 }],
        baseline: [{ name: '2025-03', value: 13 }], scenario: [{ name: '2025-03', value: 15 }],
        baseline_total: 13, scenario_total: 15, difference: 2, extrapolating: true, caveats: ['Association, not intervention.'],
      },
    })
    render(<ScenarioDialog datasetId={1} dateColumn="month" measure="revenue" candidates={['spend']} onClose={() => {}} />)
    fireEvent.change(screen.getByLabelText('Change spend by percent'), { target: { value: '20' } })
    await waitFor(() => expect(analysisCatalogueApi.run).toHaveBeenLastCalledWith(1, 'forecast_scenario',
      expect.objectContaining({ factors: ['spend'], adjustments: { spend: 0.2 } })), { timeout: 2000 })
    expect((await screen.findByTestId('scenario-summary')).textContent).toContain('+15.4%')
    expect(screen.getByText(/extrapolation, not evidence/)).toBeTruthy()
  })
})

describe('WhyDialog', () => {
  it('lists every layer, and says when a layer is empty', async () => {
    const { WhyDialog, describeFilter } = await import('./ViewerKit')
    render(<WhyDialog title="Sales" onClose={() => {}} sections={[
      { title: 'Set by the author (this widget)', empty: 'No filters.', items: [describeFilter({ column: 'region', op: 'neq', value: 'Test' })] },
      { title: 'Your selections', empty: 'None.', items: [] },
    ]} />)
    const text = screen.getByTestId('why-sections').textContent ?? ''
    expect(text).toContain('region is not Test')
    expect(text).toContain('None.')
    expect(describeFilter({ column: 'country', op: 'in', value: ['EG', 'SA'] })).toBe('country is one of EG, SA')
  })
})


describe('DifferenceDialog (Phase 7.2)', () => {
  it('tests the chosen bars under the chart\'s filters and shows every number with its evidence', async () => {
    vi.mocked(differenceApi.check).mockResolvedValue({
      population: { rows_a: 200, rows_b: 400, group_a: 'A', group_b: 'C', dimension: 'region', measure: 'revenue', aggregation: 'sum' },
      summary: 'A total is rows × typical value. The gap is driven by the number of rows.',
      tests: [
        { question: 'typical row', test: "Welch's t-test", p_value: 0.4, p_text: 'p = 0.4', significant: false,
          effect_name: 'cohens_d', effect_size: 0.05, effect_label: 'negligible', values: { A: 100, C: 101 }, sentence: 'No statistically significant difference.' },
        { question: 'row counts', test: 'Exact binomial test (even split)', p_value: 0.0001, p_text: 'p < 0.001', significant: true,
          effect_name: 'cohens_h', effect_size: -0.34, effect_label: 'small', values: { A: 200, C: 400 }, sentence: 'Statistically significant.' },
      ],
      caveats: ['Tested on the 600 rows behind these two bars, after this chart\'s filters.'],
    })
    render(<DifferenceDialog datasetId={5} dimension="region" measure="revenue" aggregation="sum"
      filters={[{ column: 'year', op: 'eq', value: 2026 }]} names={['A', 'B', 'C']} initial={['A', 'C']} onClose={() => {}} />)
    await waitFor(() => expect(screen.getByTestId('difference-result')).toBeTruthy())
    expect(differenceApi.check).toHaveBeenCalledWith(5, { dimension: 'region', groups: ['A', 'C'], measure: 'revenue',
      aggregation: 'sum', granularity: undefined, filters: [{ column: 'year', op: 'eq', value: 2026 }] })
    expect(screen.getByText(/driven by the number of rows/)).toBeTruthy()
    const chips = screen.getAllByTestId('evidence-chip').map(c => c.textContent)
    expect(chips[1]).toContain('p < 0.001 · small effect')
    expect(screen.getByText(/200 rows of A and 400 of C/)).toBeTruthy()
    fireEvent.change(screen.getByLabelText('Second bar'), { target: { value: 'A' } })
    expect(await screen.findByText('Pick two different bars')).toBeTruthy()
  })
})
