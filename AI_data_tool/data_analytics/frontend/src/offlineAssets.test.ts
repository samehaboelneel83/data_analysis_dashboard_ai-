/**
 * Offline-readiness regression pin (Tier-4 Task O1).
 *
 * Production runs with NO internet access. Any string in the frontend
 * source (or index.html) that points at a public CDN — Google Fonts,
 * unpkg, jsdelivr, cdnjs, or a bare "cdn." host — would silently break
 * at runtime in an isolated network (fonts not loading, scripts 404ing)
 * with no obvious error. This walks the real source tree and index.html
 * and fails loudly if any such reference reappears.
 */
import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const frontendRoot = path.resolve(here, '..')
const srcRoot = path.join(frontendRoot, 'src')

const FORBIDDEN = /fonts\.googleapis|fonts\.gstatic|cdn\.|unpkg|jsdelivr|cdnjs/i

// Binary/asset extensions we don't need to text-scan.
const SKIP_EXT = new Set([
  '.woff2', '.woff', '.ttf', '.otf', '.png', '.jpg', '.jpeg', '.gif', '.ico',
  '.webp', '.svg', '.mp4', '.pdf',
])

const SELF = path.basename(fileURLToPath(import.meta.url))

function walk(dir: string, out: string[] = []): string[] {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === 'node_modules') continue
    if (entry.name === SELF) continue // this file names the forbidden strings itself
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) {
      walk(full, out)
    } else if (!SKIP_EXT.has(path.extname(entry.name).toLowerCase())) {
      out.push(full)
    }
  }
  return out
}

describe('offline readiness: no public CDN references', () => {
  it('frontend/src contains no fonts.googleapis/cdn./unpkg/jsdelivr/cdnjs strings', () => {
    const offenders: string[] = []
    for (const file of walk(srcRoot)) {
      const text = fs.readFileSync(file, 'utf8')
      if (FORBIDDEN.test(text)) {
        offenders.push(path.relative(frontendRoot, file))
      }
    }
    expect(offenders, `forbidden CDN reference(s) found in: ${offenders.join(', ')}`).toEqual([])
  })

  it('frontend/index.html contains no fonts.googleapis/cdn./unpkg/jsdelivr/cdnjs strings', () => {
    const indexPath = path.join(frontendRoot, 'index.html')
    const text = fs.readFileSync(indexPath, 'utf8')
    expect(FORBIDDEN.test(text)).toBe(false)
  })
})
