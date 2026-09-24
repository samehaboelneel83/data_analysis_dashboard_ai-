import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

/**
 * Every page that renders a search box must actually filter with it.
 *
 * This exists because two of the four wirings silently did not take: the hook
 * was called and `{filter.input}` rendered, so the box appeared and looked
 * functional -- but the list below it still mapped over the UNFILTERED array,
 * so typing did nothing. Nothing failed; the page just quietly ignored the
 * user.
 *
 * That is the same trap this codebase has hit repeatedly -- a control that
 * looks wired and is not -- so it gets a mechanical check rather than trust.
 * A fifth list page added later fails here until it filters too.
 *
 * Source-level on purpose. The alternative is four full page-render tests with
 * their whole API surface mocked, which is far more machinery to assert one
 * structural property that is plainly visible in the source.
 */

const PAGES: {
  file: string; hook: string; collection: string
  /** The page slices the filtered rows before mapping them, so the chain is
   *  `filtered -> rows -> slice -> visible -> map` rather than one expression.
   *  Named here so the check follows the whole chain instead of being
   *  loosened for everybody. */
  paginated?: boolean
  /** The page hands the filtered rows WHOLE to a renderer that arranges them
   *  (Dashboards groups them under folder headings), so the chain is
   *  `filtered -> arrange -> map` and no `.map` touches the hook directly.
   *  The pin follows the hand-off instead of being loosened for everybody. */
  arranged?: boolean
}[] = [
  { file: 'Dashboard.tsx', hook: 'dsFilter', collection: 'datasets', paginated: true },
  { file: 'Reports.tsx', hook: 'repFilter', collection: 'reports', arranged: true },
  { file: 'Connections.tsx', hook: 'srcFilter', collection: 'sources' },
]

const read = (f: string) =>
  fs.readFileSync(path.join(__dirname, f), 'utf8')

describe('every list page filters with the box it renders', () => {
  it.each(PAGES)('$file renders the search box', ({ file, hook }) => {
    expect(read(file)).toContain(`${hook}.input`)
  })

  it.each(PAGES.filter(p => !p.paginated && !p.arranged))(
    '$file maps over the FILTERED rows', ({ file, hook }) => {
      // THE assertion. Without it the box renders, accepts typing, and changes
      // nothing on screen.
      expect(read(file)).toContain(`${hook}.filtered.map`)
    })

  it.each(PAGES.filter(p => p.paginated))(
    '$file pages the FILTERED rows, and maps the page', ({ file, hook }) => {
      // Same guarantee, one link longer. Every step is asserted, so a page
      // that slices the raw collection -- or maps something the filter never
      // touched -- still fails here.
      const src = read(file)
      expect(src, 'the page rows must come from the filter')
        .toContain(`const rows = ${hook}.filtered`)
      expect(src, 'the visible slice must come from those rows')
        .toMatch(/const visible = rows\.slice\(/)
      expect(src, 'and the table must map the slice')
        .toContain('visible.map(')
    })

  it.each(PAGES.filter(p => p.arranged))(
    '$file arranges the FILTERED rows', ({ file, hook }) => {
      // The filtered array is passed whole as the FIRST argument --
      // `arranged(repFilter.filtered, ...)` -- so a page that arranged the raw
      // collection fails the check below, one that never called the arranger
      // fails this one, and `.filtered.filter(...)` (narrowing it first,
      // outside the hook) fails too: the character after `filtered` must
      // close or continue the call, never start a chain.
      expect(read(file)).toMatch(new RegExp('[(]' + hook + '[.]filtered[,)]'))
    })

  it.each(PAGES)('$file no longer maps the raw collection', ({ file, collection }) => {
    // Catches a half-migration that leaves both paths in place -- the filtered
    // list rendered somewhere and the unfiltered one still rendered too.
    const src = read(file)
    expect(src).not.toContain(`{${collection}.map(`)
  })

  it.each(PAGES)('$file says so when a search matches nothing', ({ file, hook }) => {
    // An empty result from a SEARCH is not the same claim as "you have none",
    // and the page's own empty-state copy would be the wrong answer -- the
    // same class of lie as rendering an outage as an empty state.
    expect(read(file)).toContain(`${hook}.noMatches`)
  })
})
