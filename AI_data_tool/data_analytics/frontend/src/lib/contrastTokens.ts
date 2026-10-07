/**
 * QA4 V1: the text colours of a widget with its own background follow that
 * background, not the theme. In the dark theme a light background (#fde68a)
 * kept white titles, labels and axis text; in the light theme a dark one kept
 * dark text. The widget sets these tokens on itself, so everything drawn in it
 * that reads them (title, header icons, axis ticks, data labels, legend, grid)
 * follows. A background that is not a plain colour (a variable, a gradient)
 * changes nothing.
 */
export function parseColor(c: string): [number, number, number] | null {
  const s = c.trim().toLowerCase()
  let m = s.match(/^#([0-9a-f]{3,8})$/)
  if (m) {
    let h = m[1]
    if (h.length === 3 || h.length === 4) h = h.slice(0, 3).split('').map(x => x + x).join('')
    if (h.length !== 6 && h.length !== 8) return null
    return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)]
  }
  m = s.match(/^rgba?\(\s*(\d+)[\s,]+(\d+)[\s,]+(\d+)/)
  return m ? [Number(m[1]), Number(m[2]), Number(m[3])] : null
}

/** WCAG relative luminance, 0 (black) to 1 (white). */
export function luminance([r, g, b]: [number, number, number]): number {
  const ch = (v: number) => { const x = v / 255; return x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4 }
  return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)
}

const ON_LIGHT = { '--text': '#1f2328', '--muted': '#4d5560', '--border': 'rgba(0, 0, 0, .16)',
  '--surface2': 'rgba(0, 0, 0, .05)', '--dl-table-rule': 'rgba(0, 0, 0, .10)' }
const ON_DARK = { '--text': '#f3f5f7', '--muted': '#c3cad3', '--border': 'rgba(255, 255, 255, .22)',
  '--surface2': 'rgba(255, 255, 255, .07)', '--dl-table-rule': 'rgba(255, 255, 255, .14)' }

export function contrastTokens(background: unknown): Record<string, string> {
  if (typeof background !== 'string') return {}
  const rgb = parseColor(background)
  if (!rgb) return {}
  // The midpoint where black and white text have equal contrast (~0.18).
  return luminance(rgb) > 0.18 ? ON_LIGHT : ON_DARK
}
