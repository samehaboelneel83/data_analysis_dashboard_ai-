import type { Dataset } from '../services/api'
import { AGGREGATIONS } from '../types/report'

/** Shown wherever an aggregate dataset is named in the builder. */
export const PRE_AGGREGATED_HINT =
  'Pre-aggregated: each row is a group. Measures are already summed; an average is x_sum / row_count.'

// sum/min/max are the only aggregations `services/aggregates.py` allows a
// SOURCE measure to compile into, precisely because they are the only ones
// that still mean the same thing re-aggregated at a coarser grain -- SUM of
// SUMs is the true sum, MAX of MAXes is the true max. Everything else on this
// select (avg, the percentiles, the statistical group, ...) does not survive
// that, over a measure the aggregate has already collapsed.
const RE_AGGREGATES_CORRECTLY = new Set(['sum', 'min', 'max'])

// Everything that counts rows rather than reading the measure. 'countd' is
// the real select value (AGGREGATIONS in types/report.ts); 'count_distinct'
// and 'distinct' are backend synonyms (widget_data._agg_series,
// suggest_dataset_dashboard). 'frequency' and 'pct' belong here too: the
// shaper takes groupby(dim).size() for both and pct divides that by the
// total, so neither ever touches the measure -- over a grain column they
// count groups exactly as count does.
const COUNT_FAMILY = new Set(['count', 'countd', 'count_distinct', 'distinct', 'frequency', 'pct'])

// Derived from the select itself, not hard-coded: a label for any value
// AGGREGATIONS offers, so a new aggregation added there is warned about here
// automatically instead of silently falling through as safe.
const AGGREGATION_LABELS = new Map(AGGREGATIONS.map(a => [a.value, a.label]))

/**
 * The consumption-side half of the aggregate design: the Aggregates tab says
 * measures are pre-aggregated, and now the builder does too, at the moment an
 * author picks an aggregation that does not re-aggregate correctly. `avg` over
 * `amount_sum` is an average of sums; `count` counts groups, not rows -- a KPI
 * can read "2 orders" where the truth is 5, with no error anywhere.
 */
export function aggregationWarning(ds: Dataset | undefined, measure: string, aggregation: string): string | null {
  const spec = ds?.aggregate_spec
  if (!ds?.aggregate_of_dataset_id || !spec) return null
  // 'countd' is the real select value (AGGREGATIONS in types/report.ts);
  // 'count_distinct' is a backend synonym (e.g. suggest_dataset_dashboard
  // normalises count_distinct -> countd) -- both must be caught here.
  if (COUNT_FAMILY.has(aggregation)) {
    return 'On a pre-aggregated dataset this counts groups, not rows. For the row count use sum(row_count).'
  }
  if (RE_AGGREGATES_CORRECTLY.has(aggregation)) return null
  // A DERIVED measure: one of the aggregate's own measures, or the reserved
  // row_count column every aggregate carries. A GRAIN column (tenant,
  // region, ...) is untouched by the aggregation step and stays silent --
  // p90 over `region` is exactly as valid here as anywhere else.
  const derived = new Set(spec.measures.map(m => m.name))
  derived.add('row_count')
  if (!derived.has(measure)) return null
  if (aggregation === 'avg' || aggregation === 'mean' || aggregation === 'average') {
    if (measure === 'row_count') {
      // sum(row_count) / sum(row_count) is 1; the honest figure is rows per group.
      return 'On a pre-aggregated dataset this is the average of the groups\' row counts, not an average of rows: rows per group is sum(row_count) / the number of groups.'
    }
    return `On a pre-aggregated dataset this is an average of sums, not of rows. For the true average use sum(${measure}) / sum(row_count).`
  }
  const label = AGGREGATION_LABELS.get(aggregation) ?? aggregation
  return `On a pre-aggregated dataset ${label} is computed over group totals, not rows, and does not re-aggregate correctly.`
}
