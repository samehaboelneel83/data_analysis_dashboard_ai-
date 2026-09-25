import { describe, it, expect } from 'vitest'
import { seriesName, axisTitles, brushProps, xAxisProps, yAxisProps, yAxisWidth, gridProps, legendProps, labelListProps, MAX_DATA_LABELS } from './axisOptions'

describe('xAxisProps', () => {
  it('reproduces the current hard-coded defaults when no config is set', () => {
    const p = xAxisProps({}, false)
    expect(p.tick).toEqual({ fill: 'var(--muted)', fontSize: 10 })
    expect(p.axisLine).toBe(false)
    expect(p.tickLine).toBe(false)
    expect(p.reversed).toBe(false)
  })

  it('reverses for RTL', () => {
    expect(xAxisProps({}, true).reversed).toBe(true)
  })

  it('applies tick font size and colour overrides', () => {
    const p = xAxisProps({ axis_tick_size: 14, axis_tick_color: '#f00' }, false)
    expect(p.tick).toEqual({ fill: '#f00', fontSize: 14 })
  })

  it('shows the axis line when asked', () => {
    expect(xAxisProps({ axis_line: true }, false).axisLine).toBe(true)
  })

  it('applies a label when one is set, and omits it otherwise', () => {
    // The title is drawn INSIDE the axis band, in the lane `height` reserves
    // for it. Recharts positions an axis label relative to the AXIS box (its
    // own x/y/width/height), not the plot: 'insideBottom' is the bottom of
    // the tick band, and 'bottom' is BELOW the band -- which, on a chart with
    // a legend, is the legend. Measured in Chrome on a stacked bar at 380x220:
    // title at 178-193px, legend at 183-198px, printed on top of each other,
    // while the band's reserved lane sat empty above them.
    expect(xAxisProps({ x_axis_label: 'Region' }, false).label)
      .toEqual({ value: 'Region', position: 'insideBottom', offset: 4, fill: 'var(--muted)', fontSize: 11 })
    expect(xAxisProps({}, false).label).toBeUndefined()
  })
})

describe('yAxisProps', () => {
  it('reproduces the current hard-coded defaults', () => {
    const p = yAxisProps({}, false)
    expect(p.tick).toEqual({ fill: 'var(--muted)', fontSize: 10 })
    expect(p.axisLine).toBe(false)
    expect(p.tickLine).toBe(false)
    expect(p.orientation).toBe('left')
    expect(p.allowDecimals).toBe(false)
    expect(p.domain).toBeUndefined()
    expect(p.scale).toBeUndefined()
  })

  it('puts the axis on the right for RTL', () => {
    expect(yAxisProps({}, true).orientation).toBe('right')
  })

  it('builds a fixed domain from min and max', () => {
    expect(yAxisProps({ y_min: 0, y_max: 500 }, false).domain).toEqual([0, 500])
  })

  it('uses auto for the unset half of a partial domain', () => {
    expect(yAxisProps({ y_min: 10 }, false).domain).toEqual([10, 'auto'])
    expect(yAxisProps({ y_max: 90 }, false).domain).toEqual(['auto', 90])
  })

  it('applies a log scale when asked', () => {
    const p = yAxisProps({ y_scale: 'log' }, false)
    expect(p.scale).toBe('log')
    expect(p.domain).toEqual(['auto', 'auto'])
  })

  it('falls back to a linear auto domain when log is asked for but the data contains a non-positive value', () => {
    // Recharts cannot render a log axis through zero; an empty chart is a worse
    // answer than a linear one, so the caller passes the observed minimum.
    const p = yAxisProps({ y_scale: 'log' }, false, undefined, undefined, 0)
    expect(p.scale).toBeUndefined()
    expect(p.domain).toBeUndefined()
  })

  it('degrades from log to linear when y_min is set to zero', () => {
    // User setting y_min=0 with log scale is a likely input; Recharts cannot render it.
    // The explicit y_min must still reach the domain even though scale degrades --
    // only the scale is allowed to fall back, not the author's bounds.
    const p = yAxisProps({ y_scale: 'log', y_min: 0 }, false)
    expect(p.scale).toBeUndefined()
    expect(p.domain).toEqual([0, 'auto'])
  })

  it('preserves log scale when y_min is positive', () => {
    // Log scale is safe when the requested minimum is positive.
    const p = yAxisProps({ y_scale: 'log', y_min: 10 }, false)
    expect(p.scale).toBe('log')
    expect(p.domain).toEqual([10, 'auto'])
  })
})

