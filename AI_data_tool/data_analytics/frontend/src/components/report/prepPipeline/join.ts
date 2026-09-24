import type { PrepStep, Relationship } from '../../../services/api'

export function joinPairs(step: PrepStep): { left: string; right: string }[] {
  const ls = step.left_ons as string[] | undefined
  const rs = step.right_ons as string[] | undefined
  if (Array.isArray(ls) && Array.isArray(rs) && ls.length) {
    return ls.map((left, i) => ({ left, right: rs[i] ?? '' }))
  }
  return [{ left: (step.left_on as string) || '', right: (step.right_on as string) || '' }]
}

/** Write pairs back in the NARROWEST shape that fits: one pair stays
 *  `left_on`/`right_on`, so a single-key step's JSON is unchanged and older
 *  readers keep understanding it. */
export function writeJoinPairs(pairs: { left: string; right: string }[]): Partial<PrepStep> {
  if (pairs.length <= 1) {
    const p = pairs[0] ?? { left: '', right: '' }
    return { left_on: p.left, right_on: p.right, left_ons: undefined, right_ons: undefined }
  }
  return {
    left_ons: pairs.map(p => p.left), right_ons: pairs.map(p => p.right),
    left_on: undefined, right_on: undefined,
  }
}

//: Precedence from services/metadata/store.py: a human's approval outranks a
//: catalog FK, which outranks this platform's own guess.
const REL_RANK: Record<string, number> = { confirmed: 2, declared: 1, inferred: 0 }

/** The best known key pair between two datasets, or null when nothing links
 *  them. Relationships are undirected for this purpose: a link recorded as
 *  B -> A is still the answer when joining A to B, read the other way round. */
export function suggestJoinKeys(
  rels: Relationship[], baseId: number, targetId: number,
): { left_on: string; right_on: string; source: string; confidence: number } | null {
  const matches = rels
    .map(r => {
      if (r.from_dataset_id === baseId && r.to_dataset_id === targetId)
        return { left_on: r.from_column, right_on: r.to_column, source: r.source, confidence: r.confidence }
      if (r.to_dataset_id === baseId && r.from_dataset_id === targetId)
        return { left_on: r.to_column, right_on: r.from_column, source: r.source, confidence: r.confidence }
      return null
    })
    .filter(Boolean) as { left_on: string; right_on: string; source: string; confidence: number }[]
  if (!matches.length) return null
  return matches.sort((a, b) =>
    (REL_RANK[b.source] ?? 0) - (REL_RANK[a.source] ?? 0) || b.confidence - a.confidence)[0]
}

