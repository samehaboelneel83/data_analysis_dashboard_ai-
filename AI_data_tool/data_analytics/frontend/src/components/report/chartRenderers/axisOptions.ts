/**
 * Pure prop-builders for the Recharts Cartesian primitives.
 *
 * Every builder's no-config path returns the values that were hard-coded in the
 * renderers before this module existed, so a widget saved earlier renders
 * identically. That is load-bearing: this module is consumed by 20 renderers, and
 * a drifted default would be a silent visual regression across the whole app.
 *
 * These return props rather than components on purpose — each renderer keeps its
 * own JSX and its own layout quirks, and only the option plumbing is shared.
 */
import type { CalcColumnFormat } from '../../../services/api'
import { createElement, type ComponentType } from 'react'
import { LineChart, Line } from 'recharts'
import { fmtStr, LegendWithTitle } from '../chartUtils'
import { hijriLabel } from '../../../lib/arabicFormats'

export interface FormatConfig {
  overview_axis?: boolean
  axis_tick_size?: number
  axis_tick_color?: string
  axis_line?: boolean
  tick_line?: boolean
  x_axis_label?: string
  y_axis_label?: string
  /** The RIGHT axis's title on a dual-axis chart. Two measures on two scales
   *  are two different things, and titling both from `y_axis_label` states
   *  something false about one of them. */
  y2_axis_label?: string
  /** A heading for the legend, naming the FIELD its entries are values of. */
  legend_title?: string
  y_min?: number
  y_max?: number
  y_scale?: 'linear' | 'log'
  grid?: boolean
  grid_style?: 'dashed' | 'solid'
  grid_color?: string
  legend?: boolean
  legend_position?: 'top' | 'bottom' | 'left' | 'right'
  data_labels?: boolean
  // -- The widget's own fields -------------------------------------------
  // Read here for ONE purpose: titling the axes when the author has not (see
  // axisTitles). They are part of every widget config already; this declares
  // the handful this module looks at, so the titles are typed rather than
  // reached through a cast.
  dimension?: string
  dimension2?: string
  measure?: string
  measure2?: string
  aggregation?: string
  aggregation2?: string
  /** The scatter family's own column keys. */
  x_axis?: string
  y_axis?: string
  /** The date column of a time series, which has no `dimension` of its own. */
  start?: string
  /** Older single-column widgets (WidgetRenderer reads `cfg.dimension ??
   *  cfg.column`). */
  column?: string
}

const DEFAULT_TICK_COLOR = 'var(--muted)'
const DEFAULT_TICK_SIZE = 10

function tick(cfg: FormatConfig) {
  return { fill: cfg.axis_tick_color ?? DEFAULT_TICK_COLOR, fontSize: cfg.axis_tick_size ?? DEFAULT_TICK_SIZE }
}

/** Width of one Latin character at a given font size, for the default UI face.
 *  Validated against real rendered currency labels. A second, differently
 *  guessed constant for the same font would be a bug waiting to disagree with
 *  the first, so everything here goes through `textWidth`. */
const CHAR_W = 0.62

/** Arabic is materially wider per character than Latin at the same px size --
 *  the glyphs are cursive and carry their own joining forms -- so measuring an
 *  Arabic axis with the Latin factor under-reads it by roughly a third and the
 *  gutter comes back too small. That is why the labels still collided in
 *  Arabic after the Latin case was fixed. */
const CHAR_W_ARABIC = 0.85

/** Han/Kana are full-width by design. */
const CHAR_W_WIDE = 1.0

/** Arabic harakat and other combining marks stack ON the previous glyph and
 *  add no advance width, but `String.length` counts them, so they would
 *  inflate every estimate on vocalised text. */
function isZeroWidth(cp: number): boolean {
  return (cp >= 0x0610 && cp <= 0x061a) || (cp >= 0x064b && cp <= 0x065f)
    || cp === 0x0670 || (cp >= 0x06d6 && cp <= 0x06ed)
    || (cp >= 0x0300 && cp <= 0x036f)
    // The bidi isolates fmtStr wraps number runs in are formatting characters
    // that render nothing (see chartUtils.isolateLtr).
    || cp === 0x2066 || cp === 0x2069 || (cp >= 0x200b && cp <= 0x200f)
}

function charFactor(cp: number): number {
  if (isZeroWidth(cp)) return 0
  // Arabic-Indic digits sit inside the Arabic block but are tabular figures,
  // as narrow as their Latin counterparts. They matter: on an Arabic locale
  // every numeric tick is drawn in them, and charging them the cursive factor
  // would inflate the value-axis gutter by a third for no reason.
  if ((cp >= 0x0660 && cp <= 0x0669) || (cp >= 0x06f0 && cp <= 0x06f9)) return CHAR_W
  // Arabic, Arabic Supplement, and the presentation-form blocks.
  if ((cp >= 0x0600 && cp <= 0x06ff) || (cp >= 0x0750 && cp <= 0x077f)
    || (cp >= 0xfb50 && cp <= 0xfdff) || (cp >= 0xfe70 && cp <= 0xfeff)) return CHAR_W_ARABIC
  if ((cp >= 0x4e00 && cp <= 0x9fff) || (cp >= 0x3040 && cp <= 0x30ff)
    || (cp >= 0xac00 && cp <= 0xd7af)) return CHAR_W_WIDE
  return CHAR_W
}

/** Estimated rendered width of one label, script by script.
 *
 *  Deliberately per-character rather than one global factor: a mixed label
 *  like "Q1 القاهرة" is neither wholly Latin nor wholly Arabic, and a single
 *  factor is wrong for both halves. */
