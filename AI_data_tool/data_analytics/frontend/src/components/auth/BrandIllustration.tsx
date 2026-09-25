import { useEffect, useId, useState } from 'react'
import { Cloud, Database, FileSpreadsheet, Sparkles } from 'lucide-react'
import { useT } from '../../i18n'
import { localDigits } from '../../lib/arabicFormats'

/**
 * The sign-in page's brand picture: what Datalytics does, in one frame.
 * Three kinds of source (database, spreadsheet, cloud) send data along thin
 * flowing lines into a small AI node, and out the other side comes a mini
 * dashboard -- a KPI that counts up, bars, a line that draws itself, a donut.
 *
 * Pure SVG + CSS (styles in pages/login.css), app tokens only, no remote
 * assets. Every loop is 4-8 s and stops under prefers-reduced-motion, where
 * the picture shows its finished state. In RTL the layout mirrors (sources
 * on the right, data flowing leftward); chart internals stay LTR, as they
 * do everywhere else in the product.
 */

const W = 640
const H = 400   // the drawing's own frame; the viewBox crops its empty margin
const KPI_TARGET = 2_480_000
const LOOP_MS = 6000
const COUNT_MS = 1600

function prefersReducedMotion(): boolean {
  try { return window.matchMedia('(prefers-reduced-motion: reduce)').matches } catch { return false }
}

