/**
 * Saved models, and scoring rows with one.
 *
 * The analysis endpoints all refit and discard, so this is the first surface
 * here that answers "score these rows" rather than "what could predict this".
 * Two things the UI must not soften:
 *
 *   **Unseen values.** A model has no opinion about a category it never saw; it
 *   encodes as "none of the above" and still returns a prediction. Showing that
 *   prediction alone lets somebody score a year of new data the model
 *   recognises none of and read it as a forecast.
 *
 *   **A refusal is a reason, not an empty state.** Scoring with a model trained
 *   on a column the user may not read is refused by the server. Rendering that
 *   as "no results" would send them looking for a bug.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import PredictionModelsPanel from './PredictionModelsPanel'
import { predictionModelsApi } from '../../services/api'

vi.mock('../../services/api', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  predictionModelsApi: {
    list: vi.fn(), train: vi.fn(), score: vi.fn(), remove: vi.fn(), promote: vi.fn(),
  },
}))

const model = (over: object = {}) => ({
  id: 7, name: 'Churn model', dataset_id: 1, target: 'churn',
  features: ['region', 'spend'], task: 'classification' as const,
  model_family: 'random forest', score: 0.91, score_name: 'accuracy',
  created_at: '2026-09-11T00:00:00Z', ...over,
})

const columns = [
  { id: 1, name: 'region', dtype: 'categorical', missing_pct: 0, stats: {} },
  { id: 2, name: 'spend', dtype: 'numeric', missing_pct: 0, stats: {} },
  { id: 3, name: 'churn', dtype: 'categorical', missing_pct: 0, stats: {} },
] as never

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(predictionModelsApi.list).mockResolvedValue([])
})

const panel = () => render(<PredictionModelsPanel datasetId={1} columns={columns} />)

describe('PredictionModelsPanel', () => {
  it('says what a saved model is for when there are none', async () => {
    panel()
    expect(await screen.findByText(/no saved models/i)).toBeInTheDocument()
  })

  it('lists a model with its score and what it predicts', async () => {
    vi.mocked(predictionModelsApi.list).mockResolvedValue([model()])
    panel()
    expect(await screen.findByText('Churn model')).toBeInTheDocument()
    // Scoped to the row: "churn" is also an option in the target dropdown, so a
    // bare text query matches the form as readily as the model it is meant to
    // be checking.
    expect(screen.getByText(/predicts/i)).toHaveTextContent('churn')
    expect(screen.getByText(/predicts/i)).toHaveTextContent('region, spend')
    expect(screen.getByText(/accuracy 0\.91/)).toBeInTheDocument()
  })

  it('trains a model and shows it', async () => {
    vi.mocked(predictionModelsApi.train).mockResolvedValue(model())
    vi.mocked(predictionModelsApi.list)
      .mockResolvedValueOnce([]).mockResolvedValue([model()])
    panel()
    await screen.findByText(/no saved models/i)

    fireEvent.change(await screen.findByLabelText(/predict/i), { target: { value: 'churn' } })
    fireEvent.click(screen.getByRole('button', { name: /train/i }))

    await waitFor(() => expect(predictionModelsApi.train).toHaveBeenCalledWith(
      1, expect.objectContaining({ target: 'churn' })))
    expect(await screen.findByText('Churn model')).toBeInTheDocument()
  })

  it('scores the dataset and shows how many rows it answered for', async () => {
    vi.mocked(predictionModelsApi.list).mockResolvedValue([model()])
    vi.mocked(predictionModelsApi.score).mockResolvedValue({
      predictions: ['yes', 'no'], n_scored: 2, unseen_values: {},
      target: 'churn', task: 'classification', model_family: 'random forest',
    })
    panel()
    fireEvent.click(await screen.findByRole('button', { name: /score/i }))

    await waitFor(() => expect(predictionModelsApi.score).toHaveBeenCalledWith(
      1, 7, expect.objectContaining({ from_dataset: true })))
    expect(await screen.findByText(/2 rows/i)).toBeInTheDocument()
  })

  it('warns when the model met values it was never trained on', async () => {
    vi.mocked(predictionModelsApi.list).mockResolvedValue([model()])
    vi.mocked(predictionModelsApi.score).mockResolvedValue({
      predictions: ['yes'], n_scored: 1, unseen_values: { region: ['West'] },
      target: 'churn', task: 'classification', model_family: 'random forest',
    })
    panel()
    fireEvent.click(await screen.findByRole('button', { name: /score/i }))

    expect(await screen.findByText(/never saw/i)).toBeInTheDocument()
    expect(screen.getByText(/West/)).toBeInTheDocument()
  })

  it("shows the server's reason when scoring is refused", async () => {
    // A model trained on a column this user may not read. The reason is the
    // whole content of the response, and an empty table would hide it.
    vi.mocked(predictionModelsApi.list).mockResolvedValue([model()])
    vi.mocked(predictionModelsApi.score).mockRejectedValue({
      response: { status: 400, data: { detail: "This model was trained on 'spend', which is not available to you." } },
    })
    panel()
    fireEvent.click(await screen.findByRole('button', { name: /score/i }))

    expect(await screen.findByText(/not available to you/i)).toBeInTheDocument()
  })

  it('deletes a model', async () => {
    vi.mocked(predictionModelsApi.list).mockResolvedValue([model()])
    vi.mocked(predictionModelsApi.remove).mockResolvedValue(undefined)
    panel()
    fireEvent.click(await screen.findByRole('button', { name: /delete churn model/i }))

    await waitFor(() => expect(predictionModelsApi.remove).toHaveBeenCalledWith(1, 7))
  })
})

/**
 * A DirectQuery dataset cannot train a model, and the panel has to say so.
 *
 * Caught by driving the real UI: the Models tab on "Demo — Live Orders
 * (DirectQuery)" offered a column picker, a name box and a Train button. The
 * server refuses — training is import-mode only — so the author fills the form
 * and learns that after pressing the button.
 *
 * Offering a control that cannot work is the failure this codebase keeps
 * finding, and this one was added an hour earlier by me.
 */
