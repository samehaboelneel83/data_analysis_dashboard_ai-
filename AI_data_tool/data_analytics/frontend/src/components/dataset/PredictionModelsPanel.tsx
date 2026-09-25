import { useCallback, useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import { Brain } from 'lucide-react'
import EmptyState from '../ui/EmptyState'
import { useT } from '../../i18n'
import { predictionModelsApi } from '../../services/api'
import type { DatasetColumn, PredictionModelSummary, ScoreResult } from '../../services/api'

/**
 * Models kept so they can score rows they have never seen.
 *
 * Every other analysis on this dataset refits and discards, which answers "what
 * could predict this, and how well" and never "score these rows". This is the
 * surface for the other half.
 *
 * Two things here deliberately refuse to look tidier than the truth:
 *
 *   A model has NO OPINION about a category it never met during training — it
 *   encodes as "none of the above" and still returns a prediction. So unseen
 *   values are reported beside the count, because otherwise somebody scores a
 *   year of new data the model recognises none of and reads it as a forecast.
 *
 *   A refusal is shown as its reason. Scoring with a model trained on a column
 *   the reader may not see is refused by the server with an explanation they
 *   can act on; rendering that as an empty result would send them hunting a bug.
 */
export default function PredictionModelsPanel({ datasetId, columns, mode }: {
  datasetId: number
  columns: DatasetColumn[]
  /** The dataset's mode. Training reads every row and stores a derivative, so
   *  it is import-only — and a form that cannot work must say so rather than
   *  fail on the button. */
  mode?: string
}) {
  const t = useT()
  const [models, setModels] = useState<PredictionModelSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [target, setTarget] = useState('')
  const [name, setName] = useState('')
  const [partition, setPartition] = useState('')
  const [training, setTraining] = useState(false)
  const [result, setResult] = useState<ScoreResult | null>(null)
  const [scoreError, setScoreError] = useState<string | null>(null)
  const [scoringId, setScoringId] = useState<number | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setModels(await predictionModelsApi.list(datasetId))
    } catch {
      setModels([])
    } finally {
      setLoading(false)
    }
  }, [datasetId])

  useEffect(() => { void load() }, [load])

  // Partition columns: made by the prep pipeline (listed with negative ids)
  // or named as one. Training on their Training rows keeps the Validation
  // rows unseen, so the canvas can grade the saved model honestly later.
  const partitionCols = columns
    .filter(c => (typeof c.id === 'number' && c.id < 0) || /partition/i.test(c.name))
    .map(c => c.name)

  const train = async () => {
    if (!target) return
    setTraining(true)
    try {
      const made = await predictionModelsApi.train(datasetId, {
        name: name.trim() || `${target} model`, target,
        ...(partition ? { partition } : {}),
      })
      toast.success(`Saved "${made.name}"`)
      setName('')
      await load()
    } catch (e) {
      const detail = (e as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail
      toast.error(detail || 'Could not train a model on this data')
    } finally {
      setTraining(false)
    }
  }

  const score = async (m: PredictionModelSummary) => {
    setScoringId(m.id)
    setResult(null)
    setScoreError(null)
    try {
      // The dataset's own rows, which the server narrows to the caller's.
      setResult(await predictionModelsApi.score(datasetId, m.id, { from_dataset: true }))
    } catch (e) {
      const detail = (e as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail
      setScoreError(detail || 'Scoring failed')
    } finally {
      setScoringId(null)
    }
  }

  const remove = async (m: PredictionModelSummary) => {
    try {
      await predictionModelsApi.remove(datasetId, m.id)
      await load()
    } catch {
      toast.error('Could not delete that model')
    }
  }

  return (
    <div style={{ padding: 12, display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div>
        <h3 style={{ fontSize: 13, margin: '0 0 4px' }}>Saved models</h3>
        <p style={{ fontSize: 11, color: 'var(--muted)', margin: 0, maxWidth: 640 }}>
          A saved model can score rows whose outcome is not known yet. Every other
          analysis here refits and throws the model away, which answers what
          <em> could</em> be predicted rather than what a new row is likely to do.
        </p>
      </div>

      {mode === 'directquery' ? (
        // Said up front, not discovered after filling the form in. Existing
        // models are still listed below: a dataset switched to DirectQuery
        // later may carry some, and hiding them loses the work.
        <p style={{ fontSize: 12, color: 'var(--muted)', margin: 0,
          border: '1px solid var(--border)', borderRadius: 8, padding: '8px 10px' }}>
          Training needs to read every row, so it is available on
          <strong> import-mode</strong> datasets only. This one queries its
          source live.
        </p>
      ) : (
      <div style={{ display: 'flex', gap: 6, alignItems: 'flex-end', flexWrap: 'wrap' }}>
        <div>
          <label htmlFor="pm-target" style={{ display: 'block', fontSize: 11, fontWeight: 700, color: 'var(--muted)' }}>
            Predict
          </label>
          <select id="pm-target" value={target} onChange={e => setTarget(e.target.value)}
            style={{ fontSize: 12, padding: '4px 6px' }}>
            <option value="">Choose a column…</option>
            {columns.map(c => <option key={c.name} value={c.name}>{c.name}</option>)}
          </select>
        </div>
        <div>
          <label htmlFor="pm-name" style={{ display: 'block', fontSize: 11, fontWeight: 700, color: 'var(--muted)' }}>
            Name
          </label>
          <input id="pm-name" value={name} onChange={e => setName(e.target.value)}
            placeholder={target ? `${target} model` : 'Optional'}
            style={{ fontSize: 12, padding: '4px 6px' }} />
        </div>
        {partitionCols.length > 0 && (
          <div>
            <label htmlFor="pm-partition" style={{ display: 'block', fontSize: 11, fontWeight: 700, color: 'var(--muted)' }}>
              Train on
            </label>
            <select id="pm-partition" value={partition} onChange={e => setPartition(e.target.value)}
              style={{ fontSize: 12, padding: '4px 6px' }}>
              <option value="">All rows</option>
              {partitionCols.map(c => <option key={c} value={c}>Training rows of {c}</option>)}
            </select>
          </div>
        )}
        <button onClick={train} disabled={!target || training} title={!target ? 'Choose what to predict first' : undefined} className="btn btn-sm"
          style={{ fontSize: 11, padding: '5px 10px' }}>
          {training ? 'Training…' : 'Train and save'}
        </button>
      </div>
      )}

      {loading ? (
        <p style={{ fontSize: 12, color: 'var(--muted)' }}>Loading…</p>
      ) : models.length === 0 ? (
        <EmptyState icon={Brain}
          title={mode === 'directquery' ? t('models.emptyDq') : t('models.empty')}
          description={mode === 'directquery' ? undefined
            : t('models.emptyBody')} />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {models.map(m => (
            <div key={m.id} style={{
              border: '1px solid var(--border)', borderRadius: 8, padding: 10,
              display: 'flex', flexDirection: 'column', gap: 6,
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <strong style={{ fontSize: 12 }}>{m.name}</strong>
                <span style={{ fontSize: 11, color: 'var(--muted)' }}>
                  predicts <code>{m.target}</code> from {m.features.join(', ')}
                </span>
                <span style={{ marginInlineStart: 'auto', display: 'flex', gap: 6 }}>
                  <button onClick={() => void score(m)} disabled={scoringId === m.id}
                    className="btn btn-ghost btn-sm" style={{ fontSize: 11, padding: '3px 8px' }}>
                    {scoringId === m.id ? 'Scoring…' : 'Score this dataset'}
                  </button>
                  <button onClick={() => void remove(m)}
                    aria-label={`Delete ${m.name}`} title={`Delete ${m.name}`}
                    className="btn btn-ghost btn-sm" style={{ fontSize: 11, padding: '3px 8px' }}>
                    Delete
                  </button>
                </span>
              </div>
              <div style={{ fontSize: 11, color: 'var(--muted)' }}>
                {m.model_family}
                {m.score != null && <> · {m.score_name || 'score'} {m.score}</>}
              </div>
            </div>
          ))}
        </div>
      )}

      {scoreError && (
        <p style={{ fontSize: 11, color: 'var(--danger)', margin: 0 }}>{scoreError}</p>
      )}

      {result && (
        <div style={{ border: '1px solid var(--border)', borderRadius: 8, padding: 10 }}>
          <div style={{ fontSize: 12 }}>
            Scored <strong>{result.n_scored} rows</strong> for <code>{result.target}</code>.
          </div>
          {Object.keys(result.unseen_values).length > 0 && (
            <p style={{ fontSize: 11, color: '#f59e0b', margin: '6px 0 0' }}>
              The model never saw some of these values, so it has no opinion about
              them and treated them as none of the categories it knows:{' '}
              {Object.entries(result.unseen_values)
                .map(([col, vals]) => `${col}: ${vals.join(', ')}`)
                .join(' · ')}
            </p>
          )}
        </div>
      )}
    </div>
  )
}