export function textWidth(s: string, fontSize: number): number {
  let w = 0
  for (const ch of String(s ?? '')) w += charFactor(ch.codePointAt(0) ?? 0)
  return w * fontSize
}

/** Widest of a set of labels, in px. */
function widestLabel(labels: readonly unknown[], fontSize: number): number {
  let w = 0
  for (const l of labels) w = Math.max(w, textWidth(String(l ?? ''), fontSize))
  return w
}

/** How many characters of `s` fit in `px`, measured the same way. */
function charsThatFit(s: string, fontSize: number, px: number): number {
  let w = 0, n = 0
  for (const ch of String(s ?? '')) {
    w += charFactor(ch.codePointAt(0) ?? 0) * fontSize
    if (w > px) break
    n++
  }
  return n
}

/** Angles the planner tries, in order. Each step buys horizontal room and
 *  costs legibility, so the first one that fits wins. -90 is last because
 *  vertical text is genuinely hard to read -- but it still beats two labels
 *  printed on top of each other. */
const ANGLE_LADDER = [0, -30, -45, -90]

/** How much of the chart the category labels may eat before the band stops
 *  growing and the labels start being ellipsised instead. A chart that is
 *  four-fifths axis is not a chart. */
const MAX_X_BAND = 96

/** Nominal plot width when the caller cannot measure one. ResponsiveContainer
 *  knows the real width but does not hand it to prop builders, so a caller
 *  that has not measured gets a plan computed for a typical widget. The plan
 *  still adapts to label LENGTH and COUNT, which are what actually drive
 *  collisions; width only shifts where the thresholds land. */
const NOMINAL_PLOT_W = 560

/** Vertical lane reserved for the x-axis TITLE when the author sets one, at
 *  its 11px font plus breathing room. */
export const X_TITLE_H = 16

export interface XAxisPlan {
  angle: number
  textAnchor: 'middle' | 'end' | 'start'
  height: number
  /** Recharts' numeric interval: draw every (interval + 1)th tick. 0 = all. */
  interval: number
  /** Longest label this plan can show intact; longer ones are ellipsised. */
  maxChars: number
  /** The exact labels to draw, when thinning is needed.
   *
   *  Recharts' own `interval` counts forward from index 0 and simply stops,
   *  so it DROPS THE LAST CATEGORY: measured on 12 categories, interval 1
   *  ends at Cat11, interval 2 at Cat10, interval 3 at Cat9. The final value
   *  is the one a reader most often came for -- it is the newest point on any
   *  time series -- and this module already refuses to lose it elsewhere, in
   *  `keepsLabel`. So when the axis has to be thinned, the surviving labels
   *  are chosen here and passed explicitly instead. */
  ticks?: readonly string[]
}

/**
 * Choose which labels survive thinning, keeping BOTH ends.
 *
 * Anchored on the last index and walked backwards, for the same reason
 * `keepsLabel` is: a naive forward walk drops the final category whenever
 * `n - 1` is not a multiple of the stride. Index 0 is then added back unless
 * doing so would crowd it against its neighbour.
 */
function endpointTicks(labels: readonly string[], stride: number): string[] {
  const n = labels.length
  const keep: number[] = []
  for (let i = n - 1; i >= 0; i -= stride) keep.push(i)
  keep.reverse()
  if (keep[0] !== 0 && keep[0] >= stride / 2) keep.unshift(0)
  return keep.map(i => labels[i])
}

/**
 * Decide how the category axis draws its labels.
 *
 * WHY THIS IS A PURE FUNCTION rather than left to Recharts: the previous code
 * passed `interval: 'preserveStartEnd'` plus `minTickGap`, which makes Recharts
 * choose from MEASURED text width. That is invisible to the test suite --
 * jsdom reports zero for every text metric, so `preserveStartEnd` collapses to
 * a single tick under test while a browser draws many. Behaviour that differs
 * between test and production is behaviour no test can defend, which is
 * exactly how the crowding shipped. A numeric `interval` is deterministic in
 * both, so the decision is made here, where it can be asserted.
 *
 * The ladder: draw upright if the labels fit; else rotate as little as
 * possible; and only when even vertical text collides, start skipping ticks.
 * Skipping is last because a dropped label is information the reader cannot
 * recover, whereas a tilted one is merely harder to read.
 */
