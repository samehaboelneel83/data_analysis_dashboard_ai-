import { useState } from 'react'
import { compileCondition } from '../../lib/displayRules'
import type { DisplayRule, RuleCondition, RuleOperator } from '../../lib/displayRules'
import ValueMapEditor from './ValueMapEditor'
import IntervalEditor from './IntervalEditor'
import DataBarEditor from './DataBarEditor'
import { ruleControls } from './ruleCapabilities'

const RULE_KINDS: { value: DisplayRule['kind']; label: string }[] = [
  { value: 'expression', label: 'Expression' },
  { value: 'value_map', label: 'Colour map' },
  { value: 'interval', label: 'Bands' },
  { value: 'data_bar', label: 'Data bar' },
]

const OPERATORS: { value: RuleOperator; label: string }[] = [
  { value: 'gt', label: 'is greater than' }, { value: 'gte', label: 'is at least' },
  { value: 'lt', label: 'is less than' },    { value: 'lte', label: 'is at most' },
  { value: 'eq', label: 'equals' },          { value: 'ne', label: 'does not equal' },
  { value: 'between', label: 'is between' }, { value: 'in', label: 'is one of' },
  { value: 'isnull', label: 'is blank' },    { value: 'notnull', label: 'is not blank' },
]

interface Props {
  rules: DisplayRule[]
  columns: string[]
  // Which of `columns` are numeric — drives coercion below. Omitted/absent columns are
  // treated as non-numeric (dtype unknown or genuinely categorical), never guessed at.
  numericColumns?: string[]
  onChange: (rules: DisplayRule[]) => void
  errors?: { id?: string; message: string }[]
}

// Numbers must survive as numbers on a numeric column: `value > "1000"` compares a
// Series to a string. But coercing every numeric-looking string regardless of column
// is the mirror-image bug: `region == "2024"` on a text column would silently become
// `region == 2024` and never match. Only coerce when the caller has told us the
// column is numeric; otherwise leave the value exactly as typed.
const coerce = (raw: string, isNumeric: boolean): unknown =>
  isNumeric && raw !== '' && !isNaN(Number(raw)) ? Number(raw) : raw

const inp: React.CSSProperties = { fontSize: 11, padding: '3px 6px', width: '100%',
  background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 4, color: 'var(--text)' }

const lbl: React.CSSProperties = { display: 'block', fontSize: 10.5, color: 'var(--muted)', marginBottom: 2 }

