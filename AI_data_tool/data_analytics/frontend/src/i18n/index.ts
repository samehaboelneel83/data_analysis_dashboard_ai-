import { useCallback } from 'react'
import { useDirection, type Language } from '../contexts/DirectionContext'
import { en, type MessageKey } from './en'
import { ar } from './ar'

const CATALOG: Record<Language, Record<MessageKey, string>> = { en, ar }

export type { MessageKey }
export { en, ar }

/** Longest path prefix wins, matching the top-bar title rule. */
export const PATH_MESSAGE: [string, MessageKey][] = [
  ['/ask', 'nav.askAi'],
  ['/upload', 'nav.upload'],
  ['/datasets', 'nav.datasets'],
  ['/reports', 'nav.dashboards'],
  ['/dashboards', 'nav.dashboards'],
  ['/connections', 'nav.connections'],
  ['/setup', 'setup.title'],
  ['/lineage', 'nav.lineage'],
  ['/glossary', 'nav.glossary'],
  ['/dataflows', 'nav.dataflows'],
  ['/insights', 'nav.insights'],
  ['/automation', 'nav.automations'],
  ['/migration', 'nav.migration'],
  ['/monitoring/jobs', 'nav.jobs'],
  ['/monitoring/deliveries', 'nav.deliveries'],
  ['/monitoring/activity', 'nav.activity'],
  ['/admin/users', 'nav.users'],
  ['/admin/roles', 'nav.roles'],
  ['/admin/org-units', 'nav.orgChart'],
  ['/admin/row-security-rules', 'nav.rowSecurity'],
  ['/admin/column-security-rules', 'nav.columnSecurity'],
  ['/admin/export-policy', 'nav.exportPolicy'],
  ['/admin/api-keys', 'nav.apiKeys'],
  ['/admin/sso', 'nav.sso'],
  ['/admin/maps', 'nav.maps'],
  ['/admin/calendar', 'nav.calendar'],
  ['/admin/audit', 'nav.audit'],
  ['/admin/settings', 'nav.settings'],
  // Admin pages that are reachable but not in the rail still need a title:
  // without an entry here the bar falls back to "Home", which reads as if
  // the navigation had failed. `titles.test.ts` pins that every route has one.
  ['/admin/custom-connectors', 'nav.customConnectors'],
  ['/admin/connection-rules', 'nav.connectionRules'],
  ['/platform/organizations', 'nav.organizations'],
  ['/platform/settings', 'nav.platformSettings'],
]

export const NAV_ITEM_MESSAGE: Record<string, MessageKey> = {
  '/': 'nav.home',
  '/ask': 'nav.askAi',
  '/datasets': 'nav.datasets',
  '/lineage': 'nav.lineage',
  '/glossary': 'nav.glossary',
  '/dataflows': 'nav.dataflows',
  '/upload': 'nav.upload',
  '/connections': 'nav.connections',
  '/reports': 'nav.dashboards',
  '/insights': 'nav.insights',
  '/automation': 'nav.automations',
  '/migration': 'nav.migration',
  '/monitoring/jobs': 'nav.jobs',
  '/monitoring/deliveries': 'nav.deliveries',
  '/monitoring/activity': 'nav.activity',
  '/admin/users': 'nav.users',
  '/admin/roles': 'nav.roles',
  '/admin/org-units': 'nav.orgChart',
  '/admin/row-security-rules': 'nav.rowSecurity',
  '/admin/column-security-rules': 'nav.columnSecurity',
  '/admin/export-policy': 'nav.exportPolicy',
  '/admin/api-keys': 'nav.apiKeys',
  '/admin/sso': 'nav.sso',
  '/admin/maps': 'nav.maps',
  '/admin/calendar': 'nav.calendar',
  '/admin/audit': 'nav.audit',
  '/admin/settings': 'nav.settings',
  '/admin/custom-connectors': 'nav.customConnectors',
  '/platform/organizations': 'nav.organizations',
  '/platform/settings': 'nav.platformSettings',
}

