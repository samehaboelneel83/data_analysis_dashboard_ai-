import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

/**
 * QA B1 (7-QA): at 1180–1280 px the Datasets table sat beside the 300 px
 * preview with less room than its fixed columns need (658 px), so the Name
 * column was 0 px wide. jsdom applies no stylesheet, so the fix is pinned by
 * the rule itself: the page is a container, and below 1100 px of it the
 * preview stacks under the table, leaving the table the full width.
 */
const css = fs.readFileSync(path.join(__dirname, 'datasetsList.css'), 'utf8')

describe('Datasets list layout (QA B1)', () => {
  it('the page is a size container', () => {
    expect(css).toMatch(/\.dl-dsl\s*\{[^}]*container-type:\s*inline-size/)
  })

  it('below 1100 px of page the preview stacks under the table', () => {
    const q = css.match(/@container dsl \(max-width: 1100px\)\s*\{([\s\S]*?)\n\}/)
    expect(q, 'no container query for the stacked layout').toBeTruthy()
    expect(q![1]).toMatch(/\.dl-dsl__body\s*\{\s*grid-template-columns:\s*minmax\(0, 1fr\)/)
  })

  it('the name column never collapses: the table keeps room for it and scrolls before it squeezes', () => {
    expect(css).toMatch(/\.dl-dsl__table\s*\{[^}]*min-inline-size:\s*\d+px/)
  })
})
