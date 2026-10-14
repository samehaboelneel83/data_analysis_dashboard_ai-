import { describe, it, expect } from 'vitest'
import path from 'node:path'
import { hardcodedStrings } from './hardcodedStrings'
import * as dataset from '../i18n/pages/i18n2Dataset'
import * as common from '../i18n/pages/i18n2Common'

/** Autopilot step 9 (i18n-2): the English left on the dataset page and in the
 *  shared components. */
const FILES = [
  'pages/DatasetDetail.tsx',
  'components/dataset/AlertsPanel.tsx',
  'components/dataset/ColumnMeaningPanel.tsx',
  'components/dataset/AggregatesPanel.tsx',
  'components/StatisticsPanel.tsx',
  'components/dataset/ChecksPanel.tsx',
  'components/WorkspaceTree.tsx',
  'components/CommandPalette.tsx',
  'components/QueryBuilderDialog.tsx',
  'components/review/SuggestFromSourceDialog.tsx',
  'components/DatasetShareDialog.tsx',
  'pages/SharedReport.tsx',
  'components/review/JoinGraph.tsx',
  'components/chat/DashboardProposals.tsx',
  'components/report/chartRenderers/HierarchyRenderer.tsx',
  'pages/connections/SchemaBrowser.tsx',
  'components/review/SyncProgress.tsx',
  'pages/connections/SqlEditor.tsx',
  'components/ProtectedRoute.tsx',
]

describe('no hard-coded English: i18n-2', () => {
  for (const f of FILES) {
    it(f, () => {
      expect(hardcodedStrings(path.join(__dirname, '..', f)).map(h => `${h.line} ${h.text}`)).toEqual([])
    })
  }
  const names = (s: string) => [...new Set([...s.matchAll(/\{(\w+)/g)].map(m => m[1]))].sort().join()
  for (const [label, { en, ar }] of [['i18n2Dataset', dataset], ['i18n2Common', common]] as const) {
    it(`${label} holds the same keys and placeholders in both languages`, () => {
      const e = en as Record<string, string>, a = ar as Record<string, string>
      expect(Object.keys(a).sort()).toEqual(Object.keys(e).sort())
      expect(Object.keys(e).filter(k => names(e[k]) !== names(a[k]))).toEqual([])
    })
  }
})
