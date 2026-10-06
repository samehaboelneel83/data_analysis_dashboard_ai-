/** Terms a clarification sets apart -- **bold**, `code`, "quoted" -- that
 *  name one of the dataset's columns (redesign AB3). Case and
 *  spaces/underscores are ignored; the dataset's own spelling is returned, in
 *  the reply's order, once each. Offered as "Use <column>" chips. */
export function columnsMentioned(text: string, columns: string[]): string[] {
  const norm = (s: string) => s.trim().toLowerCase().replace(/[\s_-]+/g, '_')
  const byNorm = new Map(columns.map(c => [norm(c), c]))
  const out: string[] = []
  const re = /\*\*([^*]+)\*\*|`([^`]+)`|"([^"]+)"|“([^”]+)”|«([^»]+)»|'([^']+)'/g
  for (const m of text.matchAll(re)) {
    const term = m.slice(1).find(Boolean)
    const col = term ? byNorm.get(norm(term)) : undefined
    if (col && !out.includes(col)) out.push(col)
  }
  return out
}
