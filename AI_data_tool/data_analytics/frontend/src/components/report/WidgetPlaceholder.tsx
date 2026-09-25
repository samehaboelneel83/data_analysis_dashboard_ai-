/**
 * What an unconfigured widget looks like: a dimmed SAMPLE of its own chart
 * family, the roles it still needs, and an "Assign data" button.
 *
 * SAS VA draws every new object with synthetic data behind an "Assign data"
 * button, so the canvas is never a blank frame and the author edits FROM
 * something. The sample is decoration only -- it is drawn from constants,
 * never from the dataset, and says so ("Sample") so nobody reads it as data.
 */
import type { Widget, WidgetType } from '../../types/report'
import { ROLE_SPECS, configKeyFor } from '../../types/report'

/** Event the builder listens for: select this widget, open its Data roles. */
export const ASSIGN_DATA_EVENT = 'datalytics:assign-data'

/** Event the builder listens for: open the "add a dataset" list in the fields panel. */
export const ADD_DATASET_EVENT = 'datalytics:add-dataset'

/**
 * Why a role picker has nothing to offer, in the reader's words -- or null when
 * it has options. An empty dropdown with no reason is a silent refusal: the
 * author cannot tell "no data yet" from "wrong kind of column" from a bug.
 */
export function emptyPickerReason(hasAnyColumns: boolean, kind: string | undefined): string | null {
  if (!hasAnyColumns) return 'No dataset is attached to this report yet.'
  if (kind === 'numeric') return 'This dataset has no numeric columns to measure.'
  if (kind === 'datetime') return 'This dataset has no date columns. Set a column\'s type to date in the Data tab, or use a chart that takes a category.'
  return 'No columns of the right kind for this field.'
}

/** Required roles this widget has not been given yet (labels, for display). */
export function missingRequiredRoles(widget: Pick<Widget, 'widget_type' | 'config'>): string[] {
  const cfg = (widget.config ?? {}) as Record<string, unknown>
  return (ROLE_SPECS[widget.widget_type as WidgetType] ?? [])
    .filter(rf => rf.required)
    .filter(rf => {
      const v = cfg[configKeyFor(rf.role)]
      return v === undefined || v === null || v === '' || (Array.isArray(v) && v.length === 0)
    })
    .map(rf => (rf.label ?? rf.role).replace(/\s*\(.*\)\s*$/, ''))
}

const HIERARCHY_TYPES = new Set(['tree', 'sunburst', 'icicle', 'circle_pack', 'dendrogram', 'org'])

/** What a type needs that is chosen as a widget OPTION rather than a role slot:
 *  a hierarchy's ordered levels, a layered map's first layer, a saved model.
 *  Their ROLE_SPECS are all optional, so missingRequiredRoles found nothing
 *  and an unfinished one said "No data." or drew nothing (BUG-038) instead of
 *  the placeholder every other chart shows. */
export function missingWidgetOptions(widget: Pick<Widget, 'widget_type' | 'config'>): string[] {
  const cfg = (widget.config ?? {}) as Record<string, unknown>
  const has = (k: string) => {
    const v = cfg[k]
    return !(v === undefined || v === null || v === '' || (Array.isArray(v) && v.length === 0))
  }
  const wt = widget.widget_type
  if (HIERARCHY_TYPES.has(wt)) return has('levels') || (has('id_col') && has('parent_col')) ? [] : ['Hierarchy levels']
  if (wt === 'map_layers') {
    return has(configKeyFor('category')) || (has(configKeyFor('lat')) && has(configKeyFor('lon')))
      ? [] : ['Country or Latitude/Longitude']
  }
  if (wt === 'model_score') return has('prediction_model_id') ? [] : ['Saved model']
  if (wt === 'model_compare') return has('compare') ? [] : ['Models to compare']
  return []
}


type Family = 'bars' | 'line' | 'pie' | 'scatter' | 'table' | 'kpi' | 'map'

