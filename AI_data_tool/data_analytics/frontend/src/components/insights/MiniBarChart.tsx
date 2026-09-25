/**
 * A finding's chart, not a dashboard widget: no axes, no tooltip, no library --
 * just enough to see the shape a sentence just described. Rows already arrive
 * in the {name, value} shape the widget-data endpoint returns for a plain bar
 * or histogram config, so this renders them directly.
 *
 * TWO MODES, because the two charts mean different things by "row order".
 *
 * A categorical bar is a RANKING: the reader wants the biggest first, and the
 * order of the categories carries nothing else. A histogram is a
 * DISTRIBUTION: position on the axis IS the meaning, and sorting its bins by
 * count destroys the only thing the chart was drawn to show. This rendered
 * every chart the first way, so a histogram came out as
 * "16.00–265.20, 265.20–514.40, 4750.80–500…, 514.40–763.60" -- the bins in
 * frequency order, which is not a distribution of anything.
 */

interface Row {
  name: unknown
  value?: unknown
  /** Present on histogram rows only (shape_histogram). Real numbers, so a
   *  label never has to be recovered by parsing the formatted `name`. */
  bin_start?: unknown
  bin_end?: unknown
}

/** Ranked mode shows the leaders; beyond a handful it is a list, not a shape. */
const TOP_N = 5

/** Ordered mode: the most rows a thumbnail inside a bullet can carry before it
 *  stops being a thumbnail. 20 bins at ~11px each is 220px per finding. */
const MAX_BINS = 12

interface Bin { name: string; value: number; lo: number | null; hi: number | null }

/**
 * A bin bound, short enough to read in a 72px column.
 *
 * The server pre-formats `name` as "4750.80–500000.00", which the label column
 * then truncated to "4750.80–500…" -- the bound the reader wanted was the half
 * that got cut. Rebuilt from `bin_start`/`bin_end`, which arrive as real
 * numbers (shape_histogram), so nothing has to be recovered by parsing a
 * display string.
 *
 * Compact rather than a wider column: widening enough for "500000.00" takes
 * the width from the bar, and the bar is the chart.
 */
function compact(n: number): string {
  const abs = Math.abs(n)
  const sign = n < 0 ? '-' : ''
  const scaled = (v: number, suffix: string) => {
    const r = Math.round(v * 10) / 10
    return sign + (Number.isInteger(r) ? r : r.toFixed(1)) + suffix
  }
  if (abs >= 1e9) return scaled(abs / 1e9, 'B')
  if (abs >= 1e6) return scaled(abs / 1e6, 'M')
  if (abs >= 1e3) return scaled(abs / 1e3, 'k')
  // Below a thousand the exact value fits, and rounding it would misstate a
  // bin edge -- "0.8–1.2" and "1–1" are not the same bin.
  if (Number.isInteger(abs)) return sign + abs
  return sign + (Math.round(abs * 100) / 100)
}

/** The label a bin shows: its own bounds when it has them, else the server's. */
function label(b: Bin): string {
  return b.lo != null && b.hi != null ? `${compact(b.lo)}–${compact(b.hi)}` : b.name
}

/**
 * Empty bins at the ENDS are padding; empty bins in the MIDDLE are data.
 *
 * np.histogram spreads its bins evenly between the observed min and max, so a
 * column with one far outlier gets a long tail of zero bins that say only
 * "nothing out here" -- already implied by the axis. A gap BETWEEN populated
 * bins is the opposite: a real hole in the distribution, and the most
 * interesting thing on some charts. So only the ends are trimmed, and a run
 * of interior zeros survives intact.
 */
function trimEmptyEnds(bins: Bin[]): Bin[] {
  let lo = 0
  let hi = bins.length - 1
  while (lo <= hi && bins[lo].value === 0) lo++
  while (hi >= lo && bins[hi].value === 0) hi--
  return bins.slice(lo, hi + 1)
}

/**
 * Too many bins to draw? Merge ADJACENT ones rather than dropping any.
 *
 * Slicing to the first N would cut the tail off, and the tail is usually the
 * finding -- an outlier_impact chart exists precisely to show it. Merging
 * neighbours is just a coarser histogram: counts add, and the merged label
 * spans from the first lower bound to the last upper bound.
 */
function coarsen(bins: Bin[], maxBins: number): Bin[] {
  if (bins.length <= maxBins) return bins
  const groupSize = Math.ceil(bins.length / maxBins)
  const out: Bin[] = []
  for (let i = 0; i < bins.length; i += groupSize) {
    const group = bins.slice(i, i + groupSize)
    out.push({
      name: `${group[0].name.split('–')[0]}–${group[group.length - 1].name.split('–').pop()}`,
      // lo/hi carry the merge, so the label is rebuilt from numbers rather
      // than from the two half-strings above.

      value: group.reduce((n, b) => n + b.value, 0),
      lo: group[0].lo,
      hi: group[group.length - 1].hi,
    })
  }
  return out
}

export default function MiniBarChart({ rows, ordered = false, caption }: {
  rows: Row[]
  /**
   * What the two sides of this chart are, e.g. "sum(total) by region".
   *
   * This chart has no axes to title -- each bar carries its own name and its
   * own number -- but that names the CATEGORIES and never the measure, so a
   * reader could see "west 1,420" without knowing what 1,420 counts. One line
   * above the bars says it, which is the axis-title job at thumbnail size.
   */
  caption?: string
  /**
   * Keep the rows in the order given -- for a histogram, whose bins arrive
   * from the server in ascending range order. Default is ranked, for the
   * categorical bar this was originally written for.
   */
  ordered?: boolean
}) {
  const clean = rows
    .map(r => ({
      name: String(r.name),
      value: Number(r.value),
      lo: typeof r.bin_start === 'number' ? r.bin_start : null,
      hi: typeof r.bin_end === 'number' ? r.bin_end : null,
    }))
    .filter(r => !isNaN(r.value))

  const top = ordered
    ? coarsen(trimEmptyEnds(clean), MAX_BINS)
    : [...clean].sort((a, b) => b.value - a.value).slice(0, TOP_N)

  if (top.length === 0) return null

  const max = Math.max(...top.map(r => Math.abs(r.value)), 1)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 3, marginTop: 8 }}>
      {caption && (
        <div data-testid="mini-bar-caption"
          style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 1,
                   overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
          title={caption}>{caption}</div>
      )}
      {top.map((r, i) => (
        <div key={i} data-testid="mini-bar-row"
          style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11 }}>
          <span style={{ flex: '0 0 72px', color: 'var(--muted)', overflow: 'hidden',
            textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
            title={r.name}>{ordered ? label(r) : r.name}</span>
          <span style={{ flex: 1, background: 'var(--surface2)', borderRadius: 3, height: 8 }}>
            <span style={{ display: 'block', height: '100%', borderRadius: 3, background: 'var(--accent)',
              width: `${(Math.abs(r.value) / max) * 100}%` }} />
          </span>
          <span style={{ flex: '0 0 auto', fontFamily: 'var(--mono)', color: 'var(--muted)' }}>
            {Number.isInteger(r.value) ? r.value : r.value.toFixed(1)}
          </span>
        </div>
      ))}
    </div>
  )
}
