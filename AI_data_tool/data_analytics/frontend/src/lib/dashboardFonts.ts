/**
 * The fonts a dashboard style can name are SHIPPED with the app (open-licence
 * families, SIL OFL, from the @fontsource packages) -- so a dashboard reads
 * the same on a machine that has none of them installed. Each family is
 * fetched from this server the first time a dashboard uses it, never before,
 * and never from another site.
 */
import type { StyleFont } from './dashboardStyle'

const LOADERS: Record<StyleFont, (() => Promise<unknown>)[]> = {
  system: [],
  sans: [() => import('@fontsource/inter/400.css'), () => import('@fontsource/inter/600.css'), () => import('@fontsource/inter/700.css')],
  serif: [() => import('@fontsource/merriweather/400.css'), () => import('@fontsource/merriweather/700.css')],
  mono: [() => import('@fontsource/jetbrains-mono/400.css'), () => import('@fontsource/jetbrains-mono/700.css')],
  rounded: [() => import('@fontsource/nunito/400.css'), () => import('@fontsource/nunito/600.css'), () => import('@fontsource/nunito/700.css')],
  condensed: [() => import('@fontsource/roboto-condensed/400.css'), () => import('@fontsource/roboto-condensed/700.css')],
  arabic: [() => import('@fontsource/noto-kufi-arabic/400.css'), () => import('@fontsource/noto-kufi-arabic/700.css')],
}

const asked = new Set<StyleFont>()

/** Fetch a family's files once. A failure leaves the stack's next font in use. */
export function ensureFont(family: StyleFont | undefined): void {
  if (!family || asked.has(family)) return
  asked.add(family)
  for (const load of LOADERS[family] ?? []) void load().catch(() => { /* the fallback font shows */ })
}
