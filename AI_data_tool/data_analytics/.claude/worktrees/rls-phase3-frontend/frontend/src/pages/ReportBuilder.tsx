import { useEffect, useState, useCallback, useRef } from 'react'
import { useParams, Link, NavLink } from 'react-router-dom'
import { reportsApi, datasetsApi, hierarchyApi } from '../services/api'
import type { Dataset, DatasetColumn, CalcColumn, CalcColumnFormat } from '../services/api'
import CalcColumnsPanel from '../components/report/CalcColumnsPanel'
import ColumnFormatsPanel from '../components/report/ColumnFormatsPanel'
import type { Report, ReportPage, Widget, WidgetType, PageType } from '../types/report'
import { WIDGET_CATALOG } from '../types/report'
import type { HierarchyNode } from '../types/report'
import WidgetRenderer from '../components/report/WidgetRenderer'
import WidgetConfigPanel from '../components/report/WidgetConfigPanel'
import PagePropertiesPanel from '../components/report/PagePropertiesPanel'
import HierarchyTree from '../components/report/HierarchyTree'
import FilterBar from '../components/report/FilterBar'
import { CrossFilterProvider } from '../components/report/CrossFilterContext'
import { ArrowLeft, Plus, Settings, Eye } from 'lucide-react'
import toast from 'react-hot-toast'

// â”€â”€ Grid layout constants â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

