/**
 * Schema autocomplete for the Browse SQL editor (4.3): the word being typed
 * at the caret, matched against table names and the columns of tables the
 * statement already mentions. No SQL parser -- a prefix match over names the
 * connection actually has is what saves the typing ("dep" -> dept_emp,
 * departments) without pretending to understand the query.
 */
export const SQL_KEYWORDS = ['SELECT', 'FROM', 'WHERE', 'GROUP BY', 'ORDER BY', 'JOIN', 'LEFT JOIN',
  'INNER JOIN', 'ON', 'AND', 'OR', 'COUNT', 'SUM', 'AVG', 'MIN', 'MAX', 'DISTINCT', 'AS', 'LIMIT', 'HAVING', 'IS NULL']

/** The identifier fragment ending at `caret`, and where it starts. */
export function wordAt(text: string, caret: number): { word: string; start: number } {
  let i = caret
  while (i > 0 && /[A-Za-z0-9_]/.test(text[i - 1])) i--
  return { word: text.slice(i, caret), start: i }
}

/** Tables named in the statement (whole-word matches only). */
export function mentionedTables(text: string, tables: string[]): string[] {
  const words = new Set((text.match(/[A-Za-z0-9_]+/g) ?? []).map(w => w.toLowerCase()))
  return tables.filter(t => words.has(t.toLowerCase()))
}

export function suggest(text: string, caret: number, tables: string[],
  columnsByTable: Record<string, string[]>, max = 8): { label: string; insert: string; kind: 'table' | 'column' | 'keyword' }[] {
  const { word } = wordAt(text, caret)
  if (word.length < 2) return []
  const w = word.toLowerCase()
  const out: { label: string; insert: string; kind: 'table' | 'column' | 'keyword' }[] = []
  const seen = new Set<string>()
  const push = (label: string, insert: string, kind: 'table' | 'column' | 'keyword') => {
    if (seen.has(insert.toLowerCase()) || insert.toLowerCase() === w) return
    seen.add(insert.toLowerCase())
    out.push({ label, insert, kind })
  }
  for (const t of tables) if (t.toLowerCase().startsWith(w)) push(t, t, 'table')
  for (const t of mentionedTables(text, tables)) {
    for (const c of columnsByTable[t] ?? []) if (c.toLowerCase().startsWith(w)) push(`${c} · ${t}`, c, 'column')
  }
  for (const k of SQL_KEYWORDS) if (k.toLowerCase().startsWith(w)) push(k, k, 'keyword')
  for (const t of tables) if (!t.toLowerCase().startsWith(w) && t.toLowerCase().includes(w)) push(t, t, 'table')
  return out.slice(0, max)
}

/** Replace the word at the caret with `insert`; returns the new text and caret. */
export function applySuggestion(text: string, caret: number, insert: string): { text: string; caret: number } {
  const { start } = wordAt(text, caret)
  const next = text.slice(0, start) + insert + text.slice(caret)
  return { text: next, caret: start + insert.length }
}
