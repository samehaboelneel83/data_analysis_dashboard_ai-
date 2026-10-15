import type { ReportPage } from '../types/report'

/**
 * C-21: a page's size.
 *
 * "fit" is the flowing canvas that fills the available width (the long-standing
 * behaviour, and still the default). The others are a FIXED frame of
 * `custom_width` x `custom_height` px; the presets store their size too.
 *
 * A page with no stored dimensions flows whatever its `page_size` says: every
 * page made before page sizes were applied carries the old default "16:9" with
 * no dimensions, and those dashboards must keep their layout.
 */
export type PageSizeChoice = 'fit' | '16:9' | '4:3' | 'custom'

export const PAGE_PRESETS: Record<'16:9' | '4:3', { w: number; h: number }> = {
  '16:9': { w: 1280, h: 720 },
  '4:3':  { w: 960,  h: 720 },
}
/** The server refuses anything outside this range (schemas.PageDim). */
export const PAGE_DIM_MIN = 320
export const PAGE_DIM_MAX = 10000

type Sized = Pick<ReportPage, 'page_size' | 'custom_width' | 'custom_height'> | null | undefined

/** The fixed frame a page is drawn in, or null for a flowing page. */
export function pageFrame(page: Sized): { w: number; h: number } | null {
  if (!page || page.page_size === 'fit') return null
  const w = Number(page.custom_width), h = Number(page.custom_height)
  if (!(w > 0) || !(h > 0)) return null
  const clamp = (n: number) => Math.min(PAGE_DIM_MAX, Math.max(PAGE_DIM_MIN, Math.round(n)))
  return { w: clamp(w), h: clamp(h) }
}

/** What the Page size control shows as chosen. */
export function pageSizeChoice(page: Sized): PageSizeChoice {
  if (!pageFrame(page)) return 'fit'
  const s = page!.page_size
  return s === '16:9' || s === '4:3' || s === 'custom' ? s : 'custom'
}

/** A typed dimension, or null when it is not a whole number in range. */
export function parsePageDim(text: string): number | null {
  if (!/^\s*\d+\s*$/.test(text)) return null
  const n = Number(text)
  return n >= PAGE_DIM_MIN && n <= PAGE_DIM_MAX ? n : null
}
