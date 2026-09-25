import { describe, it, expect, beforeAll } from 'vitest'
import { render } from '@testing-library/react'
import BarChartRenderer from './BarChartRenderer'
import { xAxisPlan, yAxisProps, yCategoryPlan, textWidth, chartMargin } from './axisOptions'

const W = 600, H = 400
beforeAll(() => {
  Element.prototype.getBoundingClientRect = () => ({
    width: W, height: H, top: 0, left: 0, right: W, bottom: H, x: 0, y: 0, toJSON() {},
  }) as DOMRect
})

const AR = ['القاهرة', 'الإسكندرية', 'الجيزة', 'أسوان', 'بورسعيد', 'المنصورة',
            'شرم الشيخ', 'الأقصر', 'أسيوط', 'طنطا', 'دمياط', 'الفيوم']

describe('a tilted category label mirrors in a right-to-left page', () => {
  it('flips the rotation sign, not just the anchor', () => {
    // THE Arabic bug. SVG rotate(-30) is counter-clockwise, so the rotated
    // baseline runs up-and-right. Anchoring at `start` while keeping the
    // negative angle therefore sent the label UP INTO THE PLOT; only the pair
    // (+30, start) is the true mirror of (-30, end).
    const ltr = xAxisPlan(AR, { fontSize: 10, width: 560 })
    const rtl = xAxisPlan(AR, { fontSize: 10, width: 560, rtl: true })
    expect(ltr.angle).toBeLessThan(0)
    expect(ltr.textAnchor).toBe('end')
    expect(rtl.angle).toBeGreaterThan(0)
    expect(rtl.textAnchor).toBe('start')
    expect(rtl.angle).toBe(-ltr.angle)
  })

  it('keeps an upright axis at positive zero, never negative zero', () => {
    // `0 * -1` is -0, which is not Object.is-equal to 0. A mirrored upright
    // axis must still compare equal to an unmirrored one.
    const p = xAxisPlan(['أ', 'ب', 'ج'], { fontSize: 10, width: 560, rtl: true })
    expect(p.angle).toBe(0)
    expect(Object.is(p.angle, -0)).toBe(false)
    expect(p.textAnchor).toBe('middle')
  })

  it('mirrors an explicit author angle too', () => {
    const p = xAxisPlan(AR, { fontSize: 10, width: 560, rtl: true, angle: -45 })
    expect(p.angle).toBe(45)
  })

  it('renders the mirrored rotation on a real chart', () => {
    const rows = AR.map((name, i) => ({ name, value: 100 + i }))
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const mk = (rtl: boolean): any => ({ rows, data: { rows }, cfg: {}, rtl,
      broadcasts: false, localSelected: null, onClickPoint: () => {} })
    const tick = (rtl: boolean) => {
      const { container } = render(
        <div style={{ width: W, height: H }} dir={rtl ? 'rtl' : 'ltr'}>
          <BarChartRenderer {...mk(rtl)} /></div>)
      return container.querySelector('.recharts-xAxis .recharts-cartesian-axis-tick-value')!
    }
    expect(tick(false).getAttribute('transform')).toMatch(/rotate\(-30/)
    expect(tick(true).getAttribute('transform')).toMatch(/rotate\(30/)
  })
})

describe('the value-axis title follows its axis when the page mirrors', () => {
  it('sits on the outer edge of the gutter on whichever side the axis is', () => {
    // The axis moves to the right in RTL (orientation), and 'insideLeft' then
    // means the edge against the PLOT: measured at x=521 with the plot ending
    // at ~524, so the title was drawn on the data.
    const ltr = yAxisProps({ y_axis_label: 'القيمة' }, false, undefined, [10]).label
    const rtl = yAxisProps({ y_axis_label: 'القيمة' }, true, undefined, [10]).label
    expect(ltr).toMatchObject({ position: 'insideLeft', angle: -90 })
    expect(rtl).toMatchObject({ position: 'insideRight', angle: 90 })
  })

  it('draws the title out in the gutter, not over the plot', () => {
    const rows = AR.map((name, i) => ({ name, value: 100 + i }))
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const props: any = { rows, data: { rows }, cfg: { y_axis_label: 'القيمة' }, rtl: true,
      broadcasts: false, localSelected: null, onClickPoint: () => {} }
    const { container } = render(
      <div style={{ width: W, height: H }} dir="rtl"><BarChartRenderer {...props} /></div>)
    const title = Array.from(container.querySelectorAll('text'))
      .find(t => t.textContent === 'القيمة')!
    const plotRight = Math.max(...Array.from(
      container.querySelectorAll('.recharts-cartesian-grid-vertical line'))
      .map(l => Number(l.getAttribute('x1'))))
    expect(Number(title.getAttribute('x'))).toBeGreaterThan(plotRight)
  })
})

describe('label width is measured per script, not with a Latin constant', () => {
  it('charges Arabic more per character than Latin', () => {
    // Cursive Arabic is materially wider at the same px size; the Latin factor
    // under-read it by about a third, so an Arabic axis came back with a
    // gutter too small and the labels collided anyway.
    expect(textWidth('ابجدهو', 10)).toBeGreaterThan(textWidth('abcdef', 10))
  })

  it('charges Arabic-Indic digits the same as Latin digits', () => {
    // They live in the Arabic block but are tabular figures; charging them the
    // cursive rate would inflate every numeric gutter on an Arabic locale.
    expect(textWidth('١٢٣٤٥', 10)).toBeCloseTo(textWidth('12345', 10), 5)
  })

  it('charges nothing for combining marks and bidi isolates', () => {
    const bare = textWidth('كتب', 10)
    expect(textWidth('كَتَبَ', 10)).toBeCloseTo(bare, 5)          // harakat
    expect(textWidth('⁦abc⁩', 10)).toBeCloseTo(textWidth('abc', 10), 5)
  })

  it('measures a mixed label by its parts', () => {
    const mixed = textWidth('Q1 القاهرة', 10)
    expect(mixed).toBeGreaterThan(textWidth('Q1 ', 10))
    expect(mixed).toBeLessThan(textWidth('القاهرة القاهرة', 10))
  })

  it('gives an Arabic category axis a wider gutter than a Latin one', () => {
    const latin = yCategoryPlan(['Engineering', 'Sales', 'Support'], { fontSize: 10 })
    const arabic = yCategoryPlan(['الهندسة والتطوير', 'المبيعات', 'الدعم'], { fontSize: 10 })
    expect(arabic.width).toBeGreaterThan(latin.width)
  })
})

describe('the value-axis title is centred on its axis and kept inside the card', () => {
  // Measured in Chrome before the fix: 'insideLeft' anchors the title at the
  // axis MIDPOINT with text-anchor 'start', and the -90 rotation then runs the
  // whole title upward from there. On a 220px tile that put its top at y=-17
  // and on a 200px tile at y=-34 -- "Total revenue" printed as "Total rever".
  // RTL mirrors the same failure with 'insideRight' + 'end'. Centring the text
  // on its anchor is what Recharts' own docs do for a rotated axis title, and
  // it has to be a STYLE: Label overrides the textAnchor prop with the one its
  // position implies, so a plain prop would be silently discarded.
  it('anchors the rotated title at its middle in both directions', () => {
    const ltr = yAxisProps({ y_axis_label: 'Total revenue' }, false, undefined, [10]).label
    const rtl = yAxisProps({ y_axis_label: 'القيمة' }, true, undefined, [10]).label
    expect(ltr).toMatchObject({ style: { textAnchor: 'middle' } })
    expect(rtl).toMatchObject({ style: { textAnchor: 'middle' } })
  })

  it('offsets the title so its glyph box sits inside the reserved lane', () => {
    // Recharts' default offset of 5 centred the rotated 15px line box at
    // x=5, so its outer 2.5px -- the tops of the letters -- fell off the SVG
    // edge. Half the lane width puts the box at 0.5..15.5 inside the 16px
    // lane the gutter reserves for it (Y_TITLE_W).
    const ltr = yAxisProps({ y_axis_label: 'Total revenue' }, false, undefined, [10]).label
    const rtl = yAxisProps({ y_axis_label: 'Total revenue' }, true, undefined, [10]).label
    expect(ltr?.offset).toBe(8)
    expect(rtl?.offset).toBe(8)
  })

  it('renders the centred anchor onto the SVG text', () => {
    const rows = AR.map((name, i) => ({ name, value: 100 + i }))
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const props: any = { rows, data: { rows }, cfg: { y_axis_label: 'القيمة' }, rtl: true,
      broadcasts: false, localSelected: null, onClickPoint: () => {} }
    const { container } = render(
      <div style={{ width: W, height: H }} dir="rtl"><BarChartRenderer {...props} /></div>)
    const title = Array.from(container.querySelectorAll('text'))
      .find(t => t.textContent === 'القيمة') as SVGTextElement
    expect(title.style.textAnchor).toBe('middle')
  })
})

describe('the category-axis title sits inside its reserved lane', () => {
  it('ends at the bottom of the tick band instead of hanging below it', () => {
    // xAxisProps adds X_TITLE_H to the band for the title, but 'bottom'
    // positioned the label BELOW the band with a 'start' vertical anchor, so
    // the lane stayed empty and the title hung into whatever came next -- the
    // legend, on any multi-series chart. Inside the band the label's vertical
    // anchor is 'end': the text stands ON its baseline (dy <= 0) rather than
    // hanging from it (dy = cap height, positive).
    const rows = AR.slice(0, 4).map((name, i) => ({ name, value: 100 + i }))
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const props: any = { rows, data: { rows }, cfg: { x_axis_label: 'المدينة' }, rtl: false,
      broadcasts: false, localSelected: null, onClickPoint: () => {} }
    const { container } = render(
      <div style={{ width: W, height: H }}><BarChartRenderer {...props} /></div>)
    const title = Array.from(container.querySelectorAll('text'))
      .find(t => t.textContent === 'المدينة') as SVGTextElement
    // The band ends where the chart's bottom margin begins (BarChartRenderer
    // draws with margin.bottom = 20 and no legend on a single series).
    const svg = container.querySelector('svg.recharts-surface')!
    const bandBottom = Number(svg.getAttribute('height')) - 20
    expect(Number(title.getAttribute('y'))).toBeLessThanOrEqual(bandBottom)
    const dy = parseFloat(title.querySelector('tspan')!.getAttribute('dy') ?? '0')
    expect(dy).toBeLessThanOrEqual(0)
  })
})

describe('the plot keeps the same edge clearance when the page mirrors', () => {
  // Renderers leave the LEFT margin at 0 because the value-axis gutter is
  // there, and keep 8px on the right for the last category's label. In RTL
  // the gutter moves to the right and the plot starts at x=0, so that label
  // is drawn against the card edge: measured in Chrome, the last label of an
  // RTL line chart lost up to 10px of its glyphs off the left of the SVG.
  it('swaps the horizontal margins for a mirrored chart and leaves LTR alone', () => {
    const m = { top: 4, right: 8, bottom: 20, left: 0 }
    expect(chartMargin(false, m)).toEqual(m)
    expect(chartMargin(true, m)).toEqual({ top: 4, right: 0, bottom: 20, left: 8 })
  })

  it('renders the RTL plot as the mirror image of the LTR plot', () => {
    const rows = AR.slice(0, 6).map((name, i) => ({ name, value: 100 + i }))
    const plotOf = (rtl: boolean) => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const props: any = { rows, data: { rows }, cfg: {}, rtl,
        broadcasts: false, localSelected: null, onClickPoint: () => {} }
      const { container } = render(
        <div style={{ width: W, height: H }} dir={rtl ? 'rtl' : 'ltr'}><BarChartRenderer {...props} /></div>)
      const xs = Array.from(container.querySelectorAll('.recharts-cartesian-grid-vertical line'))
        .map(l => Number(l.getAttribute('x1')))
      return { left: Math.min(...xs), right: Math.max(...xs) }
    }
    const ltr = plotOf(false), rtl = plotOf(true)
    expect(rtl.left).toBeCloseTo(W - ltr.right, 5)
    expect(W - rtl.right).toBeCloseTo(ltr.left, 5)
  })
})
