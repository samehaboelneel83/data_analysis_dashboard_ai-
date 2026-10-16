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
  /** Key influencers, how they are drawn (chartRenderers/ModelRenderer). */
  influencer_style?: 'bars' | 'bubbles'
  influencer_direction?: 'both' | 'higher' | 'lower'
  influencer_limit?: number
  /** What each influencer's figure is: how far from usual ("+23.5%"), how many times the usual ("1.24×"), or its own value. */
  influencer_format?: 'change' | 'times' | 'value'
  influencer_decimals?: number
  /** Association rules read one way only, by the role each value plays (chartRenderers/RuleRoles). */
  rules_view?: 'network' | 'matrix' | 'summary' | 'table' | 'chord'
  rules_items?: number
  /** One of the model's views alone, as a tile (ModelRenderer `model_tab`). */
  model_tab?: string
  /** false = only the influencers: no model line, no row counts, no tabs. */
  influencer_details?: boolean
  max_depth?: number
  compare?: ModelSpec[]
}

export function seedModelOpts(cfg: Record<string, unknown>): ModelOpts {
  const o: ModelOpts = {}
  if (typeof cfg.event_value === 'string' && cfg.event_value) o.event_value = cfg.event_value
  if (typeof cfg.prediction_model_id === 'number') o.prediction_model_id = cfg.prediction_model_id
  if (cfg.model_follows === 'champion') o.model_follows = 'champion'
  if (typeof cfg.max_depth === 'number') o.max_depth = cfg.max_depth
  if (cfg.influencer_style === 'bubbles' || cfg.influencer_style === 'bars') o.influencer_style = cfg.influencer_style
  if (cfg.influencer_direction === 'higher' || cfg.influencer_direction === 'lower' || cfg.influencer_direction === 'both') o.influencer_direction = cfg.influencer_direction
  if (typeof cfg.influencer_limit === 'number' && cfg.influencer_limit > 0) o.influencer_limit = cfg.influencer_limit
  if (cfg.influencer_details === false) o.influencer_details = false
  if (cfg.influencer_format === 'change' || cfg.influencer_format === 'times' || cfg.influencer_format === 'value') o.influencer_format = cfg.influencer_format
  if (typeof cfg.influencer_decimals === 'number' && cfg.influencer_decimals >= 0) o.influencer_decimals = cfg.influencer_decimals
  if (['network', 'matrix', 'summary', 'table', 'chord'].includes(cfg.rules_view as string)) o.rules_view = cfg.rules_view as ModelOpts['rules_view']
  if (typeof cfg.rules_items === 'number' && cfg.rules_items > 1) o.rules_items = cfg.rules_items
  if (typeof cfg.model_tab === 'string' && cfg.model_tab) o.model_tab = cfg.model_tab
  if (Array.isArray(cfg.compare)) o.compare = cfg.compare as ModelSpec[]
  return o
}

