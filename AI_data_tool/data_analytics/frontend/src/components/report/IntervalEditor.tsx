import { useState } from 'react'
import type { DisplayRule } from '../../lib/displayRules'

interface Props {
  rule: DisplayRule
  onChange: (rule: DisplayRule) => void
}

type Bound = 'min' | 'max'

/** A fixed vocabulary, not a free-text field: Power BI's classic icon sets (traffic
 *  lights, symbols, arrows) all pick from a small closed list per threshold, and
 *  a fixed list is what lets WidgetRenderer render a glyph it knows is legible at
 *  table-cell size rather than trusting arbitrary author-typed text/emoji. */
const BAND_ICONS = ['✅', '⚠️', '❌', '▲', '▼'] as const

/** Authoring surface for `kind: 'interval'` — what a gauge rule actually is.
 *  The engine (services/display_rules.py::_interval_style) matches bands
 *  lower-inclusive / upper-exclusive, EXCEPT the last band's upper bound, which is
 *  inclusive so a value equal to the maximum lands in a band instead of falling
 *  through unstyled. An author cannot infer that, so the UI states it. */
export default function IntervalEditor({ rule, onChange }: Props) {
  const bands = rule.bands ?? []
  const emit = (patch: Partial<DisplayRule>) => onChange({ ...rule, kind: 'interval', ...patch })

  // A bound is typed one character at a time, and '-', '0.', '-0.' are all
  // legitimate intermediate states on the way to a real number. `Number('-')` is
  // NaN and `Number('0.')` is 0 (silently eating the point the instant it's typed),
  // so neither can drive what's on screen. The raw text the author is typing is
  // tracked here, independent of the numeric `bands` prop, and is what the input
  // renders while a draft exists for it. Only once a draft parses to a finite
  // number is it emitted upward as a real bound; a blank or still-incomplete draft
  // is left visibly as-is rather than snapped to 0 or some other number the author
  // never entered. Keyed by `${bandIndex}-${bound}` and reset whenever the bands
  // array is restructured (add/remove), since indices would otherwise point at the
  // wrong band after a shift.
  const [drafts, setDrafts] = useState<Record<string, string>>({})

  const draftKey = (i: number, bound: Bound) => `${i}-${bound}`

  const displayValue = (i: number, bound: Bound, stored: number) => {
    const key = draftKey(i, bound)
    return key in drafts ? drafts[key] : String(stored ?? '')
  }

  const setBound = (i: number, bound: Bound, raw: string) => {
    setDrafts(d => ({ ...d, [draftKey(i, bound)]: raw }))
    if (raw.trim() === '') return // cleared — stays visibly blank, nothing emitted
    const parsed = Number(raw)
    if (!Number.isFinite(parsed)) return // e.g. '-', '0.', '.': incomplete, don't emit yet
    emit({ bands: bands.map((b, j) => j === i ? { ...b, [bound]: parsed } : b) })
  }

  const setColor = (i: number, v: string) =>
    emit({ bands: bands.map((b, j) => j === i ? { ...b, color: v } : b) })

  const setIcon = (i: number, v: string) =>
    emit({
      bands: bands.map((b, j) => {
        if (j !== i) return b
        if (!v) { const { icon: _icon, ...rest } = b; return rest }
        return { ...b, icon: v }
      }),
    })

  const addBand = () => {
    setDrafts({})
    emit({ bands: [...bands, { min: 0, max: 0, color: '#f87171' }] })
  }

  const removeBand = (i: number) => {
    setDrafts({})
    emit({ bands: bands.filter((_, j) => j !== i) })
  }

  return (
    <div style={{ display: 'grid', gap: 6 }}>
      {bands.map((b, i) => (
        <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <label htmlFor={`bd-min-${rule.id}-${i}`} style={{ fontSize: 11 }}>Band {i + 1} minimum</label>
          <input id={`bd-min-${rule.id}-${i}`} type="text" inputMode="decimal"
            value={displayValue(i, 'min', b.min)}
            onChange={e => setBound(i, 'min', e.target.value)} />
          <label htmlFor={`bd-max-${rule.id}-${i}`} style={{ fontSize: 11 }}>Band {i + 1} maximum</label>
          <input id={`bd-max-${rule.id}-${i}`} type="text" inputMode="decimal"
            value={displayValue(i, 'max', b.max)}
            onChange={e => setBound(i, 'max', e.target.value)} />
          <input type="color" aria-label={`Colour for band ${i + 1}`} value={b.color ?? '#f87171'}
            onChange={e => setColor(i, e.target.value)} />
          <select aria-label={`Icon for band ${i + 1}`} value={b.icon ?? ''}
            onChange={e => setIcon(i, e.target.value)}>
            <option value="">No icon</option>
            {BAND_ICONS.map(icon => <option key={icon} value={icon}>{icon}</option>)}
          </select>
          <button type="button" onClick={() => removeBand(i)}>Remove band {i + 1}</button>
        </div>
      ))}

      <button type="button" onClick={addBand}>
        Add band
      </button>

      <p style={{ fontSize: 11, color: 'var(--muted)', margin: 0 }}>
        A band includes its minimum and excludes its maximum, so bands can sit end to end.
        The <strong>last band</strong> also includes its maximum, so a value equal to the
        top of the range is still coloured.
      </p>
    </div>
  )
}
