import { describe, it, expect } from 'vitest'
import path from 'node:path'
import { hardcodedStrings } from './hardcodedStrings'

/** 8-i18n: no hard-coded English in the adminPlatform area (see builderStrings.test.ts). */
const FILES: string[] = [
  'pages/admin/PlatformOrgs.tsx',
  'pages/admin/AdminOrgUnits.tsx',
  'pages/admin/AdminSso.tsx',
  'pages/admin/ApiKeys.tsx',
  'pages/admin/AdminCustomConnectors.tsx',
  'pages/admin/AdminMaps.tsx',
  'pages/admin/Settings.tsx',
  'components/admin/BasemapSettings.tsx',
  'components/admin/LlmEndpointsPanel.tsx',
]

describe('no hard-coded English: adminPlatform (8-i18n)', () => {
  it.each(FILES.length ? FILES : ['(none yet)'])('%s', f => {
    if (f === '(none yet)') return
    expect(hardcodedStrings(path.join(__dirname, '..', f)).map(h => `${f}:${h.line} ${h.text}`)).toEqual([])
  })
})
