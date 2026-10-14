import type { ReactNode } from 'react'

/** One SQL statement, always left-to-right, with its keywords and strings
 *  picked out (step 10 design: `.sql .kw` / `.st`). Display only: the text
 *  is the query exactly as it ran. */

const KEYWORDS = new Set(('select from where group by order having limit offset as and or not in is null like between ' +
  'join left right inner outer full cross on union all distinct case when then else end with over partition asc desc ' +
  'sum avg count min max round cast coalesce date_trunc interval current_date').split(' '))

/** Split into strings ('…'), quoted names ("…"), words and everything else. */
const TOKEN = /('(?:[^']|'')*')|("(?:[^"]|"")*")|([A-Za-z_][A-Za-z0-9_]*)|([^'"A-Za-z_]+)/g

export function sqlTokens(sql: string): { text: string; kind: 'kw' | 'str' | null }[] {
  const out: { text: string; kind: 'kw' | 'str' | null }[] = []
  for (const m of sql.matchAll(TOKEN)) {
    if (m[1]) out.push({ text: m[1], kind: 'str' })
    else if (m[3] && KEYWORDS.has(m[3].toLowerCase())) out.push({ text: m[3], kind: 'kw' })
    else out.push({ text: m[0], kind: null })
  }
  return out
}

export default function SqlBlock({ sql }: { sql: string }) {
  const parts: ReactNode[] = sqlTokens(sql).map((tok, i) =>
    tok.kind ? <span key={i} className={`dl-sqlb__${tok.kind}`}>{tok.text}</span> : tok.text)
  return <pre dir="ltr" className="dl-sqlb__code"><code>{parts}</code></pre>
}
