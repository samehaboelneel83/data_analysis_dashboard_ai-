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

  // C-12 round 2: centred at the top, the toolbar still sat on the tile's own
  // title. It sits at the header's end, and the header makes room for it
  // while it shows, so the title truncates instead of being covered.
  it.each([['View', '.dl-vw-wt'], ['Edit', '.dl-bd-wt']])('%s: the toolbar sits at the header end, not over the centre', (_m, sel) => {
    const decl = rule(sel === '.dl-vw-wt' ? viewCss : builderCss, sel)
    expect(decl).toMatch(/inset-inline-end:\s*\d+px/)
    expect(decl).not.toMatch(/left:\s*50%/)
  })
  it.each([['View', '.dl-vw-wt'], ['Edit', '.dl-bd-wt']])('%s: the header reserves the toolbar width while it shows', (_m, sel) => {
    const css = sel === '.dl-vw-wt' ? viewCss : builderCss
    const m = new RegExp(`:has\\(> \\${sel}\\):hover \\.dl-whead[^{]*\\{([^}]*)\\}`).exec(css)
    expect(m?.[1] ?? '').toMatch(/padding-inline-end:\s*\d+px/)
  })
})
