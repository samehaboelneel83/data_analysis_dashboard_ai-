import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

/**
 * QA V4 (7-QA): on a narrower window the breadcrumb shrank to "Dashboards > Q",
 * because the controls on the right of the top bar are fixed and the trail is
 * what gives. CSS only (TopBar.tsx untouched): below 1360 px the muted section
 * word in front ("Analyse ›") gives way first, so the page's own name keeps
 * the room. jsdom applies no stylesheet, so the rule itself is pinned.
 */
const css = fs.readFileSync(path.join(__dirname, '..', 'index.css'), 'utf8')

describe('top bar breadcrumb (QA V4)', () => {
  it('on a narrower window the leading section word gives way, not the page name', () => {
    const q = css.match(/@media \(max-width: 1360px\)\s*\{([\s\S]*?)\n\}/g)?.find(b => b.includes('dl-crumbs'))
    expect(q, 'no narrow-window rule for the breadcrumb').toBeTruthy()
    expect(q!).toMatch(/\.dl-crumbs > \.dl-crumbs__section:first-child:not\(\.dl-crumbs__link\)/)
    expect(q!).toMatch(/display:\s*none/)
  })
})

describe('app shell (QA V5)', () => {
  it('the shell clips rather than hides, so nothing can scroll it', () => {
    expect(css).toMatch(/\.dl-shell\s*\{[^}]*overflow:\s*clip/)
  })
})

describe('dark theme natives (QA V10)', () => {
  it('scrollbars and their corner are dark in the dark theme', () => {
    expect(css).toMatch(/:root\[data-theme="dark"\]\s*\{\s*color-scheme:\s*dark/)
  })
})
