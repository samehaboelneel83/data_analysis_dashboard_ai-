/**
 * The map layer stack (MASTER_PLAN Phase 4 item 3): regions, bubbles, points
 * and lines on ONE map, drawn bottom-up in the author's order, each layer with
 * its own roles and its own boundary set.
 *
 * A layer the server could not draw is listed in the legend with its reason
 * ("Stores — not drawn: needs Longitude"). SAS drops an incompatible layer
 * without a word; a map missing a layer it does not mention reads as "there is
 * nothing there", which is the wrong conclusion.
 */
import { useEffect, useMemo, useState } from 'react'
import type { ChartRendererProps } from './types'
import { COLORS, fmtStr } from '../chartUtils'
import { COUNTRIES, COUNTRY_SET, fittedProjection, matchRegion, regionBoundsPoints, regionCentroid,
  regionLabel, type RegionFeature, type RegionSet } from '../geo/worldGeometry'
import { loadRegionSet } from '../geo/regionSetCache'
import { MapSvg, MAP_WRAP_STYLE, useMapBox } from '../geo/MapFrame'

interface Item { lat: number; lon: number; lat2?: number; lon2?: number; value?: number }
export interface StackLayer {
  id?: string | null
  kind: 'regions' | 'bubbles' | 'points' | 'lines' | null
  title?: string
  color?: string | null
  boundary_set_id?: number | null
  measure?: string | null
  regions?: { name: unknown; value: number }[]
  points?: Item[]
  lines?: Item[]
  dropped?: number
  truncation?: { applied?: boolean; shown?: number; of?: number }
  error?: string
}

const layerColor = (l: StackLayer, i: number) => l.color || COLORS[i % COLORS.length]

/** Boundary sets used by the stack, loaded together (countries are built in). */
function useSets(ids: number[]) {
  const key = [...new Set(ids)].sort().join(',')
  const [sets, setSets] = useState<Record<number, RegionSet>>({})
  useEffect(() => {
    let live = true
    for (const id of key ? key.split(',').map(Number) : []) {
      loadRegionSet(id).then(s => { if (live) setSets(prev => ({ ...prev, [id]: s })) }).catch(() => {})
    }
    return () => { live = false }
  }, [key])
  return sets
}

