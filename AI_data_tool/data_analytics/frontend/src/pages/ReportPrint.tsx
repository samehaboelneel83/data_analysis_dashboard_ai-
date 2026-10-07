import { useCallback, useEffect, useState } from 'react'
import { useT } from '../i18n'
import { useParams, Link } from 'react-router-dom'
import { reportsApi, datasetsApi, themesApi } from '../services/api'
import { exportPrintViewToPptx } from '../lib/pptExport'
import type { Dataset, CalcColumn, CalcColumnFormat } from '../services/api'
import type { Report, ReportPage } from '../types/report'
import WidgetRenderer from '../components/report/WidgetRenderer'
import { CrossFilterProvider } from '../components/report/CrossFilterContext'
import { StaticChartsContext } from '../components/report/chartRenderers/useChartViewport'
import LoadError from '../components/ui/LoadError'
import LoadingState from '../components/ui/LoadingState'
import { applyTheme } from '../components/report/chartUtils'

/**
 * Print layout: every page of the report laid out linearly, one report page per
 * printed sheet, with the interactive chrome gone.
 *
 * This is also the PDF route: the browser's own print-to-PDF renders exactly this
 * view, so "export as PDF" needs no server-side browser. Widgets resolve their data
 * through the same authenticated API as the builder, so row-level security and
 * filters apply to the printed page identically -- there is no separate print
 * pipeline to drift or leak.
 */
export default function ReportPrint() {
  const t = useT()
  const { id } = useParams()
  const reportId = Number(id)
  const [report, setReport] = useState<Report | null>(null)
  const [dataset, setDataset] = useState<Dataset | null>(null)
  const [error, setError] = useState<unknown>(null)

  const load = useCallback(async () => {
    setError(null)
    try {
      const r = await reportsApi.get(reportId)
      // Printed in the report's own palette, an org palette included.
      const customs = r.theme?.startsWith('custom:')
        ? Object.fromEntries((await themesApi.list().catch(() => [])).map(t => [`custom:${t.id}`, t.colors]))
        : undefined
      applyTheme(r.theme ?? 'default', customs)
      setReport(r)
      if (r.dataset_id) setDataset(await datasetsApi.get(r.dataset_id))
    } catch (e) {
      setError(e)
    }
  }, [reportId])
  useEffect(() => { load() }, [load])
  // Paper is light (QA2 Visual 7). The whole page, not only this subtree: many
  // dark styles are written as [data-theme="dark"] .x and still match through
  // <html>. Set on the next tick, after the shell's own theme effect has run
  // on mount; the reader's saved theme comes back on leaving.
  useEffect(() => {
    const root = document.documentElement
    const id = setTimeout(() => root.setAttribute('data-theme', 'light'), 0)
    return () => {
      clearTimeout(id)
      let saved: string | null = null
      try { saved = localStorage.getItem('theme') } catch { /* blocked storage */ }
      root.setAttribute('data-theme', saved === 'dark' ? 'dark' : 'light')
    }
  }, [])

  if (error) return <div style={{ padding: 40 }}><LoadError what="this report" error={error} onRetry={load} /></div>
  if (!report) return <div style={{ padding: 40 }}><LoadingState label={t('prt.preparing')} /></div>

  const calcCols: CalcColumn[] = dataset?.calculated_columns ?? []
  const formats: Record<string, CalcColumnFormat> = dataset?.column_formats ?? {}
  // Hidden pages are hidden in view mode; a printout is view mode on paper.
  const pages = report.pages.filter((p: ReportPage) => p.page_type !== 'hidden')

  return (
    // Paper is light (QA2 Visual 7): this subtree takes the light theme's
    // tokens whatever the app's theme, so widgets draw light cards with dark
    // text -- in dark mode they were dark cards with near-black text.
    <div data-product="datalytics" data-theme="light" className="dl-paper"
      style={{ background: '#fff', color: '#111', minHeight: '100%', colorScheme: 'light' }}>
      <style>{`
        @media print {
          .print-toolbar { display: none !important; }
          .print-page { break-after: page; }
        }
        @media screen {
          .print-page { max-width: 1100px; margin: 0 auto 32px; border: 1px solid #ddd; }
        }
      `}</style>

      <div className="print-toolbar" style={{ display: 'flex', gap: 10, alignItems: 'center',
        padding: '10px 16px', borderBottom: '1px solid #ddd' }}>
        <h1 style={{ fontSize: 15, fontWeight: 700, margin: 0 }}>{report.name}</h1>
        <span style={{ color: '#888', fontSize: 12 }}>{t('prt.pages', { n: pages.length })}</span>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          <button className="btn btn-primary btn-sm" onClick={() => window.print()}>
            {t('prt.print')}
          </button>
          <button className="btn btn-sm" onClick={async () => {
            const n = await exportPrintViewToPptx(report.name, document.body)
            console.info(`Exported ${n} slides`)
          }}>
            {t('prt.pptx')}
          </button>
          <Link className="btn btn-ghost btn-sm" to={`/reports/${reportId}`}>{t('prt.back')}</Link>
        </div>
      </div>

      {pages.map(page => (
        <section key={page.id} className="print-page" aria-label={page.name}
          style={{ padding: 24 }}>
          <h2 style={{ fontSize: 16, margin: '0 0 14px' }}>{page.title || page.name}</h2>
          <CrossFilterProvider>
            {/* Paper shows every point: no slider to drag, no window to leave data out. */}
            <StaticChartsContext.Provider value={true}>
            <div data-print-canvas style={{ position: 'relative' }}>
              {page.widgets.map(w => {
                const l = w.layout ?? { x: 0, y: 0, w: 6, h: 4 }
                // The builder's 12-column grid mapped onto a fixed print width. Absolute
                // positioning reproduces the authored layout; a flowed list would not.
                const cell = (1050 - 11 * 8) / 12
                return (
                  <div key={w.id} data-print-widget style={{
                    position: 'absolute',
                    left: l.x * (cell + 8),
                    top: l.y * 66,
                    width: l.w * cell + (l.w - 1) * 8,
                    height: l.h * 58 + (l.h - 1) * 8,
                  }}>
                    <WidgetRenderer
                      widget={w} datasetId={(w.config as { dataset_id?: number } | undefined)?.dataset_id ?? report.dataset_id ?? null}
                      calculatedColumns={calcCols} columnFormats={formats}
                      editMode={false} isPreview={false} eagerFetch
                      pages={report.pages}
                    />
                  </div>
                )
              })}
              {/* Reserve the page's height: children are absolutely positioned. */}
              <div style={{ height: Math.max(200,
                ...page.widgets.map(w => ((w.layout?.y ?? 0) + (w.layout?.h ?? 4)) * 66 + 20)) }} />
            </div>
            </StaticChartsContext.Provider>
          </CrossFilterProvider>
        </section>
      ))}
    </div>
  )
}
