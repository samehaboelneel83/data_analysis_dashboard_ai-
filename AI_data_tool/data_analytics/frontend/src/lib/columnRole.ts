/**
 * Identifier-column detection — the frontend mirror of the metadata plane's
 * canonical heuristic (`backend/app/services/metadata/infer_semantic.py`,
 * `classify_role`). An id-like column (state_id, student_id, ...) is numeric
 * in dtype but a CATEGORY in meaning: summing it, or painting it on a
 * continuous color ramp, produces a number/gradient that means nothing.
 *
 * Kept in sync by hand with the backend regex rather than shared at build
 * time — the two run in different languages and the pattern is small enough
 * that drift is easy to catch in review.
 */

/** Same name pattern as infer_semantic.classify_role: id / _id / _key / _uuid / uuid / _code. */
const ID_NAME_PATTERN = /(^id$|_id$|_key$|_uuid$|^uuid$|_code$)/i

/** Same threshold as infer_semantic's _IDENTIFIER_UNIQUENESS. */
const IDENTIFIER_UNIQUENESS = 0.98

interface ColumnLike {
  name: string
  stats?: Record<string, unknown> | null
}

/**
 * True when a column is an identifier wearing a numeric dtype — matched by
 * name, or (when the stats blob happens to carry distinct/row counts) by
 * near-uniqueness. In this codebase `DatasetColumn.stats` is populated as
 * `{}` almost everywhere today, so the name check does most of the work;
 * the count-based check is here for when a caller does have that data
 * (e.g. a future stats blob, or a caller that computed it locally).
 */
export function isIdLikeColumn(col: ColumnLike): boolean {
  if (ID_NAME_PATTERN.test(col.name)) return true

  const stats = col.stats
  if (!stats) return false
  const distinct = Number(stats.distinct_count ?? stats.unique ?? stats.n_unique ?? NaN)
  const rowCount = Number(stats.row_count ?? stats.count ?? NaN)
  if (Number.isFinite(distinct) && Number.isFinite(rowCount) && rowCount > 0) {
    return distinct >= rowCount * IDENTIFIER_UNIQUENESS
  }
  return false
}