export function xAxisPlan(
  labels: readonly string[],
  opts: {
    fontSize?: number
    /** Measured plot width, when the caller has one. */
    width?: number
    rtl?: boolean
    /** Author override from the Formatting panel. An explicit angle wins over
     *  the ladder, but never over the collision maths that picks `interval` --
     *  an author who asks for upright labels still gets readable ticks. */
    angle?: number
    maxHeight?: number
  } = {},
): XAxisPlan {
  const fontSize = opts.fontSize ?? DEFAULT_TICK_SIZE
  const width = opts.width && opts.width > 0 ? opts.width : NOMINAL_PLOT_W
  const maxBand = opts.maxHeight ?? MAX_X_BAND
  const lineH = fontSize + 2
  const n = labels.length

  if (n === 0) {
    return { angle: 0, textAnchor: 'middle', height: lineH + 8, interval: 0, maxChars: Infinity }
  }

  const labelW = widestLabel(labels, fontSize)
  const slot = width / n

  // Horizontal room one label needs at a given angle. Upright text needs its
  // whole width; tilted text needs only its stacking pitch, because the labels
  // run parallel -- which is the entire reason rotating buys room.
  const needed = (deg: number) =>
    deg === 0 ? labelW + 6 : lineH / Math.sin(Math.abs(deg) * Math.PI / 180) + 2

  // Vertical room the same label eats: the bounding box of the rotated text.
  const band = (deg: number) => {
    const r = Math.abs(deg) * Math.PI / 180
    return Math.ceil(labelW * Math.sin(r) + lineH * Math.cos(r)) + 8
  }

  const ladder = opts.angle === undefined || opts.angle === null ? ANGLE_LADDER : [opts.angle]
  let angle = ladder[ladder.length - 1]
  for (const a of ladder) {
    if (needed(a) <= slot) { angle = a; break }
  }

  // Even at the last angle the labels may still collide; thin them out.
  // `interval` counts ticks SKIPPED between drawn ones, so every k-th is k - 1.
  const stride = Math.max(1, Math.ceil(needed(angle) / Math.max(slot, 1)))
  const interval = stride - 1

  // Growing the band beats truncating, up to the cap; past it the labels are
  // ellipsised so the plot keeps most of the card.
  let height = Math.min(band(angle), maxBand)
  let maxChars = Infinity
  if (band(angle) > maxBand) {
    const r = Math.abs(angle) * Math.PI / 180
    const usableW = angle === 0
      ? width / Math.max(n / stride, 1)
      : (maxBand - 8 - lineH * Math.cos(r)) / Math.max(Math.sin(r), 0.001)
    // Measured on the widest label itself, so a clip on Arabic text keeps the
    // characters that actually fit rather than a Latin-calibrated guess.
    const widest = labels.reduce((a, b) =>
      textWidth(String(b ?? ''), fontSize) > textWidth(String(a ?? ''), fontSize) ? b : a, labels[0])
    maxChars = Math.max(3, charsThatFit(String(widest ?? ''), fontSize, usableW))
    height = maxBand
  }
  if (angle === 0) height = Math.min(Math.max(lineH + 8, height), maxBand)

  return {
    // In a mirrored page the tilt mirrors too. Anchoring at `start` while
    // KEEPING the negative angle was the Arabic bug: SVG rotates -30 counter-
    // clockwise, so the baseline runs up-and-right, and a `start` anchor sent
    // the label up into the plot instead of down under its tick. Flipping the
    // sign restores the mirror -- +30 with `start` trails down-and-right,
    // exactly as -30 with `end` trails down-and-left.
    //
    // `angle === 0` is special-cased so an upright axis stays +0: `0 * -1` is
    // -0, which is not `Object.is`-equal to 0 and would fail an honest test.
    angle: angle === 0 ? 0 : opts.rtl ? -angle : angle,
    // Upright labels centre under their tick. A tilted label hangs from the
    // tick and trails away from it, so the END of the text is the anchor --
    // and in a mirrored page it trails the other way, hence `start`.
    textAnchor: angle === 0 ? 'middle' : opts.rtl ? 'start' : 'end',
    height,
    interval,
    maxChars,
    // Only when something actually has to go. At stride 1 every label is
    // drawn and an explicit list would just be the input back again.
    ...(stride > 1
      ? { ticks: endpointTicks(labels.map(l => String(l ?? '')), stride) }
      : {}),
  }
}

/** Ellipsise to `max` characters, or return the string unchanged. */
export function clipLabel(s: string, max: number): string {
  if (!Number.isFinite(max) || s.length <= max) return s
  return s.slice(0, Math.max(1, max - 1)) + '…'
}

/**
 * @param labels the category labels this axis will draw. Supply them for a
 *   CATEGORY axis and the planner adapts angle, band height and tick density
 *   to them. Omit for a NUMERIC x axis (scatter, bubble), which keeps the
 *   upright defaults -- rotating a number line helps nobody.
 */
/** What the value-axis gutter and the right margin take out of a tile before
 *  the category axis sees any of it. Deliberately generous: under-stating the
 *  room makes the planner rotate or thin one step sooner, which is invisible,
 *  while over-stating it puts labels back on top of each other. */
const X_GUTTER_ALLOWANCE = 84

/**
 * Chart margins for the reading direction.
 *
 * Renderers leave the LEFT margin at 0 because the value-axis gutter sits
 * there, and keep a few pixels on the right so the last category's label has
 * room past the plot. In a mirrored page the gutter moves to the right and the
 * plot then starts at x=0, so that last label is drawn against the card edge:
 * measured in Chrome, an RTL line chart lost up to 10px of its leftmost label
 * off the SVG. Swapping the horizontal margins restores the LTR geometry as a
 * mirror image; top and bottom are direction-free and untouched.
 */
export function chartMargin(
  rtl: boolean,
  m: { top: number; right: number; bottom: number; left: number },
) {
  return rtl ? { ...m, left: m.right, right: m.left } : m
}

/**
 * @param labels the category labels this axis will draw. Supply them for a
 *   CATEGORY axis and the planner adapts angle, band height and tick density
 *   to them. Omit for a NUMERIC x axis (scatter, bubble), which keeps the
 *   upright defaults -- rotating a number line helps nobody.
 * @param containerW the tile's measured width, from WidgetRenderer. The plot
 *   is narrower than the tile by the value-axis gutter, so it is netted off
 *   here rather than by each caller.
 */
