import { useEffect, useState } from 'react'
import { explainApi } from '../../services/api'
import { useModalDialog } from '../ui/useModalDialog'
import { useT } from '../../i18n'
import {
  FactorBars, GoalSeekAnswer, RelationshipPlot, SectionLabel,
  type Factor, type GoalSeekResult, type Relationship,
} from '../analysis/analysisResults'

interface Explanation {
  response: string
  factors: Factor[]
  relationship: Relationship | null
  note: string | null
  /** One guarded sentence describing the top factor, or null. Null is the
   *  NORMAL case in an air-gapped install: there is no model to ask, and the
   *  factors are the explanation either way. */
  narrative?: string | null
  /** What wrote the sentence. Shown, because a reader deciding something on
   *  the strength of a line has a right to know it was generated. */
  narrative_source?: string | null
}

/**
 * SAS's "explain this measure", sized to a dialog: a relative-importance bar
 * list (top factor = 1, rest proportional — numeric factors by |correlation|,
 * categorical by √eta², one comparable scale) and the top factor's
 * relationship: a scatter for numeric, group means for categorical.
 *
 * The bars, the plot and the goal-seek answer now come from
 * `analysis/analysisResults` because the same two analyses are in the registry
 * and runnable from the generic analysis panel — two hand-drawn copies of one
 * chart are two charts that drift. What stays here is this dialog's own
 * interaction: the goal-seek FORM, where a target and optional bounds are
 * typed against the column the scatter is already showing.
 */
export default function ExplainDialog({ datasetId, column, onClose }: {
  datasetId: number
  column: string
  onClose: () => void
}) {
  const dialogRef = useModalDialog<HTMLDivElement>(onClose)
  const t = useT()
  const [result, setResult] = useState<Explanation | null>(null)
  const [goalTarget, setGoalTarget] = useState('')
  const [goalMin, setGoalMin] = useState('')
  const [goalMax, setGoalMax] = useState('')
  const [goal, setGoal] = useState<GoalSeekResult | null>(null)
  const [goalError, setGoalError] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    explainApi.explain(datasetId, column).then(setResult)
      .catch(e => setError(e?.response?.data?.detail || t('bc.canvas.explainFailed')))
  }, [datasetId, column])

  const rel = result?.relationship

  return (
    <div aria-label={t('bc.canvas.whatMoves', { column })} onClick={onClose}
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.45)', zIndex: 1000,
        display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-label={t('bc.canvas.whatMoves', { column })}
          onClick={e => e.stopPropagation()}
        style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10,
          padding: 18, width: 540, maxWidth: '92vw', maxHeight: '84vh', overflowY: 'auto' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
          <strong style={{ fontSize: 13 }}>{t('bc.canvas.whatMovesQ', { column })}</strong>
          <button onClick={onClose} aria-label={t('bc.canvas.close')}
            style={{ border: 'none', background: 'none', cursor: 'pointer', fontSize: 14, color: 'var(--muted)' }}>✕</button>
        </div>

        {error && <p role="alert" dir="auto" style={{ fontSize: 12, color: 'var(--danger)' }}>{error}</p>}
        {!result && !error && <p style={{ fontSize: 12, color: 'var(--muted)' }}>{t('bc.canvas.computing')}</p>}
        {result?.note && <p dir="auto" style={{ fontSize: 12, color: 'var(--muted)' }}>{result.note}</p>}

        {result?.narrative && (
          <div style={{ border: '1px solid var(--border)', borderRadius: 8,
            padding: '8px 10px', marginBottom: 10, background: 'var(--surface2)' }}>
            <p dir="auto" style={{ fontSize: 12, margin: 0 }}>{result.narrative}</p>
            {result.narrative_source === 'model' && (
              // Named rather than implied. The numbers below are computed; this
              // line is not, and the difference matters to anyone acting on it.
              <p style={{ fontSize: 11, color: 'var(--muted)', margin: '4px 0 0' }}>
                {t('bc.canvas.generatedFromFigures')}
              </p>
            )}
          </div>
        )}

        {result && result.factors.length > 0 && (
          <>
            <SectionLabel>{t('bc.canvas.relativeImportance')}</SectionLabel>
            <FactorBars factors={result.factors} />

            {rel && (
              <>
                <SectionLabel>{t('bc.canvas.xVsY', { a: column, b: rel.column })}</SectionLabel>
                <RelationshipPlot rel={rel} />
                {rel.kind === 'scatter' && (
                  <div style={{ marginTop: 10, borderTop: '1px solid var(--border)', paddingTop: 8 }}>
                    <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 4 }}>
                      {t('bc.canvas.goalSeek')}
                    </div>
                    <div style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 12, flexWrap: 'wrap' }}>
                      {t('bc.canvas.toReach', { column })}
                      <input aria-label={t('bc.canvas.goalTarget')} type="number" value={goalTarget}
                        onChange={e => setGoalTarget(e.target.value)} style={{ width: 100, fontSize: 12 }} />
                      <button className="btn" style={{ fontSize: 11 }} disabled={goalTarget === ''} title={goalTarget === '' ? t('bc.canvas.enterGoalFirst') : undefined}
                        onClick={() => {
                          setGoal(null); setGoalError('')
                          explainApi.goalSeek(datasetId, rel.column, column, Number(goalTarget),
                            goalMin === '' ? undefined : Number(goalMin),
                            goalMax === '' ? undefined : Number(goalMax))
                            .then(setGoal)
                            .catch(e => setGoalError(e?.response?.data?.detail || t('bc.canvas.couldNotSolve')))
                        }}>{t('bc.canvas.solve')}</button>
                    </div>
                    <div style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 11, color: 'var(--muted)', marginTop: 4 }}>
                      {t('bc.canvas.bounds', { column: rel.column })}
                      <input aria-label={t('bc.canvas.factorMin')} type="number" placeholder={t('bc.canvas.min')} value={goalMin}
                        onChange={e => setGoalMin(e.target.value)} style={{ width: 70, fontSize: 11 }} />
                      –
                      <input aria-label={t('bc.canvas.factorMax')} type="number" placeholder={t('bc.canvas.max')} value={goalMax}
                        onChange={e => setGoalMax(e.target.value)} style={{ width: 70, fontSize: 11 }} />
                    </div>
                    {goal && (
                      <GoalSeekAnswer goal={goal} xName={rel.column} yName={column} />
                    )}
                    {goalError && <p role="alert" dir="auto" style={{ fontSize: 11, color: 'var(--danger)', marginTop: 4 }}>{goalError}</p>}
                  </div>
                )}
              </>
            )}
          </>
        )}
      </div>
    </div>
  )
}
