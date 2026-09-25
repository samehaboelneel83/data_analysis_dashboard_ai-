import { useMemo, useState } from 'react'
import type { ChartRendererProps } from './types'
import { fmtStr } from '../chartUtils'
import type { CalcColumnFormat } from '../../../services/api'

/**
 * Six hierarchy layouts over ONE shaped contract.
 *
 * `shape_hierarchy` returns a nested `{name, value, children, omitted}` tree for
 * all of tree / sunburst / icicle / dendrogram / org / circle pack, so these
 * renderers differ only in how they draw the same numbers. That is deliberate, and the same rule
 * small multiples follows: a layout that computed its own totals would be a
 * second aggregation path, and the two would drift.
 *
 * Drawn with divs and inline SVG — no new charting library, so the air-gapped
 * bundle is unchanged.
 */

interface Node {
  name: string
  value: number | null
  children: Node[]
  depth: number
  omitted?: number
  is_other?: boolean
}

const INDENT = 14

function nodeCount(node: Node): number {
  return 1 + (node.children ?? []).reduce((n, c) => n + nodeCount(c), 0)
}

// ── Tree / indented list, with multi-select ─────────────────────────────────

/**
 * The tree, the tree grid and the "tree list box" are one control: an indented
 * list that expands, and whose checked nodes broadcast as a multi-value filter
 * exactly as a slicer's do. Splitting them into three widgets would have meant
 * three renderers over identical data differing only in whether a checkbox was
 * drawn.
 */
function TreeRows({ node, rtl, fmt, checked, onToggle, selectable }: {
  node: Node
  rtl: boolean
  fmt?: CalcColumnFormat | null
  checked: Set<string>
  onToggle: (name: string) => void
  selectable: boolean
}) {
  // Collapsed by default below the second level: an org chart that opens fully
  // expanded is a wall, and the reader has not asked for the leaves yet.
  const [open, setOpen] = useState(node.depth < 2)
  const kids = node.children ?? []
  const hasKids = kids.length > 0

  return (
    <div>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 4,
        paddingInlineStart: node.depth * INDENT, fontSize: 12, lineHeight: '20px',
      }}>
        {hasKids ? (
          <button onClick={() => setOpen(o => !o)}
            aria-label={open ? `Collapse ${node.name}` : `Expand ${node.name}`}
            aria-expanded={open}
            style={{
              border: 'none', background: 'none', cursor: 'pointer', padding: 0,
              width: 12, color: 'var(--muted)', fontSize: 9,
            }}>
            {open ? '▼' : '▶'}
          </button>
        ) : <span style={{ width: 12 }} />}

        {selectable && (
          <input type="checkbox" checked={checked.has(node.name)}
            onChange={() => onToggle(node.name)}
            aria-label={`Select ${node.name}`}
            style={{ margin: 0, cursor: 'pointer' }} />
        )}

        <span style={{
          flex: 1, overflow: 'hidden', textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
          fontStyle: node.is_other ? 'italic' : undefined,
          color: node.is_other ? 'var(--muted)' : undefined,
        }}>{node.name}</span>

        {node.value != null && (
          <span style={{ fontFamily: 'var(--mono)', color: 'var(--muted)', fontSize: 11 }}>
            {fmtStr(node.value, fmt)}
          </span>
        )}
      </div>

      {open && kids.map((c, i) => (
        <TreeRows key={`${c.name}-${i}`} node={c} rtl={rtl} fmt={fmt}
          checked={checked} onToggle={onToggle} selectable={selectable} />
      ))}

      {/* A node whose children were capped says so where they would have been,
          rather than looking like a leaf. */}
      {open && !!node.omitted && !kids.some(k => k.is_other) && (
        <div style={{
          paddingInlineStart: (node.depth + 1) * INDENT + 16,
          fontSize: 11, color: 'var(--muted)', fontStyle: 'italic',
        }}>
          + {node.omitted} more not shown
        </div>
      )}
    </div>
  )
}