describe('gridProps', () => {
  it('defaults to faint, solid, horizontal-only rules', () => {
    expect(gridProps({})).toEqual({ strokeDasharray: undefined, stroke: 'var(--dl-table-rule, var(--border))', vertical: false })
  })

  it('keeps the dashed grid one setting away', () => {
    expect(gridProps({ grid_style: 'dashed' })).toMatchObject({ strokeDasharray: '3 3' })
  })

  it('returns null when grid lines are turned off, so the caller omits the element', () => {
    expect(gridProps({ grid: false })).toBeNull()
  })

  it('supports a solid grid and a custom colour', () => {
    expect(gridProps({ grid_style: 'solid', grid_color: '#333' }))
      .toEqual({ strokeDasharray: undefined, stroke: '#333', vertical: false })
  })
})

describe('legendProps', () => {
  it('reproduces the current default legend placement', () => {
    expect(legendProps({})).toEqual({
      verticalAlign: 'bottom', align: 'center', layout: 'horizontal',
    })
  })

  it('returns null when the legend is turned off, so the caller omits the element', () => {
    expect(legendProps({ legend: false })).toBeNull()
  })

  it('places the legend on the right as a vertical list', () => {
    const p = legendProps({ legend_position: 'right' })!
    expect(p.align).toBe('right')
    expect(p.layout).toBe('vertical')
    expect(p.verticalAlign).toBe('middle')
  })

  it('places the legend on top', () => {
    const p = legendProps({ legend_position: 'top' })!
    expect(p.verticalAlign).toBe('top')
    expect(p.layout).toBe('horizontal')
  })
})

describe('labelListProps', () => {
  it('returns null by default, since data labels are opt-in', () => {
    expect(labelListProps({})).toBeNull()
  })

  it('returns a LabelList config when data labels are on', () => {
    const p = labelListProps({ data_labels: true })!
    expect(p.position).toBe('top')
    expect(p.style).toEqual({ fill: 'var(--muted)', fontSize: 10 })
  })

  it('formats label values with the measure format when one is given', () => {
    // Reads through `valueAccessor` rather than `formatter`: Recharts calls
    // `formatter(label)` with one argument, so a formatter cannot know which
    // point it is on -- and the index is what thinning needs.
    const p = labelListProps({ data_labels: true },
      { type: 'currency', symbol: '$', decimals: 0 })!
    expect(p.valueAccessor({ value: 1234 }, 0)).toContain('$')
  })

  it('reads the series a multi-series renderer names', () => {
    const p = labelListProps({ data_labels: true }, undefined, 'Revenue')!
    // toLocaleString renders Arabic-Indic digits in this environment, so the
    // assertion is that the RIGHT SERIES was read, not the glyphs used.
    expect(p.valueAccessor({ Revenue: 42 }, 0)).toBe((42).toLocaleString())
    expect(p.valueAccessor({ Revenue: 42, value: 999 }, 0))
      .not.toContain((999).toLocaleString())
  })
})

