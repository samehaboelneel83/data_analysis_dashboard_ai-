import { useEffect, useState, useCallback, useRef } from 'react'
import { useParams, Link } from 'react-router-dom'
import { reportsApi, datasetsApi, hierarchyApi } from '../services/api'
import type { Dataset, DatasetColumn } from '../services/api'
import type { Report, ReportPage, Widget, WidgetType } from '../types/report'
import { WIDGET_CATALOG } from '../types/report'
import type { HierarchyNode } from '../types/report'
import WidgetRenderer from '../components/report/WidgetRenderer'
import WidgetConfigPanel from '../components/report/WidgetConfigPanel'
import HierarchyTree from '../components/report/HierarchyTree'
import FilterBar from '../components/report/FilterBar'
import { CrossFilterProvider } from '../components/report/CrossFilterContext'
import { ArrowLeft, Plus, Settings, Eye } from 'lucide-react'
import toast from 'react-hot-toast'

// ── Grid layout constants ────────────────────────────────────────────────────
const COLS    = 12
const ROW_H   = 58    // px per grid row unit
const GAP     = 8

function gridStyle(layout: Widget['layout'], containerW: number): React.CSSProperties {
  const cellW = (containerW - GAP * (COLS - 1)) / COLS
  return {
    position: 'absolute',
    left:   layout.x * (cellW + GAP),
    top:    layout.y * (ROW_H + GAP),
    width:  layout.w * cellW + (layout.w - 1) * GAP,
    height: layout.h * ROW_H + (layout.h - 1) * GAP,
  }
}

function canvasH(widgets: Widget[]) {
  if (!widgets.length) return 560
  return Math.max(560, Math.max(...widgets.map(w => w.layout.y + w.layout.h)) * (ROW_H + GAP) + 80)
}