// ── Icicle: nested rectangles, one row per level ────────────────────────────

function Icicle({ node, fmt }: { node: Node; fmt?: CalcColumnFormat | null }) {
  const rows: Node[][] = []
  const collect = (n: Node, d: number) => {
    (rows[d] ??= []).push(n)
    n.children?.forEach(c => collect(c, d + 1))
  }
  node.children?.forEach(c => collect(c, 0))
  const total = node.value || rows[0]?.reduce((s, n) => s + (n.value ?? 0), 0) || 1

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 2, padding: 4 }}>
      {rows.map((row, d) => (
        <div key={d} style={{ display: 'flex', gap: 1, height: 26 }}>
          {row.map((n, i) => {
            // Width is the node's share of the ROOT, so every level spans the
            // same axis and a child sits under its parent's extent.
            const pct = Math.max(((n.value ?? 0) / total) * 100, 0.4)
            return (
              <div key={i} title={`${n.name}: ${fmtStr(n.value, fmt)}`}
                style={{
                  width: `${pct}%`, background: 'var(--accent)',
                  opacity: 1 - d * 0.13, borderRadius: 2, overflow: 'hidden',
                  display: 'flex', alignItems: 'center', paddingInline: 4,
                  fontSize: 10, color: '#fff', whiteSpace: 'nowrap',
                }}>
                {pct > 6 ? n.name : ''}
              </div>
            )
          })}
        </div>
      ))}
    </div>
  )
}

// ── Sunburst: concentric rings ──────────────────────────────────────────────

function arc(cx: number, cy: number, r0: number, r1: number,
             a0: number, a1: number): string {
  const p = (r: number, a: number) =>
    [cx + r * Math.cos(a - Math.PI / 2), cy + r * Math.sin(a - Math.PI / 2)]
  const [x0, y0] = p(r1, a0), [x1, y1] = p(r1, a1)
  const [x2, y2] = p(r0, a1), [x3, y3] = p(r0, a0)
  const large = a1 - a0 > Math.PI ? 1 : 0
  return `M${x0},${y0}A${r1},${r1} 0 ${large} 1 ${x1},${y1}` +
         `L${x2},${y2}A${r0},${r0} 0 ${large} 0 ${x3},${y3}Z`
}

function Sunburst({ node, fmt }: { node: Node; fmt?: CalcColumnFormat | null }) {
  const size = 260, cx = size / 2, cy = size / 2
  const maxDepth = useMemo(() => {
    let d = 0
    const walk = (n: Node, depth: number) => {
      d = Math.max(d, depth)
      n.children?.forEach(c => walk(c, depth + 1))
    }
    node.children?.forEach(c => walk(c, 1))
    return Math.max(d, 1)
  }, [node])
  const ring = (cx - 10) / (maxDepth + 1)

  const segments: JSX.Element[] = []
  const walk = (n: Node, depth: number, a0: number, a1: number) => {
    if (depth > 0) {
      segments.push(
        <path key={`${n.name}-${depth}-${a0.toFixed(3)}`}
          d={arc(cx, cy, depth * ring, (depth + 1) * ring, a0, a1)}
          fill="var(--accent)" opacity={1 - depth * 0.15}
          stroke="var(--surface)" strokeWidth={1}>
          <title>{`${n.name}: ${fmtStr(n.value, fmt)}`}</title>
        </path>)
    }
    const total = (n.children ?? []).reduce((s, c) => s + (c.value ?? 0), 0)
    let a = a0
    for (const c of n.children ?? []) {
      // The parent's angle is divided among its children by value -- which is
      // exactly why the shaper refuses non-additive aggregations here.
      const span = total > 0 ? ((c.value ?? 0) / total) * (a1 - a0) : 0
      walk(c, depth + 1, a, a + span)
      a += span
    }
  }
  walk(node, 0, 0, Math.PI * 2)

  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%' }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}
        role="img" aria-label="Sunburst hierarchy">{segments}</svg>
    </div>
  )
}