/** The KPI's number: counts up once per loop, then holds. Static under reduced motion. */
function useCountUp(target: number): number {
  const [value, setValue] = useState(() => (prefersReducedMotion() ? target : 0))
  useEffect(() => {
    if (prefersReducedMotion() || typeof requestAnimationFrame !== 'function') { setValue(target); return }
    let raf = 0
    const start = performance.now()
    const tick = (now: number) => {
      const t = ((now - start) % LOOP_MS) / COUNT_MS
      const eased = t >= 1 ? 1 : 1 - Math.pow(1 - t, 3)
      setValue(Math.round(target * eased))
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [target])
  return value
}

export default function BrandIllustration({ rtl, className, decorative }: {
  rtl: boolean
  className?: string
  /** A second copy (the phone strip) that must not be announced twice. */
  decorative?: boolean
}) {
  const t = useT()
  const uid = useId().replace(/:/g, '')
  const titleId = `dl-ill-title-${uid}`, descId = `dl-ill-desc-${uid}`, glowId = `dl-ill-glow-${uid}`
  const kpi = useCountUp(KPI_TARGET)
  // Mirror a horizontal position for RTL; vertical positions never change.
  const X = (x: number) => (rtl ? W - x : x)

  const sources = [
    { y: 92, Icon: Database, label: t('brand.source.database'), tone: 1 },
    { y: 200, Icon: FileSpreadsheet, label: t('brand.source.file'), tone: 5 },
    { y: 308, Icon: Cloud, label: t('brand.source.cloud'), tone: 2 },
  ]
  const TILE = 56
  const srcX = 72                    // tile centre
  const node = { x: 304, y: 200 }    // AI node centre
  const card = { x: 400, y: 56, w: 212, h: 288 }  // dashboard (LTR coordinates)
  const cardX = rtl ? W - card.x - card.w : card.x

  // Source -> node curves. Drawn FROM the source so the dash flow runs toward the centre.
  const flow = (y: number) => {
    const x0 = X(srcX + TILE / 2 + 6), x1 = X(node.x - 34)
    const c0 = X(srcX + TILE / 2 + 96), c1 = X(node.x - 110)
    return `M${x0} ${y} C ${c0} ${y}, ${c1} ${node.y}, ${x1} ${node.y}`
  }
  const outPath = `M${X(node.x + 34)} ${node.y} L ${X(card.x - 8)} ${node.y}`

  const bars = [0.42, 0.66, 0.54, 0.86, 0.72]
  const line = 'M0 46 L 28 38 L 56 42 L 85 26 L 113 30 L 142 14 L 170 8'
  const donut = [
    { len: 46, off: 0, cls: 's1' },
    { len: 30, off: -46, cls: 's2' },
    { len: 24, off: -76, cls: 's3' },
  ]
  const kpiText = localDigits(kpi.toLocaleString('en-US'))

  return (
    <svg viewBox={`28 40 ${W - 56} ${H - 74}`} className={`dl-ill ${className ?? ''}`}
      preserveAspectRatio="xMidYMid meet" focusable="false"
      {...(decorative
        ? { 'aria-hidden': true }
        : { role: 'img', 'aria-labelledby': `${titleId} ${descId}` })}>
      {!decorative && <title id={titleId}>{t('brand.illustration.title')}</title>}
      {!decorative && <desc id={descId}>{t('brand.illustration.desc')}</desc>}
      <defs>
        <radialGradient id={glowId}>
          <stop offset="0%" className="dl-ill__glow-stop0" />
          <stop offset="100%" className="dl-ill__glow-stop1" />
        </radialGradient>
      </defs>

      {/* Flow lines: a quiet rail with a brighter moving dash on top. */}
      {sources.map(s => (
        <g key={s.y}>
          <path d={flow(s.y)} className="dl-ill__rail" />
          <path d={flow(s.y)} className="dl-ill__flow" style={{ animationDelay: `${(s.y / 100) * -0.7}s` }} />
        </g>
      ))}
      <path d={outPath} className="dl-ill__rail" />
      <path d={outPath} className="dl-ill__flow dl-ill__flow--out" />

      {/* Sources */}
      {sources.map(({ y, Icon, label, tone }) => (
        <g key={label}>
          <rect x={X(srcX) - TILE / 2} y={y - TILE / 2} width={TILE} height={TILE} rx={14}
            className="dl-ill__tile" />
          <Icon x={X(srcX) - 12} y={y - 12} width={24} height={24} className={`dl-ill__icon dl-ill__icon--${tone}`} aria-hidden />
          <text x={X(srcX)} y={y + TILE / 2 + 18} textAnchor="middle" className="dl-ill__caption">{label}</text>
        </g>
      ))}

      {/* AI node */}
      <g>
        <circle cx={X(node.x)} cy={node.y} r={62} fill={`url(#${glowId})`} className="dl-ill__glow" />
        <circle cx={X(node.x)} cy={node.y} r={38} className="dl-ill__orbit" />
        <circle cx={X(node.x)} cy={node.y} r={26} className="dl-ill__core" />
        <Sparkles x={X(node.x) - 13} y={node.y - 13} width={26} height={26} className="dl-ill__spark" aria-hidden />
        <text x={X(node.x)} y={node.y + 58} textAnchor="middle" className="dl-ill__caption dl-ill__caption--ai">
          {t('brand.ai')}
        </text>
      </g>

      {/* Mini dashboard. Chart internals are drawn in the card's own LTR frame. */}
      <g transform={`translate(${cardX} ${card.y})`}>
        <rect width={card.w} height={card.h} rx={16} className="dl-ill__card" />
        <circle cx={16} cy={16} r={3.5} className="dl-ill__dot" />
        <circle cx={28} cy={16} r={3.5} className="dl-ill__dot" />
        <circle cx={40} cy={16} r={3.5} className="dl-ill__dot" />

        {/* KPI */}
        <rect x={12} y={30} width={card.w - 24} height={62} rx={10} className="dl-ill__panel" />
        <text x={rtl ? card.w - 24 : 24} y={50} textAnchor={rtl ? 'end' : 'start'} className="dl-ill__kpi-label">
          {t('brand.kpi')}
        </text>
        <text x={rtl ? card.w - 24 : 24} y={78} textAnchor={rtl ? 'end' : 'start'} className="dl-ill__kpi">
          {kpiText}
        </text>
        <g transform={`translate(${rtl ? 24 : card.w - 76} 40)`}>
          <rect width={52} height={20} rx={10} className="dl-ill__delta-bg" />
          <text x={26} y={14} textAnchor="middle" className="dl-ill__delta">{localDigits('+12.4%')}</text>
        </g>

        {/* Bars */}
        <g transform="translate(12 104)">
          <rect width={104} height={94} rx={10} className="dl-ill__panel" />
          {bars.map((h, i) => (
            <rect key={i} x={12 + i * 17} y={82 - h * 66} width={11} height={h * 66} rx={2.5}
              className={`dl-ill__bar ${i === 3 ? 'dl-ill__bar--hi' : ''}`}
              style={{ animationDelay: `${i * 120}ms` }} />
          ))}
        </g>

        {/* Donut */}
        <g transform={`translate(${card.w - 12 - 84} 104)`}>
          <rect width={84} height={94} rx={10} className="dl-ill__panel" />
          <circle cx={42} cy={47} r={25} className="dl-ill__donut-track" />
          {donut.map(seg => (
            <circle key={seg.cls} cx={42} cy={47} r={25} pathLength={100} transform="rotate(-90 42 47)"
              className={`dl-ill__donut dl-ill__donut--${seg.cls}`}
              style={{ ['--len' as string]: seg.len, strokeDasharray: `${seg.len} 100`, strokeDashoffset: seg.off }} />
          ))}
        </g>

        {/* Line */}
        <g transform="translate(12 210)">
          <rect width={card.w - 24} height={66} rx={10} className="dl-ill__panel" />
          <g transform="translate(8 6)">
            <path d={`${line} L 170 54 L 0 54 Z`} className="dl-ill__area" />
            <path d={line} pathLength={1} className="dl-ill__line" />
          </g>
        </g>
      </g>
    </svg>
  )
}
