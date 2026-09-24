/**
 * Model Comparison inputs.
 *
 * A comparison widget stores a SNAPSHOT of each model it compares (response,
 * predictors, options), not just ids: the server refits every candidate on one
 * shared split, so it needs the specs, and a shared link or an embed must be
 * able to render the comparison without the builder around it.
 *
 * A snapshot can drift from the widget it was taken from (someone adds a
 * predictor). That is disclosed, never silently papered over: `staleSnapshots`
 * names the drifted ones and the panel offers a one-click update.
 */
import type { ReportPage, Widget } from '../types/report'

export type ComparableKind = 'linear' | 'logistic' | 'tree'

export const COMPARABLE: Record<string, ComparableKind> = {
  model_linear: 'linear',
  model_logistic: 'logistic',
  model_tree: 'tree',
}

export interface ModelSpec {
  id: number
  title: string
  model: ComparableKind
  response: string | null
  predictors: string[]
  event_value?: string
  max_depth?: number
  /** The Partition column the model holds out, when it has one. */
  partition?: string
}

const strList = (v: unknown): string[] =>
  Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string' && x !== '') : []

/** The spec the server refits, read from a model widget's config. */
export function modelSnapshot(w: Widget): ModelSpec | null {
  const model = COMPARABLE[w.widget_type]
  if (!model) return null
  const c = (w.config ?? {}) as Record<string, unknown>
  // A linear model's response sits in `measure` (it is a numeric role); the
  // others use `response`, which also accepts a yes/no text column.
  const response = (model === 'linear' ? c.measure : c.response)
  const spec: ModelSpec = {
    id: w.id,
    title: w.title || `${model} model`,
    model,
    response: typeof response === 'string' && response ? response : null,
    predictors: strList(c.predictors ?? c.measures),
  }
  if (typeof c.event_value === 'string' && c.event_value) spec.event_value = c.event_value
  if (typeof c.max_depth === 'number') spec.max_depth = c.max_depth
  if (typeof c.partition === 'string' && c.partition) spec.partition = c.partition
  return spec
}

export interface Candidate { widget: Widget; spec: ModelSpec; pageName: string }

/** Every comparable model in the report, the comparison's own page first. */
export function compareCandidates(pages: ReportPage[] | undefined, self: Widget): Candidate[] {
  const out: Candidate[] = []
  for (const p of pages ?? []) {
    for (const w of p.widgets ?? []) {
      if (w.id === self.id) continue
      const spec = modelSnapshot(w)
      if (spec) out.push({ widget: w, spec, pageName: p.name })
    }
  }
  const own = (c: Candidate) => (c.widget.page_id === self.page_id ? 0 : 1)
  return out.sort((a, b) => own(a) - own(b))
}

/** Why a candidate cannot join the current selection; null when it can. */
export function candidateBlockReason(spec: ModelSpec, chosen: ModelSpec[]): string | null {
  if (!spec.response) return 'has no response yet'
  const others = chosen.filter(c => c.id !== spec.id && c.response)
  const first = others[0]
  if (first && first.response !== spec.response) {
    return `predicts ${spec.response}, the others predict ${first.response}`
  }
  const part = others.find(c => c.partition)?.partition
  if (part && spec.partition && spec.partition !== part) {
    return `holds out ${spec.partition}, the others hold out ${part}`
  }
  return null
}

// Key order is not meaning: a snapshot that went through the database comes
// back with its keys sorted, and must not then read as "changed".
const canon = (s: ModelSpec) => JSON.stringify(
  Object.fromEntries(Object.entries({ ...s, title: '' }).filter(([, v]) => v !== undefined).sort(([a], [b]) => a.localeCompare(b))))
const same = (a: ModelSpec, b: ModelSpec) => canon(a) === canon(b)

/** Titles of stored snapshots whose model widget has changed or gone. */
export function staleSnapshots(stored: ModelSpec[], pages: ReportPage[] | undefined): string[] {
  const live = new Map<number, ModelSpec>()
  for (const p of pages ?? []) for (const w of p.widgets ?? []) {
    const s = modelSnapshot(w)
    if (s) live.set(w.id, s)
  }
  return stored.filter(s => { const l = live.get(s.id); return !l || !same(l, s) }).map(s => s.title)
}

/** Re-take the snapshots from the live widgets, dropping any that were deleted. */
export function refreshSnapshots(stored: ModelSpec[], pages: ReportPage[] | undefined): ModelSpec[] {
  const live = new Map<number, ModelSpec>()
  for (const p of pages ?? []) for (const w of p.widgets ?? []) {
    const s = modelSnapshot(w)
    if (s) live.set(w.id, s)
  }
  return stored.flatMap(s => { const l = live.get(s.id); return l ? [l] : [] })
}
