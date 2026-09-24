/**
 * Model-specific settings for the model widgets (Phase 3): the logistic event
 * level, a tree's depth, and which models a comparison weighs.
 *
 * Kept out of WidgetConfigPanel's hundred useStates: the panel holds ONE
 * `modelOpts` object seeded from the config, and this component edits it.
 */
import { useEffect, useState } from 'react'
import type { ReportPage, Widget } from '../../types/report'
import { predictionModelsApi, type PredictionModelSummary } from '../../services/api'
import {
  type ModelSpec, candidateBlockReason, compareCandidates, refreshSnapshots, staleSnapshots,
} from '../../lib/modelCompare'

export interface ModelOpts {
  prediction_model_id?: number
  event_value?: string
  max_depth?: number
  compare?: ModelSpec[]
}

export function seedModelOpts(cfg: Record<string, unknown>): ModelOpts {
  const o: ModelOpts = {}
  if (typeof cfg.event_value === 'string' && cfg.event_value) o.event_value = cfg.event_value
  if (typeof cfg.prediction_model_id === 'number') o.prediction_model_id = cfg.prediction_model_id
  if (typeof cfg.max_depth === 'number') o.max_depth = cfg.max_depth
  if (Array.isArray(cfg.compare)) o.compare = cfg.compare as ModelSpec[]
  return o
}

/** The keys this widget type writes; nothing for a type that ignores them. */
export function modelOptsConfig(wt: string, o: ModelOpts): Record<string, unknown> {
  if (wt === 'model_logistic' && o.event_value) return { event_value: o.event_value }
  if (wt === 'model_tree' && o.max_depth) return { max_depth: o.max_depth }
  if (wt === 'model_compare') return { compare: o.compare ?? [] }
  if (wt === 'model_score') {
    return {
      ...(o.prediction_model_id ? { prediction_model_id: o.prediction_model_id } : {}),
      ...(o.event_value ? { event_value: o.event_value } : {}),
    }
  }
  return {}
}

const lbl: React.CSSProperties = { display: 'block', fontSize: 10, fontWeight: 700, color: 'var(--muted)',
  textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 4 }
const hint: React.CSSProperties = { fontSize: 9.5, color: 'var(--muted)', marginTop: 3 }

/** Picks the saved model a scoring widget applies. Lists only models this
 *  viewer may use -- the server already omits any trained on a column they
 *  are denied, so nothing is offered that would then be refused. */
function SavedModelPicker({ datasetId, value, onChange }: {
  datasetId: number | null; value: ModelOpts; onChange: (next: ModelOpts) => void
}) {
  const [models, setModels] = useState<PredictionModelSummary[] | null>(null)
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    if (!datasetId) return
    let live = true
    predictionModelsApi.list(datasetId)
      .then(m => { if (live) setModels(m) })
      .catch(() => { if (live) setFailed(true) })
    return () => { live = false }
  }, [datasetId])
  const chosen = models?.find(m => m.id === value.prediction_model_id)
  return (
    <div style={{ marginBottom: 12 }} data-testid="saved-model-picker">
      <label htmlFor="saved-model" style={lbl}>Saved model *</label>
      {!datasetId ? (
        <div role="status" style={{ fontSize: 11.5, color: 'var(--muted)' }}>Attach a dataset first.</div>
      ) : failed ? (
        <div role="status" style={{ fontSize: 11.5, color: 'var(--muted)' }}>Could not load the saved models.</div>
      ) : models && models.length === 0 ? (
        <div role="status" style={{ fontSize: 11.5, color: 'var(--muted)' }}>
          No saved model on this dataset yet. Train one from the dataset's Prediction models panel
          (or save the champion of an Automated prediction), then pick it here.
        </div>
      ) : (
        <select id="saved-model" value={value.prediction_model_id ?? ''} style={{ width: '100%' }}
          onChange={e => onChange({ ...value, prediction_model_id: e.target.value ? Number(e.target.value) : undefined })}>
          <option value="">{models ? '— choose a model —' : 'Loading…'}</option>
          {(models ?? []).map(m => (
            <option key={m.id} value={m.id}>{m.name} — predicts {m.target} ({m.model_family})</option>
          ))}
        </select>
      )}
      {chosen?.task === 'classification' && (
        <>
          <label htmlFor="score-event" style={{ ...lbl, marginTop: 8 }}>Outcome to count</label>
          <input id="score-event" value={value.event_value ?? ''} placeholder="blank = the rarer predicted outcome"
            onChange={e => onChange({ ...value, event_value: e.target.value || undefined })} style={{ width: '100%' }} />
        </>
      )}
      {chosen && (
        <div style={hint}>
          Predicts <b>{chosen.target}</b> from {chosen.features.join(', ')}. Re-scores the rows on the page as filters change.
        </div>
      )}
    </div>
  )
}

