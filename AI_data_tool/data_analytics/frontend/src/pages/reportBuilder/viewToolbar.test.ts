import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

/** QA2 N4: in Arabic the reading toolbar (Ask AI, Focus) sat on the widget's
 *  own ⋮ menu, both at the inline-end corner, so a click on Focus opened the
 *  chart menu. It was then centred on the top edge -- where it covered the
 *  tile's own title (C-12). C-12 round 2: it sits at the inline-end corner
 *  again, and the header reserves its width while it shows, so the header's
 *  own icons (the ⋮ menu among them) move inward, clear of it. */
const css = fs.readFileSync(path.join(__dirname, 'viewMode.css'), 'utf8')

describe('reading toolbar placement (QA2 N4, C-12)', () => {
  it('sits at the inline-end corner, and the header makes room so the ⋮ menu is never under it', () => {
    const r = css.match(/\.dl-vw-wt\s*\{([^}]*)\}/)?.[1] ?? ''
    expect(r).toMatch(/inset-inline-end/)
    expect(r).not.toMatch(/left:\s*50%/)
    expect(css).toMatch(/:has\(> \.dl-vw-wt\):hover \.dl-whead[^{]*\{[^}]*padding-inline-end:\s*\d+px/)
  })
})
