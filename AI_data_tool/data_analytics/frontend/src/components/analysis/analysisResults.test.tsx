import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ResultFor, toneOf } from './analysisResults'

const sentiment = {
  kind: 'text_sentiment', column: 'comment', documents_used: 40, documents_skipped: 0,
  languages: { primary: 'ar', languages: ['ar', 'en'] },
  split: { positive: 18, neutral: 0, negative: 18, unscored: 4 }, coverage: 0.9, average: 0.01,
  top_positive_words: [{ word: 'ممتازه', count: 3 }], top_negative_words: [{ word: 'broken', count: 3 }],
  most_positive: [{ text: 'الخدمة ممتازة جدا', score: 0.74 }], most_negative: [{ text: 'The item arrived broken', score: -0.46 }],
  groups: { column: 'branch', rows: [{ group: 'South', comments: 27, scored: 27, average: -0.2, positive_share: 0.33, negative_share: 0.67 }], omitted: 0 },
  agreement: { column: 'label', compared: 36, agreement: 1, polar_agreement: 1 },
  caveats: ['4 of 40 comments contain no scored word and are left unscored rather than counted as neutral.'],
}

describe('where rows stand', () => {
  it('shows the headline counts, then each stage with what is still going, overdue and on time', () => {
    render(<ResultFor kind="stage_board" params={{}} result={{
      meta: { stage_col: 'state', as_of: '2025-06-30', rows: 1000, open: 120, overdue: 30, overdue_pct: 25, finished: 880, on_time_pct: 91.5 },
      rows: [{ stage: 'moving', rows: 120, share_pct: 12, open: 120, median_age_days: 4.5, oldest_days: 40, overdue: 30 },
             { stage: 'done', rows: 880, share_pct: 88, open: 0, overdue: 0, finished: 880, on_time_pct: 91.5 }],
      warnings: ['"Now" is the newest date in the data (2025-06-30), not today.'] }} />)
    expect(screen.getAllByTestId('stage-stat').map(e => e.textContent)).toEqual(['Rows1,000', 'Still going120', 'Overdue30 (25%)', 'Finished on time91.5%'])
    const rows = screen.getAllByTestId('stage-row')
    expect(rows).toHaveLength(2)
    expect(rows[0].textContent).toContain('4.5')
    expect(rows[1].textContent).toContain('91.5%')
    expect(screen.getByText(/not today/)).toBeTruthy()
  })
})

describe('scenarios side by side', () => {
  it('leads with which ends higher, then each total against nothing moved, and flags one beyond the data', () => {
    render(<ResultFor kind="compare_scenarios" params={{}} result={{
      measure: 'revenue', horizon: 6, r2: 0.98, series: ['Nothing moved', 'spend +10%', 'spend -10%'],
      highest: 'spend +10%', lowest: 'spend -10%', gap: 360, gap_pct: 6.5,
      table: [{ scenario: 'Nothing moved', baseline: true, total: 5500, vs_baseline: 0, vs_baseline_pct: 0, extrapolating: false },
              { scenario: 'spend +10%', baseline: false, total: 5680, vs_baseline: 180, vs_baseline_pct: 3.27, extrapolating: true },
              { scenario: 'spend -10%', baseline: false, total: 5320, vs_baseline: -180, vs_baseline_pct: -3.27, extrapolating: false }],
      chart: [{ name: '2026-07', 'Nothing moved': 900, 'spend +10%': 930, 'spend -10%': 870 }],
      caveats: ['This is association, not intervention.'] }} />)
    expect(screen.getByTestId('scenarios-headline').textContent).toMatch(/spend \+10%.*360.*above.*spend -10%/)
    expect(screen.getAllByTestId('scenario-row')).toHaveLength(3)
    expect(screen.getByText(/\+180 \(\+3\.27%\)/)).toBeTruthy()
    expect(screen.getByText(/beyond the data/)).toBeTruthy()
    expect(screen.getByText(/association, not intervention/)).toBeTruthy()
  })
})

