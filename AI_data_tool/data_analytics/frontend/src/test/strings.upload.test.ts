import { describe, it, expect } from 'vitest'
import path from 'node:path'
import { hardcodedStrings } from './hardcodedStrings'
import { en, ar } from '../i18n/pages/upload'

/** Autopilot step 5: no hard-coded English on the Upload page. */
describe('no hard-coded English: Upload', () => {
  it('pages/Upload.tsx', () => {
    expect(hardcodedStrings(path.join(__dirname, '..', 'pages/Upload.tsx')).map(h => `${h.line} ${h.text}`)).toEqual([])
  })
  it('holds the same keys and placeholders in both languages', () => {
    expect(Object.keys(ar).sort()).toEqual(Object.keys(en).sort())
    const names = (s: string) => [...new Set([...s.matchAll(/\{(\w+)/g)].map(m => m[1]))].sort().join()
    expect((Object.keys(en) as (keyof typeof en)[]).filter(k => names(en[k]) !== names(ar[k]))).toEqual([])
  })
})
