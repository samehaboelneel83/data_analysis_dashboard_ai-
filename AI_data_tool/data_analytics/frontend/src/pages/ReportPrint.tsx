import { useCallback, useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { reportsApi, datasetsApi } from '../services/api'
import { exportPrintViewToPptx } from '../lib/pptExport'
import type { Dataset, CalcColumn, CalcColumnFormat } from '../services/api'
import type { Report, ReportPage } from '../types/report'
import WidgetRenderer from '../components/report/WidgetRenderer'
import { CrossFilterProvider } from '../components/report/CrossFilterContext'
import LoadError from '../components/ui/LoadError'
import LoadingState from '../components/ui/LoadingState'

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
  const { id } = useParams()
  const reportId = Number(id)
  const [report, setReport] = useState<Report | null>(null)
  const [dataset, setDataset] = useState<Dataset | null>(null)
  const [error, setError] = useState<unknown>(null)

  const load = useCallback(async () => {
    setError(null)
    try {
      const r = await reportsApi.get(reportId)
      setReport(r)
      if (r.dataset_id) setDataset(await datasetsApi.get(r.dataset_id))
    } catch (e) {
      setError(e)
    }
  }, [reportId])
  useEffect(() => { load() }, [load])

  if (error) return <div style={{ padding: 40 }}><LoadError what="this report" error={error} onRetry={load} /></div>
  if (!report) return <div style={{ padding: 40 }}><LoadingState label="Preparing print view…" /></div>

  const calcCols: CalcColumn[] = dataset?.calculated_columns ?? []
  const formats: Record<string, CalcColumnFormat> = dataset?.column_formats ?? {}
  // Hidden pages are hidden in view mode; a printout is view mode on paper.
  const pages = report.pages.filter((p: ReportPage) => p.page_type !== 'hidden')

  return (
    <div style={{ background: '#fff', color: '#111', minHeight: '100%' }}>
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
        <strong style={{ fontSize: 15 }}>{report.name}</strong>
        <span style={{ color: '#888', fontSize: 12 }}>{pages.length} page{pages.length === 1 ? '' : 's'}</span>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          <button className="btn btn-primary btn-sm" onClick={() => window.print()}>
            Print / Save as PDF
          </button>
          <button className="btn btn-sm" onClick={async () => {
            const n = await exportPrintViewToPptx(report.name, document.body)
            console.info(`Exported ${n} slides`)
          }}>
            Download PowerPoint
          </button>
          <Link className="btn btn-ghost btn-sm" to={`/reports/${reportId}`}>Back to report</Link>
        </div>
      </div>

      {pages.map(page => (
        <section key={page.id} className="print-page" aria-label={page.name}
          style={{ padding: 24 }}>
          <h2 style={{ fontSize: 16, margin: '0 0 14px' }}>{page.title || page.name}</h2>
          <CrossFilterProvider>
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
          </CrossFilterProvider>
        </section>
      ))}
    </div>
  )
}
