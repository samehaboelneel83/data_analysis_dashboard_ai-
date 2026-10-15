import { ResponsiveContainer, Sankey, Tooltip } from 'recharts'
import { TT, fmtStr, COLORS } from '../chartUtils'
import type { ChartRendererProps } from './types'
import { EmptyState } from '../chartUtils'

const LABEL_GAP = 6
const CHAR_W = 6.5      // ~px per character at 11px

/** Flow diagram over the backend's {nodes, links}. Recharts ships a Sankey layout;
 *  the shaper already guaranteed no self-loops and split node identity by side, both
 *  of which the layout cannot survive without.
 *
 *  C-08: recharts draws a bare rectangle for a node given as an object, so the
 *  chart named nothing, and every flow was one pale colour. Nodes are drawn
 *  here with their name (outside the bar, towards the middle of the chart),
 *  and each flow takes its SOURCE node's colour. */
export default function SankeyChartRenderer({ data, measureFmt, plotW, plotH }: ChartRendererProps) {
  const nodes: { name: string }[] = data?.nodes ?? []
  const links: { source: number; target: number; value: number }[] = data?.links ?? []
  if (!nodes.length || !links.length) return <EmptyState msg="No flows to draw" />

  const longest = Math.max(...nodes.map(n => String(n.name ?? '').length), 1)
  const width = plotW && plotW > 0 ? plotW : 0
  // Room for the right-hand labels, at most a third of the chart.
  const side = Math.min(Math.max(40, longest * CHAR_W + LABEL_GAP + 4), width ? width / 3 : 160)
  const maxChars = Math.max(3, Math.floor((side - LABEL_GAP) / CHAR_W))
  const colorOf = (i: number) => COLORS[i % COLORS.length]

  const Node = (p: any) => {
    const { x, y, width: w, height: h, index, payload, containerWidth } = p
    const name = String(payload?.name ?? '')
    const right = x + w / 2 > (containerWidth ?? width) / 2     // right-hand column: label to the left
    const label = name.length > maxChars ? `${name.slice(0, maxChars - 1)}…` : name
    return (
      <g>
        <rect x={x} y={y} width={w} height={h} fill={colorOf(index)} stroke="var(--border)" />
        <text x={right ? x - LABEL_GAP : x + w + LABEL_GAP} y={y + h / 2} dy="0.35em"
          textAnchor={right ? 'end' : 'start'} fontSize={11} fill="var(--text)">
          <title>{`${name}: ${fmtStr(payload?.value, measureFmt)}`}</title>
          {label}
        </text>
      </g>
    )
  }
  const Link = (p: any) => {
    const { sourceX, targetX, sourceY, targetY, sourceControlX, targetControlX, linkWidth, index } = p
    const src = links[index]?.source ?? 0
    return (
      <path data-sankey-link=""
        d={`M${sourceX},${sourceY} C${sourceControlX},${sourceY} ${targetControlX},${targetY} ${targetX},${targetY}`}
        fill="none" stroke={colorOf(src)} strokeOpacity={0.35} strokeWidth={Math.max(1, linkWidth)} />
    )
  }
  const chart = (w?: number, h?: number) => (
    <Sankey
      width={w} height={h}
      data={{ nodes, links }}
      nodePadding={18}
      margin={{ top: 8, right: side, bottom: 8, left: 8 }}
      link={<Link />}
      node={<Node />}
    >
      <Tooltip contentStyle={TT} formatter={(v: unknown, name: unknown) => [fmtStr(v, measureFmt), String(name ?? '')]} />
    </Sankey>
  )
  // The tile's measured plot box when there is one; otherwise fill the container.
  if (plotW && plotH && plotW > 0 && plotH > 0) return chart(plotW, plotH)
  return <ResponsiveContainer width="100%" height="100%">{chart()}</ResponsiveContainer>
}
