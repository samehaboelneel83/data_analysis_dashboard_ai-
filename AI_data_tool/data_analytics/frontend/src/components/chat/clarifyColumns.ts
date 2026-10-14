/** The dataset's columns a clarification names, offered as "Use <column>"
 *  chips (redesign AB3). First the terms it sets apart -- **bold**, `code`,
 *  "quoted" -- then plain whole-word mentions (QA B3: the model writes "the
 *  highest revenue"), where a column's first word stands for it when no other
 *  column starts the same way ("margin" -> margin_pct). Case and
 *  spaces/underscores are ignored; the dataset's own spelling is returned, in
 *  the reply's order, once each. */
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
  // Plain words. Each column, and its first word when unique, as a whole-word
  // phrase; the hits are ordered by where they appear in the reply.
  const words = (c: string) => c.toLowerCase().split(/[\s_-]+/).filter(Boolean)
  const firsts = new Map<string, number>()
  for (const c of columns) { const f = words(c)[0]; if (f) firsts.set(f, (firsts.get(f) ?? 0) + 1) }
  const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const plain: { col: string; at: number }[] = []
  for (const c of columns) {
    const ws = words(c)
    if (!ws.length) continue
    const phrases = [ws.map(esc).join('[\\s_-]+')]
    if (ws.length > 1 && firsts.get(ws[0]) === 1 && ws[0].length >= 3) phrases.push(esc(ws[0]))
    let at = -1
    for (const ph of phrases) {
      const m = new RegExp(`(^|[^\\p{L}\\p{N}_])(${ph})(?=$|[^\\p{L}\\p{N}_])`, 'iu').exec(text)
      if (m && (at < 0 || m.index < at)) at = m.index + m[1].length
    }
    if (at >= 0) plain.push({ col: c, at })
  }
  for (const { col } of plain.sort((a, b) => a.at - b.at)) if (!out.includes(col)) out.push(col)
  return out
}
