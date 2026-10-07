import type { ReactNode } from 'react'

/**
 * QA3 D5: numbers in prose keep their order whatever the paragraph's
 * direction. In a right-to-left paragraph a range "7.61–30.21" read
 * "30.21–7.61" (the en dash is neutral, so the two numbers swap), and a
 * leading "51" jumped to the end of the line. Each number, with its sign,
 * currency, % and a range partner, is set left-to-right in its own isolate.
 *
 * Used on text the server writes (insight narratives and findings), which is
 * English today and Arabic once the engine localizes (backend T12).
 */
const NUM = /[-+−]?[$€£]?\d[\d,]*(?:\.\d+)?%?(?:\s*[–—-]\s*[-+−]?[$€£]?\d[\d,]*(?:\.\d+)?%?)?/g

export function isolateNumbers(text: string | null | undefined): ReactNode {
  if (!text) return text ?? null
  const out: ReactNode[] = []
  let last = 0
  for (const m of text.matchAll(NUM)) {
    const at = m.index ?? 0
    if (at > last) out.push(text.slice(last, at))
    out.push(<bdi key={at} dir="ltr">{m[0]}</bdi>)
    last = at + m[0].length
  }
  if (last < text.length) out.push(text.slice(last))
  return out
}