/**
 * What the two axes are, when the author has not said.
 *
 * A chart with no axis titles asks the reader to guess what they are looking
 * at -- and on a dashboard, where the tile's heading is usually a phrase
 * rather than a column name, there is nothing to guess FROM. Reported
 * outright: "i didnot know what are you drawn what is this data no axis
 * lable how user understand". The names were already in the config; they were
 * simply never drawn unless someone typed them a second time by hand.
 *
 * Three states per title, and the middle one is the point:
 *   `undefined` -> derive it from the fields this chart draws (here)
 *   `''`        -> the author cleared it; draw no title
 *   any text    -> the author's own words, which always win
 *
 * The derivation is the field NAME, with its aggregation when it has one --
 * `sum(total)` rather than `total`, because that is what the bars measure.
 * Nothing is invented: every string returned came out of the config, so a
 * chart whose measure is unset gets no measure title rather than a guess.
 */
export function axisTitles(cfg: FormatConfig): {
  category?: string
  measure?: string
  measure2?: string
} {
  const text = (v: unknown) =>
    typeof v === 'string' && v.trim() ? v.trim() : undefined
  const applied = (column?: string, agg?: string) =>
    column ? (agg && agg !== 'none' ? `${agg}(${column})` : column) : undefined

  const agg = text(cfg.aggregation)
  // `x_axis`/`y_axis` are the scatter family's own column keys; `start` names
  // the date axis of a time series, which has no `dimension` of its own.
  const category = text(cfg.x_axis) ?? text(cfg.dimension) ?? text(cfg.start)
    ?? text(cfg.column)
  const measure = text(cfg.y_axis)
    ?? applied(text(cfg.measure), agg)
    // COUNT names no column -- "how many rows" -- and the axis should say so
    // rather than stay blank on the one aggregation that has nothing to name.
    ?? (agg === 'count' ? 'count' : undefined)
  const measure2 = applied(text(cfg.measure2), text(cfg.aggregation2) ?? agg)
  return { category, measure, measure2 }
}

/**
 * The name of the primary series, for tooltips, legends and table headers --
 * the SAME words the measure axis uses, so the tooltip never disagrees with the
 * axis beside it. Before this, fourteen renderers fell back to the internal data
 * key and a reader hovering a bar saw "value : 514" under an axis titled
 * "count". With no measure the shaper counts rows, so that is what it is called.
 */
export function seriesName(cfg: FormatConfig): string {
  const m = typeof cfg.measure === 'string' && cfg.measure.trim() ? cfg.measure.trim() : undefined
  return axisTitles(cfg).measure ?? m ?? 'count'
}

/** A y-axis title's Label props, mirrored for RTL.
 *
 * Exported because CustomGraphRenderer draws its own axes rather than going
 * through the builders below, and every number here was MEASURED (see the
 * comments inside). A second, eyeballed copy of them is exactly the "drifted
 * default" this module's header warns about.
 */
export function yTitleLabel(value: string, rtl: boolean, right = false) {
  // `right` is the second axis of a dual-scale chart: it sits on the opposite
  // side, so both its side and its rotation are the other way round.
  const onRight = rtl ? !right : right
  return {
    value,
    // The value axis moves to the RIGHT in a mirrored page and the title has
    // to move with it; pinned 'insideLeft' it sat on the data instead of in
    // the gutter. The rotation mirrors too, so the text still reads upward on
    // the side it is on.
    angle: onRight ? 90 : -90,
    position: (onRight ? 'insideRight' : 'insideLeft') as 'insideLeft' | 'insideRight',
    // Half the title lane, so the rotated line box sits inside it. Recharts'
    // default 5 cut the tops of the letters off at the SVG edge.
    offset: Y_TITLE_W / 2,
    // CENTRED on the axis midpoint: both inside positions anchor at the
    // middle and then rotate, so the anchor the position implies ran the
    // whole title one way and clipped it. A style, because Label overrides
    // the textAnchor prop with its positional one.
    style: { textAnchor: 'middle' as const },
    fill: DEFAULT_TICK_COLOR,
    fontSize: 11,
  }
}

/** An x-axis title's Label props: inside the lane `X_TITLE_H` reserves for it
 *  at the bottom of the tick band, never below it where the legend lives. */
export function xTitleLabel(value: string) {
  return {
    value,
    position: 'insideBottom' as const,
    offset: 4,
    fill: DEFAULT_TICK_COLOR,
    fontSize: 11,
  }
}

/** The title an axis should carry: the caller's override, else the author's
 *  own label, else the derived name. An empty string at either of the first
 *  two means "no title" and stops the fallback -- that is how a title is
 *  turned OFF, and why `??` would be wrong here. */
function resolveTitle(explicit: string | undefined,
                      authored: string | undefined,
                      derived: string | undefined): string | undefined {
  if (explicit !== undefined) return explicit || undefined
  if (authored !== undefined) return authored || undefined
  return derived
}

