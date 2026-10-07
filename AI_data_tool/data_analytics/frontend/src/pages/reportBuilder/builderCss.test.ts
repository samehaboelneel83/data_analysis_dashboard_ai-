import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

/** QA3 Batch B rules that are CSS only. */
const read = (p: string) => fs.readFileSync(path.join(__dirname, p), 'utf8')
const builder = read('builder.css')
const index = read('../../index.css')
const main = read('../../main.tsx')
const rule = (css: string, sel: string) => css.match(new RegExp(sel.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '\\s*\\{([^}]*)\\}'))?.[1] ?? ''

describe('builder CSS (QA3 Batch B)', () => {
  it('B3: the save state has a fixed width and keeps undo/redo beside it', () => {
    expect(rule(builder, '.dl-bd-save')).toMatch(/width:\s*\d+px/)
    expect(rule(builder, '.dl-bd-save > .tx')).toMatch(/text-overflow:\s*ellipsis/)
    expect(rule(builder, '.dl-bd-saveundo')).toMatch(/white-space:\s*nowrap/)
  })

  it('B3: the sensitivity select has a fixed width that no narrow-header rule caps', () => {
    expect(rule(builder, '.dl-bd-sel')).toMatch(/width:\s*124px/)
    expect(builder).not.toMatch(/\.dl-bd-sel\s*\{\s*max-width/)
  })

  it('B4: the header controls paint on the widget colour and join the row when selected', () => {
    expect(rule(index, '.dl-whead__ctl')).toContain('var(--dl-wbg, var(--surface))')
    expect(index).toMatch(/\.dl-widget--selected \.dl-whead__ctl,\s*\.dl-whead:focus-within \.dl-whead__ctl\s*\{[^}]*position:\s*static/)
    expect(rule(index, '.dl-whead > .dl-whead__title')).toMatch(/min-width:\s*min\(/)
    expect(index).not.toMatch(/padding-inline-end:\s*84px/)
    expect(rule(index, '.dl-widget--selected .dl-wmark')).toMatch(/display:\s*none/)
    expect(index).toMatch(/@container dlwidget \(max-width: 260px\)\s*\{\s*\.dl-widget--selected \.dl-wdel\s*\{\s*display:\s*none/)
  })

  it('B6: toasts sit above the status bar', () => {
    expect(main).toContain("containerStyle={{ bottom: 'var(--dl-toast-bottom, 16px)' }}")
    expect(rule(index, ':root:has(.dl-statusbar)')).toMatch(/--dl-toast-bottom:\s*\d+px/)
  })
})