/** The keys this widget type writes; nothing for a type that ignores them. */
export function modelOptsConfig(wt: string, o: ModelOpts): Record<string, unknown> {
  if (wt === 'model_influencers') {
    return {
      ...(o.event_value ? { event_value: o.event_value } : {}),
      ...(o.influencer_style && o.influencer_style !== 'bars' ? { influencer_style: o.influencer_style } : {}),
      ...(o.influencer_direction && o.influencer_direction !== 'both' ? { influencer_direction: o.influencer_direction } : {}),
      ...(o.influencer_limit ? { influencer_limit: o.influencer_limit } : {}),
      ...(o.influencer_details === false ? { influencer_details: false } : {}),
      ...(o.influencer_format ? { influencer_format: o.influencer_format } : {}),
      ...(o.influencer_decimals != null ? { influencer_decimals: o.influencer_decimals } : {}),
    }
  }
  const only = o.model_tab ? { model_tab: o.model_tab } : {}
  if (wt === 'model_logistic') return { ...(o.event_value ? { event_value: o.event_value } : {}), ...only }
  if (wt === 'model_linear' || wt === 'model_cluster') return only
  if (wt === 'model_rules') {
    return { ...(o.rules_view ? { rules_view: o.rules_view } : {}), ...(o.rules_items ? { rules_items: o.rules_items } : {}) }
  }
  if (wt === 'model_tree') return { ...(o.max_depth ? { max_depth: o.max_depth } : {}), ...only }
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

/** The views each fitted model has, by the keys ModelRenderer gives its tabs. */
export const MODEL_TABS: Record<string, string[]> = {
  model_linear: ['coef', 'resid', 'ap', 'fit'], model_logistic: ['coef', 'cm', 'roc', 'fit'],
  model_tree: ['imp', 'rules', 'fit'], model_cluster: ['seg', 'map', 'fit'],
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

/** Model types whose settings split into a specification (Fields) and how
 *  the result is drawn (Format): F-16, Key influencers. */
export const MODEL_DISPLAY_SPLIT = new Set(['model_influencers'])

export default function ModelSettings({ widget, pages, value, onChange, datasetId = null, part = 'all' }: {
  widget: Widget
  pages?: ReportPage[]
  value: ModelOpts
  onChange: (next: ModelOpts) => void
  /** The dataset the widget reads (its own, else the report's). */
  datasetId?: number | null
  /** F-16: 'spec' = what the model is (Fields); 'display' = how it is drawn
   *  (the Format tab). 'all' = both, as before. */
  part?: 'all' | 'spec' | 'display'
}) {
  const t = useT()
  const wt = widget.widget_type
  if (wt === 'model_score') return <SavedModelPicker datasetId={datasetId} value={value} onChange={onChange} />
  if (wt === 'model_influencers') {
    // Which value of the outcome to explain; blank = the rarest one.
    const spec = (
      <>
        <label htmlFor="model-event" style={lbl}>{t('pg.modelsMaps.ms.event')}</label>
        <input id="model-event" value={value.event_value ?? ''} placeholder={t('mdl.infl.eventBlank')}
          onChange={e => onChange({ ...value, event_value: e.target.value || undefined })} style={{ width: '100%' }} />
      </>
    )
    if (part === 'spec') return <div style={{ marginBottom: 12 }}>{spec}</div>
    return (
      <div style={{ marginBottom: 12 }}>
        {part === 'all' && spec}
        {/* How the influencers are drawn: display only, the figures are the same. */}
        <label htmlFor="infl-style" style={{ ...lbl, marginTop: part === 'all' ? 10 : 0 }}>{t('mdl.infl.o.style')}</label>
        <select id="infl-style" value={value.influencer_style ?? 'bars'} style={{ width: '100%' }}
          onChange={e => onChange({ ...value, influencer_style: e.target.value as 'bars' | 'bubbles' })}>
          <option value="bars">{t('mdl.infl.o.bars')}</option>
          <option value="bubbles">{t('mdl.infl.o.bubbles')}</option>
        </select>
        <label htmlFor="infl-direction" style={{ ...lbl, marginTop: 10 }}>{t('mdl.infl.o.direction')}</label>
        <select id="infl-direction" value={value.influencer_direction ?? 'both'} style={{ width: '100%' }}
          onChange={e => onChange({ ...value, influencer_direction: e.target.value as 'both' | 'higher' | 'lower' })}>
          <option value="both">{t('mdl.infl.o.both')}</option>
          <option value="higher">{t('mdl.infl.o.higher')}</option>
          <option value="lower">{t('mdl.infl.o.lower')}</option>
        </select>
        <label htmlFor="infl-limit" style={{ ...lbl, marginTop: 10 }}>{t('mdl.infl.o.limit')}</label>
        <input id="infl-limit" type="number" min={1} max={50} value={value.influencer_limit ?? ''} placeholder={t('mdl.infl.o.all')}
          onChange={e => onChange({ ...value, influencer_limit: e.target.value ? Math.max(1, Math.min(50, Number(e.target.value))) : undefined })}
          style={{ width: '100%' }} />
        <label htmlFor="infl-format" style={{ ...lbl, marginTop: 10 }}>{t('mdl.infl.o.format')}</label>
        <select id="infl-format" value={value.influencer_format ?? ''} style={{ width: '100%' }}
          onChange={e => onChange({ ...value, influencer_format: (e.target.value || undefined) as ModelOpts['influencer_format'] })}>
          <option value="">{t('mdl.infl.o.formatAuto')}</option>
          <option value="change">{t('mdl.infl.o.formatChange')}</option>
          <option value="times">{t('mdl.infl.o.formatTimes')}</option>
          <option value="value">{t('mdl.infl.o.formatValue')}</option>
        </select>
        <label htmlFor="infl-decimals" style={{ ...lbl, marginTop: 10 }}>{t('mdl.infl.o.decimals')}</label>
        <select id="infl-decimals" value={value.influencer_decimals ?? ''} style={{ width: '100%' }}
          onChange={e => onChange({ ...value, influencer_decimals: e.target.value === '' ? undefined : Number(e.target.value) })}>
          <option value="">{t('mdl.infl.o.formatAuto')}</option>
          {[0, 1, 2, 3].map(n => <option key={n} value={n}>{n}</option>)}
        </select>
        <label style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 12.5, marginTop: 10 }}>
          <input type="checkbox" checked={value.influencer_details !== false}
            onChange={e => onChange({ ...value, influencer_details: e.target.checked ? undefined : false })} />
          {t('mdl.infl.o.details')}
        </label>
        <div style={hint}>{t('mdl.infl.o.detailsHint')}</div>
      </div>
    )
  }
  const showOnly = MODEL_TABS[wt] ? (
    <div style={{ marginBottom: 12 }}>
      <label htmlFor="model-tab" style={lbl}>{t('mdl.only.label')}</label>
      <select id="model-tab" value={value.model_tab ?? ''} style={{ width: '100%' }}
        onChange={e => onChange({ ...value, model_tab: e.target.value || undefined })}>
        <option value="">{t('mdl.role.o.tabs')}</option>
        {MODEL_TABS[wt].map(k => <option key={k} value={k}>{t(`mdl.only.${k}` as never)}</option>)}
      </select>
      <div style={hint}>{t('mdl.only.hint')}</div>
    </div>
  ) : null
  if (wt === 'model_linear' || wt === 'model_cluster') return showOnly
  if (wt === 'model_logistic') {
    return (
      <div style={{ marginBottom: 12 }}>
        {showOnly}
        <label htmlFor="model-event" style={lbl}>{t('pg.modelsMaps.ms.event')}</label>
        <input id="model-event" value={value.event_value ?? ''} placeholder={t('pg.modelsMaps.ms.eventBlank')}
          onChange={e => onChange({ ...value, event_value: e.target.value || undefined })} style={{ width: '100%' }} />
        <div style={hint}>{rich(t, 'pg.modelsMaps.ms.oddsHint', { this: <i>{t('pg.modelsMaps.ms.this')}</i> })}</div>
      </div>
    )
  }
  if (wt === 'model_rules') {
    return (
      <div style={{ marginBottom: 12 }}>
        <label htmlFor="rules-view" style={lbl}>{t('mdl.role.o.view')}</label>
        <select id="rules-view" value={value.rules_view ?? ''} style={{ width: '100%' }}
          onChange={e => onChange({ ...value, rules_view: (e.target.value || undefined) as ModelOpts['rules_view'] })}>
          <option value="">{t('mdl.role.o.tabs')}</option>
          {(['network', 'matrix', 'summary', 'table', 'chord'] as const).map(v => <option key={v} value={v}>{t(`mdl.role.o.${v}`)}</option>)}
        </select>
        <div style={hint}>{t('mdl.role.o.viewHint')}</div>
        <label htmlFor="rules-items" style={{ ...lbl, marginTop: 10 }}>{t('mdl.role.o.items')}</label>
        <input id="rules-items" type="number" min={2} max={30} value={value.rules_items ?? ''} placeholder="10"
          onChange={e => onChange({ ...value, rules_items: e.target.value ? Math.max(2, Math.min(30, Number(e.target.value))) : undefined })}
          style={{ width: '100%' }} />
      </div>
    )
  }
  if (wt === 'model_tree') {
    return (
      <div style={{ marginBottom: 12 }}>
        {showOnly}
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
