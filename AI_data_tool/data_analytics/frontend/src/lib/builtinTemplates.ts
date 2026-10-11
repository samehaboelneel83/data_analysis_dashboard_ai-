import { pageTemplatesApi, reportsApi } from '../services/api'
import type { MessageKey, TranslateFn } from '../i18n'

/**
 * QA6 A10: a built-in page template, added in the author's language.
 *
 * The server's built-ins are English ("Four-panel comparison", widgets "By
 * category / Over time / Share / Detail"), so an Arabic author got an English
 * page. Like an automatic chart title, the page and its widgets are named in
 * the language they are created in, and keep it: right after the page is
 * added, its name, title and the widget titles the template set are renamed.
 * A title the template did not set, or one already changed, is left alone.
 * (Backend follow-up: the built-ins should carry message keys.)
 */
const PAGE: Record<string, { name: MessageKey; title: MessageKey }> = {
  'kpi-strip': { name: 'dsh.tpl.kpi', title: 'dsh.tplp.overview' },
  quad: { name: 'dsh.tpl.quad', title: 'dsh.tplp.comparison' },
  'geo-overview': { name: 'dsh.tpl.geo', title: 'dsh.tplp.geography' },
  'detail-page': { name: 'dsh.tpl.detail', title: 'dsh.tplp.detail' },
}
const WIDGET: Record<string, MessageKey> = {
  Breakdown: 'dsh.tplw.breakdown', Trend: 'dsh.tplw.trend', 'By category': 'dsh.tplw.byCategory',
  'Over time': 'dsh.tplw.overTime', Share: 'dsh.tplw.share', Detail: 'dsh.tplw.detail',
  'By region': 'dsh.tplw.byRegion', Total: 'dsh.tplw.total', 'Top regions': 'dsh.tplw.topRegions',
  Filter: 'dsh.tplw.filter', 'Detail rows': 'dsh.tplw.detailRows',
}

/** A template widget's title in the author's language; null when the
 *  template did not set it. */
export function templateWidgetTitle(t: TranslateFn, title: string | null | undefined): string | null {
  if (!title) return null
  const kpi = /^KPI (\d)$/.exec(title)
  if (kpi) return t('dsh.tplw.kpi', { n: kpi[1] })
  return WIDGET[title] ? t(WIDGET[title]) : null
}

export async function addBuiltinPage(reportId: number, key: string, language: string, t: TranslateFn) {
  const added = await pageTemplatesApi.addFrom(reportId, { builtin: key })
  if (language === 'en') return added
  const names = PAGE[key]
  if (names) await reportsApi.updatePage(reportId, added.page_id, { name: t(names.name), title: t(names.title) }).catch(() => {})
  const page = (await reportsApi.get(reportId).catch(() => null))?.pages?.find(p => p.id === added.page_id)
  for (const w of page?.widgets ?? []) {
    const title = templateWidgetTitle(t, w.title)
    if (title) await reportsApi.updateWidget(reportId, added.page_id, w.id, { title }).catch(() => {})
  }
  return added
}
