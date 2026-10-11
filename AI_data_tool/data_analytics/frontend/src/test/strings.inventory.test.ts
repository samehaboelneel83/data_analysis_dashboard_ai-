import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import { hardcodedStrings } from './hardcodedStrings'

/**
 * The whole app's hard-coded English, as a number per file that may only go
 * DOWN (docs/i18n/INVENTORY.md).
 *
 * The per-area tests beside this one (builderStrings, strings.*) each hold a
 * list of files that are fully translated. This one covers every other
 * screen: `i18nBaseline.json` records how many reader-visible English
 * literals each file still has. A file may not exceed its number, and a file
 * not listed must have none -- so new screens are born translated, and a
 * migrated file cannot slide back.
 *
 * To record progress after translating a file (or to accept a new count
 * deliberately), regenerate the baseline:
 *
 *     UPDATE_I18N_BASELINE=1 npx vitest run src/test/strings.inventory.test.ts
 *
 * Configurable in the baseline file itself:
 *   "ignore": folders or files never scanned (tests and fixtures always are)
 *   "files":  { "<path under src>": <literals still in English> }
 */
const SRC = path.join(__dirname, '..')
const BASELINE = path.join(__dirname, 'i18nBaseline.json')

interface Baseline { ignore: string[]; files: Record<string, number> }

function walk(dir: string, out: string[] = []): string[] {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) walk(full, out)
    else if (/\.tsx$/.test(entry.name) && !/\.test\.tsx$/.test(entry.name)) out.push(full)
  }
  return out
}

function scan(ignore: string[]): Record<string, number> {
  const counts: Record<string, number> = {}
  for (const file of walk(SRC)) {
    const rel = path.relative(SRC, file).split(path.sep).join('/')
    if (rel.startsWith('test/') || ignore.some(i => rel === i || rel.startsWith(i.replace(/\/?$/, '/')))) continue
    const n = hardcodedStrings(file).length
    if (n) counts[rel] = n
  }
  return counts
}

const read = (): Baseline => fs.existsSync(BASELINE)
  ? JSON.parse(fs.readFileSync(BASELINE, 'utf8')) : { ignore: [], files: {} }

describe('hard-coded English may only go down', () => {
  const baseline = read()
  const now = scan(baseline.ignore ?? [])

  if (process.env.UPDATE_I18N_BASELINE) {
    it('records the inventory', () => {
      const files = Object.fromEntries(Object.entries(now).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])))
      fs.writeFileSync(BASELINE, JSON.stringify({ ignore: baseline.ignore ?? [], files }, null, 2) + '\n')
      expect(Object.keys(files).length).toBeGreaterThanOrEqual(0)
    })
    return
  }

  it('no file has more English than its recorded number', () => {
    const worse = Object.entries(now)
      .filter(([file, n]) => n > (baseline.files[file] ?? 0))
      .map(([file, n]) => `${file}: ${n} (recorded ${baseline.files[file] ?? 0})`)
    expect(worse).toEqual([])
  })

  it('a file that was translated is taken off the list', () => {
    // Keeps the inventory honest: a number that is too high hides a slide back.
    const stale = Object.entries(baseline.files)
      .filter(([file, n]) => (now[file] ?? 0) < n)
      .map(([file, n]) => `${file}: now ${now[file] ?? 0}, recorded ${n} -- regenerate the baseline`)
    expect(stale).toEqual([])
  })
})
