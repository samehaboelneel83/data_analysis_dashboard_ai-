/**
 * Structural guard on the expression palette.
 *
 * This panel once offered `.str.upper()` and `.dt.year` snippets that the backend's
 * `_validate_expr_safety` rejects outright — it forbids all attribute access by
 * design, so those buttons produced expressions that could never run. The UI
 * advertised functions the engine did not have.
 *
 * Rather than re-list every function name here (which would just drift in a second
 * place), this asserts the structural rule that made those snippets impossible:
 * no snippet may contain attribute access.
 */
import { describe, it, expect } from 'vitest'
import raw from './calcColumns/catalog.ts?raw'

// Pull every `snippet: '...'` / `snippet: "..."` literal out of the source.
const snippets = [...raw.matchAll(/snippet:\s*(['"])((?:\\.|(?!\1).)*)\1/g)].map(m => m[2])

describe('expression palette snippets', () => {
  it('finds snippets to check', () => {
    expect(snippets.length).toBeGreaterThan(30)
  })

  it('contains no attribute access, which the expression validator forbids', () => {
    // A dot followed by an identifier character is attribute access. Decimal numbers
    // (`0.5`) and quoted separators (`"-"`) are not, so only letters/underscore count.
    const offenders = snippets.filter(s => /\.[A-Za-z_]/.test(s))
    expect(offenders, `these can never evaluate: ${offenders.join(', ')}`).toEqual([])
  })

  it('never uses the pandas .str or .dt accessors that caused the original bug', () => {
    expect(snippets.filter(s => s.includes('.str') || s.includes('.dt'))).toEqual([])
  })

  it('offers the text functions the engine now provides', () => {
    const joined = snippets.join(' ')
    for (const fn of ['UPPER(', 'LOWER(', 'TRIM(', 'LEN(', 'SUBSTRING(', 'CONCAT(', 'REPLACE(', 'FIND(', 'CONTAINS(', 'SPLIT(']) {
      expect(joined, `palette is missing ${fn}`).toContain(fn)
    }
  })
})
