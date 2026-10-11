/**
 * A dashboard's look beyond its palette: fonts, card borders, corners,
 * shadows, backgrounds, light or dark (backend services/dashboard_templates/
 * spec.py, STYLE_KEYS -- the two lists are the same).
 *
 * It is applied as CSS custom properties on the element that holds a page's
 * widgets, so every place a dashboard is drawn (the builder, the viewer, the
 * shared and embedded pages, print) gets it from one function, and a widget's
 * own setting still wins: the card reads `var(--dl-s-…, <the app's default>)`
 * only where its own config says nothing.
 */
import type { CSSProperties } from 'react'
import { ensureFont } from './dashboardFonts'

export type StyleFont = 'system' | 'sans' | 'serif' | 'mono' | 'rounded' | 'condensed' | 'arabic'
export type StyleBorder = 'none' | 'solid' | 'dashed' | 'dotted' | 'double'
export type StyleShadow = 'none' | 'soft' | 'raised' | 'strong'

export interface DashboardStyle {
  mode?: 'auto' | 'light' | 'dark'
  palette?: string
  font_family?: StyleFont
  font_size?: number
  title_size?: number
  title_weight?: number
  title_align?: 'start' | 'center' | 'end'
  title_color?: string
  text_color?: string
  number_size?: number
  page_background?: string
  card_background?: string
  border_style?: StyleBorder
  border_width?: number
  border_color?: string
  radius?: number
  shadow?: StyleShadow
  padding?: number
  gap?: number
  density?: 'compact' | 'comfortable' | 'spacious'
  accent?: string
}

/** Each stack begins with the family the app ships (lib/dashboardFonts), then
 *  what a machine is likely to have. */
export const FONT_STACKS: Record<StyleFont, string> = {
  system: 'system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
  sans: 'Inter, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
  serif: 'Merriweather, Georgia, "Times New Roman", "Noto Serif", serif',
  mono: '"JetBrains Mono", ui-monospace, "SF Mono", "Cascadia Mono", Menlo, Consolas, monospace',
  rounded: 'Nunito, ui-rounded, "Varela Round", "Segoe UI", sans-serif',
  condensed: '"Roboto Condensed", "Arial Narrow", "Liberation Sans Narrow", sans-serif',
  arabic: '"Noto Kufi Arabic", "Noto Sans Arabic", "Segoe UI", Tahoma, sans-serif',
}
export const FONTS = Object.keys(FONT_STACKS) as StyleFont[]
export const BORDERS: StyleBorder[] = ['none', 'solid', 'dashed', 'dotted', 'double']
export const SHADOWS: Record<StyleShadow, string> = {
  none: 'none',
  soft: '0 1px 2px rgba(15,23,42,.06), 0 1px 3px rgba(15,23,42,.08)',
  raised: '0 4px 12px rgba(15,23,42,.10), 0 2px 4px rgba(15,23,42,.06)',
  strong: '0 12px 28px rgba(0,0,0,.28), 0 4px 8px rgba(0,0,0,.18)',
}
/** The neutral tokens of each mode, for a dashboard that is dark (or light)
 *  whatever the app's own theme is. Explicit colours in the style win. */
const MODE_TOKENS = {
  dark: { surface: '#1e293b', surface2: '#0f172a', text: '#e2e8f0', muted: '#94a3b8', border: '#334155' },
  light: { surface: '#ffffff', surface2: '#f4f6fb', text: '#0f172a', muted: '#64748b', border: '#e5e7eb' },
}

const px = (v: number | undefined) => (typeof v === 'number' ? `${v}px` : undefined)

/** The custom properties (and the few real ones) that carry a style, for the
 *  element holding a page's widgets. An empty style gives an empty object. */
export function styleVars(style?: DashboardStyle | null): CSSProperties {
  const s = style ?? {}
  const out: Record<string, string> = {}
  const set = (k: string, v: string | undefined) => { if (v) out[k] = v }
  const tokens = s.mode === 'dark' || s.mode === 'light' ? MODE_TOKENS[s.mode] : null
  if (tokens) {
    out['--surface'] = s.card_background ?? tokens.surface
    out['--surface2'] = s.page_background ?? tokens.surface2
    out['--text'] = s.text_color ?? tokens.text
    out['--muted'] = tokens.muted
    out['--border'] = s.border_color ?? tokens.border
    out.colorScheme = s.mode as string
  } else {
    set('--text', s.text_color)
  }
  set('--dl-s-page-bg', s.page_background ?? tokens?.surface2)
  set('--dl-s-card-bg', s.card_background ?? tokens?.surface)
  set('--dl-s-font', s.font_family ? FONT_STACKS[s.font_family] : undefined)
  set('--dl-s-font-size', px(s.font_size))
  set('--dl-s-title-size', px(s.title_size))
  set('--dl-s-title-weight', s.title_weight != null ? String(s.title_weight) : undefined)
  set('--dl-s-title-align', s.title_align)
  set('--dl-s-title-color', s.title_color)
  set('--dl-s-number-size', px(s.number_size))
  if (s.border_style || s.border_width != null || s.border_color) {
    const kind = s.border_style ?? 'solid'
    out['--dl-s-border'] = kind === 'none' ? '0 solid transparent'
      // A double rule needs three pixels to show as two lines.
      : `${Math.max(s.border_width ?? 1, kind === 'double' ? 3 : 0)}px ${kind} ${s.border_color ?? tokens?.border ?? 'var(--border)'}`
  }
  set('--dl-s-radius', px(s.radius))
  set('--dl-s-shadow', s.shadow ? SHADOWS[s.shadow] : undefined)
  set('--dl-s-padding', px(s.padding))
  set('--accent', s.accent)
  if (s.font_family) { out.fontFamily = FONT_STACKS[s.font_family]; ensureFont(s.font_family) }
  if (s.font_size) out.fontSize = `${s.font_size}px`
  if (s.text_color || tokens) out.color = out['--text']
  return out as CSSProperties
}

/** The space between cards, in grid pixels, when the style sets one. */
export function styleGap(style?: DashboardStyle | null): number | undefined {
  if (typeof style?.gap === 'number') return style.gap
  return style?.density === 'compact' ? 6 : style?.density === 'spacious' ? 18 : undefined
}

/** A style with empty entries removed -- what is stored. */
export function tidyStyle(style: DashboardStyle): DashboardStyle {
  return Object.fromEntries(Object.entries(style).filter(([, v]) => v !== undefined && v !== null && v !== '')) as DashboardStyle
}
