import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

/**
 * Every full-screen overlay must be a real dialog.
 *
 * This test exists because of how the FIRST pass at modal accessibility missed
 * six modals. That pass found its targets by grepping for `role="dialog"` and
 * adding what was missing around them -- a method that structurally cannot find
 * a modal which never had a role at all. The six it missed were the admin
 * screens: user management, roles, row-security rules, connections. Exactly the
 * screens where being unable to escape matters most.
 *
 * So this searches by the thing an overlay cannot fake: the CSS that makes it
 * cover the viewport. Anything painting `position: fixed; inset: 0` is a
 * modal layer, whatever else it does or does not declare, and it must carry a
 * dialog role and use the shared hook that supplies Escape, the focus trap and
 * focus restoration.
 */

const SRC = path.resolve(__dirname, '../..')

/** `position: fixed` with `inset: 0` — the signature of a viewport overlay. */
const OVERLAY = /position:\s*['"]?fixed['"]?[^}]*inset:\s*0/

/** Files whose overlay implements the mechanics itself, verified by its own
 *  tests. Listed explicitly so adding one is a decision, not an oversight. */
const OWN_IMPLEMENTATION = new Set([
  // The original, and the source the shared hook was extracted from. Covered by
  // ConfirmDialog.test.tsx.
  'components/ui/ConfirmDialog.tsx',
])

function walk(dir: string, out: string[] = []): string[] {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, entry.name)
    if (entry.isDirectory()) {
      if (entry.name !== 'node_modules') walk(p, out)
    } else if (entry.name.endsWith('.tsx') && !entry.name.includes('.test.')) {
      out.push(p)
    }
  }
  return out
}

/** Files containing at least one viewport overlay. */
function filesWithOverlays(): { rel: string; src: string; lines: number[] }[] {
  return walk(SRC)
    .map(file => {
      const src = fs.readFileSync(file, 'utf8')
      const lines = src.split('\n')
        .map((l, i) => (OVERLAY.test(l) ? i + 1 : 0))
        .filter(Boolean)
      return { rel: path.relative(SRC, file).replace(/\\/g, '/'), src, lines }
    })
    .filter(f => f.lines.length > 0)
}

describe('every viewport overlay is an escapable dialog', () => {
  it('finds overlays to check', () => {
    // Guard the guard: if the CSS signature stops matching, every assertion
    // below would pass by checking an empty list.
    expect(filesWithOverlays().length).toBeGreaterThan(8)
  })

  it('declares a dialog role', () => {
    // Without a role the overlay is an anonymous div: assistive technology
    // announces nothing, and nothing marks the page behind it as inert.
    const missing = filesWithOverlays()
      .filter(f => !OWN_IMPLEMENTATION.has(f.rel))
      .filter(f => !/role="(dialog|alertdialog)"/.test(f.src))
      .map(f => `${f.rel}:${f.lines.join(',')}`)
    expect(missing).toEqual([])
  })

  it('uses the shared hook for Escape, focus trap and focus restore', () => {
    // THE assertion. A role alone still leaves a keyboard user unable to get
    // out: Tab walks behind the scrim they cannot see, and Escape does nothing.
    const missing = filesWithOverlays()
      .filter(f => !OWN_IMPLEMENTATION.has(f.rel))
      .filter(f => !f.src.includes('useModalDialog'))
      .map(f => `${f.rel}:${f.lines.join(',')}`)
    expect(missing).toEqual([])
  })

  it('puts the role on the panel, not on the backdrop', () => {
    // The scrim behind a dialog is not the dialog. Marking the backdrop makes
    // the accessible name cover the whole viewport and puts the page's own
    // content inside the dialog's boundary.
    const offenders: string[] = []
    for (const f of filesWithOverlays()) {
      if (OWN_IMPLEMENTATION.has(f.rel)) continue
      const lines = f.src.split('\n')
      for (const n of f.lines) {
        // The overlay's own element starts at most a couple of lines above the
        // matched style; a role there means the backdrop claimed it.
        const head = lines.slice(Math.max(0, n - 4), n).join('\n')
        if (/role="(dialog|alertdialog)"/.test(head)) {
          offenders.push(`${f.rel}:${n}`)
        }
      }
    }
    expect(offenders).toEqual([])
  })
})
