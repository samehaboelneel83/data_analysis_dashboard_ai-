/**
 * Authoring the map layer stack: an ordered list, bottom layer first, of
 * regions / bubbles / points / lines, each with its own fields and (for the
 * region kinds) its own boundary set. Stored whole in `config.layers`.
 */
import { useEffect, useState } from 'react'
import type { DatasetColumn } from '../../services/api'
import { boundarySetsApi } from '../../services/api'
import { COLORS } from './chartUtils'

export type MapLayerKind = 'regions' | 'bubbles' | 'points' | 'lines'
export interface MapLayerCfg {
  id: string
  kind: MapLayerKind
  title?: string
  category?: string
  measure?: string
  aggregation?: string
  lat?: string
  lon?: string
  lat2?: string
  lon2?: string
  boundary_set_id?: number | null
  color?: string
}

const KINDS: { value: MapLayerKind; label: string }[] = [
  { value: 'regions', label: 'Regions (filled shapes)' },
  { value: 'bubbles', label: 'Bubbles on regions' },
  { value: 'points', label: 'Points (latitude / longitude)' },
  { value: 'lines', label: 'Lines (from → to)' },
]
export const MAX_LAYERS = 6

let seq = 0
const newId = () => `l${Date.now().toString(36)}${(seq++).toString(36)}`

const sel: React.CSSProperties = { fontSize: 11, padding: '3px 5px', width: '100%' }
const lbl: React.CSSProperties = { fontSize: 9.5, color: 'var(--muted)', display: 'block', marginTop: 4 }

export default function MapLayersEditor({ value, onChange, columns }: {
  value: MapLayerCfg[]
  onChange: (next: MapLayerCfg[]) => void
  columns: DatasetColumn[]
}) {
  const [sets, setSets] = useState<{ id: number; name: string }[]>([])
  useEffect(() => {
    Promise.resolve().then(() => boundarySetsApi.list?.()).then(s => setSets(Array.isArray(s) ? s : [])).catch(() => {})
  }, [])
  const numeric = columns.filter(c => c.dtype === 'numeric' || c.dtype === 'calculated')
  const patch = (i: number, p: Partial<MapLayerCfg>) => onChange(value.map((l, j) => (j === i ? { ...l, ...p } : l)))
  const move = (i: number, d: number) => {
    const j = i + d
    if (j < 0 || j >= value.length) return
    const next = [...value]; [next[i], next[j]] = [next[j], next[i]]; onChange(next)
  }
  const col = (i: number, key: keyof MapLayerCfg, label: string, list: DatasetColumn[], optional = false) => (
    <label style={lbl}>{label}{optional ? '' : ' *'}
      <select aria-label={`Layer ${i + 1} ${label}`} style={sel} value={(value[i][key] as string) ?? ''}
        onChange={e => patch(i, { [key]: e.target.value || undefined } as Partial<MapLayerCfg>)}>
        <option value="">{optional ? '— none —' : '— select column —'}</option>
        {list.map(c => <option key={c.name} value={c.name}>{c.name}</option>)}
      </select>
    </label>
  )
  return (
    <div data-testid="map-layers-editor" style={{ marginTop: 10 }}>
      <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.06em' }}>
        Layers {value.length > 0 && <span style={{ fontWeight: 400, textTransform: 'none' }}>(bottom first)</span>}
      </div>
      {value.length === 0 && (
        <p style={{ fontSize: 10.5, color: 'var(--muted)', margin: '4px 0' }}>
          No layer stack yet — the map draws the region and point fields above. Add layers to stack
          regions, bubbles, points and lines, each with its own fields.
        </p>
      )}
      {value.map((l, i) => (
        <div key={l.id} style={{ border: '1px solid var(--border)', borderInlineStart: `3px solid ${l.color || COLORS[i % COLORS.length]}`,
          borderRadius: 6, padding: 6, marginTop: 6, background: 'var(--surface2)' }}>
          <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
            <input aria-label={`Layer ${i + 1} title`} value={l.title ?? ''} placeholder={`Layer ${i + 1}`}
              onChange={e => patch(i, { title: e.target.value })} style={{ ...sel, flex: 1 }} />
            <button type="button" className="btn btn-sm" aria-label={`Move layer ${i + 1} down`} disabled={i === 0}
              onClick={() => move(i, -1)}>↓</button>
            <button type="button" className="btn btn-sm" aria-label={`Move layer ${i + 1} up`} disabled={i === value.length - 1}
              onClick={() => move(i, 1)}>↑</button>
            <button type="button" className="btn btn-sm" aria-label={`Remove layer ${i + 1}`}
              onClick={() => onChange(value.filter((_, j) => j !== i))}>×</button>
          </div>
          <label style={lbl}>Type
            <select aria-label={`Layer ${i + 1} type`} style={sel} value={l.kind}
              onChange={e => patch(i, { kind: e.target.value as MapLayerKind })}>
              {KINDS.map(k => <option key={k.value} value={k.value}>{k.label}</option>)}
            </select>
          </label>
          {(l.kind === 'regions' || l.kind === 'bubbles') && <>
            {col(i, 'category', 'Region', columns)}
            {col(i, 'measure', 'Value (blank = count rows)', numeric, true)}
            <label style={lbl}>Boundaries
              <select aria-label={`Layer ${i + 1} boundaries`} style={sel} value={l.boundary_set_id ?? ''}
                onChange={e => patch(i, { boundary_set_id: e.target.value ? Number(e.target.value) : null })}>
                <option value="">Countries (built in)</option>
                {sets.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </label>
          </>}
          {l.kind === 'points' && <>
            {col(i, 'lat', 'Latitude', numeric)}
            {col(i, 'lon', 'Longitude', numeric)}
            {col(i, 'measure', 'Size', numeric, true)}
          </>}
          {l.kind === 'lines' && <>
            {col(i, 'lat', 'From latitude', numeric)}
            {col(i, 'lon', 'From longitude', numeric)}
            {col(i, 'lat2', 'To latitude', numeric)}
            {col(i, 'lon2', 'To longitude', numeric)}
            {col(i, 'measure', 'Width', numeric, true)}
          </>}
          <label style={{ ...lbl, display: 'flex', alignItems: 'center', gap: 6 }}>Colour
            <input type="color" aria-label={`Layer ${i + 1} colour`} value={l.color || COLORS[i % COLORS.length]}
              onChange={e => patch(i, { color: e.target.value })} />
          </label>
        </div>
      ))}
      <button type="button" className="btn btn-sm" style={{ marginTop: 6 }} disabled={value.length >= MAX_LAYERS}
        title={value.length >= MAX_LAYERS ? `A map draws at most ${MAX_LAYERS} layers` : undefined}
        onClick={() => onChange([...value, { id: newId(), kind: value.length ? 'points' : 'regions' }])}>
        + Add layer
      </button>
    </div>
  )
}
