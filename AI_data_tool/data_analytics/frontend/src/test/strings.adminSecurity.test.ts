import { describe, it, expect } from 'vitest'
import path from 'node:path'
import { hardcodedStrings } from './hardcodedStrings'

/** 8-i18n: no hard-coded English in the adminSecurity area (see builderStrings.test.ts). */
const FILES: string[] = [
  'pages/admin/AdminRowSecurityRules.tsx',
  'pages/admin/AdminColumnSecurityRules.tsx',
  'pages/admin/ConnectionRowPolicies.tsx',
  'pages/admin/AdminRoles.tsx',
  'pages/admin/AdminAudit.tsx',
  'pages/admin/AdminUsers.tsx',
  'pages/admin/AdminExportPolicy.tsx',
]

describe('no hard-coded English: adminSecurity (8-i18n)', () => {
  it.each(FILES.length ? FILES : ['(none yet)'])('%s', f => {
    if (f === '(none yet)') return
    expect(hardcodedStrings(path.join(__dirname, '..', f)).map(h => `${f}:${h.line} ${h.text}`)).toEqual([])
  })
})
