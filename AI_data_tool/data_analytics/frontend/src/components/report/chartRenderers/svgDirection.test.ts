/**
 * Structural pin: every Recharts SVG is drawn in physical (ltr) coordinates.
 *
 * SVG `text-anchor` is LOGICAL. Under `<html dir="rtl">` the chart's <svg>
 * inherits `direction: rtl`, and `text-anchor: start` then puts the RIGHT end
 * of the text at the anchor -- so every anchor Recharts and axisOptions emit
 * is mirrored: a right-hand value axis prints its ticks leftward across the
 * plot, and a +30-degree category label trails up-left into the bars. Measured
 * in Chrome: 12 of 12 x ticks and 5 of 5 y ticks over the plot in RTL, with
 * Arabic and with English data alike; zero once the SVG is pinned to ltr.
 *
 * Recharts lays everything out in physical x/y and mirrors nothing itself, so
 * the mirroring this app does (orientation, reversed, insideRight, the +angle
 * ladder) is only correct when the anchors are physical too. The rule lives in
 * index.css because it must cover every Recharts chart, including the ones
 * that never touch axisOptions; jsdom applies no stylesheet, so the file is
 * pinned by content and the geometry is verified in a real browser.
 */
import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const css = fs.readFileSync(path.resolve(here, '../../../index.css'), 'utf8')

describe('Recharts surfaces are pinned to physical text anchoring', () => {
  it('index.css forces direction: ltr on .recharts-surface', () => {
    const rule = css.match(/\.recharts-surface\s*\{[^}]*\}/)
    expect(rule, 'no .recharts-surface rule in index.css').toBeTruthy()
    expect(rule![0]).toMatch(/direction\s*:\s*ltr/)
  })
})