describe('on a DirectQuery dataset', () => {
  const dq = () => render(
    <PredictionModelsPanel datasetId={1} columns={columns} mode="directquery" />)

  it('says training is not available rather than offering the form', async () => {
    dq()
    expect(await screen.findByText(/import-mode/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /train/i })).not.toBeInTheDocument()
  })

  it('still lists models that already exist', async () => {
    // A dataset switched to DirectQuery later may still carry saved models, and
    // hiding them would lose the work rather than explain it.
    vi.mocked(predictionModelsApi.list).mockResolvedValue([model()])
    dq()
    expect(await screen.findByText('Churn model')).toBeInTheDocument()
  })

  describe('versions (E13)', () => {
    const card = {
      target: 'churn', task: 'classification', model_family: 'random forest', score: 0.91,
      score_name: 'accuracy', candidates: [{ model: 'random forest', score: 0.91 }, { model: 'logistic', score: 0.84 }],
      baseline_score: 0.55, beats_baseline: true, predictors_used: ['region', 'spend'], predictors_skipped: [],
      n_train: 225, n_test: 75, n_fitted: 300, split: { kind: 'random', test_share: 0.25 },
      row_scope: 'every row', caveats: [], trained_by: 'ana@example.com', trained_at: '2026-09-20T10:00:00',
      dataset: { id: 1, name: 'Churn', row_count: 300, content_sha256: null, last_refreshed_at: null },
    }
    const v1 = model({ id: 7, version: 1, status: 'champion', card })
    const v2 = model({ id: 8, version: 2, status: 'candidate', model_family: 'logistic', card: { ...card, model_family: 'logistic' } })

    it('shows each version of a name, the champion first and marked', async () => {
      vi.mocked(predictionModelsApi.list).mockResolvedValue([v2, v1])
      panel()
      const first = await screen.findByTestId('model-7')
      expect(first).toHaveTextContent('v1')
      expect(first).toHaveTextContent('Champion')
      expect(screen.getByTestId('model-8')).toHaveTextContent('candidate')
      const ids = screen.getAllByTestId(/^model-\d+$/).map(e => e.getAttribute('data-testid'))
      expect(ids).toEqual(['model-7', 'model-8'])
      // Only a candidate can be made champion.
      expect(screen.getAllByRole('button', { name: 'Make champion' })).toHaveLength(1)
    })

    it('makes a candidate the champion and reloads', async () => {
      vi.mocked(predictionModelsApi.list).mockResolvedValue([v1, v2])
      vi.mocked(predictionModelsApi.promote).mockResolvedValue({ ...v2, status: 'champion' } as never)
      panel()
      fireEvent.click(await screen.findByRole('button', { name: 'Make champion' }))
      await waitFor(() => expect(predictionModelsApi.promote).toHaveBeenCalledWith(1, 8))
      await waitFor(() => expect(predictionModelsApi.list).toHaveBeenCalledTimes(2))
    })

    it('opens the model card: how it was chosen and on what', async () => {
      vi.mocked(predictionModelsApi.list).mockResolvedValue([v1])
      render(<PredictionModelsPanel datasetId={1} columns={columns}
        dataset={{ row_count: 300, content_sha256: null, last_refreshed_at: null }} />)
      fireEvent.click(await screen.findByRole('button', { name: 'Model card' }))
      const c = screen.getByTestId('model-card')
      expect(c).toHaveTextContent('Trained by ana@example.com')
      expect(c).toHaveTextContent('against 0.550')
      expect(c).toHaveTextContent('refit on all 300 usable rows')
      expect(screen.getByRole('table', { name: 'Candidates compared for Churn model v1' })).toHaveTextContent('logistic')
      expect(c).not.toHaveTextContent('has changed since')
    })

    it('says when the dataset has changed since the model was trained', async () => {
      vi.mocked(predictionModelsApi.list).mockResolvedValue([v1])
      render(<PredictionModelsPanel datasetId={1} columns={columns}
        dataset={{ row_count: 420, content_sha256: null, last_refreshed_at: null }} />)
      fireEvent.click(await screen.findByRole('button', { name: 'Model card' }))
      expect(screen.getByTestId('model-card')).toHaveTextContent('The dataset has changed since this model was trained (300 rows then, 420 now)')
    })

    it('a model saved before cards says so instead of an empty card', async () => {
      vi.mocked(predictionModelsApi.list).mockResolvedValue([model({ version: 1, status: 'champion', card: null })])
      panel()
      fireEvent.click(await screen.findByRole('button', { name: 'Model card' }))
      expect(await screen.findByText(/saved before model cards were kept/)).toBeInTheDocument()
    })

    it('names the version that scored', async () => {
      vi.mocked(predictionModelsApi.list).mockResolvedValue([v1])
      vi.mocked(predictionModelsApi.score).mockResolvedValue({
        predictions: ['yes'], n_scored: 1, unseen_values: {}, target: 'churn', task: 'classification',
        model_family: 'random forest', model: { id: 7, name: 'Churn model', version: 1, status: 'champion' },
      })
      panel()
      fireEvent.click(await screen.findByRole('button', { name: 'Score this dataset' }))
      expect(await screen.findByText(/with Churn model v1/)).toBeInTheDocument()
    })
  })
})