export function xAxisProps(
  cfg: FormatConfig,
  rtl: boolean,
  labels?: readonly string[],
  containerW?: number,
  /** `title` overrides the axis title for THIS axis. The charts whose x axis
   *  is NOT the category -- a dot plot, a bubble chart, a histogram -- pass
   *  what their x really is, because only the renderer knows that. */
  opts?: { title?: string },
) {
  const fontSize = cfg.axis_tick_size ?? DEFAULT_TICK_SIZE
  const title = resolveTitle(opts?.title, cfg.x_axis_label,
                             axisTitles(cfg).category)
  const explicitAngle = (cfg as { x_axis_angle?: number }).x_axis_angle
  const width = containerW && containerW > 0
    ? Math.max(120, containerW - X_GUTTER_ALLOWANCE)
    : undefined
  const plan = labels && labels.length
    ? xAxisPlan(labels, { fontSize, width, rtl, angle: explicitAngle })
    : null

  return {
    tick: tick(cfg),
    axisLine: cfg.axis_line ?? false,
    tickLine: cfg.tick_line ?? false,
    reversed: rtl,

    // Sized from the labels rather than pinned at the old fixed 52px, which
    // fitted a 30-degree label of AVERAGE length and let anything longer run
    // out of its band, over the axis line and off the bottom of the card.
    //
    // The axis TITLE is pinned to the bottom of the chart area, while the tick
    // band grows upward from that same edge -- so without this the tilted
    // labels ended exactly on the title's baseline (measured: a 12-category
    // -30 axis put its lowest label at y=380 and the title at y=380). Adding
    // the title's own line height reserves it a lane of its own.
    height: (plan ? plan.height : 52) + (title ? X_TITLE_H : 0),
    ...(plan ? { angle: plan.angle, textAnchor: plan.textAnchor } : {}),

    // A NUMBER, not 'preserveStartEnd' -- see xAxisPlan for why measured
    // decluttering was untestable and therefore undefended. When the plan had
    // to thin the axis it names the survivors outright, because Recharts'
    // own interval walk drops the last category (see XAxisPlan.ticks); the
    // interval is then 0 so every named tick is drawn.
    interval: plan ? (plan.ticks ? 0 : plan.interval) : ('preserveStartEnd' as const),
    ...(plan?.ticks ? { ticks: plan.ticks as string[] } : {}),
    ...(plan ? {} : { minTickGap: 8 }),
    // Hijri buckets arrive as "1444-09" (sortable); the axis names the month
    // in the reader's language (Phase 7.5).
    ...(String((cfg as { dimension_granularity?: string }).dimension_granularity ?? '').startsWith('hijri')
      ? { tickFormatter: (v: unknown) => {
            const text = hijriLabel(v)
            return plan && Number.isFinite(plan.maxChars) ? clipLabel(text, plan.maxChars) : text
          } }
      : plan && Number.isFinite(plan.maxChars)
        ? { tickFormatter: (v: unknown) => clipLabel(String(v ?? ''), plan.maxChars) }
        : {}),

    label: title ? xTitleLabel(title) : undefined,
  }
}

/** Recharts' own default. Fits "1,500" and nothing much longer. */
const DEFAULT_Y_WIDTH = 60

/**
 * How much gutter the value axis needs, measured from the ACTUAL tick labels.
 *
 * Recharts 2.15 reserves a fixed 60px and neither grows nor clips: a wider
 * label simply overflows its gutter and prints across the plot, which is the
 * bug this fixes. (`width: 'auto'` is a Recharts 3 feature -- 2.15.4's
 * ChartUtils has no handling for it at all, so passing it would silently do
 * nothing while the types complain.)
 *
 * An earlier version of this estimated from the FORMAT and was wrong in the
 * commonest case: a widget with no explicit format still renders "$2,000,000"
 * because the tick FORMATTER adds the symbol, so `fmt` was null and the axis
 * stayed at 60px. The values are what get drawn, so the values are what get
 * measured.
 *
 * ~6.2px per character at the 10px default tick font, plus the tick mark's
 * own margin. Deliberately an over-estimate: a slightly wide gutter is
 * invisible, a narrow one prints over the data.
 */
export function yAxisWidth(
  cfg: FormatConfig,
  values?: readonly unknown[],
  fmt?: CalcColumnFormat | null,
): number {
  const explicit = (cfg as { y_axis_width?: number }).y_axis_width
  if (typeof explicit === 'number' && explicit > 0) return explicit

  // An author-set bound is drawn as a tick even when no datum comes near it,
  // so it is measured alongside the data -- `yAxisProps` already honours these
  // in `domain`.
  const candidates: unknown[] = [...(values ?? [])]
  if (cfg.y_min !== undefined) candidates.push(cfg.y_min)
  if (cfg.y_max !== undefined) candidates.push(cfg.y_max)
  if (candidates.length === 0) return DEFAULT_Y_WIDTH

  const fontSize = cfg.axis_tick_size ?? DEFAULT_TICK_SIZE
  let widest = 0
  for (const v of candidates) {
    const n = typeof v === 'number' ? v : Number(v)
    if (!Number.isFinite(n)) continue
    // Measured through `textWidth`, not by character count: on an Arabic
    // locale these ticks carry Arabic-Indic digits and the bidi isolates
    // fmtStr wraps currency in, and those isolates render nothing at all.
    widest = Math.max(widest, textWidth(fmtStr(n, fmt), fontSize))
  }
  if (widest === 0) return DEFAULT_Y_WIDTH

  // Recharts labels "nice" ticks computed from the domain, not the data, and
  // the top one can be a digit longer than any actual value (max 999,999 ->
  // top tick "1,000,000"). One character of headroom covers that far more
  // cheaply than reimplementing getNiceTickValues, and erring wide is free.
  const px = Math.round(widest + fontSize * CHAR_W) + 12
  // Bounded: an absurd label must not eat the plot it is labelling.
  return Math.min(Math.max(DEFAULT_Y_WIDTH, px), 160)
}

/** Lane reserved for the y-axis TITLE when the author sets one. The title is
 *  drawn rotated at 11px against the outer edge of the gutter, and the gutter
 *  is otherwise sized for the tick labels alone -- so without this the two
 *  share the same strip and the longest label runs under the title. */
export const Y_TITLE_W = 16

/** A category label on the y axis may take at most this much of the card
 *  before it is ellipsised instead. Horizontal-bar charts live or die on the
 *  bar being visible, not on the full department name. */
const MAX_Y_CATEGORY_W = 180

