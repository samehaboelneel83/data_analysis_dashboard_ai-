import { describe, expect, it } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import ModelRenderer from './ModelRenderer'

const base = { rows: [], cfg: {}, rtl: false, broadcasts: false, localSelected: null, onClickPoint: () => {} }
const pop = { rows_total: 400, rows_used: 390, rows_dropped: 10, dropped_by: { cost: 10 } }

describe('ModelRenderer', () => {
  it('states the model, its fit and its population in the header', () => {
    render(<ModelRenderer {...base} data={{
      type: 'model', status: 'ok', model: 'linear', target: 'revenue', predictors: ['units', 'cost'],
      result: { effect_label: 'large', detail: { coefficients: [{ term: 'units', estimate: 12, p_value: 0.001 }] } },
      population: pop, fit: { name: 'R²', value: 0.97, secondary: {} },
      diagnostics: { residuals: [[1, 0.2]], actual_predicted: [[1, 1.1]] }, rows: [],
    }} />)
    expect(screen.getByText('Linear regression', { exact: false })).toBeTruthy()
    expect(screen.getByText(/revenue ~ units \+ cost/)).toBeTruthy()
    expect(screen.getByText(/390/)).toBeTruthy()
    expect(screen.getByRole('tab', { name: 'Residuals' })).toBeTruthy()
    fireEvent.click(screen.getByRole('tab', { name: 'Fit' }))
    expect(screen.getByRole('tab', { name: 'Fit' }).getAttribute('aria-selected')).toBe('true')
  })

  it('shows a refusal with its reason instead of a chart', () => {
    render(<ModelRenderer {...base} data={{ type: 'model', status: 'refused', reason: 'Only 3 complete rows.' }} />)
    expect(screen.getByText('This model could not be fitted')).toBeTruthy()
    expect(screen.getByText('Only 3 complete rows.')).toBeTruthy()
  })

  it('names the comparison winner and warns when it does not beat guessing', () => {
    render(<ModelRenderer {...base} data={{
      type: 'model', status: 'ok', model: 'compare', target: 'churned', metric: 'AUC on held-out rows',
      models: [{ id: 1, title: 'Logit', score: 0.49 }, { id: 2, title: 'Tree', score: 0.48, note: 'text predictors left out of the shared refit: region' }],
      winner: 1, winner_beats_baseline: false,
      baseline: { title: 'Just guess', score: 0.5, note: 'AUC 0.5 is a coin toss' },
      population: { ...pop, train_rows: 270, test_rows: 120 },
    }} />)
    expect(screen.getByText('Logit', { selector: 'b' })).toBeTruthy()
    expect(screen.getByText(/does not beat just guessing/)).toBeTruthy()
    expect(screen.getByText(/region/)).toBeTruthy()
    expect(screen.getByText(/same 120 rows it never saw/)).toBeTruthy()
  })

  it('overlays every compared model\u2019s ROC on one chart, AUC in the legend (follow-up)', () => {
    render(<ModelRenderer {...base} data={{
      type: 'model', status: 'ok', model: 'compare', target: 'churned', metric: 'AUC on held-out rows',
      models: [{ id: 1, title: 'Logit', score: 0.81, roc: [[0, 0], [0.2, 0.7], [1, 1]] },
               { id: 2, title: 'Tree', score: 0.74, roc: [[0, 0], [0.3, 0.6], [1, 1]] }],
      winner: 1, winner_beats_baseline: true,
      baseline: { title: 'Just guess', score: 0.5, note: 'AUC 0.5 is a coin toss' },
      population: { ...pop, train_rows: 270, test_rows: 120 },
    }} />)
    fireEvent.click(screen.getByRole('tab', { name: 'ROC' }))
    const overlay = screen.getByTestId('roc-overlay')
    expect(overlay.querySelectorAll('polyline')).toHaveLength(2)
    expect(overlay.textContent).toContain('Logit — AUC 0.81')
    expect(overlay.textContent).toContain('Tree — AUC 0.74')
  })

  it('shows a saved model scoring the page, shares as percents, and flags unseen values', () => {
    render(<ModelRenderer {...base} data={{
      type: 'model', status: 'ok', model: 'score', target: 'churn',
      saved: { id: 5, name: 'Churn champion', family: 'random forest', task: 'classification' },
      event: 'yes', breakdown: 'region', measure: 'share predicted yes', value_format: 'percent',
      unseen_values: { region: ['Mars'] },
      population: { rows_total: 300, rows_used: 300, rows_dropped: 0, dropped_by: {} },
      fit: { name: 'score at training (accuracy)', value: 0.91, secondary: { 'accuracy on these rows': 0.88 } },
      rows: [{ name: 'North', value: 0.953 }],
    }} />)
    expect(screen.getByText(/Churn champion/)).toBeTruthy()
    expect(screen.getByText('95.3%')).toBeTruthy()
    expect(screen.getByText(/Mars/)).toBeTruthy()
    fireEvent.click(screen.getByRole('tab', { name: 'Check' }))
    expect(screen.getByText(/accuracy on these rows/)).toBeTruthy()
  })

  it('says when the headline is a held-out score and the sentence is about training', () => {
    render(<ModelRenderer {...base} data={{
      type: 'model', status: 'ok', model: 'linear', target: 'revenue', predictors: ['units'],
      result: { effect_label: 'large', interpretation: 'Explains 46% of the variation.', detail: { coefficients: [] } },
      population: { ...pop, partition: { column: '_Partition_', train_rows: 1431, validation_rows: 569 } },
      fit: { name: 'R² on validation rows', value: 0.363, secondary: {} }, diagnostics: {}, rows: [],
    }} />)
    expect(screen.getByText(/On the training rows: Explains 46%/)).toBeTruthy()
    expect(screen.getByText(/validated on 569/)).toBeTruthy()
  })
})