// ── Component ────────────────────────────────────────────────────────────────
export default function ReportBuilder() {
  const { id } = useParams<{ id: string }>()
  const reportId = Number(id)

  const [report,     setReport]     = useState<Report | null>(null)
  const [activePage, setActivePage] = useState<ReportPage | null>(null)
  const [selectedW,  setSelectedW]  = useState<Widget | null>(null)
  const [dataset,    setDataset]    = useState<Dataset | null>(null)
  const [hierarchy,  setHierarchy]  = useState<HierarchyNode[]>([])
  const [leftPanel,  setLeftPanel]  = useState<'widgets' | 'data'>('widgets')
  const [editMode,   setEditMode]   = useState(true)
  const [containerW, setContainerW] = useState(900)
  const [editPid,    setEditPid]    = useState<number | null>(null)
  const [editPname,  setEditPname]  = useState('')
  const canvasRef = useRef<HTMLDivElement>(null)

  // Measure canvas width
  useEffect(() => {
    if (!canvasRef.current) return
    const ro = new ResizeObserver(() => {
      if (canvasRef.current) setContainerW(canvasRef.current.clientWidth)
    })
    ro.observe(canvasRef.current)
    return () => ro.disconnect()
  }, [])

  // Load report
  const loadReport = useCallback(async () => {
    const r = await reportsApi.get(reportId)
    setReport(r)
    setActivePage(prev => r.pages.find(p => p.id === prev?.id) ?? r.pages[0] ?? null)
  }, [reportId])

  useEffect(() => { loadReport() }, [loadReport])

  // Load dataset + hierarchy
  useEffect(() => {
    if (!report?.dataset_id) return
    datasetsApi.get(report.dataset_id).then(setDataset)
    hierarchyApi.get(report.dataset_id).then(setHierarchy)
  }, [report?.dataset_id])

  const refreshHierarchy = () => {
    if (report?.dataset_id) hierarchyApi.get(report.dataset_id).then(setHierarchy)
  }

  // ── Widgets ──────────────────────────────────────────────────────────────
  const addWidget = async (type: WidgetType) => {
    if (!activePage) return toast.error('Select a page first')
    const ws = activePage.widgets
    const maxY = ws.length ? Math.max(...ws.map(w => w.layout.y + w.layout.h)) : 0
    const cat = WIDGET_CATALOG.find(c => c.type === type)
    const w = cat?.defaultW ?? 6, h = cat?.defaultH ?? 5
    const widget = await reportsApi.addWidget(reportId, activePage.id, {
      widget_type: type,
      title: cat?.label ?? type,
      config: {},
      layout: { x: 0, y: maxY, w, h },
    })
    await loadReport()
    setSelectedW(widget)
    toast.success(`${cat?.label ?? type} added`)
  }

  const deleteWidget = async (w: Widget) => {
    if (!activePage) return
    await reportsApi.deleteWidget(reportId, activePage.id, w.id)
    if (selectedW?.id === w.id) setSelectedW(null)
    await loadReport()
  }

  const updateWidgetConfig = useCallback(async (config: Record<string, unknown>, title: string) => {
    if (!selectedW || !activePage) return
    await reportsApi.updateWidget(reportId, activePage.id, selectedW.id, { config, title })
    await loadReport()
  }, [selectedW, activePage, reportId, loadReport])

  // ── Pages ────────────────────────────────────────────────────────────────
  const addPage = async () => {
    const pos = report?.pages.length ?? 0
    const page = await reportsApi.addPage(reportId, { name: `Page ${pos + 1}`, position: pos })
    await loadReport()
    setActivePage(page)
    toast.success('Page added')
  }

  const deletePage = async (page: ReportPage) => {
    if (!confirm(`Delete "${page.name}"?`)) return
    await reportsApi.deletePage(reportId, page.id)
    await loadReport()
    toast.success('Page deleted')
  }

  const savePageName = async (page: ReportPage) => {
    await reportsApi.updatePage(reportId, page.id, { name: editPname })
    setEditPid(null)
    await loadReport()
  }

  const autoGenHierarchy = async () => {
    if (!report?.dataset_id) return toast.error('Attach a dataset first')
    const nodes = await hierarchyApi.autoGenerate(report.dataset_id)
    setHierarchy(nodes)
    toast.success('Hierarchy generated from column types')
  }

  if (!report) return <p style={{ color: 'var(--muted)', padding: 32 }}>Loading…</p>

  const columns: DatasetColumn[] = dataset?.columns ?? []
  const pageWidgets = activePage?.widgets ?? []

  return (
    <div style={{ display:'flex', flexDirection:'column', height:'100%' }}>

      {/* ── Top bar ── */}
      <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:14, flexShrink:0 }}>
        <Link to="/reports" style={{ color:'var(--muted)', display:'flex', alignItems:'center', gap:4, fontSize:12, textDecoration:'none' }}>
          <ArrowLeft size={13} /> Reports
        </Link>
        <span style={{ color:'var(--border)' }}>|</span>
        <span style={{ fontWeight:700, fontSize:16 }}>{report.name}</span>
        {dataset && <span className="badge badge-categorical">{dataset.name}</span>}
        <div style={{ marginLeft:'auto', display:'flex', gap:8 }}>
          <button className={`btn btn-ghost btn-sm`} onClick={() => setEditMode(m => !m)}
            style={{ color: editMode ? 'var(--accent)' : 'var(--muted)' }}>
            {editMode ? <><Settings size={12}/> Edit mode</> : <><Eye size={12}/> View mode</>}
          </button>
        </div>
      </div>

      {/* ── Page tabs ── */}
      <div style={{ display:'flex', alignItems:'center', gap:3, marginBottom:14, borderBottom:'1px solid var(--border)', paddingBottom:0, flexShrink:0 }}>
        {report.pages.map(page => (
          <div key={page.id} style={{ display:'flex', alignItems:'center', borderBottom: page.id===activePage?.id ? '2px solid var(--accent)' : '2px solid transparent', marginBottom:-1 }}>
            {editPid === page.id ? (
              <input value={editPname} onChange={e => setEditPname(e.target.value)}
                onBlur={() => savePageName(page)} onKeyDown={e => e.key==='Enter' && savePageName(page)}
                style={{ fontSize:12, padding:'5px 8px', width:90 }} autoFocus />
            ) : (
              <button
                style={{ padding:'7px 13px', border:'none', background:'none', cursor:'pointer', fontSize:12,
                  color: page.id===activePage?.id ? 'var(--accent)' : 'var(--muted)',
                  fontWeight: page.id===activePage?.id ? 600 : 400, fontFamily:'var(--sans)' }}
                onClick={() => { setActivePage(page); setSelectedW(null) }}
                onDoubleClick={() => { setEditPid(page.id); setEditPname(page.name) }}
              >{page.name}</button>
            )}
            {editMode && report.pages.length > 1 && (
              <button style={{ background:'none', border:'none', color:'var(--muted)', cursor:'pointer', padding:'0 4px', fontSize:13 }}
                onClick={() => deletePage(page)}>×</button>
            )}
          </div>
        ))}
        {editMode && (
          <button className="btn btn-ghost btn-sm" onClick={addPage} style={{ marginBottom:3, fontSize:11 }}>
            <Plus size={11}/> Page
          </button>
        )}
      </div>

      {/* ── Main 3-column layout ── */}
      <div style={{ display:'flex', flex:1, gap:10, overflow:'hidden', minHeight:0 }}>

        {/* Left panel */}
        {editMode && (
          <div style={{ width:215, flexShrink:0, display:'flex', flexDirection:'column', background:'var(--surface)', border:'1px solid var(--border)', borderRadius:'var(--radius)', overflow:'hidden' }}>
            <div style={{ display:'flex', borderBottom:'1px solid var(--border)' }}>
              {(['widgets','data'] as const).map(key => (
                <button key={key} onClick={() => setLeftPanel(key)}
                  style={{ flex:1, padding:'8px 4px', border:'none', background:'none', cursor:'pointer', fontSize:11,
                    fontFamily:'var(--sans)', fontWeight: leftPanel===key ? 700 : 400,
                    color: leftPanel===key ? 'var(--accent)' : 'var(--muted)',
                    borderBottom: leftPanel===key ? '2px solid var(--accent)' : '2px solid transparent', marginBottom:-1 }}>
                  {key === 'widgets' ? '⊞ Widgets' : '🗂 Data View'}
                </button>
              ))}
            </div>

            <div style={{ flex:1, overflowY:'auto', padding:10 }}>
              {leftPanel === 'widgets' && (
                <>
                  {['Charts','Controls'].map(cat => (
                    <div key={cat}>
                      <div style={{ fontSize:10, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.07em', padding:'8px 0 5px' }}>{cat}</div>
                      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:5 }}>
                        {WIDGET_CATALOG.filter(w => w.category===cat).map(w => (
                          <button key={w.type} onClick={() => addWidget(w.type)}
                            style={{ display:'flex', flexDirection:'column', alignItems:'center', gap:3, padding:'9px 4px',
                              background:'var(--surface2)', border:'1px solid var(--border)', borderRadius:7,
                              cursor:'pointer', fontSize:10, color:'var(--text)', fontFamily:'var(--sans)', transition:'border-color .15s' }}
                            onMouseEnter={e => (e.currentTarget.style.borderColor='var(--accent)')}
                            onMouseLeave={e => (e.currentTarget.style.borderColor='var(--border)')}>
                            <span style={{ fontSize:18 }}>{w.icon}</span>
                            <span style={{ color:'var(--muted)', lineHeight:1.2, textAlign:'center' }}>{w.label}</span>
                          </button>
                        ))}
                      </div>
                    </div>
                  ))}
                </>
              )}

              {leftPanel === 'data' && (
                <>
                  <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:8 }}>
                    <span style={{ fontSize:10, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em' }}>Hierarchy</span>
                    {dataset && (
                      <button className="btn btn-ghost btn-sm" onClick={autoGenHierarchy} style={{ fontSize:10, padding:'2px 6px' }}>
                        ✦ Auto
                      </button>
                    )}
                  </div>
                  {!dataset
                    ? <p style={{ fontSize:12, color:'var(--muted)', textAlign:'center', marginTop:20 }}>Attach a dataset to this report to browse columns.</p>
                    : <HierarchyTree nodes={hierarchy} datasetId={dataset.id} onRefresh={refreshHierarchy} />
                  }
                </>
              )}
            </div>
          </div>
        )}

        {/* Canvas */}
        <div style={{ flex:1, overflowY:'auto', overflowX:'hidden' }}>
          <CrossFilterProvider>
            <FilterBar />
            <div ref={canvasRef} style={{ position:'relative', minHeight:canvasH(pageWidgets), background:'var(--surface2)', borderRadius:'var(--radius)', border:'1px solid var(--border)' }}>
              {pageWidgets.length === 0 && editMode && (
                <div style={{ position:'absolute', inset:0, display:'flex', alignItems:'center', justifyContent:'center', flexDirection:'column', gap:10, color:'var(--muted)', pointerEvents:'none' }}>
                  <span style={{ fontSize:36, opacity:.2 }}>⊞</span>
                  <span style={{ fontSize:13 }}>Click a widget from the left panel to add it here</span>
                </div>
              )}
              {pageWidgets.map(widget => (
                <div key={widget.id} style={{ ...gridStyle(widget.layout, containerW), padding: GAP/2 }}>
                  <WidgetRenderer
                    widget={widget}
                    datasetId={report.dataset_id}
                    selected={selectedW?.id === widget.id}
                    onSelect={() => setSelectedW(widget)}
                    onDelete={() => deleteWidget(widget)}
                    editMode={editMode}
                  />
                </div>
              ))}
            </div>
          </CrossFilterProvider>
        </div>

        {/* Right: config panel */}
        {editMode && selectedW && (
          <div style={{ width:245, flexShrink:0, background:'var(--surface)', border:'1px solid var(--border)', borderRadius:'var(--radius)', overflowY:'auto' }}>
            <div style={{ padding:'9px 13px', borderBottom:'1px solid var(--border)', display:'flex', alignItems:'center', justifyContent:'space-between' }}>
              <span style={{ fontSize:10, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em' }}>Properties</span>
              <button style={{ background:'none', border:'none', color:'var(--muted)', cursor:'pointer', fontSize:14 }} onClick={() => setSelectedW(null)}>×</button>
            </div>
            <WidgetConfigPanel widget={selectedW} columns={columns} onUpdate={updateWidgetConfig} />
          </div>
        )}
      </div>
    </div>
  )
}
