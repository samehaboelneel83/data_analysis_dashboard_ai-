import { GRAPH_MARKS } from '../../types/report'
import type { DatasetColumn } from '../../services/api'
import { useT } from '../../i18n'
import { codeLabel } from '../../i18n/pages/modelsMaps'

/**
 * Building a graph out of plot layers — the authoring half of Graph Builder.
 *
 * Each layer is a measure, a mark, an aggregation and an axis. That is the
 * whole model: the chart is whatever the layers say, which is what makes this a
 * graph BUILDER rather than a fourth fixed combination beside dual-axis bar,
 * line and bar-line.
 *
 * The aggregation belongs to the LAYER, not the widget. "Encounters counted,
 * wait averaged" is the ordinary reason to put two things on one chart, and a
 * single widget-level aggregation cannot say it.
 */
export interface GraphLayer {
  measure?: string
  mark?: string
  aggregation?: string
  axis?: 'left' | 'right'
  label?: string
}

const AGGREGATIONS = ['sum', 'avg', 'count', 'min', 'max', 'median'] as const

const cell: React.CSSProperties = {
  fontSize: 11, padding: '3px 5px', border: '1px solid var(--border)',
  borderRadius: 4, background: 'var(--surface)', color: 'var(--text)',
}

export default function GraphLayersEditor({ value, columns, onChange }: {
  value: GraphLayer[]
  columns: DatasetColumn[]
  onChange: (layers: GraphLayer[]) => void
}) {
  const t = useT()
  const layers = value ?? []
  const numeric = columns.filter(c => c.dtype === 'numeric')

  const patch = (i: number, next: Partial<GraphLayer>) =>
    onChange(layers.map((l, j) => (j === i ? { ...l, ...next } : l)))

  const move = (i: number, by: number) => {
    const to = i + by
    if (to < 0 || to >= layers.length) return
    const next = [...layers]
    ;[next[i], next[to]] = [next[to], next[i]]
    onChange(next)
  }

  return (
    <div style={{ marginBottom: 12 }}>
      <label style={{ display: 'block', fontSize: 11, fontWeight: 700, color: 'var(--muted)', marginBottom: 4 }}>
        {t('pg.modelsMaps.ml.layers')}
      </label>

      {layers.length === 0 && (
        <p style={{ fontSize: 11, color: 'var(--muted)', margin: '0 0 6px' }}>{t('pg.modelsMaps.gl.empty')}</p>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {layers.map((l, i) => {
          const name = l.measure || t('pg.modelsMaps.gl.fallbackName', { n: i + 1 })
          return (
            <div key={i} style={{
              border: '1px solid var(--border)', borderRadius: 6, padding: 6,
              display: 'flex', flexDirection: 'column', gap: 4,
            }}>
              <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
                <select value={l.measure ?? ''} aria-label={t('pg.modelsMaps.gl.measureFor', { name })}
                  onChange={e => patch(i, { measure: e.target.value })}
                  style={{ ...cell, flex: 1 }}>
                  <option value="">{t('pg.modelsMaps.gl.chooseMeasure')}</option>
                  {numeric.map(c => <option key={c.name} value={c.name}>{c.name}</option>)}
                </select>
                {/* Draw order is the author's: bars behind a line is the usual
                    reading, and only they know which layer is the subject. */}
                <button onClick={() => move(i, -1)} disabled={i === 0}
                  aria-label={t('pg.modelsMaps.gl.moveUpNamed', { name })} title={t('pg.modelsMaps.gl.moveUp')}
                  style={{ ...cell, cursor: 'pointer' }}>↑</button>
                <button onClick={() => move(i, 1)} disabled={i === layers.length - 1}
                  aria-label={t('pg.modelsMaps.gl.moveDownNamed', { name })} title={t('pg.modelsMaps.gl.moveDown')}
                  style={{ ...cell, cursor: 'pointer' }}>↓</button>
                <button onClick={() => onChange(layers.filter((_, j) => j !== i))}
                  aria-label={t('pg.modelsMaps.gl.remove', { name })} title={t('pg.modelsMaps.gl.remove', { name })}
                  style={{ background: 'none', border: 'none', color: 'var(--muted)',
                    cursor: 'pointer', fontSize: 14, lineHeight: 1, padding: '0 2px' }}>
                  ×
                </button>
              </div>
              <div style={{ display: 'flex', gap: 4 }}>
                <select value={l.mark ?? 'bar'} aria-label={t('pg.modelsMaps.gl.markFor', { name })}
                  onChange={e => patch(i, { mark: e.target.value })}
                  style={{ ...cell, flex: 1 }}>
                  {GRAPH_MARKS.map(m => <option key={m} value={m}>{codeLabel(t, 'pg.modelsMaps.gl.mark.', m)}</option>)}
                </select>
                <select value={l.aggregation ?? 'sum'} aria-label={t('pg.modelsMaps.gl.aggFor', { name })}
                  onChange={e => patch(i, { aggregation: e.target.value })}
                  style={{ ...cell, flex: 1 }}>
                  {AGGREGATIONS.map(a => <option key={a} value={a}>{codeLabel(t, 'pg.modelsMaps.gl.agg.', a)}</option>)}
                </select>
                <select value={l.axis ?? 'left'} aria-label={t('pg.modelsMaps.gl.axisFor', { name })}
                  onChange={e => patch(i, { axis: e.target.value as 'left' | 'right' })}
                  style={{ ...cell, flex: 1 }}>
                  <option value="left">{t('pg.modelsMaps.gl.left')}</option>
                  <option value="right">{t('pg.modelsMaps.gl.right')}</option>
                </select>
              </div>
            </div>
          )
        })}
      </div>

      <button onClick={() => onChange([...layers,
        { measure: '', mark: 'bar', aggregation: 'sum', axis: 'left' }])}
        className="btn btn-ghost btn-sm"
        style={{ fontSize: 11, padding: '3px 8px', marginTop: 6 }}>
        {t('pg.modelsMaps.gl.add')}
      </button>
    </div>
  )
}
