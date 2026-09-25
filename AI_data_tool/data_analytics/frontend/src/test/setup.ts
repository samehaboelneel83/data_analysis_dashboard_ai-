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
