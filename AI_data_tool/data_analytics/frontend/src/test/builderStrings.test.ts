import { describe, it, expect } from 'vitest'
import path from 'node:path'
import { hardcodedStrings } from './hardcodedStrings'

/**
 * QA3 Batch C: the Builder's components show no hard-coded English. Every
 * word a reader sees goes through the translator (t / tr, or the settings
 * panel's L), so Arabic never falls back to English here again. A literal
 * that is not prose (a unit, a code sample) is marked `// i18n-ok`.
 */
export const BUILDER_FILES = [
  'pages/ReportBuilder.tsx',
  'pages/reportBuilder/BookmarksConnected.tsx', 'pages/reportBuilder/CanvasOverlays.tsx', 'pages/reportBuilder/PageTabs.tsx',
  'pages/reportBuilder/PageTemplateMenu.tsx', 'pages/reportBuilder/RightRail.tsx', 'pages/reportBuilder/SaveState.tsx',
  'pages/reportBuilder/SchedulePanel.tsx', 'pages/reportBuilder/ShortcutsDialog.tsx', 'pages/reportBuilder/TemplatesPane.tsx',
  'pages/reportBuilder/ZoomControl.tsx',
  'components/report/BookmarksPane.tsx', 'components/report/CommentsPane.tsx', 'components/report/DataRolesList.tsx',
  'components/report/DisplayRulesPanel.tsx', 'components/report/ExplainDialog.tsx', 'components/report/InteractionSettings.tsx',
  'components/report/MobileLayoutEditor.tsx', 'components/report/OutlinePane.tsx', 'components/report/PagePropertiesPanel.tsx',
  'components/report/ReviewPane.tsx', 'components/report/SelectionPane.tsx', 'components/report/SyncSlicersPane.tsx',
  'components/report/TabOrderPane.tsx', 'components/report/TranslationsPane.tsx', 'components/report/WidgetPlaceholder.tsx',
  'components/report/ViewerKit.tsx', 'components/report/WidgetRenderer.tsx', 'components/report/WidgetConfigPanel.tsx',
  'components/report/StatusBar.tsx',
  'components/report/DataBarEditor.tsx', 'components/report/IntervalEditor.tsx', 'components/report/ValueMapEditor.tsx',
  'components/report/CollapsibleSide.tsx', 'components/report/FilterBar.tsx', 'components/report/FloatingFilterWindow.tsx',
  'components/ui/LoadError.tsx',
]

describe('no hard-coded English in the Builder (QA3 Batch C)', () => {
  it.each(BUILDER_FILES)('%s', f => {
    const hits = hardcodedStrings(path.join(__dirname, '..', f))
    expect(hits.map(h => `${f}:${h.line} ${h.text}`)).toEqual([])
  })
})
