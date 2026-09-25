/**
 * Inline field hints — SAS's "related measures" icon and outlier marker.
 *
 * The statistics were already there: `analyze_numeric` computes a Pearson matrix and
 * a per-column IQR outlier count. They were just never surfaced next to the fields
 * themselves, which is where they are actually useful — noticing that two measures
 * move together while you are choosing what to chart.
 *
 * The thresholds follow SAS's documented behaviour where it states one, and say so
 * where it does not:
 *   - |r| >= 0.6 counts as related (SAS's stated threshold)
 *   - above 150 measures, correlation is not reported at all (SAS's stated cutoff)
 *   - below 56 rows, SAS says it raises the threshold but not to what. 0.8 is this
 *     app's choice, not SAS's — small samples throw up strong correlations by chance.
 */

export interface FieldHint {
  /** Count of values outside 1.5x IQR. Absent when there are none. */
  outliers?: number
  /** Other measures this one moves with, strongest first. Absent when none. */
  related?: { column: string; r: number }[]
  /** How many distinct values a category holds. The single most useful thing
   *  to know before charting one: 47 countries is a bar chart, 748K order IDs
   *  is a mistake. `analyze_categorical` has computed this as `n_unique` all
   *  along and nothing showed it. */
  distinct?: number
}

/** "748K" rather than "748,000" — the exact figure is noise at that size and
 *  the field list is a narrow column. SAS abbreviates the same way. */
export function countLabel(n: number): string {
  if (!Number.isFinite(n)) return ''
  const abs = Math.abs(n)
  if (abs >= 1e6) return `${trim(n / 1e6)}M`
  if (abs >= 1e3) return `${trim(n / 1e3)}K`
  return String(n)
}

function trim(v: number): string {
  // 3.2K keeps its decimal; 748K does not need one.
  const rounded = Math.round(v * 10) / 10
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1)
}

const STRONG = 0.6
const SMALL_SAMPLE_STRONG = 0.8
const SMALL_SAMPLE_ROWS = 56
const MAX_MEASURES = 150

export function fieldHints(analysis: any, rowsOverride?: number): Record<string, FieldHint> {
  const out: Record<string, FieldHint> = {}

  // Distinct counts come from the CATEGORICAL profile, which a dataset can have
  // without any numeric columns at all -- so this runs before the numeric
  // section's early return rather than after it.
  for (const [col, stats] of Object.entries<any>(analysis?.categorical?.columns ?? {})) {
    const n = Number(stats?.n_unique)
    if (Number.isFinite(n)) (out[col] ??= {}).distinct = n
  }

  const numeric = analysis?.numeric
  if (!numeric) return out

  const rows = rowsOverride ?? Number(analysis?.overview?.rows ?? 0)
  const threshold = rows > 0 && rows < SMALL_SAMPLE_ROWS ? SMALL_SAMPLE_STRONG : STRONG

  for (const [col, stats] of Object.entries<any>(numeric.columns ?? {})) {
    const n = Number(stats?.iqr_outliers ?? 0)
    if (n > 0) (out[col] ??= {}).outliers = n
  }

  const corr = numeric.correlation
  // Past a certain width the pairings stop being informative and the matrix itself
  // gets expensive to walk, so skip rather than emit noise.
  if (corr && Object.keys(corr).length <= MAX_MEASURES) {
    for (const [col, row] of Object.entries<any>(corr)) {
      const related = Object.entries<any>(row ?? {})
        .filter(([other, r]) =>
          other !== col && typeof r === 'number' && Number.isFinite(r) && Math.abs(r) >= threshold)
        .map(([other, r]) => ({ column: other, r: r as number }))
        // Strongest first, by magnitude — a -0.95 is a stronger relationship than a 0.65.
        .sort((a, b) => Math.abs(b.r) - Math.abs(a.r))
      if (related.length > 0) (out[col] ??= {}).related = related
    }
  }

  return out
}

/** Human-readable tooltip for a field's hints, or '' when there is nothing to say. */
export function hintTitle(hint: FieldHint | undefined): string {
  if (!hint) return ''
  const parts: string[] = []
  if (hint.outliers) parts.push(`${hint.outliers} outlier${hint.outliers === 1 ? '' : 's'} beyond 1.5×IQR`)
  if (hint.related?.length) {
    parts.push('moves with ' + hint.related.map(r => `${r.column} (r=${r.r.toFixed(2)})`).join(', '))
  }
  return parts.join(' · ')
}
