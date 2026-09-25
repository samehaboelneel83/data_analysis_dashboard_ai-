import { useState } from 'react'
import type { DisplayRule } from '../../lib/displayRules'

interface Props {
  rule: DisplayRule
  onChange: (rule: DisplayRule) => void
}

/** Authoring surface for `kind: 'data_bar'` — an in-cell proportional bar,
 *  Excel/Power-BI style. Min/Max are optional: left blank, the engine
 *  (services/display_rules.py::_data_bar_styles) scales to the column's own
 *  observed range instead of a fixed one, which is the right default for a
 *  measure whose range isn't known ahead of time. Same draft-typing problem
 *  IntervalEditor solves for its bounds: '-', '0.' are legitimate
 *  intermediate keystrokes, and a blank box means "auto", not "zero". */
export default function DataBarEditor({ rule, onChange }: Props) {
  const emit = (patch: Partial<DisplayRule>) => onChange({ ...rule, kind: 'data_bar', ...patch })

  const [minDraft, setMinDraft] = useState<string | null>(null)
  const [maxDraft, setMaxDraft] = useState<string | null>(null)

  const minValue = minDraft ?? (rule.min != null ? String(rule.min) : '')
  const maxValue = maxDraft ?? (rule.max != null ? String(rule.max) : '')

  const setBound = (which: 'min' | 'max', raw: string) => {
    (which === 'min' ? setMinDraft : setMaxDraft)(raw)
    if (raw.trim() === '') { emit({ [which]: undefined }); return }
    const parsed = Number(raw)
    if (!Number.isFinite(parsed)) return
    emit({ [which]: parsed })
  }

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
      <label style={{ fontSize: 11 }} htmlFor={`bar-min-${rule.id}`}>
        Minimum (blank = auto)
        <input id={`bar-min-${rule.id}`} type="text" inputMode="decimal"
          value={minValue} placeholder="auto"
          onChange={e => setBound('min', e.target.value)} />
      </label>
      <label style={{ fontSize: 11 }} htmlFor={`bar-max-${rule.id}`}>
        Maximum (blank = auto)
        <input id={`bar-max-${rule.id}`} type="text" inputMode="decimal"
          value={maxValue} placeholder="auto"
          onChange={e => setBound('max', e.target.value)} />
      </label>
      <label style={{ fontSize: 11 }} htmlFor={`bar-color-${rule.id}`}>
        Bar colour
        <input id={`bar-color-${rule.id}`} type="color" value={rule.color ?? '#60a5fa'}
          onChange={e => emit({ color: e.target.value })} />
      </label>
    </div>
  )
}
