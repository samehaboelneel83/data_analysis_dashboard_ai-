import { describe, it, expect } from 'vitest'
import path from 'node:path'
import { hardcodedStrings } from './hardcodedStrings'

/** 8-i18n: no hard-coded English in the modelsMaps area (see builderStrings.test.ts). */
const FILES: string[] = [
  'components/dataset/PredictionModelsPanel.tsx',
  'components/report/ModelSettings.tsx',
  'components/report/ModelView.tsx',
  'components/report/chartRenderers/ModelRenderer.tsx',
  'components/report/MapLayersEditor.tsx',
  'components/report/MapPinsEditor.tsx',
  'components/report/GraphLayersEditor.tsx',
  'components/report/BoundarySetPicker.tsx',
  'components/report/GeoMatchCheck.tsx',
]

describe('no hard-coded English: modelsMaps (8-i18n)', () => {
  it.each(FILES.length ? FILES : ['(none yet)'])('%s', f => {
    if (f === '(none yet)') return
    expect(hardcodedStrings(path.join(__dirname, '..', f)).map(h => `${f}:${h.line} ${h.text}`)).toEqual([])
  })
})
