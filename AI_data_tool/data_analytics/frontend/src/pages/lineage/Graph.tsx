import { forwardRef, useCallback, useEffect, useImperativeHandle, useLayoutEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import { ChevronsDown, ChevronsUp, Database, Files, LayoutDashboard, Minus, Plus, Scan, Table2, TriangleAlert, Unlink } from 'lucide-react'
import { useT } from '../../i18n'
import { localDigits } from '../../lib/arabicFormats'
import { lineageSvg } from './exportPng'
import { CW, NH, WIDTH, filtersOn, matches, sourceTypeName, type Col, type Filters, type LNode, type Layout, type Model } from './model'

/**
 * The Lineage graph (step 11; design `graph()` in lin.js): a canvas that pans
 * (drag) and zooms (scroll, the + / − buttons, Fit), with the three column
 * heads kept in view, a legend, and a mini-map that moves the view.
 *
 * Every edge leaves and enters its card at its own point, so a card with many
 * edges fans them out; a join or derivation between datasets is dashed and
 * loops on the datasets' far side; an edge out of a failing dataset is red.
 * Labels (extract / join / reads) show on hover. The focus lights its path
 * and fades the rest; filters fade what fails them, so nothing moves.
 *
 * In right-to-left the flow mirrors (sources on the right); names and numbers
 * keep their own direction.
 */

export interface GraphHandle {
  fit: () => void
  centerOn: (key: string) => void
  focusNode: (key: string) => void
  /** The drawing as it is, as one SVG with the theme's colours, for Export PNG. */
  svg: () => string
}

const Z_MIN = 0.35, Z_MAX = 2
const headKeys = [['lineage.sources', Database], ['lineage.datasets', Table2], ['lineage.reports', LayoutDashboard]] as const

export const KIND_KEY = ['lin2.kind.source', 'lin2.kind.dataset', 'lin2.kind.report'] as const

export function NodeIcon({ n, size = 32 }: { n: LNode; size?: number }) {
  const Icon = n.col === 0 ? (n.sourceType === 'file' ? Files : Database) : n.col === 1 ? Table2 : LayoutDashboard
  const tone = n.col === 0 ? (n.sourceType === 'file' ? 'file' : 'src') : n.col === 1 ? 'ds' : 'rep'
  return (
    <span className={`dl-ln-ic dl-ln-ic--${tone}`} style={{ width: size, height: size }} aria-hidden>
      <Icon size={Math.round(size * 0.5)} />
    </span>
  )
}

export function useNodeText() {
  const t = useT()
  return {
    kind: (n: LNode) => t(KIND_KEY[n.col]),
    sub: (n: LNode) => n.col === 0 ? (n.sourceType === 'file' ? t('lin2.file') : sourceTypeName(n.sourceType))
      : n.col === 2 ? localDigits(t('lin2.reads', { n: n.reads ?? 0 })) : '',
    issue: (n: LNode) => n.issue ? t(`lin2.iss.${n.issue}`) : '',
    mode: (n: LNode) => t(n.mode === 'directquery' ? 'lineage.directquery' : 'lineage.import'),
  }
}

const Graph = forwardRef<GraphHandle, {
  model: Model
  cols: LNode[][]
  lay: Layout
  lit: { nodes: Set<string>; edges: Set<number> } | null
  selected: string | null
  hit: string | null
  filters: Filters
  rtl: boolean
  onSelect: (key: string) => void
  onMore: (col: Col) => void
  /** The card that takes Tab (the roving focus). */
  tabKey: string | null
  onNodeKey?: (e: KeyboardEvent<HTMLButtonElement>, key: string) => void
}>(function Graph({ model, cols, lay, lit, selected, hit, filters, rtl, onSelect, onMore, tabKey, onNodeKey }, ref) {
  const t = useT()
  const text = useNodeText()
  const cv = useRef<HTMLDivElement>(null)
  const world = useRef<HTMLDivElement>(null)
  const heads = useRef<HTMLDivElement>(null)
  const vp = useRef<SVGRectElement>(null)
  const nodeEls = useRef<Record<string, HTMLButtonElement | null>>({})
  const view = useRef({ z: 1, tx: 0, ty: 0 })
  const [pct, setPct] = useState(100)
  const W = WIDTH, H = lay.height

  const apply = useCallback(() => {
    const { z, tx, ty } = view.current
    if (world.current) world.current.style.transform = `translate(${tx}px, ${ty}px) scale(${z})`
    heads.current?.querySelectorAll<HTMLElement>('[data-cx]').forEach(h => { h.style.transform = `translateX(${tx + Number(h.dataset.cx) * z}px)` })
    const box = cv.current
    if (box && vp.current) {
      vp.current.setAttribute('x', String(-tx / z)); vp.current.setAttribute('y', String(-ty / z))
      vp.current.setAttribute('width', String(box.clientWidth / z)); vp.current.setAttribute('height', String(box.clientHeight / z))
    }
    setPct(Math.round(z * 100))
  }, [])

  const fit = useCallback(() => {
    const box = cv.current
    if (!box) return
    const z = Math.max(Z_MIN, Math.min(1, (box.clientWidth - 40) / W, (box.clientHeight - 20) / H))
    view.current = { z, tx: (box.clientWidth - W * z) / 2, ty: 0 }
    apply()
  }, [W, H, apply])

  const centerOn = useCallback((key: string) => {
    const box = cv.current
    const n = model.byKey[key]
    if (!box || !n || lay.y[key] == null) return
    const z = Math.max(view.current.z, 0.9)
    view.current = { z, tx: box.clientWidth / 2 - (lay.x(n.col) + CW / 2) * z, ty: Math.min(0, box.clientHeight / 2 - (lay.y[key] + NH / 2) * z) }
    apply()
  }, [model, lay, apply])

  useImperativeHandle(ref, () => ({
    fit, centerOn,
    focusNode: key => {
      nodeEls.current[key]?.focus({ preventScroll: true })
      // Keep the card in view as the keyboard moves through the graph.
      const box = cv.current, n = model.byKey[key]
      if (!box || !n || lay.y[key] == null) return
      const { z, tx, ty } = view.current
      const x = tx + lay.x(n.col) * z, y = ty + lay.y[key] * z
      if (x < 0 || y < 40 || x + CW * z > box.clientWidth || y + NH * z > box.clientHeight) centerOn(key)
    },
    svg: () => {
      const css = getComputedStyle(cv.current ?? document.documentElement)
      const v = (name: string) => css.getPropertyValue(name).trim()
      return lineageSvg(model, cols, lay, edges.map(x => ({ d: x.d, on: x.on, dim: x.dim, dashed: x.e.kind === 'join' || x.e.kind === 'derived', bad: x.e.bad })),
        lit?.nodes ?? null,
        { bg: v('--bg'), surface: v('--surface'), border: v('--border'), edge: v('--mc-border-strong'), accent: v('--accent'), danger: v('--danger'),
          text: v('--text'), muted: v('--muted'), font: css.fontFamily },
        headKeys.map(([k], c) => `${t(k)} ${cols[c].length}`))
    },
  }), [fit, centerOn, model, cols, lay, lit, t, filters, rtl])

  // Fit once the first drawing is there; later changes keep the reader's view.
  const fitted = useRef(false)
  useLayoutEffect(() => {
    if (fitted.current || !cv.current) return
    fitted.current = true
    fit()
  }, [fit])
  useLayoutEffect(() => { apply() }, [apply, lay])

  // Zoom with the wheel, around the pointer. Not passive: the page must not scroll too.
  const zoomAt = useCallback((factor: number, px: number, py: number) => {
    const { z, tx, ty } = view.current
    const nz = Math.max(Z_MIN, Math.min(Z_MAX, z * factor))
    view.current = { z: nz, tx: px - (px - tx) * (nz / z), ty: py - (py - ty) * (nz / z) }
    apply()
  }, [apply])
  useEffect(() => {
    const box = cv.current
    if (!box) return
    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      const r = box.getBoundingClientRect()
      zoomAt(e.deltaY < 0 ? 1.1 : 1 / 1.1, e.clientX - r.left, e.clientY - r.top)
    }
    box.addEventListener('wheel', onWheel, { passive: false })
    return () => box.removeEventListener('wheel', onWheel)
  }, [zoomAt])
  const zoomCentre = (factor: number) => { const box = cv.current; if (box) zoomAt(factor, box.clientWidth / 2, box.clientHeight / 2) }

  // Drag the background to pan.
  const drag = useRef<{ x: number; y: number; tx: number; ty: number; id: number } | null>(null)
  const onDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if ((e.target as HTMLElement).closest('button, a, [role="group"]') || e.button !== 0) return
    drag.current = { x: e.clientX, y: e.clientY, tx: view.current.tx, ty: view.current.ty, id: e.pointerId }
    e.currentTarget.setPointerCapture?.(e.pointerId)
    e.currentTarget.classList.add('is-dragging')
  }
  const onMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const d = drag.current
    if (!d) return
    view.current = { ...view.current, tx: d.tx + e.clientX - d.x, ty: d.ty + e.clientY - d.y }
    apply()
  }
  const onUp = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!drag.current) return
    e.currentTarget.releasePointerCapture?.(drag.current.id)
    e.currentTarget.classList.remove('is-dragging')
    drag.current = null
  }

  // The mini-map moves the view to where it was clicked.
  const onMini = (e: React.MouseEvent<SVGSVGElement>) => {
    const box = cv.current
    const svg = e.currentTarget
    if (!box) return
    const r = svg.getBoundingClientRect()
    const s = Math.min(r.width / W, r.height / H)
    const ox = (r.width - W * s) / 2, oy = (r.height - H * s) / 2
    const wx = (e.clientX - r.left - ox) / s, wy = (e.clientY - r.top - oy) / s
    const { z } = view.current
    view.current = { z, tx: box.clientWidth / 2 - wx * z, ty: box.clientHeight / 2 - wy * z }
    apply()
  }

  const fo = filtersOn(filters)
  const isDim = (n: LNode) => !!(lit && !lit.nodes.has(n.key)) || (fo && !matches(model, n, filters) && !(lit?.nodes.has(n.key)))

  // Each card spreads its edges over its height, sorted so they do not cross at the card.
  const edges = useMemo(() => {
    const outs: Record<string, number[]> = {}, ins: Record<string, number[]> = {}
    model.edges.forEach((e, i) => { (outs[e.from] ??= []).push(i); (ins[e.to] ??= []).push(i) })
    const yOf = (k: string) => lay.y[k] ?? 0
    for (const l of Object.values(outs)) l.sort((a, b) => yOf(model.edges[a].to) - yOf(model.edges[b].to))
    for (const l of Object.values(ins)) l.sort((a, b) => yOf(model.edges[a].from) - yOf(model.edges[b].from))
    const port = (list: number[], i: number) => {
      const k = list.indexOf(i), n = list.length
      return n < 2 ? 0 : (k - (n - 1) / 2) * Math.min(8, (NH - 16) / (n - 1))
    }
    return model.edges.map((e, i) => {
      const A = model.byKey[e.from], B = model.byKey[e.to]
      const y1 = yOf(e.from) + NH / 2 + (lay.visible[e.from] ? port(outs[e.from], i) : 0)
      const y2 = yOf(e.to) + NH / 2 + (lay.visible[e.to] ? port(ins[e.to], i) : 0)
      let d: string, mx: number
      if (A.col === B.col) {
        const x = rtl ? lay.x(A.col) : lay.x(A.col) + CW
        const bx = rtl ? x - 46 : x + 46
        d = `M${x} ${y1}C${bx} ${y1} ${bx} ${y2} ${x} ${y2}`
        mx = rtl ? x - 40 : x + 40
      } else {
        const x1 = rtl ? lay.x(A.col) : lay.x(A.col) + CW
        const x2 = rtl ? lay.x(B.col) + CW : lay.x(B.col)
        const m = (x1 + x2) / 2
        d = `M${x1} ${y1}C${m} ${y1} ${m} ${y2} ${x2} ${y2}`
        mx = m
      }
      const on = !!lit?.edges.has(i)
      const dim = (!!lit && !on) || (fo && !(matches(model, A, filters) && matches(model, B, filters)) && !on)
      return { i, d, mx, my: (y1 + y2) / 2, on, dim, e }
    })
  }, [model, lay, lit, rtl, filters, fo])

  const countOf = (c: Col) => cols[c].length

  return (
    <div className="dl-ln-cv" ref={cv} aria-label={t('lin2.canvas')} role="region"
      onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp} onPointerCancel={onUp}>
      <div className="dl-ln-heads" ref={heads} aria-hidden>
        {headKeys.map(([k, Icon], c) => (
          <span key={k} className="dl-ln-ch" data-cx={lay.x(c as Col)}>
            <Icon size={14} />{t(k)}<span className="dl-ln-ch__n" dir="ltr">{localDigits(String(countOf(c as Col)))}</span>
          </span>
        ))}
      </div>
      <div className="dl-ln-world" ref={world} style={{ width: W, height: H }} data-testid="lineage-world">
        <svg width={W} height={H} className="dl-ln-edges" aria-hidden>
          {edges.map(x => (
            <g key={x.i} className={`dl-ln-e dl-ln-e--${x.e.kind}${x.on ? ' is-on' : ''}${x.dim ? ' is-dim' : ''}${x.e.bad && !x.on ? ' is-bad' : ''}`}
              data-from={x.e.from} data-to={x.e.to}>
              <path className="dl-ln-e__hit" d={x.d} />
              <path className="dl-ln-e__v" d={x.d} />
              <text x={x.mx} y={x.my - 4} textAnchor="middle">{t(`lin2.edge.${x.e.kind}`)}</text>
            </g>
          ))}
        </svg>
        {cols.flat().filter(n => lay.visible[n.key]).map(n => {
          const on = !!lit?.nodes.has(n.key)
          const up = model.edges.filter(e => e.to === n.key).length
          const down = model.edges.filter(e => e.from === n.key).length
          const cls = ['dl-ln-n', n.key === selected ? 'is-sel' : on ? 'is-on' : '', isDim(n) ? 'is-dim' : '', hit === n.key ? 'is-hit' : '']
          return (
            <button key={n.key} type="button" ref={el => { nodeEls.current[n.key] = el }}
              className={cls.filter(Boolean).join(' ')} data-key={n.key}
              style={{ left: lay.x(n.col), top: lay.y[n.key] }}
              aria-pressed={n.key === selected} tabIndex={n.key === tabKey ? 0 : -1}
              aria-label={localDigits(t('lin2.aria', { name: n.name, kind: text.kind(n), up, down }))}
              onClick={() => onSelect(n.key)} onKeyDown={e => onNodeKey?.(e, n.key)}>
              <NodeIcon n={n} />
              <span className="dl-ln-n__tx">
                <span className="dl-ln-n__nm" dir="auto" title={n.name}>{n.name}</span>
                <span className="dl-ln-n__sb">
                  {n.col === 1 ? (
                    <>
                      <span className={`dl-ln-mode dl-ln-mode--${n.mode}`}>{text.mode(n)}</span>
                      {!!n.steps && <span>{localDigits(t('lin2.steps', { n: n.steps }))}</span>}
                    </>
                  ) : <span dir="auto">{text.sub(n)}</span>}
                </span>
              </span>
              {n.issue && (
                <span className={`dl-ln-iss dl-ln-iss--${n.issue}`} title={text.issue(n)}>
                  {n.issue === 'orphan' ? <Unlink size={15} aria-hidden /> : <TriangleAlert size={15} aria-hidden />}
                </span>
              )}
              {n.col === 1 && <span className={`dl-ln-dot dl-ln-dot--${n.status}`} aria-hidden />}
            </button>
          )
        })}
        {lay.more.map(m => (
          <button key={m.col} type="button" className="dl-ln-more" style={{ left: lay.x(m.col), top: m.y }} onClick={() => onMore(m.col)}>
            {m.hidden ? <ChevronsDown size={15} aria-hidden /> : <ChevronsUp size={15} aria-hidden />}
            {m.hidden ? localDigits(t(m.col === 1 ? 'lin2.moreDatasets' : 'lin2.moreReports', { n: m.hidden })) : t('lin2.fewer')}
          </button>
        ))}
      </div>
      <div className="dl-ln-legend" aria-hidden>
        <span><i />{t('lin2.lg.flow')}</span><span><i className="is-join" />{t('lin2.lg.join')}</span><span><i className="is-bad" />{t('lin2.lg.broken')}</span>
      </div>
      <div className="dl-ln-zoom" role="group" aria-label={t('lin2.zoom')}>
        <button type="button" className="dl-ln-ib" aria-label={t('lin2.zoomIn')} title={t('lin2.zoomIn')} onClick={() => zoomCentre(1.2)}><Plus size={16} aria-hidden /></button>
        <span className="dl-ln-zoom__pc" dir="ltr" data-testid="zoom-pct">{localDigits(`${pct}%`)}</span>
        <button type="button" className="dl-ln-ib" aria-label={t('lin2.zoomOut')} title={t('lin2.zoomOut')} onClick={() => zoomCentre(1 / 1.2)}><Minus size={16} aria-hidden /></button>
        <button type="button" className="dl-ln-ib" aria-label={t('lin2.fit')} title={t('lin2.fit')} onClick={fit}><Scan size={16} aria-hidden /></button>
      </div>
      <div className="dl-ln-mini" title={t('lin2.minimap')}>
        <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid meet" onClick={onMini} aria-label={t('lin2.minimap')} role="img">
          {cols.flat().filter(n => lay.visible[n.key]).map(n => (
            <rect key={n.key} x={lay.x(n.col)} y={lay.y[n.key]} width={CW} height={NH} rx={10}
              className={lit?.nodes.has(n.key) ? 'is-on' : n.issue && n.issue !== 'orphan' ? 'is-iss' : undefined}
              opacity={lit && !lit.nodes.has(n.key) ? 0.35 : 1} />
          ))}
          <rect ref={vp} className="dl-ln-mini__vp" x={0} y={0} width={10} height={10} rx={8} />
        </svg>
      </div>
    </div>
  )
})

export default Graph
