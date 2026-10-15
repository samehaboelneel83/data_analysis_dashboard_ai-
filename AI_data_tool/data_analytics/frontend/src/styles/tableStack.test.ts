import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

/** AD-20: on a phone the Monitoring tables become cards -- one per row, each
 *  cell with its column name -- instead of a 560 px table scrolled sideways.
 *  jsdom applies no stylesheet, so the rule is pinned (home/layout.test.ts). */
const css = fs.readFileSync(path.join(__dirname, '..', 'index.css'), 'utf8')

describe('.dl-table--stack (AD-20)', () => {
  const block = /@media \(max-width: 600px\)\s*\{([\s\S]*?\.dl-table--stack[\s\S]*?)\n\}/.exec(css)?.[1] ?? ''

  it('turns each row into a card under 600 px', () => {
    expect(block).toMatch(/\.dl-table--stack tr\s*\{[^}]*display:\s*block/)
    expect(block).toMatch(/\.dl-table--stack thead\s*\{[^}]*(display:\s*none|clip)/)
  })

  it('names each cell with its column, from data-label', () => {
    expect(block).toMatch(/\.dl-table--stack td\[data-label\]::before\s*\{[^}]*content:\s*attr\(data-label\)/)
  })

  it('drops the 560 px minimum so nothing scrolls sideways', () => {
    expect(block).toMatch(/\.dl-table--stack\s*\{[^}]*min-inline-size:\s*0/)
  })
})
