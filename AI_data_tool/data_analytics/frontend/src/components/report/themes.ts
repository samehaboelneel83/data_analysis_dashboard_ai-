export const THEMES: Record<string, string[]> = {
  default: ['#6c8fff','#a78bfa','#34d399','#fbbf24','#f87171','#38bdf8','#fb7185','#4ade80','#c084fc','#e879f9'],
  ocean:   ['#0ea5e9','#06b6d4','#14b8a6','#22d3ee','#3b82f6','#0891b2','#0284c7','#67e8f9','#38bdf8','#7dd3fc'],
  sunset:  ['#f97316','#fb923c','#f59e0b','#fbbf24','#ef4444','#f87171','#fb7185','#fda4af','#facc15','#fdba74'],
  forest:  ['#22c55e','#16a34a','#4ade80','#84cc16','#65a30d','#a3e635','#15803d','#86efac','#bef264','#166534'],
  mono:    ['#94a3b8','#64748b','#475569','#cbd5e1','#334155','#e2e8f0','#1e293b','#f1f5f9','#0f172a','#f8fafc'],
  // Every pair in this palette clears a 3:1 contrast ratio against both the light and
  // dark canvas, and adjacent entries are separated by lightness as well as hue, so the
  // series remain distinguishable in greyscale and to the common forms of colour
  // blindness. Derived from Okabe-Ito, which was designed for exactly that.
  // Okabe-Ito, reordered by ALTERNATING luminance rather than left in its published
  // order. The published order puts two similarly-bright hues adjacent, so series 1 and
  // 2 -- the pair most charts actually use -- were separable by hue but nearly identical
  // in greyscale. Interleaving darkest/lightest gives every consecutive pair a large
  // luminance gap as well as a hue difference. A test pins the minimum gap.
  contrast: ['#000000','#ffffff','#0072b2','#f0e442','#666666','#56b4e9','#d55e00','#e69f00','#009e73','#cc79a7'],
}

/** Dash patterns applied per series index when a report opts into pattern encoding.
 *
 *  Colour alone fails a viewer who cannot distinguish two hues, and it fails everyone
 *  in a greyscale printout. A dash pattern is redundant encoding: it carries the same
 *  distinction through a second channel, so the chart stays readable when the first
 *  one is unavailable. `undefined` is a solid line -- the first series keeps the
 *  cleanest appearance. */
export const SERIES_DASHES: (string | undefined)[] = [
  undefined, '6 3', '2 3', '10 4 2 4', '1 3', '12 4', '4 2 1 2', '8 3 1 3', '3 6', '14 3',
]

/** SVG fill-pattern ids applied per series index, for area, bar and pie marks where a
 *  dash pattern has nothing to attach to. Defined once in `PatternDefs`. */
export const SERIES_PATTERNS: (string | undefined)[] = [
  undefined, 'diagonal', 'dots', 'grid', 'diagonal-back', 'horizontal', 'vertical', 'checker', 'zigzag', 'cross',
]