describe('two groups, one outcome', () => {
  const base = { group_col: 'arm', outcome: 'done', outcome_value: 'yes', measure: 'rate' as const, baseline: 'first',
    other: 'second', difference: 0.037, low: 0.017, high: 0.057, level: 0.95, lift_pct: 35.2, chance_higher: 0.98,
    p_value: 0.001, verdict: 'higher' as const, sentence: 'second is higher than first, and the rows seen leave little room for the opposite.',
    curves: { first: [[0.09, 0.1], [0.105, 1], [0.12, 0.1]] as [number, number][], second: [[0.127, 0.1], [0.142, 1], [0.157, 0.1]] as [number, number][] } }
  const rows = [{ group: 'first', rows: 2000, baseline: true, rate: 0.105 }, { group: 'second', rows: 2000, baseline: false, rate: 0.142 }]

  it('leads with the verdict, then each group, the range, the lift and the chance', () => {
    render(<ResultFor kind="two_groups" params={{}} result={{ rows, meta: base,
      warnings: ['If rows were not put in their groups at random, this is a difference between two kinds of rows, not the effect of the group.'] }} />)
    expect(screen.getByTestId('two-groups-verdict').textContent).toMatch(/second is higher than first/)
    expect(screen.getAllByTestId('two-groups-group')).toHaveLength(2)
    expect(screen.getByText('14.2%')).toBeTruthy()
    expect(screen.getByTestId('two-groups-difference').textContent).toMatch(/\+3\.7 points.*\+1\.7 points.*\+5\.7 points/)
    expect(screen.getByTestId('two-groups-chance').textContent).toBe('98%')
    expect(screen.getByText(/at random/)).toBeTruthy()
  })
})

describe('phase 3 results', () => {
  it('says where a change sits, and that it is not a cause', () => {
    render(<ResultFor kind="change_drivers" params={{}} result={{
      rows: [], warnings: ['This says WHERE the change sits, not what caused it.'],
      meta: { measure: 'amount', period: '2024-06', baseline: '2024-05', now: 72000, then: 55800, change: 16200,
        change_pct: 29, additive: true,
        factors: [{ column: 'kind', top: 'b', concentration: 0.93, levels: 3,
          values: [{ value: 'b', now: 36000, then: 18600, delta: 17400, share_of_change_pct: 107.4 }] }] },
    }} />)
    expect(screen.getByTestId('change-headline').textContent).toMatch(/55,800.*72,000/)
    expect(screen.getByText(/mostly b/)).toBeTruthy()
    expect(screen.getByText(/107\.4% of the change/)).toBeTruthy()
    expect(screen.getByText(/not what caused it/)).toBeTruthy()
  })
})

describe('text analytics results (Phase 6.6)', () => {
  it('renders the sentiment split with unscored kept apart, agreement and groups', () => {
    render(<ResultFor kind="text_sentiment" result={sentiment} params={{}} />)
    expect(screen.getByTestId('sentiment-summary').textContent).toContain('90% scored')
    expect(screen.getByTestId('sentiment-summary').textContent).toContain('Arabic + English')
    expect(screen.getByTestId('sentiment-split').textContent).toContain('Unscored 4 (10%)')
    expect(screen.getByTestId('sentiment-agreement').textContent).toContain('100% of 36')
    expect(screen.getByTestId('sentiment-groups').textContent).toContain('South')
    expect(screen.getByText('ممتازه ×3')).toBeTruthy()
    expect(screen.getByText(/left unscored rather than counted as neutral/)).toBeTruthy()
  })

  it('shows each topic’s tone and the stop lists used', () => {
    render(<ResultFor kind="text_topics" params={{}} result={{
      column: 'c', documents_used: 30, documents_skipped: 0, vocabulary: 40, languages: ['ar'], caveats: [],
      topics: [{ rank: 1, documents: 15, terms: [{ term: 'توصيل', weight: 1 }], examples: ['التوصيل متأخر'],
        sentiment: { average: -0.4, scored: 12 } }],
    }} />)
    expect(screen.getByTestId('topics-summary').textContent).toContain('Arabic common words removed')
    expect(screen.getByTestId('topic-tone').textContent).toContain('negative (-0.40)')
  })

  it('names tone in words, not only colour', () => {
    expect(toneOf(null).word).toBe('no scored words')
    expect(toneOf(0.01).word).toBe('neutral (0.01)')
  })
})

