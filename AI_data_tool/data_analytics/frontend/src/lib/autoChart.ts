/**
 * Which chart a set of dropped fields should become.
 *
 * One field already worked in `ReportBuilder` (date → line, numeric →
 * histogram, else a bar of counts). SAS handles a MULTI-field drop, and that
 * was the whole of the gap — the rule for one field was never the problem.
 *
 * Pure on purpose. The rules are the interesting part, and a rule table buried
 * in a drop handler can only be argued with by dragging things onto a canvas.
 *
 * Two properties the table is built around:
 *
 *   * **Nothing is silently dropped.** Four fields produce a chart from three
 *     and NAME the fourth, because a chart quietly built from half the fields
 *     is a wrong answer wearing the shape of a right one.
 *
 *   * **The drop order does not decide the answer.** Fields arrive in whatever
 *     order the field list happened to be in; a chart that depends on that is
 *     a chart nobody can predict. Roles are assigned by TYPE, and a date always
 *     wins the axis — a bar of revenue by month sorted alphabetically is the
 *     classic version of this going wrong.
 */

import type { MessageKey, TranslateFn } from '../i18n'

export interface AutoField {
  name: string
  dtype: string
  /** From `isNumericField`, which respects column_meta — a numeric ZIP code is
   *  a category, and this must agree with the field list that showed it. */
  numeric: boolean
  /** The column carries a geography classification (`column_meta.role`). That
   *  is what the role is for: assign it, drop the field, get a map — without
   *  it the classification could be set and did nothing visible. */
  geography?: boolean
}

export interface AutoChart {
  suggestion: {
    widget_type: string
    title: string
    config: Record<string, unknown>
    reason: string
  }
  /** The fields that made it into the config. */
  used: string[]
  /** The fields the rule could not place, for the caller to report. */
  ignored: string[]
}

const isDate = (f: AutoField) => f.dtype === 'datetime'

/** QA5b S3: the title templates, in the reader's language when a translator is
 *  given. Without one (tests, the View-as pick) the English is the same text it
 *  always was. */
type TitleFn = (key: string, p: Record<string, string>) => string
const TITLE_EN: Record<string, string> = {
  countBy: 'Count by {a}', mBy: '{m} by {a}', m2By: '{m1} and {m2} by {a}', mByTwo: '{m} by {a} and {b}',
  aByB: '{a} by {b}', against: '{y} against {x}', dist: 'Distribution of {m}', trend: 'Trend of {f}',
}
const englishTitle: TitleFn = (key, p) => TITLE_EN[key].replace(/\{(\w+)\}/g, (_, k) => p[k])

/** The chart for a dropped set of fields, or null when there is nothing to draw. */
export function chartForFields(fields: AutoField[], t?: TranslateFn): AutoChart | null {
  const title: TitleFn = t ? (key, p) => t(`bc.canvas.auto.${key}` as MessageKey, p) : englishTitle
  const all = fields.filter(f => f && f.name)
  if (all.length === 0) return null

  const dates = all.filter(isDate)
  const measures = all.filter(f => f.numeric && !isDate(f))
  const categories = all.filter(f => !f.numeric && !isDate(f))

  // A date is the axis whenever there is one, then a category. Everything is
  // decided from these three buckets, never from arrival order.
  const axis = dates[0] ?? categories[0] ?? null
  const second = categories[axis && !isDate(axis) ? 1 : 0] ?? null

  const make = (widget_type: string, title: string, config: Record<string, unknown>,
                used: AutoField[]): AutoChart => ({
    suggestion: { widget_type, title, config, reason: '' },
    used: used.map(f => f.name),
    ignored: all.filter(f => !used.includes(f)).map(f => f.name),
  })

  // ── geography beats the generic rules, but never a date ─────────────────
  // A classified column asked for a map explicitly. A DATE still wins the axis:
  // dropping a region and a date has two honest readings, and letting arrival
  // order pick between them is the thing this table exists to prevent.
  const geoField = all.find(f => f.geography && !isDate(f))
  if (geoField && dates.length === 0) {
    const measure = measures[0] ?? null
    const used = measure ? [geoField, measure] : [geoField]
    return make('map_choropleth',
      measure ? title('mBy', { m: measure.name, a: geoField.name }) : title('countBy', { a: geoField.name }),
      measure
        ? { dimension: geoField.name, measure: measure.name, aggregation: 'sum' }
        : { dimension: geoField.name, aggregation: 'count' },
      used)
  }

  // ── one field: the rules that already existed ────────────────────────────
  if (all.length === 1) {
    const f = all[0]
    if (isDate(f)) {
      return make('line', title('trend', { f: f.name }),
        { dimension: f.name, aggregation: 'count' }, [f])
    }
    if (f.numeric) {
      return make('histogram', title('dist', { m: f.name }),
        { measure: f.name, bins: 20 }, [f])
    }
    return make('bar', title('countBy', { a: f.name }),
      { dimension: f.name, aggregation: 'count' }, [f])
  }

  // ── an axis and one measure ──────────────────────────────────────────────
  if (axis && measures.length === 1 && !second) {
    const m = measures[0]
    return make(isDate(axis) ? 'line' : 'bar',
      title('mBy', { m: m.name, a: axis.name }),
      { dimension: axis.name, measure: m.name, aggregation: 'sum' }, [axis, m])
  }

  // ── an axis and two measures: one bar per measure, two scales ────────────
  if (axis && measures.length >= 2 && !second) {
    const [m1, m2] = measures
    return make('dual_axis_bar', title('m2By', { m1: m1.name, m2: m2.name, a: axis.name }),
      { dimension: axis.name, measure: m1.name, measure2: m2.name,
        aggregation: 'sum' }, [axis, m1, m2])
  }

  // ── a date axis with a category to split by ──────────────────────────────
  // "How did this change, broken down by that" — a heatmap of months against
  // regions answers that question far worse than a bar over time whose series
  // is the category.
  if (axis && isDate(axis) && second && measures.length >= 1) {
    const m = measures[0]
    return make('bar', title('mByTwo', { m: m.name, a: axis.name, b: second.name }),
      { dimension: axis.name, dimension2: second.name, measure: m.name,
        aggregation: 'sum' }, [axis, second, m])
  }

  // ── two categories, with or without a measure ────────────────────────────
  if (axis && second && measures.length >= 1) {
    const m = measures[0]
    return make('heatmap', title('mByTwo', { m: m.name, a: axis.name, b: second.name }),
      { dimension: axis.name, dimension2: second.name, measure: m.name,
        aggregation: 'sum' }, [axis, second, m])
  }
  if (axis && second) {
    return make('crosstab', title('aByB', { a: axis.name, b: second.name }),
      { dimension: axis.name, dimension2: second.name, aggregation: 'count' },
      [axis, second])
  }

  // ── no category at all: a numeric against a numeric ──────────────────────
  if (measures.length >= 2) {
    const [x, y] = measures
    return make('numeric_series', title('against', { y: y.name, x: x.name }),
      { measure: x.name, measure2: y.name }, [x, y])
  }

  // ── a lone measure with nothing to put it against ────────────────────────
  if (measures.length === 1) {
    const m = measures[0]
    return make('histogram', title('dist', { m: m.name }),
      { measure: m.name, bins: 20 }, [m])
  }

  // Several dates and nothing else: chart the first as a trend rather than
  // refusing, and name the rest as unused.
  const f = all[0]
  return make('line', title('trend', { f: f.name }),
    { dimension: f.name, aggregation: 'count' }, [f])
}
