import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

/** QA2 N4: in Arabic the reading toolbar (Ask AI, Focus) sat on the widget's
 *  own ⋮ menu, both at the inline-end corner, so a click on Focus opened the
 *  chart menu. It is centred on the top edge now, clear of either corner. */
const css = fs.readFileSync(path.join(__dirname, 'viewMode.css'), 'utf8')

describe('reading toolbar placement (QA2 N4)', () => {
  it('is centred on the top edge, not in a corner where the widget keeps its menu', () => {
    const r = css.match(/\.dl-vw-wt\s*\{([^}]*)\}/)?.[1] ?? ''
    expect(r).toMatch(/left:\s*50%/)
    expect(r).toMatch(/translateX\(-50%\)/)
    expect(r).not.toMatch(/inset-inline-end/)
  })
})
