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
