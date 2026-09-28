/**
 * Dates and numbers follow the INTERFACE language, not the browser's.
 *
 * A bare `toLocaleString()` takes the browser's locale, which follows the
 * operating system. On a Windows machine set to Arabic, an English page read
 * "Last refreshed 28ص 1:38:17 2026/9/" and a dashboard card "272026/9/"
 * (live QA 2026-09-28) -- from 157 such calls across 51 files. Rather than
 * thread the language through every one, the calls that name NO locale take
 * the interface's: English formats as en-GB (day/month/year), and Arabic
 * keeps the browser's own Arabic formatting, exactly as before. A call that
 * names a locale is never touched.
 *
 * The same technique the test setup uses to pin en-US (src/test/setup.ts);
 * installed from main.tsx only, so the suite keeps its own pin.
 */

let current: string | undefined
let installed = false

/** The locale bare calls get for this interface language. */
export function displayLocaleFor(language: string): string | undefined {
  return language === 'en' ? 'en-GB' : undefined
}

/** Follow the interface language (DirectionProvider calls this on change). */
export function setDisplayLocale(language: string) {
  current = displayLocaleFor(language)
}

const pick = (locales: unknown) => (locales === undefined ? current : locales) as Intl.LocalesArgument

/** Route bare locale calls through `current`. Idempotent. */
export function installDisplayLocale(language: string) {
  setDisplayLocale(language)
  if (installed) return
  installed = true
  for (const [proto, method] of [
    [Number.prototype, 'toLocaleString'], [BigInt.prototype, 'toLocaleString'],
    [Date.prototype, 'toLocaleString'], [Date.prototype, 'toLocaleDateString'],
    [Date.prototype, 'toLocaleTimeString'],
  ] as const) {
    const original = (proto as unknown as Record<string, (...a: unknown[]) => string>)[method]
    Object.defineProperty(proto, method, {
      configurable: true, writable: true,
      value(this: unknown, locales?: unknown, options?: unknown) { return original.call(this, pick(locales), options) },
    })
  }
  for (const name of ['NumberFormat', 'DateTimeFormat', 'PluralRules', 'RelativeTimeFormat', 'ListFormat'] as const) {
    const Original = (Intl as unknown as Record<string, any>)[name]
    if (!Original) continue
    const Pinned = function (this: unknown, locales?: unknown, options?: unknown) {
      return new Original(pick(locales), options)
    } as any
    Pinned.prototype = Original.prototype
    Pinned.supportedLocalesOf = Original.supportedLocalesOf
    ;(Intl as unknown as Record<string, unknown>)[name] = Pinned
  }
}
