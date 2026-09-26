/**
 * What a map shows, for someone who cannot see it (E15).
 *
 * A map was an image with a two-word name ("Choropleth map"): a screen reader
 * heard that and nothing else, and a keyboard could not reach a region. Every
 * map now names what it plots, how many places carry a value and the highest
 * and lowest; and carries its values as a table that is read, not drawn.
 */
import { fmtStr } from '../chartUtils'

export interface MapEntry { label: string; value: number }

const MAX_ROWS = 200

/** One sentence: what, how many, the extremes. */
export function mapSummary(kind: string, entries: MapEntry[], measureFmt?: unknown): string {
  if (!entries.length) return `${kind}: no values to show`
  const sorted = [...entries].sort((a, b) => b.value - a.value)
  const hi = sorted[0], lo = sorted[sorted.length - 1]
  const f = (v: number) => fmtStr(v, measureFmt as never)
  const n = `${entries.length} ${entries.length === 1 ? 'place' : 'places'}`
  return entries.length === 1
    ? `${kind}: ${n}, ${hi.label} ${f(hi.value)}`
    : `${kind}: ${n}; highest ${hi.label} ${f(hi.value)}, lowest ${lo.label} ${f(lo.value)}`
}

/** The values behind the map, largest first, visually hidden. */
export function MapDataTable({ caption, entries, measureFmt, unmatched = 0 }: {
  caption: string; entries: MapEntry[]; measureFmt?: unknown; unmatched?: number
}) {
  const sorted = [...entries].sort((a, b) => b.value - a.value)
  return (
    <table className="dl-sr-only" data-testid="map-data-table">
      <caption>{caption}{unmatched > 0 ? ` (${unmatched} row${unmatched === 1 ? '' : 's'} not placed on the map)` : ''}</caption>
      <thead><tr><th scope="col">Place</th><th scope="col">Value</th></tr></thead>
      <tbody>
        {sorted.slice(0, MAX_ROWS).map((e, i) => (
          <tr key={`${e.label}-${i}`}><th scope="row">{e.label}</th><td>{fmtStr(e.value, measureFmt as never)}</td></tr>
        ))}
        {sorted.length > MAX_ROWS && (
          <tr><td colSpan={2}>{`… and ${sorted.length - MAX_ROWS} more`}</td></tr>
        )}
      </tbody>
    </table>
  )
}
