import { ResponsiveContainer, Sankey, Tooltip } from 'recharts'
import { TT, fmtStr, COLORS } from '../chartUtils'
import type { ChartRendererProps } from './types'
import { EmptyState } from '../chartUtils'

/** Flow diagram over the backend's {nodes, links}. Recharts ships a Sankey layout;
 *  the shaper already guaranteed no self-loops and split node identity by side, both
 *  of which the layout cannot survive without. */
export default function SankeyChartRenderer({ data, measureFmt }: ChartRendererProps) {
  const nodes: { name: string }[] = data?.nodes ?? []
  const links: { source: number; target: number; value: number }[] = data?.links ?? []
  if (!nodes.length || !links.length) return <EmptyState msg="No flows to draw" />

  return (
    <ResponsiveContainer width="100%" height="100%">
      <Sankey
        data={{ nodes, links }}
        nodePadding={18}
        margin={{ top: 8, right: 90, bottom: 8, left: 8 }}
        link={{ stroke: COLORS[0], strokeOpacity: 0.35 }}
        node={{ fill: COLORS[1], stroke: 'var(--border)' }}
      >
        <Tooltip contentStyle={TT} formatter={(v: unknown, name: unknown) => [fmtStr(v, measureFmt), String(name ?? '')]} />
      </Sankey>
    </ResponsiveContainer>
  )
}
