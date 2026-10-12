import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import { Database, ImageDown, LayoutDashboard, List, Network, Plug, Search, Shapes, Table2, TriangleAlert, Upload, X, Zap } from 'lucide-react'
import { Link, useSearchParams } from 'react-router-dom'
import toast from 'react-hot-toast'
import LoadError from '../components/ui/LoadError'
import LoadingState from '../components/ui/LoadingState'
import { lineageApi, type LineageGraph } from '../services/api'
import { useDirection } from '../contexts/DirectionContext'
import { useT } from '../i18n'
import { localDigits } from '../lib/arabicFormats'
import Graph, { NodeIcon, useNodeText, type GraphHandle } from './lineage/Graph'
import FilterChip from './lineage/FilterChip'
import { NO_FILTERS, buildModel, filtersOn, layout, matches, orderColumns, reach, sourceTypeName, type Col, type Depth, type Direction, type Filters } from './lineage/model'
import SidePanel from './lineage/SidePanel'
import ListView from './lineage/ListView'
import { downloadPng } from './lineage/exportPng'
import './lineage/lineage.css'

/**
 * Lineage (step 11, design `Lineage Redesign.html`): an explorer of where
 * every report gets its data. Sources feed datasets, datasets join or derive
 * from each other, reports read datasets.
 *
 * The toolbar finds any node (it is centred and pulses), and filters by node
 * type, source type, mode and "issues only" -- filters fade what fails them,
 * so the layout stays put. Clicking a card lights its whole path and fades the
 * rest. The graph pans, zooms and fits; a mini-map moves the view.
 *
 * The focus (Part B) shows Upstream only, Both or Downstream only, one hop
 * or all, and opens a side panel with what a change would touch. The same
 * estate reads as a table in List view. Arrow keys move between cards: up and
 * down in a column, across along the connections. Export as PNG draws the
 * graph on the client. `?focus=ds:5` opens with a node focused.
 *
 * Built from `GET /datasets/lineage/graph` only (lineage/model.ts). There is
 * no owner in the graph, so there is no Owner filter (backend row).
 */
