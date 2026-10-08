import { describe, it, expect } from 'vitest'
import path from 'node:path'
import { hardcodedStrings } from './hardcodedStrings'

/** 8-i18n: no hard-coded English in the panelsB area (see builderStrings.test.ts). */
const FILES: string[] = [
  'components/report/PrepPipelinePanel.tsx',
  'components/report/PrepStepsPanel.tsx',
  'components/report/prepPipeline/StepEditor.tsx',
  'components/report/prepPipeline/JoinMatchNote.tsx',
  'components/report/prepPipeline/model.ts',
  'components/report/prepPipeline/join.ts',
  'components/report/prepPipeline/tNodes.tsx',
  'components/report/OutlierDetailsDialog.tsx',
  'components/report/DataView.tsx',
  'components/report/DataViewsBar.tsx',
  'components/report/RelativeDateEditor.tsx',
  // QA5 L1/L2: the expression builder (calc-column builder, filter-rows step);
  // calcColumns/* is guarded in strings.panelsA.test.ts.
  'components/expr/ExpressionBuilder.tsx',
]

describe('no hard-coded English: panelsB (8-i18n)', () => {
  it.each(FILES.length ? FILES : ['(none yet)'])('%s', f => {
    if (f === '(none yet)') return
    expect(hardcodedStrings(path.join(__dirname, '..', f)).map(h => `${f}:${h.line} ${h.text}`)).toEqual([])
  })
})