// â”€â”€ Component â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
export default function ReportBuilder() {
  const { id } = useParams<{ id: string }>()
  const reportId = Number(id)

  const [report,     setReport]     = useState<Report | null>(null)
  const [activePage, setActivePage] = useState<ReportPage | null>(null)
  const [selectedW,  setSelectedW]  = useState<Widget | null>(null)
  const [dataset,    setDataset]    = useState<Dataset | null>(null)
  const [datasets,   setDatasets]   = useState<Record<number, Dataset>>({})
  const [allDatasets,setAllDatasets]= useState<Dataset[]>([])
  const [showDsMenu, setShowDsMenu] = useState(false)
  const [hierarchy,  setHierarchy]  = useState<HierarchyNode[]>([])
  const [calcCols,      setCalcCols]      = useState<CalcColumn[]>([])
  const [columnFormats, setColumnFormats] = useState<Record<string, CalcColumnFormat>>({})
  const [leftPanel,  setLeftPanel]  = useState<'widgets' | 'data'>('widgets')
  const [editMode,   setEditMode]   = useState(true)
  const [containerW, setContainerW] = useState(900)
  const [editPid,      setEditPid]      = useState<number | null>(null)
  const [editPname,    setEditPname]    = useState('')
  const [promptValues, setPromptValues] = useState<Record<number, string>>({})

  // Drag / resize state
  const [dragging,  setDragging]  = useState<{ widgetId:number; startX:number; startY:number; layout:Widget['layout']; offsetX:number; offsetY:number } | null>(null)
  const [resizing,  setResizing]  = useState<{ widgetId:number; startX:number; startY:number; layout:Widget['layout'] } | null>(null)
  const [localLayouts, setLocalLayouts] = useState<Record<number, Widget['layout']>>({})
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

  // Load all attached datasets (primary + additional) into the datasets map
  useEffect(() => {
    if (!report) return
    const ids = [
      ...(report.dataset_id ? [report.dataset_id] : []),
      ...(report.additional_dataset_ids ?? []),
    ]
    if (ids.length === 0) return
    Promise.all(ids.map(id => datasetsApi.get(id))).then(list => {
      const map: Record<number, Dataset> = {}
      list.forEach(ds => { map[ds.id] = ds })
      setDatasets(map)
      const primary = report.dataset_id ? map[report.dataset_id] : null
      if (primary) {
        setDataset(primary)
        setCalcCols(primary.calculated_columns ?? [])
        setColumnFormats(primary.column_formats ?? {})
      }
    })
    if (report.dataset_id) {
      hierarchyApi.get(report.dataset_id).then(setHierarchy)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [report?.dataset_id, JSON.stringify(report?.additional_dataset_ids)])

  const refreshHierarchy = () => {
    if (report?.dataset_id) hierarchyApi.get(report.dataset_id).then(setHierarchy)
  }

  const attachDataset = async (dsId: number) => {
    if (!report) return
    const current = report.additional_dataset_ids ?? []
    if (current.includes(dsId) || dsId === report.dataset_id) return
    await reportsApi.update(report.id, { additional_dataset_ids: [...current, dsId] })
    await loadReport()
  }

  const detachDataset = async (dsId: number) => {
    if (!report) return
    const current = report.additional_dataset_ids ?? []
    await reportsApi.update(report.id, { additional_dataset_ids: current.filter(id => id !== dsId) })
    setDatasets(p => { const n = { ...p }; delete n[dsId]; return n })
    await loadReport()
  }

  // â”€â”€ Widgets â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

  // â”€â”€ Pages â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

  const updatePageProps = useCallback(async (data: Partial<ReportPage>) => {
    if (!activePage) return
    await reportsApi.updatePage(reportId, activePage.id, data)
    await loadReport()
  }, [activePage, reportId, loadReport])

  const autoGenHierarchy = async () => {
    if (!report?.dataset_id) return toast.error('Attach a dataset first')
    try {
      const nodes = await hierarchyApi.autoGenerate(report.dataset_id)
      setHierarchy(nodes)
      toast.success('Hierarchy generated from column types')
    } catch (err: any) {
      const msg = err?.response?.data?.detail ?? 'Failed to generate hierarchy'
      toast.error(msg)
    }
  }

  // ── Drag ─────────────────────────────────────────────────────────────────
  const handleDragStart = useCallback((widget: Widget) => (e: React.MouseEvent) => {
    e.preventDefault()
    const canvasEl = canvasRef.current
    if (!canvasEl) return
    const rect = canvasEl.getBoundingClientRect()
    const cellW = (containerW - GAP * (COLS - 1)) / COLS
    const widgetLeft = widget.layout.x * (cellW + GAP)
    const widgetTop  = widget.layout.y * (ROW_H + GAP)
    setDragging({
      widgetId: widget.id,
      startX: e.clientX, startY: e.clientY,
      layout: widget.layout,
      offsetX: e.clientX - rect.left - widgetLeft,
      offsetY: e.clientY - rect.top  - widgetTop,
    })
  }, [containerW])

  const handleResizeStart = useCallback((widget: Widget) => (e: React.MouseEvent) => {
    e.preventDefault()
    setResizing({ widgetId: widget.id, startX: e.clientX, startY: e.clientY, layout: widget.layout })
  }, [])

  useEffect(() => {
    if (!dragging && !resizing) return
    const cellW = (containerW - GAP * (COLS - 1)) / COLS

    const onMove = (e: MouseEvent) => {
      const canvasEl = canvasRef.current
      if (dragging && canvasEl) {
        const rect = canvasEl.getBoundingClientRect()
        const relX = e.clientX - rect.left - dragging.offsetX
        const relY = e.clientY - rect.top  - dragging.offsetY
        const newX = Math.max(0, Math.min(COLS - dragging.layout.w, Math.round(relX / (cellW + GAP))))
        const newY = Math.max(0, Math.round(relY / (ROW_H + GAP)))
        setLocalLayouts(p => ({ ...p, [dragging.widgetId]: { ...dragging.layout, x: newX, y: newY } }))
      }
      if (resizing) {
        const dx = e.clientX - resizing.startX
        const dy = e.clientY - resizing.startY
        const newW = Math.max(1, Math.min(COLS - resizing.layout.x, resizing.layout.w + Math.round(dx / (cellW + GAP))))
        const newH = Math.max(1, resizing.layout.h + Math.round(dy / (ROW_H + GAP)))
        setLocalLayouts(p => ({ ...p, [resizing.widgetId]: { ...resizing.layout, w: newW, h: newH } }))
      }
    }

    const onUp = async () => {
      const id      = dragging?.widgetId ?? resizing?.widgetId
      const layout  = id !== undefined ? localLayouts[id] : undefined
      const page    = activePage
      if (id !== undefined && layout && page) {
        await reportsApi.updateWidget(reportId, page.id, id, { layout })
        loadReport()
      }
      setDragging(null)
      setResizing(null)
    }

    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup',   onUp)
    return () => { window.removeEventListener('mousemove', onMove); window.removeEventListener('mouseup', onUp) }
  }, [dragging, resizing, containerW, localLayouts, activePage, reportId, loadReport])

  if (!report) return <p style={{ color: 'var(--muted)', padding: 32 }}>Loadingâ€¦</p>

  const columns: DatasetColumn[] = [
    ...(dataset?.columns ?? []),
    ...calcCols.map(c => ({ id: -1, name: c.name, dtype: 'calculated', missing_pct: 0, stats: {} })),
  ]
  const pageWidgets = activePage?.widgets ?? []

  const navLink = ({ isActive }: { isActive: boolean }): React.CSSProperties => ({
    display:'flex', alignItems:'center', gap:8, padding:'7px 10px', borderRadius:7,
    textDecoration:'none', fontSize:13,
    color: isActive ? 'var(--accent)' : 'var(--muted)',
    background: isActive ? 'rgba(108,143,255,.1)' : 'transparent',
    fontWeight: isActive ? 600 : 400, transition:'all .15s',
  })

  return (
    <div style={{ display:'flex', height:'100vh', overflow:'hidden', background:'var(--bg)' }}>

      {/* Integrated left sidebar */}
      <div style={{ width:220, flexShrink:0, display:'flex', flexDirection:'column', background:'var(--surface)', borderRight:'1px solid var(--border)', overflow:'hidden' }}>

        {/* Logo */}
        <div style={{ padding:'18px 16px 10px', fontWeight:800, fontSize:17, color:'var(--accent)', flexShrink:0 }}>
          Datalytics
        </div>

        {/* Nav */}
        <nav style={{ padding:'0 8px', flexShrink:0 }}>
          <NavLink to="/" end style={navLink}>⊞ Datasets</NavLink>
          <NavLink to="/upload" style={navLink}>↑ Upload</NavLink>
          <NavLink to="/reports" style={navLink}>📊 Reports</NavLink>
        </nav>

        {/* Analytics section */}
        <div style={{ borderTop:'1px solid var(--border)', margin:'12px 0 0', flexShrink:0 }} />
        <div style={{ padding:'9px 16px 5px', fontSize:10, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.08em', flexShrink:0 }}>
          Analytics
        </div>

        {/* Tabs */}
        <div style={{ display:'flex', borderBottom:'1px solid var(--border)', flexShrink:0 }}>
          {(['widgets','data'] as const).map(key => (
            <button key={key} onClick={() => setLeftPanel(key)}
              style={{ flex:1, padding:'7px 4px', border:'none', background:'none', cursor:'pointer', fontSize:11,
                fontFamily:'var(--sans)', fontWeight: leftPanel===key ? 700 : 400,
                color: leftPanel===key ? 'var(--accent)' : 'var(--muted)',
                borderBottom: leftPanel===key ? '2px solid var(--accent)' : '2px solid transparent', marginBottom:-1 }}>
              {key === 'widgets' ? '⊞ Widgets' : '🗂 Data View'}
            </button>
          ))}
        </div>

        {/* Panel content */}
        <div style={{ flex:1, overflowY:'auto', padding:10 }}>
          {leftPanel === 'widgets' && (
            <>
              {!editMode && (
                <p style={{ fontSize:11, color:'var(--muted)', textAlign:'center', padding:'10px 0 6px' }}>Switch to Edit mode to add widgets</p>
              )}
              {['Charts','Controls'].map(cat => (
                <div key={cat}>
                  <div style={{ fontSize:10, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.07em', padding:'8px 0 5px' }}>{cat}</div>
                  <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:5 }}>
                    {WIDGET_CATALOG.filter(w => w.category===cat).map(w => (
                      <button key={w.type} onClick={() => editMode && addWidget(w.type)}
                        style={{ display:'flex', flexDirection:'column', alignItems:'center', gap:3, padding:'9px 4px',
                          background:'var(--surface2)', border:'1px solid var(--border)', borderRadius:7,
                          cursor: editMode ? 'pointer' : 'default', fontSize:10, color:'var(--text)',
                          fontFamily:'var(--sans)', opacity: editMode ? 1 : 0.45, transition:'border-color .15s' }}
                        onMouseEnter={e => { if (editMode) e.currentTarget.style.borderColor='var(--accent)' }}
                        onMouseLeave={e => { e.currentTarget.style.borderColor='var(--border)' }}>
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
              {/* Datasets section */}
              <div style={{ marginBottom:12, paddingBottom:12, borderBottom:'1px solid var(--border)' }}>
                <div style={{ fontSize:10, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:6 }}>Datasets</div>

                {report.dataset_id && datasets[report.dataset_id] && (
                  <div style={{ display:'flex', alignItems:'center', gap:5, padding:'4px 7px', background:'var(--surface2)', borderRadius:5, marginBottom:3, fontSize:11 }}>
                    <span style={{ color:'var(--accent)' }}>★</span>
                    <span style={{ flex:1, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{datasets[report.dataset_id].name}</span>
                    {datasets[report.dataset_id].default_filter_expr
                      ? <span title={datasets[report.dataset_id].default_filter_expr!} style={{ fontSize:9, color:'var(--accent)', background:'rgba(99,102,241,.15)', borderRadius:3, padding:'1px 4px', flexShrink:0 }}>⊙ filtered</span>
                      : <span style={{ fontSize:9, color:'var(--muted)', flexShrink:0 }}>primary</span>
                    }
                  </div>
                )}

                {(report.additional_dataset_ids ?? []).map(dsId => (
                  <div key={dsId} style={{ display:'flex', alignItems:'center', gap:5, padding:'4px 7px', background:'var(--surface2)', borderRadius:5, marginBottom:3, fontSize:11 }}>
                    <span style={{ color:'var(--muted)' }}>◉</span>
                    <span style={{ flex:1, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{datasets[dsId]?.name ?? `Dataset #${dsId}`}</span>
                    {datasets[dsId]?.default_filter_expr && (
                      <span title={datasets[dsId].default_filter_expr!} style={{ fontSize:9, color:'var(--accent)', background:'rgba(99,102,241,.15)', borderRadius:3, padding:'1px 4px', flexShrink:0 }}>⊙ filtered</span>
                    )}
                    <button onClick={() => detachDataset(dsId)} title="Remove"
                      style={{ background:'none', border:'none', color:'var(--muted)', cursor:'pointer', fontSize:14, lineHeight:1, padding:'0 2px', flexShrink:0 }}>×</button>
                  </div>
                ))}

                <div style={{ position:'relative', marginTop:5 }}>
                  <button className="btn btn-ghost btn-sm" style={{ width:'100%', fontSize:10 }}
                    onClick={() => { setShowDsMenu(m => !m); if (!showDsMenu) datasetsApi.list().then(setAllDatasets) }}>
                    + Add Dataset
                  </button>
                  {showDsMenu && (
                    <div style={{ position:'absolute', top:'100%', left:0, right:0, zIndex:50, background:'var(--surface)', border:'1px solid var(--border)', borderRadius:6, maxHeight:160, overflowY:'auto', boxShadow:'0 4px 16px rgba(0,0,0,.25)', marginTop:2 }}>
                      {allDatasets
                        .filter(ds => ds.id !== report.dataset_id && !(report.additional_dataset_ids ?? []).includes(ds.id))
                        .map(ds => (
                          <button key={ds.id} onClick={() => { attachDataset(ds.id); setShowDsMenu(false) }}
                            style={{ display:'block', width:'100%', textAlign:'left', padding:'6px 10px', border:'none', background:'none', cursor:'pointer', fontSize:11, color:'var(--text)', fontFamily:'var(--sans)' }}
                            onMouseEnter={e => { e.currentTarget.style.background = 'var(--surface2)' }}
                            onMouseLeave={e => { e.currentTarget.style.background = 'none' }}>
                            {ds.name}
                          </button>
                        ))}
                      {allDatasets.filter(ds => ds.id !== report.dataset_id && !(report.additional_dataset_ids ?? []).includes(ds.id)).length === 0 && (
                        <div style={{ padding:'8px 10px', fontSize:11, color:'var(--muted)' }}>No more datasets to add</div>
                      )}
                    </div>
                  )}
                </div>
              </div>

              <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:8 }}>
                <span style={{ fontSize:10, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em' }}>Hierarchy</span>
                {dataset && (
                  <button className="btn btn-ghost btn-sm" onClick={autoGenHierarchy} style={{ fontSize:10, padding:'2px 6px' }}>
                    Auto
                  </button>
                )}
              </div>
              {!dataset
                ? <p style={{ fontSize:12, color:'var(--muted)', textAlign:'center', marginTop:20 }}>Attach a dataset to this report to browse columns.</p>
                : <HierarchyTree nodes={hierarchy} datasetId={dataset.id} onRefresh={refreshHierarchy} />
              }

              {dataset && (
                <div style={{ marginTop:16, borderTop:'1px solid var(--border)', paddingTop:12 }}>
                  <CalcColumnsPanel
                    datasetId={dataset.id}
                    columns={dataset.columns}
                    onChanged={setCalcCols}
                  />
                </div>
              )}

              {dataset && (
                <div style={{ marginTop:16, borderTop:'1px solid var(--border)', paddingTop:12 }}>
                  <ColumnFormatsPanel
                    datasetId={dataset.id}
                    columns={dataset.columns}
                    columnFormats={columnFormats}
                    onChanged={setColumnFormats}
                  />
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {/* Right section: top bar + page tabs + canvas */}
      <div style={{ flex:1, display:'flex', flexDirection:'column', overflow:'hidden' }}>

        {/* Top bar */}
        <div style={{ display:'flex', alignItems:'center', gap:10, padding:'10px 20px', borderBottom:'1px solid var(--border)', flexShrink:0, background:'var(--surface)' }}>
          <Link to="/reports" style={{ color:'var(--muted)', display:'flex', alignItems:'center', gap:4, fontSize:12, textDecoration:'none' }}>
            <ArrowLeft size={13} /> Reports
          </Link>
          <span style={{ color:'var(--border)' }}>|</span>
          <span style={{ fontWeight:700, fontSize:16 }}>{report.name}</span>
          {dataset && <span className="badge badge-categorical">{dataset.name}</span>}
          <div style={{ marginLeft:'auto', display:'flex', gap:8 }}>
            <button className="btn btn-ghost btn-sm" onClick={() => setEditMode(m => !m)}
              style={{ color: editMode ? 'var(--accent)' : 'var(--muted)' }}>
              {editMode ? <><Settings size={12}/> Edit mode</> : <><Eye size={12}/> View mode</>}
            </button>
          </div>
        </div>

        {/* Page tabs */}
        <div style={{ display:'flex', alignItems:'center', gap:3, padding:'0 16px', borderBottom:'1px solid var(--border)', flexShrink:0, background:'var(--surface)' }}>
          {report.pages
            .filter(page => editMode || page.page_type !== 'hidden')
            .map(page => {
              const typeIcon = page.page_type === 'hidden' ? ' [H]' : page.page_type === 'popup' ? ' [P]' : ''
              const isActive = page.id === activePage?.id
              return (
                <div key={page.id} style={{ display:'flex', alignItems:'center', borderBottom: isActive ? '2px solid var(--accent)' : '2px solid transparent', marginBottom:-1,
                  opacity: page.page_type === 'hidden' ? 0.55 : 1 }}>
                  {editPid === page.id ? (
                    <input value={editPname} onChange={e => setEditPname(e.target.value)}
                      onBlur={() => savePageName(page)} onKeyDown={e => e.key==='Enter' && savePageName(page)}
                      style={{ fontSize:12, padding:'5px 8px', width:90 }} autoFocus />
                  ) : (
                    <button
                      style={{ padding:'7px 13px', border:'none', background:'none', cursor:'pointer', fontSize:12,
                        color: isActive ? 'var(--accent)' : 'var(--muted)',
                        fontWeight: isActive ? 600 : 400, fontFamily:'var(--sans)' }}
                      onClick={() => { setActivePage(page); setSelectedW(null) }}
                      onDoubleClick={() => { setEditPid(page.id); setEditPname(page.name) }}
                    >{page.name}{typeIcon}</button>
                  )}
                  {editMode && report.pages.length > 1 && (
                    <button style={{ background:'none', border:'none', color:'var(--muted)', cursor:'pointer', padding:'0 4px', fontSize:13 }}
                      onClick={() => deletePage(page)}>x</button>
                  )}
                </div>
              )
            })}
          {editMode && (
            <button className="btn btn-ghost btn-sm" onClick={addPage} style={{ marginBottom:3, fontSize:11 }}>
              <Plus size={11}/> Page
            </button>
          )}
        </div>

        {/* Canvas + right panel */}
        <CrossFilterProvider>
        <div style={{ display:'flex', flex:1, gap:10, padding:'10px 16px', overflow:'hidden', minHeight:0 }}>

          {/* Canvas */}
          <div style={{ flex:1, overflowY:'auto', overflowX:'hidden' }}>
            <FilterBar />
            {activePage?.prompt_column && (
              <div style={{ display:'flex', alignItems:'center', gap:10, padding:'8px 12px', background:'var(--surface)', borderBottom:'1px solid var(--border)', flexShrink:0, marginBottom:8 }}>
                <span style={{ fontSize:12, fontWeight:600, color:'var(--muted)', whiteSpace:'nowrap' }}>
                  {activePage.prompt_label || ('Filter by ' + activePage.prompt_column)}
                </span>
                <input value={promptValues[activePage.id] ?? ''}
                  onChange={e => setPromptValues(p => ({ ...p, [activePage.id]: e.target.value }))}
                  placeholder={'Enter ' + activePage.prompt_column + '...'}
                  style={{ flex:1, fontSize:12, padding:'4px 8px' }} />
                {promptValues[activePage.id] && (
                  <button onClick={() => setPromptValues(p => { const n = {...p}; delete n[activePage.id]; return n })}
                    style={{ background:'none', border:'none', cursor:'pointer', color:'var(--muted)', fontSize:16 }}>x</button>
                )}
              </div>
            )}
            <div ref={canvasRef} style={{ position:'relative', minHeight:canvasH(pageWidgets), background:'var(--surface2)', borderRadius:'var(--radius)', border:'1px solid var(--border)' }}>
              {pageWidgets.length === 0 && editMode && (
                <div style={{ position:'absolute', inset:0, display:'flex', alignItems:'center', justifyContent:'center', flexDirection:'column', gap:10, color:'var(--muted)', pointerEvents:'none' }}>
                  <span style={{ fontSize:36, opacity:.2 }}>⊞</span>
                  <span style={{ fontSize:13 }}>Click a widget from the left panel to add it here</span>
                </div>
              )}
              {pageWidgets.map(widget => {
                const effLayout = localLayouts[widget.id] ?? widget.layout
                const isBeingDragged = dragging?.widgetId === widget.id || resizing?.widgetId === widget.id
                return (
                  <div key={widget.id} style={{ ...gridStyle(effLayout, containerW), padding: GAP/2,
                    transition: isBeingDragged ? 'none' : 'left .12s, top .12s, width .12s, height .12s',
                    zIndex: isBeingDragged ? 100 : 1 }}>
                    <WidgetRenderer
                      widget={{ ...widget, layout: effLayout }}
                      datasetId={report.dataset_id}
                      calculatedColumns={calcCols}
                      columnFormats={columnFormats}
                      datasets={datasets}
                      selected={selectedW?.id === widget.id}
                      onSelect={() => setSelectedW(widget)}
                      onDelete={() => deleteWidget(widget)}
                      editMode={editMode}
                      promptFilter={activePage && activePage.prompt_column && promptValues[activePage.id]
                        ? { column: activePage.prompt_column, value: promptValues[activePage.id] }
                        : null}
                      onDragStart={editMode ? handleDragStart(widget) : undefined}
                      onResizeStart={editMode ? handleResizeStart(widget) : undefined}
                      isDragging={isBeingDragged}
                    />
                  </div>
                )
              })}
            </div>
          </div>

          {/* Right: config panel */}
          {editMode && (
            <div style={{ width:245, flexShrink:0, background:'var(--surface)', border:'1px solid var(--border)', borderRadius:'var(--radius)', overflowY:'auto' }}>
              <div style={{ padding:'9px 13px', borderBottom:'1px solid var(--border)', display:'flex', alignItems:'center', justifyContent:'space-between' }}>
                <span style={{ fontSize:10, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em' }}>
                  {selectedW ? 'Widget' : 'Page'}
                </span>
                {selectedW && <button style={{ background:'none', border:'none', color:'var(--muted)', cursor:'pointer', fontSize:14 }} onClick={() => setSelectedW(null)}>x</button>}
              </div>
              {selectedW
                ? <WidgetConfigPanel widget={selectedW} columns={columns} datasets={datasets} primaryDatasetId={report.dataset_id} onUpdate={updateWidgetConfig} />
                : activePage && <PagePropertiesPanel page={activePage} columns={columns} onUpdate={updatePageProps} />
              }
            </div>
          )}
        </div>
        </CrossFilterProvider>
      </div>
    </div>
  )
}
