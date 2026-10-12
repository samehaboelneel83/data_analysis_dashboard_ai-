/**
 * Ready-made looks for a dashboard: one click sets every key of its style
 * (lib/dashboardStyle) and its chart palette together, and each control of
 * the style panel can still be changed afterwards. Nothing here is a new kind
 * of setting -- a look is only a filled-in style.
 */
import type { DashboardStyle } from './dashboardStyle'

export interface DashboardLook { key: string; style: DashboardStyle }

export const LOOKS: DashboardLook[] = [
  { key: 'midnight', style: {
    mode: 'dark', palette: 'emerald', page_background: '#0a1322', card_background: '#101c31', text_color: '#d6e2f5',
    title_color: '#ffffff', border_style: 'solid', border_width: 1, border_color: '#1c2c48', radius: 14, shadow: 'soft',
    font_family: 'sans', title_size: 14, title_weight: 600, number_size: 30, accent: '#4ade80', gap: 14 } },
  { key: 'deepspace', style: {
    mode: 'dark', palette: 'aurora', page_background: '#060a18', card_background: '#0c142c', text_color: '#cfd9f5',
    title_color: '#f1f5ff', border_style: 'solid', border_width: 1, border_color: '#22305c', radius: 16, shadow: 'strong',
    font_family: 'sans', title_size: 13, title_weight: 700, number_size: 32, accent: '#38bdf8', gap: 16 } },
  { key: 'ember', style: {
    mode: 'dark', palette: 'ember', page_background: '#0a0d14', card_background: '#11151f', text_color: '#d9dee8',
    title_color: '#ffffff', border_style: 'solid', border_width: 1, border_color: '#1f2532', radius: 12, shadow: 'soft',
    font_family: 'sans', title_size: 14, title_weight: 600, number_size: 30, accent: '#fb923c', gap: 14 } },
  { key: 'graphite', style: {
    mode: 'dark', palette: 'default', page_background: '#0e1014', card_background: '#171a20', text_color: '#e3e6eb',
    title_color: '#ffffff', border_style: 'solid', border_width: 1, border_color: '#272c36', radius: 10, shadow: 'none',
    font_family: 'sans', title_size: 13, title_weight: 600, number_size: 28, accent: '#a78bfa', gap: 12 } },
  { key: 'clean', style: {
    mode: 'light', palette: 'default', page_background: '#f4f6fb', card_background: '#ffffff', border_style: 'none',
    radius: 16, shadow: 'raised', font_family: 'sans', title_size: 14, title_weight: 600, number_size: 30,
    accent: '#2563eb', gap: 16 } },
  { key: 'outline', style: {
    mode: 'light', palette: 'ocean', page_background: '#ffffff', card_background: '#ffffff', border_style: 'solid',
    border_width: 1, border_color: '#e2e8f0', radius: 8, shadow: 'none', font_family: 'sans', title_size: 13,
    title_weight: 700, number_size: 28, accent: '#0284c7', gap: 12 } },
]

/** The look a style IS, when every key of one matches it (so the panel can
 *  mark the one in use); undefined once anything has been changed by hand. */
export function lookOf(style: DashboardStyle | null | undefined): string | undefined {
  const s = (style ?? {}) as Record<string, unknown>
  return LOOKS.find(l => {
    const want = l.style as Record<string, unknown>
    return Object.keys(want).length === Object.keys(s).length && Object.keys(want).every(k => want[k] === s[k])
  })?.key
}