export interface YCategoryPlan {
  width: number
  /** Recharts numeric interval: draw every (interval + 1)th label. */
  interval: number
  maxChars: number
}

/**
 * Size the gutter of a CATEGORY y axis (horizontal bars, dot plots, Gantt) to
 * the names it actually has to draw.
 *
 * The three renderers that own such an axis each pinned a fixed gutter --
 * 90px, 100px, 100px -- so a 35-character department name was estimated to
 * start 127px LEFT of the card and was simply cut off. Sizing from the labels
 * fixes that; the cap plus ellipsis stops the opposite failure, where one long
 * name squeezes the plot down to nothing.
 */
export function yCategoryPlan(
  labels: readonly string[],
  opts: { fontSize?: number; height?: number; maxWidth?: number; hasTitle?: boolean } = {},
): YCategoryPlan {
  const fontSize = opts.fontSize ?? DEFAULT_TICK_SIZE
  const cap = opts.maxWidth ?? MAX_Y_CATEGORY_W
  const lineH = fontSize + 2
  const n = labels.length
  if (n === 0) return { width: DEFAULT_Y_WIDTH, interval: 0, maxChars: Infinity }

  const want = Math.ceil(widestLabel(labels, fontSize)) + 12

  let width = Math.min(want, cap)
  let maxChars = Infinity
  if (want > cap) {
    const widest = labels.reduce((a, b) =>
      textWidth(String(b ?? ''), fontSize) > textWidth(String(a ?? ''), fontSize) ? b : a, labels[0])
    maxChars = Math.max(3, charsThatFit(String(widest ?? ''), fontSize, cap - 12))
  }
  if (opts.hasTitle) width += Y_TITLE_W

  // Category labels stack vertically, so they collide on HEIGHT, not width.
  // Unlike the x axis there is no rotation to fall back on -- a sideways label
  // beside a horizontal bar is unreadable -- so thinning is the only lever.
  // Netted the same way xAxisProps nets the gutter: the category axis only
  // gets the tile height that is left after the x band and margins.
  const height = opts.height && opts.height > 0
    ? Math.max(80, opts.height - Y_BAND_ALLOWANCE) : NOMINAL_PLOT_H
  const slot = height / n
  const interval = Math.max(0, Math.ceil(lineH / Math.max(slot, 1)) - 1)

  return { width: Math.max(DEFAULT_Y_WIDTH, width), interval, maxChars }
}

/** Nominal plot height when the caller cannot measure one -- see
 *  NOMINAL_PLOT_W for why prop builders often cannot. */
const NOMINAL_PLOT_H = 300

/** What the category band, legend and margins take out of a tile before the
 *  value axis sees any of it. Generous for the same reason as
 *  X_GUTTER_ALLOWANCE. */
const Y_BAND_ALLOWANCE = 72

/**
 * How many ticks a NUMERIC y axis should generate for the height it has.
 *
 * Capped at Recharts' own default of 5 on purpose: this exists to THIN a short
 * chart, never to add gridlines to a normal one, so an untouched widget keeps
 * exactly the axis it has today.
 */
export function yTickCount(height?: number, fontSize = DEFAULT_TICK_SIZE): number {
  const h = height && height > 0 ? height : NOMINAL_PLOT_H
  // A tick needs its own line height plus enough air to read as a separate
  // gridline rather than a hatch pattern.
  const pitch = (fontSize + 2) * 2.5
  return Math.max(2, Math.min(5, Math.floor(h / pitch)))
}

