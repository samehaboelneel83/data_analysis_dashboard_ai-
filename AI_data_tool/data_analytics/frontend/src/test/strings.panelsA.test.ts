import { describe, it, expect } from 'vitest'
import path from 'node:path'
import { hardcodedStrings } from './hardcodedStrings'

/** 8-i18n: no hard-coded English in the panelsA area (see builderStrings.test.ts). */
const FILES: string[] = [
  'components/report/MeasuresPanel.tsx',
  'components/report/ColumnFormatsPanel.tsx',
  'components/report/CustomFunctionsPanel.tsx',
  'components/report/CalcColumnsPanel.tsx',
  'components/report/calcColumns/BuilderModal.tsx',
  'components/report/CustomCategoryPanel.tsx',
  'components/report/HierarchyTree.tsx',
  'components/report/HierarchyChains.tsx',
  'components/DatasetSensitivity.tsx',
  'components/report/AccessDialog.tsx',
  'components/report/AccessExplainer.tsx',
  'components/report/SubscribeButton.tsx',
  'components/report/SuggestionsPane.tsx',
  'components/report/calcColumns/catalog.ts',
  'components/report/PackTermsConfirm.tsx',
  'components/report/GeoMatchLine.tsx',
]

describe('no hard-coded English: panelsA (8-i18n)', () => {
  it.each(FILES.length ? FILES : ['(none yet)'])('%s', f => {
    if (f === '(none yet)') return
    expect(hardcodedStrings(path.join(__dirname, '..', f)).map(h => `${f}:${h.line} ${h.text}`)).toEqual([])
  })
})
