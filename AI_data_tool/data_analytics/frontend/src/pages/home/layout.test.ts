import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

/** QA V10 (7-QA): the quick actions' subtitles clipped to "Start from a bl…"
 *  on a narrower window. jsdom applies no stylesheet, so the rule is pinned. */
const css = fs.readFileSync(path.join(__dirname, 'home.css'), 'utf8')

describe('Home quick actions (QA V10)', () => {
  it('a subtitle wraps to two lines instead of clipping to one', () => {
    const r = css.match(/\.hm-qa small\s*\{([^}]*)\}/)?.[1] ?? ''
    expect(r).not.toMatch(/white-space:\s*nowrap/)
    expect(r).toMatch(/line-clamp:\s*2/)
  })
})

describe('Home stat cards on a phone (AD-15)', () => {
  it('lay out 2 x 2 under 600 px, after the 4-across rule for 1100 px', () => {
    const at1100 = css.indexOf('@media (max-width: 1100px)')
    const m = /@media \(max-width: 600px\)\s*\{[^@]*?\.hm-stats\s*\{([^}]*)\}/.exec(css)
    expect(m?.[1] ?? '').toMatch(/grid-template-columns:\s*repeat\(2,/)
    expect(m!.index).toBeGreaterThan(at1100)
  })

  it('a stat subtitle wraps to two lines instead of clipping', () => {
    const r = css.match(/\.hm-st \.s > span:last-child\s*\{([^}]*)\}/)?.[1] ?? ''
    expect(r).not.toMatch(/white-space:\s*nowrap/)
    expect(r).toMatch(/line-clamp:\s*2/)
  })
})
