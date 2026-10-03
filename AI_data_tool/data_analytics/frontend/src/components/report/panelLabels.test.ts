import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { PANEL_AR, panelLabel } from './panelLabels'

const SOURCE = readFileSync(resolve(__dirname, 'WidgetConfigPanel.tsx'), 'utf8')

/** Every English label the panel shows through L(), fld() or its tabs. */
function labels(): string[] {
  const found = new Set<string>()
  const lit = String.raw`("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')`
  for (const re of [new RegExp(String.raw`\bL\(` + lit, 'g'), new RegExp(String.raw`\bfld\(` + lit, 'g')]) {
    for (const m of SOURCE.matchAll(re)) found.add(m[1].startsWith('"') ? JSON.parse(m[1]) : m[1].slice(1, -1).replace(/\\'/g, "'"))
  }
  // Placeholders handed to sel(): every "— … —" choice line.
  for (const m of SOURCE.matchAll(/'(— [^']+ —)'/g)) found.add(m[1])
  const tabs = /const SETTINGS_TABS = \[([^\]]*)\]/.exec(SOURCE)
  for (const m of (tabs?.[1] ?? '').matchAll(/'([^']+)'/g)) found.add(m[1])
  return [...found]
}

describe('widget settings panel in Arabic', () => {
  it('finds the panel labels it checks', () => {
    expect(labels().length).toBeGreaterThan(250)
  })

  it('has an Arabic entry for every label the panel shows', () => {
    const missing = labels().filter(l => !(l in PANEL_AR))
    expect(missing).toEqual([])
  })

  it('keeps every placeholder in the translation', () => {
    const bad = Object.entries(PANEL_AR).filter(([en, ar]) =>
      (en.match(/\{\w+\}/g) ?? []).sort().join() !== (ar.match(/\{\w+\}/g) ?? []).sort().join())
    expect(bad).toEqual([])
  })

  it('translates and fills, and leaves English and unknown text alone', () => {
    expect(panelLabel('ar', '{type} settings', { type: panelLabel('ar', 'Line') })).toBe('إعدادات خط')
    expect(panelLabel('en', 'Show legend')).toBe('Show legend')
    expect(panelLabel('ar', 'region')).toBe('region')
  })
})

describe('aggregation names', () => {
  it('has Arabic for every aggregation and group the panel lists', async () => {
    const { AGGREGATIONS } = await import('../../types/report')
    const missing = AGGREGATIONS.flatMap(a => [a.label, a.group]).filter(l => !(l in PANEL_AR))
    expect([...new Set(missing)]).toEqual([])
  })
})
