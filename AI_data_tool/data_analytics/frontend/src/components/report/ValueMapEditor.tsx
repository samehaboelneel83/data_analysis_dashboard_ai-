import type { DisplayRule } from '../../lib/displayRules'

interface Props {
  rule: DisplayRule
  onChange: (rule: DisplayRule) => void
}

/** Authoring surface for `kind: 'value_map'`. The engine has evaluated this shape
 *  since phase 1 (services/display_rules.py::_value_map_style) — including SAS's
 *  Any Category mode — but nothing ever created one, which is why the gap row sat
 *  at Partial rather than Yes. */
export default function ValueMapEditor({ rule, onChange }: Props) {
  const mappings = rule.mappings ?? []
  const emit = (patch: Partial<DisplayRule>) => onChange({ ...rule, kind: 'value_map', ...patch })

  return (
    <div style={{ display: 'grid', gap: 6 }}>
      <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12 }}>
        <input type="checkbox" checked={!!rule.any_category}
          onChange={e => emit({ any_category: e.target.checked })} />
        Any category
      </label>

      {mappings.map((m, i) => (
        <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          {/* Every per-row affordance is indexed, matching IntervalEditor: with two or
              more mappings an unindexed "Mapped value" / "Remove mapping" gives every
              row the same accessible name, so a screen reader announces a column of
              identical controls and getByRole('button', {name:/remove mapping/i})
              throws on the ambiguity. */}
          <label htmlFor={`vm-val-${rule.id}-${i}`} style={{ fontSize: 11 }}>Mapped value {i + 1}</label>
          <input id={`vm-val-${rule.id}-${i}`} value={String(m.value ?? '')}
            onChange={e => emit({ mappings: mappings.map((x, j) => j === i ? { ...x, value: e.target.value } : x) })} />
          <input type="color" aria-label={`Colour for mapping ${i + 1}`} value={m.color ?? '#6c8fff'}
            onChange={e => emit({ mappings: mappings.map((x, j) => j === i ? { ...x, color: e.target.value } : x) })} />
          <button type="button" onClick={() => emit({ mappings: mappings.filter((_, j) => j !== i) })}>
            Remove mapping {i + 1}
          </button>
        </div>
      ))}

      <button type="button" onClick={() => emit({ mappings: [...mappings, { value: '', color: '#6c8fff' }] })}>
        Add mapping
      </button>
    </div>
  )
}