export default function GeoLayerStackRenderer({ data, measureFmt, broadcasts, localSelected,
                                                onClickPoint, plotW, plotH }: ChartRendererProps) {
  const { ref, w, h, tiles } = useMapBox(plotW, plotH)
  const [hover, setHover] = useState<string | null>(null)
  const layers: StackLayer[] = (data as { layers?: StackLayer[] })?.layers ?? []
  const sets = useSets(layers.flatMap(l => (l.boundary_set_id != null && !l.error ? [l.boundary_set_id] : [])))
  const setOf = (l: StackLayer) => (l.boundary_set_id != null ? sets[l.boundary_set_id] ?? null : COUNTRY_SET)

  // Every layer's resolved marks, computed once and shared by the fit and the drawing.
  const resolved = useMemo(() => layers.map(l => {
    if (l.error) return { l, regions: [] as { f: RegionFeature; value: number; name: unknown }[], unmatched: [] as string[] }
    const set = setOf(l)
    const regions: { f: RegionFeature; value: number; name: unknown }[] = []
    const unmatched: string[] = []
    if (set) {
      for (const r of l.regions ?? []) {
        const f = matchRegion(r.name, set)
        if (f) regions.push({ f, value: Number(r.value) || 0, name: r.name })
        else if (r.name != null && String(r.name).trim()) unmatched.push(String(r.name))
      }
    }
    return { l, regions, unmatched }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }), [layers, sets])

  const { projection, path } = useMemo(() => fittedProjection(w, h, resolved.flatMap(({ l, regions }) => [
    ...(l.kind === 'regions' ? regions.flatMap(r => regionBoundsPoints(r.f)) : []),
    ...(l.kind === 'bubbles' ? regions.map(r => regionCentroid(r.f)) : []),
    ...(l.points ?? []).map(p => [p.lon, p.lat] as [number, number]),
    ...(l.lines ?? []).flatMap(p => [[p.lon, p.lat], [p.lon2!, p.lat2!]] as [number, number][]),
  ])), [resolved, w, h, tiles])

  const hoverOn = (text: string) => () => setHover(text)
  const off = () => setHover(null)

  return (
    <div ref={ref} style={MAP_WRAP_STYLE}>
      <MapSvg w={w} h={h} projection={projection} tiles={tiles}
        credit={[...new Set(layers.flatMap(l => {
          const c = !l.error ? setOf(l)?.attribution : undefined
          return c ? [c] : []
        }))].join(' · ') || null}
        role="img" aria-label={`Map with ${layers.filter(l => !l.error).length} layers`}>
        {COUNTRIES.map(f => (
          <path key={f.properties.name} d={path(f) ?? undefined} fill="var(--surface2)" stroke="var(--border)" strokeWidth={0.4} />
        ))}
        {resolved.map(({ l, regions }, i) => {
          if (l.error) return null
          const color = layerColor(l, i)
          const max = Math.max(1e-9, ...regions.map(r => r.value), ...(l.points ?? []).map(p => Number(p.value) || 0),
            ...(l.lines ?? []).map(p => Number(p.value) || 0))
          const set = setOf(l)
          if (l.kind === 'regions') {
            return (
              <g key={i} data-layer={l.id ?? i} data-layer-kind="regions">
                {regions.map((r, j) => {
                  const selected = localSelected != null && localSelected === r.name
                  return (
                    <path key={j} d={path(r.f as never) ?? undefined}
                      fill={`color-mix(in srgb, ${color} ${Math.round((0.2 + 0.8 * (r.value / max)) * 100)}%, var(--surface2))`}
                      stroke={selected ? 'var(--text)' : 'var(--border)'} strokeWidth={selected ? 2 : 0.5}
                      style={broadcasts ? { cursor: 'pointer' } : undefined}
                      onClick={broadcasts ? () => onClickPoint(r.name) : undefined}
                      onMouseEnter={hoverOn(`${l.title}: ${set ? regionLabel(r.f, set) : r.name} — ${fmtStr(r.value, measureFmt)}`)}
                      onMouseLeave={off} />
                  )
                })}
              </g>
            )
          }
          if (l.kind === 'bubbles') {
            return (
              <g key={i} data-layer={l.id ?? i} data-layer-kind="bubbles">
                {regions.map((r, j) => {
                  const pt = projection(regionCentroid(r.f))
                  if (!pt) return null
                  return <circle key={j} cx={pt[0]} cy={pt[1]} r={3 + 14 * Math.sqrt(r.value / max)}
                    fill={color} fillOpacity={0.6} stroke="#fff" strokeWidth={0.75}
                    style={broadcasts ? { cursor: 'pointer' } : undefined}
                    onClick={broadcasts ? () => onClickPoint(r.name) : undefined}
                    onMouseEnter={hoverOn(`${l.title}: ${String(r.name)} — ${fmtStr(r.value, measureFmt)}`)} onMouseLeave={off} />
                })}
              </g>
            )
          }
          if (l.kind === 'points') {
            return (
              <g key={i} data-layer={l.id ?? i} data-layer-kind="points">
                {(l.points ?? []).map((p, j) => {
                  const pt = projection([p.lon, p.lat])
                  if (!pt) return null
                  return <circle key={j} cx={pt[0]} cy={pt[1]} r={p.value != null ? 2.5 + 6 * Math.sqrt((Number(p.value) || 0) / max) : 3}
                    fill={color} fillOpacity={0.8} stroke="#fff" strokeWidth={0.5}
                    onMouseEnter={hoverOn(`${l.title}${p.value != null ? ` — ${fmtStr(Number(p.value), measureFmt)}` : ''}`)} onMouseLeave={off} />
                })}
              </g>
            )
          }
          return (
            <g key={i} data-layer={l.id ?? i} data-layer-kind="lines">
              {(l.lines ?? []).map((p, j) => (
                <path key={j} d={path({ type: 'LineString', coordinates: [[p.lon, p.lat], [p.lon2!, p.lat2!]] } as never) ?? undefined}
                  fill="none" stroke={color} strokeOpacity={0.7}
                  strokeWidth={p.value != null ? 0.75 + 3 * ((Number(p.value) || 0) / max) : 1.2}
                  onMouseEnter={hoverOn(`${l.title}${p.value != null ? ` — ${fmtStr(Number(p.value), measureFmt)}` : ''}`)} onMouseLeave={off} />
              ))}
            </g>
          )
        })}
      </MapSvg>

      <div data-testid="layer-legend" style={{ position: 'absolute', bottom: 4, left: 6, fontSize: 10,
        background: 'color-mix(in srgb, var(--surface) 85%, transparent)', borderRadius: 6, padding: '3px 6px',
        display: 'flex', flexDirection: 'column', gap: 1, maxWidth: '70%' }}>
        {resolved.map(({ l, unmatched }, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <span aria-hidden style={{ width: 8, height: 8, borderRadius: l.kind === 'regions' ? 2 : 4,
              background: l.error ? 'transparent' : layerColor(l, i), border: '1px solid var(--border)' }} />
            <span style={{ color: l.error ? 'var(--danger)' : 'var(--text)' }}>
              {l.title}{l.error ? ` — not drawn: ${l.error}` : ''}
              {!l.error && unmatched.length > 0 && (
                <span style={{ color: 'var(--muted)' }}> · not on the map: {unmatched.slice(0, 3).join(', ')}{unmatched.length > 3 ? '…' : ''}</span>
              )}
              {!l.error && l.truncation?.applied && (
                <span style={{ color: 'var(--muted)' }}> · showing {l.truncation.shown?.toLocaleString()} of {l.truncation.of?.toLocaleString()}</span>
              )}
            </span>
          </div>
        ))}
      </div>
      {hover && (
        <div style={{ position: 'absolute', top: 8, left: 8, fontSize: 11, background: 'var(--surface)',
          border: '1px solid var(--border)', borderRadius: 6, padding: '4px 8px' }}>{hover}</div>
      )}
    </div>
  )
}