export const SECTION_MESSAGE: Record<string, MessageKey> = {
  Data: 'nav.section.data',
  'Data sources': 'nav.section.dataSources',
  Analyse: 'nav.section.analyse',
  Monitoring: 'nav.section.monitoring',
  Admin: 'nav.section.admin',
  Platform: 'nav.section.platform',
}

function interpolate(template: string, vars?: Record<string, string | number>): string {
  if (!vars) return template
  return template.replace(/\{(\w+)\}/g, (_, k: string) =>
    vars[k] === undefined ? `{${k}}` : String(vars[k]))
}

/** `{n, plural, one{...} two{...} few{# ...} other{# ...}}` -- the ICU shape,
 *  categories chosen by Intl.PluralRules for the language. Arabic needs it:
 *  "منذ 2 ساعة" and "3 عمود" read as mistakes (HR re-test 2026-10-01); the
 *  right forms are "منذ ساعتين" and "3 أعمدة". `#` is the value as passed, so
 *  an already-formatted "240,124" stays formatted. */
const PLURAL = /\{(\w+),\s*plural,\s*((?:[a-z]+\s*\{[^{}]*\}\s*)+)\}/g

export function pluralize(template: string, language: string,
                          vars?: Record<string, string | number>): string {
  if (!vars || !template.includes('plural')) return template
  return template.replace(PLURAL, (whole, k: string, body: string) => {
    const raw = vars[k]
    if (raw === undefined) return whole
    // Arabic-Indic digits ("٨", "٢٫٥") are read too: callers pass localDigits()
    // output, and NaN here left the raw template on screen (QA T2).
    const latin = String(raw).replace(/[\u0660-\u0669]/g, d => String(d.charCodeAt(0) - 0x0660)).replace(/\u066B/g, '.')
    const n = typeof raw === 'number' ? raw : Number(latin.replace(/[,\s\u066C]/g, ''))
    if (!Number.isFinite(n)) return whole
    const forms: Record<string, string> = {}
    for (const m of body.matchAll(/([a-z]+)\s*\{([^{}]*)\}/g)) forms[m[1]] = m[2]
    let cat = 'other'
    try { cat = new Intl.PluralRules(language).select(n) } catch { /* 'other' */ }
    const form = forms[cat] ?? forms.other ?? ''
    return form.replace(/#/g, String(raw))
  })
}

export function translate(
  language: Language,
  key: MessageKey,
  vars?: Record<string, string | number>,
): string {
  const table = CATALOG[language] ?? en
  return interpolate(pluralize(table[key] ?? en[key], language, vars), vars)
}

export function messageForPath(pathname: string): MessageKey {
  const hit = PATH_MESSAGE
    .filter(([p]) => pathname === p || pathname.startsWith(p + '/'))
    .sort((a, b) => b[0].length - a[0].length)[0]
  return hit ? hit[1] : 'nav.home'
}

export function formatTimeAgo(iso: string | undefined, t: TranslateFn): string | null {
  if (!iso) return null
  const ms = Date.now() - new Date(iso).getTime()
  if (Number.isNaN(ms)) return null
  const mins = Math.round(ms / 60000)
  if (mins < 1) return t('time.justNow')
  if (mins < 60) {
    return t(mins === 1 ? 'time.minutesAgo' : 'time.minutesAgo_other', { n: mins })
  }
  const hours = Math.round(mins / 60)
  if (hours < 24) {
    return t(hours === 1 ? 'time.hoursAgo' : 'time.hoursAgo_other', { n: hours })
  }
  const days = Math.round(hours / 24)
  if (days < 30) {
    return t(days === 1 ? 'time.daysAgo' : 'time.daysAgo_other', { n: days })
  }
  return new Date(iso).toLocaleDateString()
}

export type TranslateFn = (key: MessageKey, vars?: Record<string, string | number>) => string

/** Translate a chrome string in the language the switcher currently holds. */
export function useT(): TranslateFn {
  const { language } = useDirection()
  return useCallback(
    (key, vars) => translate(language, key, vars),
    [language],
  )
}
