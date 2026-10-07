import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

/**
 * QA V1–V3 (7-QA) on the Dashboards list. jsdom applies no stylesheet, so
 * these pin the rules themselves.
 *  V1: five columns in percentages all shrank together on a narrow main area,
 *      leaving the name "Use c…". The small columns now have fixed widths, so
 *      the name takes whatever is left; on a narrow table the folder column
 *      gives way and the folder moves under the name.
 *  V2: the bulk bar's count wrapped onto three lines.
 *  V3: the browser's own clear button showed beside ours.
 */
const css = fs.readFileSync(path.join(__dirname, 'dashboards.css'), 'utf8')
const rule = (sel: string) => css.match(new RegExp(sel.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '\\s*\\{([^}]*)\\}'))?.[1] ?? ''

describe('Dashboards list layout (QA V1–V3)', () => {
  it('the name column takes the room the others leave: they are fixed, it is not', () => {
    for (const c of ['c-fd', 'c-ds', 'c-st', 'c-mod']) expect(rule(`.dsh-tbl .${c}`), c).toMatch(/width:\s*\d+px/)
    expect(rule('.dsh-tbl .c-nm')).not.toMatch(/width:/)
  })

  it('on a narrow table the folder column gives way and shows under the name', () => {
    expect(rule('.dsh-tblw')).toMatch(/container-type:\s*inline-size/)
    const q = css.match(/@container dshtbl \(max-width: 960px\)\s*\{([\s\S]*?)\n\}/)
    expect(q, 'no container query for the narrow table').toBeTruthy()
    // Collapsed, not removed: a removed column leaves the colSpan-7 group
    // rows a phantom column that soaks up the name's room.
    expect(q![1]).toMatch(/\.dsh-tbl \.c-fd\s*\{[^}]*width:\s*0/)
    expect(q![1]).toMatch(/\.dsh-tbl \.c-fd > \*\s*\{[^}]*display:\s*none/)
    expect(q![1]).toMatch(/\.dsh-nmc \.fdi\s*\{[^}]*display:/)
  })

  it('the table scrolls sideways before the name column collapses', () => {
    expect(rule('.dsh-tblw > .dsh-tbl')).toMatch(/min-inline-size:\s*\d+px/)
    expect(rule('.dsh-tblw')).toMatch(/overflow-x:\s*auto/)
  })

  it('the bulk bar never breaks a label; the bar wraps instead', () => {
    expect(rule('.dsh-bulk')).toMatch(/flex-wrap:\s*wrap/)
    expect(rule('.dsh-bulk > *')).toMatch(/white-space:\s*nowrap/)
  })

  it("the browser's own clear button is hidden: the box has one", () => {
    expect(css).toMatch(/\.dsh-srch input\[type="search"\]::-webkit-search-cancel-button\s*\{[^}]*display:\s*none/)
  })

  it('narrower still (QA2 V1, 125% zoom: a 606 px box), Status folds into the name cell and the table fits without scrolling', () => {
    const q = css.match(/@container dshtbl \(max-width: 719px\)\s*\{([\s\S]*?)\n\}/)
    expect(q, 'no second narrow step').toBeTruthy()
    expect(q![1]).toMatch(/\.dsh-tbl \.c-st\s*\{[^}]*width:\s*0/)
    expect(q![1]).toMatch(/\.dsh-nmc \.sti\s*\{[^}]*display:/)
    const min = Number(rule('.dsh-tblw > .dsh-tbl').match(/min-inline-size:\s*(\d+)px/)?.[1])
    expect(min).toBeLessThanOrEqual(560)
  })
})

