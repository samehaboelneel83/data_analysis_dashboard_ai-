import type { DisplayRule } from '../../lib/displayRules'

/** Which controls a display-rule row should render, given the rule shape being
 *  authored — the same idea as widgetCapabilities.ts's `formattingCapabilities`, and
 *  for the same reason: the panel must not offer a control that the engine has no
 *  consumer for. A swatch that paints nothing is indistinguishable, from the author's
 *  side, from a swatch whose colour is wrong.
 *
 *  Every entry below is a statement about backend/app/services/display_rules.py:
 *
 *  - `column` — all three kinds read `rule.column`. An expression rule compiles
 *    against it (compileCondition), `_value_map_style` reads the cell to compare, and
 *    `_interval_style` reads the cell to bracket. It was previously rendered only in
 *    the expression branch, so a Bands rule inherited whichever column the rule
 *    happened to hold — for a freshly added rule the FIRST rule column, which is the
 *    categorical one — and `float("US")` then errored on every render with no control
 *    on screen to fix it. The one exception is value_map's Any Category mode, which
 *    scans every category column and never reads `rule.column` at all.
 *
 *  - `condition` — the structured operator/value editor. Only an expression rule has
 *    a `condition`; the other two kinds carry mappings/bands instead.
 *
 *  - `fill` — the rule's own `style`. `_rule_row_styles` consults `rule.style` for an
 *    expression rule, but for value_map and interval it returns the matched
 *    mapping's/band's own colour and never looks at `rule.style` at all. `rule.style`
 *    becomes load-bearing for those two kinds only at `target: 'background'`, where
 *    the match decides *whether* the rule fired and `style.background` supplies the
 *    colour that lands in ruleStyles.widget. The `visibility` target ignores `style`
 *    entirely for every kind.
 */
export type RuleControl = 'column' | 'condition' | 'fill'

// Both fields are optional here even though DisplayRule requires them: a rule that
// arrived from an older saved config (or from a hand-written import) can be missing
// either, and the panel must still decide what to render rather than throw.
type RuleShape = Partial<Pick<DisplayRule, 'kind' | 'target' | 'any_category'>>

export function ruleControls(rule: RuleShape): RuleControl[] {
  const kind = rule.kind ?? 'expression'
  const controls: RuleControl[] = []

  if (!(kind === 'value_map' && rule.any_category)) controls.push('column')

  if (kind === 'expression') {
    controls.push('condition')
    if (rule.target !== 'visibility') controls.push('fill')
    return controls
  }

  // value_map / interval: the mappings and bands carry their own colours.
  if (rule.target === 'background') controls.push('fill')
  return controls
}
