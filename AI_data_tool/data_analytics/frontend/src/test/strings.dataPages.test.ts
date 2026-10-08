import { describe, it, expect } from 'vitest'
import path from 'node:path'
import { hardcodedStrings } from './hardcodedStrings'

/** 8-i18n: no hard-coded English in the dataPages area (see builderStrings.test.ts). */
const FILES: string[] = [
  'pages/Connections.tsx',
  'pages/connections/ConnectionModal.tsx',
  'pages/connections/CombineDialog.tsx',
  'pages/SourceReview.tsx',
  'pages/sourceReview/ReviewPanels.tsx',
  'components/review/SourceOverview.tsx',
  'pages/Glossary.tsx',
  'components/review/GlossaryPanel.tsx',
  'pages/monitoring/MonitoringActivity.tsx',
  'pages/monitoring/MonitoringJobs.tsx',
  'pages/monitoring/MonitoringDeliveries.tsx',
  'pages/reports/listParts.tsx',
  'pages/home/DashboardsSection.tsx',
]

describe('no hard-coded English: dataPages (8-i18n)', () => {
  it.each(FILES.length ? FILES : ['(none yet)'])('%s', f => {
    if (f === '(none yet)') return
    expect(hardcodedStrings(path.join(__dirname, '..', f)).map(h => `${f}:${h.line} ${h.text}`)).toEqual([])
  })
})
