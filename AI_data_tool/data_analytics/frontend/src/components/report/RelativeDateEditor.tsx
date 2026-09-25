import { useState } from 'react'
import { MODES, PRESETS, UNITS, describeSpec, presetOf, specProblem, usesN,
  type RelativeAnchor, type RelativeMode, type RelativeSpec, type RelativeUnit } from '../../lib/relativeDates'

interface Props {
  value: RelativeSpec
  onChange: (next: RelativeSpec) => void
  /** Prefix for accessible names, e.g. "Filter 2". */
  label: string
  compact?: boolean
}

/** Relative date picker: a preset list (one click for the common windows) and,
 *  under "Custom…", the parts. The anchor is always its own visible choice —
 *  never implied — and the sentence under it says exactly what will be kept. */
export default function RelativeDateEditor({ value, onChange, label, compact }: Props) {
  // "Custom…" is a mode of the editor, not of the spec: choosing it on a spec
  // that matches a preset must still open the parts.
  const [customOpen, setCustomOpen] = useState(false)
  const preset = customOpen ? 'custom' : presetOf(value)
  const problem = specProblem(value)
  const fs = compact ? 10 : 11
  const set = (patch: Partial<RelativeSpec>) => onChange({ ...value, ...patch })
  return (
    <div data-testid="relative-date-editor" style={{ display: 'flex', flexDirection: 'column', gap: 4, width: '100%' }}>
      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
        <select aria-label={`${label} period`} value={preset} style={{ fontSize: fs, flex: 1, minWidth: 110 }}
          onChange={e => {
            const p = PRESETS.find(x => x.id === e.target.value)
            setCustomOpen(!p)
            if (p) onChange({ ...p.spec, anchor: value.anchor })
          }}>
          {PRESETS.map(p => <option key={p.id} value={p.id}>{p.label}</option>)}
          <option value="custom">Custom…</option>
        </select>
        <select aria-label={`${label} counted from`} value={value.anchor} style={{ fontSize: fs }}
          onChange={e => set({ anchor: e.target.value as RelativeAnchor })}>
          <option value="data_max">from latest date in data</option>
          <option value="today">from today</option>
        </select>
      </div>
      {preset === 'custom' && (
        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', alignItems: 'center' }}>
          <select aria-label={`${label} mode`} value={value.mode} style={{ fontSize: fs }}
            onChange={e => set({ mode: e.target.value as RelativeMode })}>
            {MODES.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
          </select>
          {usesN(value.mode) && (
            <input aria-label={`${label} number of periods`} type="number" min={1} max={1000}
              value={value.n ?? ''} style={{ fontSize: fs, width: 56 }}
              onChange={e => set({ n: e.target.value === '' ? undefined : Number(e.target.value) })} />
          )}
          <select aria-label={`${label} unit`} value={value.unit} style={{ fontSize: fs }}
            onChange={e => set({ unit: e.target.value as RelativeUnit })}>
            {UNITS.map(u => <option key={u} value={u}>{u}{usesN(value.mode) ? 's' : ''}</option>)}
          </select>
          {value.mode === 'last' && value.unit !== 'day' && (
            <label style={{ fontSize: fs, display: 'inline-flex', gap: 3, alignItems: 'center' }}>
              <input type="checkbox" checked={!!value.include_current}
                onChange={e => set({ include_current: e.target.checked })} />
              include the current {value.unit}
            </label>
          )}
        </div>
      )}
      <div role={problem ? 'alert' : undefined} style={{ fontSize: 11, color: problem ? 'var(--danger)' : 'var(--muted)' }}>
        {problem ?? describeSpec(value)}
      </div>
    </div>
  )
}
