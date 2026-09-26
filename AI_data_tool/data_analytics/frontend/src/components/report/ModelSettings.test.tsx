import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import ModelSettings, { modelOptsConfig, seedModelOpts } from './ModelSettings'
import { predictionModelsApi } from '../../services/api'

vi.mock('../../services/api', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  predictionModelsApi: { list: vi.fn() },
}))

const v = (id: number, version: number, status: 'champion' | 'candidate') => ({
  id, name: 'Churn model', dataset_id: 1, target: 'churn', features: ['spend'], task: 'regression' as const,
  model_family: 'linear', score: 0.8, score_name: 'r2', created_at: null, version, status,
})

describe('a scoring widget can follow the champion (E13)', () => {
  beforeEach(() => { vi.mocked(predictionModelsApi.list).mockResolvedValue([v(7, 1, 'champion'), v(8, 2, 'candidate')]) })

  it('lists each version, marking the champion', async () => {
    render(<ModelSettings widget={{ widget_type: 'model_score' } as never} pages={[]} datasetId={1}
      value={{}} onChange={() => {}} />)
    expect(await screen.findByRole('option', { name: /Churn model v1 \(champion\)/ })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: /Churn model v2 — predicts/ })).toBeInTheDocument()
  })

  it('ticking "Always use the current champion" writes model_follows', async () => {
    const onChange = vi.fn()
    render(<ModelSettings widget={{ widget_type: 'model_score' } as never} pages={[]} datasetId={1}
      value={{ prediction_model_id: 8 }} onChange={onChange} />)
    const box = await screen.findByRole('checkbox', { name: /Always use the current champion of “Churn model”/ })
    expect(screen.getByText(/keeps scoring with v2/)).toBeInTheDocument()
    fireEvent.click(box)
    expect(onChange).toHaveBeenCalledWith({ prediction_model_id: 8, model_follows: 'champion' })
  })

  it('the setting round-trips through the saved config, and only with a model chosen', () => {
    expect(modelOptsConfig('model_score', { prediction_model_id: 8, model_follows: 'champion' }))
      .toEqual({ prediction_model_id: 8, model_follows: 'champion' })
    expect(modelOptsConfig('model_score', { model_follows: 'champion' })).toEqual({})
    expect(seedModelOpts({ prediction_model_id: 8, model_follows: 'champion' }))
      .toEqual({ prediction_model_id: 8, model_follows: 'champion' })
    expect(seedModelOpts({ prediction_model_id: 8, model_follows: 'pinned' })).toEqual({ prediction_model_id: 8 })
  })
})