describe('chart element collision', () => {
  // Two independent collisions, both fixed at this one choke point because all
  // 18 renderers build their axis props and their data labels here.
  //
  //   1. Every category tick was drawn -- fifty names overprinted into a smear.
  //   2. Every point was labelled -- fifty numbers over fifty marks.
  //
  // These are written so that reverting either fix fails them: the label
  // assertions COUNT the survivors rather than spot-checking one, so restoring
  // "label everything" is caught even though each individual label is correct.

  const labelsFor = (n: number) => {
    const p = labelListProps({ data_labels: true }, undefined, 'value', n)!
    return Array.from({ length: n }, (_, i) =>
      p.valueAccessor({ value: i }, i) as string)
  }

  it('declutters the category axis instead of drawing every tick', () => {
    const x = xAxisProps({}, false)
    // preserveStartEnd rather than a plain interval number: it keeps the first
    // and last tick, which are the two a reader looks for to know the range.
    expect(x.interval).toBe('preserveStartEnd')
    expect(x.minTickGap).toBeGreaterThan(0)
  })

  it('labels every point while they still fit', () => {
    expect(labelsFor(MAX_DATA_LABELS).filter(Boolean))
      .toHaveLength(MAX_DATA_LABELS)
  })

  it('thins the labels on a long series rather than overprinting them', () => {
    // THE test: fifty labels on fifty marks is a band of text naming nothing.
    const shown = labelsFor(50).filter(Boolean)
    expect(shown.length).toBeLessThanOrEqual(MAX_DATA_LABELS)
    expect(shown.length).toBeGreaterThan(1)
  })

  it('always keeps the newest point, which is the one being asked about', () => {
    // Anchored on the LAST point, not the first. A naive `i % stride === 0`
    // drops the final value whenever n-1 is not a multiple of the stride --
    // labelling everything except the number the reader came for.
    for (const n of [13, 25, 37, 50, 99, 100, 1000]) {
      const shown = labelsFor(n)
      expect(shown[n - 1], `n=${n}`).not.toBe('')
      expect(shown.filter(Boolean).length, `n=${n}`)
        .toBeLessThanOrEqual(MAX_DATA_LABELS)
    }
  })

  it('drops only the text, leaving the mark and its tooltip intact', () => {
    // Returning '' rather than filtering the data: the point is still plotted
    // and still hoverable, and only its printed number goes away.
    const p = labelListProps({ data_labels: true }, undefined, 'value', 50)!
    expect(p.valueAccessor({ value: 7 }, 1)).toBe('')
    expect(p.position).toBe('top')
  })

  it('labels everything when a renderer passes no count', () => {
    // The signature took three arguments before this change. A caller not yet
    // threaded through keeps its old behaviour rather than silently losing
    // labels -- the thinning is opt-in per renderer.
    const p = labelListProps({ data_labels: true })!
    for (let i = 0; i < 40; i++) {
      expect(p.valueAccessor({ value: i }, i)).not.toBe('')
    }
  })
})

describe('brushProps', () => {
  it('returns null by default — the overview axis is opt-in chrome', () => {
    expect(brushProps({})).toBeNull()
    expect(brushProps({ overview_axis: false })).toBeNull()
  })

  it('returns Brush props keyed to the category axis when opted in', () => {
    const p = brushProps({ overview_axis: true })!
    expect(p.dataKey).toBe('name')
    expect(p.height).toBe(18)
  })

  it('carries a mini chart of the whole series and reports the zoomed range (Phase 6.3)', () => {
    const rows = [{ name: 'Jan', value: 1 }, { name: 'Feb', value: 2 }, { name: 'Mar', value: 3 }, { name: 'Apr', value: 4 }]
    const seen: unknown[] = []
    const p = brushProps({ overview_axis: true }, { rows, dataKey: 'value', onChange: r => seen.push(r) })! as any
    expect(p.height).toBe(30)
    expect(p.children).toBeTruthy()
    p.onChange({ startIndex: 1, endIndex: 2 })
    p.onChange({ startIndex: 0, endIndex: 3 })
    expect(seen).toEqual([{ start: 'Feb', end: 'Mar', startIndex: 1, endIndex: 2, of: 4 }, null])
  })
})

