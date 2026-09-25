/**
 * Dropping fields on the canvas and getting the right chart.
 *
 * One field already worked (date → line, numeric → histogram, else bar). SAS
 * handles a MULTI-field drop, and that is the whole of this gap: the rules for
 * two and three fields, kept pure so they can be argued with in a test rather
 * than discovered by dragging.
 *
 * Two properties matter more than which chart each combination picks:
 *
 *  - **Nothing is silently dropped.** A four-field drop charts what it can and
 *    NAMES what it left out; a chart quietly built from half the fields is a
 *    wrong answer that looks like a right one.
 *  - **Order of the drop does not change the answer.** Fields arrive in
 *    whatever order the list was in, and a chart that depends on that is a
 *    chart the user cannot predict.
 */
import { describe, it, expect } from 'vitest'
import { chartForFields, type AutoField } from './autoChart'

const cat = (name: string): AutoField => ({ name, dtype: 'categorical', numeric: false })
const num = (name: string): AutoField => ({ name, dtype: 'numeric', numeric: true })
const date = (name: string): AutoField => ({ name, dtype: 'datetime', numeric: false })

describe('one field — the rules that already existed', () => {
  it('a date becomes a trend line', () => {
    const r = chartForFields([date('ordered_at')])!
    expect(r.suggestion.widget_type).toBe('line')
    expect(r.suggestion.config.dimension).toBe('ordered_at')
  })

  it('a number becomes a distribution', () => {
    const r = chartForFields([num('revenue')])!
    expect(r.suggestion.widget_type).toBe('histogram')
    expect(r.suggestion.config.measure).toBe('revenue')
  })

  it('anything else becomes a count by that field', () => {
    const r = chartForFields([cat('region')])!
    expect(r.suggestion.widget_type).toBe('bar')
    expect(r.suggestion.config.aggregation).toBe('count')
  })
})

describe('two fields', () => {
  it('a category and a measure become a bar of the measure', () => {
    // Not a count: dropping revenue next to region asks about revenue.
    const r = chartForFields([cat('region'), num('revenue')])!
    expect(r.suggestion.widget_type).toBe('bar')
    expect(r.suggestion.config).toMatchObject({
      dimension: 'region', measure: 'revenue', aggregation: 'sum' })
  })

  it('the same two fields in the other order give the same chart', () => {
    const a = chartForFields([cat('region'), num('revenue')])!
    const b = chartForFields([num('revenue'), cat('region')])!
    expect(b.suggestion).toEqual(a.suggestion)
  })

  it('a date and a measure become a trend of the measure', () => {
    const r = chartForFields([date('ordered_at'), num('revenue')])!
    expect(r.suggestion.widget_type).toBe('line')
    expect(r.suggestion.config).toMatchObject({
      dimension: 'ordered_at', measure: 'revenue', aggregation: 'sum' })
  })

  it('a date wins over a plain category as the axis', () => {
    // Time is the axis whenever there is one; a bar of revenue by month
    // ordered alphabetically is the classic version of this going wrong.
    const r = chartForFields([cat('region'), date('ordered_at'), num('revenue')])!
    expect(r.suggestion.config.dimension).toBe('ordered_at')
  })

  it('two measures become a numeric x/y plot, not a bar', () => {
    const r = chartForFields([num('spend'), num('revenue')])!
    expect(r.suggestion.widget_type).toBe('numeric_series')
    expect(r.suggestion.config).toMatchObject({ measure: 'spend', measure2: 'revenue' })
  })

  it('two categories become a crosstab of counts', () => {
    const r = chartForFields([cat('region'), cat('segment')])!
    expect(r.suggestion.widget_type).toBe('crosstab')
    expect(r.suggestion.config).toMatchObject({
      dimension: 'region', dimension2: 'segment', aggregation: 'count' })
  })
})

