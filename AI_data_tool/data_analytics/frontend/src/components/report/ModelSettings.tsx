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
import { useT } from '../../i18n'
import { familyLabel, rich } from '../../i18n/pages/modelsMaps'

export interface ModelOpts {
  prediction_model_id?: number
  /** E13: score with whichever version of the chosen model's name is champion now. */
  model_follows?: 'champion'
  event_value?: string
  max_depth?: number
  compare?: ModelSpec[]
}

export function seedModelOpts(cfg: Record<string, unknown>): ModelOpts {
  const o: ModelOpts = {}
  if (typeof cfg.event_value === 'string' && cfg.event_value) o.event_value = cfg.event_value
  if (typeof cfg.prediction_model_id === 'number') o.prediction_model_id = cfg.prediction_model_id
  if (cfg.model_follows === 'champion') o.model_follows = 'champion'
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
      ...(o.prediction_model_id && o.model_follows ? { model_follows: o.model_follows } : {}),
      ...(o.event_value ? { event_value: o.event_value } : {}),
    }
  }
  return {}
}

const lbl: React.CSSProperties = { display: 'block', fontSize: 11, fontWeight: 700, color: 'var(--muted)',
  textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 4 }
const hint: React.CSSProperties = { fontSize: 10.5, color: 'var(--muted)', marginTop: 3 }

/** Picks the saved model a scoring widget applies. Lists only models this
 *  viewer may use -- the server already omits any trained on a column they
 *  are denied, so nothing is offered that would then be refused. */