describe('axes reserve enough room for their labels', () => {
  // From the Arabic dashboard screenshot: "$ 2,000,000" printed over the bars
  // on one axis and was clipped by the card edge on the other, because
  // Recharts' default y-axis width is 60px and never grows.

  it('widens the value axis for the values it will actually draw', () => {
    const small = yAxisProps({}, false, undefined, [10, 20, 30]).width
    const big = yAxisProps({}, false, undefined, [1_000_000, 2_000_000]).width
    expect(big).toBeGreaterThan(small as number)
  })

  it('widens for large values even when NO format is configured', () => {
    // The regression that made the first attempt at this fix useless. The
    // earlier estimator keyed off the FORMAT, so a widget with no explicit
    // format stayed at 60px -- but its ticks still render "2,000,000" because
    // the tick FORMATTER, not the format config, produces the label. That is
    // the commonest case, and it is the one in the user's screenshot.
    expect(yAxisProps({}, false, undefined, [2_000_000]).width).toBeGreaterThan(60)
    expect(yAxisProps({}, false, null as never, [2_000_000]).width).toBeGreaterThan(60)
  })

  it('widens the value axis for a currency format', () => {
    const plain = yAxisProps({}, false, undefined, [1500]).width
    const money = yAxisProps({}, false, { type: 'currency', symbol: '$', decimals: 2 } as never,
                             [2_000_000]).width
    expect(money).toBeGreaterThan(plain as number)
    // "$2,000,000.00" is about 13 characters at ~6.2px.
    expect(money).toBeGreaterThanOrEqual(90)
  })

  it('measures an author-set bound that no datum reaches', () => {
    // y_max is drawn as a tick even when the data stops far below it, and
    // yAxisProps already honours it in `domain`.
    expect(yAxisProps({ y_max: 5_000_000 }, false, undefined, [12]).width)
      .toBeGreaterThan(yAxisProps({}, false, undefined, [12]).width as number)
  })

  it('keeps the default width when it has nothing to measure', () => {
    expect(yAxisProps({}, false).width).toBe(60)
    expect(yAxisProps({}, false, undefined, []).width).toBe(60)
    // Small values must not SHRINK the axis below Recharts' default.
    expect(yAxisProps({}, false, undefined, [1, 2, 3]).width).toBe(60)
  })

  it('ignores non-numeric values rather than counting their text', () => {
    // A category axis passing names through would otherwise size the gutter
    // from a long label that is never drawn as a tick.
    expect(yAxisProps({}, false, undefined, ['some very long category name']).width).toBe(60)
  })

  it('bounds the width so an absurd label cannot eat the plot', () => {
    expect(yAxisProps({}, false, { type: 'currency', symbol: '$', decimals: 6 } as never,
                      [1e21]).width).toBeLessThanOrEqual(160)
  })

  it('sizes a stacked axis from the stack TOTAL, not the plotted values', () => {
    // A stacked bar's axis tops out at the row sum. Three series of 900,000
    // are each 7 digits, but they stack to 2,700,000 -- and the gutter has to
    // fit the tick that is actually drawn. BarChartRenderer passes the summed
    // values for this reason; this pins the width difference that makes it
    // worth doing.
    const money = { type: 'currency', symbol: '$', decimals: 0 } as never
    const plotted = yAxisWidth({}, [900_000, 900_000, 900_000], money)
    const stacked = yAxisWidth({}, [2_700_000], money)
    expect(stacked).toBeGreaterThan(plotted)
  })

  it('honours an explicit author width over the estimate', () => {
    expect(yAxisProps({ y_axis_width: 140 } as never, false,
                      { type: 'currency' } as never, [2_000_000]).width).toBe(140)
  })

  it('gives the category axis room for its rotated labels', () => {
    // Every renderer draws these at -30 degrees; a rotated label is taller
    // than the ~14px Recharts reserves, so without this the names overprinted
    // the axis and ran off the bottom of the card.
    expect(xAxisProps({}, false).height).toBeGreaterThanOrEqual(40)
  })
})

describe('the legend keeps swatch-then-label in an RTL page', () => {
  it('pins the legend wrapper to ltr only when the page is rtl', () => {
    expect(legendProps({}, false)).not.toHaveProperty('wrapperStyle')
    expect(legendProps({}, true)).toMatchObject({ wrapperStyle: { direction: 'ltr' } })
  })

  it('still returns null when the legend is switched off', () => {
    expect(legendProps({ legend: false }, true)).toBeNull()
  })
})