export function yAxisProps(
  cfg: FormatConfig,
  rtl: boolean,
  fmt?: CalcColumnFormat, // callers apply their own tickFormatter; not returned by this builder
  /** The values this axis will actually plot. Used only to size the gutter --
   *  see `yAxisWidth` for why the FORMAT alone is not enough. Ahead of
   *  `observedMin` because nearly every caller has values and few have a
   *  minimum: the other order made most call sites pass `undefined` in the
   *  slot between, and a stray number landing in the wrong one is the kind of
   *  positional bug the types would not catch. */
  values?: readonly unknown[],
  observedMin?: number,
  /** Extra context the builder cannot infer.
   *  `categoryLabels` switches this axis to the CATEGORY plan (horizontal
   *  bars, dot plots, Gantt); omit it for an ordinary value axis.
   *  `height` is the measured plot height when the caller has one. */
  /** Extra context the builder cannot infer. `title` overrides the axis title
   *  for THIS axis -- a dual-axis chart's right side passes `y2_axis_label`
   *  through it, so the two axes can be named separately. */
  opts?: { categoryLabels?: readonly string[]; height?: number; title?: string },
) {
  const tickFontSize = cfg.axis_tick_size ?? DEFAULT_TICK_SIZE
  // `opts.title` when the caller supplied one (including an empty string, which
  // means "this axis has no title"), otherwise the widget's own y-axis title.
  const axisTitle = resolveTitle(opts?.title, cfg.y_axis_label,
                                axisTitles(cfg).measure)
  const yAngle = (cfg as { y_axis_angle?: number }).y_axis_angle
  const catPlan = opts?.categoryLabels?.length
    ? yCategoryPlan(opts.categoryLabels, {
        fontSize: tickFontSize, height: opts.height, hasTitle: !!axisTitle,
      })
    : null

  // Recharts cannot render a log axis through zero or negatives. Rendering an
  // empty chart is a worse answer than quietly rendering a linear one, so the
  // caller passes the observed minimum and we degrade when it is non-positive.
  // Degrade if log is requested but any known lower bound is non-positive.
  const logRequested = cfg.y_scale === 'log'
  const logUsable =
    logRequested &&
    (cfg.y_min === undefined || cfg.y_min > 0) &&
    (observedMin === undefined || observedMin > 0)

  // Domain follows the author's explicit y_min/y_max regardless of whether log
  // scale ends up usable — an explicit bound must never be discarded just because
  // log degraded to linear. logUsable governs `scale` only, below.
  let domain: [number | string, number | string] | undefined
  if (cfg.y_min !== undefined || cfg.y_max !== undefined) {
    domain = [cfg.y_min ?? 'auto', cfg.y_max ?? 'auto']
  } else if (logUsable) {
    // Log scale usable with no explicit bounds: let Recharts auto-size both ends.
    domain = ['auto', 'auto']
  }

  return {
    tick: tick(cfg),
    axisLine: cfg.axis_line ?? false,
    tickLine: cfg.tick_line ?? false,
    orientation: (rtl ? 'right' : 'left') as 'left' | 'right',
    // Recharts' default y-axis width is 60px, which fits "1,500" and nothing
    // longer. A currency tick like "$ 2,000,000" is ~90px, so the label ran
    // out of its gutter and printed over the bars -- and on the second axis of
    // a dual-axis chart it was clipped by the chart edge instead.
    //
    // Recharts 2.15 accepts width:'auto', but its bundled type definitions do
    // not, so the width is computed instead of cast: an estimate from the
    // FORMAT (currency and big numbers are wide, a bare integer is not) is
    // honest about what it knows, whereas `as any` would only hide that the
    // types disagree with the runtime.
    width: catPlan
      ? catPlan.width
      : yAxisWidth(cfg, values, fmt) + (axisTitle ? Y_TITLE_W : 0),

    // Numeric ticks: an explicit count and an explicit interval, for the same
    // reason the x axis stopped using 'preserveStartEnd' -- Recharts' default
    // decides from MEASURED text, which is zero under jsdom, so the axis drew
    // one tick in the suite and five in a browser. The count is capped at
    // Recharts' own default so a normal chart is unchanged and only a short
    // one is thinned.
    ...(catPlan
      ? { interval: catPlan.interval }
      : {
          interval: 0 as const,
          // Netted the same way yCategoryPlan nets it: what arrives is the
          // TILE height, and the value axis only gets what is left after the
          // category band, legend and margins. Passing the raw tile height
          // over-counted the room and kept five ticks on a chart with space
          // for two.
          tickCount: yTickCount(
            opts?.height && opts.height > 0
              ? Math.max(80, opts.height - Y_BAND_ALLOWANCE) : undefined,
            tickFontSize),
        }),

    // Category names too long for the capped gutter are ellipsised rather than
    // being drawn off the edge of the card. Numeric axes are untouched here:
    // their callers supply their own value tickFormatter after the spread.
    ...(catPlan && Number.isFinite(catPlan.maxChars)
      ? { tickFormatter: (v: unknown) => clipLabel(String(v ?? ''), catPlan.maxChars) }
      : {}),

    // Author override, mirroring the x axis control. Left automatic (absent)
    // this changes nothing.
    ...(yAngle !== undefined && yAngle !== null
      ? { angle: yAngle, textAnchor: (rtl ? 'start' : 'end') as 'start' | 'end' }
      : {}),

    allowDecimals: false,
    scale: logUsable ? ('log' as const) : undefined,
    domain,
    label: axisTitle ? yTitleLabel(axisTitle, rtl) : undefined,
  }
}

export function gridProps(cfg: FormatConfig) {
  // wall_color paints the plot area behind the grid -- SAS's "wall". CartesianGrid's
  // own fill is the one Recharts surface that covers exactly the plotting rectangle,
  // so the wall and the grid share an element. A wall with the grid turned OFF still
  // needs that element, hence the fill-only early return rather than null.
  const wall = (cfg as { wall_color?: string }).wall_color
  if (cfg.grid === false) {
    return wall ? { stroke: 'transparent', fill: wall } : null
  }
  // Horizontal rules only, solid and faint: the value lines a reader traces
  // across to the axis. Vertical rules repeat what the category labels already
  // say, and a dashed grid at full border strength was the busiest thing on
  // most charts. Dashed stays one setting away.
  return {
    strokeDasharray: cfg.grid_style === 'dashed' ? '3 3' : undefined,
    stroke: cfg.grid_color ?? 'var(--dl-table-rule, var(--border))',
    vertical: false,
    ...(wall ? { fill: wall } : {}),
  }
}

const LEGEND_PLACEMENT = {
  bottom: { verticalAlign: 'bottom' as const, align: 'center' as const, layout: 'horizontal' as const },
  top:    { verticalAlign: 'top' as const,    align: 'center' as const, layout: 'horizontal' as const },
  left:   { verticalAlign: 'middle' as const, align: 'left' as const,   layout: 'vertical' as const },
  right:  { verticalAlign: 'middle' as const, align: 'right' as const,  layout: 'vertical' as const },
}

