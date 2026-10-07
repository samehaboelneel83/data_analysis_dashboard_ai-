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
