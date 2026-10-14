import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { DirectionProvider } from '../../contexts/DirectionContext'
import { DifferenceDialog } from './ViewerKit'
import { differenceApi, type DifferenceCheck } from '../../services/api'
import { en, ar } from '../../i18n/builder/stats'

vi.mock('../../services/api', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  differenceApi: { check: vi.fn() },
}))

/** QA4 T5: the body of "Is this difference real?" in Arabic. */
const RESPONSE: DifferenceCheck = {
  population: { rows_a: 2200, rows_b: 1900, group_a: 'Development', group_b: 'Sales', dimension: 'department', measure: null, aggregation: 'count' },
  summary: 'Statistically significant difference in how many rows Development and Sales have (p < 0.001), with a negligible statistical effect size. Development has 300 more rows than Sales (+15.8%).',
  tests: [{
    question: 'row counts', test: 'Exact binomial test (even split)', p_value: 0.000001, p_text: 'p < 0.001', significant: true,
    effect_name: 'cohens_h', effect_size: 0.07, effect_label: 'negligible', values: { Development: 2200, Sales: 1900 },
    sentence: 'Statistically significant difference in how many rows Development and Sales have (p < 0.001), with a negligible statistical effect size.',
    business: { absolute: 300, percent: 15.8, sentence: 'Development has 300 more rows than Sales (+15.8%).' },
  }],
  caveats: [
    "Tested on the 4,100 rows behind these two bars, after this chart's filters.",
    "Significance at 5%; with many rows, tiny differences are 'significant'. The effect size says how much the groups overlap; the size of the gap says how much it matters.",
    'An observed difference, not a cause.',
  ],
}

const open = () => render(<DirectionProvider>
  <DifferenceDialog datasetId={1} dimension="department" measure={null} aggregation="count" filters={[]}
    names={['Development', 'Sales']} initial={['Development', 'Sales']} onClose={() => {}} />
</DirectionProvider>)

describe('the difference check body in Arabic (QA4 T5)', () => {
  beforeEach(() => {
    localStorage.setItem('datalytics.language', 'ar')
    vi.mocked(differenceApi.check).mockResolvedValue(RESPONSE)
  })
  afterEach(() => localStorage.removeItem('datalytics.language'))

  it('holds the same keys and placeholders in both languages', () => {
    expect(Object.keys(ar).sort()).toEqual(Object.keys(en).sort())
    const names = (s: string) => [...s.matchAll(/\{(\w+)\}/g)].map(m => m[1]).sort().join()
    const keys = Object.keys(en) as (keyof typeof en)[]
    expect(keys.filter(k => names(en[k]) !== names(ar[k]))).toEqual([])
    expect(keys.every(k => k.startsWith('bc.stats.'))).toBe(true)
  })

  it('keeps each part of the evidence line in its own isolate, so right-to-left cannot reorder it (QA5b S6)', async () => {
    open()
    const chip = await screen.findByTestId('evidence-chip')
    const isolates = [...chip.querySelectorAll('bdi')].map(b => [b.getAttribute('dir'), b.textContent])
    expect(isolates).toEqual([
      [null, 'اختبار ذي الحدين الدقيق (تقسيم متساوٍ)'],
      ['ltr', 'p < 0.001'],
      // QA6 A7: the statistic and its value in ONE isolate -- "(Cohen's h 0.07)".
      ['ltr', "Cohen's h 0.07"],
    ])
    expect(chip.textContent).toBe("اختبار ذي الحدين الدقيق (تقسيم متساوٍ) · p < 0.001 · أثر ضئيل (Cohen's h 0.07)")
  })

  it('translates the labels, the verdict and the footnotes; the server sentences keep dir="auto"', async () => {
    open()
    const result = await screen.findByTestId('difference-result')
    expect(screen.getByText('عدد الصفوف')).toBeInTheDocument()
    expect(screen.queryByText('row counts')).toBeNull()
    // The effect word, in the gap grid and the chip.
    expect(screen.getByText(/^ضئيل — /)).toBeInTheDocument()
    expect(screen.getByTestId('evidence-chip').textContent).toContain('أثر ضئيل')
    // The verdict, composed from the numbers, with the p-value in an LTR isolate.
    expect(result.textContent).toContain('يوجد فرق ذو دلالة إحصائية بين عدد صفوف Development وعدد صفوف Sales (p < 0.001)')
    const p = [...result.querySelectorAll('bdi[dir="ltr"]')].find(b => b.textContent === 'p < 0.001')
    expect(p).toBeTruthy()
    // The footnotes.
    expect(screen.getByText('فرق مُلاحَظ، لا علاقة سببية.')).toBeInTheDocument()
    const tested = [...result.querySelectorAll('li')].find(li => li.textContent?.startsWith('اختُبرت الصفوف'))
    expect(tested?.querySelector('bdi[dir="ltr"]')?.textContent).toBe('4,100')
    expect(result.textContent).not.toMatch(/Tested on|Significance at|An observed difference/)
    // QA6 A7: the gap is composed in Arabic from the server's numbers, and the
    // English summary (which the verdict and the gap already say) is not shown.
    const gap = screen.getByTestId('difference-business').querySelector('b')!
    expect(gap.textContent).toBe('عدد صفوف Development يزيد على عدد صفوف Sales بمقدار 300 (+15.8%).')
    expect([...gap.querySelectorAll('bdi[dir="ltr"]')].map(b => b.textContent)).toEqual(['300', '+15.8%'])
    expect(result.textContent).not.toContain('Development has 300 more rows')
    expect(result.textContent).not.toContain('Statistically significant difference')
  })

  it('composes an average gap in Arabic, lower and with its two values (QA6 A7)', async () => {
    vi.mocked(differenceApi.check).mockResolvedValue({ ...RESPONSE,
      population: { ...RESPONSE.population, measure: 'salary', aggregation: 'mean' },
      tests: [{ ...RESPONSE.tests[0], question: 'typical row', test: "Welch's t-test", effect_name: 'cohens_d', effect_size: -0.0119,
        values: { Development: 5120.4, Sales: 5400 },
        business: { absolute: -279.6, percent: -5.18, sentence: 'Average salary: Development 5,120 vs Sales 5,400 -- 280 lower (−5.2%).' } }] })
    open()
    await screen.findByTestId('difference-result')
    expect(screen.getByTestId('difference-business').querySelector('b')!.textContent)
      .toBe('متوسط salary: Development 5,120 مقابل Sales 5,400، أقل بمقدار 280 (−5.2%).')
    expect(screen.getByTestId('evidence-chip').textContent).toContain("(Cohen's d -0.0119)")
  })

  it('in English shows the server sentences exactly as sent', async () => {
    localStorage.setItem('datalytics.language', 'en')
    open()
    await waitFor(() => expect(screen.getByTestId('difference-result')).toBeTruthy())
    expect(screen.getByText('row counts')).toBeInTheDocument()
    expect(screen.getByText(RESPONSE.tests[0].sentence)).toBeInTheDocument()
    expect(screen.getByText(RESPONSE.caveats[2])).toBeInTheDocument()
    expect(screen.getByText(/200 rows of Development and 1,900 of Sales/)).toBeInTheDocument()
  })
})
