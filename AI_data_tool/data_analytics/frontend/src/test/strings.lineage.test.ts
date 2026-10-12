import { describe, it, expect } from 'vitest'
import path from 'node:path'
import { hardcodedStrings } from './hardcodedStrings'
import { en, ar } from '../i18n/pages/lineage'

/** Step 11: no hard-coded English on the Lineage explorer. */
const FILES = ['pages/Lineage.tsx', 'pages/lineage/Graph.tsx', 'pages/lineage/FilterChip.tsx']

describe('no hard-coded English: Lineage (step 11)', () => {
  it.each(FILES)('%s', f => {
    expect(hardcodedStrings(path.join(__dirname, '..', f)).map(h => `${f}:${h.line} ${h.text}`)).toEqual([])
  })
  it('holds the same keys and placeholders in both languages', () => {
    expect(Object.keys(ar).sort()).toEqual(Object.keys(en).sort())
    const names = (s: string) => [...new Set([...s.matchAll(/\{(\w+)/g)].map(m => m[1]))].sort().join()
    expect((Object.keys(en) as (keyof typeof en)[]).filter(k => names(en[k]) !== names(ar[k]))).toEqual([])
  })
})
