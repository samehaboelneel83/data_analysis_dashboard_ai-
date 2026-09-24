import { useMemo, useState } from 'react'
import type { ChartRendererProps } from './types'
import { fmtStr, TT } from '../chartUtils'
import { matchRegion, regionBoundsPoints, regionLabel, fittedProjection } from '../geo/worldGeometry'
import { MapSvg, MAP_WRAP_STYLE, useMapBox } from '../geo/MapFrame'
import { useRegionSet } from '../geo/regionSetCache'

/**
 * Choropleth: countries shaded by measure value.
 *
 * Consumes the ordinary series shape ({name, value} rows keyed by region), so the
 * whole existing pipeline -- filters, RLS, aggregation, display-rule evaluation --
 * applies without a geo-specific backend. Rows whose region cannot be matched are
 * surfaced as a count rather than silently unpainted: a hole in the map should read
 * as "3 rows didn't match", not as zero.
 *
 * `config.boundary_set_id` picks the shapes; failing that, the dimension
 * column's own geography classification does. Without either this is countries,
 * as it always was; with one it is whatever the org uploaded -- governorates, states,
 * districts -- and the chosen set REPLACES the world rather than layering on it,
 * so a governorate map is framed on Egypt instead of being a speck on a globe.
 */
export default function GeoChoroplethRenderer({ rows, cfg, measureFmt, broadcasts,
                                               localSelected, onClickPoint,
                                               geography, plotW, plotH }: ChartRendererProps) {
  const { ref, w, h, tiles } = useMapBox(plotW, plotH)
  // Precedence, and the order matters: the widget's own setting is a DELIBERATE
  // override and must beat the dataset's classification, which in turn beats
  // the world. Without the middle term a column classified as geography drew a
  // world map -- the classification saved, and nothing read it.
  const dimension = (cfg as { dimension?: string })?.dimension
  const classified = dimension ? geography?.[dimension] ?? null : null
  const setId = (cfg as { boundary_set_id?: number | null })?.boundary_set_id ?? classified
  const { set, loading, error } = useRegionSet(setId)
  const [hover, setHover] = useState<{ name: string; value: number; x: number; y: number } | null>(null)

  // Framed on the countries that actually matched, so a national choropleth
  // fills the tile instead of sitting as a speck on a world map.
  const { projection, path } = useMemo(() => fittedProjection(w, h,
    (rows as { name: unknown }[]).flatMap(r => {
      const f = matchRegion(r.name, set)
      return f ? regionBoundsPoints(f) : []
    })), [rows, set, w, h, tiles])

  const { byFeature, sourceNames, unmatched, unmatchedNames, min, max } = useMemo(() => {
    // Keyed by the FEATURE, not by its name. An uploaded boundary file need not
    // have a `name` property at all -- its regions may be named by `NAME_1` or
    // `shapeName` -- and two features sharing a name would silently merge.
    const byFeature = new Map<object, number>()
    // What the DATA called this region, kept alongside the value. A click has
    // to filter by the row's own name -- rows say "US", the geometry says
    // "United States of America", and `region = United States of America`
    // matches nothing.
    const sourceNames = new Map<object, unknown[]>()
    let unmatched = 0
    const unmatchedNames: string[] = []
    for (const r of rows as { name: unknown; value: number }[]) {
      const f = matchRegion(r.name, set)
      if (!f) { unmatched++; if (r.name != null && String(r.name).trim()) unmatchedNames.push(String(r.name)); continue }
      // Two data rows landing on one region (e.g. "US" and "USA") sum rather than
      // last-write-wins -- they are the same place, and dropping one would understate it.
      byFeature.set(f, (byFeature.get(f) ?? 0) + r.value)
      sourceNames.set(f, [...(sourceNames.get(f) ?? []), r.name])
    }
    const values = [...byFeature.values()]
    return {
      byFeature, sourceNames, unmatched, unmatchedNames,
      min: values.length ? Math.min(...values) : 0,
      max: values.length ? Math.max(...values) : 0,
    }
  }, [rows, set])

  const scale = (v: number) => {
    // Single-hue lightness ramp on the accent colour. A ramp is readable in greyscale
    // (unlike a rainbow) and inherits the report theme.
    const t = max > min ? (v - min) / (max - min) : 0.5
    return `color-mix(in srgb, var(--accent) ${Math.round(15 + t * 85)}%, var(--surface2))`
  }

  return (
    <div ref={ref} style={MAP_WRAP_STYLE}>
      <MapSvg w={w} h={h} projection={projection} tiles={tiles} credit={set.attribution} role="img" aria-label="Choropleth map">
        {set.features.map((f, i) => {
          const v = byFeature.get(f)
          // The set's own naming property, not `name`: an uploaded file may
          // call it NAME_1 or shapeName, and an index in a tooltip tells a
          // reader nothing.
          const label = regionLabel(f, set) || String(i)
          const names = sourceNames.get(f) ?? []
          // One name filters by that value; several (two spellings of the same
          // place) filter by all of them, or the other spelling's rows vanish
          // from every widget on the page.
          const payload: unknown = names.length > 1 ? names : names[0]
          const clickable = broadcasts && v != null && names.length > 0
          const selected = names.length > 0 && (Array.isArray(localSelected)
            ? names.some(n => (localSelected as unknown[]).includes(n))
            : names.includes(localSelected))
          return (
            <path
              key={i}
              d={path(f) ?? undefined}
              fill={v != null ? scale(v) : 'var(--surface2)'}
              stroke={selected ? 'var(--accent)' : 'var(--border)'}
              strokeWidth={selected ? 2.5 : 0.5}
              data-country={label}
              data-value={v}
              data-selected={selected ? 'true' : undefined}
              style={clickable ? { cursor: 'pointer' } : undefined}
              onClick={clickable ? () => onClickPoint(payload) : undefined}
              onMouseMove={v != null ? e => {
                const box = (e.currentTarget.ownerSVGElement as SVGSVGElement).getBoundingClientRect()
                setHover({ name: label, value: v, x: e.clientX - box.left, y: e.clientY - box.top })
              } : undefined}
              onMouseLeave={() => setHover(null)}
            />
          )
        })}
      </MapSvg>
      {hover && (
        <div style={{ ...TT, position: 'absolute', left: hover.x + 10, top: hover.y + 10,
          padding: '4px 8px', pointerEvents: 'none' }}>
          {hover.name}: {fmtStr(hover.value, measureFmt)}
        </div>
      )}
      {loading && (
        <div data-testid="geo-loading" style={{ position: 'absolute', top: 6, left: 8,
          fontSize: 10, color: 'var(--muted)' }}>Loading boundaries…</div>
      )}
      {error && (
        <div role="alert" style={{ position: 'absolute', top: 6, left: 8,
          fontSize: 10, color: 'var(--danger)' }}>{error}</div>
      )}
      {!loading && unmatched > 0 && (
        <div data-testid="geo-unmatched" style={{ position: 'absolute', bottom: 4, left: 8,
          fontSize: 10, color: 'var(--muted)' }}>
          {unmatched} row{unmatched === 1 ? '' : 's'} did not match a
          {setId != null ? ' region in this boundary set' : ' country'}
          {/* Named, so the reader knows WHICH places are missing from the
              picture -- a count alone cannot be acted on. */}
          {unmatchedNames.length > 0 && `: ${unmatchedNames.slice(0, 3).join(', ')}${unmatchedNames.length > 3 ? '…' : ''}`}
        </div>
      )}
    </div>
  )
}