// ── Circle packing: nested circles, area = value ────────────────────────────

/**
 * Children drawn INSIDE their parent, each circle's AREA proportional to its
 * value — which is why this joins sunburst and icicle in `PARTITION_WIDGETS`
 * and refuses non-additive aggregations.
 *
 * Radius scales with √value, never with value. Using value directly is the
 * classic bubble lie: three times the number becomes three times the width and
 * NINE times the ink, in the one chart type whose entire argument is area.
 *
 * Children are scaled to fit their parent, so **area comparisons are exact
 * between siblings and not across branches** — d3's pack makes the same trade,
 * and it is forced: children whose areas sum to their parent's cannot fit
 * inside it, since circles cannot tile a circle. Each `<title>` carries the real
 * number, so the value is never only inferable from the picture.
 *
 * Placement is a ring rather than a true pack solver: a full implementation is
 * a lot of geometry for a layout whose job is "which of these is big", and a
 * ring keeps both properties above true.
 */
interface Circle { cx: number; cy: number; r: number; node: Node; depth: number }

function packCircles(node: Node, cx: number, cy: number, r: number,
                     depth: number, out: Circle[]): void {
  out.push({ cx, cy, r, node, depth })
  const kids = (node.children ?? []).filter(c => (c.value ?? 0) > 0)
  if (!kids.length || r < 6) return

  // √value, because area is the encoding. A null value contributes nothing
  // rather than NaN — the contract allows `value: null` wherever a level has no
  // measure, and one NaN radius would blank the whole branch.
  const raw = kids.map(c => Math.sqrt(Math.max(c.value ?? 0, 0)))
  const maxRaw = Math.max(...raw)
  if (!(maxRaw > 0)) return

  const pad = 2
  let ringR: number
  let allowed: number
  if (kids.length === 1) {
    ringR = 0
    allowed = r * 0.78
  } else {
    ringR = r * 0.52
    // Two limits: stay inside the parent, and leave room for a neighbour on
    // the ring. The chord between adjacent centres is 2·ringR·sin(π/n).
    const chord = 2 * ringR * Math.sin(Math.PI / kids.length)
    allowed = Math.min(r - ringR - pad, chord * 0.48)
  }
  if (allowed <= 0) return

  const scale = allowed / maxRaw
  kids.forEach((child, i) => {
    const angle = (i / kids.length) * Math.PI * 2 - Math.PI / 2
    const kx = cx + ringR * Math.cos(angle)
    const ky = cy + ringR * Math.sin(angle)
    packCircles(child, kx, ky, raw[i] * scale, depth + 1, out)
  })
}

function CirclePack({ node, fmt }: { node: Node; fmt?: CalcColumnFormat | null }) {
  const size = 260
  const circles = useMemo(() => {
    const out: Circle[] = []
    packCircles(node, size / 2, size / 2, size / 2 - 2, 0, out)
    return out
  }, [node])

  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%' }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}
        role="img" aria-label="Circle packing hierarchy">
        {circles.map((c, i) => (
          <circle key={`${c.node.name}-${c.depth}-${i}`}
            cx={c.cx} cy={c.cy} r={Math.max(c.r, 0)}
            fill="var(--accent)" fillOpacity={0.1 + c.depth * 0.18}
            stroke="var(--accent)" strokeWidth={0.75}>
            {/* Depth 0 is the synthetic root the shaper always returns; naming
                it would put a label on a circle the user never chose. */}
            {c.depth > 0 && <title>{`${c.node.name}: ${fmtStr(c.node.value, fmt)}`}</title>}
          </circle>
        ))}
        {circles.filter(c => c.depth > 0 && c.r > 16).map((c, i) => (
          <text key={`t${i}`} x={c.cx} y={c.cy} textAnchor="middle" dominantBaseline="middle"
            fontSize={10} fill="var(--text)" pointerEvents="none">
            {c.node.name}
          </text>
        ))}
      </svg>
    </div>
  )
}