function SavedModelPicker({ datasetId, value, onChange }: {
  datasetId: number | null; value: ModelOpts; onChange: (next: ModelOpts) => void
}) {
  const t = useT()
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
      <label htmlFor="saved-model" style={lbl}>{t('pg.modelsMaps.ms.savedModel')}</label>
      {!datasetId ? (
        <div role="status" style={{ fontSize: 11.5, color: 'var(--muted)' }}>{t('pg.modelsMaps.ms.attachFirst')}</div>
      ) : failed ? (
        <div role="status" style={{ fontSize: 11.5, color: 'var(--muted)' }}>{t('pg.modelsMaps.ms.loadFailed')}</div>
      ) : models && models.length === 0 ? (
        <div role="status" style={{ fontSize: 11.5, color: 'var(--muted)' }}>{t('pg.modelsMaps.ms.noSaved')}</div>
      ) : (
        <select id="saved-model" value={value.prediction_model_id ?? ''} style={{ width: '100%' }}
          onChange={e => onChange({ ...value, prediction_model_id: e.target.value ? Number(e.target.value) : undefined })}>
          <option value="">{models ? t('pg.modelsMaps.ms.choose') : t('pg.modelsMaps.loading')}</option>
          {(models ?? []).map(m => (
            <option key={m.id} value={m.id}>
              {t(m.status === 'champion' ? 'pg.modelsMaps.ms.optionChampion' : 'pg.modelsMaps.ms.option', {
                name: `${m.name}${m.version ? ` v${m.version}` : ''}`, target: m.target, family: familyLabel(t, m.model_family),
              })}
            </option>
          ))}
        </select>
      )}
      {chosen?.task === 'classification' && (
        <>
          <label htmlFor="score-event" style={{ ...lbl, marginTop: 8 }}>{t('pg.modelsMaps.ms.outcome')}</label>
          <input id="score-event" value={value.event_value ?? ''} placeholder={t('pg.modelsMaps.ms.outcomeBlank')}
            onChange={e => onChange({ ...value, event_value: e.target.value || undefined })} style={{ width: '100%' }} />
        </>
      )}
      {chosen && (
        <div style={hint}>
          {rich(t, 'pg.modelsMaps.ms.predictsHint', {
            target: <b><bdi>{chosen.target}</bdi></b>, from: <bdi>{chosen.features.join(', ')}</bdi>,
          })}
        </div>
      )}
      {chosen && (
        <label style={{ display: 'flex', gap: 6, alignItems: 'flex-start', fontSize: 11.5, marginTop: 8, cursor: 'pointer' }}>
          <input type="checkbox" checked={value.model_follows === 'champion'}
            onChange={e => onChange({ ...value, model_follows: e.target.checked ? 'champion' : undefined })} />
          <span>{t('pg.modelsMaps.ms.follow', { name: chosen.name, v: String(chosen.version ?? 1) })}</span>
        </label>
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
  const t = useT()
  const wt = widget.widget_type
  if (wt === 'model_score') return <SavedModelPicker datasetId={datasetId} value={value} onChange={onChange} />
  if (wt === 'model_logistic') {
    return (
      <div style={{ marginBottom: 12 }}>
        <label htmlFor="model-event" style={lbl}>{t('pg.modelsMaps.ms.event')}</label>
        <input id="model-event" value={value.event_value ?? ''} placeholder={t('pg.modelsMaps.ms.eventBlank')}
          onChange={e => onChange({ ...value, event_value: e.target.value || undefined })} style={{ width: '100%' }} />
        <div style={hint}>{rich(t, 'pg.modelsMaps.ms.oddsHint', { this: <i>{t('pg.modelsMaps.ms.this')}</i> })}</div>
      </div>
    )
  }
  if (wt === 'model_tree') {
    return (
      <div style={{ marginBottom: 12 }}>
        <label htmlFor="model-depth" style={lbl}>{t('pg.modelsMaps.ms.maxDepth')}</label>
        <input id="model-depth" type="number" min={1} max={10} value={value.max_depth ?? ''} placeholder="4"
          onChange={e => {
            const n = Number(e.target.value)
            onChange({ ...value, max_depth: e.target.value === '' || !Number.isFinite(n) ? undefined : Math.min(10, Math.max(1, Math.round(n))) })
          }} style={{ width: '100%' }} />
        <div style={hint}>{t('pg.modelsMaps.ms.depthHint')}</div>
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
      <div style={lbl}>{t('pg.modelsMaps.ms.toCompare')}</div>
      {candidates.length === 0 ? (
        <div role="status" style={{ fontSize: 11.5, color: 'var(--muted)' }}>{t('pg.modelsMaps.ms.noCandidates')}</div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4, background: 'var(--surface2)',
          border: '1px solid var(--border)', borderRadius: 6, padding: '6px 8px' }}>
          {candidates.map(({ widget: w, spec, pageName }) => {
            const on = chosen.some(c => c.id === spec.id)
            const why = on ? null : candidateBlockReason(spec, chosen, t)
            return (
              <label key={w.id} title={why ?? undefined}
                style={{ display: 'flex', alignItems: 'flex-start', gap: 6, fontSize: 12, cursor: why ? 'not-allowed' : 'pointer' }}>
                <input type="checkbox" checked={on} disabled={!!why} title={why || undefined} onChange={() => toggle(spec)} />
                <span>
                  <span style={{ color: why ? 'var(--muted)' : 'var(--text)' }}>{spec.title}</span>
                  <span style={{ display: 'block', fontSize: 11, color: 'var(--muted)' }}>
                    {familyLabel(t, spec.model)} · {spec.response
                      ? <bdi dir="ltr">{`${spec.response} ~ ${spec.predictors.join(' + ') || t('pg.modelsMaps.ms.allColumns')}`}</bdi>
                      : t('pg.modelsMaps.ms.noResponse')}{w.page_id !== widget.page_id ? ` · ${t('pg.modelsMaps.ms.page', { page: pageName })}` : ''}
                    {why ? ` — ${why}` : ''}
                  </span>
                </span>
              </label>
            )
          })}
        </div>
      )}
      {chosen.length === 1 && <div style={hint}>{t('pg.modelsMaps.ms.pickOneMore')}</div>}
      {stale.length > 0 && (
        <div role="alert" style={{ marginTop: 6, fontSize: 11, padding: '6px 8px', borderRadius: 6,
          border: '1px solid var(--warning, #d68910)', background: 'color-mix(in srgb, var(--warning, #d68910) 10%, transparent)' }}>
          {t('pg.modelsMaps.ms.stale', { n: stale.length, list: stale.join(', ') })}{' '}
          <button type="button" className="btn btn-sm" onClick={() => onChange({ ...value, compare: refreshSnapshots(chosen, pages) })}>
            {t('pg.modelsMaps.ms.update')}
          </button>
        </div>
      )}
    </div>
  )
}
