import type { CalcColumnFormat } from '../../../services/api'
import type { RuleStyles } from '../../../lib/displayRules'

export interface ChartRendererProps {
  rows: any[]
  data: any
  cfg: any
  rtl: boolean
  broadcasts: boolean
  localSelected: unknown
  onClickPoint: (v: unknown) => void
  measureFmt?: CalcColumnFormat
  measure2Fmt?: CalcColumnFormat
  allFormats?: Record<string, CalcColumnFormat | undefined>
  ruleStyles?: RuleStyles
  /** Columns classified as geography, and the boundary set each draws with:
   *  `{ governorate: 9 }`. Derived from the dataset's `column_meta`, so the
   *  classification travels with the DATA rather than with one widget — and
   *  published to shared links and embeds as a derived subset, never as the
   *  whole blob, which also carries the prep recipe. */
  geography?: Record<string, number>
  /** Measured pixel size of the tile this chart fills, supplied by
   *  WidgetRenderer. The axis planners need real numbers: sized from a nominal
   *  width they were too optimistic on a narrow tile, and the labels collided
   *  anyway -- most visibly in Arabic, whose glyphs are wider, so the same
   *  error bit sooner. Optional because the measurement lands one frame after
   *  mount; until then the planners fall back to their nominal. */
  plotW?: number
  plotH?: number
  /** Overview-axis zoom, reported so the widget can show it as a widget-local
   *  filter (the transparency pane, a "zoomed" chip with reset). */
  onBrushChange?: (range: import('./axisOptions').BrushRange | null) => void
}