describe('automated prediction split (follow-up)', () => {
  it('names the partition column when the split was not random', () => {
    const cand = { model: 'random forest', score: 0.8, train_score: 0.85, n_test: 50, is_baseline: false, error: null }
    render(<ResultFor kind="automated_prediction" params={{}} result={{
      task: 'regression', target: 'y', score_name: 'r2', candidates: [cand], champion: cand,
      baseline_score: 0, lift_over_baseline: 0.8, beats_baseline: true, n_train: 150, n_test: 50,
      split: { kind: 'partition', column: '_Partition_' }, predictors_skipped: [], caveats: [],
    }} />)
    expect(screen.getByTestId('prediction-split').textContent).toContain('_Partition_ (150 training rows)')
  })
})

describe('key influencers renderer (redesign KI-7)', () => {
  const ki = {
    kind: 'key_influencers',
    columns: [{ name: 'units', dtype: 'int64' }],
    rows: [
      { factor: 'region', group: 'Africa', grouped_by: 'value', mean: 3755, baseline: 4316, lift: 0.87, rows: 400, share_of_rows: 0.2 },
      { factor: 'units', group: '251 – 420', grouped_by: 'quantile', mean: 6992, baseline: 4316, lift: 1.62, rows: 500, share_of_rows: 0.25 },
      { factor: 'product', group: 'Water bottles', grouped_by: 'value', mean: 2244, baseline: 4316, lift: 0.52, rows: 171, share_of_rows: 0.09 },
    ],
    meta: { method: 'group lift', target: 'revenue', target_value: null, measure: 'mean', baseline: 4316,
            n_rows_used: 2000, n_rows_total: 2000, sampled: false, groups_considered: 12,
            caveat: 'These factors move with the outcome; that is not proof they cause it.' },
    warnings: [],
  }

  it('draws a ranked chart instead of the generic table, strongest effect first', () => {
    render(<ResultFor kind="key_influencers" result={ki} params={{}} />)
    expect(screen.getByTestId('key-influencers')).toBeInTheDocument()
    const lifts = screen.getAllByTestId('influencer-lift').map(e => e.textContent)
    expect(lifts[0]).toMatch(/1\.62× more/)
    expect(lifts[1]).toMatch(/0\.52× less/)
    expect(lifts[2]).toMatch(/0\.87× less/)
    expect(screen.getAllByTestId('influencer-bar')).toHaveLength(3)
  })

  it('marks a group under 10% of the rows as a small group, and shows rows with their share', () => {
    render(<ResultFor kind="key_influencers" result={ki} params={{}} />)
    expect(screen.getAllByText('small group')).toHaveLength(1)
    expect(screen.getByText('Water bottles', { exact: false }).closest('tr')).toHaveAttribute('data-small', 'true')
    expect(screen.getByText(/· 25%/)).toBeInTheDocument()
  })

  it('a condition and its small-group mark never break across lines (QA V6)', () => {
    // "month is 2024-02 [small group]" wrapped over 4–5 lines and broke the
    // date at its hyphen; in Arabic "= 2024-02" split.
    render(<ResultFor kind="key_influencers" result={ki} params={{}} />)
    const cond = screen.getByText('Water bottles', { exact: false })
    expect(cond).toHaveStyle({ whiteSpace: 'nowrap' })
    expect(screen.getByText('small group')).toHaveStyle({ whiteSpace: 'nowrap' })
    expect(screen.getAllByTestId('influencer-lift')[0]).toHaveStyle({ whiteSpace: 'nowrap' })
  })

  it('invents no p-values and keeps the not-causation caveat', () => {
    render(<ResultFor kind="key_influencers" result={ki} params={{}} />)
    expect(screen.queryByText(/p[- ]?value/i)).toBeNull()
    expect(screen.getByText(/not proof they cause it/)).toBeInTheDocument()
  })
})

