/**
 * Combine two edits of one widget made from the same starting point (E09).
 *
 * When a colleague saved the widget after this editor opened it, the server
 * refuses the editor's save and returns what the editor started from
 * (`base`) and what is stored now (`theirs`). With the editor's own edit
 * (`mine`), every setting falls into one of four cases:
 *
 *   - only I changed it       -> mine
 *   - only they changed it    -> theirs
 *   - we both made it equal   -> either
 *   - we both changed it, differently -> a conflict: the person chooses
 *
 * so two people who touched different settings lose nothing, and only a
 * setting both of them changed needs a decision. The title and the chart type
 * are settings like any other; each top-level config key is one setting (a
 * filter list or a display rule set is taken whole, not merged item by item:
 * half of each is rarely what either person meant).
 */

export interface WidgetEdit {
  widget_type: string
  title: string | null
  config: Record<string, unknown>
}

export interface MergeConflict {
  /** 'title', 'widget_type', or a config key. */
  key: string
  base: unknown
  theirs: unknown
  mine: unknown
}

export interface MergeResult {
  /** Every setting resolved, conflicts provisionally as theirs. */
  merged: WidgetEdit
  conflicts: MergeConflict[]
  /** How many settings came from each side without a question. */
  fromMine: number
  fromTheirs: number
}

const same = (a: unknown, b: unknown) => JSON.stringify(a ?? null) === JSON.stringify(b ?? null)

function pick(base: unknown, theirs: unknown, mine: unknown): 'mine' | 'theirs' | 'either' | 'conflict' {
  if (same(mine, theirs)) return 'either'
  if (same(mine, base)) return 'theirs'
  if (same(theirs, base)) return 'mine'
  return 'conflict'
}

export function mergeWidgetEdits(base: WidgetEdit, theirs: WidgetEdit, mine: WidgetEdit): MergeResult {
  const conflicts: MergeConflict[] = []
  let fromMine = 0, fromTheirs = 0
  const choose = (key: string, b: unknown, t: unknown, m: unknown) => {
    const which = pick(b, t, m)
    if (which === 'mine') { fromMine++; return m }
    if (which === 'theirs') { fromTheirs++; return t }
    if (which === 'conflict') conflicts.push({ key, base: b, theirs: t, mine: m })
    return t
  }
  const widget_type = choose('widget_type', base.widget_type, theirs.widget_type, mine.widget_type) as string
  const title = choose('title', base.title, theirs.title, mine.title) as string | null
  const config: Record<string, unknown> = {}
  const keys = new Set([...Object.keys(base.config ?? {}), ...Object.keys(theirs.config ?? {}),
                        ...Object.keys(mine.config ?? {})])
  for (const k of [...keys].sort()) {
    const v = choose(k, base.config?.[k], theirs.config?.[k], mine.config?.[k])
    if (v !== undefined) config[k] = v
  }
  return { merged: { widget_type, title, config }, conflicts, fromMine, fromTheirs }
}

/** The merged edit with each conflict settled as chosen ('mine' or 'theirs'). */
export function resolveMerge(result: MergeResult, choices: Record<string, 'mine' | 'theirs'>): WidgetEdit {
  const out: WidgetEdit = { ...result.merged, config: { ...result.merged.config } }
  for (const c of result.conflicts) {
    const v = choices[c.key] === 'mine' ? c.mine : c.theirs
    if (c.key === 'widget_type') out.widget_type = v as string
    else if (c.key === 'title') out.title = v as string | null
    else if (v === undefined) delete out.config[c.key]
    else out.config[c.key] = v
  }
  return out
}