describe('three fields', () => {
  it('two categories and a measure become a heatmap', () => {
    const r = chartForFields([cat('region'), cat('segment'), num('revenue')])!
    expect(r.suggestion.widget_type).toBe('heatmap')
    expect(r.suggestion.config).toMatchObject({
      dimension: 'region', dimension2: 'segment', measure: 'revenue' })
  })

  it('a category and two measures become a dual-axis bar', () => {
    const r = chartForFields([cat('region'), num('revenue'), num('cost')])!
    expect(r.suggestion.widget_type).toBe('dual_axis_bar')
    expect(r.suggestion.config).toMatchObject({
      dimension: 'region', measure: 'revenue', measure2: 'cost' })
  })
})

describe('it never charts less than it was given without saying so', () => {
  it('names the fields it could not use', () => {
    const r = chartForFields([cat('region'), cat('segment'), cat('channel'), num('revenue')])!
    expect(r.ignored).toContain('channel')
    expect(r.used).toEqual(expect.arrayContaining(['region', 'segment', 'revenue']))
  })

  it('reports nothing ignored when it used everything', () => {
    const r = chartForFields([cat('region'), num('revenue')])!
    expect(r.ignored).toEqual([])
  })

  it('every used field appears in the config it produced', () => {
    // The property that stops a rule claiming a field and then dropping it.
    const r = chartForFields([cat('region'), num('revenue'), num('cost')])!
    const values = Object.values(r.suggestion.config).map(String)
    for (const f of r.used) expect(values).toContain(f)
  })

  it('an empty drop produces nothing rather than an empty chart', () => {
    expect(chartForFields([])).toBeNull()
  })
})

describe('the title says what the chart shows', () => {
  it('names both fields for a two-field chart', () => {
    const r = chartForFields([cat('region'), num('revenue')])!
    expect(r.suggestion.title).toContain('revenue')
    expect(r.suggestion.title).toContain('region')
  })
})

describe('a date, a category and a measure', () => {
  it('stacks the category over time rather than making a heatmap', () => {
    // Both are defensible for two plain categories, but when one axis is TIME
    // the question is almost always "how did this change, split by that" — and
    // a heatmap of months against regions answers it far worse than a bar over
    // time with the category as its series.
    const r = chartForFields([date('ordered_at'), cat('region'), num('revenue')])!
    expect(r.suggestion.widget_type).toBe('bar')
    expect(r.suggestion.config).toMatchObject({
      dimension: 'ordered_at', dimension2: 'region', measure: 'revenue' })
    expect(r.ignored).toEqual([])
  })

  it('still heatmaps two plain categories with a measure', () => {
    const r = chartForFields([cat('region'), cat('segment'), num('revenue')])!
    expect(r.suggestion.widget_type).toBe('heatmap')
  })
})

/**
 * A column classified as geography should drop as a map.
 *
 * That is what the role is FOR — SAS's geography roles exist so that assigning
 * one and dropping the field gives you a map without configuring an object.
 * Ours could be assigned, drew nothing, and dropped as a bar of counts like any
 * other text column, which left the classification looking decorative.
 */
describe('a geography column', () => {
  const geo = (name: string): AutoField =>
    ({ name, dtype: 'categorical', numeric: false, geography: true })

  it('drops as a choropleth rather than a bar of counts', () => {
    const out = chartForFields([geo('governorate')])
    expect(out?.suggestion.widget_type).toBe('map_choropleth')
    expect(out?.suggestion.config.dimension).toBe('governorate')
  })

  it('maps the measure it was dropped with', () => {
    const out = chartForFields([geo('governorate'),
      { name: 'revenue', dtype: 'numeric', numeric: true }])
    expect(out?.suggestion.widget_type).toBe('map_choropleth')
    expect(out?.suggestion.config.measure).toBe('revenue')
    expect(out?.used).toEqual(expect.arrayContaining(['governorate', 'revenue']))
  })

  it('leaves an unclassified text column alone', () => {
    const out = chartForFields([{ name: 'status', dtype: 'categorical', numeric: false }])
    expect(out?.suggestion.widget_type).toBe('bar')
  })

  it('still prefers a date axis, because a trend is the stronger question', () => {
    // Two legitimate readings; picking the map would make dropping a date
    // alongside a region do something the arrival order cannot explain.
    const out = chartForFields([geo('governorate'),
      { name: 'ordered_at', dtype: 'datetime', numeric: false }])
    expect(out?.suggestion.widget_type).not.toBe('map_choropleth')
  })
})
