import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import DisplayRulesPanel from './DisplayRulesPanel'

describe('DisplayRulesPanel', () => {
  it('stores the compiled expression alongside the structured condition', () => {
    const onChange = vi.fn()
    render(<DisplayRulesPanel rules={[]} columns={['value', 'name']} numericColumns={['value']} onChange={onChange} />)

    fireEvent.click(screen.getByRole('button', { name: /add rule/i }))
    fireEvent.change(screen.getByLabelText(/column/i), { target: { value: 'value' } })
    fireEvent.change(screen.getByLabelText(/operator/i), { target: { value: 'gt' } })
    fireEvent.change(screen.getByLabelText(/^value$/i), { target: { value: '1000' } })

    const calls = onChange.mock.calls
    const saved = calls[calls.length - 1][0][0]
    expect(saved.expression).toBe('value > 1000')
    expect(saved.condition).toEqual({ op: 'gt', value: 1000, value2: undefined })
  })

  it('round-trips an existing rule back into the builder controls', () => {
    const rule = {
      id: 'r1', kind: 'expression' as const, target: 'mark' as const, column: 'value',
      expression: 'value > 1000', condition: { op: 'gt' as const, value: 1000 },
      style: { fill: '#f87171' },
    }
    render(<DisplayRulesPanel rules={[rule]} columns={['value']} onChange={vi.fn()} />)

    expect((screen.getByLabelText(/operator/i) as HTMLSelectElement).value).toBe('gt')
    expect((screen.getByLabelText(/^value$/i) as HTMLInputElement).value).toBe('1000')
  })

  it('shows a warning on the rule the engine could not evaluate', () => {
    const rule = { id: 'bad', kind: 'expression' as const, target: 'mark' as const,
                   column: 'value', expression: 'nope >', style: {} }
    render(
      <DisplayRulesPanel rules={[rule]} columns={['value']} onChange={vi.fn()}
        errors={[{ id: 'bad', message: 'Expression is not valid' }]} />
    )

    expect(screen.getByText(/Expression is not valid/i)).toBeInTheDocument()
  })

  it('leaves a numeric-looking value as a string on a column that is not numeric', () => {
    const onChange = vi.fn()
    // `region` is a text column here — coercing "2024" to a number would silently turn
    // `region == "2024"` into `region == 2024`, which can never match a text column.
    render(<DisplayRulesPanel rules={[]} columns={['region', 'value']} numericColumns={['value']} onChange={onChange} />)

    fireEvent.click(screen.getByRole('button', { name: /add rule/i }))
    fireEvent.change(screen.getByLabelText(/column/i), { target: { value: 'region' } })
    fireEvent.change(screen.getByLabelText(/operator/i), { target: { value: 'eq' } })
    fireEvent.change(screen.getByLabelText(/^value$/i), { target: { value: '2024' } })

    const calls = onChange.mock.calls
    const saved = calls[calls.length - 1][0][0]
    expect(saved.condition.value).toBe('2024')
    expect(saved.expression).toBe('region == "2024"')
  })

  it('does not compile a bogus "between" expression until the second value is filled in', () => {
    const onChange = vi.fn()
    render(<DisplayRulesPanel rules={[]} columns={['value']} numericColumns={['value']} onChange={onChange} />)

    fireEvent.click(screen.getByRole('button', { name: /add rule/i }))
    fireEvent.change(screen.getByLabelText(/operator/i), { target: { value: 'between' } })

    // Selecting "between" alone (before "To" is filled in) must not compile
    // literal(undefined) into the string "undefined" and hand it to onChange —
    // the 600ms debounced save in WidgetConfigPanel would persist exactly that if
    // the author navigated away at this point.
    let calls = onChange.mock.calls
    let saved = calls[calls.length - 1][0][0]
    expect(saved.expression).not.toContain('undefined')

    fireEvent.change(screen.getByLabelText(/^to$/i), { target: { value: '100' } })
    calls = onChange.mock.calls
    saved = calls[calls.length - 1][0][0]
    expect(saved.expression).toBe('(value >= 0) and (value <= 100)')
  })

  it('keys the colour by target — a background rule saves style.background, not style.fill', () => {
    // Regression for the bug where every rule, regardless of target, wrote its colour to
    // style.fill: the engine copies that dict verbatim into ruleStyles.widget, and
    // WidgetRenderer only reads ruleStyles.widget.background for the container paint, so
    // a background rule authored with style.fill silently did nothing.
    const onChange = vi.fn()
    const rule = {
      id: 'r1', kind: 'expression' as const, target: 'background' as const, column: 'value',
      expression: 'value > 1', condition: { op: 'gt' as const, value: 1 }, style: {},
    }
    render(<DisplayRulesPanel rules={[rule]} columns={['value']} onChange={onChange} />)

    fireEvent.change(screen.getByLabelText(/background/i), { target: { value: '#123456' } })

    const calls = onChange.mock.calls
    const saved = calls[calls.length - 1][0][0]
    expect(saved.style).toEqual({ background: '#123456' })
  })

  it('hides the colour control for a visibility-target rule, which the engine ignores', () => {
    const rule = {
      id: 'r1', kind: 'expression' as const, target: 'visibility' as const, column: 'value',
      expression: 'value > 1', condition: { op: 'gt' as const, value: 1 }, style: {},
    }
    render(<DisplayRulesPanel rules={[rule]} columns={['value']} onChange={vi.fn()} />)

    expect(screen.queryByLabelText(/^fill$/i)).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/^background$/i)).not.toBeInTheDocument()
  })

  it('removes a rule', () => {
    const onChange = vi.fn()
    const rule = { id: 'r1', kind: 'expression' as const, target: 'mark' as const,
                   column: 'value', expression: 'value > 1', style: {} }
    render(<DisplayRulesPanel rules={[rule]} columns={['value']} onChange={onChange} />)

    fireEvent.click(screen.getByRole('button', { name: /remove/i }))

    expect(onChange).toHaveBeenCalledWith([])
  })
})

