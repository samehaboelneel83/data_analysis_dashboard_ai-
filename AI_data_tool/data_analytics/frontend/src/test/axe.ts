import axe from 'axe-core'

/**
 * Accessibility violations under `node`, as readable lines (constitution rule 6:
 * accessible by construction -- checked on every test run, not once by hand).
 *
 * jsdom has no layout, so the rules that need one are off: colour contrast is
 * checked in a real browser (see MASTER_PLAN quality pass), and `region` only
 * makes sense for a whole page, not a component. Everything structural -- names,
 * roles, nesting, labels, ARIA validity -- runs.
 *
 * axe schedules work on timers: a test file that fakes timers must switch back
 * to real ones (`vi.useRealTimers()`) before calling this, or it never resolves.
 */
export async function axeViolations(node: Element, alsoDisable: string[] = []): Promise<string[]> {
  const rules: Record<string, { enabled: boolean }> = {
    'color-contrast': { enabled: false },
    region: { enabled: false },
  }
  for (const r of alsoDisable) rules[r] = { enabled: false }
  const res = await axe.run(node, { rules, resultTypes: ['violations'] })
  return res.violations.map(v =>
    `${v.id} (${v.impact}): ${v.help} -- ${v.nodes.slice(0, 3).map(n => n.target.join(' ')).join(' | ')}`)
}