// ── Dendrogram / org: node-and-link diagram ─────────────────────────────────

function LinkTree({ node, fmt, compact }: {
  node: Node; fmt?: CalcColumnFormat | null; compact: boolean
}) {
  const kids = node.children ?? []
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 0 }}>
      <div style={{
        border: '1px solid var(--border)', borderRadius: compact ? 3 : 6,
        background: 'var(--surface)', padding: compact ? '2px 6px' : '5px 9px',
        fontSize: compact ? 10 : 11, whiteSpace: 'nowrap', flexShrink: 0,
      }}>
        <div style={{ fontWeight: 500 }}>{node.name}</div>
        {!compact && node.value != null && (
          <div style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--muted)' }}>
            {fmtStr(node.value, fmt)}
          </div>
        )}
      </div>
      {kids.length > 0 && (
        <>
          <div style={{ width: 14, height: 1, background: 'var(--border)', flexShrink: 0 }} />
          <div style={{
            display: 'flex', flexDirection: 'column', gap: 5,
            borderInlineStart: '1px solid var(--border)', paddingInlineStart: 10,
          }}>
            {kids.map((c, i) => (
              <LinkTree key={`${c.name}-${i}`} node={c} fmt={fmt} compact={compact} />
            ))}
            {!!node.omitted && (
              <div style={{ fontSize: 10, color: 'var(--muted)', fontStyle: 'italic' }}>
                + {node.omitted} more
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}

// ── Entry point ─────────────────────────────────────────────────────────────

export default function HierarchyRenderer(
  { data, rtl, measureFmt, checked, onToggleValue }: ChartRendererProps & {
    checked?: Set<unknown>
    onToggleValue?: (v: unknown) => void
  },
) {
  const root: Node | undefined = data?.root
  const kind: string = data?.type ?? 'tree'

  const checkedSet = useMemo(
    () => new Set(Array.from(checked ?? []).map(String)), [checked])

  if (!root || !(root.children?.length)) {
    return <div style={{ color: 'var(--muted)', fontSize: 12, padding: 8 }}>No data.</div>
  }

  const count = nodeCount(root)

  const body = (() => {
    if (kind === 'sunburst') return <Sunburst node={root} fmt={measureFmt} />
    if (kind === 'icicle') return <Icicle node={root} fmt={measureFmt} />
    if (kind === 'circle_pack') return <CirclePack node={root} fmt={measureFmt} />
    if (kind === 'dendrogram' || kind === 'org') {
      return (
        <div style={{ padding: 8, overflow: 'auto', height: '100%' }}>
          {root.children.map((c, i) => (
            <LinkTree key={`${c.name}-${i}`} node={c} fmt={measureFmt}
              compact={kind === 'dendrogram'} />
          ))}
        </div>
      )
    }
    return (
      <div style={{ padding: 6, overflow: 'auto', height: '100%' }}>
        {root.children.map((c, i) => (
          <TreeRows key={`${c.name}-${i}`} node={c} rtl={!!rtl} fmt={measureFmt}
            checked={checkedSet}
            onToggle={n => onToggleValue?.(n)}
            selectable={!!onToggleValue} />
        ))}
      </div>
    )
  })()

  return (
    <div dir={rtl ? 'rtl' : undefined}
      style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <div style={{ flex: 1, minHeight: 0, overflow: 'auto' }}>{body}</div>
      {/* A truncated hierarchy must say so: the reader cannot see which
          branches never reached the page. */}
      {data?.truncated && (
        <div style={{ fontSize: 10, color: 'var(--muted)', padding: '2px 8px' }}>
          Showing the first {count.toLocaleString()} nodes; deeper branches were
          not loaded.
        </div>
      )}
    </div>
  )
}
