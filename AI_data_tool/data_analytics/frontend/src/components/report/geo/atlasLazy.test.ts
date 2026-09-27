/**
 * The bundled world atlas (~740 kB raw) must only load with a map.
 *
 * worldGeometry.ts imports world-atlas/countries-50m.json. Every map renderer is
 * React.lazy for exactly that reason, but one static import anywhere on the path
 * from a page to worldGeometry puts the atlas back into that page's chunk. That
 * happened: GeoContourRenderer was imported statically in chartRenderers/index,
 * which put the atlas into the WidgetRenderer chunk (950 kB), and the report
 * builder pulled it in through the geography check. Nothing failed; every
 * dashboard, share link and embed simply downloaded it.
 *
 * This walks the STATIC import graph (dynamic `import()` is the escape hatch)
 * from the pages that render widgets and fails with the offending chain.
 */
import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const srcRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..')
const ATLAS = path.join(srcRoot, 'components/report/geo/worldGeometry.ts')

// `import x from './a'`, `import './a'`, `export { x } from './a'` -- but not
// `import type` / `export type`, which the compiler erases.
const STATIC_IMPORT = /^\s*(?:import|export)\s+(?!type\b)(?:[\s\S]*?\sfrom\s+)?['"](\.{1,2}\/[^'"]+)['"]/gm

function resolve(from: string, spec: string): string | null {
  const base = path.resolve(path.dirname(from), spec)
  for (const c of [base, `${base}.ts`, `${base}.tsx`, path.join(base, 'index.ts'), path.join(base, 'index.tsx')]) {
    if (fs.existsSync(c) && fs.statSync(c).isFile()) return c
  }
  return null
}

/** The import chain from `entry` to the atlas, or null when there is none. */
function chainToAtlas(entry: string): string[] | null {
  const parent = new Map<string, string | null>([[entry, null]])
  const queue = [entry]
  while (queue.length) {
    const file = queue.shift()!
    if (file === ATLAS) {
      const chain: string[] = []
      for (let f: string | null = file; f; f = parent.get(f) ?? null) chain.unshift(path.relative(srcRoot, f))
      return chain
    }
    if (!/\.tsx?$/.test(file)) continue
    const text = fs.readFileSync(file, 'utf8')
    for (const m of text.matchAll(STATIC_IMPORT)) {
      const dep = resolve(file, m[1])
      if (dep && !parent.has(dep)) { parent.set(dep, file); queue.push(dep) }
    }
  }
  return null
}

describe('world atlas stays out of non-map chunks', () => {
  it.each([
    'components/report/WidgetRenderer.tsx',
    'components/report/WidgetConfigPanel.tsx',
    'pages/ReportBuilder.tsx',
    'pages/SharedReport.tsx',
    'pages/EmbeddedReport.tsx',
  ])('%s reaches worldGeometry only through a lazy import', entry => {
    expect(chainToAtlas(path.join(srcRoot, entry))).toBeNull()
  })

  it('the walker does find the atlas when it is imported statically', () => {
    // Guards the guard: a map renderer imports it directly.
    const chain = chainToAtlas(path.join(srcRoot, 'components/report/chartRenderers/GeoContourRenderer.tsx'))
    expect(chain?.at(-1)).toBe('components/report/geo/worldGeometry.ts')
  })
})
