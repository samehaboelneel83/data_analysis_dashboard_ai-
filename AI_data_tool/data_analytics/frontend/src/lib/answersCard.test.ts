import { describe, it, expect } from 'vitest'
import { answersCard } from './answersCard'

const words = { title: 'Your questions', notOnPages: 'not answered on the pages chosen' }
const design = (widgets: Record<string, unknown>[], unanswered: string[] = []) =>
  ({ id: 'd', dataset_id: 1, dataset_name: 'x', derived: {}, history: [],
     proposal: { title: 'P', widgets, unanswered } }) as never

describe('answersCard (plan 2.1)', () => {
  const qs = [{ id: 'q1', text: 'Which item is weakest?', asked: true },
              { id: 'q2', text: 'How did it change?', asked: true },
              { id: 'q3', text: 'An idea the setup added', asked: false },
              { id: 'q4', text: 'Which region pays most?', asked: true }]

  it('answers each asked question from whichever chosen page holds it', () => {
    const card = answersCard([
      design([{ widget_type: 'bar', question: 'q1', finding: 'lowest: g (4.15)', config: {} }]),
      design([{ widget_type: 'kpi', question: 'q2', finding: '+12.0% (from 10 to 11.2)', config: {} }],
             ['This data could not answer: Which region pays most? -- no chart of these columns answers it']),
    ], qs, words)!
    expect(card.widget_type).toBe('text')
    expect(card.config.content).toBe([
      '• Which item is weakest: lowest: g (4.15)',
      '• How did it change: +12.0% (from 10 to 11.2)',
      '• Which region pays most: no chart of these columns answers it',
    ].join('\n'))
  })

  it('says when no chosen page answers it, and nothing when nothing was asked', () => {
    const card = answersCard([design([])], [{ id: 'q1', text: 'ما نسبة المرتجعات؟', asked: true }], words)!
    expect(card.config.content).toBe('• ما نسبة المرتجعات: not answered on the pages chosen')
    expect(answersCard([design([])], [{ id: 'q1', text: 'x', asked: false }], words)).toBeNull()
  })
})
