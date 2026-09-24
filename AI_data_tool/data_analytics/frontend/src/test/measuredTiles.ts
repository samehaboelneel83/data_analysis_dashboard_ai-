import { afterEach, beforeEach, vi } from 'vitest'

/**
 * Give every element a real-looking box for the tests in the calling block.
 *
 * jsdom does no layout, so `getBoundingClientRect()` is 0×0 everywhere.
 * Charts measure their tile before drawing (`MeasuredChart`, `useMapBox`), and a
 * map correctly draws NOTHING into a tile it has not measured rather than
 * guessing a 16:9 box — so without this, a test that clicks a region waits
 * for a shape that is never drawn and times out, which reads as a click bug.
 */
export function withMeasuredTiles(width = 640, height = 400) {
  beforeEach(() => {
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({
      x: 0, y: 0, top: 0, left: 0, width, height, right: width, bottom: height,
      toJSON: () => ({}),
    } as DOMRect)
  })
  afterEach(() => {
    vi.mocked(HTMLElement.prototype.getBoundingClientRect).mockRestore?.()
  })
}
