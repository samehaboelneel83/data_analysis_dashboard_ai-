import { Treemap, Tooltip, ResponsiveContainer } from 'recharts'
import { COLORS, SELECTED_STROKE, DIM_OPACITY, TT, fmtStr } from '../chartUtils'
import type { ChartRendererProps } from './types'
import { seriesName } from './axisOptions'

export default function TreemapChartRenderer({ rows, cfg, rtl, broadcasts, localSelected, onClickPoint, measureFmt, ruleStyles }: ChartRendererProps) {
  const tmData = rows.map((r: any, i: number) => ({ name: r.name, size: r.value, _i: i }))
  // Opt-out: a node's name has been drawn, whenever its box was big enough to
  // hold it, unconditionally, since this renderer was written -- an unset
  // config must keep showing it. The width/height size gate stays regardless
  // of this toggle, since text that overflows its box is a bug, not a label.
  const showLabels = cfg.data_labels !== false
  return (
    <div dir={rtl ? 'rtl' : undefined} style={{ height: '100%' }}>
      <ResponsiveContainer width="100%" height="100%">
        <Treemap data={tmData} dataKey="size" nameKey="name" aspectRatio={4/3}
          isAnimationActive={false}
          onClick={broadcasts ? (d: any) => onClickPoint(d.name) : undefined}
          style={{ cursor: broadcasts ? 'pointer' : 'default' }}
          content={((props: any) => {
            const { x, y, width, height, name, _i } = props
            const color = ruleStyles?.rows?.[_i ?? 0]?.fill ?? COLORS[(_i ?? 0) % COLORS.length]
            const isActive = localSelected === name
            const dimmed  = broadcasts && localSelected !== null && !isActive
            return width > 8 && height > 8 ? (
              <g>
                <rect x={x} y={y} width={width} height={height}
                  fill={color} opacity={dimmed ? DIM_OPACITY : 1}
                  stroke={isActive ? SELECTED_STROKE : 'var(--surface)'} strokeWidth={isActive ? 2 : 1.5} rx={4} />
                {showLabels && width > 60 && height > 28 && (
                  <text x={x + width / 2} y={y + height / 2} textAnchor="middle" dominantBaseline="middle"
                    fill="#fff" fontSize={Math.min(12, width / 7)} fontWeight={600}>{name}</text>
                )}
              </g>
            ) : <g />
          }) as any}
        >
          <Tooltip contentStyle={TT} formatter={(v: unknown) => [fmtStr(v, measureFmt), seriesName(cfg)]} />
        </Treemap>
      </ResponsiveContainer>
    </div>
  )
}
