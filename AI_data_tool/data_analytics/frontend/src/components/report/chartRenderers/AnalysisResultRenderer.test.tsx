import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import AnalysisResultRenderer from './AnalysisResultRenderer'

const base = { rows: [], cfg: {}, rtl: false, broadcasts: false, localSelected: null, onClickPoint: () => {} }

describe('an analysis result as a tile', () => {
  it('draws the same view the analysis page does', () => {
    render(<AnalysisResultRenderer {...(base as any)} data={{ type: 'analysis', status: 'ok', analysis: 'stage_board', kind: 'stage_board',
      params: {}, result: { meta: { stage_col: 'state', as_of: '2025-06-30', rows: 1000, open: 120 },
        rows: [{ stage: 'moving', rows: 120, share_pct: 12, open: 120, median_age_days: 4.5 }], warnings: [] } }} />)
    expect(screen.getByTestId('analysis-tile')).toBeTruthy()
    expect(screen.getAllByTestId('stage-row')).toHaveLength(1)
  })

  it('says in words why it has nothing to draw', () => {
    render(<AnalysisResultRenderer {...(base as any)} data={{ type: 'analysis', status: 'refused', reason: 'Only two groups can be compared.' }} />)
    expect(screen.getByTestId('analysis-tile-note').textContent).toContain('Only two groups can be compared.')
  })

  it('a tile with no analysis asks for one', () => {
    render(<AnalysisResultRenderer {...(base as any)} data={{ type: 'analysis', status: 'incomplete' }} />)
    expect(screen.getByTestId('analysis-tile-note').textContent).toMatch(/no analysis yet/)
  })
})