// ── The two new rule kinds, driven the way an author reaches them ─────────────
// Both editors had unit tests against hand-built fixtures that already carried a
// correct `column`, so a panel that never rendered a Column control at all still
// went green. Everything below starts from "+ Add rule" and the Rule kind select —
// the only path an author has — and asserts the rule shape that leaves the panel,
// which is the shape display_rules.py has to evaluate.
describe('DisplayRulesPanel — Colour map and Bands authoring', () => {
  const COLUMNS = ['region', 'value', 'target']
  const NUMERIC = ['value', 'target']

  function addRuleOfKind(kind: 'value_map' | 'interval', onChange: ReturnType<typeof vi.fn>) {
    render(<DisplayRulesPanel rules={[]} columns={COLUMNS} numericColumns={NUMERIC} onChange={onChange} />)
    fireEvent.click(screen.getByRole('button', { name: /add rule/i }))
    fireEvent.change(screen.getByLabelText(/rule kind/i), { target: { value: kind } })
    const calls = onChange.mock.calls
    return calls[calls.length - 1][0][0]
  }

  it('lands a new Bands rule on a numeric column, not the categorical first column', () => {
    // The defect this pins: "Add rule → Rule kind: Bands" inherited columns[0] — the
    // categorical column — and _interval_style then did float("region_value") on every
    // render, so the rule errored from the moment it was created and nothing in the
    // Bands UI let the author correct it.
    const saved = addRuleOfKind('interval', vi.fn())

    expect(saved.kind).toBe('interval')
    expect(NUMERIC).toContain(saved.column)
    expect(saved.column).not.toBe('region')
  })

  it('renders a Column control for a Bands rule and offers only numeric columns', () => {
    // _interval_style coerces the cell with float(), so a categorical column is not a
    // choice the editor should be able to make.
    addRuleOfKind('interval', vi.fn())

    const select = screen.getByLabelText(/^column$/i) as HTMLSelectElement
    expect(Array.from(select.options).map(o => o.value)).toEqual(NUMERIC)
  })

  it('sends the Bands column choice to the rule as `column`, which is what the engine reads', () => {
    const onChange = vi.fn()
    addRuleOfKind('interval', onChange)

    fireEvent.change(screen.getByLabelText(/^column$/i), { target: { value: 'target' } })

    const calls = onChange.mock.calls
    expect(calls[calls.length - 1][0][0].column).toBe('target')
  })

  it('renders a Column control for a Colour map rule and sends the choice through', () => {
    const onChange = vi.fn()
    const saved = addRuleOfKind('value_map', onChange)
    // A colour map compares stringified values, so any column is legitimate here.
    expect(saved.column).toBe('region')

    const select = screen.getByLabelText(/^column$/i) as HTMLSelectElement
    expect(Array.from(select.options).map(o => o.value)).toEqual(COLUMNS)

    fireEvent.change(select, { target: { value: 'value' } })
    const calls = onChange.mock.calls
    expect(calls[calls.length - 1][0][0].column).toBe('value')
  })

  it('drops the expression fields when switching to a colour map, keeping the rule evaluable', () => {
    const saved = addRuleOfKind('value_map', vi.fn())

    expect(saved.expression).toBeUndefined()
    expect(saved.condition).toBeUndefined()
    expect(saved.mappings).toEqual([])
  })

  it('hides the Column control in Any Category mode, which never reads a column', () => {
    const onChange = vi.fn()
    addRuleOfKind('value_map', onChange)

    fireEvent.click(screen.getByLabelText(/any category/i))

    expect(screen.queryByLabelText(/^column$/i)).not.toBeInTheDocument()
  })

  it('offers no Fill swatch on a mark-target Colour map rule', () => {
    // _rule_row_styles returns the matched mapping's/band's own colour for these two
    // kinds and never consults rule.style, so a swatch here paints nothing at all.
    addRuleOfKind('value_map', vi.fn())

    expect(screen.queryByLabelText(/^fill$/i)).not.toBeInTheDocument()
  })

  it('offers no Fill swatch on a mark-target Bands rule either', () => {
    addRuleOfKind('interval', vi.fn())

    expect(screen.queryByLabelText(/^fill$/i)).not.toBeInTheDocument()
  })

  it('does offer the swatch at the background target, where rule.style is what paints', () => {
    // Here the mapping only decides WHETHER the rule fired; style.background is the
    // colour the engine copies into ruleStyles.widget.
    const onChange = vi.fn()
    addRuleOfKind('interval', onChange)

    fireEvent.change(screen.getByLabelText(/applies to/i), { target: { value: 'background' } })
    fireEvent.change(screen.getByLabelText(/^background$/i), { target: { value: '#123456' } })

    const calls = onChange.mock.calls
    expect(calls[calls.length - 1][0][0].style).toEqual({ background: '#123456' })
  })

  it('keeps the Fill swatch for a mark-target expression rule, which does read rule.style', () => {
    const onChange = vi.fn()
    render(<DisplayRulesPanel rules={[]} columns={COLUMNS} numericColumns={NUMERIC} onChange={onChange} />)
    fireEvent.click(screen.getByRole('button', { name: /add rule/i }))

    expect(screen.getByLabelText(/^fill$/i)).toBeInTheDocument()
  })

  it('carries the column through a round trip back to Expression', () => {
    const onChange = vi.fn()
    addRuleOfKind('interval', onChange)
    fireEvent.change(screen.getByLabelText(/^column$/i), { target: { value: 'target' } })
    fireEvent.change(screen.getByLabelText(/rule kind/i), { target: { value: 'expression' } })

    const calls = onChange.mock.calls
    const saved = calls[calls.length - 1][0][0]
    expect(saved.column).toBe('target')
    expect(saved.expression).toContain('target')
  })
})

