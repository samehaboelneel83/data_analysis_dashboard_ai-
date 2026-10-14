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

  it('QA4 E0: the shell and the page area are containing blocks, so nothing positioned inside them stretches the document', () => {
    // Home's visually hidden "Actions" header was placed against the document
    // (y≈1557 in a 1080px window) and the whole window scrolled.
    expect(css).toMatch(/\.dl-shell\s*\{[^}]*position:\s*relative/)
    expect(css).toMatch(/\.dl-shell__content\s*\{[^}]*overflow:\s*auto[^}]*position:\s*relative/)
  })
})

describe('dark theme natives (QA V10)', () => {
  it('scrollbars and their corner are dark in the dark theme', () => {
    expect(css).toMatch(/:root\[data-theme="dark"\]\s*\{\s*color-scheme:\s*dark/)
  })
})

describe('top bar at 125% zoom (QA2 V4)', () => {
  // At ~1150–1230 CSS px the page name was still cut ("Datasets > Demo …"):
  // Search (180 px) and the model picker (up to 260 px) are fixed. Below 1280
  // Search is its icon (its aria-label stays) and the picker's name truncates.
  const q = () => css.match(/@media \(max-width: 1279px\)\s*\{([\s\S]*?)\n\}/g)?.find(b => b.includes('llm-picker')) ?? ''
  it('Search gives up its words below 1280 px', () => {
    expect(q()).toMatch(/\.dl-crumbs \+ div \+ button\s*\{[^}]*min-width:\s*0/)
    expect(q()).toMatch(/\.dl-crumbs \+ div \+ button > span:not\(:first-child\)\s*\{[^}]*display:\s*none/)
  })
  it('the model picker narrows', () => {
    expect(q()).toMatch(/\[data-testid="llm-picker"\] > button\s*\{[^}]*max-width:\s*1\d\dpx/)
  })
})

describe('the scrollbar corner (QA2 V10)', () => {
  it('is transparent: custom scrollbars leave it white otherwise, in every theme', () => {
    // color-scheme (QA1) did not reach it: with ::-webkit-scrollbar set, the
    // corner is painted white unless it is styled too.
    expect(css).toMatch(/::-webkit-scrollbar-corner\s*\{[^}]*background:\s*transparent/)
  })
})

describe('chart tooltips in dark mode (QA2 Visual 6)', () => {
  it('the value is in the text colour; the series name keeps its colour as the cue', () => {
    expect(css).toMatch(/\.recharts-tooltip-item-value[^{]*\{[^}]*color:\s*var\(--text\)/)
    expect(css).toMatch(/\.recharts-tooltip-label[^{]*\{[^}]*color:\s*var\(--text\)/)
  })
})


describe('breadcrumb gives way in order, at any zoom (QA3 D1)', () => {
  const rule = (sel: string) => css.match(new RegExp(sel.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '\\s*\\{([^}]*)\\}'))?.[1] ?? ''
  it('the middle link shrinks first, then the section word; both keep a stub', () => {
    expect(rule('.dl-crumbs__section')).toMatch(/flex:\s*0 400 auto/)
    expect(rule('.dl-crumbs__section')).toMatch(/text-overflow:\s*ellipsis/)
    expect(rule('.dl-crumbs > .dl-crumbs__link')).toMatch(/flex-shrink:\s*1000/)
  })
  it('the page name gives way last and keeps a readable minimum (Arabic showed "D.")', () => {
    expect(rule('.dl-crumbs__page')).toMatch(/flex:\s*0 1 auto/)
    // QA4 V8: no cap and no floor -- either cut a crumb with room to spare
    expect(rule('.dl-crumbs__page')).not.toMatch(/max-inline-size/)
    expect(rule('.dl-crumbs__page')).toMatch(/min-inline-size:\s*0/)
  })
})
