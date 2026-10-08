import { useCallback, useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import { Brain } from 'lucide-react'
import EmptyState from '../ui/EmptyState'
import { useConfirm } from '../ui/ConfirmDialog'
import { useT, type TranslateFn } from '../../i18n'
import { familyLabel, rich } from '../../i18n/pages/modelsMaps'
import { isJobActive, jobsApi, predictionModelsApi } from '../../services/api'
import { Link } from 'react-router-dom'
import '../../pages/datasetDetail/models.css'
import type { DatasetColumn, DatasetSummaryForCard, DriftSnapshot, Job, ModelDrift, PredictionModelSummary, ScoreResult } from '../../services/api'
import { formatDate } from '../../lib/dateFormat'

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
const DRIFT_KEY = {
  stable: 'pg.modelsMaps.drift.stable', moderate: 'pg.modelsMaps.drift.moderate',
  major: 'pg.modelsMaps.drift.major', missing: 'pg.modelsMaps.drift.missing',
} as const
const driftWord = (t: TranslateFn, level: string) =>
  level in DRIFT_KEY ? t(DRIFT_KEY[level as ModelDrift['overall']]) : level

/** E13: today's rows against the version's training rows, per predictor. */
function DriftCheck({ m, datasetId }: { m: PredictionModelSummary; datasetId: number }) {
  const t = useT()
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
    return <p style={{ fontSize: 11, color: 'var(--muted)', margin: 0 }}>{t('pg.modelsMaps.pm.noProfile')}</p>
  }
  const check = async () => {
    setBusy(true); setErr(null)
    try {
      const r = await predictionModelsApi.checkDrift(datasetId, m.id)
      setDrift(r); setHistory(r.history ?? [])
    }
    catch (e) { setErr((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail || t('pg.modelsMaps.pm.driftFailed')) }
    finally { setBusy(false) }
  }
  const recent = [...history].reverse().slice(0, 10)
  return (
    <div data-testid="model-drift" style={{ display: 'grid', gap: 6 }}>
      <div>
        <button type="button" className="btn btn-ghost btn-sm" disabled={busy} onClick={() => void check()}
          style={{ fontSize: 11, padding: '3px 8px' }}>
          {busy ? t('pg.modelsMaps.pm.checking') : t('pg.modelsMaps.pm.checkDrift')}
        </button>
      </div>
      {err && <p style={{ fontSize: 11, color: 'var(--danger)', margin: 0 }}>{err}</p>}
      {recent.length > 0 && (
        // E13: the checks kept -- the daily one for the champion, and each one
        // asked for -- newest first, so a creeping predictor shows as a trend.
        <table aria-label={t('pg.modelsMaps.pm.driftHistoryAria', { name: m.name, v: m.version ?? 1 })} data-testid="drift-history"
          style={{ borderCollapse: 'collapse', maxWidth: 420, fontSize: 11 }}>
          <thead><tr>
            <th style={{ textAlign: 'start', padding: '2px 8px' }}>{t('pg.modelsMaps.pm.colChecked')}</th>
            <th style={{ textAlign: 'start', padding: '2px 8px' }}>{t('pg.modelsMaps.pm.colOverall')}</th>
            <th style={{ textAlign: 'end', padding: '2px 8px' }}>{t('pg.modelsMaps.pm.colLargest')}</th>
            <th style={{ textAlign: 'end', padding: '2px 8px' }}>{t('pg.modelsMaps.pm.colRows')}</th>
          </tr></thead>
          <tbody>{recent.map(h => (
            <tr key={h.at}>
              <td style={{ padding: '2px 8px' }}>{new Date(h.at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}</td>
              <td style={{ padding: '2px 8px', color: h.overall === 'major' ? 'var(--danger)' : h.overall === 'moderate' ? '#b45309' : undefined }}>
                {driftWord(t, h.overall)}</td>
              <td style={{ textAlign: 'end', padding: '2px 8px', fontVariantNumeric: 'tabular-nums' }}>{h.max_psi == null ? '—' : h.max_psi.toFixed(3)}</td>
              <td style={{ textAlign: 'end', padding: '2px 8px', fontVariantNumeric: 'tabular-nums' }}>{h.rows?.toLocaleString() ?? '—'}</td>
            </tr>
          ))}</tbody>
        </table>
      )}
      {m.status === 'champion' && (
        <p style={{ fontSize: 10.5, color: 'var(--muted)', margin: 0 }}>{t('pg.modelsMaps.pm.championDaily')}</p>
      )}
      {drift && (
        <>
          <div style={{ fontSize: 11.5 }}>
            {rich(t, drift.trained_rows ? 'pg.modelsMaps.pm.overallTrained' : 'pg.modelsMaps.pm.overall', {
              word: <b>{driftWord(t, drift.overall)}</b>,
              rows: drift.rows.toLocaleString(), trained: drift.trained_rows?.toLocaleString() ?? '',
            })}
            {drift.overall === 'major' && <> {t('pg.modelsMaps.pm.driftMajor')}</>}
          </div>
          <table aria-label={t('pg.modelsMaps.pm.driftAria', { name: m.name, v: m.version ?? 1 })} style={{ borderCollapse: 'collapse', maxWidth: 420 }}>
            <thead><tr>
              <th style={{ textAlign: 'start', padding: '2px 8px' }}>{t('pg.modelsMaps.pm.colPredictor')}</th>
              <th style={{ textAlign: 'end', padding: '2px 8px' }}>{t('pg.modelsMaps.pm.colStability')}</th>
              <th style={{ textAlign: 'start', padding: '2px 8px' }}>{t('pg.modelsMaps.pm.colReading')}</th>
            </tr></thead>
            <tbody>
              {drift.features.map(f => (
                <tr key={f.feature}>
                  <td style={{ padding: '2px 8px' }}><bdi>{f.feature}</bdi></td>
                  <td style={{ textAlign: 'end', padding: '2px 8px', fontVariantNumeric: 'tabular-nums' }}>{f.psi == null ? '—' : f.psi.toFixed(3)}</td>
                  <td style={{ padding: '2px 8px', color: f.level === 'major' ? 'var(--danger)' : f.level === 'moderate' ? '#b45309' : undefined }}>
                    {f.new_values?.length
                      ? t('pg.modelsMaps.pm.withNew', { word: driftWord(t, f.level), list: f.new_values.join(', ') })
                      : driftWord(t, f.level)}
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
  const t = useT()
  const c = m.card
  if (!c) {
    return <p style={{ fontSize: 11, color: 'var(--muted)', margin: 0 }}>{t('pg.modelsMaps.pm.noCard')}</p>
  }
  const then = c.dataset
  const changed = !!(then && dataset && (
    (then.content_sha256 && dataset.content_sha256 && then.content_sha256 !== dataset.content_sha256)
    || (then.row_count != null && dataset.row_count != null && then.row_count !== dataset.row_count)
    || (!!then.last_refreshed_at && !!dataset.last_refreshed_at
        && new Date(then.last_refreshed_at).getTime() !== new Date(dataset.last_refreshed_at).getTime())))
  const split = c.split?.kind === 'partition' ? t('pg.modelsMaps.pm.splitPartition', { col: c.split.column ?? c.partition ?? '' })
    : c.split ? t('pg.modelsMaps.pm.splitRandom', { pct: Math.round((1 - (c.split.test_share ?? 0.25)) * 100) }) : '—'
  const skipped = (c.predictors_skipped ?? []).map(s => typeof s === 'string' ? s : `${s.column}${s.reason ? ` (${s.reason})` : ''}`)
  return (
    <div data-testid="model-card" style={{ fontSize: 11.5, display: 'grid', gap: 6 }}>
      {changed && (
        <p role="status" style={{ margin: 0, color: '#b45309' }}>
          {t('pg.modelsMaps.pm.cardChanged', { then: then?.row_count ?? '?', now: dataset?.row_count ?? '?' })}
        </p>
      )}
      <div>{rich(t, 'pg.modelsMaps.pm.trainedBy', {
        who: <b><bdi>{c.trained_by ?? t('pg.modelsMaps.pm.unknown')}</bdi></b>,
        when: <bdi dir="ltr">{c.trained_at?.replace('T', ' ') ?? '—'}</bdi>,
        // The server's default scope is a phrase; any other scope is the filter as written.
        scope: c.row_scope && c.row_scope !== 'every row' ? <bdi>{c.row_scope}</bdi> : t('pg.modelsMaps.pm.everyRow'),
      })}</div>
      <div>
        {rich(t, c.beats_baseline === false ? 'pg.modelsMaps.pm.chosenNoBeat' : 'pg.modelsMaps.pm.chosen', {
          split,
          family: <b><bdi>{familyLabel(t, c.model_family)}</bdi></b>,
          metric: <bdi>{c.score_name}</bdi>,
          score: <bdi dir="ltr">{fmt(c.score)}</bdi>,
          n: c.n_test ?? '?',
          baseline: <bdi dir="ltr">{fmt(c.baseline_score)}</bdi>,
          warn: <b>{t('pg.modelsMaps.pm.noBeatGuess')}</b>,
          fitted: c.n_fitted ?? '?',
        })}
      </div>
      {(c.candidates?.length ?? 0) > 0 && (
        <table aria-label={t('pg.modelsMaps.pm.candidatesAria', { name: m.name, v: m.version ?? 1 })} style={{ borderCollapse: 'collapse', maxWidth: 360 }}>
          <thead><tr><th style={{ textAlign: 'start', padding: '2px 8px' }}>{t('pg.modelsMaps.pm.colCandidate')}</th>
            <th style={{ textAlign: 'end', padding: '2px 8px' }}>{c.score_name || t('pg.modelsMaps.pm.score')}</th></tr></thead>
          <tbody>
            {c.candidates!.map(k => (
              <tr key={k.model}><td style={{ padding: '2px 8px' }}><bdi>{familyLabel(t, k.model)}</bdi>{k.model === c.model_family ? ' ★' : ''}</td>
                <td style={{ textAlign: 'end', padding: '2px 8px', fontVariantNumeric: 'tabular-nums' }}>{fmt(k.score)}</td></tr>
            ))}
          </tbody>
        </table>
      )}
      <div>{rich(t, skipped.length > 0 ? 'pg.modelsMaps.pm.predictorsSkipped' : 'pg.modelsMaps.pm.predictors', {
        list: <bdi>{(c.predictors_used ?? m.features).join(', ') || '—'}</bdi>,
        skipped: <bdi>{skipped.join(', ')}</bdi>,
      })}</div>
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
  const confirm = useConfirm()
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
      toast.success(t('pg.modelsMaps.pm.queued', { name: m.name, v: m.version ?? 1 }))
    } catch (e) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      toast.error(detail || t('pg.modelsMaps.pm.queueFailed'))
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
        name: name.trim() || t('pg.modelsMaps.pm.defaultName', { target }), target,
        ...(partition ? { partition } : {}),
      })
      toast.success(t('pg.modelsMaps.pm.saved', { name: made.name }))
      setName('')
      await load()
    } catch (e) {
      const detail = (e as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail
      toast.error(detail || t('pg.modelsMaps.pm.trainFailed'))
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
      setScoreError(detail || t('pg.modelsMaps.pm.scoreFailed'))
    } finally {
      setScoringId(null)
    }
  }

  const promote = async (m: PredictionModelSummary) => {
    try {
      await predictionModelsApi.promote(datasetId, m.id)
      toast.success(t('pg.modelsMaps.pm.promoted', { name: m.name, v: m.version ?? 1 }))
      await load()
    } catch (e) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      toast.error(detail || t('pg.modelsMaps.pm.promoteFailed'))
    }
  }

  // Each name's versions together, the champion first, then newest first.
  const ordered = [...models].sort((a, b) => a.name.localeCompare(b.name)
    || Number(b.status === 'champion') - Number(a.status === 'champion')
    || (b.version ?? 1) - (a.version ?? 1))

  const remove = async (m: PredictionModelSummary) => {
    // QA5b S1: this deleted on one click, with no question at all.
    if (!await confirm({ title: t('bc.dialogs.deleteNamed', { name: m.name }), body: t('bc.dialogs.cannotUndo') })) return
    try {
      await predictionModelsApi.remove(datasetId, m.id)
      await load()
    } catch {
      toast.error(t('pg.modelsMaps.pm.deleteFailed'))
    }
  }

  /** "r2" as people write it. */
  const scoreName = (n?: string | null) => (!n ? t('pg.modelsMaps.pm.score') : /^r2$/i.test(n) ? 'R²' : n)
  /** The fit as a 0..1 bar when the score is one (R², accuracy, AUC). */
  const fitShare = (m: PredictionModelSummary) =>
    m.score != null && m.score >= 0 && m.score <= 1 ? m.score : null
  const fitWords = (m: PredictionModelSummary) => {
    const share = fitShare(m)
    if (share == null) return null
    const pct = Math.round(share * 100)
    if (/r2|r²/i.test(m.score_name ?? '')) {
      return t('mdl3.explains', { pct, target: m.target })
        + (m.card?.beats_baseline === false ? ` ${t('mdl3.noBeatAvg')}` : '')
    }
    return m.card?.beats_baseline === false ? t('mdl3.noBeat') : null
  }

  return (
    <div className="dl-models">
      {mode === 'directquery' && (
        // HR re-test 2026-10-01: training used to be refused here while every
        // model WIDGET fitted on the same live data. It now reads the rows
        // live, secured as the reader, up to the analysis cap.
        <p data-testid="models-dq-note" className="dl-models__note">{t('models.dqTrainNote')}</p>
      )}
      <section className="dl-models__card dl-models__train">
        <div className="dl-models__train-row">
          <strong>{t('mdl3.train')}</strong>
          <label htmlFor="pm-target">{t('mdl3.predict')}</label>
          <select id="pm-target" value={target} onChange={e => setTarget(e.target.value)}>
            <option value="">{t('mdl3.chooseColumn')}</option>
            {columns.map(c => <option key={c.name} value={c.name}>{c.name}</option>)}
          </select>
          <span>{t('mdl3.fromAll')}</span>
          {partitionCols.length > 0 && (
            <>
              <label htmlFor="pm-partition">{t('mdl3.trainOn')}</label>
              <select id="pm-partition" value={partition} onChange={e => setPartition(e.target.value)}>
                <option value="">{t('mdl3.allRows')}</option>
                {partitionCols.map(c => <option key={c} value={c}>{t('mdl3.trainingRowsOf', { col: c })}</option>)}
              </select>
            </>
          )}
          <label htmlFor="pm-name" className="dl-sr-only">{t('mdl3.name')}</label>
          <input id="pm-name" value={name} onChange={e => setName(e.target.value)}
            placeholder={target ? t('pg.modelsMaps.pm.defaultName', { target }) : t('mdl3.nameOptional')} />
          <button onClick={train} disabled={!target || training} title={!target ? t('pg.modelsMaps.pm.chooseTargetFirst') : undefined}
            className="btn btn-primary btn-sm">
            {training ? t('mdl3.training') : t('mdl3.trainSave')}
          </button>
        </div>
        <p>{t('mdl3.trainNote')}</p>
      </section>

      {loading ? (
        <p className="dl-models__note">{t('pg.modelsMaps.loading')}</p>
      ) : models.length === 0 ? (
        <section className="dl-models__card">
          <EmptyState icon={Brain}
            title={mode === 'directquery' ? t('models.emptyDq') : t('models.empty')}
            description={mode === 'directquery' ? undefined : t('models.emptyBody')} />
        </section>
      ) : (
        ordered.map(m => {
          const c = m.card
          const share = fitShare(m)
          const words = fitWords(m)
          const then = c?.dataset
          const changed = !!(then && dataset && then.row_count != null && dataset.row_count != null && then.row_count !== dataset.row_count)
          return (
            <section key={m.id} data-testid={`model-${m.id}`} className="dl-models__card dl-models__model">
              <div className="dl-models__main">
                <div className="dl-models__title">
                  <h3 dir="auto">{m.name}</h3>
                  <span className="dl-models__pill">v{m.version ?? 1}</span>
                  {m.status === 'champion'
                    ? <span className="dl-models__pill dl-models__pill--champ">{t('mdl3.champion')}</span>
                    : <span className="dl-models__pill">{t('mdl3.candidate')}</span>}
                </div>
                <p className="dl-models__predicts">{t('mdl3.predicts', { target: m.target, from: m.features.join(', ') })}</p>
                <div className="dl-models__fit">
                  <div className="dl-models__fit-head">
                    <strong>{t('mdl3.fit')}</strong>
                    <span>{m.score != null ? <>{scoreName(m.score_name)} {m.score}</> : '—'}</span>
                  </div>
                  {share != null && <div className="dl-models__bar"><span style={{ inlineSize: `${share * 100}%` }} /></div>}
                  {words && <p>{words}</p>}
                </div>
                {changed && (
                  <p role="status" className="dl-models__warn">
                    <strong>{t('mdl3.changed')}</strong>{' '}
                    {t('mdl3.changedBody', { now: dataset?.row_count?.toLocaleString() ?? '?', then: then?.row_count?.toLocaleString() ?? '?' })}
                  </p>
                )}
                {scoreJobs[m.id] && (
                  <div data-testid={`score-job-${m.id}`} role="status" className="dl-models__note">
                    {isJobActive(scoreJobs[m.id])
                      ? t('pg.modelsMaps.pm.jobRunning', { stage: String(scoreJobs[m.id].progress?.stage ?? scoreJobs[m.id].state) })
                      : scoreJobs[m.id].state === 'succeeded' && scoreJobs[m.id].result?.dataset_id ? rich(t, 'pg.modelsMaps.pm.jobDone', {
                          n: Number((scoreJobs[m.id].result as { rows?: number } | null)?.rows ?? 0).toLocaleString(),
                          link: <Link to={`/datasets/${scoreJobs[m.id].result!.dataset_id}`}>{t('pg.modelsMaps.pm.openScored')}</Link>,
                        })
                      : <span style={{ color: 'var(--danger)' }}>{t('pg.modelsMaps.pm.jobFailed', { error: String(scoreJobs[m.id].error ?? scoreJobs[m.id].state) })}</span>}
                  </div>
                )}
                <div className="dl-models__actions">
                  <button onClick={() => void score(m)} disabled={scoringId === m.id} className="btn btn-primary btn-sm">
                    {scoringId === m.id ? t('mdl3.scoring') : t('mdl3.score')}
                  </button>
                  {mode !== 'directquery' && (
                    <button onClick={() => void queueScore(m)} disabled={!!scoreJobs[m.id] && isJobActive(scoreJobs[m.id])}
                      className="btn btn-sm" title={t('pg.modelsMaps.pm.saveAllTitle')}>
                      {t('mdl3.savePredictions')}
                    </button>
                  )}
                  {m.status !== 'champion' && (
                    <button onClick={() => void promote(m)} className="btn btn-sm"
                      title={t('pg.modelsMaps.pm.championTitle')}>
                      {t('mdl3.makeChampion')}
                    </button>
                  )}
                  <button onClick={() => setCardFor(cardFor === m.id ? null : m.id)} aria-expanded={cardFor === m.id} className="btn btn-sm">
                    {t('mdl3.card')}
                  </button>
                  <button onClick={() => void remove(m)} aria-label={t('pg.modelsMaps.pm.deleteNamed', { name: m.name })} title={t('pg.modelsMaps.pm.deleteNamed', { name: m.name })}
                    className="dl-ov__linkish dl-models__delete">
                    {t('mdl3.delete')}
                  </button>
                </div>
                {cardFor === m.id && <ModelCardView m={m} dataset={dataset} datasetId={datasetId} />}
              </div>
              <aside className="dl-models__facts">
                <dl>
                  <div><dt>{t('mdl3.approach')}</dt><dd>{familyLabel(t, m.model_family)}</dd></div>
                  <div><dt>{t('mdl3.baseline')}</dt><dd>{c?.baseline_score != null ? `${scoreName(m.score_name)} ${fmt(c.baseline_score)}` : '—'}</dd></div>
                  <div><dt>{t('mdl3.testedOn')}</dt><dd>{c?.n_test != null ? t('mdl3.heldOut', { n: c.n_test.toLocaleString() }) : '—'}</dd></div>
                  <div><dt>{t('mdl3.trainedOn')}</dt><dd>{c?.n_fitted != null ? t('mdl3.rows', { n: c.n_fitted.toLocaleString() }) : '—'}</dd></div>
                  <div><dt>{t('mdl3.drift')}</dt><dd>{m.last_drift ? driftWord(t, m.last_drift.overall) : t('mdl3.notChecked')}</dd></div>
                  <div><dt>{t('mdl3.trainedBy')}</dt><dd>{c?.trained_by ?? '—'}{c?.trained_at ? ` · ${formatDate(c.trained_at, 'date')}` : ''}</dd></div>
                </dl>
                {(c?.candidates?.length ?? 0) > 1 && (
                  <p>{t('mdl3.alsoTried', { list: c!.candidates!.filter(k => k.model !== c!.model_family)
                    .map(k => `${familyLabel(t, k.model)} (${scoreName(c!.score_name)} ${fmt(k.score)})`).join(', ') })}</p>
                )}
              </aside>
            </section>
          )
        })
      )}

      {scoreError && <p className="dl-models__error">{scoreError}</p>}

      {result && (
        <section className="dl-models__card">
          <div style={{ fontSize: 13 }}>
            {rich(t, result.model ? 'pg.modelsMaps.pm.scoredForWith' : 'pg.modelsMaps.pm.scoredFor', {
              rows: <strong>{t('pg.modelsMaps.rows', { n: result.n_scored })}</strong>,
              target: <code>{result.target}</code>,
              model: result.model ? `${result.model.name} v${result.model.version}` : '',
            })}
          </div>
          {Object.keys(result.unseen_values).length > 0 && (
            <p style={{ fontSize: 12, color: 'var(--mc-warning, #a46b16)', margin: '6px 0 0' }}>
              {t('pg.modelsMaps.pm.unseen', { list: Object.entries(result.unseen_values)
                .map(([col, vals]) => `${col}: ${vals.join(', ')}`)
                .join(' · ') })}
            </p>
          )}
        </section>
      )}
    </div>
  )
}
