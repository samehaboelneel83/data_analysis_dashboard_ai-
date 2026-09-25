import { Treemap, ResponsiveContainer } from 'recharts'
import { COLORS, SELECTED_STROKE, DIM_OPACITY } from '../chartUtils'
import type { ChartRendererProps } from './types'

export default function TreemapChartRenderer({ rows, rtl, broadcasts, localSelected, onClickPoint }: ChartRendererProps) {
  const tmData = rows.map((r: any, i: number) => ({ name: r.name, size: r.value, _i: i }))
  return (
    <div dir={rtl ? 'rtl' : undefined} style={{ height: '100%' }}>
      <ResponsiveContainer width="100%" height="100%">
        <Treemap data={tmData} dataKey="size" nameKey="name" aspectRatio={4/3}
          onClick={broadcasts ? (d: any) => onClickPoint(d.name) : undefined}
          style={{ cursor: broadcasts ? 'pointer' : 'default' }}
          content={((props: any) => {
            const { x, y, width, height, name, _i } = props
            const color = COLORS[(_i ?? 0) % COLORS.length]
            const isActive = localSelected === name
            const dimmed  = broadcasts && localSelected !== null && !isActive
            return width > 8 && height > 8 ? (
              <g>
                <rect x={x} y={y} width={width} height={height}
                  fill={color} opacity={dimmed ? DIM_OPACITY : 1}
                  stroke={isActive ? SELECTED_STROKE : 'var(--surface)'} strokeWidth={isActive ? 2 : 1.5} rx={4} />
                {width > 60 && height > 28 && (
                  <text x={x + width / 2} y={y + height / 2} textAnchor="middle" dominantBaseline="middle"
                    fill="#fff" fontSize={Math.min(12, width / 7)} fontWeight={600}>{name}</text>
                )}
              </g>
            ) : <g />
          }) as any}
        />
      </ResponsiveContainer>
    </div>
  )
}
