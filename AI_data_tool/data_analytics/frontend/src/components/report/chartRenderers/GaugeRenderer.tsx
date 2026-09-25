import { RadialBarChart, RadialBar, PolarAngleAxis, ResponsiveContainer } from 'recharts'
import { fmtStr } from '../chartUtils'
import type { ChartRendererProps } from './types'

/**
 * Gauge shapes, SAS-style: one value+target result, five presentations.
 *   arc (default)  half-donut radial fill — the original shape
 *   speedometer    dial with a needle over a 240° band
 *   bullet         Few-style horizontal bar with target tick
 *   thermometer    vertical tube with bulb
 *   progress       slim horizontal bar with % label
 * All read the same shaped result; display-rule fill (interval bands over
 * `value`) overrides the attainment colour in every shape.
 */
export default function GaugeRenderer({ data, measureFmt, ruleStyles, cfg }: ChartRendererProps) {
  const value: number | null = data?.value ?? null
  const target: number | null = data?.target ?? null
  const shape = String((cfg as { gauge_shape?: string })?.gauge_shape || 'arc')

  if (value == null) {
    return <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--muted)', fontSize: 12 }}>Configure widget to see data</div>
  }

  const max = target != null && target > 0 ? Math.max(target, value) * 1.1 : (value > 0 ? value * 1.25 : 1)
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0
  // display_rules.py's result_frame() lifts a gauge result into a single-row frame
  // ({value, target}), so an interval rule (bands keyed on the `value` column) paints
  // ruleStyles.rows[0] -- the only row that exists for a gauge.
  const ruleFill = ruleStyles?.rows?.[0]?.fill
  const fill = ruleFill ?? (target != null && value >= target ? '#34d399' : '#6c8fff')
  const valueLabel = fmtStr(value, measureFmt)
  const targetLabel = target != null ? fmtStr(target, measureFmt) : null

  if (shape === 'bullet') {
    const targetPct = target != null && max > 0 ? Math.min(100, (target / max) * 100) : null
    return (
      <div data-testid="gauge-bullet" style={{ height: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'center', padding: '0 16px', gap: 6 }}>
        <div style={{ fontSize: 18, fontWeight: 700 }}>{valueLabel}
          {targetLabel && <span style={{ fontSize: 11, fontWeight: 400, color: 'var(--muted)' }}> of {targetLabel}</span>}
        </div>
        <div style={{ position: 'relative', height: 18, background: 'var(--surface2)', borderRadius: 4 }}>
          <div style={{ position: 'absolute', inset: 0, width: `${pct}%`, background: fill, borderRadius: 4 }} />
          {targetPct != null && (
            <div data-testid="gauge-bullet-target" style={{ position: 'absolute', top: -3, bottom: -3, left: `${targetPct}%`, width: 2, background: 'var(--text)' }} />
          )}
        </div>
      </div>
    )
  }

  if (shape === 'progress') {
    return (
      <div data-testid="gauge-progress" style={{ height: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'center', padding: '0 16px', gap: 6 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
          <span style={{ fontSize: 18, fontWeight: 700 }}>{valueLabel}</span>
          <span style={{ fontSize: 12, color: 'var(--muted)' }}>{Math.round(pct)}%{targetLabel ? ` of ${targetLabel}` : ''}</span>
        </div>
        <div style={{ height: 8, background: 'var(--surface2)', borderRadius: 4, overflow: 'hidden' }}>
          <div style={{ height: '100%', width: `${pct}%`, background: fill, transition: 'width .3s' }} />
        </div>
      </div>
    )
  }

  if (shape === 'thermometer') {
    const tubeH = 100
    const fillH = (pct / 100) * tubeH
    return (
      <div data-testid="gauge-thermometer" style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 14 }}>
        <svg viewBox="0 0 40 140" style={{ height: '85%', maxHeight: 220 }}>
          <rect x={14} y={10} width={12} height={tubeH} rx={6} fill="var(--surface2)" />
          <rect x={14} y={10 + (tubeH - fillH)} width={12} height={fillH} rx={fillH > 10 ? 6 : 2} fill={fill} />
          <circle cx={20} cy={122} r={14} fill={fill} />
          <circle cx={20} cy={122} r={14} fill="none" stroke="var(--border)" />
        </svg>
        <div>
          <div style={{ fontSize: 20, fontWeight: 700 }}>{valueLabel}</div>
          {targetLabel && <div style={{ fontSize: 11, color: 'var(--muted)' }}>of {targetLabel}</div>}
        </div>
      </div>
    )
  }

  if (shape === 'speedometer') {
    // 240° band from 210° to -30° (SVG angles measured from +x, CCW positive)
    const startDeg = 210
    const sweep = 240
    const angle = startDeg - (pct / 100) * sweep
    const rad = (a: number) => (a * Math.PI) / 180
    const cx = 70, cy = 70, rOuter = 58, rInner = 44
    const arcPoint = (a: number, r: number) => `${cx + r * Math.cos(rad(a))},${cy - r * Math.sin(rad(a))}`
    const band = (from: number, to: number, color: string, key: string) => {
      const large = from - to > 180 ? 1 : 0
      return (
        <path key={key}
          d={`M ${arcPoint(from, rOuter)} A ${rOuter} ${rOuter} 0 ${large} 1 ${arcPoint(to, rOuter)} L ${arcPoint(to, rInner)} A ${rInner} ${rInner} 0 ${large} 0 ${arcPoint(from, rInner)} Z`}
          fill={color} />
      )
    }
    const fillEnd = startDeg - (pct / 100) * sweep
    return (
      <div data-testid="gauge-speedometer" style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <svg viewBox="0 0 140 110" style={{ height: '90%', width: '100%' }}>
          {band(startDeg, startDeg - sweep, 'var(--surface2)', 'track')}
          {pct > 0 && band(startDeg, fillEnd, fill, 'fill')}
          <line data-testid="gauge-needle" x1={cx} y1={cy} x2={cx + 40 * Math.cos(rad(angle))} y2={cy - 40 * Math.sin(rad(angle))}
            stroke="var(--text)" strokeWidth={2.5} strokeLinecap="round" />
          <circle cx={cx} cy={cy} r={5} fill="var(--text)" />
          <text x={cx} y={cy + 28} textAnchor="middle" style={{ fontSize: 14, fontWeight: 700, fill: 'var(--text)' }}>{valueLabel}</text>
          {targetLabel && <text x={cx} y={cy + 40} textAnchor="middle" style={{ fontSize: 8, fill: 'var(--muted)' }}>of {targetLabel}</text>}
        </svg>
      </div>
    )
  }

  const chartData = [{ name: 'value', value: pct, fill }]
  return (
    <div style={{ height: '100%', width: '100%', position: 'relative' }}>
      <ResponsiveContainer width="100%" height="100%">
        <RadialBarChart data={chartData} cx="50%" cy="55%" innerRadius="65%" outerRadius="100%" startAngle={180} endAngle={0} barSize={18}>
          <PolarAngleAxis type="number" domain={[0, 100]} angleAxisId={0} tick={false} />
          <RadialBar background dataKey="value" cornerRadius={9} isAnimationActive={false} />
        </RadialBarChart>
      </ResponsiveContainer>
      <div style={{ position: 'absolute', top: '55%', left: '50%', transform: 'translate(-50%, -20%)', textAlign: 'center', pointerEvents: 'none' }}>
        <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--text)' }}>{fmtStr(value, measureFmt)}</div>
        {target != null && <div style={{ fontSize: 11, color: 'var(--muted)' }}>of {fmtStr(target, measureFmt)}</div>}
      </div>
    </div>
  )
}
