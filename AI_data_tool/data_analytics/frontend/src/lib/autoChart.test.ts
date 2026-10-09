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
import { translate, type MessageKey, type TranslateFn } from '../i18n'

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

describe('the title is in the reader\'s language (QA5b S3)', () => {
  const tAr = ((key: string, vars?: Record<string, string | number>) => translate('ar', key as MessageKey, vars)) as TranslateFn
  const tEn = ((key: string, vars?: Record<string, string | number>) => translate('en', key as MessageKey, vars)) as TranslateFn
  const product: AutoField = { name: 'product', dtype: 'categorical', numeric: false }
  const region: AutoField = { name: 'region', dtype: 'categorical', numeric: false }
  const revenue: AutoField = { name: 'revenue', dtype: 'numeric', numeric: true }
  const units: AutoField = { name: 'units', dtype: 'numeric', numeric: true }
  const date: AutoField = { name: 'date', dtype: 'datetime', numeric: false }
  const sets: AutoField[][] = [[product], [date], [revenue], [region, revenue], [region, revenue, units],
    [date, region, revenue], [region, product, revenue], [region, product], [revenue, units]]

  it('"Count by product" is Arabic, with the field name isolated', () => {
    expect(chartForFields([product], tAr)!.suggestion.title).toBe('العدد حسب ⁨product⁩')
  })

  it('every rule has an Arabic title and the English through the catalog is unchanged', () => {
    for (const s of sets) {
      expect(chartForFields(s, tEn)!.suggestion.title).toBe(chartForFields(s)!.suggestion.title)
      expect(chartForFields(s, tAr)!.suggestion.title).not.toMatch(/\b(by|and|against|Count|Trend|Distribution)\b/)
    }
  })
})

describe('Fields plan F3/F4 — sensible summaries, and lists for links', () => {
  it('a measure starts on its default summary, never a blind sum', () => {
    const price: AutoField = { ...num('price_egp'), summary: 'avg' }
    const r = chartForFields([cat('make'), price])!
    expect(r.suggestion.config.aggregation).toBe('avg')
    // ...and the title says so: "price_egp by make" read as a total.
    expect(r.suggestion.title).toBe('Average price_egp by make')
  })

  it('without a summary it still sums', () => {
    expect(chartForFields([cat('region'), num('revenue')])!.suggestion.config.aggregation).toBe('sum')
  })

  it('a link becomes a list, not thousands of bars of height 1', () => {
    const link: AutoField = { ...cat('item_url'), listOnly: true }
    const r = chartForFields([link])!
    expect(r.suggestion.widget_type).toBe('table')
    expect(r.suggestion.config.columns).toEqual(['item_url'])
  })

  it('a link with other fields lists them, the link last', () => {
    const link: AutoField = { ...cat('item_url'), listOnly: true }
    const r = chartForFields([link, cat('make'), num('price_egp')])!
    expect(r.suggestion.widget_type).toBe('table')
    expect((r.suggestion.config.columns as string[]).at(-1)).toBe('item_url')
  })
})