describe('axis titles, when the author has not written one', () => {
  /**
   * Reported as a question nobody should have to ask about their own
   * dashboard: "i didnot know what are you drawn what is this data no axis
   * lable how user understand". The field names were always in the config;
   * they were only ever drawn if someone typed them a second time by hand.
   */
  const bars = { dimension: 'region', measure: 'total', aggregation: 'sum' }

  it('names the axes after the fields the chart draws', () => {
    expect(axisTitles(bars)).toEqual({
      category: 'region', measure: 'sum(total)', measure2: undefined })
  })

  it('carries the aggregation, because that is what the bars measure', () => {
    expect(axisTitles({ measure: 'total', aggregation: 'avg' }).measure).toBe('avg(total)')
    expect(axisTitles({ measure: 'total' }).measure).toBe('total')
    expect(axisTitles({ measure: 'total', aggregation: 'none' }).measure).toBe('total')
  })

  it('says "count" for the aggregation that names no column', () => {
    expect(axisTitles({ aggregation: 'count' }).measure).toBe('count')
  })

  it('invents nothing: an unset field gets no title', () => {
    expect(axisTitles({})).toEqual({
      category: undefined, measure: undefined, measure2: undefined })
    expect(axisTitles({ dimension: '   ' }).category).toBeUndefined()
  })

  it('falls back to the date column when a time series has no dimension', () => {
    expect(axisTitles({ start: 'created_at' }).category).toBe('created_at')
  })

  it('titles the second measure from its own aggregation', () => {
    expect(axisTitles({ measure2: 'orders', aggregation: 'sum', aggregation2: 'avg' })
      .measure2).toBe('avg(orders)')
    // ...and from the first when it has none of its own.
    expect(axisTitles({ measure2: 'orders', aggregation: 'sum' }).measure2).toBe('sum(orders)')
  })

  it('reaches the axes themselves', () => {
    expect(xAxisProps(bars, false).label).toMatchObject({ value: 'region' })
    expect(yAxisProps(bars, false).label).toMatchObject({ value: 'sum(total)' })
  })

  it("gives way to the author's own words", () => {
    const p = xAxisProps({ ...bars, x_axis_label: 'Governorate' }, false)
    expect(p.label).toMatchObject({ value: 'Governorate' })
  })

  it('stays off when the author cleared it', () => {
    // An empty string is a decision, not an absence: it stops the fallback.
    expect(xAxisProps({ ...bars, x_axis_label: '' }, false).label).toBeUndefined()
    expect(yAxisProps({ ...bars, y_axis_label: '' }, false).label).toBeUndefined()
  })

  it('reserves the title its lane, as it always did for a typed one', () => {
    // The title sits inside the tick band; without the extra height the
    // tilted labels end on its baseline.
    const titled = xAxisProps(bars, false, ['a', 'b'], 600)
    const bare = xAxisProps({}, false, ['a', 'b'], 600)
    expect(titled.height).toBeGreaterThan(bare.height)
  })

  it('lets a renderer name an axis that is not the usual one', () => {
    // A dot plot puts the measure along the bottom; without this the x axis
    // would be titled after the category it does not draw.
    expect(xAxisProps(bars, false, undefined, undefined, { title: 'sum(total)' }).label)
      .toMatchObject({ value: 'sum(total)' })
    expect(xAxisProps(bars, false, undefined, undefined, { title: '' }).label)
      .toBeUndefined()
  })
})

describe('seriesName -- tooltips and legends use the axis words, never the data key', () => {
  it('a row count is called "count", not "value"', () => {
    expect(seriesName({ aggregation: 'sum' } as never)).toBe('count')
    expect(seriesName({} as never)).toBe('count')
  })
  it('a measure carries its aggregation, as the axis title does', () => {
    expect(seriesName({ measure: 'revenue', aggregation: 'sum' } as never)).toBe('sum(revenue)')
  })
  it('an explicit y-axis column wins, as it does on the axis', () => {
    expect(seriesName({ y_axis: 'margin', measure: 'revenue' } as never)).toBe('margin')
  })
})
