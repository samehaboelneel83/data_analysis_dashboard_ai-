/**
 * "Your questions": one block at the top of a dashboard made by the guided
 * setup, answering every question the person ASKED -- from whichever chosen
 * page holds its chart, in that chart's own measured words -- or saying why it
 * could not be answered (persona test, plan 2.1). Built from the designs the
 * person chose; nothing is computed here.
 */
import type { SetupDesign, SuggestedWidget } from '../services/api'

type Question = { id: string; text: string; asked?: boolean }
type Words = { title: string; notOnPages: string }

const SEP = ' -- '

export function answersCard(chosen: SetupDesign[], questions: Question[], words: Words): SuggestedWidget | null {
  const asked = questions.filter(q => q.asked !== false && q.text.trim())
  if (!asked.length || !chosen.length) return null
  const lines = asked.map(q => {
    for (const d of chosen) {
      const w = (d.proposal.widgets ?? []).find(x => x.question === q.id && x.finding
        && !['table', 'list', 'text', 'button', 'slicer'].includes(x.widget_type))
      if (w) return `• ${q.text.replace(/[?؟]\s*$/, '')}: ${w.finding}`
    }
    // Why not, in the setup's own words, when a chosen page recorded it.
    for (const d of chosen) {
      const said = (d.proposal.unanswered ?? []).find(u => u.includes(q.text))
      if (said) return `• ${said.includes(SEP) ? `${q.text.replace(/[?؟]\s*$/, '')}: ${said.split(SEP).slice(1).join(SEP)}` : said}`
    }
    return `• ${q.text.replace(/[?؟]\s*$/, '')}: ${words.notOnPages}`
  })
  return { widget_type: 'text', title: words.title, config: { content: lines.join('\n') }, row_count: 1 }
}