export function legendProps(cfg: FormatConfig, rtl = false) {
  if (cfg.legend === false) return null
  const position = cfg.legend_position ?? 'bottom'
  return {
    // A titled legend draws its own content. Built here rather than in each
    // renderer so all nine that already spread these props inherit it; the
    // title sits UNDER the entries on a bottom legend, which is where a reader
    // looks for it and where SAS puts it.
    ...(cfg.legend_title
      ? { content: (props: { payload?: readonly { value?: unknown; color?: string }[] }) =>
            createElement(LegendWithTitle, {
              payload: props.payload, title: cfg.legend_title as string,
              below: position === 'bottom',
            }) }
      : {}),
    ...LEGEND_PLACEMENT[position],
    // A legend entry is a SWATCH followed by its label, and that order is the
    // meaning: the mark identifies the colour, the words explain it. Recharts
    // lays the entries out with inline elements, so `dir="rtl"` mirrored each
    // one into "cost▪" -- the swatch trailing the text it belongs to, which
    // reads as a bullet on the wrong side rather than a key.
    //
    // The wrapper is pinned to ltr so swatch-then-label survives, while the
    // legend BLOCK still sits wherever the mirrored layout puts it. Labels
    // that are themselves Arabic still render right-to-left, because the text
    // node's own bidi resolution is untouched by the container's direction.
    ...(rtl ? { wrapperStyle: { direction: 'ltr' as const } } : {}),
  }
}

/**
 * Overview axis (Recharts <Brush>): a miniature of the whole series under the
 * chart with draggable handles, so a long series can be inspected without
 * losing sight of the whole. Off unless the author opts in -- a brush on a
 * five-point chart is chrome, not signal -- and null (not hidden-but-mounted)
 * when off so untouched widgets render byte-identically to before.
 */
export interface BrushRange { start: string; end: string; startIndex: number; endIndex: number; of: number }

export function brushProps(cfg: FormatConfig, overview?: {
  /** The plotted rows; with them the brush carries a mini chart of the whole series. */
  rows?: readonly Record<string, unknown>[]
  /** The value key the mini chart draws ('value' for a single series). */
  dataKey?: string
  /** Reports the zoomed range (null = the whole series), so the widget can say
   *  in its transparency pane that the reader is looking at a slice. */
  onChange?: (range: BrushRange | null) => void
}) {
  if (!cfg.overview_axis) return null
  const rows = overview?.rows
  const mini = rows && rows.length > 1 && overview?.dataKey
    ? createElement(LineChart, { data: rows as Record<string, unknown>[] },
        // Recharts' Line class types its defaultProps loosely enough that
        // createElement's overloads reject it; the props here are the ones
        // <Line> takes in every renderer.
        createElement(Line as unknown as ComponentType<Record<string, unknown>>, { dataKey: overview.dataKey, stroke: 'var(--accent)', dot: false,
          strokeWidth: 1, isAnimationActive: false }))
    : undefined
  return {
    dataKey: 'name',
    height: mini ? 30 : 18,
    travellerWidth: 8,
    stroke: 'var(--accent)',
    fill: 'var(--surface2, transparent)',
    ...(mini ? { children: mini } : {}),
    ...(overview?.onChange && rows ? {
      onChange: (r: { startIndex?: number; endIndex?: number }) => {
        const n = rows.length
        const a = r?.startIndex ?? 0
        const b = r?.endIndex ?? n - 1
        overview.onChange!(a <= 0 && b >= n - 1 ? null : {
          start: String(rows[a]?.name ?? a), end: String(rows[b]?.name ?? b),
          startIndex: a, endIndex: b, of: n,
        })
      },
    } : {}),
  }
}

/** Labels drawn on one series before they stop being readable.
 *
 *  Twelve for the same reason `HIER_MAX_CHILDREN` and `FACET_MAX_PANELS` are
 *  twelve: past roughly a dozen, the marks are closer together than the text
 *  that names them. */
export const MAX_DATA_LABELS = 12

/** Every how-manyth point carries a label, given `n` points. */
export function labelStride(n: number): number {
  return n <= MAX_DATA_LABELS ? 1 : Math.ceil(n / MAX_DATA_LABELS)
}

/** Does the point at `index` keep its label?
 *
 *  Anchored on the LAST point rather than the first. On a time series the
 *  newest value is the one the reader came for, and a naive `i % stride === 0`
 *  drops it whenever `n - 1` is not a multiple of the stride -- labelling
 *  everything except the number being asked about.
 */
export function keepLabel(index: number, n: number): boolean {
  const stride = labelStride(n)
  if (stride === 1) return true
  return (n - 1 - index) % stride === 0
}

export function labelListProps(
  cfg: FormatConfig, fmt?: CalcColumnFormat, dataKey = 'value', pointCount = 0,
) {
  // Opt-in, not opt-out: switching every existing chart to labelled would be a
  // visual change to widgets nobody edited. What "on" means has since narrowed
  // slightly -- labels, THINNED to stay legible -- because labelling all fifty
  // points of a line chart produced a band of overlapping text naming nothing.
  //
  // Note: grouped and column-keyed renderers (BarChartRenderer,
  // RibbonChartRenderer) must pass their own dataKey matching their Bar/Line
  // dataKey values.
  if (!cfg.data_labels) return null

  // Thinning rides on `valueAccessor`, which Recharts calls with (entry, index)
  // -- the only place in LabelList that sees an index. `formatter` cannot do
  // it: Label.js calls `formatter(label)` with one argument, so a formatter
  // never learns which point it is on. Returning '' for a dropped point leaves
  // the mark drawn and the tooltip intact; only the text goes away.
  const n = pointCount
  return {
    position: 'top' as const,
    style: { fill: 'var(--muted)', fontSize: 10 },
    valueAccessor: (entry: Record<string, unknown>, index: number) => {
      if (n > 0 && !keepLabel(index, n)) return ''
      const payload = (entry?.payload ?? entry) as Record<string, unknown>
      const raw = payload?.[dataKey] ?? entry?.value
      return raw == null ? '' : fmtStr(raw, fmt)
    },
  }
}