export default function DisplayRulesPanel({ rules: initialRules, columns, numericColumns, onChange, errors }: Props) {
  // Own the working copy locally: the caller's `onChange` reports the new array upward,
  // but nothing guarantees the resulting `rules` prop round-trips back down before the
  // author's next keystroke (e.g. a debounced save). Rendering from local state keeps the
  // controls responsive; the panel is remounted (keyed on widget id) when the author
  // switches widgets, so this never goes stale across widgets.
  const [rules, setRules] = useState<DisplayRule[]>(initialRules)

  const commit = (next: DisplayRule[]) => {
    setRules(next)
    onChange(next)
  }

  const update = (i: number, patch: Partial<DisplayRule>) => {
    const next = rules.map((r, j) => (j === i ? { ...r, ...patch } : r))
    const rule = next[i]
    // Recompile on every edit so the stored expression can never drift from the
    // structured condition an author is looking at. Exception: "between" needs both
    // ends of the range — recompiling the instant the operator is picked (before "To"
    // is filled in) would compile literal(undefined) into the string "undefined" and
    // persist it via the debounced save if the author navigates away mid-edit. Wait
    // for value2 to be set before compiling; the expression stays at its prior value
    // (still syntactically valid) in the meantime.
    const readyToCompile = !(rule.condition?.op === 'between' && rule.condition.value2 === undefined)
    if (rule.condition && rule.column && readyToCompile) {
      rule.expression = compileCondition(rule.column, rule.condition)
    }
    commit(next)
  }

  // Switching kind needs more than a field merge: an expression rule's `condition` and
  // `expression` are meaningless once the rule is a colour map (and vice versa), so
  // leaving them behind would let a stale condition silently recompile over a value_map
  // rule the moment `update` next runs. Rebuild the kind-specific fields from scratch,
  // carrying over only what still makes sense (existing mappings/bands/condition when
  // toggling back), and commit directly rather than going through `update`'s
  // condition-driven recompile.
  const changeKind = (i: number, kind: DisplayRule['kind']) => {
    const rule = rules[i]
    let patch: Partial<DisplayRule>
    if (kind === 'value_map') {
      // The engine stringifies both sides of the comparison (_value_map_style), so a
      // colour map is happy on any column — the inherited one is kept, and columns[0]
      // is the categorical column, which is what a colour map usually wants anyway.
      patch = { kind, column: rule.column ?? columns[0] ?? 'value',
        mappings: rule.mappings ?? [], any_category: rule.any_category ?? false,
        condition: undefined, expression: undefined }
    } else if (kind === 'interval') {
      // A band rule does float(cell), so the ONE column it can never use is the
      // categorical one — which is exactly what columns[0] is. Carrying the inherited
      // column over unchecked is how "Add rule → Bands" produced a rule that errored
      // on every render. Land on a numeric column instead.
      patch = { kind, column: intervalColumn(rule.column), bands: rule.bands ?? [],
        condition: undefined, expression: undefined }
    } else if (kind === 'data_bar') {
      // Same float()/to_numeric() constraint as Bands, and a bar only ever paints a
      // mark — there is no meaningful "widget background" or "hide the widget" a
      // continuous 0..1 proportion could drive, so target is fixed rather than offered.
      patch = { kind, target: 'mark', column: intervalColumn(rule.column),
        min: rule.min, max: rule.max, color: rule.color,
        condition: undefined, expression: undefined }
    } else {
      const column = rule.column ?? columns[0] ?? 'value'
      const condition = rule.condition ?? { op: 'gt', value: 0 }
      patch = { kind, column, condition, expression: compileCondition(column, condition) }
    }
    commit(rules.map((r, j) => (j === i ? { ...r, ...patch } : r)))
  }

  // Columns a band rule may name: numeric ones only, because _interval_style coerces
  // the cell with float() and anything else is an error the author cannot see the
  // cause of. The two empty cases are NOT the same and must not share a fallback:
  //   * `numericColumns` undefined — the caller knows nothing about dtypes. Offer
  //     every column; an unknown dtype is not evidence of a bad column.
  //   * `numericColumns` provided and nothing matches — the caller has told us this
  //     result has no numeric column at all. Offering every column here would walk
  //     the author straight back into a text column and the float() error this
  //     control exists to prevent, so offer none and say why (noNumericColumns).
  const numericRuleColumns = columns.filter(c => numericColumns?.includes(c))
  const dtypesKnown = numericColumns !== undefined
  const intervalColumns = dtypesKnown ? numericRuleColumns : columns
  const noNumericColumns = dtypesKnown && numericRuleColumns.length === 0
  const intervalColumn = (current?: string) =>
    (current && intervalColumns.includes(current)) ? current : (intervalColumns[0] ?? 'value')

  const addRule = () => commit([...rules, {
    id: crypto.randomUUID(), kind: 'expression', target: 'mark',
    column: columns[0] ?? 'value', condition: { op: 'gt', value: 0 },
    expression: compileCondition(columns[0] ?? 'value', { op: 'gt', value: 0 }),
    style: { fill: '#f87171' },
  }])

  return (
    <div>
      <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase',
        letterSpacing: '.06em', marginBottom: 8 }}>
        Display Rules
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {rules.map((rule, i) => {
          const error = errors?.find(e => e.id === rule.id)
          const cond: RuleCondition = rule.condition ?? { op: 'gt' }

          const wrapperStyle: React.CSSProperties = { border: '1px solid var(--border)',
            borderRadius: 5, background: 'var(--surface2)', overflow: 'hidden', padding: '7px 8px' }

          // Shared across all three kinds: which rule shape this row authors.
          const kindSelect = (
            <label style={{ ...lbl, flex: '1 1 110px' }} htmlFor={`kind-${rule.id}`}>
              Rule kind
              <select id={`kind-${rule.id}`} value={rule.kind} style={inp}
                onChange={e => changeKind(i, e.target.value as DisplayRule['kind'])}>
                {RULE_KINDS.map(k => <option key={k.value} value={k.value}>{k.label}</option>)}
              </select>
            </label>
          )

          // Which controls this rule shape has a live consumer for — see
          // ruleCapabilities.ts, which traces each one to display_rules.py.
          const controls = ruleControls(rule)

          // Shared across all three kinds: the column the rule reads from. It used to
          // be rendered only in the expression branch, which left a Bands rule
          // silently pointing at whatever column it inherited — invisible and
          // unfixable from the editor the author was looking at.
          // The offered list stays exactly what the caller says the shaped result will
          // contain (`ruleColumns` is frame-aware) — narrowed to the numeric ones for a
          // Bands rule, which can only read a number. A rule already naming something
          // outside that list renders as an empty select rather than having its stale
          // value smuggled into the options: an unselectable blank next to the engine's
          // error is a prompt to pick a real column, whereas offering the bad one back
          // would suggest it is a legitimate choice.
          const colOptions = (rule.kind === 'interval' || rule.kind === 'data_bar') ? intervalColumns : columns
          const colValue = rule.column ?? ''
          // A select with no options is itself a control that cannot do anything, so
          // it is not rendered — the note below explains the empty case instead.
          const showColumnSelect = controls.includes('column') && colOptions.length > 0

          const columnSelect = (
            <label style={{ ...lbl, flex: '1 1 90px' }} htmlFor={`col-${rule.id}`}>
              Column
              <select id={`col-${rule.id}`} value={colValue} style={inp}
                onChange={e => update(i, { column: e.target.value })}>
                {colOptions.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </label>
          )

          const targetSelect = (
            <label style={{ ...lbl, flex: '1 1 110px' }} htmlFor={`target-${rule.id}`}>
              Applies to
              <select id={`target-${rule.id}`} value={rule.target} style={inp}
                onChange={e => update(i, { target: e.target.value as DisplayRule['target'] })}>
                <option value="mark">The mark</option>
                <option value="background">Widget background</option>
                <option value="visibility">Hide the widget</option>
              </select>
            </label>
          )

          // Rendered only where `rule.style` has a consumer (see ruleCapabilities.ts):
          // the visibility target ignores `style` entirely, and a value_map/interval
          // rule painting a mark takes its colour from the matched mapping or band and
          // never consults `rule.style` — so a swatch there would be a control the
          // author can turn all day with nothing changing on screen. For the
          // background target, the colour must be keyed as `style.background`, not
          // `style.fill`: the engine copies this dict verbatim into
          // ruleStyles.widget, and WidgetRenderer only reads
          // ruleStyles.widget.background for the container's own paint.
          const fillControl = controls.includes('fill') && (
            <label style={{ ...lbl, flex: '0 0 auto' }} htmlFor={`fill-${rule.id}`}>
              {rule.target === 'background' ? 'Background' : 'Fill'}
              <input id={`fill-${rule.id}`} type="color"
                value={(rule.target === 'background' ? rule.style?.background : rule.style?.fill) ?? '#f87171'}
                style={{ width: 36, height: 26, padding: 2, border: '1px solid var(--border)', borderRadius: 4, cursor: 'pointer', background: 'var(--surface)' }}
                onChange={e => update(i, {
                  style: rule.target === 'background' ? { background: e.target.value } : { fill: e.target.value },
                })} />
            </label>
          )

          if (rule.kind === 'value_map') return (
            <div key={rule.id} style={wrapperStyle}>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
                {kindSelect}
                {showColumnSelect && columnSelect}
                {targetSelect}
                {fillControl}
              </div>

              <div style={{ marginTop: 6 }}>
                <ValueMapEditor rule={rule} onChange={next => update(i, next)} />
              </div>

              {rule.target === 'visibility' && (
                <p style={{ fontSize: 10.5, color: 'var(--muted)', margin: '4px 0 0' }}>
                  Presentational only — matching rows are still sent to the client, and a
                  broken visibility rule reveals the widget (rules fail open). Not a
                  substitute for row-level security.
                </p>
              )}

              {error && <div role="alert" style={{ color: '#f87171', fontSize: 11, marginTop: 5 }}>{error.message}</div>}

              <button type="button" onClick={() => commit(rules.filter((_, j) => j !== i))}
                style={{ marginTop: 6, background: 'none', border: 'none', color: 'var(--muted)', cursor: 'pointer', fontSize: 11, padding: 0 }}>
                Remove
              </button>
            </div>
          )

          if (rule.kind === 'interval') return (
            <div key={rule.id} style={wrapperStyle}>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
                {kindSelect}
                {showColumnSelect && columnSelect}
                {targetSelect}
                {fillControl}
              </div>

              {noNumericColumns && (
                <p role="note" style={{ fontSize: 10.5, color: '#f87171', margin: '4px 0 0' }}>
                  A Bands rule reads a number, and this widget has no numeric column to
                  read. Pick a different rule kind, or add a numeric field.
                </p>
              )}

              <div style={{ marginTop: 6 }}>
                <IntervalEditor rule={rule} onChange={next => update(i, next)} />
              </div>

              {rule.target === 'visibility' && (
                <p style={{ fontSize: 10.5, color: 'var(--muted)', margin: '4px 0 0' }}>
                  Presentational only — matching rows are still sent to the client, and a
                  broken visibility rule reveals the widget (rules fail open). Not a
                  substitute for row-level security.
                </p>
              )}

              {error && <div role="alert" style={{ color: '#f87171', fontSize: 11, marginTop: 5 }}>{error.message}</div>}

              <button type="button" onClick={() => commit(rules.filter((_, j) => j !== i))}
                style={{ marginTop: 6, background: 'none', border: 'none', color: 'var(--muted)', cursor: 'pointer', fontSize: 11, padding: 0 }}>
                Remove
              </button>
            </div>
          )

          if (rule.kind === 'data_bar') return (
            <div key={rule.id} style={wrapperStyle}>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
                {kindSelect}
                {showColumnSelect && columnSelect}
              </div>

              {noNumericColumns && (
                <p role="note" style={{ fontSize: 10.5, color: '#f87171', margin: '4px 0 0' }}>
                  A Data bar rule reads a number, and this widget has no numeric column
                  to read. Pick a different rule kind, or add a numeric field.
                </p>
              )}

              <div style={{ marginTop: 6 }}>
                <DataBarEditor rule={rule} onChange={next => update(i, next)} />
              </div>

              {error && <div role="alert" style={{ color: '#f87171', fontSize: 11, marginTop: 5 }}>{error.message}</div>}

              <button type="button" onClick={() => commit(rules.filter((_, j) => j !== i))}
                style={{ marginTop: 6, background: 'none', border: 'none', color: 'var(--muted)', cursor: 'pointer', fontSize: 11, padding: 0 }}>
                Remove
              </button>
            </div>
          )

          // A hand-written expression has no structured form to render controls from.
          if (!rule.condition) return (
            <div key={rule.id} style={wrapperStyle}>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5, marginBottom: 6 }}>
                {kindSelect}
              </div>
              <label htmlFor={`expr-${rule.id}`} style={lbl}>Expression</label>
              <input id={`expr-${rule.id}`} value={rule.expression ?? ''} readOnly style={inp} />
              {error && <div role="alert" style={{ color: '#f87171', fontSize: 11, marginTop: 4 }}>{error.message}</div>}
              <button type="button" onClick={() => commit(rules.filter((_, j) => j !== i))}
                style={{ marginTop: 6, background: 'none', border: 'none', color: 'var(--muted)', cursor: 'pointer', fontSize: 11, padding: 0 }}>
                Remove
              </button>
            </div>
          )

          return (
            <div key={rule.id} style={wrapperStyle}>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
                {kindSelect}
                {showColumnSelect && columnSelect}

                <label style={{ ...lbl, flex: '1 1 110px' }} htmlFor={`op-${rule.id}`}>
                  Operator
                  <select id={`op-${rule.id}`} value={cond.op} style={inp}
                    onChange={e => update(i, { condition: { ...cond, op: e.target.value as RuleOperator } })}>
                    {OPERATORS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </select>
                </label>

                {cond.op !== 'isnull' && cond.op !== 'notnull' && (() => {
                  const isNumeric = !!rule.column && !!numericColumns?.includes(rule.column)
                  return (<>
                    <label style={{ ...lbl, flex: '1 1 70px' }} htmlFor={`val-${rule.id}`}>
                      Value
                      <input id={`val-${rule.id}`} value={String(cond.value ?? '')} style={inp}
                        onChange={e => update(i, { condition: { ...cond, value: coerce(e.target.value, isNumeric) } })} />
                    </label>
                    {cond.op === 'between' && (
                      <label style={{ ...lbl, flex: '1 1 70px' }} htmlFor={`val2-${rule.id}`}>
                        To
                        <input id={`val2-${rule.id}`} value={String(cond.value2 ?? '')} style={inp}
                          onChange={e => update(i, { condition: { ...cond, value2: coerce(e.target.value, isNumeric) } })} />
                      </label>
                    )}
                  </>)
                })()}

                {targetSelect}
                {fillControl}
              </div>

              {rule.target === 'visibility' && (
                <p style={{ fontSize: 10.5, color: 'var(--muted)', margin: '4px 0 0' }}>
                  Presentational only — matching rows are still sent to the client, and a
                  broken visibility rule reveals the widget (rules fail open). Not a
                  substitute for row-level security.
                </p>
              )}

              {error && <div role="alert" style={{ color: '#f87171', fontSize: 11, marginTop: 5 }}>{error.message}</div>}

              <button type="button" onClick={() => commit(rules.filter((_, j) => j !== i))}
                style={{ marginTop: 6, background: 'none', border: 'none', color: 'var(--muted)', cursor: 'pointer', fontSize: 11, padding: 0 }}>
                Remove
              </button>
            </div>
          )
        })}
      </div>

      <button type="button" onClick={addRule}
        style={{ marginTop: 8, width: '100%', padding: '5px 0', background: 'var(--surface2)',
          border: '1px dashed var(--border)', borderRadius: 5, color: 'var(--accent)', cursor: 'pointer', fontSize: 11 }}>
        + Add rule
      </button>

      {rules.length === 0 && (
        <p style={{ fontSize: 11, color: 'var(--muted)', textAlign: 'center', padding: '8px 0', margin: 0 }}>
          No display rules yet
        </p>
      )}
    </div>
  )
}