export function familyOf(t: string): Family {
  if (t.startsWith('map')) return 'map'
  if (t.startsWith('model_')) return 'scatter'
  if (/pie|donut|treemap|sunburst|icicle|circle_pack|word_cloud/.test(t)) return 'pie'
  if (/scatter|bubble|vector|correlation|network|parallel/.test(t)) return 'scatter'
  if (/line|area|time_series|step|forecast|numeric_series|sparkline/.test(t)) return 'line'
  if (/table|crosstab|matrix|pivot|list/.test(t)) return 'table'
  if (/kpi|card|gauge|metric/.test(t)) return 'kpi'
  return 'bars'
}

function Sample({ family }: { family: Family }) {
  const c = 'currentColor'
  switch (family) {
    case 'line':
      return <polyline points="10,70 40,52 70,58 100,34 130,40 160,18 190,26" fill="none" stroke={c} strokeWidth="4" />
    case 'pie':
      return (<g transform="translate(100,48)">
        <circle r="36" fill="none" stroke={c} strokeWidth="18" strokeDasharray="90 300" />
        <circle r="36" fill="none" stroke={c} strokeOpacity=".55" strokeWidth="18" strokeDasharray="70 300" strokeDashoffset="-94" />
        <circle r="36" fill="none" stroke={c} strokeOpacity=".3" strokeWidth="18" strokeDasharray="60 300" strokeDashoffset="-168" />
      </g>)
    case 'scatter':
      return <g fill={c}>{[[20,70],[40,58],[55,62],[70,44],[90,48],[110,34],[125,40],[150,22],[170,28],[185,14]].map(([x, y], i) =>
        <circle key={i} cx={x} cy={y} r="5" />)}</g>
    case 'table':
      return <g fill={c}>{[0, 1, 2, 3, 4].map(r => [0, 1, 2].map(k =>
        <rect key={`${r}-${k}`} x={12 + k * 62} y={8 + r * 16} width="54" height="10" rx="2" opacity={r === 0 ? 1 : 0.5} />))}</g>
    case 'kpi':
      return (<g fill={c}><rect x="60" y="20" width="80" height="30" rx="4" /><rect x="72" y="58" width="56" height="8" rx="2" opacity=".5" /></g>)
    case 'map':
      return <path d="M20,40 C40,10 80,10 95,30 C110,50 150,15 180,35 C190,55 160,80 120,72 C90,66 60,85 30,70 Z" fill={c} />
    default:
      return <g fill={c}>{[40, 62, 30, 52, 70].map((h, i) =>
        <rect key={i} x={18 + i * 36} y={80 - h} width="26" height={h} rx="2" />)}</g>
  }
}

export function WidgetPlaceholder({ widget, missing, onAssignData }:
  { widget: Pick<Widget, 'widget_type'>; missing: string[]; onAssignData?: () => void }) {
  return (
    <div data-testid="widget-placeholder" style={{ position: 'relative', height: '100%', minHeight: 90,
      display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden' }}>
      <svg viewBox="0 0 200 86" preserveAspectRatio="xMidYMid meet" aria-hidden="true"
        style={{ position: 'absolute', inset: 8, width: 'calc(100% - 16px)', height: 'calc(100% - 16px)',
          color: 'var(--accent)', opacity: 0.16 }}>
        <Sample family={familyOf(widget.widget_type)} />
      </svg>
      <div style={{ position: 'relative', textAlign: 'center', display: 'flex', flexDirection: 'column',
        alignItems: 'center', gap: 6, padding: 8 }}>
        <span style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '.06em', color: 'var(--muted)' }}>Sample</span>
        <span style={{ fontSize: 12, color: 'var(--text)' }}>
          Needs {missing.join(' · ')}
        </span>
        {onAssignData
          ? <button type="button" className="btn btn-primary btn-sm"
              onMouseDown={e => e.stopPropagation()} onPointerDown={e => e.stopPropagation()}
              onClick={e => { e.stopPropagation(); onAssignData() }}>
              Assign data
            </button>
          : <span style={{ fontSize: 11, color: 'var(--muted)' }}>The author has not finished this widget.</span>}
      </div>
    </div>
  )
}
