import { useCallback, useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import { Brain } from 'lucide-react'
import EmptyState from '../ui/EmptyState'
import { useT } from '../../i18n'
import { isJobActive, jobsApi, predictionModelsApi } from '../../services/api'
import { Link } from 'react-router-dom'
import type { DatasetColumn, DatasetSummaryForCard, DriftSnapshot, Job, ModelDrift, PredictionModelSummary, ScoreResult } from '../../services/api'

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
const fmt = (v: number | null | undefined) => (v == null ? '—' : Number.isInteger(v) ? String(v) : v.toFixed(3))

/** E13: how a saved model was chosen and on what, and whether the data has
 *  moved since. */
const DRIFT_WORD: Record<ModelDrift['overall'], string> = {
  stable: 'stable', moderate: 'moderate shift', major: 'major shift', missing: 'missing now',
}

/** E13: today's rows against the version's training rows, per predictor. */
function DriftCheck({ m, datasetId }: { m: PredictionModelSummary; datasetId: number }) {
  const [drift, setDrift] = useState<ModelDrift | null>(null)
  const [history, setHistory] = useState<DriftSnapshot[]>([])
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    if (!m.has_training_profile) return
    let live = true
    predictionModelsApi.driftHistory(datasetId, m.id)
      .then(h => { if (live) setHistory(h ?? []) })
      .catch(() => { /* a reader who may not use the version sees no history */ })
    return () => { live = false }
  }, [datasetId, m.id, m.has_training_profile])
  if (!m.has_training_profile) {
    return <p style={{ fontSize: 11, color: 'var(--muted)', margin: 0 }}>
      This version was saved before training profiles were kept, so drift cannot be checked. Retrain it to compare.
    </p>
  }
  const check = async () => {
    setBusy(true); setErr(null)
    try {
      const r = await predictionModelsApi.checkDrift(datasetId, m.id)
      setDrift(r); setHistory(r.history ?? [])
    }
    catch (e) { setErr((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'Could not check drift') }
    finally { setBusy(false) }
  }
  const recent = [...history].reverse().slice(0, 10)
  return (
    <div data-testid="model-drift" style={{ display: 'grid', gap: 6 }}>
      <div>
        <button type="button" className="btn btn-ghost btn-sm" disabled={busy} onClick={() => void check()}
          style={{ fontSize: 11, padding: '3px 8px' }}>
          {busy ? 'Checking…' : 'Check drift against today\'s rows'}
        </button>
      </div>
      {err && <p style={{ fontSize: 11, color: 'var(--danger)', margin: 0 }}>{err}</p>}
      {recent.length > 0 && (
        // E13: the checks kept -- the daily one for the champion, and each one
        // asked for -- newest first, so a creeping predictor shows as a trend.
        <table aria-label={`Drift over time for ${m.name} v${m.version ?? 1}`} data-testid="drift-history"
          style={{ borderCollapse: 'collapse', maxWidth: 420, fontSize: 11 }}>
          <thead><tr>
            <th style={{ textAlign: 'start', padding: '2px 8px' }}>Checked</th>
            <th style={{ textAlign: 'start', padding: '2px 8px' }}>Overall</th>
            <th style={{ textAlign: 'end', padding: '2px 8px' }}>Largest index</th>
            <th style={{ textAlign: 'end', padding: '2px 8px' }}>Rows</th>
          </tr></thead>
          <tbody>{recent.map(h => (
            <tr key={h.at}>
              <td style={{ padding: '2px 8px' }}>{new Date(h.at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}</td>
              <td style={{ padding: '2px 8px', color: h.overall === 'major' ? 'var(--danger)' : h.overall === 'moderate' ? '#b45309' : undefined }}>
                {DRIFT_WORD[h.overall] ?? h.overall}</td>
              <td style={{ textAlign: 'end', padding: '2px 8px', fontVariantNumeric: 'tabular-nums' }}>{h.max_psi == null ? '—' : h.max_psi.toFixed(3)}</td>
              <td style={{ textAlign: 'end', padding: '2px 8px', fontVariantNumeric: 'tabular-nums' }}>{h.rows?.toLocaleString() ?? '—'}</td>
            </tr>
          ))}</tbody>
        </table>
      )}
      {m.status === 'champion' && (
        <p style={{ fontSize: 10.5, color: 'var(--muted)', margin: 0 }}>The champion is checked every day; each check is kept.</p>
      )}
      {drift && (
        <>
          <div style={{ fontSize: 11.5 }}>
            Overall: <b>{DRIFT_WORD[drift.overall]}</b> over {drift.rows.toLocaleString()} rows
            {drift.trained_rows ? <> (trained on {drift.trained_rows.toLocaleString()})</> : null}.
            {drift.overall === 'major' && ' The data has moved enough that the training score no longer describes it; retrain.'}
          </div>
          <table aria-label={`Drift for ${m.name} v${m.version ?? 1}`} style={{ borderCollapse: 'collapse', maxWidth: 420 }}>
            <thead><tr>
              <th style={{ textAlign: 'start', padding: '2px 8px' }}>Predictor</th>
              <th style={{ textAlign: 'end', padding: '2px 8px' }}>Stability index</th>
              <th style={{ textAlign: 'start', padding: '2px 8px' }}>Reading</th>
            </tr></thead>
            <tbody>
              {drift.features.map(f => (
                <tr key={f.feature}>
                  <td style={{ padding: '2px 8px' }}>{f.feature}</td>
                  <td style={{ textAlign: 'end', padding: '2px 8px', fontVariantNumeric: 'tabular-nums' }}>{f.psi == null ? '—' : f.psi.toFixed(3)}</td>
                  <td style={{ padding: '2px 8px', color: f.level === 'major' ? 'var(--danger)' : f.level === 'moderate' ? '#b45309' : undefined }}>
                    {DRIFT_WORD[f.level]}{f.new_values?.length ? ` (new: ${f.new_values.join(', ')})` : ''}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  )
}

export function ModelCardView({ m, dataset, datasetId }: { m: PredictionModelSummary; dataset?: DatasetSummaryForCard; datasetId?: number }) {
  const c = m.card
  if (!c) {
    return <p style={{ fontSize: 11, color: 'var(--muted)', margin: 0 }}>
      This model was saved before model cards were kept, so how it was chosen was not recorded.
    </p>
  }
  const then = c.dataset
  const changed = !!(then && dataset && (
    (then.content_sha256 && dataset.content_sha256 && then.content_sha256 !== dataset.content_sha256)
    || (then.row_count != null && dataset.row_count != null && then.row_count !== dataset.row_count)
    || (!!then.last_refreshed_at && !!dataset.last_refreshed_at
        && new Date(then.last_refreshed_at).getTime() !== new Date(dataset.last_refreshed_at).getTime())))
  const split = c.split?.kind === 'partition' ? `the Training rows of ${c.split.column ?? c.partition}`
    : c.split ? `a random ${Math.round((1 - (c.split.test_share ?? 0.25)) * 100)}% of rows` : '—'
  const skipped = (c.predictors_skipped ?? []).map(s => typeof s === 'string' ? s : `${s.column}${s.reason ? ` (${s.reason})` : ''}`)
  return (
    <div data-testid="model-card" style={{ fontSize: 11.5, display: 'grid', gap: 6 }}>
      {changed && (
        <p role="status" style={{ margin: 0, color: '#b45309' }}>
          The dataset has changed since this model was trained ({then?.row_count ?? '?'} rows then,
          {' '}{dataset?.row_count ?? '?'} now). Its score describes the data it saw; retrain to grade it on today's.
        </p>
      )}
      <div>Trained by <b>{c.trained_by ?? 'unknown'}</b> on {c.trained_at?.replace('T', ' ') ?? '—'}, over {c.row_scope ?? 'every row'}.</div>
      <div>
        Chosen on {split}: <b>{c.model_family}</b> scored {c.score_name} {fmt(c.score)} on {c.n_test ?? '?'} held-out rows,
        against {fmt(c.baseline_score)} for a model that always guesses the usual answer
        {c.beats_baseline === false ? <b> — it does not beat that guess.</b> : '.'} It was then refit on all {c.n_fitted ?? '?'} usable rows.
      </div>
      {(c.candidates?.length ?? 0) > 0 && (
        <table aria-label={`Candidates compared for ${m.name} v${m.version ?? 1}`} style={{ borderCollapse: 'collapse', maxWidth: 360 }}>
          <thead><tr><th style={{ textAlign: 'start', padding: '2px 8px' }}>Candidate</th>
            <th style={{ textAlign: 'end', padding: '2px 8px' }}>{c.score_name || 'score'}</th></tr></thead>
          <tbody>
            {c.candidates!.map(k => (
              <tr key={k.model}><td style={{ padding: '2px 8px' }}>{k.model}{k.model === c.model_family ? ' ★' : ''}</td>
                <td style={{ textAlign: 'end', padding: '2px 8px', fontVariantNumeric: 'tabular-nums' }}>{fmt(k.score)}</td></tr>
            ))}
          </tbody>
        </table>
      )}
      <div>Predictors: {(c.predictors_used ?? m.features).join(', ') || '—'}
        {skipped.length > 0 && <> · left out: {skipped.join(', ')}</>}</div>
      {(c.caveats?.length ?? 0) > 0 && <ul style={{ margin: 0, paddingInlineStart: 18 }}>{c.caveats!.map(x => <li key={x}>{x}</li>)}</ul>}
      {datasetId != null && <DriftCheck m={m} datasetId={datasetId} />}
    </div>
  )
}

export default function PredictionModelsPanel({ datasetId, columns, mode, dataset }: {
  datasetId: number
  columns: DatasetColumn[]
  /** The dataset's mode. Training reads every row and stores a derivative, so
   *  it is import-only — and a form that cannot work must say so rather than
   *  fail on the button. */
  mode?: string
  /** The dataset as it is now, for the card's "changed since training". */
  dataset?: DatasetSummaryForCard
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
  const [cardFor, setCardFor] = useState<number | null>(null)
  // E13: batch scoring jobs, followed until they finish.
  const [scoreJobs, setScoreJobs] = useState<Record<number, Job>>({})
  useEffect(() => {
    const active = Object.values(scoreJobs).filter(isJobActive)
    if (!active.length) return
    const id = setInterval(() => {
      active.forEach(j => {
        jobsApi.get(j.id).then(next => setScoreJobs(s => {
          const mid = Number(Object.keys(s).find(k => s[Number(k)].id === j.id))
          return Number.isNaN(mid) ? s : { ...s, [mid]: next }
        })).catch(() => {})
      })
    }, 2000)
    return () => clearInterval(id)
  }, [scoreJobs])
  const queueScore = async (m: PredictionModelSummary) => {
    try {
      const j = await predictionModelsApi.scoreJob(datasetId, m.id)
      setScoreJobs(s => ({ ...s, [m.id]: { ...(j as unknown as Job), state: j.state as Job['state'] } }))
      toast.success(`Predicting with ${m.name} v${m.version ?? 1}: the result will be a new dataset`)
    } catch (e) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      toast.error(detail || 'Could not start scoring')
    }
  }

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

  const promote = async (m: PredictionModelSummary) => {
    try {
      await predictionModelsApi.promote(datasetId, m.id)
      toast.success(`v${m.version ?? 1} of "${m.name}" is now the champion`)
      await load()
    } catch (e) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      toast.error(detail || 'Could not make that version the champion')
    }
  }

  // Each name's versions together, the champion first, then newest first.
  const ordered = [...models].sort((a, b) => a.name.localeCompare(b.name)
    || Number(b.status === 'champion') - Number(a.status === 'champion')
    || (b.version ?? 1) - (a.version ?? 1))

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

      {mode === 'directquery' && (
        // HR re-test 2026-10-01: training used to be refused here while every
        // model WIDGET fitted on the same live data. It now reads the rows
        // live, secured as the reader, up to the analysis cap.
        <p data-testid="models-dq-note" style={{ fontSize: 12, color: 'var(--muted)', margin: 0,
          border: '1px solid var(--border)', borderRadius: 8, padding: '8px 10px' }}>
          {t('models.dqTrainNote')}
        </p>
      )}
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

      {loading ? (
        <p style={{ fontSize: 12, color: 'var(--muted)' }}>Loading…</p>
      ) : models.length === 0 ? (
        <EmptyState icon={Brain}
          title={mode === 'directquery' ? t('models.emptyDq') : t('models.empty')}
          description={mode === 'directquery' ? undefined
            : t('models.emptyBody')} />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {ordered.map(m => (
            <div key={m.id} data-testid={`model-${m.id}`} style={{
              border: '1px solid var(--border)', borderRadius: 8, padding: 10,
              display: 'flex', flexDirection: 'column', gap: 6,
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <strong style={{ fontSize: 12 }}>{m.name}</strong>
                <span style={{ fontSize: 11, color: 'var(--muted)' }}>v{m.version ?? 1}</span>
                {m.status === 'champion'
                  ? <span style={{ fontSize: 10.5, fontWeight: 700, color: 'var(--accent)', border: '1px solid var(--accent)',
                      borderRadius: 999, padding: '0 6px' }}>Champion</span>
                  : <span style={{ fontSize: 10.5, color: 'var(--muted)' }}>candidate</span>}
                <span style={{ fontSize: 11, color: 'var(--muted)' }}>
                  predicts <code>{m.target}</code> from {m.features.join(', ')}
                </span>
                <span style={{ marginInlineStart: 'auto', display: 'flex', gap: 6 }}>
                  {m.status !== 'champion' && (
                    <button onClick={() => void promote(m)} className="btn btn-ghost btn-sm" style={{ fontSize: 11, padding: '3px 8px' }}
                      title="Dashboards that follow the champion score with this version from now on">
                      Make champion
                    </button>
                  )}
                  <button onClick={() => setCardFor(cardFor === m.id ? null : m.id)} aria-expanded={cardFor === m.id}
                    className="btn btn-ghost btn-sm" style={{ fontSize: 11, padding: '3px 8px' }}>
                    Model card
                  </button>
                  {mode !== 'directquery' && (
                    <button onClick={() => void queueScore(m)} disabled={!!scoreJobs[m.id] && isJobActive(scoreJobs[m.id])}
                      className="btn btn-ghost btn-sm" style={{ fontSize: 11, padding: '3px 8px' }}
                      title="Predict every row you can see and keep the result as a new dataset">
                      Save predictions as a dataset
                    </button>
                  )}
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
              {scoreJobs[m.id] && (
                <div data-testid={`score-job-${m.id}`} role="status" style={{ fontSize: 11.5 }}>
                  {isJobActive(scoreJobs[m.id]) ? <>Scoring… ({String(scoreJobs[m.id].progress?.stage ?? scoreJobs[m.id].state)})</>
                    : scoreJobs[m.id].state === 'succeeded' && scoreJobs[m.id].result?.dataset_id ? (
                      <>Scored {Number((scoreJobs[m.id].result as { rows?: number } | null)?.rows ?? 0).toLocaleString()} rows:{' '}
                        <Link to={`/datasets/${scoreJobs[m.id].result!.dataset_id}`}>open the scored dataset</Link></>
                    ) : <span style={{ color: 'var(--danger)' }}>Scoring failed: {scoreJobs[m.id].error ?? scoreJobs[m.id].state}</span>}
                </div>
              )}
              {cardFor === m.id && <ModelCardView m={m} dataset={dataset} datasetId={datasetId} />}
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
            Scored <strong>{result.n_scored} rows</strong> for <code>{result.target}</code>
            {result.model && <> with {result.model.name} v{result.model.version}</>}.
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
