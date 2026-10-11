import { describe, it, expect } from 'vitest'
import path from 'node:path'
import { hardcodedStrings } from './hardcodedStrings'
import { en, ar } from '../i18n/pages/askAi'

/** Step 10: no hard-coded English on the redesigned Ask AI page. Each part
 *  adds the files it builds or restyles. */
const FILES: string[] = [
  // Part A
  'pages/AskAI.tsx',
  'pages/ask/AskHero.tsx',
  'pages/ask/AskIllustration.tsx',
  'pages/ask/AskRobot.tsx',
  'pages/ask/DataPicker.tsx',
  'pages/ask/SuggestionGrid.tsx',
  // Part B
  'components/chat/RobotHead.tsx',
  'components/chat/CardSection.tsx',
  'components/chat/SqlBlock.tsx',
  'components/chat/Pending.tsx',
]

describe('no hard-coded English: Ask AI (step 10)', () => {
  it.each(FILES)('%s', f => {
    expect(hardcodedStrings(path.join(__dirname, '..', f)).map(h => `${f}:${h.line} ${h.text}`)).toEqual([])
  })

  it('holds the same keys and placeholders in both languages', () => {
    expect(Object.keys(ar).sort()).toEqual(Object.keys(en).sort())
    const names = (s: string) => [...new Set([...s.matchAll(/\{(\w+)/g)].map(m => m[1]))].sort().join()
    const keys = Object.keys(en) as (keyof typeof en)[]
    expect(keys.filter(k => names(en[k]) !== names(ar[k]))).toEqual([])
  })
})