export default function ModelSettings({ widget, pages, value, onChange, datasetId = null }: {
  widget: Widget
  pages?: ReportPage[]
  value: ModelOpts
  onChange: (next: ModelOpts) => void
  /** The dataset the widget reads (its own, else the report's). */
  datasetId?: number | null
}) {
  const wt = widget.widget_type
  if (wt === 'model_score') return <SavedModelPicker datasetId={datasetId} value={value} onChange={onChange} />
  if (wt === 'model_logistic') {
    return (
      <div style={{ marginBottom: 12 }}>
        <label htmlFor="model-event" style={lbl}>Event (the outcome being predicted)</label>
        <input id="model-event" value={value.event_value ?? ''} placeholder="blank = the rarer outcome"
          onChange={e => onChange({ ...value, event_value: e.target.value || undefined })} style={{ width: '100%' }} />
        <div style={hint}>Odds ratios read as "how much more likely is <i>this</i> outcome".</div>
      </div>
    )
  }
  if (wt === 'model_tree') {
    return (
      <div style={{ marginBottom: 12 }}>
        <label htmlFor="model-depth" style={lbl}>Maximum depth</label>
        <input id="model-depth" type="number" min={1} max={10} value={value.max_depth ?? ''} placeholder="4"
          onChange={e => {
            const n = Number(e.target.value)
            onChange({ ...value, max_depth: e.target.value === '' || !Number.isFinite(n) ? undefined : Math.min(10, Math.max(1, Math.round(n))) })
          }} style={{ width: '100%' }} />
        <div style={hint}>Deeper trees fit the training rows better and new rows worse.</div>
      </div>
    )
  }
  if (wt !== 'model_compare') return null

  const chosen = value.compare ?? []
  const candidates = compareCandidates(pages, widget)
  const stale = staleSnapshots(chosen, pages)
  const toggle = (spec: ModelSpec) => {
    const on = chosen.some(c => c.id === spec.id)
    onChange({ ...value, compare: on ? chosen.filter(c => c.id !== spec.id) : [...chosen, spec] })
  }
  return (
    <div style={{ marginBottom: 12 }} data-testid="model-compare-settings">
      <div style={lbl}>Models to compare *</div>
      {candidates.length === 0 ? (
        <div role="status" style={{ fontSize: 11.5, color: 'var(--muted)' }}>
          No regression, logistic or decision-tree widget in this report yet. Add two models of the same
          response, then pick them here.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4, background: 'var(--surface2)',
          border: '1px solid var(--border)', borderRadius: 6, padding: '6px 8px' }}>
          {candidates.map(({ widget: w, spec, pageName }) => {
            const on = chosen.some(c => c.id === spec.id)
            const why = on ? null : candidateBlockReason(spec, chosen)
            return (
              <label key={w.id} title={why ?? undefined}
                style={{ display: 'flex', alignItems: 'flex-start', gap: 6, fontSize: 12, cursor: why ? 'not-allowed' : 'pointer' }}>
                <input type="checkbox" checked={on} disabled={!!why} title={why || undefined} onChange={() => toggle(spec)} />
                <span>
                  <span style={{ color: why ? 'var(--muted)' : 'var(--text)' }}>{spec.title}</span>
                  <span style={{ display: 'block', fontSize: 10, color: 'var(--muted)' }}>
                    {spec.model} · {spec.response ?? 'no response'}{spec.response ? ` ~ ${spec.predictors.join(' + ') || 'all columns'}` : ''}{w.page_id !== widget.page_id ? ` · page ${pageName}` : ''}
                    {why ? ` — ${why}` : ''}
                  </span>
                </span>
              </label>
            )
          })}
        </div>
      )}
      {chosen.length === 1 && <div style={hint}>Pick one more model to compare.</div>}
      {stale.length > 0 && (
        <div role="alert" style={{ marginTop: 6, fontSize: 11, padding: '6px 8px', borderRadius: 6,
          border: '1px solid var(--warning, #d68910)', background: 'color-mix(in srgb, var(--warning, #d68910) 10%, transparent)' }}>
          Changed since you chose {stale.length === 1 ? 'it' : 'them'}: {stale.join(', ')}.{' '}
          <button type="button" className="btn btn-sm" onClick={() => onChange({ ...value, compare: refreshSnapshots(chosen, pages) })}>
            Update comparison
          </button>
        </div>
      )}
    </div>
  )
}