describe('key influencers footnotes in Arabic (QA2 T1, new)', () => {
  it('the caveat and the server\'s skip notes are Arabic; column names keep their spelling', async () => {
    const { DirectionProvider } = await import('../../contexts/DirectionContext')
    localStorage.setItem('datalytics.language', 'ar')
    try {
      const ki = {
        kind: 'key_influencers', columns: [],
        rows: [{ factor: 'region', group: 'Africa', grouped_by: 'value', mean: 3755, baseline: 4316, lift: 0.87, rows: 400, share_of_rows: 0.2 }],
        meta: { method: 'group lift', target: 'revenue', target_value: null, measure: 'mean', baseline: 4316, n_rows_used: 2000, n_rows_total: 2000,
          sampled: false, groups_considered: 1, caveat: 'These factors move with the outcome; that is not proof they cause it.' },
        warnings: ["'date' skipped: 633 distinct values, too many to group", "'cost' skipped: it identifies rows rather than describing them",
          "'notes' skipped: only one value", "'x' skipped: no values", 'analysed a 50,000-row sample of 120,000 rows', 'something new from the server'],
      }
      render(<DirectionProvider><ResultFor kind="key_influencers" result={ki} params={{}} /></DirectionProvider>)
      const box = screen.getByTestId('key-influencers')
      expect(box.textContent).not.toMatch(/not proof|skipped|too many|identifies rows|only one value|no values|analysed a/)
      expect(box.textContent).toContain('date')
      expect(box.textContent).toContain('633')
      // An unknown sentence is shown as sent, never dropped.
      expect(box.textContent).toContain('something new from the server')
    } finally { localStorage.removeItem('datalytics.language') }
  })
})


describe('the new result views in Arabic', () => {
  it('says the stage board and its warning in Arabic, numbers as they are', async () => {
    localStorage.setItem('datalytics.language', 'ar')
    const { DirectionProvider } = await import('../../contexts/DirectionContext')
    render(<DirectionProvider><ResultFor kind="stage_board" params={{}} result={{
      meta: { stage_col: 'state', as_of: '2025-06-30', rows: 1000, open: 120, overdue: 30, overdue_pct: 25,
        warnings_i18n: [{ key: 'an.now', vars: { d: '2025-06-30' } }] },
      rows: [{ stage: 'moving', rows: 120, share_pct: 12, open: 120, median_age_days: 4.5, overdue: 30 }],
      warnings: ['"Now" is the newest date in the data (2025-06-30), not today.'] }} /></DirectionProvider>)
    expect(screen.getAllByText('ما زالت جارية').length).toBeGreaterThan(0)
    expect(screen.getByText(/«الآن» هو أحدث تاريخ في البيانات \(2025-06-30\)/)).toBeTruthy()
    expect(screen.getByText('1,000')).toBeTruthy()
    localStorage.removeItem('datalytics.language')
  })

  it('says an older view in Arabic too: the prediction comparison', async () => {
    localStorage.setItem('datalytics.language', 'ar')
    const { DirectionProvider } = await import('../../contexts/DirectionContext')
    render(<DirectionProvider><ResultFor kind="automated_prediction" params={{}} result={{
      task: 'classification', target: 'state', score_name: 'accuracy', n_train: 300, n_test: 100,
      champion: { model: 'decision tree', score: 0.9, train_score: 0.92, n_test: 100, is_baseline: false, error: null },
      candidates: [{ model: 'decision tree', score: 0.9, train_score: 0.92, n_test: 100, is_baseline: false, error: null },
                   { model: 'always the most common', score: 0.6, train_score: 0.6, n_test: 100, is_baseline: true, error: null }],
      baseline_score: 0.6, lift_over_baseline: 0.3, beats_baseline: true, predictors_skipped: [], caveats: [] }} /></DirectionProvider>)
    expect(screen.getByText('توقّع state')).toBeTruthy()
    expect(screen.getByText('كل ما جُرّب')).toBeTruthy()
    expect(screen.getByTestId('prediction-verdict').textContent).toContain('أفضل بمقدار 0.3 من مجرد التخمين')
    localStorage.removeItem('datalytics.language')
  })
})