export default function Lineage() {
  const t = useT()
  const { rtl } = useDirection()
  const text = useNodeText()
  const [graph, setGraph] = useState<LineageGraph | null>(null)
  const [loadError, setLoadError] = useState<unknown>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [hit, setHit] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [resOpen, setResOpen] = useState(false)
  const [resAt, setResAt] = useState(0)
  const [filters, setFilters] = useState<Filters>(NO_FILTERS)
  const [expanded, setExpanded] = useState<Partial<Record<Col, boolean>>>({})
  const [kb, setKb] = useState<string | null>(null)
  const [view, setView] = useState<'graph' | 'list'>('graph')
  const [dir, setDir] = useState<Direction>('both')
  const [depth, setDepth] = useState<Depth>('all')
  const [params] = useSearchParams()
  const g = useRef<GraphHandle>(null)

  // A failed load is said as such, never drawn as an empty estate.
  const load = useCallback(() => {
    setLoadError(null)
    lineageApi.graph().then(setGraph).catch(e => setLoadError(e ?? new Error('failed')))
  }, [])
  useEffect(load, [load])

  const model = useMemo(() => (graph ? buildModel(graph, t('lin2.uploads')) : null), [graph, t])
  const cols = useMemo(() => (model ? orderColumns(model) : [[], [], []]), [model])
  const keep = useMemo(() => new Set([selected, hit].filter((k): k is string => !!k)), [selected, hit])
  const lay = useMemo(() => layout(cols, expanded, keep, rtl), [cols, expanded, keep, rtl])
  const lit = useMemo(() => (model ? reach(model.edges, selected, dir, depth) : null), [model, selected, dir, depth])

  // A link can open the page focused on a node (`?focus=ds:5`).
  const linked = params.get('focus')
  useEffect(() => {
    if (!model || !linked || !model.byKey[linked]) return
    setSelected(linked); setKb(linked)
    requestAnimationFrame(() => g.current?.centerOn(linked))
  }, [model, linked])

  // A search hit pulses for a moment.
  useEffect(() => {
    if (!hit) return
    const id = setTimeout(() => setHit(null), 2400)
    return () => clearTimeout(id)
  }, [hit])

  if (loadError) return <div className="dl-ln"><LoadError what={t('nav.lineage')} error={loadError} onRetry={load} /></div>
  if (!graph || !model) {
    return (
      <div className="dl-ln" aria-busy="true">
        <header className="dl-ln__head">
          <h1 className="dl-page-title">{t('nav.lineage')}</h1>
          <p className="dl-page-head__sub">{t('lin2.sub')}</p>
        </header>
        <div className="dl-ln-skel" aria-hidden>
          {[4, 7, 6].map((n, c) => <div key={c}>{Array.from({ length: n }, (_, i) => <i key={i} />)}</div>)}
        </div>
        <LoadingState label={t('lin2.loading')} />
      </div>
    )
  }

  // Nothing connected or built yet: say what will appear, and how to start.
  if (model.nodes.length === 0) {
    return (
      <div className="dl-ln">
        <header className="dl-ln__head">
          <h1 className="dl-page-title">{t('nav.lineage')}</h1>
          <p className="dl-page-head__sub">{t('lin2.sub')}</p>
        </header>
        <div className="dl-ln-empty">
          <div className="dl-ln-empty__art" aria-hidden>
            <span className="dl-ln-ic dl-ln-ic--src"><Database size={22} /></span><i />
            <span className="dl-ln-ic dl-ln-ic--ds"><Table2 size={22} /></span><i />
            <span className="dl-ln-ic dl-ln-ic--rep"><LayoutDashboard size={22} /></span>
          </div>
          <h2>{t('lin2.empty.title')}</h2>
          <p>{t('lin2.empty.body')}</p>
          <div className="dl-ln-empty__acts">
            <Link to="/connections" className="btn btn-primary"><Plug size={16} aria-hidden /> {t('lin2.empty.connect')}</Link>
            <Link to="/upload" className="btn btn-ghost"><Upload size={16} aria-hidden /> {t('lin2.empty.upload')}</Link>
          </div>
        </div>
      </div>
    )
  }

  const q = query.trim().toLowerCase()
  const results = q ? model.nodes.filter(n => n.name.toLowerCase().includes(q)).slice(0, 7) : []
  const pick = (key: string) => {
    setQuery(model.byKey[key]?.name ?? ''); setResOpen(false); setHit(key)
    // After the layout has unfolded it, centre it.
    requestAnimationFrame(() => g.current?.centerOn(key))
  }
  const onSearchKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setResOpen(true); setResAt(a => Math.min(a + 1, results.length - 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setResAt(a => Math.max(a - 1, 0)) }
    else if (e.key === 'Enter' && results[resAt]) { e.preventDefault(); pick(results[resAt].key) }
    else if (e.key === 'Escape') { if (resOpen) setResOpen(false); else setQuery('') }
  }

  const select = (key: string) => { setSelected(s => (s === key ? null : key)); setKb(key) }
  const showInGraph = (key: string) => {
    setView('graph'); setSelected(key); setKb(key)
    requestAnimationFrame(() => requestAnimationFrame(() => g.current?.centerOn(key)))
  }

  // Arrow keys: up and down within a column, across along the connections
  // (the flow mirrors in right-to-left). Escape clears the focus.
  const onNodeKey = (e: KeyboardEvent<HTMLButtonElement>, key: string) => {
    const n = model.byKey[key]
    let next: string | undefined
    if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
      const col = cols[n.col].filter(x => lay.visible[x.key])
      const i = col.findIndex(x => x.key === key)
      next = col[i + (e.key === 'ArrowDown' ? 1 : -1)]?.key
    } else if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
      const downward = (e.key === 'ArrowRight') !== rtl
      const near = model.edges.filter(x => (downward ? x.from === key : x.to === key)).map(x => (downward ? x.to : x.from))
        .filter(k => lay.visible[k]).sort((a, b) => lay.y[a] - lay.y[b])
      next = near[0]
    } else if (e.key === 'Escape') { setSelected(null); return }
    if (!next) return
    e.preventDefault()
    setKb(next)
    g.current?.focusNode(next)
  }

  const exportPng = async () => {
    try {
      await downloadPng(g.current?.svg() ?? '', 'lineage.png')
      toast.success(t('lin2.exported'))
    } catch { toast.error(t('lin2.exportFailed')) }
  }
  const sel = selected ? model.byKey[selected] : null
  const issues = model.nodes.filter(n => n.issue).length
  const sourceTypes = [...new Set(model.nodes.filter(n => n.col === 0).map(n => n.sourceType ?? ''))].filter(Boolean)
  const typeLabel = filters.types.size
    ? [...filters.types].sort().map(c => t((['lineage.sources', 'lineage.datasets', 'lineage.reports'] as const)[c])).join(', ')
    : t('lin2.f.type')
  const srcName = (s: string) => (s === 'file' ? t('lin2.file') : sourceTypeName(s))
  const tabKey = kb && lay.visible[kb] ? kb : selected ?? cols[0][0]?.key ?? cols[1][0]?.key ?? null

  return (
    <div className="dl-ln">
      <header className="dl-ln__head">
        <h1 className="dl-page-title">{t('nav.lineage')}</h1>
        <p className="dl-page-head__sub">{t('lin2.sub')}</p>
      </header>

      <div className="dl-ln-tools">
        <div className="dl-ln-sw">
          <label className="dl-ln-search">
            <Search size={16} aria-hidden />
            <input value={query} role="combobox" aria-expanded={resOpen && !!q} aria-controls="dl-ln-res" aria-autocomplete="list"
              aria-activedescendant={resOpen && results[resAt] ? `dl-ln-res-${resAt}` : undefined}
              aria-label={t('lin2.search')} placeholder={t('lin2.search')} autoComplete="off"
              onChange={e => { setQuery(e.target.value); setResOpen(true); setResAt(0) }}
              onFocus={() => setResOpen(true)} onBlur={() => setTimeout(() => setResOpen(false), 120)} onKeyDown={onSearchKey} />
            {query && (
              <button type="button" className="dl-ln-ib dl-ln-ib--sm" aria-label={t('lin2.clearSearch')} title={t('lin2.clearSearch')}
                onClick={() => { setQuery(''); setResOpen(false) }}><X size={14} aria-hidden /></button>
            )}
          </label>
          {resOpen && q && (
            <div className="dl-ln-res" id="dl-ln-res" role="listbox" aria-label={t('lin2.search')}>
              {results.length ? results.map((n, i) => (
                <div key={n.key} id={`dl-ln-res-${i}`} role="option" aria-selected={i === resAt}
                  className={`dl-ln-res__o${i === resAt ? ' is-act' : ''}`}
                  onMouseDown={e => { e.preventDefault(); pick(n.key) }} onMouseEnter={() => setResAt(i)}>
                  <NodeIcon n={n} size={24} /><b dir="auto">{n.name}</b><small>{text.kind(n)}</small>
                </div>
              )) : <p className="dl-ln-res__none">{t('lin2.noMatch')}</p>}
            </div>
          )}
        </div>
        <FilterChip multi icon={<Shapes size={15} aria-hidden />} label={typeLabel} active={filters.types.size > 0}
          options={([0, 1, 2] as Col[]).map(c => ({ value: String(c), checked: filters.types.has(c),
            label: t((['lineage.sources', 'lineage.datasets', 'lineage.reports'] as const)[c]) }))}
          onPick={v => setFilters(f => { const types = new Set(f.types); const c = Number(v) as Col; if (types.has(c)) types.delete(c); else types.add(c); return { ...f, types } })} />
        {sourceTypes.length > 0 && (
          <FilterChip icon={<Database size={15} aria-hidden />} label={filters.sourceType ? srcName(filters.sourceType) : t('lin2.f.source')}
            active={!!filters.sourceType}
            options={sourceTypes.map(s => ({ value: s, label: srcName(s), checked: filters.sourceType === s }))}
            onPick={v => setFilters(f => ({ ...f, sourceType: f.sourceType === v ? null : v }))} />
        )}
        <FilterChip icon={<Zap size={15} aria-hidden />} active={!!filters.mode}
          label={filters.mode ? t(filters.mode === 'directquery' ? 'lineage.directquery' : 'lineage.import') : t('lin2.f.mode')}
          options={[{ value: 'import', label: t('lineage.import'), checked: filters.mode === 'import' },
            { value: 'directquery', label: t('lineage.directquery'), checked: filters.mode === 'directquery' }]}
          onPick={v => setFilters(f => ({ ...f, mode: f.mode === v ? null : v as Filters['mode'] }))} />
        <button type="button" className={`dl-ln-chip${filters.issues ? ' is-on' : ''}`} aria-pressed={filters.issues}
          onClick={() => setFilters(f => ({ ...f, issues: !f.issues }))}>
          <TriangleAlert size={15} aria-hidden /><span>{t('lin2.f.issues')}</span>
          <b className="dl-ln-chip__n" dir="ltr">{localDigits(String(issues))}</b>
        </button>
      </div>

      <div className="dl-ln-row2">
        <div className="dl-ln-seg" role="radiogroup" aria-label={t('lin2.view')}>
          {(['graph', 'list'] as const).map(v => (
            <button key={v} type="button" role="radio" aria-checked={view === v} onClick={() => setView(v)}>
              {v === 'graph' ? <Network size={15} aria-hidden /> : <List size={15} aria-hidden />}{t(`lin2.view.${v}`)}
            </button>
          ))}
        </div>
        {view === 'graph' && (
          <button type="button" className="dl-ln-chip" onClick={() => void exportPng()}>
            <ImageDown size={15} aria-hidden /><span>{t('lin2.export')}</span>
          </button>
        )}
      </div>

      {sel && view === 'graph' && (
        <div className="dl-ln-focus">
          <span className="dl-ln-focus__l">{t('lin2.focused')}</span>
          <span className="dl-ln-focus__chip">
            <NodeIcon n={sel} size={22} /><b dir="auto">{sel.name}</b>
            <button type="button" className="dl-ln-ib dl-ln-ib--sm" aria-label={t('lin2.clearFocus')} title={t('lin2.clearFocus')}
              onClick={() => setSelected(null)}><X size={14} aria-hidden /></button>
          </span>
          <span className="dl-ln-grow" />
          <div className="dl-ln-seg" role="radiogroup" aria-label={t('lin2.dir')}>
            {(['up', 'both', 'down'] as const).map(d => (
              <button key={d} type="button" role="radio" aria-checked={dir === d} onClick={() => setDir(d)}>{t(`lin2.dir.${d}`)}</button>
            ))}
          </div>
          <div className="dl-ln-seg" role="radiogroup" aria-label={t('lin2.depth')}>
            {(['one', 'all'] as const).map(d => (
              <button key={d} type="button" role="radio" aria-checked={depth === d} onClick={() => setDepth(d)}>{t(`lin2.depth.${d}`)}</button>
            ))}
          </div>
        </div>
      )}

      <div className="dl-ln-body">
        {view === 'graph' ? (
          <Graph ref={g} model={model} cols={cols} lay={lay} lit={lit} selected={selected} hit={hit} filters={filters} rtl={rtl}
            onSelect={select} onMore={c => setExpanded(x => ({ ...x, [c]: !x[c] }))} tabKey={tabKey} onNodeKey={onNodeKey} />
        ) : (
          <ListView model={model} onShow={showInGraph}
            nodes={cols.flat().filter(n => !filtersOn(filters) || matches(model, n, filters))} />
        )}
        {sel && view === 'graph' && (
          <SidePanel model={model} node={sel} onSelect={k => { setSelected(k); setKb(k); g.current?.centerOn(k) }} onClose={() => setSelected(null)} />
        )}
      </div>
    </div>
  )
}
