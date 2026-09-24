import { describe, it, expect } from 'vitest'
import { ruleControls } from './ruleCapabilities'

// Each expectation below is a claim about display_rules.py, not about layout: a
// control is listed only where the engine reads the field it writes.
describe('ruleControls', () => {
  it('gives an expression rule a column, a condition and a fill', () => {
    expect(ruleControls({ kind: 'expression', target: 'mark' }))
      .toEqual(['column', 'condition', 'fill'])
  })

  it('drops the fill for a visibility rule, whose target ignores style entirely', () => {
    expect(ruleControls({ kind: 'expression', target: 'visibility' }))
      .not.toContain('fill')
  })

  it('gives value_map and interval a column but no fill at the mark target', () => {
    // _rule_row_styles returns the matched mapping's/band's colour and never consults
    // rule.style for these two kinds.
    for (const kind of ['value_map', 'interval'] as const) {
      const controls = ruleControls({ kind, target: 'mark' })
      expect(controls).toContain('column')
      expect(controls).not.toContain('fill')
      expect(controls).not.toContain('condition')
    }
  })

  it('restores the fill for value_map and interval at the background target', () => {
    // There the match only decides WHETHER the rule fired; style.background carries
    // the colour into ruleStyles.widget.
    for (const kind of ['value_map', 'interval'] as const) {
      expect(ruleControls({ kind, target: 'background' })).toContain('fill')
    }
  })

  it('drops the column control in Any Category mode, which never reads one', () => {
    expect(ruleControls({ kind: 'value_map', target: 'mark', any_category: true }))
      .not.toContain('column')
  })

  it('treats a rule with no kind as an expression rule', () => {
    expect(ruleControls({ kind: undefined, target: 'mark' })).toContain('condition')
  })
})
