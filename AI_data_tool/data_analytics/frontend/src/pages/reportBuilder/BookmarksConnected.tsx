import BookmarksPane from '../../components/report/BookmarksPane'
import SyncSlicersPane from '../../components/report/SyncSlicersPane'
import { useCrossFilter } from '../../components/report/CrossFilterContext'
import { reportsApi } from '../../services/api'
import type { Report, ReportPage, Widget, Bookmark, BookmarkState } from '../../types/report'

// Connects SyncSlicersPane to CrossFilterContext — must render inside CrossFilterProvider,
// which ReportBuilder's own function body is not (it creates one further down its own tree).
export function SyncSlicersPaneConnected({ pages }: { pages: ReportPage[] }) {
  const { interactions, setInteraction } = useCrossFilter()
  return (
    <SyncSlicersPane pages={pages} interactions={interactions}
      onToggleSync={(id, sync) => setInteraction(id, { ...(interactions[id] ?? { broadcasts: true, receives: true }), syncAllPages: sync })} />
  )
}

// Connects BookmarksPane to CrossFilterContext for the same reason as SyncSlicersPaneConnected —
// capturing/restoring a bookmark needs activeFilters/emitFilter/clearAllFilters.
export function BookmarksPaneConnected({ reportId, report, activePage, pageWidgets, promptValues, bookmarks,
  setActivePage, setPromptValues, setBookmarks, loadReport }: {
  reportId: number
  report: Report
  activePage: ReportPage | null
  pageWidgets: Widget[]
  promptValues: Record<number, string>
  bookmarks: Bookmark[]
  setActivePage: (p: ReportPage) => void
  setPromptValues: (fn: (p: Record<number, string>) => Record<number, string>) => void
  setBookmarks: (fn: (b: Bookmark[]) => Bookmark[]) => void
  loadReport: () => Promise<void>
}) {
  const { activeFilters, emitFilter, emitMultiFilter, clearAllFilters } = useCrossFilter()

  const captureState = (): BookmarkState => ({
    pageId: activePage!.id,
    activeFilters,
    promptValues,
    hiddenWidgetIds: pageWidgets.filter(w => !!(w.config as any).hidden).map(w => w.id),
  })

  const applyBookmark = async (b: Bookmark) => {
    const target = report.pages.find(p => p.id === b.state.pageId)
    if (!target) return
    setActivePage(target)
    setPromptValues(p => ({ ...p, ...b.state.promptValues }))
    clearAllFilters()
    b.state.activeFilters.forEach(f =>
      Array.isArray(f.value)
        ? emitMultiFilter(f.sourceWidgetId, f.sourcePageId, f.column, f.value, f.label)
        : emitFilter(f.sourceWidgetId, f.sourcePageId, f.column, f.value, f.label)
    )
    const hiddenSet = new Set(b.state.hiddenWidgetIds)
    const toFix = target.widgets.filter(w => !!(w.config as any).hidden !== hiddenSet.has(w.id))
    await Promise.all(toFix.map(w =>
      reportsApi.updateWidget(reportId, target.id, w.id, { config: { ...w.config, hidden: hiddenSet.has(w.id) } })
    ))
    if (toFix.length > 0) await loadReport()
  }

  return (
    <BookmarksPane reportId={reportId} bookmarks={bookmarks} captureState={captureState}
      onCaptured={b => setBookmarks(p => [...p, b])} onApply={applyBookmark}
      onDeleted={id => setBookmarks(p => p.filter(b => b.id !== id))} />
  )
}