describe('DisplayRulesPanel — Data bar authoring', () => {
  const COLUMNS = ['region', 'value', 'target']
  const NUMERIC = ['value', 'target']

  function addDataBarRule(onChange: ReturnType<typeof vi.fn>) {
    render(<DisplayRulesPanel rules={[]} columns={COLUMNS} numericColumns={NUMERIC} onChange={onChange} />)
    fireEvent.click(screen.getByRole('button', { name: /add rule/i }))
    fireEvent.change(screen.getByLabelText(/rule kind/i), { target: { value: 'data_bar' } })
    const calls = onChange.mock.calls
    return calls[calls.length - 1][0][0]
  }

  it('lands a new Data bar rule on a numeric column, like Bands', () => {
    // _data_bar_style coerces the cell with to_numeric(), same constraint as Bands.
    const saved = addDataBarRule(vi.fn())

    expect(saved.kind).toBe('data_bar')
    expect(NUMERIC).toContain(saved.column)
    expect(saved.column).not.toBe('region')
  })

  it('renders a Column control for a Data bar rule and offers only numeric columns', () => {
    addDataBarRule(vi.fn())

    const select = screen.getByLabelText(/^column$/i) as HTMLSelectElement
    expect(Array.from(select.options).map(o => o.value)).toEqual(NUMERIC)
  })

  it('renders the DataBarEditor (min/max/colour), not the Bands or Colour map editor', () => {
    addDataBarRule(vi.fn())

    expect(screen.getByLabelText(/minimum/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/maximum/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/bar colour/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /add band/i })).toBeNull()
  })

  it('drops the expression fields when switching to a data bar, keeping the rule evaluable', () => {
    const onChange = vi.fn()
    addDataBarRule(onChange)

    const saved = onChange.mock.calls[onChange.mock.calls.length - 1][0][0]
    expect(saved.condition).toBeUndefined()
    expect(saved.expression).toBeUndefined()
  })
})
