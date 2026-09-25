import '@testing-library/jest-dom'

// jsdom doesn't implement matchMedia -- Layout.tsx's theme detection (and anything
// that renders it) needs this polyfilled globally.
if (typeof window !== 'undefined' && !window.matchMedia) {
  window.matchMedia = (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }) as unknown as MediaQueryList
}

// jsdom doesn't implement ResizeObserver -- recharts' ResponsiveContainer (used by
// every chart widget) needs this polyfilled globally.
if (typeof window !== 'undefined' && !window.ResizeObserver) {
  window.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver
}

// The suite's expected strings are en-US ("2,000", "Showing 20 of 213"), but a
// bare toLocaleString() takes Node's DEFAULT locale, and on Windows Node reads
// that from the OS -- LANG/LC_ALL are ignored. On a machine set to Arabic
// (ar-EG) 22 tests failed on "٢٬٠٠٠". Pin the default for calls that name no
// locale; a call that asks for 'ar' still gets Arabic digits.
const TEST_LOCALE = 'en-US'
const pick = (locales: unknown) => (locales === undefined ? TEST_LOCALE : locales) as Intl.LocalesArgument
for (const [proto, method] of [
  [Number.prototype, 'toLocaleString'], [BigInt.prototype, 'toLocaleString'],
  [Date.prototype, 'toLocaleString'], [Date.prototype, 'toLocaleDateString'],
  [Date.prototype, 'toLocaleTimeString'],
] as const) {
  const original = (proto as any)[method] as (...a: unknown[]) => string
  Object.defineProperty(proto, method, {
    configurable: true, writable: true,
    value(this: unknown, locales?: unknown, options?: unknown) { return original.call(this, pick(locales), options) },
  })
}
for (const name of ['NumberFormat', 'DateTimeFormat', 'PluralRules', 'RelativeTimeFormat', 'ListFormat', 'Collator'] as const) {
  const Original = (Intl as any)[name]
  if (!Original) continue
  const Pinned = function (this: unknown, locales?: unknown, options?: unknown) {
    return new Original(pick(locales), options)
  } as any
  Pinned.prototype = Original.prototype
  Pinned.supportedLocalesOf = Original.supportedLocalesOf
  ;(Intl as any)[name] = Pinned
}
