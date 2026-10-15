import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const viewCss = fs.readFileSync(path.resolve(here, 'viewMode.css'), 'utf8')
const builderCss = fs.readFileSync(path.resolve(here, 'builder.css'), 'utf8')

/** C-12: the hover toolbars sat ABOVE their tile (top: -18px / -22px), over the
 *  title of the tile above, and a click on "empty canvas" hit Duplicate. */
function rule(css: string, selector: string): string {
  const m = new RegExp(`(^|\\n)\\s*${selector.replace('.', '\\.')}\\s*\\{([^}]*)\\}`).exec(css)
  return m?.[2] ?? ''
}
const topOf = (decl: string) => Number(/(?:^|;|\s)top:\s*(-?\d+)px/.exec(decl)?.[1] ?? NaN)

describe('hover toolbars stay inside their own tile', () => {

  it('View: .dl-vw-wt sits inside the tile', () => {
    expect(topOf(rule(viewCss, '.dl-vw-wt'))).toBeGreaterThanOrEqual(0)
  })
  it('Edit: .dl-bd-wt sits inside the tile', () => {
    expect(topOf(rule(builderCss, '.dl-bd-wt'))).toBeGreaterThanOrEqual(0)
  })
  it('the buttons are not armed the instant the pointer passes over', () => {
    expect(rule(viewCss, '.dl-vw-wt')).toMatch(/visibility/)
    expect(rule(builderCss, '.dl-bd-wt')).toMatch(/visibility/)
  })
})
